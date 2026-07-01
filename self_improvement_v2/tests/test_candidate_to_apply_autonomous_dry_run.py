"""Tests for SI-v2 Candidate-to-Apply Pipeline with autonomous dry-run support.

Test coverage:
  1. Qualified canary candidate → READY_FOR_AUTONOMOUS_DRY_RUN_APPLY
  2. Old human approval missing does not block dry-run policy path
  3. Non-canary mutating candidate blocked
  4. Active measurement deferred
  5. execute=True does not mutate and returns explicit Phase 6B status
"""

from __future__ import annotations

from si_v2.pipeline.candidate_to_apply import (
    CandidateApplyInput,
    candidate_to_apply_pipeline,
)


def _make_candidate(
    *,
    candidate_id: str = "test_candidate_001",
    source: str = "shadow_proposal",
    target_bot: str = "freqtrade-freqforge-canary",
    parameter: str = "max_open_trades",
    current_value: object = 3,
    proposed_value: object = 2,
    confidence: float | None = 0.85,
    evidence_refs: tuple[str, ...] = ("cycle_001",),
    requires_human_approval: bool = True,
    autonomy_mode: str = "DRY_RUN",
) -> CandidateApplyInput:
    return CandidateApplyInput(
        candidate_id=candidate_id,
        source=source,
        target_bot=target_bot,
        parameter=parameter,
        current_value=current_value,
        proposed_value=proposed_value,
        confidence=confidence,
        evidence_refs=evidence_refs,
        requires_human_approval=requires_human_approval,
        autonomy_mode=autonomy_mode,
    )


def _default_config() -> dict[str, object]:
    return {
        "dry_run": True,
        "max_open_trades": 3,
        "cooldown_candles": 3,
    }


class TestCandidatePipelineAutonomousDryRun:
    """Tests for the autonomous dry-run policy path."""

    def test_qualified_canary_candidate(self) -> None:
        """A qualified canary candidate should reach READY_FOR_AUTONOMOUS_DRY_RUN_APPLY."""
        candidate = _make_candidate()
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in (
            "READY_FOR_AUTONOMOUS_DRY_RUN_APPLY",
            "AUTO_DRY_RUN_APPROVED",
        ), f"Got {result.decision.status}: {result.decision.blocked_reasons}"

    def test_human_approval_not_required_in_dry_run_mode(self) -> None:
        """In DRY_RUN mode, requires_human_approval=False should not block."""
        candidate = _make_candidate(
            requires_human_approval=False,
            autonomy_mode="DRY_RUN",
        )
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            active_measurement_candidate_id=None,
        )
        # Should not be blocked by human approval
        assert result.decision.status not in ("BLOCKED", "DEFERRED"), (
            f"Human approval gate should not block in DRY_RUN mode: "
            f"{result.decision.status}: {result.decision.blocked_reasons}"
        )

    def test_non_canary_mutating_candidate_blocked(self) -> None:
        """Non-canary target should be blocked."""
        candidate = _make_candidate(
            target_bot="freqtrade-regime-hybrid",
        )
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in (
            "BLOCKED", "AUTO_DRY_RUN_BLOCKED",
        ), f"Non-canary should be blocked: {result.decision.status}"

    def test_active_measurement_deferred(self) -> None:
        """Active measurement window should defer."""
        candidate = _make_candidate(
            candidate_id="new_candidate_002",
        )
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            active_measurement_candidate_id="existing_measurement_001",
        )
        assert result.decision.status in (
            "DEFERRED", "AUTO_DRY_RUN_DEFERRED",
        ), f"Active measurement should defer: {result.decision.status}"

    def test_execute_true_returns_not_implemented(self) -> None:
        """execute=True should return NOT_IMPLEMENTED_EXECUTION."""
        candidate = _make_candidate()
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            execute=True,
            active_measurement_candidate_id=None,
        )
        assert result.decision.status == "NOT_IMPLEMENTED_EXECUTION"
        assert "phase_6a" in result.decision.next_step.lower() or "phase 6b" in result.decision.next_step.lower()

    def test_execute_true_no_mutation(self) -> None:
        """execute=True should not mutate anything."""
        candidate = _make_candidate()
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            execute=True,
            active_measurement_candidate_id=None,
        )
        assert result.decision.status == "NOT_IMPLEMENTED_EXECUTION"
        assert result.readiness_report is None
        assert result.restart_plan_required
        assert result.measurement_plan_required
        assert result.rollback_plan_required


