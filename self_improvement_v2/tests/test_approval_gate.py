"""Unit tests for the ApprovalGateManager."""

from __future__ import annotations

from datetime import UTC, datetime

from si_v2.adapters.dry_run_stub import DryRunTelegramAdapter
from si_v2.approve.approval_gate import (
    ApprovalConfig,
    ApprovalDecision,
    ApprovalGateManager,
    ApprovalStatus,
)
from si_v2.backtest.walk_forward import WalkForwardResult
from si_v2.deploy.shadow_logger import ShadowLogger
from si_v2.state.schemas import BacktestResult, BotConfig, MutationCandidate


def _make_backtest(
    *,
    passed: bool = True,
    profit_total_pct: float = 3.5,
    max_drawdown_pct: float = 0.05,
    total_trades: int = 20,
) -> BacktestResult:
    return BacktestResult(
        bot_id="bot_a",
        candidate_sha256="sha-1",
        total_trades=total_trades,
        profit_total_pct=profit_total_pct,
        profit_total_abs=70.0,
        max_drawdown_pct=max_drawdown_pct,
        win_rate_pct=60.0,
        sharpe=1.5,
        profit_factor=1.4,
        duration_seconds=100.0,
        passed=passed,
        ts=datetime.now(UTC),
    )


def _make_walk_forward(
    *,
    passed: bool = True,
    stability_score: float = 0.8,
    reason: str = "all criteria met",
) -> WalkForwardResult:
    return WalkForwardResult(
        in_sample_metrics=_make_backtest(),
        out_of_sample_metrics=_make_backtest(),
        stability_score=stability_score,
        passed=passed,
        reason=reason,
    )


def _make_candidate() -> MutationCandidate:
    return MutationCandidate(
        bot_id="bot_a",
        bot_name="Bot Alpha",
        candidate_sha256="sha-1",
        source_decision="mutate",
        parameters={
            "rsi_period": 14,
            "stoploss_pct": -0.02,
            "take_profit_pct": 0.035,
            "stake_factor": 1.0,
            "max_open_trades": 2,
            "cooldown_candles": 9,
        },
        active_overlay_candidates={},
    )


def _make_bot_config() -> BotConfig:
    return BotConfig(
        bot_id="bot_a",
        bot_name="Bot Alpha",
        alias="bot_alpha",
        container="bot_alpha_container",
        strategy="TestStrategy",
    )


def _build_manager() -> tuple[ApprovalGateManager, DryRunTelegramAdapter, ShadowLogger]:
    telegram = DryRunTelegramAdapter()
    logger = ShadowLogger(log_dir=None)
    mgr = ApprovalGateManager(
        telegram_adapter=telegram,
        approval_config=ApprovalConfig(),
        shadow_logger=logger,
    )
    return mgr, telegram, logger


