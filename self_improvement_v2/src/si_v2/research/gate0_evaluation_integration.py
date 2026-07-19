"""Gate-0 evaluation integration pipeline (C5).

Wires the frozen snapshot through EvaluationBundleV1 → EvaluationRunnerV1
for calibration and walk-forward validation. No holdout evaluation.

Architecture:
  Snapshot (CSV+gz) → CandleV1 → partition → EvaluationBundleV1
  Freqtrade backtest output (JSON) → raw_trades → RawTradeV1
  Bundle + RawTradeV1 → EvaluationRunnerV1 → artifact → decision

The Freqtrade backtest step is a separate HermesTrader-side call (freqtrade
is not available in this container). This module provides the complete
pipeline code; the backtest wrapper is callable from the host.
"""

from __future__ import annotations

import csv
import gzip
import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


from si_v2.research.evaluation_bundle_v1 import (
    BoundaryPolicy,
    CandleV1,
    ContinuationPolicy,
    CostConfig,
    EvaluationBundleV1,
    EvaluationManifestV1,
    EvaluationRunnerV1,
    EvaluationThresholdsV1,
    FreqtradeProvenanceV1,
    PartitionWindowV1,
    RawTradeV1,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SNAPSHOT_DIR = Path("/opt/data/gate0-snapshot")
MANIFEST_PATH = SNAPSHOT_DIR / "snapshot_manifest.json"

TIMEFRAME = "15m"
TIMEFRAME_SECONDS = {"15m": 900}

# Partition windows per frozen manifest
CALIBRATION = PartitionWindowV1(
    label="calibration",
    start=datetime(2025, 1, 1, tzinfo=UTC),
    end=datetime(2025, 6, 30, 23, 59, 59, tzinfo=UTC),
)
WALK_FORWARD_1 = PartitionWindowV1(
    label="walk_forward_1",
    start=datetime(2025, 7, 1, tzinfo=UTC),
    end=datetime(2025, 9, 30, 23, 59, 59, tzinfo=UTC),
)
WALK_FORWARD_2 = PartitionWindowV1(
    label="walk_forward_2",
    start=datetime(2025, 10, 1, tzinfo=UTC),
    end=datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC),
)
HOLDOUT = PartitionWindowV1(
    label="holdout",
    start=datetime(2026, 1, 1, tzinfo=UTC),
    end=datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC),
)

PARTITIONS = [CALIBRATION, WALK_FORWARD_1, WALK_FORWARD_2, HOLDOUT]

# ---------------------------------------------------------------------------
# Snapshot loading
# ---------------------------------------------------------------------------


def load_snapshot_manifest() -> dict[str, object]:
    """Load the snapshot_manifest.json from the snapshot directory."""
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"Snapshot manifest not found: {MANIFEST_PATH}")
    return json.loads(MANIFEST_PATH.read_text())


