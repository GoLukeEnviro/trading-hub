"""Freqtrade-native Bitget futures data contract (A1; no execution).

Defines the immutable, reproducible download contract for the Gate-0
selection backtest dataset. All file-layout and pair-filename rules are
derived from the real Freqtrade IDataHandler upstream contract (verified
2026-08-03 against the pinned image).

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
import json
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
FREQTRADE_VERSION = "2026.7"
# Historical contract field — informational only, not an active contract value.
SUPERSEDED_INFORMATIONAL_VERSION = "2026.6"

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

# ---------------------------------------------------------------------------
# Pair filename contract — derived from upstream IDataHandler
# ---------------------------------------------------------------------------
# pair_to_filename("BTC/USDT:USDT") → "BTC_USDT_USDT"
# (replaces /, :, ' ', '.', '@', '$', '+' with '_')
# _pair_data_filename() → flat futures/<pair_s>-<tf>-<candle_type>.feather
# _OHLCV_REGEX = ^([\w-]+)\-(\d+[a-zA-Z]{1,2})\-?([a-zA-Z_]*)?(?=\.)
# rebuild_pair_from_filename("BTC_USDT_USDT") → "BTC/USDT:USDT"
#   (first _ → /, second _ → :)


def pair_to_filename(pair: str) -> str:
    """Freqtrade upstream ``pair_to_filename`` (misc.py)."""
    for ch in ["/", " ", ".", "@", "$", "+", ":"]:
        pair = pair.replace(ch, "_")
    return pair


def rebuild_pair_from_filename(filename_pair: str) -> str:
    """Freqtrade upstream ``rebuild_pair_from_filename``."""
    return filename_pair.replace("_", "/", 1).replace("_", ":", 1)


def _pair_data_filename(
    pair: str,
    timeframe: str,
    candle_type: str,
    *,
    datadir: Path | None = None,
) -> Path:
    """Deterministic Freqtrade ``_pair_data_filename`` equivalent.

    ``candle_type`` is the string value (e.g. ``"futures"``, ``"mark"``,
    ``"funding_rate"``). For ``"futures"`` (which maps to ``CandleType.SPOT``
    in Freqtrade's enum), no candle suffix is appended and the file lives
    directly in the ``futures/`` directory. For all other candle types, the
    file lives in ``futures/`` with a ``-<candle_type>`` suffix.
    """
    pair_s = pair_to_filename(pair)
    tf = timeframe.replace("M", "Mo")  # timeframe_to_file
    base = datadir or Path()
    if candle_type == "futures":
        # CandleType.SPOT → no suffix, but still in futures/ dir
        return base / "futures" / f"{pair_s}-{tf}.feather"
    return base / "futures" / f"{pair_s}-{tf}-{candle_type}.feather"


PAIR_FILENAMES: tuple[str, ...] = tuple(pair_to_filename(p) for p in PAIRS)


def full_timerange() -> str:
    return f"{FULL_TIMERANGE_START:%Y%m%d}-{FULL_TIMERANGE_END:%Y%m%d}"


def selection_timerange() -> str:
    return f"{FULL_TIMERANGE_START:%Y%m%d}-{SELECTION_TIMERANGE_END:%Y%m%d}"


# ---------------------------------------------------------------------------
# Required coverage windows (inclusive lower bounds)
# ---------------------------------------------------------------------------

REQUIRED_COVERAGE: dict[str, dict[str, dict[str, str]]] = {
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


def render_inventory_command(
    *,
    datadir_host: Path | str = HOST_DATA_DIR,
    inventory_script_host: Path | str = (
        "self_improvement_v2/src/si_v2/research/datahandler_inventory.py"
    ),
) -> str:
    """Render the pinned DataHandler inventory command (read-only).

    Runs ``datahandler_inventory.py`` inside the pinned container against
    the mounted datadir. Output is canonical JSON.
    """
    return (
        "docker run --rm \\\n"
        "  --user 10000:10000 \\\n"
        f"  -v {datadir_host}:/freqtrade/user_data/data:ro \\\n"
        f"  -v {inventory_script_host}:/inventory.py:ro \\\n"
        f"  --entrypoint python3 {PINNED_IMAGE} \\\n"
        "  /inventory.py /freqtrade/user_data/data"
    )


# ---------------------------------------------------------------------------
# DataHandler inventory parser + fail-closed validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InventoryEntry:
    """One entry from the DataHandler inventory JSON."""

    pair: str
    timeframe: str
    candle_type: str
    first: str | None
    last: str | None
    count: int
    relative_path: str
    sha256: str | None

    @classmethod
    def from_dict(cls, d: dict) -> "InventoryEntry":
        return cls(
            pair=str(d["pair"]),
            timeframe=str(d["timeframe"]),
            candle_type=str(d["candle_type"]),
            first=str(d["first"]) if d.get("first") else None,
            last=str(d["last"]) if d.get("last") else None,
            count=int(d.get("count", 0)),
            relative_path=str(d["relative_path"]),
            sha256=str(d["sha256"]) if d.get("sha256") else None,
        )


def parse_inventory(json_text: str) -> list[InventoryEntry]:
    """Parse the canonical DataHandler inventory JSON."""
    data = json.loads(json_text)
    if not isinstance(data, list):
        raise ValueError("INVENTORY_NOT_LIST")
    return [InventoryEntry.from_dict(item) for item in data]


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"INVALID_TIMESTAMP: {value!r}") from exc


def _interval_grace(timeframe: str) -> timedelta:
    if timeframe == "1h":
        return timedelta(hours=1)
    return timedelta(minutes=15)


def validate_coverage(
    inventory: list[InventoryEntry],
    *,
    required: dict[str, dict[str, dict[str, str]]] | None = None,
) -> None:
    """Fail-closed coverage validation against the DataHandler inventory.

    Every required pair / timeframe / candle type must be present with
    ``first <= required.from`` and ``last >= required.to`` (with a grace of
    one funding interval / one candle interval for auxiliary data).
    """
    required = required or REQUIRED_COVERAGE
    # Build lookup: candle_type -> timeframe -> pair -> entry
    lookup: dict[str, dict[str, dict[str, InventoryEntry]]] = {}
    for entry in inventory:
        lookup.setdefault(entry.candle_type, {}).setdefault(
            entry.timeframe, {}
        )[entry.pair] = entry

    for candle_type, tf_map in required.items():
        for timeframe, window in tf_map.items():
            req_from = _parse_iso(window["from"])
            req_to = _parse_iso(window["to"])
            for pair in PAIRS:
                got = (
                    lookup.get(candle_type, {})
                    .get(timeframe, {})
                    .get(pair)
                )
                if got is None:
                    raise RuntimeError(
                        f"COVERAGE_MISSING: {pair} {timeframe} {candle_type}"
                    )
                if got.first is None or got.last is None:
                    raise RuntimeError(
                        f"COVERAGE_EMPTY: {pair} {timeframe} {candle_type}"
                    )
                first = _parse_iso(got.first)
                last = _parse_iso(got.last)
                grace = _interval_grace(timeframe)
                if first > req_from + grace:
                    raise RuntimeError(
                        f"COVERAGE_START_LATE: {pair} {timeframe} "
                        f"{candle_type} first={got.first} "
                        f"required<={window['from']}"
                    )
                if last < req_to - grace:
                    raise RuntimeError(
                        f"COVERAGE_END_EARLY: {pair} {timeframe} "
                        f"{candle_type} last={got.last} "
                        f"required>={window['to']}"
                    )


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
