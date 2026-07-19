"""Gate-0 snapshot fetcher for Bitget futures history-candles (C1, #653).

This module provides a tested, path-confined fetcher for the Gate-0 edge-
evidence snapshot. It fetches 15-minute candle data from Bitget's public
**history-candles** endpoint (not the short-history ``candles`` endpoint),
supports backward pagination, deduplication, atomic writes, and detached
manifest hashing.

**Safety boundary:** This is a research tool. It uses only public read-only
endpoints — no API credentials, no authenticated calls, no strategy execution,
no holdout inspection. All network access is injected via ``http_get`` so tests
never touch real endpoints.

The fetcher is **not executed** in this PR. It is present and tested but must
only run under an explicit ``APPROVED_A2_GATE0_SNAPSHOT_FETCH`` marker.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from si_v2.research.evaluation_bundle_v1 import CandleV1, canonical_candle_hash

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bitget API constants
# ---------------------------------------------------------------------------

BASE_URL = "https://api.bitget.com"
HISTORY_ENDPOINT = "/api/v2/mix/market/history-candles"
MAX_CANDLES_PER_REQUEST = 200
MAX_QUERY_RANGE_DAYS = 90
DEFAULT_RATE_LIMIT_RPS = 10
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY = 2.0  # seconds

# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class SnapshotFetchError(RuntimeError):
    """Raised when a snapshot fetch fails irrecoverably."""


# ---------------------------------------------------------------------------
# HTTP callable type
# ---------------------------------------------------------------------------

# http_get(url, params, headers) -> (status_code, body_text)
HttpGet = Callable[[str, dict[str, str], dict[str, str]], tuple[int, str]]


def _default_http_get(
    url: str, params: dict[str, str], headers: dict[str, str]
) -> tuple[int, str]:
    """Default HTTP GET using urllib (no external deps).

    This is only called at runtime under A2 authorization — never in tests.
    """
    import urllib.parse
    import urllib.request

    qs = urllib.parse.urlencode(params)
    full_url = f"{url}?{qs}" if qs else url
    req = urllib.request.Request(full_url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8")
    except Exception as exc:
        status = getattr(exc, "code", 0)
        body = getattr(exc, "read", lambda: b"")()
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        return int(status) if status else 0, body or str(exc)


# ---------------------------------------------------------------------------
# Candle normalization
# ---------------------------------------------------------------------------

_TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def _normalize_timestamp(ts_ms: int | float | str, timeframe: str = "15m") -> datetime:
    """Convert a millisecond timestamp to a UTC datetime snapped to the timeframe boundary."""
    seconds = int(float(ts_ms)) / 1000.0
    dt = datetime.fromtimestamp(seconds, tz=UTC)
    tf_seconds = _TIMEFRAME_SECONDS.get(timeframe, 900)
    snapped = int(dt.timestamp()) // tf_seconds * tf_seconds
    return datetime.fromtimestamp(snapped, tz=UTC)


def normalize_candles(
    raw_rows: Sequence[Sequence[str]],
    pair: str,
    timeframe: str = "15m",
) -> list[CandleV1]:
    """Convert raw Bitget candle arrays to CandleV1 objects.

    Raw format: ``[ts_ms, open, high, low, close, volume]`` as strings.

    Skips malformed rows (wrong length, non-numeric values). Raises on
    invalid OHLCV semantics (negative prices, inconsistent high/low) from
    CandleV1 validation — these are data-quality errors, not parse errors.
    """
    result: list[CandleV1] = []
    for row in raw_rows:
        if not row or len(row) < 6:
            continue
        try:
            ts = _normalize_timestamp(row[0], timeframe)
            o = float(row[1])
            hi = float(row[2])
            lo = float(row[3])
            c = float(row[4])
            vol = float(row[5])
        except (ValueError, TypeError):
            continue  # parse error — skip malformed row
        # CandleV1 validation raises ValueError on bad OHLCV semantics
        candle = CandleV1(
            pair=pair,
            timestamp=ts,
            open=o,
            high=hi,
            low=lo,
            close=c,
            volume=vol,
        )
        result.append(candle)
    return result


# ---------------------------------------------------------------------------
# Deduplication and sorting
# ---------------------------------------------------------------------------


def dedup_and_sort(candles: Sequence[CandleV1]) -> list[CandleV1]:
    """Remove duplicate (pair, timestamp) entries and sort chronologically."""
    seen: dict[tuple[str, datetime], CandleV1] = {}
    for c in candles:
        key = (c.pair, c.timestamp)
        seen[key] = c  # last write wins (idempotent)
    return sorted(seen.values(), key=lambda c: (c.pair, c.timestamp))


# ---------------------------------------------------------------------------
# Backward pagination fetch
# ---------------------------------------------------------------------------


def _split_into_sub_ranges(
    start: datetime, end: datetime, max_days: int = MAX_QUERY_RANGE_DAYS
) -> list[tuple[datetime, datetime]]:
    """Split a date range into sub-ranges of at most ``max_days`` days."""
    sub_ranges: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=max_days), end)
        sub_ranges.append((cursor, chunk_end))
        cursor = chunk_end
    return sub_ranges


def fetch_history_candles(
    *,
    pair: str,
    symbol: str,
    product_type: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    http_get: HttpGet | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_BASE_DELAY,
    rate_limit_rps: int = DEFAULT_RATE_LIMIT_RPS,
) -> list[CandleV1]:
    """Fetch candle data from Bitget's history-candles endpoint.

    Uses backward pagination: starts from ``end`` and walks backward in
    chunks of ``MAX_CANDLES_PER_REQUEST`` (200). Automatically splits the
    total date range into sub-ranges of at most ``MAX_QUERY_RANGE_DAYS`` (90)
    to comply with Bitget's query range limit.

    Retries on 429/5xx with exponential backoff. Raises ``SnapshotFetchError``
    if retries are exhausted.

    No authentication: only public read-only endpoints, no credentials.
    """
    if http_get is None:
        http_get = _default_http_get

    headers: dict[str, str] = {"Accept": "application/json"}
    # Explicitly no auth headers — public read-only only.

    all_candles: list[CandleV1] = []
    sub_ranges = _split_into_sub_ranges(start, end, MAX_QUERY_RANGE_DAYS)
    min_interval = 1.0 / rate_limit_rps if rate_limit_rps > 0 else 0

    for sub_start, sub_end in sub_ranges:
        # Backward pagination within each sub-range
        cursor_end = sub_end
        while cursor_end > sub_start:
            params: dict[str, str] = {
                "symbol": symbol,
                "productType": product_type,
                "granularity": timeframe,
                "endTime": str(int(cursor_end.timestamp() * 1000)),
                "limit": str(MAX_CANDLES_PER_REQUEST),
            }

            # Retry with exponential backoff
            status, body = _retry_request(
                http_get,
                BASE_URL + HISTORY_ENDPOINT,
                params,
                headers,
                max_retries,
                retry_delay,
            )

            if status != 200:
                raise SnapshotFetchError(
                    f"HTTP {status} from {HISTORY_ENDPOINT}: {body[:200]}"
                )

            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise SnapshotFetchError(f"Invalid JSON response: {exc}") from exc

            raw_candles = payload.get("data", [])
            if not raw_candles:
                break  # no more data in this direction

            page_candles = normalize_candles(raw_candles, pair=pair, timeframe=timeframe)
            all_candles.extend(page_candles)

            # If we got fewer than MAX, this was the last page
            if len(raw_candles) < MAX_CANDLES_PER_REQUEST:
                break

            # Move cursor backward to before the oldest candle in this page
            oldest_ts = min(c.timestamp for c in page_candles)
            cursor_end = oldest_ts - timedelta(seconds=_TIMEFRAME_SECONDS.get(timeframe, 900))

            if min_interval > 0:
                time.sleep(min_interval)

    return dedup_and_sort(all_candles)


def _retry_request(
    http_get: HttpGet,
    url: str,
    params: dict[str, str],
    headers: dict[str, str],
    max_retries: int,
    base_delay: float,
) -> tuple[int, str]:
    """Execute an HTTP request with exponential backoff retry on 429/5xx."""
    last_status, last_body = 0, ""
    for attempt in range(max_retries + 1):
        status, body = http_get(url, params, headers)
        if status == 200:
            return status, body
        if status == 429 or status >= 500:
            last_status, last_body = status, body
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                if delay > 0:
                    time.sleep(delay)
                continue
        # Non-retryable error
        if status == 429:
            raise SnapshotFetchError(f"rate limit (429) after {max_retries} retries: {body[:200]}")
        return status, body

    if last_status == 429:
        raise SnapshotFetchError(f"rate limit (429) after {max_retries} retries: {last_body[:200]}")
    if last_status >= 500:
        raise SnapshotFetchError(f"HTTP {last_status} after {max_retries} retries: {last_body[:200]}")
    return last_status, last_body


# ---------------------------------------------------------------------------
# Atomic snapshot writes
# ---------------------------------------------------------------------------


def write_snapshot(
    candles: Sequence[CandleV1],
    *,
    pair_label: str,
    target_dir: Path,
    timeframe: str = "15m",
) -> dict[str, str]:
    """Write candles to a gzipped CSV with SHA-256 sidecar and canonical hash.

    Uses atomic write: data is written to a temp file, then renamed.
    Returns a dict with ``path``, ``sha256``, and ``canonical_sha256`` paths.

    The ``target_dir`` must be the designated snapshot directory — no writes
    occur outside it.
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"{pair_label}_{timeframe}"
    csv_gz_path = target_dir / f"{base_name}.csv.gz"
    sha256_path = target_dir / f"{base_name}.csv.gz.sha256"
    canonical_path = target_dir / f"{base_name}.canonical_sha256"

    # Write to temp file then atomic rename
    tmp_fd, tmp_path = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
    try:
        with gzip.open(os.fdopen(tmp_fd, "wb"), "wt", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["pair", "timestamp", "open", "high", "low", "close", "volume"])
            for c in sorted(candles, key=lambda x: x.timestamp):
                writer.writerow([
                    c.pair,
                    c.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    c.open,
                    c.high,
                    c.low,
                    c.close,
                    c.volume,
                ])
        os.rename(tmp_path, csv_gz_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    # Per-file SHA-256 (content hash of the gzip file)
    file_hash = hashlib.sha256(csv_gz_path.read_bytes()).hexdigest()
    sha256_path.write_text(f"{file_hash}  {csv_gz_path.name}\n")

    # Canonical candle hash (compatible with evaluation_bundle_v1)
    ch = canonical_candle_hash(list(candles))
    canonical_path.write_text(f"{ch}\n")

    return {
        "path": str(csv_gz_path.relative_to(target_dir)),
        "sha256": file_hash,
        "canonical_sha256": ch,
    }


# ---------------------------------------------------------------------------
# Manifest with detached hash
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotManifest:
    """Immutable snapshot manifest (no self-hash field)."""

    snapshot_id: str
    exchange: str
    product_type: str
    pairs: tuple[str, ...]
    timeframe: str
    timerange_start: datetime
    timerange_end: datetime
    created_at_utc: datetime
    files: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timerange_start"] = self.timerange_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        d["timerange_end"] = self.timerange_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        d["created_at_utc"] = self.created_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        d["pairs"] = list(self.pairs)
        d["files"] = list(self.files)
        return d


def build_manifest(
    *,
    snapshot_id: str,
    exchange: str,
    pairs: tuple[str, ...],
    timeframe: str,
    timerange_start: datetime,
    timerange_end: datetime,
    snapshot_files: list[dict[str, Any]],
    target_dir: Path,
    product_type: str = "USDT-FUTURES",
) -> SnapshotManifest:
    """Write the snapshot manifest JSON and a detached SHA-256 sidecar.

    The manifest JSON contains NO ``overall_sha256`` field (circular hash
    problem). Instead, the SHA-256 of the manifest file is written to
    ``snapshot_manifest.json.sha256`` as a detached sidecar.
    """
    manifest = SnapshotManifest(
        snapshot_id=snapshot_id,
        exchange=exchange,
        product_type=product_type,
        pairs=pairs,
        timeframe=timeframe,
        timerange_start=timerange_start,
        timerange_end=timerange_end,
        created_at_utc=datetime.now(UTC),
        files=tuple(snapshot_files),
    )

    manifest_path = target_dir / "snapshot_manifest.json"
    detached_path = target_dir / "snapshot_manifest.json.sha256"

    # Atomic write: temp -> rename
    tmp_fd, tmp_path = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(manifest.to_dict(), f, indent=2, sort_keys=True)
        os.rename(tmp_path, manifest_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    # Detached hash (no circular dependency)
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    detached_path.write_text(f"{manifest_hash}  snapshot_manifest.json\n")

    return manifest
