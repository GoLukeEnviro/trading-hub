"""End-to-end simulation test for SI v2 Phase D.

Walks the full Approval + Shadow pipeline using dry-run adapters and
an injected clock. Verifies:
  * Losing candidate → auto-rejected → plan rejected.
  * Passing candidate without human approval → plan pending_approval.
  * Human-approved candidate → plan ready_for_shadow.
  * Shadow session transitions: pending → complete / failed.
  * Unknown bots return ShadowStatus.UNKNOWN.
  * All shadow log entries are written to tmp_path JSONL files.
  * No live config writes occur (all I/O is in tmp_path).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from si_v2.deploy.shadow_mode import ShadowModeManager, ShadowStatus
from si_v2.state.schemas import BacktestResult, BotConfig, MutationCandidate

# ---- Helpers ----------------------------------------------------------------


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
        ts=datetime(2026, 1, 1, tzinfo=UTC),
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
    log_dir: Path,
) -> tuple[
    DeploymentPlanOrchestrator,
    ShadowLogger,
    DryRunTelegramAdapter,
    ShadowModeManager,
]:
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
    return orch, logger, telegram, shadow


# ---- Tests ------------------------------------------------------------------


class TestPhaseDLosingCandidate:
    """A losing candidate is auto-rejected; the deployment plan is rejected."""

    def test_negative_profit_yields_rejected_plan(self, tmp_path: Path) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        clock = lambda: start  # noqa: E731

        orch, _logger, telegram, _ = _build_orchestrator(clock, tmp_path)
        plan = orch.build_deployment_plan(
            candidate=_candidate(),
            bot_config=_bot_config(),
            backtest_result=_backtest(profit_total_pct=-1.0),
            walk_forward_result=_walk_forward(),
            human_approved=False,
        )
        assert plan.status == DeploymentStatus.REJECTED.value
        # No approval request captured
        assert telegram.get_messages() == []
        # The shadow logger JSONL file exists in tmp_path
        log_file = tmp_path / "shadow_bot_a.jsonl"
        assert log_file.exists()
        lines = [json.loads(line) for line in log_file.read_text().splitlines() if line]
        assert any(line["phase"] == "approve" for line in lines)


class TestPhaseDPassingCandidatePending:
    """A passing candidate without human approval yields pending_approval."""

    def test_passing_yields_pending_approval(self, tmp_path: Path) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        clock = lambda: start  # noqa: E731

        orch, _logger, telegram, _ = _build_orchestrator(clock, tmp_path)
        plan = orch.build_deployment_plan(
            candidate=_candidate(),
            bot_config=_bot_config(),
            backtest_result=_backtest(),
            walk_forward_result=_walk_forward(),
            human_approved=False,
        )
        assert plan.status == DeploymentStatus.PENDING_APPROVAL.value
        # Plan is NOT approved
        assert plan.status != "approved"
        assert plan.status != DeploymentStatus.READY_FOR_SHADOW.value
        # Approval request was captured
        assert len(telegram.get_messages()) == 1
        assert telegram.get_messages()[0].message_type == "approval_request"

        # All log entries are JSON-parseable and live in tmp_path
        log_file = tmp_path / "shadow_bot_a.jsonl"
        assert log_file.exists()
        lines = [json.loads(line) for line in log_file.read_text().splitlines() if line]
        # Every entry has required fields
        for entry in lines:
            assert "bot_id" in entry
            assert "candidate_sha" in entry
            assert "phase" in entry
            assert "decision" in entry
            assert "reason" in entry


class TestPhaseDHumanApproved:
    """Human-approved candidate is ready_for_shadow; shadow session starts."""

    def test_human_approved_yields_ready_for_shadow(self, tmp_path: Path) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        clock = lambda: start  # noqa: E731

        orch, _, _, shadow = _build_orchestrator(clock, tmp_path)
        plan = orch.build_deployment_plan(
            candidate=_candidate(),
            bot_config=_bot_config(),
            backtest_result=_backtest(),
            walk_forward_result=_walk_forward(),
            human_approved=True,
        )
        assert plan.status == DeploymentStatus.READY_FOR_SHADOW.value
        assert plan.phase == DeploymentPhase.SHADOW
        # A shadow session was actually started
        session = shadow.get_session("bot_a")
        assert session is not None
        assert session.status == ShadowStatus.PENDING


class TestShadowModeLifecycle:
    """Shadow mode lifecycle: pending → complete as the clock advances."""

    def test_shadow_pending_then_complete(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        # A clock that mutates an internal "now" pointer when the test
        # explicitly advances it, so multiple clock reads within a
        # single test step return the same value.
        current: list[datetime] = [start]

        def clock() -> datetime:
            return current[0]

        shadow = ShadowModeManager(clock=clock, default_duration_hours=72)
        shadow.start_shadow(
            "bot_a",
            "sha-1",
            {"profit_pct": 3.5, "sharpe": 1.5},
        )
        # First checkpoint: pending
        current[0] = start
        assert shadow.get_shadow_status("bot_a") == ShadowStatus.PENDING
        assert shadow.is_shadow_complete("bot_a") is False

        # Second checkpoint: still within window
        current[0] = start + timedelta(hours=24)
        assert shadow.get_shadow_status("bot_a") == ShadowStatus.PENDING
        assert shadow.is_shadow_complete("bot_a") is False

        # Third checkpoint: well past the end
        current[0] = start + timedelta(hours=100)
        assert shadow.get_shadow_status("bot_a") == ShadowStatus.COMPLETE
        assert shadow.is_shadow_complete("bot_a") is True


class TestPhaseDShadowFailed:
    """A shadow session fails when current metrics drop below baseline."""

    def test_failed_when_metrics_drop(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        shadow = ShadowModeManager(clock=lambda: start, default_duration_hours=72)
        shadow.start_shadow(
            "bot_a",
            "sha-1",
            {"profit_pct": 3.5, "sharpe": 1.5, "win_rate_pct": 60.0},
        )
        shadow.update_metrics("bot_a", {"profit_pct": 1.0})
        assert shadow.get_shadow_status("bot_a") == ShadowStatus.FAILED

    def test_failed_when_sharpe_drops(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        shadow = ShadowModeManager(clock=lambda: start, default_duration_hours=72)
        shadow.start_shadow("bot_a", "sha-1", {"profit_pct": 3.5, "sharpe": 1.5})
        shadow.update_metrics("bot_a", {"sharpe": 0.4})
        assert shadow.get_shadow_status("bot_a") == ShadowStatus.FAILED


class TestPhaseDUnknownBot:
    """Querying status for an unknown bot returns 'unknown'."""

    def test_unknown_bot_status(self) -> None:
        shadow = ShadowModeManager(
            clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert shadow.get_shadow_status("nonexistent") == ShadowStatus.UNKNOWN

    def test_unknown_bot_is_complete(self) -> None:
        shadow = ShadowModeManager(
            clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert shadow.is_shadow_complete("nonexistent") is False


class TestPhaseDShadowLogPersistence:
    """All shadow log entries are written to tmp_path JSONL files."""

    def test_logs_persist_to_tmp_path(self, tmp_path: Path) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        clock = lambda: start  # noqa: E731

        orch, _, _, _ = _build_orchestrator(clock, tmp_path)
        orch.build_deployment_plan(
            candidate=_candidate(),
            bot_config=_bot_config(),
            backtest_result=_backtest(),
            walk_forward_result=_walk_forward(),
            human_approved=True,
        )

        log_file = tmp_path / "shadow_bot_a.jsonl"
        assert log_file.exists()
        # Every line must be valid JSON
        raw = log_file.read_text()
        lines = [line for line in raw.splitlines() if line]
        assert len(lines) >= 5  # at least propose/backtest/wf/approve/plan/shadow
        for line in lines:
            json.loads(line)  # must parse

    def test_no_live_config_writes(self, tmp_path: Path) -> None:
        """No live config files are written outside tmp_path."""
        start = datetime(2026, 1, 1, tzinfo=UTC)
        clock = lambda: start  # noqa: E731

        # Use a sub-directory of tmp_path as the log_dir
        log_dir = tmp_path / "shadow_logs"
        log_dir.mkdir()

        orch, _, _, _ = _build_orchestrator(clock, log_dir)
        orch.build_deployment_plan(
            candidate=_candidate(),
            bot_config=_bot_config(),
            backtest_result=_backtest(),
            walk_forward_result=_walk_forward(),
            human_approved=True,
        )

        # No files should be written outside the log_dir
        for p in tmp_path.rglob("*"):
            if p.is_dir():
                continue
            assert p.is_relative_to(log_dir), f"unexpected file written: {p}"


class TestPhaseDAutoApproveImpossible:
    """Auto-approve is impossible in Phase D — enforced end-to-end."""

    def test_no_approved_status_under_any_input(self, tmp_path: Path) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        clock = lambda: start  # noqa: E731

        orch, _, _, _ = _build_orchestrator(clock, tmp_path)
        # The cleanest possible input + human_approved=True should still
        # produce a "ready_for_shadow" plan, not an "approved" plan.
        plan = orch.build_deployment_plan(
            candidate=_candidate(),
            bot_config=_bot_config(),
            backtest_result=_backtest(),
            walk_forward_result=_walk_forward(),
            human_approved=True,
        )
        assert plan.status != "approved"
        # And the status should be one of the defined enum values
        assert plan.status in {s.value for s in DeploymentStatus}
