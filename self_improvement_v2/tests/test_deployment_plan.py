"""Unit tests for the DeploymentPlanOrchestrator."""

from __future__ import annotations

from datetime import UTC, datetime

from si_v2.adapters.dry_run_stub import DryRunTelegramAdapter
from si_v2.approve.approval_gate import ApprovalConfig, ApprovalGateManager
from si_v2.backtest.walk_forward import WalkForwardResult
from si_v2.deploy.deployment_plan import (
    DeploymentPhase,
    DeploymentPlanOrchestrator,
    DeploymentStatus,
)
from si_v2.deploy.rollback_plan import RollbackPlanManager
from si_v2.deploy.shadow_logger import ShadowLogger
from si_v2.deploy.shadow_mode import ShadowModeManager
from si_v2.state.schemas import BacktestResult, BotConfig, MutationCandidate


def _backtest(
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


def _walk_forward(
    *,
    passed: bool = True,
    stability_score: float = 0.8,
    reason: str = "all criteria met",
) -> WalkForwardResult:
    return WalkForwardResult(
        in_sample_metrics=_backtest(),
        out_of_sample_metrics=_backtest(),
        stability_score=stability_score,
        passed=passed,
        reason=reason,
    )


def _candidate() -> MutationCandidate:
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


def _bot_config() -> BotConfig:
    return BotConfig(
        bot_id="bot_a",
        bot_name="Bot Alpha",
        alias="bot_alpha",
        container="bot_alpha_container",
        strategy="TestStrategy",
    )


def _build_orchestrator(
    clock,
    log_dir=None,
) -> tuple[DeploymentPlanOrchestrator, ShadowLogger, DryRunTelegramAdapter]:
    telegram = DryRunTelegramAdapter()
    logger = ShadowLogger(log_dir=log_dir)
    approval = ApprovalGateManager(
        telegram_adapter=telegram,
        approval_config=ApprovalConfig(),
        shadow_logger=logger,
    )
    rollback = RollbackPlanManager()
    shadow = ShadowModeManager(clock=clock, default_duration_hours=72)
    orch = DeploymentPlanOrchestrator(
        approval_manager=approval,
        rollback_manager=rollback,
        shadow_manager=shadow,
        shadow_logger=logger,
        clock=clock,
    )
    return orch, logger, telegram


class TestDeploymentPlanRejected:
    """A losing candidate yields a rejected plan."""

    def test_losing_candidate_is_rejected(self) -> None:
        from datetime import datetime

        base = datetime(2026, 1, 1, tzinfo=UTC)
        clock = lambda: base  # noqa: E731

        orch, logger, telegram = _build_orchestrator(clock)
        plan = orch.build_deployment_plan(
            candidate=_candidate(),
            bot_config=_bot_config(),
            backtest_result=_backtest(profit_total_pct=-1.0),
            walk_forward_result=_walk_forward(),
            human_approved=False,
        )
        assert plan.status == DeploymentStatus.REJECTED.value
        # No telegram approval request should have been sent
        assert telegram.get_messages() == []
        # At least one entry logged per pipeline phase
        entries = logger.get_entries("bot_a")
        phases = {e["phase"] for e in entries}
        assert "propose" in phases
        assert "backtest" in phases
        assert "walk_forward" in phases
        assert "approve" in phases


class TestDeploymentPlanPendingApproval:
    """A passing candidate without human approval yields pending_approval."""

    def test_passing_candidate_yields_pending_approval(self) -> None:
        from datetime import datetime

        clock = lambda: datetime(2026, 1, 1, tzinfo=UTC)  # noqa: E731

        orch, _logger, telegram = _build_orchestrator(clock)
        plan = orch.build_deployment_plan(
            candidate=_candidate(),
            bot_config=_bot_config(),
            backtest_result=_backtest(),
            walk_forward_result=_walk_forward(),
            human_approved=False,
        )
        assert plan.status == DeploymentStatus.PENDING_APPROVAL.value
        assert plan.phase != DeploymentPhase.SHADOW
        # Telegram approval request was captured
        assert len(telegram.get_messages()) == 1
        assert telegram.get_messages()[0].message_type == "approval_request"

    def test_human_approved_yields_ready_for_shadow(self) -> None:
        from datetime import datetime

        clock = lambda: datetime(2026, 1, 1, tzinfo=UTC)  # noqa: E731

        orch, _logger, _ = _build_orchestrator(clock)
        plan = orch.build_deployment_plan(
            candidate=_candidate(),
            bot_config=_bot_config(),
            backtest_result=_backtest(),
            walk_forward_result=_walk_forward(),
            human_approved=True,
        )
        assert plan.status == DeploymentStatus.READY_FOR_SHADOW.value
        assert plan.phase == DeploymentPhase.SHADOW
        assert plan.shadow_start_utc is not None
        assert plan.shadow_end_utc is not None
        # "shadow" step recorded in the plan steps
        assert any("shadow" in s for s in plan.steps)


class TestDeploymentPlanLogsEveryStep:
    """Each pipeline step must be logged to the shadow logger."""

    def test_every_step_logged(self) -> None:
        from datetime import datetime

        clock = lambda: datetime(2026, 1, 1, tzinfo=UTC)  # noqa: E731

        orch, logger, _ = _build_orchestrator(clock)
        orch.build_deployment_plan(
            candidate=_candidate(),
            bot_config=_bot_config(),
            backtest_result=_backtest(),
            walk_forward_result=_walk_forward(),
            human_approved=True,
        )
        entries = logger.get_entries("bot_a")
        phases: list[str] = [str(e["phase"]) for e in entries if isinstance(e["phase"], str)]
        # We expect at least one log per phase
        for required in ("propose", "backtest", "walk_forward", "approve", "shadow"):
            assert required in phases, f"missing phase log: {required}"


class TestDeploymentPlanNoLiveWrites:
    """The orchestrator must not write any live config files."""

    def test_no_live_writes_outside_log_dir(self, tmp_path, monkeypatch: object) -> None:
        import os
        from datetime import datetime

        # The shadow logger is given tmp_path. We then assert that no
        # files appear anywhere else.
        clock = lambda: datetime(2026, 1, 1, tzinfo=UTC)  # noqa: E731

        # Use a tmp dir and ensure no file is written outside it
        isolated = tmp_path / "isolated"
        isolated.mkdir()

        orch, _logger, _ = _build_orchestrator(clock, log_dir=isolated)
        orch.build_deployment_plan(
            candidate=_candidate(),
            bot_config=_bot_config(),
            backtest_result=_backtest(),
            walk_forward_result=_walk_forward(),
            human_approved=True,
        )

        # Walk tmp_path's tree to confirm only the shadow_* files were created
        paths = list(tmp_path.rglob("*"))
        # We should have: isolated/ and isolated/shadow_bot_a.jsonl at minimum
        for p in paths:
            assert "shadow_" in p.name or p.is_dir()
        # And no files at the trading project root
        project_root = "/home/hermes/projects/trading/self_improvement_v2"
        assert not os.path.exists(f"{project_root}/bot_a_config.json")
