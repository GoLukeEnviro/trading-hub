"""Test Pydantic state schemas: creation and JSON roundtrip."""

from __future__ import annotations

from datetime import UTC, datetime

from si_v2.state.schemas import (
    AnalysisResult,
    ApprovalGate,
    BacktestResult,
    BotConfig,
    LoopStatus,
    MutationCandidate,
    MutationOverlay,
    SafeParameters,
    WindowStats,
)


def test_safe_parameters_creation() -> None:
    """SafeParameters can be created with valid data."""
    params = SafeParameters(
        rsi_period=14,
        stoploss_pct=-0.02,
        take_profit_pct=0.035,
        stake_factor=1.0,
        max_open_trades=2,
        cooldown_candles=9,
    )
    assert params.rsi_period == 14
    assert params.stoploss_pct == -0.02


def test_safe_parameters_roundtrip() -> None:
    """SafeParameters survives JSON serialization roundtrip."""
    params = SafeParameters(
        rsi_period=14,
        stoploss_pct=-0.02,
        take_profit_pct=0.035,
        stake_factor=1.0,
        max_open_trades=2,
        cooldown_candles=9,
    )
    json_str = params.model_dump_json()
    restored = SafeParameters.model_validate_json(json_str)
    assert restored == params


def test_window_stats_creation() -> None:
    """WindowStats can be created with valid data."""
    stats = WindowStats(trades=10, wins=6, losses=4, win_rate_pct=60.0)
    assert stats.trades == 10
    assert stats.win_rate_pct == 60.0


def test_window_stats_roundtrip() -> None:
    """WindowStats survives JSON roundtrip."""
    stats = WindowStats(trades=10, wins=6, losses=4, win_rate_pct=60.0, pnl_abs=50.0)
    json_str = stats.model_dump_json()
    restored = WindowStats.model_validate_json(json_str)
    assert restored == stats


def test_analysis_result_creation() -> None:
    """AnalysisResult can be created with valid data."""
    result = AnalysisResult(
        bot_id="bot_a",
        bot_name="Bot A",
        decision="hold",
        ts=datetime.now(UTC),
        windows={"12h": WindowStats(trades=0, wins=0, losses=0)},
    )
    assert result.bot_id == "bot_a"
    assert result.decision == "hold"


def test_analysis_result_roundtrip() -> None:
    """AnalysisResult survives JSON roundtrip."""
    result = AnalysisResult(
        bot_id="bot_a",
        bot_name="Bot A",
        decision="hold",
        ts=datetime(2026, 6, 7, 13, 45, 50, tzinfo=UTC),
        windows={"12h": WindowStats(trades=5, wins=3, losses=2, win_rate_pct=60.0)},
    )
    json_str = result.model_dump_json()
    restored = AnalysisResult.model_validate_json(json_str)
    assert restored.bot_id == result.bot_id
    assert restored.windows["12h"].trades == 5


def test_approval_gate_creation() -> None:
    """ApprovalGate can be created with valid data."""
    gate = ApprovalGate(approved=True, candidate_sha256="9acaf521d47eb514")
    assert gate.approved is True


def test_approval_gate_roundtrip() -> None:
    """ApprovalGate survives JSON roundtrip."""
    gate = ApprovalGate(approved=True, candidate_sha256="9acaf521d47eb514")
    json_str = gate.model_dump_json()
    restored = ApprovalGate.model_validate_json(json_str)
    assert restored == gate


def test_loop_status_creation() -> None:
    """LoopStatus can be created with valid data."""
    status = LoopStatus(
        alias="bot_a",
        bot_name="Bot A",
        container="trading-freqtrade-freqforge-1",
        strategy="FreqForge_Override",
        status="flagged",
        health_score_0_100=40,
        last_decision="hold",
        stale_flags=["no_trades"],
        updated_ts=datetime.now(UTC),
    )
    assert status.alias == "bot_a"
    assert status.health_score_0_100 == 40


def test_loop_status_roundtrip() -> None:
    """LoopStatus survives JSON roundtrip."""
    ts = datetime(2026, 6, 6, 23, 37, 15, tzinfo=UTC)
    status = LoopStatus(
        alias="bot_a",
        bot_name="Bot A - FreqForge Core",
        container="trading-freqtrade-freqforge-1",
        strategy="FreqForge_Override",
        status="flagged",
        health_score_0_100=40,
        last_decision="hold",
        stale_flags=["no_trades", "blocked"],
        updated_ts=ts,
    )
    json_str = status.model_dump_json()
    restored = LoopStatus.model_validate_json(json_str)
    assert restored.alias == status.alias
    assert restored.stale_flags == ["no_trades", "blocked"]


