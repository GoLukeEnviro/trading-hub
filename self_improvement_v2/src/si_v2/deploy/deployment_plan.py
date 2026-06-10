"""Staged deployment plan orchestrator — simulation only.

Provides a DeploymentPlanOrchestrator that walks a candidate through
the propose → backtest → walk_forward → approval → plan pipeline and
produces a DeploymentPlan describing what WOULD happen in a real
deployment. No live configs are ever written, no Freqtrade is
restarted, no Docker actions are taken.

The orchestrator uses a caller-supplied clock so time-dependent
behaviour is fully testable. The status field of a DeploymentPlan is
one of: "blocked", "rejected", "pending_approval", "ready_for_shadow".
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from si_v2.approve.approval_gate import ApprovalDecision, ApprovalGateManager
from si_v2.backtest.walk_forward import WalkForwardResult
from si_v2.deploy.rollback_plan import RollbackPlanManager
from si_v2.deploy.shadow_logger import ShadowLogger
from si_v2.deploy.shadow_mode import ShadowModeManager
from si_v2.state.schemas import BacktestResult, BotConfig, MutationCandidate


class DeploymentPhase(StrEnum):
    """The phases of a deployment plan pipeline."""

    PROPOSE = "propose"
    BACKTEST = "backtest"
    WALK_FORWARD = "walk_forward"
    APPROVAL = "approval"
    PLAN_READY = "plan_ready"
    SHADOW = "shadow"


# Status values used in DeploymentPlan.status
class DeploymentStatus(StrEnum):
    """Terminal/intermediate status values for a deployment plan."""

    BLOCKED = "blocked"
    REJECTED = "rejected"
    PENDING_APPROVAL = "pending_approval"
    READY_FOR_SHADOW = "ready_for_shadow"


class DeploymentPlan(BaseModel):
    """A pure data model describing a would-be deployment."""

    model_config = ConfigDict(strict=False)

    bot_id: str
    candidate_sha: str
    phase: DeploymentPhase
    status: str
    steps: list[str] = Field(default_factory=list)
    shadow_start_utc: str | None = None
    shadow_end_utc: str | None = None
    reason: str


class DeploymentPlanOrchestrator:
    """Builds a DeploymentPlan by walking the candidate pipeline.

    The orchestrator does not perform any live actions — it only
    threads a candidate through the approval and shadow stages and
    emits a DeploymentPlan that documents what a real deployment would
    do. Every step is logged to the ShadowLogger with its phase.
    """

    def __init__(
        self,
        approval_manager: ApprovalGateManager,
        rollback_manager: RollbackPlanManager,
        shadow_manager: ShadowModeManager,
        shadow_logger: ShadowLogger,
        clock: Callable[[], datetime],
    ) -> None:
        """Initialise with the approval, rollback, shadow, and logger.

        Args:
            approval_manager: Manager that evaluates approval decisions.
            rollback_manager: Manager that records snapshots and plans.
            shadow_manager: Manager that runs shadow sessions.
            shadow_logger: Logger that records each pipeline step.
            clock: Callable returning the current UTC datetime.
        """
        self._approval_manager = approval_manager
        self._rollback_manager = rollback_manager
        self._shadow_manager = shadow_manager
        self._shadow_logger = shadow_logger
        self._clock = clock

    def build_deployment_plan(
        self,
        candidate: MutationCandidate,
        bot_config: BotConfig,
        backtest_result: BacktestResult,
        walk_forward_result: WalkForwardResult,
        human_approved: bool,
    ) -> DeploymentPlan:
        """Build a DeploymentPlan for the given candidate.

        Pipeline:
          propose → backtest → walk_forward → approval → plan.

        Logic:
          * If approval.status is "rejected":
              - If human_approved is True, the candidate is still
                rejected (auto-approval is impossible in Phase D).
              - If human_approved is False, plan status is
                "pending_approval" with reason noting auto-rejection.
            (We resolve this by checking approval first; if the
            approval status is "rejected", the plan is "rejected".)
          * If approval.status is "pending" and human_approved is
            False, plan status is "pending_approval".
          * If approval.status is "pending" and human_approved is
            True, plan status is "ready_for_shadow" and a shadow
            session is started.

        Args:
            candidate: The mutation candidate to plan for.
            bot_config: The bot configuration.
            backtest_result: The backtest result for this candidate.
            walk_forward_result: The walk-forward result.
            human_approved: Whether a human has approved the candidate.

        Returns:
            A DeploymentPlan describing the outcome.
        """
        steps: list[str] = []
        plan_phase = DeploymentPhase.PROPOSE

        # 1. propose
        steps.append(f"propose: candidate {candidate.candidate_sha256}")
        self._shadow_logger.log(
            bot_id=candidate.bot_id,
            candidate_sha=candidate.candidate_sha256,
            params=dict(candidate.parameters),
            outcome="candidate_received",
            phase=DeploymentPhase.PROPOSE.value,
            decision="pass",
            reason=f"candidate {candidate.candidate_sha256} submitted for review",
        )

        # 2. backtest
        plan_phase = DeploymentPhase.BACKTEST
        steps.append(
            f"backtest: passed={backtest_result.passed} profit={backtest_result.profit_total_pct}",
        )
        self._shadow_logger.log(
            bot_id=candidate.bot_id,
            candidate_sha=candidate.candidate_sha256,
            params=dict(candidate.parameters),
            outcome="backtest_evaluated",
            phase=DeploymentPhase.BACKTEST.value,
            decision="pass" if backtest_result.passed else "block",
            reason=(
                f"profit={backtest_result.profit_total_pct} "
                f"drawdown={backtest_result.max_drawdown_pct} "
                f"trades={backtest_result.total_trades}"
            ),
        )

        # 3. walk_forward
        plan_phase = DeploymentPhase.WALK_FORWARD
        steps.append(
            f"walk_forward: passed={walk_forward_result.passed} stability={walk_forward_result.stability_score}",
        )
        self._shadow_logger.log(
            bot_id=candidate.bot_id,
            candidate_sha=candidate.candidate_sha256,
            params=dict(candidate.parameters),
            outcome="walk_forward_evaluated",
            phase=DeploymentPhase.WALK_FORWARD.value,
            decision="pass" if walk_forward_result.passed else "block",
            reason=(f"stability={walk_forward_result.stability_score} reason={walk_forward_result.reason}"),
        )

        # 4. approval
        plan_phase = DeploymentPhase.APPROVAL
        decision: ApprovalDecision = self._approval_manager.evaluate(
            backtest_result=backtest_result,
            walk_forward_result=walk_forward_result,
            bot_config=bot_config,
            candidate=candidate,
        )
        steps.append(
            f"approval: status={decision.status.value} reason={decision.reason}",
        )
        self._shadow_logger.log(
            bot_id=candidate.bot_id,
            candidate_sha=candidate.candidate_sha256,
            params=dict(candidate.parameters),
            outcome=f"approval_{decision.status.value}",
            phase=DeploymentPhase.APPROVAL.value,
            decision="pass" if decision.status.value == "pending" else "block",
            reason=decision.reason,
        )

        # 5. plan / finalise
        plan_phase = DeploymentPhase.PLAN_READY
        now = self._clock().isoformat()
        shadow_start: str | None = None
        shadow_end: str | None = None

        if decision.status.value == "rejected":
            plan_status = DeploymentStatus.REJECTED.value
            plan_reason = f"rejected by approval gate: {decision.reason}"
        elif not human_approved:
            plan_status = DeploymentStatus.PENDING_APPROVAL.value
            plan_reason = "awaiting human approval"
        else:
            # human_approved=True and approval.status was "pending"
            plan_status = DeploymentStatus.READY_FOR_SHADOW.value
            plan_reason = "approved; ready for shadow mode"
            self._shadow_manager.start_shadow(
                bot_id=candidate.bot_id,
                candidate_sha=candidate.candidate_sha256,
                baseline_metrics={
                    "expected_profit_pct": backtest_result.profit_total_pct,
                    "expected_max_drawdown_pct": backtest_result.max_drawdown_pct,
                },
            )
            shadow_start = now
            shadow_end = self._clock().isoformat()
            plan_phase = DeploymentPhase.SHADOW
            steps.append("shadow: session started")

        self._shadow_logger.log(
            bot_id=candidate.bot_id,
            candidate_sha=candidate.candidate_sha256,
            params=dict(candidate.parameters),
            outcome=f"plan_{plan_status}",
            phase=plan_phase.value,
            decision="pass" if plan_status == DeploymentStatus.READY_FOR_SHADOW.value else "block",
            reason=plan_reason,
        )

        return DeploymentPlan(
            bot_id=candidate.bot_id,
            candidate_sha=candidate.candidate_sha256,
            phase=plan_phase,
            status=plan_status,
            steps=steps,
            shadow_start_utc=shadow_start,
            shadow_end_utc=shadow_end,
            reason=plan_reason,
        )
