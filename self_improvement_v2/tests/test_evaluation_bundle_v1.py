from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from backtests.cost_model import CostConfig

from si_v2.research.edge_evidence_harness import (
    LegacyEvaluationAPIError,
    StrategyEvaluationHarness,
)
from si_v2.research.evaluation_bundle_v1 import (
    BoundaryPolicy,
    CandleV1,
    ContinuationPolicy,
    EvaluationBundleV1,
    EvaluationManifestV1,
    EvaluationRunnerV1,
    EvaluationThresholdsV1,
    FreqtradeExportAdapterV1,
    FreqtradeProvenanceV1,
    Gate0Outcome,
    InvalidEvaluationError,
    PartitionWindowV1,
    ProfitFactorState,
    RawTradeV1,
    canonical_candle_hash,
)

PAIR = "BTC/USDT"
BASE = datetime(2025, 1, 1, tzinfo=UTC)


def at(hours: int) -> datetime:
    return BASE + timedelta(hours=hours)


def candles(*, price_overrides: dict[int, float] | None = None) -> tuple[CandleV1, ...]:
    overrides = price_overrides or {}
    rows: list[CandleV1] = []
    for hour in range(97):
        close = overrides.get(hour, 100.0 + hour * 0.1)
        rows.append(
            CandleV1(
                pair=PAIR,
                timestamp=at(hour),
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=10.0,
            )
        )
    return tuple(rows)


def benchmark_candles() -> tuple[CandleV1, ...]:
    return tuple(
        CandleV1(
            pair=PAIR,
            timestamp=at(hour),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=100.0,
        )
        for hour in range(97)
    )


def thresholds(**changes: object) -> EvaluationThresholdsV1:
    values: dict[str, object] = {
        "threshold_set_id": "fixture-thresholds-v1",
        "min_trades": 1,
        "min_duration_days": 0.0,
        "min_regimes": 1,
        "max_drawdown_pct": 50.0,
        "min_profit_factor": 0.5,
        "min_edge_mean": -0.01,
        "min_edge_lower_bound": -0.01,
        "max_confidence_interval_width": 1.0,
        "bootstrap_samples": 64,
        "bootstrap_block_size": 2,
        "confidence_level": 0.90,
        "bootstrap_seed": 7,
        "initial_equity": 1_000.0,
        "max_missing_candles": 0,
        "tail_quantile": 0.05,
    }
    values.update(changes)
    return EvaluationThresholdsV1(**values)  # type: ignore[arg-type]


def provenance() -> FreqtradeProvenanceV1:
    return FreqtradeProvenanceV1(
        freqtrade_version="2026.7",
        strategy_class="FixtureStrategy",
        strategy_file_sha256="1" * 64,
        strategy_commit_sha="2" * 40,
        config_sha256="3" * 64,
        exporter_version="fixture-exporter/v1",
        data_format_version="freqtrade-trades/v1",
    )


def manifest(
    source: tuple[CandleV1, ...],
    benchmark: tuple[CandleV1, ...],
    *,
    threshold_values: EvaluationThresholdsV1 | None = None,
    continuation_policy: ContinuationPolicy = ContinuationPolicy.REPORT_ONLY,
) -> EvaluationManifestV1:
    return EvaluationManifestV1(
        manifest_version="evaluation-manifest/v1",
        manifest_id="fixture-manifest-v1",
        approval_reference="issue-604-fixture-only",
        strategy_identifier="FixtureStrategy@" + "2" * 40,
        provenance=provenance(),
        data_source="pinned-fixture",
        data_snapshot_id="fixture-snapshot-v1",
        candle_snapshot_sha256=canonical_candle_hash(source),
        benchmark_snapshot_sha256=canonical_candle_hash(benchmark),
        exchange="bitget",
        trading_mode="futures",
        market_type="linear-perpetual",
        pairs=(PAIR,),
        timeframe="1h",
        timerange_start=at(0),
        timerange_end=at(96),
        calibration=PartitionWindowV1("calibration", at(0), at(24)),
        walk_forward_windows=(
            PartitionWindowV1("walk_forward_1", at(24), at(48)),
            PartitionWindowV1("walk_forward_2", at(48), at(72)),
        ),
        holdout=PartitionWindowV1("holdout", at(72), at(96)),
        cost_config=CostConfig(
            entry_fee_rate=0.0005,
            exit_fee_rate=0.0005,
            slippage_rate=0.0005,
            funding_rate_per_8h=0.0001,
        ),
        thresholds=threshold_values or thresholds(),
        boundary_policy=BoundaryPolicy.STRICT_CONTAINED,
        continuation_policy=continuation_policy,
        mark_to_market_price_field="close",
    )


