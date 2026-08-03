"""Reproducible Gate-0 selection backtest contract (A1; no execution).

Fixes the exact image, version, input hashes, timerange, command, cache
policy, export format, separated mounts and results directory for the
Gate-0 selection backtest. Materialization helpers are deterministic and
physically exclude holdout candles. Nothing in this module downloads data
or executes a backtest.

Corrective (2026-08-03): Freqtrade-native data contract —
- ``--export-filename`` removed; ``--backtest-directory`` used instead.
- Explicit ``--data-format-ohlcv feather``, ``--timeframe 15m``,
  ``--trading-mode futures``, ``--cache none``, ``--export trades``.
- Separated mounts: user_data read-only, data read-only, results read-write.
- New path constants for the native data dir, research snapshot and
  backtest results dir.
- Fail-closed checks: results persistence, strategy path presence, explicit
  data format, pinned image, holdout in datadir, missing mark/funding.
- Absolute host paths required; relative config path fails.
- Strategy/config hash validation.
- File-layout checks use the real Freqtrade IDataHandler contract
  (flat ``futures/`` directory, ``pair_to_filename`` semantics).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from si_v2.research.evaluation_bundle_v1 import CandleV1
from si_v2.research.gate0_evaluation_integration import (
    HOLDOUT,
    WALK_FORWARD_2,
    aggregate_to_1h,
    convert_to_freqtrade_format,
)

# ---------------------------------------------------------------------------
# Pinned image (verified 2026-08-02 via Docker Hub tag metadata)
# ---------------------------------------------------------------------------

PINNED_FREQTRADE_IMAGE = (
    "freqtradeorg/freqtrade@sha256:"
    "50720a4af314a812be2cfbf5cc6331c63e9332b06f3f4372241f54bc61a35486"
)
# Canonical runtime version (verified 2026-08-02 via ``freqtrade --version``
# inside the pinned image). The digest is the authoritative pin; the version
# string is informational.
FREQTRADE_VERSION = "2026.7"
# Historical contract field — informational only, not an active contract value.
SUPERSEDED_INFORMATIONAL_VERSION = "2026.6"

# ---------------------------------------------------------------------------
# Input provenance (pinned at contract creation, base commit 092f5ad)
# ---------------------------------------------------------------------------

STRATEGY_FILE_SHA256 = (
    "112ff28ef7bd1fdc28341b4e53516b48fe7c94278c747691077d4d2e6e7916c0"
)
CONFIG_FILE_SHA256 = (
    "7647ed03a88e49a63c9916e9e8137ce84d5e12a90f461785a694591e5e70345d"
)

# ---------------------------------------------------------------------------
# Windows (warm-up feeds indicators only; selection excludes holdout)
# ---------------------------------------------------------------------------

WARMUP_START_UTC = datetime(2024, 12, 1, tzinfo=UTC)
SELECTION_START_UTC = datetime(2025, 1, 1, tzinfo=UTC)
SELECTION_END_UTC = WALK_FORWARD_2.end  # 2026-01-01 — holdout excluded
DATASET_END_UTC = datetime(2026, 7, 1, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Execution contract
# ---------------------------------------------------------------------------

CACHE_POLICY = "none"
EXPORT_FORMAT = "freqtrade-trades-json"
DATA_FORMAT_OHLCV = "feather"
TIMEFRAME = "15m"
TRADING_MODE = "futures"

# Absolute canonical host paths
PROJECT_DIR = Path("/opt/data/projects/trading-hub/freqforge/user_data")
FREQTRADE_NATIVE_DATA_DIR = Path("/opt/data/gate0-freqtrade-native-r1")
RESEARCH_SNAPSHOT_DIR = Path("/opt/data/gate0-snapshot-v2-r1")
BACKTEST_RESULTS_DIR = Path("/opt/data/gate0-backtest-results")

# Container paths
CONTAINER_USER_DATA = Path("/freqtrade/user_data")
CONTAINER_DATA_DIR = Path("/freqtrade/user_data/data")
CONTAINER_RESULTS_DIR = Path("/freqtrade/user_data/backtest_results")

# Selection results subdirectory (inside the results mount)
RESULTS_SUBDIR = "gate0-selection"

BACKTEST_COMMAND = (
    "docker run --rm "
    "--user 10000:10000 "
    "-v {project_dir}:/freqtrade/user_data/project:ro "
    "-v {data_dir}:/freqtrade/user_data/data:ro "
    "-v {results_dir}:/freqtrade/user_data/backtest_results:rw "
    f"{PINNED_FREQTRADE_IMAGE} "
    "backtesting "
    "--config /freqtrade/user_data/project/config.example.json "
    "--strategy-path /freqtrade/user_data/project/strategies "
    "--strategy FreqForge_Gate0_Core_v1 "
    "--timeframe 15m "
    "--trading-mode futures "
    "--timerange {timerange} "
    "--data-format-ohlcv feather "
    "--cache none "
    "--export trades "
    "--backtest-directory "
    "/freqtrade/user_data/backtest_results/gate0-selection "
    "--breakdown month year"
)


def selection_timerange() -> str:
    """Freqtrade timerange: warm-up + selection, holdout excluded."""
    return f"{WARMUP_START_UTC:%Y%m%d}-{SELECTION_END_UTC:%Y%m%d}"


def full_dataset_timerange() -> str:
    """Freqtrade timerange for data download: full dataset incl. holdout.

    The *download* contract fetches the full range (warm-up through holdout
    end); the *backtest* timerange physically excludes holdout. The download
    datadir must not contain the holdout in the selection view.
    """
    return f"{WARMUP_START_UTC:%Y%m%d}-{DATASET_END_UTC:%Y%m%d}"


@dataclass(frozen=True)
class BacktestContract:
    """Immutable, fail-closed Gate-0 selection backtest contract."""

    image: str = PINNED_FREQTRADE_IMAGE
    freqtrade_version: str = FREQTRADE_VERSION
    strategy_sha256: str = STRATEGY_FILE_SHA256
    config_sha256: str = CONFIG_FILE_SHA256
    timerange: str = field(default_factory=selection_timerange)
    cache_policy: str = CACHE_POLICY
    export_format: str = EXPORT_FORMAT
    data_format_ohlcv: str = DATA_FORMAT_OHLCV
    timeframe: str = TIMEFRAME
    trading_mode: str = TRADING_MODE
    results_dir: str = str(BACKTEST_RESULTS_DIR)
    results_subdir: str = RESULTS_SUBDIR

    def validate(self) -> None:
        """Fail-closed: moving tags, holdout windows and missing data
        formats are forbidden."""
        if ":stable" in self.image or ":latest" in self.image:
            raise RuntimeError("IMAGE_NOT_PINNED: moving tag is forbidden")
        if not self.image.startswith("freqtradeorg/freqtrade@sha256:"):
            raise RuntimeError("IMAGE_PIN_INVALID")
        try:
            start_s, end_s = self.timerange.split("-", 1)
            start = datetime.strptime(start_s, "%Y%m%d").replace(tzinfo=UTC)
            end = datetime.strptime(end_s, "%Y%m%d").replace(tzinfo=UTC)
        except ValueError as exc:
            raise RuntimeError("TIMERANGE_INVALID") from exc
        if end > HOLDOUT.start:
            raise RuntimeError("HOLDOUT_IN_TIMERANGE")
        if start >= SELECTION_START_UTC:
            raise RuntimeError(
                "WARMUP_MISSING: timerange must start before selection"
            )
        if self.data_format_ohlcv != "feather":
            raise RuntimeError(
                f"DATA_FORMAT_NOT_EXPLICIT: {self.data_format_ohlcv!r} "
                "(must be 'feather')"
            )
        if self.timeframe != "15m":
            raise RuntimeError(f"TIMEFRAME_NOT_15M: {self.timeframe!r}")
        if self.trading_mode != "futures":
            raise RuntimeError(f"TRADING_MODE_NOT_FUTURES: {self.trading_mode!r}")


def render_backtest_command(
    *,
    project_dir: Path | str = PROJECT_DIR,
    data_dir: Path | str = FREQTRADE_NATIVE_DATA_DIR,
    results_dir: Path | str = BACKTEST_RESULTS_DIR,
    timerange: str | None = None,
) -> str:
    """Render the pinned backtest command with separated mounts.

    ``data_dir`` is mounted read-only, ``results_dir`` read-write, and the
    project (strategy + config) read-only. The results directory is the
    persistent backtest results mount.
    """
    tr = timerange or selection_timerange()
    return BACKTEST_COMMAND.format(
        project_dir=project_dir,
        data_dir=data_dir,
        results_dir=results_dir,
        timerange=tr,
    )


def _validate_absolute(path: Path, label: str) -> None:
    if not path.is_absolute():
        raise RuntimeError(
            f"PATH_NOT_ABSOLUTE: {label}={path} must be absolute"
        )


def _validate_file_hash(path: Path, expected_sha256: str, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"{label}_MISSING: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise RuntimeError(
            f"{label}_HASH_MISMATCH: {path} got {actual} expected {expected_sha256}"
        )


def _pair_data_filename(
    pair: str,
    timeframe: str,
    candle_type: str,
    *,
    datadir: Path | None = None,
) -> Path:
    """Deterministic Freqtrade ``_pair_data_filename`` equivalent.

    Duplicated from the native data contract module to avoid a circular
    import (that module imports from this one).
    """
    pair_s = pair.replace("/", "_").replace(":", "_").replace(" ", "_")
    pair_s = pair_s.replace(".", "_").replace("@", "_").replace("$", "_").replace("+", "_")
    tf = timeframe.replace("M", "Mo")
    base = datadir or Path()
    if candle_type == "futures":
        return base / "futures" / f"{pair_s}-{tf}.feather"
    return base / "futures" / f"{pair_s}-{tf}-{candle_type}.feather"


def validate_mount_contract(
    *,
    project_dir: Path | str,
    data_dir: Path | str,
    results_dir: Path | str,
    strategy_path: Path | str | None = None,
    strategy_sha256: str = STRATEGY_FILE_SHA256,
    config_sha256: str = CONFIG_FILE_SHA256,
) -> None:
    """Fail-closed mount validation for the backtest command.

    Requires: all host paths absolute, results dir present, strategy path
    present with matching hash, config present with matching hash, no
    holdout directory inside the selection datadir, and required data files
    present via the real Freqtrade IDataHandler file layout (flat
    ``futures/`` directory, ``pair_to_filename`` semantics).

    Does NOT check for fictional nested subdirectories like
    ``bitget/futures/mark/<pair>`` — the real layout is flat.
    """
    p_project = Path(project_dir)
    p_data = Path(data_dir)
    p_results = Path(results_dir)

    _validate_absolute(p_project, "project_dir")
    _validate_absolute(p_data, "data_dir")
    _validate_absolute(p_results, "results_dir")

    # Results must be persistent (read-write) — a non-existing or read-only
    # results dir would silently drop exports.
    if not p_results.exists():
        raise RuntimeError(
            f"RESULTS_NOT_PERSISTENT: {results_dir} does not exist"
        )

    # Strategy path must exist
    strategy = (
        Path(strategy_path)
        if strategy_path is not None
        else p_project / "strategies"
    )
    if not strategy.is_dir():
        raise RuntimeError(
            f"STRATEGY_PATH_MISSING: {strategy} is not a directory"
        )

    # Holdout must be physically absent from the selection datadir.
    holdout_candidates = [
        p_data / "holdout",
        p_data / "holdout-sealed",
    ]
    for candidate in holdout_candidates:
        if candidate.exists():
            raise RuntimeError(
                f"HOLDOUT_IN_DATADIR: {candidate} must not exist"
            )

    # Required data files via real IDataHandler file layout.
    # pair_to_filename("BTC/USDT:USDT") → "BTC_USDT_USDT"
    # _pair_data_filename() → flat futures/<pair_s>-<tf>[-<candle_type>].feather
    for pair in ("BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"):
        for ct in ("futures", "mark", "funding_rate"):
            tf = "15m" if ct == "futures" else "1h"
            expected = _pair_data_filename(pair, tf, ct, datadir=p_data)
            if not expected.is_file():
                raise RuntimeError(
                    f"DATA_FILE_MISSING: {expected} not found"
                )

    # Strategy file hash
    strategy_file = strategy / "FreqForge_Gate0_Core_v1.py"
    _validate_file_hash(strategy_file, strategy_sha256, "STRATEGY")

    # Config file hash
    config_file = p_project / "config.example.json"
    _validate_file_hash(config_file, config_sha256, "CONFIG")


# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------


def exclude_holdout(
    candles: Sequence[CandleV1],
    holdout_start: datetime = HOLDOUT.start,
) -> list[CandleV1]:
    """Physically drop every candle at/after ``holdout_start``."""
    return [c for c in candles if c.timestamp < holdout_start]


def aggregate_1h_dataset(candles_15m: Sequence[CandleV1]) -> list[CandleV1]:
    """Deterministic 15m to 1h aggregation for the 1h informative timeframe."""
    return aggregate_to_1h(list(candles_15m))


def materialize_selection_dataset(
    candles_by_pair: dict[str, Sequence[CandleV1]],
    output_dir: Path,
    *,
    timeframe: str = "15m",
) -> dict[str, Path]:
    """Materialize Freqtrade JSON datasets for warm-up + selection only.

    Holdout candles are physically excluded before conversion. Returns the
    ``{pair: path}`` mapping produced by :func:`convert_to_freqtrade_format`.
    """
    selection: dict[str, list[CandleV1]] = {
        label: exclude_holdout(candles)
        for label, candles in candles_by_pair.items()
    }
    all_candles: list[CandleV1] = [
        c for label in sorted(selection) for c in selection[label]
    ]
    return convert_to_freqtrade_format(
        all_candles, output_dir, timeframe=timeframe
    )


def convert_funding_to_freqtrade(
    funding_rows: Sequence[tuple[datetime, float]],
    output_dir: Path,
    *,
    pair: str = "BTC/USDT:USDT",
) -> Path:
    """Convert ``(timestamp, funding_rate)`` rows to Freqtrade funding JSON.

    Deterministic: sorted ascending by timestamp, duplicates deduplicated.
    Output: ``<output_dir>/futures_funding_rate/<pair_key>.json`` with
    ``[[ts_ms, rate], ...]`` (``pair_key`` = pair with ``/`` and ``:``
    replaced by ``_``).

    **Load-compatibility notice (2026-08-03):** this adapter output is an
    *audit helper only*. It is NOT declared load-compatible until the real
    Freqtrade history loader accepts it (verified via ``freqtrade list-data``
    / loader smoke). The canonical backtest funding/mark input is the native
    Freqtrade download (``--candle-types mark funding_rate``), per decision
    B in the Freqtrade-native data contract.
    """
    pair_key = pair.replace("/", "_").replace(":", "_")
    out = output_dir / "futures_funding_rate" / f"{pair_key}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    unique: dict[int, float] = {}
    for ts, rate in funding_rows:
        unique[int(ts.timestamp() * 1000)] = float(rate)
    out.write_text(json.dumps(sorted(unique.items()), separators=(",", ":")))
    return out


def validate_warmup_excluded_from_metrics(
    warmup_candles: Sequence[CandleV1],
    selection_start: datetime = SELECTION_START_UTC,
) -> None:
    """Fail-closed: no warm-up candle may fall into the selection window."""
    for c in warmup_candles:
        if c.timestamp >= selection_start:
            raise RuntimeError(
                f"WARMUP_LEAKS_INTO_SELECTION: {c.pair} "
                f"{c.timestamp.isoformat()}"
            )
