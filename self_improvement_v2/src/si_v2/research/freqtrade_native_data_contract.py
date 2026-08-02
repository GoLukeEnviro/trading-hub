"""Freqtrade-native Bitget futures data contract (A1; no execution).

Defines the immutable, reproducible download contract for the Gate-0
selection backtest dataset:

- pinned image digest
- exchange = bitget (USDT-FUTURES, isolated)
- pairs = BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT
- timeranges (download full; selection view excludes holdout)
- data formats (feather)
- candle types (futures for OHLCV; mark + funding_rate auxiliary)
- timeframes (15m main, 1h auxiliary)
- datadir (host + container)
- required list-data coverage windows
- required file hashes (filled by the A2 download run; empty here)

No network operations. Everything here is pure constants + deterministic
validation so tests can run offline.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from si_v2.research.backtest_contract import (
    DATASET_END_UTC,
    FREQTRADE_NATIVE_DATA_DIR,
)

# ---------------------------------------------------------------------------
# Immutable contract constants
# ---------------------------------------------------------------------------

IMAGE_DIGEST = (
    "sha256:50720a4af314a812be2cfbf5cc6331c63e9332b06f3f4372241f54bc61a35486"
)
PINNED_IMAGE = f"freqtradeorg/freqtrade@{IMAGE_DIGEST}"
FREQTRADE_VERSION = "2026.6"
CONTAINER_REPORTED_VERSION = "2026.7"

EXCHANGE = "bitget"
TRADING_MODE = "futures"
MARGIN_MODE = "isolated"

PAIRS: tuple[str, ...] = (
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
)

# Main OHLCV timeframe
MAIN_TIMEFRAME = "15m"
# Auxiliary timeframes (mark + funding_rate)
AUX_TIMEFRAMES: tuple[str, ...] = ("1h",)

# Candle types
MAIN_CANDLE_TYPES: tuple[str, ...] = ("futures",)
AUX_CANDLE_TYPES: tuple[str, ...] = ("mark", "funding_rate")

# Data format
DATA_FORMAT_OHLCV = "feather"

# Download timerange (full dataset, warm-up through holdout end)
FULL_TIMERANGE_START = datetime(2024, 12, 1, tzinfo=UTC)
FULL_TIMERANGE_END = DATASET_END_UTC  # 2026-07-01
# Selection view (backtest) timerange — holdout excluded
SELECTION_TIMERANGE_END = datetime(2026, 1, 1, tzinfo=UTC)

HOST_DATA_DIR = FREQTRADE_NATIVE_DATA_DIR
CONTAINER_DATA_DIR = Path("/freqtrade/user_data/data")

# Required list-data coverage windows (inclusive lower bounds; the download
# run must cover at least these ranges per pair / candle type).
REQUIRED_COVERAGE: dict[str, dict[str, dict[str, str]]] = {
    # candle_type -> timeframe -> {from, to} (ISO, inclusive-ish)
    "futures": {
        "15m": {"from": "2024-12-01T00:00:00Z", "to": "2026-06-30T23:45:00Z"},
    },
    "mark": {
        "1h": {"from": "2024-12-01T00:00:00Z", "to": "2026-06-30T23:00:00Z"},
    },
    "funding_rate": {
        "1h": {"from": "2024-12-01T00:00:00Z", "to": "2026-06-30T23:00:00Z"},
    },
}

# Pair directory key used by Freqtrade on disk (lowercase, / -> _; the
# colon in the futures pair suffix is KEPT, matching Freqtrade layout).
def pair_dir_key(pair: str) -> str:
    return pair.replace("/", "_").lower()


PAIR_DIR_KEYS: tuple[str, ...] = tuple(pair_dir_key(p) for p in PAIRS)


def full_timerange() -> str:
    return (
        f"{FULL_TIMERANGE_START:%Y%m%d}-{FULL_TIMERANGE_END:%Y%m%d}"
    )


def selection_timerange() -> str:
    return (
        f"{FULL_TIMERANGE_START:%Y%m%d}-{SELECTION_TIMERANGE_END:%Y%m%d}"
    )


# ---------------------------------------------------------------------------
# Download command renderer (deterministic, no execution)
# ---------------------------------------------------------------------------


def render_download_command(
    *,
    candle_types: tuple[str, ...] = MAIN_CANDLE_TYPES,
    timeframes: tuple[str, ...] = (MAIN_TIMEFRAME,),
    timerange: str | None = None,
    datadir_host: Path | str = HOST_DATA_DIR,
    config_host: Path | str = "freqforge/user_data/config.example.json",
) -> str:
    """Render the exact pinned ``download-data`` command (A2-ready).

    Deterministic; never executed by this module. Mounts: datadir read-write
    (download writes), config read-only. No ``--erase``, no ``--prepend``,
    no ``--dl-trades``.
    """
    tr = timerange or full_timerange()
    pairs_line = " \\\n    ".join(PAIRS)
    ct_line = " ".join(candle_types)
    tf_line = " ".join(timeframes)
    return (
        "docker run --rm \\\n"
        "  --user 10000:10000 \\\n"
        f"  -v {datadir_host}:/freqtrade/user_data/data:rw \\\n"
        f"  -v {config_host}:/freqtrade/user_data/config.json:ro \\\n"
        f"  {PINNED_IMAGE} \\\n"
        "  download-data \\\n"
        "  --config /freqtrade/user_data/config.json \\\n"
        "  --datadir /freqtrade/user_data/data \\\n"
        "  --trading-mode futures \\\n"
        "  --pairs \\\n"
        f"    {pairs_line} \\\n"
        f"  --timeframes {tf_line} \\\n"
        f"  --candle-types {ct_line} \\\n"
        f"  --timerange {tr} \\\n"
        "  --data-format-ohlcv feather \\\n"
        "  --no-parallel-download"
    )


def render_list_data_command(
    *,
    datadir_host: Path | str = HOST_DATA_DIR,
    config_host: Path | str = "freqforge/user_data/config.example.json",
) -> str:
    """Render the pinned ``list-data`` verification command (read-only)."""
    return (
        "docker run --rm \\\n"
        "  --user 10000:10000 \\\n"
        f"  -v {datadir_host}:/freqtrade/user_data/data:ro \\\n"
        f"  -v {config_host}:/freqtrade/user_data/config.json:ro \\\n"
        f"  {PINNED_IMAGE} \\\n"
        "  list-data \\\n"
        "  --config /freqtrade/user_data/config.json \\\n"
        "  --datadir /freqtrade/user_data/data \\\n"
        "  --trading-mode futures \\\n"
        "  --data-format-ohlcv feather \\\n"
        "  --show-timerange"
    )


# ---------------------------------------------------------------------------
# list-data coverage parser + fail-closed validation
# ---------------------------------------------------------------------------

# Marker lines emitted by ``freqtrade list-data --show-timerange``.
# Example (2026.7):
#   btc_usdt:usdt 15m futures  2024-12-01 00:00:00 -> 2026-06-30 23:45:00
# We parse a compact, documented format so tests can run offline.
COVERAGE_LINE_PREFIX = "freqtrade_native_coverage "


def coverage_line(
    pair: str, timeframe: str, candle_type: str, first: str, last: str
) -> str:
    """Deterministic coverage line (documented parser input for tests)."""
    return (
        f"{COVERAGE_LINE_PREFIX}{pair} {timeframe} {candle_type} "
        f"{first} {last}"
    )


def parse_coverage_line(line: str) -> dict[str, str] | None:
    """Parse a coverage line into ``{pair, timeframe, candle_type, first,
    last}``. Returns None for non-coverage lines."""
    if not line.startswith(COVERAGE_LINE_PREFIX):
        return None
    parts = line[len(COVERAGE_LINE_PREFIX):].split()
    if len(parts) != 5:
        raise ValueError(f"MALFORMED_COVERAGE_LINE: {line!r}")
    return {
        "pair": parts[0],
        "timeframe": parts[1],
        "candle_type": parts[2],
        "first": parts[3],
        "last": parts[4],
    }


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"INVALID_TIMESTAMP: {value!r}") from exc


def validate_coverage(
    coverage: dict[str, dict[str, dict[str, str]]],
    *,
    required: dict[str, dict[str, dict[str, str]]] | None = None,
) -> None:
    """Fail-closed coverage validation.

    ``coverage`` maps ``candle_type -> timeframe -> {pair: {first,last}}``.
    Every required pair / timeframe / candle type must be present with
    ``first <= required.from`` and ``last >= required.to`` (with a grace of
    one funding interval / one candle interval for auxiliary data).
    """
    required = required or REQUIRED_COVERAGE
    for candle_type, tf_map in required.items():
        for timeframe, window in tf_map.items():
            req_from = _parse_iso(window["from"])
            req_to = _parse_iso(window["to"])
            for pair in PAIRS:
                key = pair_dir_key(pair)
                got = coverage.get(candle_type, {}).get(timeframe, {}).get(key)
                if got is None:
                    raise RuntimeError(
                        f"COVERAGE_MISSING: {pair} {timeframe} {candle_type}"
                    )
                first = _parse_iso(got["first"])
                last = _parse_iso(got["last"])
                # Grace: one interval for 1h aux, one candle for 15m main.
                grace = (
                    (req_to - req_from) * 0
                    + _interval_grace(timeframe)
                )
                if first > req_from + grace:
                    raise RuntimeError(
                        f"COVERAGE_START_LATE: {pair} {timeframe} "
                        f"{candle_type} first={got['first']} "
                        f"required<={window['from']}"
                    )
                if last < req_to - grace:
                    raise RuntimeError(
                        f"COVERAGE_END_EARLY: {pair} {timeframe} "
                        f"{candle_type} last={got['last']} "
                        f"required>={window['to']}"
                    )


def _interval_grace(timeframe: str) -> timedelta:
    """Return a small timedelta grace for coverage bounds."""
    from datetime import timedelta

    if timeframe == "1h":
        return timedelta(hours=1)
    return timedelta(minutes=15)


# ---------------------------------------------------------------------------
# File hash manifest (filled by the A2 run; validated offline when present)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NativeDataFile:
    """One downloaded file in the native datadir with its SHA-256."""

    relative_path: str
    sha256: str | None = None

    def validate_hash(self, datadir_root: Path) -> None:
        """Fail-closed: file must exist and hash must match (if set)."""
        full = datadir_root / self.relative_path
        if not full.is_file():
            raise RuntimeError(f"DATA_FILE_MISSING: {self.relative_path}")
        if self.sha256 is not None:
            digest = hashlib.sha256(full.read_bytes()).hexdigest()
            if digest != self.sha256:
                raise RuntimeError(
                    f"HASH_MISMATCH: {self.relative_path} "
                    f"got {digest} expected {self.sha256}"
                )


# Placeholder for the A2 run manifest — filled after the download.
NATIVE_FILE_MANIFEST: list[NativeDataFile] = []


def register_native_files(files: list[NativeDataFile]) -> None:
    """Register the file manifest (A2 runtime fills this after download)."""
    NATIVE_FILE_MANIFEST.clear()
    NATIVE_FILE_MANIFEST.extend(files)