def trade(
    trade_id: str,
    entry_hour: int,
    exit_hour: int,
    *,
    entry_price: float = 100.0,
    exit_price: float = 110.0,
    side: str = "long",
    regime: str = "bull",
) -> RawTradeV1:
    return RawTradeV1(
        trade_id=trade_id,
        pair=PAIR,
        entry_time=at(entry_hour),
        exit_time=at(exit_hour),
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=1.0,
        side=side,
        regime=regime,
    )


def bundle(
    *,
    source: tuple[CandleV1, ...] | None = None,
    trades: tuple[RawTradeV1, ...] | None = None,
    threshold_values: EvaluationThresholdsV1 | None = None,
    continuation_policy: ContinuationPolicy = ContinuationPolicy.REPORT_ONLY,
) -> EvaluationBundleV1:
    source_rows = source or candles()
    benchmark = benchmark_candles()
    trade_rows = trades or (
        trade("wf1", 26, 28),
        trade("wf2", 50, 52),
        trade("holdout", 74, 76),
    )
    return EvaluationBundleV1(
        manifest=manifest(
            source_rows,
            benchmark,
            threshold_values=threshold_values,
            continuation_policy=continuation_policy,
        ),
        candles=source_rows,
        benchmark_candles=benchmark,
        raw_trades=trade_rows,
        source_metadata=(("fixture", "true"),),
    )


def test_complete_manifest_and_bundle_validate() -> None:
    candidate = bundle()
    assert candidate.validate() == ()
    assert candidate.manifest.thresholds.threshold_set_id == "fixture-thresholds-v1"


def test_manifest_from_dict_missing_thresholds_fails_as_invalid_manifest() -> None:
    payload = bundle().manifest.to_dict()
    payload.pop("thresholds")
    with pytest.raises(InvalidEvaluationError) as exc:
        EvaluationManifestV1.from_dict(payload)
    assert exc.value.code == "INVALID_MANIFEST"


@pytest.mark.parametrize(
    "bad_trade",
    [
        lambda: replace(trade("x", 26, 28), entry_price=0.0),
        lambda: replace(trade("x", 26, 28), exit_price=-1.0),
        lambda: replace(trade("x", 26, 28), quantity=0.0),
        lambda: replace(trade("x", 26, 28), side="buy"),
        lambda: replace(trade("x", 26, 28), pair="ETH/USDT"),
        lambda: replace(trade("x", 26, 28), exit_time=at(26)),
        lambda: replace(trade("x", 26, 28), entry_time=datetime(2025, 1, 2)),
    ],
)
def test_invalid_trade_values_fail_closed(bad_trade: object) -> None:
    with pytest.raises((ValueError, InvalidEvaluationError)):
        candidate = bundle(trades=(bad_trade(),))  # type: ignore[operator]
        candidate.validate()


def test_snapshot_hash_mismatch_is_invalid() -> None:
    candidate = bundle()
    candidate = replace(
        candidate,
        manifest=replace(candidate.manifest, candle_snapshot_sha256="0" * 64),
    )
    result = EvaluationRunnerV1().evaluate(candidate)
    assert result.outcome is Gate0Outcome.INVALID
    assert "CANDLE_SNAPSHOT_HASH_MISMATCH" in result.invalid_reasons