def test_mutation_candidate_creation() -> None:
    """MutationCandidate can be created with valid data."""
    candidate = MutationCandidate(
        bot_id="bot_a",
        bot_name="Bot A",
        candidate_sha256="0f7be7f8cf14f546",
        source_decision="hold",
        parameters={"rsi_period": 14, "stoploss_pct": -0.02},
        active_overlay_candidates={"stoploss_pct": -0.02},
        metadata_only_candidates={"rsi_period": 14},
    )
    assert candidate.bot_id == "bot_a"


def test_mutation_candidate_roundtrip() -> None:
    """MutationCandidate survives JSON roundtrip."""
    candidate = MutationCandidate(
        bot_id="bot_a",
        bot_name="Bot A",
        candidate_sha256="0f7be7f8cf14f546",
        source_decision="hold",
        parameters={"rsi_period": 14, "stoploss_pct": -0.02},
        active_overlay_candidates={"stoploss_pct": -0.02},
        metadata_only_candidates={"rsi_period": 14},
    )
    data = candidate.model_dump()
    restored = MutationCandidate.model_validate(data)
    assert restored.bot_id == candidate.bot_id
    assert restored.parameters == candidate.parameters


def test_mutation_overlay_creation() -> None:
    """MutationOverlay can be created with valid data."""
    overlay = MutationOverlay(
        max_open_trades=2,
        stake_amount=20.0,
        stoploss=-0.02,
        minimal_roi={"0": 0.035},
    )
    assert overlay.max_open_trades == 2


def test_mutation_overlay_roundtrip() -> None:
    """MutationOverlay survives JSON roundtrip."""
    overlay = MutationOverlay(
        max_open_trades=2,
        stake_amount=20.0,
        stoploss=-0.02,
        minimal_roi={"0": 0.035},
    )
    json_str = overlay.model_dump_json()
    restored = MutationOverlay.model_validate_json(json_str)
    assert restored == overlay


def test_backtest_result_creation() -> None:
    """BacktestResult can be created with valid data."""
    result = BacktestResult(
        bot_id="bot_a",
        candidate_sha256="abc123",
        total_trades=42,
        profit_total_pct=3.5,
        profit_total_abs=70.0,
        max_drawdown_pct=5.0,
        win_rate_pct=60.0,
        duration_seconds=10.0,
        passed=True,
        ts=datetime.now(UTC),
    )
    assert result.total_trades == 42


def test_backtest_result_roundtrip() -> None:
    """BacktestResult survives JSON roundtrip."""
    ts = datetime(2026, 6, 7, 12, 0, 0, tzinfo=UTC)
    result = BacktestResult(
        bot_id="bot_a",
        candidate_sha256="abc123",
        total_trades=42,
        profit_total_pct=3.5,
        profit_total_abs=70.0,
        max_drawdown_pct=5.0,
        win_rate_pct=60.0,
        duration_seconds=10.0,
        passed=True,
        ts=ts,
    )
    json_str = result.model_dump_json()
    restored = BacktestResult.model_validate_json(json_str)
    assert restored.total_trades == 42


def test_bot_config_creation() -> None:
    """BotConfig can be created with valid data."""
    config = BotConfig(
        bot_id="bot_a",
        bot_name="Bot A",
        alias="bot_a",
        container="trading-freqtrade-freqforge-1",
        strategy="FreqForge_Override",
        schedules={"analyze": "*/15 * * * *"},
    )
    assert config.bot_id == "bot_a"


def test_bot_config_roundtrip() -> None:
    """BotConfig survives JSON roundtrip."""
    config = BotConfig(
        bot_id="bot_a",
        bot_name="Bot A",
        alias="bot_a",
        container="trading-freqtrade-freqforge-1",
        strategy="FreqForge_Override",
        schedules={"analyze": "*/15 * * * *"},
    )
    json_str = config.model_dump_json()
    restored = BotConfig.model_validate_json(json_str)
    assert restored == config