def load_snapshot_candles(pair_label: str) -> list[CandleV1]:
    """Load candles for one pair from the gzipped CSV snapshot.

    ``pair_label`` is e.g. ``"BTC_USDT"`` (same as the filename prefix).
    Returns a sorted list with duplicates removed.
    """
    csv_gz = SNAPSHOT_DIR / f"{pair_label}_15m.csv.gz"
    if not csv_gz.is_file():
        raise FileNotFoundError(f"Snapshot file not found: {csv_gz}")

    candles: list[CandleV1] = []
    with gzip.open(csv_gz, "rt") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = datetime.strptime(row["timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            candle = CandleV1(
                pair=row["pair"],
                timestamp=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            candles.append(candle)

    # Dedup by (pair, timestamp) — last write wins
    seen: dict[tuple[str, datetime], CandleV1] = {}
    for c in candles:
        seen[(c.pair, c.timestamp)] = c
    return sorted(seen.values(), key=lambda c: (c.pair, c.timestamp))


def _partition_candles(
    candles: Sequence[CandleV1], window: PartitionWindowV1
) -> list[CandleV1]:
    """Filter candles to those strictly within a partition window."""
    return [c for c in candles if window.start <= c.timestamp < window.end]


# ---------------------------------------------------------------------------
# Freqtrade backtest wrapper
# ---------------------------------------------------------------------------


def run_backtest_cli(
    *,
    strategy_path: str,
    config_path: str,
    data_dir: str | Path,
    timerange: str,
    export_path: str | Path,
    freqtrade_bin: str = "freqtrade",
    timeout: int = 3600,
) -> int:
    """Run ``freqtrade backtesting`` via CLI and export trades to JSON.

    This is intended for HermesTrader host execution where freqtrade is
    available as a Docker container or CLI.

    Args:
        strategy_path: Path to the FreqForge_Override.py strategy file.
        config_path: Path to the backtest config JSON.
        data_dir: Freqtrade data directory (with Freqtrade-formatted data).
        timerange: ``"20250101-20250630"`` style timerange.
        export_path: Output JSON path for trade export.
        timeout: Max execution time in seconds.

    Returns:
        Exit code of the freqtrade command.
    """
    cmd = [
        freqtrade_bin,
        "backtesting",
        "--strategy-path",
        strategy_path,
        "--config",
        config_path,
        "--datadir",
        str(data_dir),
        "--timerange",
        timerange,
        "--export",
        "trades",
        "--export-filename",
        str(export_path),
        "--fee", "0.0005",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode


def parse_backtest_trades(json_path: str | Path) -> list[RawTradeV1]:
    """Parse a Freqtrade backtest trade export JSON into RawTradeV1 objects.

    Freqtrade export format is a JSON with date, pair, open_rate, close_rate,
    amount, trade_duration, profit_ratio, etc.
    """
    data = json.loads(Path(json_path).read_text())
    trades_raw = data.get("trades", data.get("strategy", {}).get("trades", []))
    if not trades_raw:
        return []

    raw_trades: list[RawTradeV1] = []
    for t in trades_raw:
        pair = t.get("pair", "")
        if pair.endswith(":USDT") or pair.endswith("/USDT"):
            pair = pair.split(":")[0] if ":" in pair else pair

        raw_trades.append(RawTradeV1(
            trade_id=str(t.get("trade_id", "")),
            pair=pair,
            entry_time=datetime.fromtimestamp(t["open_date_utc"] / 1000, tz=UTC)
                if isinstance(t.get("open_date_utc"), (int, float))
                else datetime.fromisoformat(t["open_date"].replace("Z", "+00:00")),
            exit_time=datetime.fromtimestamp(t["close_date_utc"] / 1000, tz=UTC)
                if isinstance(t.get("close_date_utc"), (int, float))
                else datetime.fromisoformat(t["close_date"].replace("Z", "+00:00")),
            entry_price=float(t.get("open_rate", 0)),
            exit_price=float(t.get("close_rate", 0)),
            quantity=float(t.get("amount", 0)),
            side="long" if t.get("is_short", False) is False else "short",
            regime="default",  # Freqtrade doesn't export regime
        ))
    return raw_trades


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------


def build_frozen_manifest(
    *, snapshot_id: str, fetcher_commit_sha: str
) -> EvaluationManifestV1:
    """Build the frozen EvaluationManifestV1 from Luke's ratified values."""
    snapshot = load_snapshot_manifest()
    pairs = tuple(sorted(snapshot["pairs"]))


    return EvaluationManifestV1(
        manifest_version="evaluation-manifest/v1",
        manifest_id=f"gate0-manifest-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        approval_reference="issue-651-APPROVED_A2_GATE0_SNAPSHOT_FETCH",
        strategy_identifier="FreqForge_Override",
        provenance=FreqtradeProvenanceV1(
            freqtrade_version="2025.7",
            strategy_class="FreqForge_Override",
            strategy_file_sha256="FETCH_AT_RUNTIME",  # computed when freqtrade runs
            strategy_commit_sha=fetcher_commit_sha,
            config_sha256="FETCH_AT_RUNTIME",
        ),
        data_source="bitget",
        data_snapshot_id=snapshot_id,
        candle_snapshot_sha256=snapshot["files"][0]["canonical_sha256"],
        benchmark_snapshot_sha256=snapshot["files"][0]["canonical_sha256"],
        exchange="bitget",
        trading_mode="futures",
        market_type="linear",
        pairs=pairs,
        timeframe=TIMEFRAME,
        timerange_start=CALIBRATION.start,
        timerange_end=HOLDOUT.end,
        calibration=CALIBRATION,
        walk_forward_windows=(WALK_FORWARD_1, WALK_FORWARD_2),
        holdout=HOLDOUT,
        cost_config=CostConfig(
            entry_fee_rate=0.0005,
            exit_fee_rate=0.0005,
            slippage_rate=0.0002,
            funding_rate_per_8h=0.0001,
            leverage=1.0,
        ),
        thresholds=EvaluationThresholdsV1(
            threshold_set_id="gate0-default-v1",
            min_trades=100,
            min_duration_days=180,
            min_regimes=2,
            max_drawdown_pct=25.0,
            min_profit_factor=1.3,
            min_edge_mean=0.01,
            min_edge_lower_bound=0.0,
            max_confidence_interval_width=0.05,
            bootstrap_samples=1000,
            bootstrap_block_size=4,
            confidence_level=0.95,
            bootstrap_seed=42,
            initial_equity=10000.0,
            max_missing_candles=100,
            tail_quantile=0.1,
        ),
        boundary_policy=BoundaryPolicy.STRICT_CONTAINED,
        continuation_policy=ContinuationPolicy.REPORT_ONLY,
        mark_to_market_price_field="close",
    )


# ---------------------------------------------------------------------------
# Evaluation pipeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowResult:
    """Result of running the evaluation runner on one partition window."""

    window_label: str
    outcome: str  # PASS_CANDIDATE, EXTEND, REJECT, INVALID
    num_trades: int
    profit_factor: float | None
    max_drawdown_pct: float | None
    num_trades_before: int | None = None


def run_calibration_and_walkforward(
    manifest: EvaluationManifestV1,
    candles: Sequence[CandleV1],
    raw_trades: Sequence[RawTradeV1],
) -> list[WindowResult]:
    """Run evaluation for calibration and walk-forward windows (no holdout).

    Args:
        manifest: The frozen evaluation manifest.
        candles: All candles for the full 18-month range.
        raw_trades: Backtest trade results (calibration + walk-forward only).

    Returns:
        A list of WindowResult, one per evaluated window.
    """
    runner = EvaluationRunnerV1()
    results: list[WindowResult] = []

    # Evaluate calibration + walk-forward windows
    eval_windows = [CALIBRATION, WALK_FORWARD_1, WALK_FORWARD_2]

    for window in eval_windows:
        window_candles = _partition_candles(candles, window)
        benchmark_candles = [c for c in window_candles if c.pair == manifest.pairs[0]]

        window_trades = [
            t for t in raw_trades
            if window.start <= t.entry_time < window.end
        ]

        bundle = EvaluationBundleV1(
            manifest=manifest,
            candles=tuple(window_candles),
            benchmark_candles=tuple(benchmark_candles),
            raw_trades=tuple(window_trades),
        )

        artifact = runner.evaluate(bundle)

        pm = artifact.partition_metrics.get(window.label)
        results.append(WindowResult(
            window_label=window.label,
            outcome=artifact.outcome.value,
            num_trades=pm.trade_count if pm else 0,
            profit_factor=pm.profit_factor if pm else None,
            max_drawdown_pct=pm.max_drawdown_pct if pm else None,
        ))

    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def format_results(results: list[WindowResult]) -> str:
    """Format evaluation results as a markdown summary."""
    lines = [
        "## Gate-0 Calibration + Walk-Forward Results",
        "",
        "| Window | Outcome | Trades | Profit Factor | Max DD % |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        pf = f"{r.profit_factor:.2f}" if r.profit_factor is not None else "N/A"
        dd = f"{r.max_drawdown_pct:.1f}" if r.max_drawdown_pct is not None else "N/A"
        lines.append(f"| {r.window_label} | {r.outcome} | {r.num_trades} | {pf} | {dd} |")

    lines.extend([
        "",
        "**Note:** Holdout is NOT evaluated in this run. The holdout partition",
        "remains sealed until `APPROVED_GATE0_HOLDOUT_EVALUATION` marker is issued.",
    ])
    return "\n".join(lines)