def test_missing_candle_is_invalid_and_reported() -> None:
    incomplete = tuple(row for row in candles() if row.timestamp != at(30))
    candidate = bundle(source=incomplete)
    result = EvaluationRunnerV1().evaluate(candidate)
    assert result.outcome is Gate0Outcome.INVALID
    assert result.data_quality.missing_candles == 1
    assert "MISSING_CANDLES" in result.invalid_reasons


def test_partition_views_are_derived_from_one_canonical_bundle() -> None:
    result = EvaluationRunnerV1().evaluate(bundle())
    assert tuple(result.partition_hashes) == (
        "calibration",
        "holdout",
        "walk_forward_1",
        "walk_forward_2",
    )
    assert result.partition_metrics["walk_forward_1"].trade_count == 1
    assert result.partition_metrics["walk_forward_2"].trade_count == 1
    assert result.partition_metrics["holdout"].trade_count == 1


def test_cross_partition_trade_is_report_only_and_never_authoritative() -> None:
    crossing = trade("crossing", 47, 49)
    result = EvaluationRunnerV1().evaluate(
        bundle(trades=(trade("wf1", 26, 28), crossing, trade("holdout", 74, 76)))
    )
    assert result.outcome is not Gate0Outcome.INVALID
    assert result.continuation_trade_ids == ("crossing",)
    assert sum(metric.trade_count for metric in result.partition_metrics.values()) == 2


def test_cross_partition_trade_without_report_policy_is_invalid() -> None:
    result = EvaluationRunnerV1().evaluate(
        bundle(
            trades=(trade("crossing", 47, 49),),
            continuation_policy=ContinuationPolicy.FORBID,
        )
    )
    assert result.outcome is Gate0Outcome.INVALID
    assert "CROSS_PARTITION_TRADE" in result.invalid_reasons


def test_holdout_change_cannot_change_selection_fingerprint() -> None:
    first = EvaluationRunnerV1().evaluate(bundle())
    changed = EvaluationRunnerV1().evaluate(
        bundle(
            trades=(
                trade("wf1", 26, 28),
                trade("wf2", 50, 52),
                trade("holdout", 74, 76, exit_price=70.0),
            )
        )
    )
    assert first.selection_fingerprint == changed.selection_fingerprint
    assert first.artifact_hash != changed.artifact_hash
    assert (
        first.partition_metrics["holdout"].total_net_pnl
        != changed.partition_metrics["holdout"].total_net_pnl
    )


def test_mark_to_market_drawdown_captures_intratrade_loss() -> None:
    source = candles(price_overrides={27: 50.0, 28: 100.0})
    flat_close = trade("wf1", 26, 28, entry_price=100.0, exit_price=100.0)
    result = EvaluationRunnerV1().evaluate(
        bundle(source=source, trades=(flat_close, trade("holdout", 74, 76)))
    )
    assert result.partition_metrics["walk_forward_1"].max_drawdown_pct > 4.0


def test_no_loss_profit_factor_is_finite_json_state() -> None:
    result = EvaluationRunnerV1().evaluate(bundle())
    metric = result.partition_metrics["walk_forward_1"]
    assert metric.profit_factor is None
    assert metric.profit_factor_state is ProfitFactorState.NO_LOSSES
    payload = result.to_canonical_json()
    assert '"profit_factor":null' in payload
    assert "Infinity" not in payload
    assert "NaN" not in payload
    json.loads(payload)


def test_artifacts_are_deterministic_and_timestamp_free() -> None:
    first = EvaluationRunnerV1().evaluate(bundle())
    second = EvaluationRunnerV1().evaluate(bundle())
    assert first.to_canonical_json() == second.to_canonical_json()
    assert first.to_markdown() == second.to_markdown()
    assert first.artifact_hash == second.artifact_hash
    assert "run_timestamp" not in first.to_canonical_json()


def test_profitable_but_insufficient_sample_extends() -> None:
    result = EvaluationRunnerV1().evaluate(
        bundle(threshold_values=thresholds(min_trades=10))
    )
    assert result.outcome is Gate0Outcome.EXTEND
    assert "INSUFFICIENT_TRADES" in result.outcome_reasons


