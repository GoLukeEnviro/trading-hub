"""Reproducible Gate-0 selection backtest contract (A1; no execution).

Fixes the exact image, version, input hashes, timerange, command, cache
policy, export format and results directory for the Gate-0 selection
backtest. Materialization helpers are deterministic and physically exclude
holdout candles. Nothing in this module downloads data or executes a
backtest.
"""

from __future__ import annotations

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
FREQTRADE_VERSION = "2026.6"

# ---------------------------------------------------------------------------
# Input provenance (pinned at contract creation, base commit 92da91e)
# ---------------------------------------------------------------------------

STRATEGY_FILE_SHA256 = (
    "112ff28ef7bd1fdc28341b4e53516b48fe7c94278c747691077d4d2e6e7916c0"
)
CONFIG_FILE_SHA256 = (
    "7647ed03a88e49a63c9916e9e8137ce84d5e12a90f461785a694591e5e70345d"
)
STRATEGY_REPO_PATH = "freqforge/user_data/strategies/FreqForge_Gate0_Core_v1.py"
CONFIG_REPO_PATH = "freqforge/user_data/config.example.json"

# ---------------------------------------------------------------------------
# Windows (warm-up feeds indicators only; selection excludes holdout)
# ---------------------------------------------------------------------------

WARMUP_START_UTC = datetime(2024, 12, 1, tzinfo=UTC)
SELECTION_START_UTC = datetime(2025, 1, 1, tzinfo=UTC)
SELECTION_END_UTC = WALK_FORWARD_2.end  # 2026-01-01 — holdout excluded

# ---------------------------------------------------------------------------
# Execution contract
# ---------------------------------------------------------------------------

CACHE_POLICY = "none"
EXPORT_FORMAT = "freqtrade-trades-json"
RESULTS_DIR = Path("freqforge/user_data/backtest_results/gate0-selection")
DATA_DIR = Path("freqforge/user_data/data")

BACKTEST_COMMAND = (
    "docker run --rm "
    "-v {data_dir}:/freqtrade/user_data/data "
    "-v {config_dir}:/freqtrade/user_data/config "
    f"{PINNED_FREQTRADE_IMAGE} "
    "backtesting "
    "--config /freqtrade/user_data/config/config.example.json "
    "--strategy FreqForge_Gate0_Core_v1 "
    "--timerange 20241201-20260101 "
    "--cache none "
    "--export trades "
    "--export-filename /freqtrade/user_data/backtest_results/gate0-selection/"
    "gate0-selection.json"
)


def selection_timerange() -> str:
    """Freqtrade timerange: warm-up + selection, holdout excluded."""
    return f"{WARMUP_START_UTC:%Y%m%d}-{SELECTION_END_UTC:%Y%m%d}"


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
    results_dir: str = str(RESULTS_DIR)

    def validate(self) -> None:
        """Fail-closed: moving tags and holdout windows are forbidden."""
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
