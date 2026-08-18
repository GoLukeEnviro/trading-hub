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

# ---------------------------------------------------------------------------
# Canonical funding data contract (issue #705; verified 2026-08-02/#697 A2 run)
# ---------------------------------------------------------------------------

# Funding status after the #697 A2 run (accepted outcome B). Bitget REST and
# the native CCXT path both cap funding history at ~90 days; the required
# start 2024-12-01 is unreachable. Human decision on #697:
# REJECT_INCOMPLETE_FUNDING, Gate-0 disposition EXTEND. Synthetic funding,
# funding_rate=0 fill and external data mixes are PROHIBITED.
FUNDING_STATUS = "INCOMPLETE_CONFIRMED_NATIVE_LIMIT"
# Canonical source identifier (Bitget REST history-fund-rate, ~90 day cap).
FUNDING_SOURCE = "bitget_rest"
# Reproducible empirical cap in days (REST v2/v3 probes 2026-08-02; native
# CCXT fetch_funding_rate_history in the #697 run: 2026-07-01..2026-08-03).
FUNDING_HISTORY_LIMIT_DAYS = 90
# Required coverage window for the Gate-0 selection backtest (warm-up start
# through selection end; aligned with REQUIRED_COVERAGE["funding_rate"]["1h"]
# in freqtrade_native_data_contract).
FUNDING_COVERAGE_REQUIRED_FROM = datetime(2024, 12, 1, tzinfo=UTC)
FUNDING_COVERAGE_REQUIRED_TO = datetime(2026, 6, 30, tzinfo=UTC)

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


# ---------------------------------------------------------------------------
# Funding coverage detection + reporting (issue #705; no silent gaps)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FundingCoverage:
    """Measured funding coverage for one pair against the required window."""

    pair: str
    first: datetime | None
    last: datetime | None
    rate_count: int


def compute_funding_coverage(
    funding_rows: Sequence[tuple[datetime, float]],
    *,
    pair: str = "BTC/USDT:USDT",
) -> FundingCoverage:
    """Measure the coverage window of ``(timestamp, rate)`` funding rows.

    Deterministic and read-only: min/max timestamp over the unique
    millisecond-keyed rows and the deduplicated rate count.
    """
    unique: dict[int, float] = {}
    for ts, rate in funding_rows:
        unique[int(ts.timestamp() * 1000)] = float(rate)
    if not unique:
        return FundingCoverage(pair=pair, first=None, last=None, rate_count=0)
    stamps = sorted(unique)
    return FundingCoverage(
        pair=pair,
        first=datetime.fromtimestamp(stamps[0] / 1000, tz=UTC),
        last=datetime.fromtimestamp(stamps[-1] / 1000, tz=UTC),
        rate_count=len(stamps),
    )


def validate_funding_coverage(
    coverage: FundingCoverage,
    *,
    required_from: datetime = FUNDING_COVERAGE_REQUIRED_FROM,
    required_to: datetime = FUNDING_COVERAGE_REQUIRED_TO,
) -> None:
    """Fail-closed funding coverage validation.

    Raises ``RuntimeError`` when the measured window does not span the full
    required window (``FUNDING_COVERAGE_EMPTY`` / ``FUNDING_COVERAGE_START_LATE``
    / ``FUNDING_COVERAGE_END_EARLY``). There is deliberately no grace: the
    selection backtest cost model needs the complete funding history, and
    partial funding is the confirmed native limit (issue #705).
    """
    if coverage.first is None or coverage.last is None:
        raise RuntimeError(
            f"FUNDING_COVERAGE_EMPTY: {coverage.pair} has no funding rows"
        )
    if coverage.first > required_from:
        raise RuntimeError(
            f"FUNDING_COVERAGE_START_LATE: {coverage.pair} first="
            f"{coverage.first.isoformat()} required<={required_from.isoformat()}"
        )
    if coverage.last < required_to:
        raise RuntimeError(
            f"FUNDING_COVERAGE_END_EARLY: {coverage.pair} last="
            f"{coverage.last.isoformat()} required>={required_to.isoformat()}"
        )


def funding_coverage_report(
    funding_rows: Sequence[tuple[datetime, float]],
    *,
    pair: str = "BTC/USDT:USDT",
) -> dict[str, object]:
    """Build the canonical funding coverage report dict (no exceptions).

    Deterministic: always returns the measured window, the required window,
    the source identifier, the funding status and a boolean ``coverage_ok``.
    This is the no-silent-gap evidence record for the adapter.
    """
    coverage = compute_funding_coverage(funding_rows, pair=pair)
    return {
        "pair": pair,
        "status": FUNDING_STATUS,
        "source": FUNDING_SOURCE,
        "history_limit_days": FUNDING_HISTORY_LIMIT_DAYS,
        "first": coverage.first.isoformat() if coverage.first else None,
        "last": coverage.last.isoformat() if coverage.last else None,
        "rate_count": coverage.rate_count,
        "required_from": FUNDING_COVERAGE_REQUIRED_FROM.isoformat(),
        "required_to": FUNDING_COVERAGE_REQUIRED_TO.isoformat(),
        "coverage_ok": (
            coverage.first is not None
            and coverage.last is not None
            and coverage.first <= FUNDING_COVERAGE_REQUIRED_FROM
            and coverage.last >= FUNDING_COVERAGE_REQUIRED_TO
        ),
    }