def test_precise_nonpositive_edge_rejects() -> None:
    losses = (
        trade("wf1", 26, 28, entry_price=100.0, exit_price=99.0),
        trade("wf2", 50, 52, entry_price=100.0, exit_price=99.0),
        trade("holdout", 74, 76, entry_price=100.0, exit_price=99.0),
    )
    result = EvaluationRunnerV1().evaluate(
        bundle(
            trades=losses,
            threshold_values=thresholds(
                min_profit_factor=0.0,
                max_drawdown_pct=99.0,
                min_edge_mean=0.0,
                min_edge_lower_bound=0.0,
                max_confidence_interval_width=1.0,
            ),
        )
    )
    assert result.outcome is Gate0Outcome.REJECT
    assert "EDGE_THRESHOLD_NOT_MET" in result.outcome_reasons


def test_wide_confidence_interval_extends_instead_of_rejecting() -> None:
    volatile = (
        trade("wf1a", 25, 26, entry_price=100.0, exit_price=150.0),
        trade("wf1b", 27, 28, entry_price=100.0, exit_price=50.0),
        trade("wf2a", 49, 50, entry_price=100.0, exit_price=150.0),
        trade("wf2b", 51, 52, entry_price=100.0, exit_price=50.0),
        trade("holdout", 74, 76),
    )
    result = EvaluationRunnerV1().evaluate(
        bundle(
            trades=volatile,
            threshold_values=thresholds(
                min_trades=1,
                min_profit_factor=0.0,
                max_drawdown_pct=99.0,
                min_edge_mean=-1.0,
                min_edge_lower_bound=-1.0,
                max_confidence_interval_width=0.000001,
            ),
        )
    )
    assert result.outcome is Gate0Outcome.EXTEND
    assert "INSUFFICIENT_PRECISION" in result.outcome_reasons


def test_all_predeclared_oos_and_holdout_rules_can_pass_candidate() -> None:
    result = EvaluationRunnerV1().evaluate(bundle())
    assert result.outcome is Gate0Outcome.PASS_CANDIDATE
    assert result.live_authorization is False


def test_freqtrade_adapter_validates_full_provenance_and_imports_only() -> None:
    candidate = bundle()
    export = {
        "provenance": {
            **candidate.manifest.provenance.to_dict(),
            "exchange": "bitget",
            "trading_mode": "futures",
            "pairs": [PAIR],
            "timeframe": "1h",
            "timerange": [at(0).isoformat(), at(96).isoformat()],
        },
        "trades": [
            {
                "trade_id": "adapter-trade",
                "pair": PAIR,
                "open_date": at(26).isoformat(),
                "close_date": at(28).isoformat(),
                "open_rate": 100.0,
                "close_rate": 110.0,
                "amount": 1.0,
                "is_short": False,
                "regime": "bull",
            }
        ],
    }
    imported = FreqtradeExportAdapterV1().import_trades(export, candidate.manifest)
    assert imported == (trade("adapter-trade", 26, 28),)


def test_freqtrade_adapter_fails_on_provenance_mismatch() -> None:
    candidate = bundle()
    export = {
        "provenance": {
            **candidate.manifest.provenance.to_dict(),
            "strategy_commit_sha": "9" * 40,
            "exchange": "bitget",
            "trading_mode": "futures",
            "pairs": [PAIR],
            "timeframe": "1h",
            "timerange": [at(0).isoformat(), at(96).isoformat()],
        },
        "trades": [],
    }
    with pytest.raises(InvalidEvaluationError) as exc:
        FreqtradeExportAdapterV1().import_trades(export, candidate.manifest)
    assert exc.value.code == "FREQTRADE_PROVENANCE_MISMATCH"


def test_legacy_evaluate_api_is_disabled_with_migration_error() -> None:
    harness = object.__new__(StrategyEvaluationHarness)
    with pytest.raises(LegacyEvaluationAPIError, match="EvaluationBundleV1"):
        harness.evaluate([], {})
