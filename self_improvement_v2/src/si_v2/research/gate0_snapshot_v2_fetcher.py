"""Gate-0 snapshot v2 fetcher — warm-up + selection + sealed holdout + funding (#693).

This module builds the immutable Bitget USDT-FUTURES dataset v2 for
``FreqForge_Gate0_Core_v1`` evaluation (manifest v3, ``gate0-manifest-v3-20260721``):

- 15m candles for BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT over
  2024-12-01T00:00:00Z .. 2026-07-01T00:00:00Z (half-open ``[start, end)``),
  fetched from the public ``history-candles`` endpoint (reusing the v1 fetcher);
- funding-rate history from the public ``history-fund-rate`` endpoint;
- deterministic 15m -> 1h derivation (reusing ``aggregate_to_1h``) with an
  explicit incomplete-hour report;
- physical selection / holdout split under ``/opt/data/gate0-snapshot-v2/``;
- quality gates, fetch audit JSONL, completion report and holdout seal.

**Safety boundary:** public read-only endpoints only. No credentials, no
private endpoints, no strategy execution, no evaluation, no holdout
inspection. All network access is injected via ``http_get`` so tests never
touch real endpoints. The orchestrator runs only under a valid, unexpired
``APPROVED_A2_BITGET_SNAPSHOT_V2`` marker (fail-closed validation).
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import itertools
import json
import logging
import math
import os
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from si_v2.research.evaluation_bundle_v1 import CandleV1
from si_v2.research.gate0_evaluation_integration import aggregate_to_1h
from si_v2.research.gate0_snapshot_fetcher import (
    BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RATE_LIMIT_RPS,
    DEFAULT_RETRY_BASE_DELAY,
    HttpGet,
    SnapshotFetchError,
    _default_http_get,
    _retry_request,
    dedup_and_sort,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical constants (mirror manifest v3 + #693 contract)
# ---------------------------------------------------------------------------

# Default immutable dataset root for snapshot v2.
DEFAULT_SNAPSHOT_V2_DIR = Path("/opt/data/gate0-snapshot-v2")

FUNDING_ENDPOINT = "/api/v2/mix/market/history-fund-rate"
HISTORY_ENDPOINT_V2 = "/api/v2/mix/market/history-candles"
FUNDING_PAGE_SIZE = 100
MAX_FUNDING_PAGES = 1000  # hard guard against runaway pagination (~8h cadence, 19 months)

PAIRS: tuple[str, ...] = (
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
)

# Bitget mix symbol (no settlement suffix) per canonical pair.
PAIR_TO_SYMBOL: dict[str, str] = {
    "BTC/USDT:USDT": "BTCUSDT",
    "ETH/USDT:USDT": "ETHUSDT",
    "SOL/USDT:USDT": "SOLUSDT",
}

# Stable file-label per canonical pair (matches v1 snapshot naming).
PAIR_TO_LABEL: dict[str, str] = {
    "BTC/USDT:USDT": "BTC_USDT",
    "ETH/USDT:USDT": "ETH_USDT",
    "SOL/USDT:USDT": "SOL_USDT",
}

PRODUCT_TYPE = "USDT-FUTURES"
TIMEFRAME_15M = "15m"
TIMEFRAME_1H = "1h"

# Half-open partition windows [start, end) — manifest v3 (gate0-manifest-v3-20260721).
WARMUP_START = datetime(2024, 12, 1, tzinfo=UTC)
SELECTION_START = datetime(2025, 1, 1, tzinfo=UTC)  # calibration start
WF1_START = datetime(2025, 7, 1, tzinfo=UTC)
WF2_START = datetime(2025, 10, 1, tzinfo=UTC)
HOLDOUT_START = datetime(2026, 1, 1, tzinfo=UTC)
DATASET_END = datetime(2026, 7, 1, tzinfo=UTC)

PARTITION_WINDOWS: tuple[tuple[str, datetime, datetime], ...] = (
    ("warmup", WARMUP_START, SELECTION_START),
    ("calibration", SELECTION_START, WF1_START),
    ("walk_forward_1", WF1_START, WF2_START),
    ("walk_forward_2", WF2_START, HOLDOUT_START),
    ("holdout", HOLDOUT_START, DATASET_END),
)

# Funding cadence used only for expected-count reporting (8h). Quality gates
# treat funding as pass when rows are sorted, duplicate-free and in-window.
FUNDING_INTERVAL_HOURS = 8

MAX_MISSING_RATIO = 0.05  # manifest v3: floor(total_expected * 0.05) / 5 % rule

# Required marker fields (fail-closed; no interpretation).
REQUIRED_MARKER_FIELDS: tuple[str, ...] = (
    "name",
    "issued_by",
    "host",
    "execution_class",
    "purpose",
    "approval_scope",
    "live_trading",
    "dry_run_false",
    "valid_until",
)
MARKER_NAME = "APPROVED_A2_BITGET_SNAPSHOT_V2"

# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class SnapshotV2Error(RuntimeError):
    """Base error for snapshot v2 orchestration."""


class A2MarkerError(SnapshotV2Error):
    """Raised when the A2 marker is missing, invalid, expired, or out of scope.

    ``code`` is one of ``MISSING_MARKER``, ``INVALID_MARKER``,
    ``EXPIRED_MARKER``, ``WRONG_SCOPE``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class PathEscapeError(SnapshotV2Error):
    """Raised when a resolved path escapes the designated dataset root."""


