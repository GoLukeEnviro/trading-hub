"""Tests for SI-v2 Phase 6B Autonomous Dry-Run Executor.

Test coverage:
  1. test_executor_blocks_when_policy_blocks_missing_evidence
  2. test_executor_blocks_non_canary_candidate
  3. test_executor_blocks_live_or_dry_run_false
  4. test_executor_prepares_overlay_rollback_audit_measurement_plan
  5. test_executor_requires_change_id
  6. test_executor_requires_evidence_refs
  7. test_executor_does_not_require_l3_token_in_autonomous_dry_run
  8. test_executor_runtime_execute_false_does_not_restart
  9. test_executor_execute_runtime_true_is_not_enabled_in_pr
  10. test_executor_result_is_serializable
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.pipeline.autonomous_dry_run_executor import (
    AutonomousDryRunExecutorInput,
    prepare_autonomous_dry_run_apply,
)
from si_v2.pipeline.candidate_to_apply import CandidateApplyInput


def _make_candidate(
    *,
    candidate_id: str = "test_candidate_001",
    target_bot: str = "freqtrade-freqforge-canary",
    parameter: str = "max_open_trades",
    current_value: object = 3,
    proposed_value: object = 2,
    requires_human_approval: bool = True,
    autonomy_mode: str = "DRY_RUN",
) -> CandidateApplyInput:
    return CandidateApplyInput(
        candidate_id=candidate_id,
        source="shadow_proposal",
        target_bot=target_bot,
        parameter=parameter,
        current_value=current_value,
        proposed_value=proposed_value,
        confidence=0.85,
        evidence_refs=("cycle_001",),
        requires_human_approval=requires_human_approval,
        autonomy_mode=autonomy_mode,
    )


def _default_input(
    *,
    candidate: CandidateApplyInput | None = None,
    change_id: str = "change_abc123",
    evidence_refs: tuple[str, ...] = ("cycle_001", "report_001"),
    source_cycle: str = "cycle_001",
    kill_switch_mode: str = "NORMAL",
    riskguard_status: str = "PASS",
    allowlist_compatible: bool = True,
) -> AutonomousDryRunExecutorInput:
    return AutonomousDryRunExecutorInput(
        candidate=candidate or _make_candidate(),
        pre_apply_config={"dry_run": True, "max_open_trades": 3},
        kill_switch_mode=kill_switch_mode,
        riskguard_status=riskguard_status,
        allowlist_compatible=allowlist_compatible,
        active_measurement_candidate_id=None,
        evidence_refs=evidence_refs,
        change_id=change_id,
        source_cycle=source_cycle,
    )


class TestExecutorBlocked:
    """Tests for blocking conditions."""

    def test_blocks_when_policy_blocks_missing_evidence(self) -> None:
        """Missing evidence should cause policy to block."""
        input_ = _default_input(
            kill_switch_mode=None,  # type: ignore[arg-type]
            riskguard_status=None,  # type: ignore[arg-type]
            allowlist_compatible=None,  # type: ignore[arg-type]
        )
        result = prepare_autonomous_dry_run_apply(input_)
        assert result.status == "EXECUTOR_BLOCKED", (
            f"Missing evidence should block: {result.status}"
        )
        assert len(result.blocked_reasons) > 0

    def test_blocks_non_canary_candidate(self) -> None:
        """Non-canary target should block."""
        candidate = _make_candidate(target_bot="freqtrade-freqforge")
        input_ = _default_input(candidate=candidate)
        result = prepare_autonomous_dry_run_apply(input_)
        assert result.status == "EXECUTOR_BLOCKED", (
            f"Non-canary should block: {result.status}"
        )

    def test_blocks_dry_run_false(self) -> None:
        """dry_run=false should block."""
        candidate = _make_candidate()
        input_ = AutonomousDryRunExecutorInput(
            candidate=candidate,
            pre_apply_config={"dry_run": False, "max_open_trades": 3},
            kill_switch_mode="NORMAL",
            riskguard_status="PASS",
            allowlist_compatible=True,
            active_measurement_candidate_id=None,
            evidence_refs=("cycle_001",),
            change_id="change_abc123",
            source_cycle="cycle_001",
        )
        result = prepare_autonomous_dry_run_apply(input_)
        assert result.status == "EXECUTOR_BLOCKED", (
            f"dry_run=false should block: {result.status}"
        )

    def test_requires_change_id(self) -> None:
        """Empty change_id should block."""
        input_ = _default_input(change_id="")
        result = prepare_autonomous_dry_run_apply(input_)
        assert result.status == "EXECUTOR_BLOCKED", (
            f"Empty change_id should block: {result.status}"
        )
        assert any("change_id" in r.lower() for r in result.blocked_reasons)

    def test_requires_evidence_refs(self) -> None:
        """Empty evidence_refs should block."""
        input_ = _default_input(evidence_refs=())
        result = prepare_autonomous_dry_run_apply(input_)
        assert result.status == "EXECUTOR_BLOCKED", (
            f"Empty evidence_refs should block: {result.status}"
        )
        assert any("evidence_refs" in r.lower() for r in result.blocked_reasons)


class TestExecutorPrepared:
    """Tests for successful preparation."""

    def test_prepares_overlay_rollback_audit_measurement_plan(
        self, tmp_path: Path,
    ) -> None:
        """Executor should create all artifacts."""
        state_dir = tmp_path / "state"
        overlay_dir = tmp_path / "overlays"
        plan_dir = tmp_path / "plans"
        audit_dir = tmp_path / "audit"

        input_ = _default_input()
        result = prepare_autonomous_dry_run_apply(
            input_,
            state_dir=state_dir,
            overlay_dir=overlay_dir,
            plan_dir=plan_dir,
            audit_dir=audit_dir,
        )
        assert result.status == "EXECUTOR_DRY_RUN_APPLY_PREPARED", (
            f"Should prepare artifacts: {result.status}: {result.blocked_reasons}"
        )
        # Verify overlay exists
        assert result.overlay_path, "Overlay path should be set"
        assert Path(result.overlay_path).exists(), "Overlay file should exist"
        # Verify rollback plan exists
        assert result.rollback_plan_path, "Rollback plan path should be set"
        assert Path(result.rollback_plan_path).exists(), "Rollback plan should exist"
        # Verify audit exists
        assert result.audit_path, "Audit path should be set"
        assert Path(result.audit_path).exists(), "Audit file should exist"
        # Verify measurement plan exists
        measurement_plans = list(plan_dir.glob("measurement_start_*"))
        assert len(measurement_plans) > 0, "Measurement start plan should exist"
        # Verify flags
        assert result.runtime_action_required
        assert result.measurement_window_required

    def test_does_not_require_l3_token_in_autonomous_dry_run(
        self, tmp_path: Path,
    ) -> None:
        """Autonomous dry-run should not require L3 token."""
        state_dir = tmp_path / "state"
        overlay_dir = tmp_path / "overlays"
        plan_dir = tmp_path / "plans"
        audit_dir = tmp_path / "audit"

        input_ = _default_input()
        result = prepare_autonomous_dry_run_apply(
            input_,
            state_dir=state_dir,
            overlay_dir=overlay_dir,
            plan_dir=plan_dir,
            audit_dir=audit_dir,
        )
        assert result.status == "EXECUTOR_DRY_RUN_APPLY_PREPARED", (
            f"Should not require L3 token: {result.status}: {result.blocked_reasons}"
        )

    def test_runtime_execute_false_does_not_restart(
        self, tmp_path: Path,
    ) -> None:
        """execute_runtime=False should not attempt restart."""
        state_dir = tmp_path / "state"
        overlay_dir = tmp_path / "overlays"
        plan_dir = tmp_path / "plans"
        audit_dir = tmp_path / "audit"

        input_ = _default_input()
        result = prepare_autonomous_dry_run_apply(
            input_,
            execute_runtime=False,
            state_dir=state_dir,
            overlay_dir=overlay_dir,
            plan_dir=plan_dir,
            audit_dir=audit_dir,
        )
        # Should prepare artifacts, not attempt runtime
        assert result.status == "EXECUTOR_DRY_RUN_APPLY_PREPARED", (
            f"Should prepare without restart: {result.status}"
        )
        assert result.runtime_action_required, (
            "Runtime action should be flagged as required"
        )


class TestExecutorRuntimeGate:
    """Tests for the execute_runtime gate."""

    def test_execute_runtime_true_is_not_enabled_in_pr(
        self, tmp_path: Path,
    ) -> None:
        """execute_runtime=True should return NOT_ENABLED."""
        state_dir = tmp_path / "state"
        overlay_dir = tmp_path / "overlays"
        plan_dir = tmp_path / "plans"
        audit_dir = tmp_path / "audit"

        input_ = _default_input()
        result = prepare_autonomous_dry_run_apply(
            input_,
            execute_runtime=True,
            state_dir=state_dir,
            overlay_dir=overlay_dir,
            plan_dir=plan_dir,
            audit_dir=audit_dir,
        )
        assert result.status == "EXECUTOR_RUNTIME_ACTION_NOT_ENABLED", (
            f"Runtime should not be enabled: {result.status}"
        )
        assert any("not_enabled" in r.lower() for r in result.blocked_reasons)


class TestExecutorResultShape:
    """Tests for result shape and serialization."""

    def test_result_is_serializable(self, tmp_path: Path) -> None:
        """Result should be JSON-serializable."""
        state_dir = tmp_path / "state"
        overlay_dir = tmp_path / "overlays"
        plan_dir = tmp_path / "plans"
        audit_dir = tmp_path / "audit"

        input_ = _default_input()
        result = prepare_autonomous_dry_run_apply(
            input_,
            state_dir=state_dir,
            overlay_dir=overlay_dir,
            plan_dir=plan_dir,
            audit_dir=audit_dir,
        )
        d = result.to_dict()
        # Should serialize to JSON without error
        json_str = json.dumps(d)
        assert len(json_str) > 0
        # Verify required fields
        assert d["status"] == "EXECUTOR_DRY_RUN_APPLY_PREPARED"
        assert d["change_id"] == "change_abc123"
        assert d["candidate_id"] == "test_candidate_001"
        assert d["target_bot"] == "freqtrade-freqforge-canary"
        assert d["overlay_path"]
        assert d["overlay_sha256"]
        assert d["rollback_plan_path"]
        assert d["audit_path"]
        assert d["runtime_action_required"] is True
        assert d["measurement_window_required"] is True
        assert d["blocked_reasons"] == []
        assert "next_step" in d

    def test_blocked_result_is_serializable(self) -> None:
        """Blocked result should also be JSON-serializable."""
        input_ = _default_input(change_id="")
        result = prepare_autonomous_dry_run_apply(input_)
        d = result.to_dict()
        json_str = json.dumps(d)
        assert len(json_str) > 0
        assert d["status"] == "EXECUTOR_BLOCKED"
        assert len(d["blocked_reasons"]) > 0