class TestApprovalGateRejectionPaths:
    """Each individual guardrail rejects the candidate."""

    def test_rejects_when_backtest_not_passed(self) -> None:
        mgr, telegram, _ = _build_manager()
        decision = mgr.evaluate(
            backtest_result=_make_backtest(passed=False),
            walk_forward_result=_make_walk_forward(),
            bot_config=_make_bot_config(),
            candidate=_make_candidate(),
        )
        assert decision.status == ApprovalStatus.REJECTED
        assert "backtest.passed=False" in decision.reason
        assert telegram.get_messages() == []

    def test_rejects_when_walk_forward_not_passed(self) -> None:
        mgr, _, _ = _build_manager()
        decision = mgr.evaluate(
            backtest_result=_make_backtest(),
            walk_forward_result=_make_walk_forward(passed=False),
            bot_config=_make_bot_config(),
            candidate=_make_candidate(),
        )
        assert decision.status == ApprovalStatus.REJECTED
        assert "walk_forward.passed=False" in decision.reason

    def test_rejects_when_profit_non_positive(self) -> None:
        mgr, _, _ = _build_manager()
        decision = mgr.evaluate(
            backtest_result=_make_backtest(profit_total_pct=-1.0),
            walk_forward_result=_make_walk_forward(),
            bot_config=_make_bot_config(),
            candidate=_make_candidate(),
        )
        assert decision.status == ApprovalStatus.REJECTED
        assert "profit_total_pct" in decision.reason

    def test_rejects_when_profit_zero(self) -> None:
        mgr, _, _ = _build_manager()
        decision = mgr.evaluate(
            backtest_result=_make_backtest(profit_total_pct=0.0),
            walk_forward_result=_make_walk_forward(),
            bot_config=_make_bot_config(),
            candidate=_make_candidate(),
        )
        assert decision.status == ApprovalStatus.REJECTED

    def test_rejects_when_drawdown_too_high(self) -> None:
        mgr, _, _ = _build_manager()
        decision = mgr.evaluate(
            backtest_result=_make_backtest(max_drawdown_pct=0.20),
            walk_forward_result=_make_walk_forward(),
            bot_config=_make_bot_config(),
            candidate=_make_candidate(),
        )
        assert decision.status == ApprovalStatus.REJECTED
        assert "max_drawdown_pct" in decision.reason

    def test_rejects_when_stability_too_low(self) -> None:
        mgr, _, _ = _build_manager()
        decision = mgr.evaluate(
            backtest_result=_make_backtest(),
            walk_forward_result=_make_walk_forward(stability_score=0.3),
            bot_config=_make_bot_config(),
            candidate=_make_candidate(),
        )
        assert decision.status == ApprovalStatus.REJECTED
        assert "stability_score" in decision.reason

    def test_rejects_when_too_few_trades(self) -> None:
        mgr, _, _ = _build_manager()
        decision = mgr.evaluate(
            backtest_result=_make_backtest(total_trades=2),
            walk_forward_result=_make_walk_forward(),
            bot_config=_make_bot_config(),
            candidate=_make_candidate(),
        )
        assert decision.status == ApprovalStatus.REJECTED
        assert "total_trades" in decision.reason

    def test_rejects_when_walk_forward_reason_insufficient(self) -> None:
        mgr, _, _ = _build_manager()
        decision = mgr.evaluate(
            backtest_result=_make_backtest(),
            walk_forward_result=_make_walk_forward(
                passed=False,
                stability_score=0.0,
                reason="insufficient data: 5 trades < 30 required",
            ),
            bot_config=_make_bot_config(),
            candidate=_make_candidate(),
        )
        assert decision.status == ApprovalStatus.REJECTED
        assert "insufficient" in decision.reason


class TestApprovalGatePendingPath:
    """When no guardrail triggers, status is pending and Telegram is called."""

    def test_emits_pending_decision_and_telegram_message(self) -> None:
        mgr, telegram, logger = _build_manager()
        decision = mgr.evaluate(
            backtest_result=_make_backtest(),
            walk_forward_result=_make_walk_forward(),
            bot_config=_make_bot_config(),
            candidate=_make_candidate(),
        )
        assert decision.status == ApprovalStatus.PENDING
        assert decision.telegram_message_id is not None
        assert decision.auto_reject_reasons == []
        msgs = telegram.get_messages()
        assert len(msgs) == 1
        assert msgs[0].message_type == "approval_request"
        assert msgs[0].bot_id == "bot_a"
        assert msgs[0].metadata["status"] == "pending_human_approval"
        # Shadow logger should have one entry from the approve phase
        entries = logger.get_entries("bot_a")
        assert any(e["phase"] == "approve" for e in entries)


class TestApprovalGateAutoApproveImpossible:
    """Auto-approve is impossible in Phase D."""

    def test_no_approved_member(self) -> None:
        assert "approved" not in [s.value for s in ApprovalStatus]
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.PENDING.value == "pending"

    def test_evaluate_never_returns_approved(self) -> None:
        mgr, _, _ = _build_manager()
        # Run with the cleanest possible inputs — must still be pending
        decision = mgr.evaluate(
            backtest_result=_make_backtest(),
            walk_forward_result=_make_walk_forward(),
            bot_config=_make_bot_config(),
            candidate=_make_candidate(),
        )
        assert decision.status != "approved"
        assert decision.status in (
            ApprovalStatus.REJECTED,
            ApprovalStatus.PENDING,
        )


class TestApprovalDecisionStructure:
    """ApprovalDecision carries the right fields."""

    def test_rejected_decision_has_no_telegram_id(self) -> None:
        mgr, _, _ = _build_manager()
        decision = mgr.evaluate(
            backtest_result=_make_backtest(passed=False),
            walk_forward_result=_make_walk_forward(),
            bot_config=_make_bot_config(),
            candidate=_make_candidate(),
        )
        assert isinstance(decision, ApprovalDecision)
        assert decision.telegram_message_id is None
        assert decision.bot_id == "bot_a"
        assert decision.candidate_sha256 == "sha-1"
        assert decision.auto_reject_reasons  # non-empty