def convert_funding_to_freqtrade_with_coverage(
    funding_rows: Sequence[tuple[datetime, float]],
    output_dir: Path,
    *,
    pair: str = "BTC/USDT:USDT",
) -> tuple[Path, dict[str, object]]:
    """Fail-closed funding conversion: validate coverage, then materialize.

    Raises ``RuntimeError`` (``FUNDING_COVERAGE_*``) when the funding window
    is incomplete — no partial funding file is written. On success returns
    ``(json_path, report)`` with the coverage report as evidence.
    """
    report = funding_coverage_report(funding_rows, pair=pair)
    if not report["coverage_ok"]:
        validate_funding_coverage(compute_funding_coverage(funding_rows, pair=pair))
    out = convert_funding_to_freqtrade(funding_rows, output_dir, pair=pair)
    return out, report


# ---------------------------------------------------------------------------
# Funding cost model v2 — Option A (issue #708; ESTIMATED_GAP)
# ---------------------------------------------------------------------------
# Luke's decision 2026-08-18 (#708 comment 5329852393):
#   FUNDING_CONTRACT_V2_OPTION=A
#   FUNDING_STATUS=INCOMPLETE_CONFIRMED_NATIVE_LIMIT
#   FUNDING_COST_MODEL=ESTIMATED_GAP
# Semantics: the dataset coverage criterion stays fail-closed (no grace,
# no silent gaps). For the cost model, the uncovered period is filled with a
# documented best-effort estimate derived EXCLUSIVELY from the real observed
# rates (per-pair median, conservatively capped). The estimate is explicitly
# labeled ESTIMATED — never presented as fetched data. No synthetic rates,
# no funding_rate=0 fill, no interpolation presented as measurement.
FUNDING_CONTRACT_V2_OPTION = "A"
FUNDING_COST_MODEL = "ESTIMATED_GAP"
FUNDING_ESTIMATE_METHOD = "PER_PAIR_MEDIAN_CAPPED"
# Conservative cap for the per-pair median estimate (0.1% per 8h interval).
# Applied symmetrically: estimate = clamp(median, -cap, +cap).
FUNDING_ESTIMATE_CAP = 0.001
# Explicit label for estimate rows in the cost-model output.
FUNDING_ESTIMATE_LABEL = "ESTIMATED"


@dataclass(frozen=True)
class FundingGapEstimate:
    """Option-A gap estimate for one pair (issue #708).

    ``estimate_rate`` is derived exclusively from the real observed rates
    (per-pair median, capped at ``FUNDING_ESTIMATE_CAP``). ``gaps`` lists
    every uncovered period inside the required window (leading, trailing or
    both — no silent gap). When the observed window already covers the full
    required window, ``gaps`` is empty and ``estimate_rate`` is ``None``.
    """

    pair: str
    observed_first: datetime | None
    observed_last: datetime | None
    gaps: tuple[tuple[datetime, datetime], ...]
    estimate_rate: float | None
    method: str = FUNDING_ESTIMATE_METHOD
    label: str = FUNDING_ESTIMATE_LABEL
    cap: float = FUNDING_ESTIMATE_CAP
    observed_rate_count: int = 0
    uncertainty_band: float | None = None