class TestCandidatePipelineLegacyMode:
    """Tests for legacy OFF mode (human-gated)."""

    def test_requires_human_approval_in_off_mode(self) -> None:
        """In OFF mode, requires_human_approval=False should defer."""
        candidate = _make_candidate(
            requires_human_approval=False,
            autonomy_mode="OFF",
        )
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            active_measurement_candidate_id=None,
        )
        assert result.decision.status == "DEFERRED", (
            f"Human approval should be required in OFF mode: {result.decision.status}"
        )

    def test_off_mode_with_human_approval(self) -> None:
        """In OFF mode with requires_human_approval=True, should reach READY_FOR_HUMAN_APPROVAL."""
        candidate = _make_candidate(
            requires_human_approval=True,
            autonomy_mode="OFF",
        )
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in (
            "READY_FOR_HUMAN_APPROVAL", "READY_FOR_CANARY_APPLY",
        ), f"Got {result.decision.status}: {result.decision.blocked_reasons}"


class TestCandidatePipelineBlocked:
    """Various blocking conditions."""

    def test_unknown_bot_blocked(self) -> None:
        """Unknown bot should be blocked."""
        candidate = _make_candidate(target_bot="unknown-bot")
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in (
            "BLOCKED", "AUTO_DRY_RUN_BLOCKED",
        ), f"Unknown bot should be blocked: {result.decision.status}"

    def test_forbidden_parameter_blocked(self) -> None:
        """Forbidden parameter should be blocked."""
        candidate = _make_candidate(parameter="exchange", proposed_value="binance")
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in (
            "BLOCKED", "AUTO_DRY_RUN_BLOCKED",
        ), f"Forbidden parameter should be blocked: {result.decision.status}"

    def test_unsafe_parameter_blocked(self) -> None:
        """Unsafe parameter should be blocked."""
        candidate = _make_candidate(parameter="unknown_param", proposed_value=42)
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in (
            "BLOCKED", "AUTO_DRY_RUN_BLOCKED",
        ), f"Unsafe parameter should be blocked: {result.decision.status}"

    def test_dry_run_false_blocked(self) -> None:
        """dry_run=false should be blocked."""
        candidate = _make_candidate()
        config = _default_config()
        config["dry_run"] = False
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=config,
            active_measurement_candidate_id=None,
        )
        assert result.decision.status in (
            "BLOCKED", "AUTO_DRY_RUN_BLOCKED",
        ), f"dry_run=false should be blocked: {result.decision.status}"


class TestCandidatePipelineResultShape:
    """Verify the result shape and to_dict()."""

    def test_result_to_dict(self) -> None:
        candidate = _make_candidate()
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            active_measurement_candidate_id=None,
        )
        d = result.to_dict()
        assert "decision" in d
        assert "readiness_report" in d
        assert "restart_plan_required" in d
        assert "measurement_plan_required" in d
        assert "rollback_plan_required" in d

    def test_decision_to_dict(self) -> None:
        candidate = _make_candidate()
        result = candidate_to_apply_pipeline(
            candidate=candidate,
            pre_apply_config=_default_config(),
            active_measurement_candidate_id=None,
        )
        d = result.decision.to_dict()
        assert d["status"] in (
            "READY_FOR_AUTONOMOUS_DRY_RUN_APPLY",
            "AUTO_DRY_RUN_APPROVED",
            "READY_FOR_CANARY_APPLY",
            "READY_FOR_HUMAN_APPROVAL",
        )
        assert d["candidate_id"] == "test_candidate_001"
        assert d["target_bot"] == "freqtrade-freqforge-canary"
        assert isinstance(d["blocked_reasons"], list)
        assert isinstance(d["next_step"], str)