# ---------------------------------------------------------------------------
# Funding rate model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FundingRateV1:
    """One settled funding event (public Bitget history-fund-rate row)."""

    symbol: str
    funding_time: datetime
    funding_rate: float

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must be non-empty")
        if not math.isfinite(self.funding_rate):
            raise ValueError(f"funding_rate must be finite, got {self.funding_rate}")


def normalize_funding_row(raw_row: object, symbol: str) -> FundingRateV1:
    """Convert a raw Bitget funding row (dict or array form) to FundingRateV1.

    Bitget ``history-fund-rate`` rows are dicts
    ``{"symbol", "fundingRate", "fundingTime"}`` (verified live). Array rows
    ``[symbol, fundingRate, fundingTime]`` are accepted for backward
    compatibility with the v1-style snapshot format.
    """
    if isinstance(raw_row, dict):
        return FundingRateV1(
            symbol=str(raw_row.get("symbol") or symbol),
            funding_time=datetime.fromtimestamp(
                int(float(raw_row["fundingTime"])) / 1000.0, tz=UTC
            ),
            funding_rate=float(raw_row["fundingRate"]),
        )
    if isinstance(raw_row, (list, tuple)):
        if len(raw_row) < 3:
            raise ValueError(f"malformed funding row: {raw_row!r}")
        return FundingRateV1(
            symbol=str(raw_row[0]) or symbol,
            funding_time=datetime.fromtimestamp(
                int(float(raw_row[2])) / 1000.0, tz=UTC
            ),
            funding_rate=float(raw_row[1]),
        )
    raise ValueError(f"unsupported funding row type: {type(raw_row).__name__}")


def dedup_and_sort_funding(rows: Sequence[FundingRateV1]) -> list[FundingRateV1]:
    """Deduplicate by ``(symbol, funding_time)`` and sort ascending by time."""
    seen: dict[tuple[str, datetime], FundingRateV1] = {}
    for row in rows:
        seen[(row.symbol, row.funding_time)] = row
    return sorted(seen.values(), key=lambda r: (r.symbol, r.funding_time))


def _parse_funding_response(body: str, symbol: str) -> list[FundingRateV1]:
    """Parse a Bitget history-fund-rate response into funding rows."""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SnapshotFetchError(f"Invalid JSON response: {exc}") from exc
    if payload.get("code") != "00000":
        raise SnapshotFetchError(
            f"Bitget error code {payload.get('code')!r}: {str(payload.get('msg'))[:200]}"
        )
    raw_rows = payload.get("data", [])
    rows: list[FundingRateV1] = []
    for raw in raw_rows:
        try:
            rows.append(normalize_funding_row(raw, symbol))
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotFetchError(
                f"malformed funding row {raw!r}: {exc}"
            ) from exc
    return rows


def fetch_history_funding(
    *,
    symbol: str,
    product_type: str,
    start: datetime,
    end: datetime,
    http_get: HttpGet | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_BASE_DELAY,
    rate_limit_rps: int = DEFAULT_RATE_LIMIT_RPS,
) -> list[FundingRateV1]:
    """Fetch historical funding rates for one symbol over ``[start, end)``.

    Bitget's ``history-fund-rate`` endpoint ignores ``startTime``/``endTime``
    (verified against the live API) and paginates backward via ``idLessThan``
    (the millisecond ``fundingTime`` of the oldest row on the previous page).
    The client filters rows to ``[start, end)`` and stops as soon as a page's
    oldest row predates ``start`` (or an empty page / no progress is seen).

    Public read-only endpoint; no credentials.
    """
    if http_get is None:
        http_get = _default_http_get

    headers: dict[str, str] = {"Accept": "application/json"}
    min_interval = 1.0 / rate_limit_rps if rate_limit_rps > 0 else 0

    all_rows: list[FundingRateV1] = []
    cursor: int | None = None  # idLessThan: exclusive fundingTime cursor (ms)
    pages = 0

    while pages < MAX_FUNDING_PAGES:
        pages += 1
        params: dict[str, str] = {
            "symbol": symbol,
            "productType": product_type,
            "pageSize": str(FUNDING_PAGE_SIZE),
        }
        if cursor is not None:
            params["idLessThan"] = str(cursor)

        status, body = _retry_request(
            http_get, BASE_URL + FUNDING_ENDPOINT, params, headers,
            max_retries, retry_delay,
        )
        if status != 200:
            raise SnapshotFetchError(
                f"HTTP {status} from {FUNDING_ENDPOINT}: {body[:200]}"
            )

        page_rows = _parse_funding_response(body, symbol)
        in_window = [r for r in page_rows if start <= r.funding_time < end]
        all_rows.extend(in_window)

        if not page_rows:
            break  # no more data
        oldest_time = min(r.funding_time for r in page_rows)
        if oldest_time < start:
            break  # fully before the requested window
        next_cursor = int(oldest_time.timestamp() * 1000)
        if cursor is not None and next_cursor >= cursor:
            # No backward progress — avoid an infinite loop on a misbehaving API.
            break
        cursor = next_cursor

        if min_interval > 0:
            time.sleep(min_interval)

    return dedup_and_sort_funding(all_rows)