def estimate_funding_gap(
    funding_rows: Sequence[tuple[datetime, float]],
    *,
    pair: str = "BTC/USDT:USDT",
    required_from: datetime = FUNDING_COVERAGE_REQUIRED_FROM,
    required_to: datetime = FUNDING_COVERAGE_REQUIRED_TO,
    cap: float = FUNDING_ESTIMATE_CAP,
) -> FundingGapEstimate:
    """Derive the Option-A gap estimate for one pair (issue #708).

    Fail-closed: an empty observed dataset raises ``RuntimeError``
    (``FUNDING_ESTIMATE_EMPTY``) — no estimate may be derived from nothing.
    The estimate is the per-pair median of the real observed rates, clamped
    to ``[-cap, +cap]``. Every uncovered period inside the required window is
    listed in ``gaps`` (leading, trailing or both). The uncertainty band is
    a conservative sensitivity bound: ``max(0.5 * abs(estimate_rate), 1e-4)``.
    """
    coverage = compute_funding_coverage(funding_rows, pair=pair)
    if coverage.first is None or coverage.last is None:
        raise RuntimeError(
            f"FUNDING_ESTIMATE_EMPTY: {pair} has no observed funding rows"
        )
    if coverage.first <= required_from and coverage.last >= required_to:
        # Full observed coverage — no gap, no estimate required.
        return FundingGapEstimate(
            pair=pair,
            observed_first=coverage.first,
            observed_last=coverage.last,
            gaps=(),
            estimate_rate=None,
            observed_rate_count=coverage.rate_count,
            uncertainty_band=None,
        )
    unique: dict[int, float] = {}
    for ts, rate in funding_rows:
        unique[int(ts.timestamp() * 1000)] = float(rate)
    rates = sorted(unique.values())
    median = rates[len(rates) // 2] if len(rates) % 2 else (
        (rates[len(rates) // 2 - 1] + rates[len(rates) // 2]) / 2.0
    )
    estimate = max(-cap, min(cap, median))
    gaps: list[tuple[datetime, datetime]] = []
    if coverage.first > required_from:
        gaps.append((required_from, min(coverage.first, required_to)))
    if coverage.last < required_to:
        gaps.append((max(coverage.last, required_from), required_to))
    band = max(0.5 * abs(estimate), 1e-4)
    return FundingGapEstimate(
        pair=pair,
        observed_first=coverage.first,
        observed_last=coverage.last,
        gaps=tuple(gaps),
        estimate_rate=estimate,
        observed_rate_count=coverage.rate_count,
        uncertainty_band=band,
    )


def funding_gap_estimate_report(
    funding_rows: Sequence[tuple[datetime, float]],
    *,
    pair: str = "BTC/USDT:USDT",
    required_from: datetime = FUNDING_COVERAGE_REQUIRED_FROM,
    required_to: datetime = FUNDING_COVERAGE_REQUIRED_TO,
) -> dict[str, object]:
    """Build the canonical Option-A gap estimate report dict.

    Deterministic and exception-free: always returns the observed window, the
    gap window, the estimate (or ``None``), the method, the label, the cap,
    the uncertainty band and the option/status identifiers. This is the
    no-silent-gap evidence record for the v2 cost model.
    """
    estimate = estimate_funding_gap(
        funding_rows, pair=pair, required_from=required_from, required_to=required_to
    )
    return {
        "pair": pair,
        "option": FUNDING_CONTRACT_V2_OPTION,
        "cost_model": FUNDING_COST_MODEL,
        "status": FUNDING_STATUS,
        "source": FUNDING_SOURCE,
        "method": estimate.method,
        "label": estimate.label,
        "cap": estimate.cap,
        "observed_first": estimate.observed_first.isoformat() if estimate.observed_first else None,
        "observed_last": estimate.observed_last.isoformat() if estimate.observed_last else None,
        "gaps": [
            [gap_from.isoformat(), gap_to.isoformat()] for gap_from, gap_to in estimate.gaps
        ],
        "estimate_rate": estimate.estimate_rate,
        "uncertainty_band": estimate.uncertainty_band,
        "observed_rate_count": estimate.observed_rate_count,
        "required_from": required_from.isoformat(),
        "required_to": required_to.isoformat(),
    }


def convert_funding_to_freqtrade_with_gap_estimate(
    funding_rows: Sequence[tuple[datetime, float]],
    output_dir: Path,
    *,
    pair: str = "BTC/USDT:USDT",
    required_from: datetime = FUNDING_COVERAGE_REQUIRED_FROM,
    required_to: datetime = FUNDING_COVERAGE_REQUIRED_TO,
) -> tuple[Path, dict[str, object], Path]:
    """Option-A cost-model conversion: observed rows + documented gap estimate.

    Writes the Freqtrade funding JSON containing the real observed rows and,
    for the uncovered period, deterministic estimate rows derived from the
    observed per-pair median (capped). A sidecar ``<pair_key>_estimate.json``
    records the exact gap window, estimate, method, label and uncertainty band
    so no estimate row is ever presented as fetched data. Fail-closed on an
    empty observed dataset (``FUNDING_ESTIMATE_EMPTY``): no JSON and no
    sidecar are written. Returns ``(json_path, report, sidecar_path)``.
    """
    report = funding_gap_estimate_report(
        funding_rows, pair=pair, required_from=required_from, required_to=required_to
    )
    estimate = estimate_funding_gap(
        funding_rows, pair=pair, required_from=required_from, required_to=required_to
    )
    pair_key = pair.replace("/", "_").replace(":", "_")
    out = output_dir / "futures_funding_rate" / f"{pair_key}.json"
    sidecar = output_dir / "futures_funding_rate" / f"{pair_key}_estimate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    unique: dict[int, float] = {}
    for ts, rate in funding_rows:
        unique[int(ts.timestamp() * 1000)] = float(rate)
    if estimate.estimate_rate is not None:
        # Deterministic hourly estimate rows across every gap window.
        step = 3600
        for gap_from, gap_to in estimate.gaps:
            start_ms = int(gap_from.timestamp() * 1000)
            end_ms = int(gap_to.timestamp() * 1000)
            ts_ms = start_ms
            while ts_ms < end_ms:
                unique.setdefault(ts_ms, estimate.estimate_rate)
                ts_ms += step * 1000
    out.write_text(json.dumps(sorted(unique.items()), separators=(",", ":")))
    sidecar.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return out, report, sidecar


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