# ---------------------------------------------------------------------------
# Candle fetch (overlap pagination — no lost candles)
# ---------------------------------------------------------------------------

MAX_QUERY_RANGE_DAYS_V2 = 90
TIMEFRAME_TO_SECONDS: dict[str, int] = {"15m": 900, "1h": 3600}


def _split_into_sub_ranges_v2(
    start: datetime, end: datetime, max_days: int = MAX_QUERY_RANGE_DAYS_V2
) -> list[tuple[datetime, datetime]]:
    """Split ``[start, end)`` into half-open sub-ranges of at most ``max_days``."""
    step = timedelta(days=max_days)
    ranges: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        next_boundary = min(cursor + step, end)
        ranges.append((cursor, next_boundary))
        cursor = next_boundary
    return ranges


def fetch_history_candles_v2(
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
    """Fetch 15m candles with **overlap** backward pagination (no lost rows).

    Unlike the v1 fetcher (which moves the cursor one timeframe step *behind*
    the oldest candle of each page and therefore drops one candle per page
    boundary on strictly exclusive ``endTime`` semantics), this fetcher keeps
    the cursor at the oldest timestamp of the page and lets the dedup pass
    remove the one-candle overlap. This is lossless under both inclusive and
    exclusive server-side ``endTime`` semantics.

    Public read-only endpoint; no credentials. Retries 429/5xx with
    exponential backoff via the shared retry helper.
    """
    from si_v2.research.gate0_snapshot_fetcher import normalize_candles

    if http_get is None:
        http_get = _default_http_get

    headers: dict[str, str] = {"Accept": "application/json"}
    min_interval = 1.0 / rate_limit_rps if rate_limit_rps > 0 else 0

    all_candles: list[CandleV1] = []
    for sub_start, sub_end in _split_into_sub_ranges_v2(start, end):
        cursor_end = sub_end
        while cursor_end > sub_start:
            params: dict[str, str] = {
                "symbol": symbol,
                "productType": product_type,
                "granularity": timeframe,
                "endTime": str(int(cursor_end.timestamp() * 1000)),
                "limit": "200",
            }
            status, body = _retry_request(
                http_get, BASE_URL + HISTORY_ENDPOINT_V2, params, headers,
                max_retries, retry_delay,
            )
            if status != 200:
                raise SnapshotFetchError(
                    f"HTTP {status} from {HISTORY_ENDPOINT_V2}: {body[:200]}"
                )
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise SnapshotFetchError(f"Invalid JSON response: {exc}") from exc

            raw_candles = payload.get("data", [])
            if not raw_candles:
                break
            page_candles = normalize_candles(raw_candles, pair=pair, timeframe=timeframe)
            all_candles.extend(page_candles)
            if len(raw_candles) < 200:
                break

            oldest_ts = min(c.timestamp for c in page_candles)
            if oldest_ts <= sub_start:
                break
            # Overlap: keep the cursor AT the oldest timestamp (no tf step
            # subtraction) so the candle immediately before the page boundary
            # is included on the next page; dedup removes the one overlap.
            cursor_end = oldest_ts
            if min_interval > 0:
                time.sleep(min_interval)

    return dedup_and_sort(all_candles)


def confine_path(root: Path, *parts: str) -> Path:
    """Resolve ``root / parts`` and fail closed if it escapes ``root``."""
    root_resolved = root.expanduser().resolve()
    candidate = root_resolved.joinpath(*parts)
    resolved = candidate.resolve(strict=False)
    if resolved != root_resolved and not str(resolved).startswith(str(root_resolved) + os.sep):
        raise PathEscapeError(
            f"SNAPSHOT_V2_PATH_ESCAPE: {resolved} escapes {root_resolved}"
        )
    return resolved


# ---------------------------------------------------------------------------
# Deterministic 1h derivation with incomplete-hour reporting
# ---------------------------------------------------------------------------


def detect_incomplete_hours(candles_15m: Sequence[CandleV1]) -> list[dict[str, object]]:
    """Report hours that do not contain all four 15m slots.

    Deterministic: for each UTC hour present in the candle set, compare the
    observed 15m slots against ``{00, 15, 30, 45}``. Hours with missing or
    extra slots are returned as report rows. ``aggregate_to_1h`` drops such
    hours; this report makes that drop explicit and auditable.
    """
    from collections import defaultdict

    grouped: dict[datetime, set[datetime]] = defaultdict(set)
    for c in candles_15m:
        hour_key = c.timestamp.replace(minute=0, second=0, microsecond=0)
        grouped[hour_key].add(c.timestamp)

    expected_slots = {0, 15, 30, 45}
    rows: list[dict[str, object]] = []
    for hour_key in sorted(grouped):
        actual_minutes = {ts.minute for ts in grouped[hour_key]}
        missing = sorted(expected_slots - actual_minutes)
        extra = sorted(actual_minutes - expected_slots)
        if missing or extra:
            rows.append(
                {
                    "hour": hour_key.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "candle_count": len(grouped[hour_key]),
                    "missing_slots": missing,
                    "extra_slots": extra,
                }
            )
    return rows


def derive_1h_candles(
    candles_15m: Sequence[CandleV1],
) -> tuple[list[CandleV1], list[dict[str, object]]]:
    """Deterministically derive 1h OHLCV from 15m candles.

    Reuses the canonical ``aggregate_to_1h`` (UTC boundaries, four full 15m
    candles per hour, open=first, high=max, low=min, close=last, volume=sum;
    incomplete hours are dropped) and additionally reports every dropped
    incomplete hour. A second run over the same input yields byte-identical
    output.
    """
    hourly = aggregate_to_1h(list(candles_15m))
    incomplete = detect_incomplete_hours(candles_15m)
    return hourly, incomplete


# ---------------------------------------------------------------------------
# Atomic writers with SHA-256 sidecars
# ---------------------------------------------------------------------------


def write_gz_csv_atomic(
    rows: Sequence[Sequence[object]],
    header: Sequence[str],
    target_dir: Path,
    filename: str,
) -> str:
    """Write a gzipped CSV atomically (temp file + rename) and return its SHA-256."""
    target = confine_path(target_dir, filename)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Deterministic gzip: mtime=0 so byte-identical output is reproducible.
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        writer = csv.writer(text)
        writer.writerow(list(header))
        for row in rows:
            writer.writerow([str(v) for v in row])
        text.flush()

    tmp_fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "wb") as raw:
            raw.write(buffer.getvalue())
        os.rename(tmp_path, target)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    write_sidecar(target.parent, filename, digest)
    return digest


def write_json_atomic(data: dict[str, object] | list[object], target_dir: Path, filename: str) -> str:
    """Write a JSON document atomically and return its SHA-256."""
    target = confine_path(target_dir, filename)
    target.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.rename(tmp_path, target)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    write_sidecar(target.parent, filename, digest)
    return digest


def write_sidecar(target_dir: Path, filename: str, digest: str) -> None:
    """Write a ``<filename>.sha256`` sidecar next to ``filename``."""
    sidecar = confine_path(target_dir, f"{filename}.sha256")
    tmp_fd, tmp_path = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            f.write(f"{digest}  {filename}\n")
        os.rename(tmp_path, sidecar)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------


def expected_15m_count(window_start: datetime, window_end: datetime) -> int:
    """Number of 15m slots in a half-open window."""
    return max(0, int((window_end - window_start).total_seconds() // 900))


def run_quality_checks(
    candles: Sequence[CandleV1],
    *,
    pair: str,
    timeframe: str,
    window_label: str,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, object]:
    """Run the standard quality gates for one dataset slice.

    Gates: in-window containment, no duplicates, strictly monotonic
    timestamps, missing ratio vs. expected count (15m only; other timeframes
    report ``expected_count=null``). Returns a JSON-serializable report dict.
    """
    sorted_candles = sorted(candles, key=lambda c: c.timestamp)
    timestamps = [c.timestamp for c in sorted_candles]

    out_of_window = [c for c in sorted_candles if not (window_start <= c.timestamp < window_end)]
    duplicate_count = len(timestamps) - len(set(timestamps))
    # Monotonicity is checked on the ORIGINAL input order — sorting first
    # would hide out-of-order input.
    non_monotonic = 0
    for prev, cur in itertools.pairwise(candles):
        if cur.timestamp <= prev.timestamp:
            non_monotonic += 1

    expected = expected_15m_count(window_start, window_end) if timeframe == TIMEFRAME_15M else None
    missing_ratio = None
    if expected is not None:
        missing = max(0, expected - len(set(timestamps)))
        missing_ratio = round(missing / expected, 6) if expected else 0.0

    return {
        "pair": pair,
        "timeframe": timeframe,
        "window": window_label,
        "window_start": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_end": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "record_count": len(sorted_candles),
        "unique_count": len(set(timestamps)),
        "expected_count": expected,
        "missing_ratio": missing_ratio,
        "duplicate_count": duplicate_count,
        "non_monotonic_count": non_monotonic,
        "out_of_window_count": len(out_of_window),
        "first_timestamp": timestamps[0].strftime("%Y-%m-%dT%H:%M:%SZ") if timestamps else None,
        "last_timestamp": timestamps[-1].strftime("%Y-%m-%dT%H:%M:%SZ") if timestamps else None,
        "pass": (
            len(out_of_window) == 0
            and duplicate_count == 0
            and non_monotonic == 0
            and (missing_ratio is None or missing_ratio <= MAX_MISSING_RATIO)
        ),
    }


def run_funding_quality_checks(
    rows: Sequence[FundingRateV1],
    *,
    symbol: str,
    window_label: str,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, object]:
    """Quality gates for funding rows: sorted, duplicate-free, in-window."""
    sorted_rows = sorted(rows, key=lambda r: r.funding_time)
    timestamps = [r.funding_time for r in sorted_rows]
    out_of_window = [r for r in sorted_rows if not (window_start <= r.funding_time < window_end)]
    duplicate_count = len(timestamps) - len(set(timestamps))
    # Monotonicity is checked on the ORIGINAL input order.
    non_monotonic = 0
    for prev, cur in itertools.pairwise(rows):
        if cur.funding_time <= prev.funding_time:
            non_monotonic += 1

    span_hours = (window_end - window_start).total_seconds() / 3600.0
    expected = int(span_hours // FUNDING_INTERVAL_HOURS) if span_hours > 0 else 0

    return {
        "pair": symbol,
        "timeframe": "funding",
        "window": window_label,
        "window_start": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_end": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "record_count": len(sorted_rows),
        "unique_count": len(set(timestamps)),
        "expected_count_8h": expected,
        "duplicate_count": duplicate_count,
        "non_monotonic_count": non_monotonic,
        "out_of_window_count": len(out_of_window),
        "first_timestamp": timestamps[0].strftime("%Y-%m-%dT%H:%M:%SZ") if timestamps else None,
        "last_timestamp": timestamps[-1].strftime("%Y-%m-%dT%H:%M:%SZ") if timestamps else None,
        "pass": (
            len(out_of_window) == 0 and duplicate_count == 0 and non_monotonic == 0
        ),
    }


# ---------------------------------------------------------------------------
# Fetch audit (append-only JSONL, atomic-ish)
# ---------------------------------------------------------------------------


class FetchAuditLogger:
    """Append-only JSONL audit for the snapshot v2 run.

    Every network request and every major write step is recorded with a UTC
    timestamp. Rows are flushed and fsynced per record so a crash cannot lose
    the audit trail of already-completed requests.
    """

    def __init__(self, path: Path) -> None:
        self.path = confine_path(path.parent, path.name)

    def record(self, **fields: object) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


# ---------------------------------------------------------------------------
# Holdout seal
# ---------------------------------------------------------------------------


def seal_holdout(
    holdout_dir: Path,
    *,
    snapshot_id: str,
    created_at_utc: datetime,
    files: dict[str, str],
    manifest_sha256: str,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, object]:
    """Write ``holdout_seal.json`` (+ sidecar) over the sealed holdout files.

    ``files`` maps dataset-relative file paths to their SHA-256 digests.
    The seal is deterministic given the same inputs (sorted file mapping).
    """
    seal: dict[str, object] = {
        "snapshot_id": snapshot_id,
        "seal_type": "holdout",
        "created_at_utc": created_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_start": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_end": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "manifest_sha256": manifest_sha256,
        "files": [{"path": p, "sha256": h} for p, h in sorted(files.items())],
    }
    digest = write_json_atomic(seal, holdout_dir, "holdout_seal.json")
    seal["seal_sha256"] = digest
    return seal


def verify_holdout_seal(holdout_dir: Path) -> dict[str, object]:
    """Verify every file listed in the holdout seal matches its recorded hash.

    Returns a report dict with ``ok``, the freshly computed ``seal_sha256``
    (of the seal file itself — matching the value recorded in the completion
    report) and per-file ``results``. Fails closed (``ok=False``) when the
    seal file, a listed file, or any hash is missing.
    """
    seal_path = confine_path(holdout_dir, "holdout_seal.json")
    if not seal_path.exists():
        return {"ok": False, "error": "HOLDOUT_SEAL_MISSING"}
    seal = json.loads(seal_path.read_text())
    seal_sha256 = hashlib.sha256(seal_path.read_bytes()).hexdigest()
    results: list[dict[str, object]] = []
    ok = True
    for entry in seal.get("files", []):
        rel = str(entry["path"])
        expected = str(entry["sha256"])
        try:
            actual_path = confine_path(holdout_dir, rel)
        except PathEscapeError:
            ok = False
            results.append({"path": rel, "ok": False, "error": "PATH_ESCAPE"})
            continue
        if not actual_path.exists():
            ok = False
            results.append({"path": rel, "ok": False, "error": "FILE_MISSING"})
            continue
        actual = hashlib.sha256(actual_path.read_bytes()).hexdigest()
        match = actual == expected
        ok = ok and match
        results.append({"path": rel, "ok": match})
    return {"ok": ok, "seal_sha256": seal_sha256, "results": results}


# ---------------------------------------------------------------------------
# A2 marker validation (fail-closed)
# ---------------------------------------------------------------------------


def validate_a2_marker(
    marker: dict[str, str] | None,
    *,
    now: datetime | None = None,
    required_scope: str = "ISSUE_693_ONLY",
) -> dict[str, str]:
    """Validate the snapshot v2 A2 marker. Fail closed on any deviation.

    Accepted marker fields are strings; the only tolerated extras are
    free-form documentation fields (they are ignored, never interpreted).
    """
    now = now or datetime.now(UTC)
    if not marker:
        raise A2MarkerError("MISSING_MARKER", "no A2 marker supplied")
    for field in REQUIRED_MARKER_FIELDS:
        if field not in marker:
            raise A2MarkerError(
                "INVALID_MARKER", f"missing marker field {field!r}"
            )
    if marker["name"] != MARKER_NAME:
        raise A2MarkerError(
            "INVALID_MARKER",
            f"marker name {marker['name']!r} != {MARKER_NAME!r}",
        )
    if marker.get("issued_by", "").lower() not in ("luke", "golukeenviro"):
        raise A2MarkerError(
            "INVALID_MARKER", f"issued_by {marker.get('issued_by')!r} not Luke"
        )
    if marker.get("host") != "HermesTrader":
        raise A2MarkerError("INVALID_MARKER", f"host {marker.get('host')!r} != HermesTrader")
    if marker.get("execution_class") != "A2":
        raise A2MarkerError(
            "INVALID_MARKER", f"execution_class {marker.get('execution_class')!r} != A2"
        )
    if marker.get("live_trading") != "PROHIBITED":
        raise A2MarkerError(
            "INVALID_MARKER", "live_trading must be PROHIBITED"
        )
    if marker.get("dry_run_false") != "PROHIBITED":
        raise A2MarkerError(
            "INVALID_MARKER", "dry_run_false must be PROHIBITED"
        )
    if marker.get("approval_scope") != required_scope:
        raise A2MarkerError(
            "WRONG_SCOPE",
            f"approval_scope {marker.get('approval_scope')!r} != {required_scope!r}",
        )
    try:
        valid_until = datetime.strptime(marker["valid_until"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
    except ValueError as exc:
        raise A2MarkerError(
            "INVALID_MARKER", f"valid_until {marker['valid_until']!r} not parseable"
        ) from exc
    if now >= valid_until:
        raise A2MarkerError(
            "EXPIRED_MARKER",
            f"marker expired at {valid_until.isoformat()} (now {now.isoformat()})",
        )
    return marker


# ---------------------------------------------------------------------------
# Dataset layout orchestration
# ---------------------------------------------------------------------------

LAYOUT_SUBDIRS = ("selection", "holdout-sealed")


def _candle_csv_rows(candles: Sequence[CandleV1]) -> list[list[object]]:
    return [
        [
            c.pair,
            c.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            c.open,
            c.high,
            c.low,
            c.close,
            c.volume,
        ]
        for c in sorted(candles, key=lambda c: c.timestamp)
    ]


def _funding_csv_rows(rows: Sequence[FundingRateV1]) -> list[list[object]]:
    return [
        [
            r.symbol,
            r.funding_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            r.funding_rate,
        ]
        for r in sorted(rows, key=lambda r: r.funding_time)
    ]


def build_snapshot_v2(
    *,
    target_root: Path,
    snapshot_id: str,
    marker: dict[str, str],
    http_get: HttpGet | None = None,
    rate_limit_rps: int = DEFAULT_RATE_LIMIT_RPS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_BASE_DELAY,
    now: datetime | None = None,
) -> dict[str, object]:
    """Build the full immutable snapshot v2 dataset under ``target_root``.

    Steps:
    1. Validate the A2 marker (fail-closed; expiry raises ``EXPIRED_MARKER``).
    2. Create the physical layout (selection/ and holdout-sealed/).
    3. Per pair: fetch 15m candles over the full range, split by holdout
       boundary, write selection and holdout-sealed candle files (15m + 1h).
    4. Per pair: fetch funding history, split, write funding files.
    5. Run quality gates per pair/timeframe/window; write quality report.
    6. Write fetch audit (JSONL), manifest, holdout seal and completion report.

    Returns a JSON-serializable summary dict. Raises on any failure; the
    dataset is never marked COMPLETE on partial failure.
    """
    now = now or datetime.now(UTC)
    validate_a2_marker(marker, now=now)

    root = target_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for sub in LAYOUT_SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    for sub in ("audit", "quality", "manifests", "reports"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    audit = FetchAuditLogger(root / "audit" / "fetch_audit.jsonl")
    audit.record(
        action="run_start",
        snapshot_id=snapshot_id,
        marker_name=marker["name"],
        marker_valid_until=marker["valid_until"],
        marker_comment_id=marker.get("comment_id"),
        target_root=str(root),
    )

    selection_15m_dir = root / "selection" / "market-15m"
    selection_1h_dir = root / "selection" / "market-1h"
    selection_funding_dir = root / "selection" / "funding"
    holdout_15m_dir = root / "holdout-sealed" / "market-15m"
    holdout_1h_dir = root / "holdout-sealed" / "market-1h"
    holdout_funding_dir = root / "holdout-sealed" / "funding"

    files: dict[str, str] = {}  # dataset-relative path -> sha256
    quality_reports: list[dict[str, object]] = []
    incomplete_hours_reports: list[dict[str, object]] = []
    errors: list[str] = []

    for pair in PAIRS:
        symbol = PAIR_TO_SYMBOL[pair]
        label = PAIR_TO_LABEL[pair]

        # --- 15m candles over the full dataset range ---
        audit.record(action="candles_fetch_start", pair=pair, symbol=symbol)
        try:
            candles_all = fetch_history_candles_v2(
                pair=pair,
                symbol=symbol,
                product_type=PRODUCT_TYPE,
                timeframe=TIMEFRAME_15M,
                start=WARMUP_START,
                end=DATASET_END,
                http_get=http_get,
                max_retries=max_retries,
                retry_delay=retry_delay,
                rate_limit_rps=rate_limit_rps,
            )
        except SnapshotFetchError as exc:
            audit.record(action="candles_fetch_error", pair=pair, error=str(exc))
            raise
        audit.record(
            action="candles_fetch_done", pair=pair,
            candle_count=len(candles_all),
        )

        selection_candles = [c for c in candles_all if c.timestamp < HOLDOUT_START]
        holdout_candles = [c for c in candles_all if c.timestamp >= HOLDOUT_START]

        # --- 15m files ---
        sel_digest = write_gz_csv_atomic(
            _candle_csv_rows(selection_candles),
            ["pair", "timestamp", "open", "high", "low", "close", "volume"],
            selection_15m_dir,
            f"{label}_{TIMEFRAME_15M}.csv.gz",
        )
        files[f"selection/market-15m/{label}_{TIMEFRAME_15M}.csv.gz"] = sel_digest

        hold_digest = write_gz_csv_atomic(
            _candle_csv_rows(holdout_candles),
            ["pair", "timestamp", "open", "high", "low", "close", "volume"],
            holdout_15m_dir,
            f"{label}_{TIMEFRAME_15M}.csv.gz",
        )
        files[f"holdout-sealed/market-15m/{label}_{TIMEFRAME_15M}.csv.gz"] = hold_digest

        # --- 1h derivation (deterministic, with incomplete-hour report) ---
        sel_1h, sel_incomplete = derive_1h_candles(selection_candles)
        hold_1h, hold_incomplete = derive_1h_candles(holdout_candles)
        for row in sel_incomplete:
            incomplete_hours_reports.append({"pair": pair, "partition": "selection", **row})
        for row in hold_incomplete:
            incomplete_hours_reports.append({"pair": pair, "partition": "holdout", **row})
        sel_1h_digest = write_gz_csv_atomic(
            _candle_csv_rows(sel_1h),
            ["pair", "timestamp", "open", "high", "low", "close", "volume"],
            selection_1h_dir,
            f"{label}_{TIMEFRAME_1H}.csv.gz",
        )
        files[f"selection/market-1h/{label}_{TIMEFRAME_1H}.csv.gz"] = sel_1h_digest
        hold_1h_digest = write_gz_csv_atomic(
            _candle_csv_rows(hold_1h),
            ["pair", "timestamp", "open", "high", "low", "close", "volume"],
            holdout_1h_dir,
            f"{label}_{TIMEFRAME_1H}.csv.gz",
        )
        files[f"holdout-sealed/market-1h/{label}_{TIMEFRAME_1H}.csv.gz"] = hold_1h_digest

        # Per-window quality for SELECTION windows only (warmup, calibration,
        # walk-forwards). The holdout window is checked separately below with
        # the physically separated holdout candles.
        for win_label, win_start, win_end in PARTITION_WINDOWS[:-1]:
            in_window = [
                c for c in selection_candles
                if win_start <= c.timestamp < win_end
            ]
            quality_reports.append(
                run_quality_checks(
                    in_window,
                    pair=pair,
                    timeframe=TIMEFRAME_15M,
                    window_label=win_label,
                    window_start=win_start,
                    window_end=win_end,
                )
            )
            quality_reports.append(
                run_quality_checks(
                    [c for c in sel_1h if win_start <= c.timestamp < win_end],
                    pair=pair,
                    timeframe=TIMEFRAME_1H,
                    window_label=win_label,
                    window_start=win_start,
                    window_end=win_end,
                )
            )
        quality_reports.append(
            run_quality_checks(
                holdout_candles,
                pair=pair,
                timeframe=TIMEFRAME_15M,
                window_label="holdout",
                window_start=HOLDOUT_START,
                window_end=DATASET_END,
            )
        )
        quality_reports.append(
            run_quality_checks(
                hold_1h,
                pair=pair,
                timeframe=TIMEFRAME_1H,
                window_label="holdout",
                window_start=HOLDOUT_START,
                window_end=DATASET_END,
            )
        )

        # --- funding ---
        audit.record(action="funding_fetch_start", symbol=symbol)
        try:
            funding_all = fetch_history_funding(
                symbol=symbol,
                product_type=PRODUCT_TYPE,
                start=WARMUP_START,
                end=DATASET_END,
                http_get=http_get,
                max_retries=max_retries,
                retry_delay=retry_delay,
                rate_limit_rps=rate_limit_rps,
            )
        except SnapshotFetchError as exc:
            audit.record(action="funding_fetch_error", symbol=symbol, error=str(exc))
            raise
        audit.record(
            action="funding_fetch_done", symbol=symbol,
            funding_count=len(funding_all),
        )

        sel_funding = [r for r in funding_all if r.funding_time < HOLDOUT_START]
        hold_funding = [r for r in funding_all if r.funding_time >= HOLDOUT_START]

        sel_fund_digest = write_gz_csv_atomic(
            _funding_csv_rows(sel_funding),
            ["symbol", "funding_time", "funding_rate"],
            selection_funding_dir,
            f"{label}_funding.csv.gz",
        )
        files[f"selection/funding/{label}_funding.csv.gz"] = sel_fund_digest
        hold_fund_digest = write_gz_csv_atomic(
            _funding_csv_rows(hold_funding),
            ["symbol", "funding_time", "funding_rate"],
            holdout_funding_dir,
            f"{label}_funding.csv.gz",
        )
        files[f"holdout-sealed/funding/{label}_funding.csv.gz"] = hold_fund_digest

        quality_reports.append(
            run_funding_quality_checks(
                sel_funding,
                symbol=symbol,
                window_label="selection",
                window_start=WARMUP_START,
                window_end=HOLDOUT_START,
            )
        )
        quality_reports.append(
            run_funding_quality_checks(
                hold_funding,
                symbol=symbol,
                window_label="holdout",
                window_start=HOLDOUT_START,
                window_end=DATASET_END,
            )
        )

    # --- quality report + gate ---
    quality_gate_pass = all(
        isinstance(r.get("pass"), bool) and r["pass"] for r in quality_reports
    )
    quality_digest = write_json_atomic(
        {
            "snapshot_id": snapshot_id,
            "created_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gate": "PASS" if quality_gate_pass else "FAIL",
            "reports": quality_reports,
            "incomplete_hours": incomplete_hours_reports,
        },
        root / "quality",
        "data_quality_report.json",
    )
    if not quality_gate_pass:
        errors.append("QUALITY_GATE_FAIL")

    # --- manifest (written exactly once, before the seal, so the seal can
    # reference a stable manifest hash; completion status lives in the
    # completion report to keep this file deterministic) ---
    manifest: dict[str, object] = {
        "snapshot_id": snapshot_id,
        "manifest_version": "snapshot-v2/1",
        "created_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "approval": {
            "marker_name": marker["name"],
            "marker_comment_id": marker.get("comment_id"),
            "marker_valid_until": marker["valid_until"],
            "approval_scope": marker.get("approval_scope"),
        },
        "host": marker.get("host"),
        "exchange": "bitget",
        "product_type": PRODUCT_TYPE,
        "market_type": "linear perpetual",
        "pairs": list(PAIRS),
        "timeframes": [TIMEFRAME_15M, TIMEFRAME_1H],
        "primary_timeframe": TIMEFRAME_15M,
        "informative_timeframe": TIMEFRAME_1H,
        "windows": [
            {"label": label, "start": s.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "end": e.strftime("%Y-%m-%dT%H:%M:%SZ")}
            for label, s, e in PARTITION_WINDOWS
        ],
        "files": [{"path": p, "sha256": h} for p, h in sorted(files.items())],
        "quality_report_sha256": quality_digest,
        "selection_holdout_isolation": {
            "selection_dir": "selection/",
            "holdout_dir": "holdout-sealed/",
            "selection_never_reads_holdout": True,
        },
        "errors": errors,
    }
    manifest_digest = write_json_atomic(
        manifest, root / "manifests", "snapshot_manifest.json"
    )

    # --- holdout seal (references the stable manifest hash; file paths are
    # relative to the holdout directory itself) ---
    holdout_files = {
        rel.removeprefix("holdout-sealed/"): digest
        for rel, digest in files.items()
        if rel.startswith("holdout-sealed/")
    }
    seal_holdout(
        root / "holdout-sealed",
        snapshot_id=snapshot_id,
        created_at_utc=now,
        files=holdout_files,
        manifest_sha256=manifest_digest,
        window_start=HOLDOUT_START,
        window_end=DATASET_END,
    )
    seal_verify = verify_holdout_seal(root / "holdout-sealed")
    if not seal_verify["ok"]:
        errors.append("HOLDOUT_SEAL_FAIL")

    # --- completion report (single source of completion status) ---
    completion = quality_gate_pass and not errors
    completion_digest = write_json_atomic(
        {
            "snapshot_id": snapshot_id,
            "created_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "completion_status": "COMPLETE" if completion else "INCOMPLETE",
            "errors": errors,
            "manifest_sha256": manifest_digest,
            "holdout_seal_sha256": seal_verify["seal_sha256"],
            "holdout_seal_verify": seal_verify["ok"],
            "quality_gate": "PASS" if quality_gate_pass else "FAIL",
        },
        root / "reports",
        "snapshot_completion_report.json",
    )

    audit.record(
        action="run_end",
        snapshot_id=snapshot_id,
        completion_status="COMPLETE" if completion else "INCOMPLETE",
        file_count=len(files),
        errors=errors,
    )

    return {
        "snapshot_id": snapshot_id,
        "target_root": str(root),
        "completion_status": "COMPLETE" if completion else "INCOMPLETE",
        "quality_gate": "PASS" if quality_gate_pass else "FAIL",
        "holdout_seal_verify": seal_verify["ok"],
        "file_count": len(files),
        "manifest_sha256": manifest_digest,
        "completion_report_sha256": completion_digest,
        "errors": errors,
    }
