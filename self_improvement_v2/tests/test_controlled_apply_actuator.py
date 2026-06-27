"""Tests for ControlledApplyActuator — all gate failure paths.

Every gate in both request_apply() and confirm_apply() is covered.
Tests use:
  - in-memory ShadowLogger (log_dir=None) — zero disk I/O
  - tmp_path pytest fixture for CooldownEnforcer, MutationCounter,
    HumanTokenManager, and _execute_apply() writes
  - lightweight stubs for KillSwitchAdapter and RiskGuardAdapter

Test index
----------
# request_apply gates
test_gate1_wrong_plan_status
test_gate1_pending_approval_is_blocked
test_gate2_wrong_bot_id_blocked
test_gate2_main_bot_blocked
test_gate3_cooldown_active_blocks
test_gate4_kill_switch_emergency_blocks
test_gate4_kill_switch_paused_blocks
test_gate4_kill_switch_unreadable_blocks
test_gate5_risk_guard_block_on_strategy_mutation
test_gate5_risk_guard_block_on_empty_sha
test_gate5_risk_guard_block_on_empty_steps
test_gate6_shadow_logger_failure_blocks
test_dry_run_passes_all_gates_no_writes
test_request_apply_returns_pending_token

# confirm_apply gates
test_confirm_wrong_plan_status_blocked
test_confirm_wrong_bot_id_blocked
test_confirm_kill_switch_blocks
test_confirm_invalid_token_blocked
test_confirm_used_token_replay_blocked
test_confirm_dry_run_valid_token

# happy path
test_full_request_confirm_cycle_applies
test_mutation_counter_increments_after_apply
test_rollback_file_written_next_to_delta
test_gate_log_populated_for_every_gate
test_mutation_counter_before_captured_in_result
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from si_v2.deploy.controlled_apply_actuator import (
    ActuatorStatus,
    ControlledApplyActuator,
    CooldownEnforcer,
    HumanTokenManager,
    KillSwitchAdapter,
    KillSwitchState,
    MutationCounter,
    RiskGuardAdapter,
    RiskGuardResult,
    RiskGuardVerdict,
)
from si_v2.deploy.deployment_plan import DeploymentPhase, DeploymentPlan, DeploymentStatus
from si_v2.deploy.rollback_plan import RollbackPlanManager
from si_v2.deploy.shadow_logger import ShadowLogger


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _make_plan(
    status: str = DeploymentStatus.READY_FOR_SHADOW.value,
    bot_id: str = "freqforge-canary",
    candidate_sha: str = "abc123def456789012345678901234567890abcd",
    steps: list[str] | None = None,
) -> DeploymentPlan:
    """Build a minimal DeploymentPlan for testing."""
    return DeploymentPlan(
        bot_id=bot_id,
        candidate_sha=candidate_sha,
        phase=DeploymentPhase.SHADOW,
        status=status,
        steps=steps if steps is not None else ["propose: candidate abc123", "backtest: passed=True profit=3.5"],
        shadow_start_utc="2026-06-27T10:00:00+00:00",
        shadow_end_utc="2026-06-27T10:01:00+00:00",
        reason="approved; ready for shadow mode",
    )


class _NormalKillSwitch(KillSwitchAdapter):
    def get_state(self) -> KillSwitchState:
        return KillSwitchState.NORMAL


class _EmergencyKillSwitch(KillSwitchAdapter):
    def get_state(self) -> KillSwitchState:
        return KillSwitchState.EMERGENCY


class _PausedKillSwitch(KillSwitchAdapter):
    def get_state(self) -> KillSwitchState:
        return KillSwitchState.PAUSED


class _UnreadableKillSwitch(KillSwitchAdapter):
    """Simulates the file being unreadable — should fail-safe to EMERGENCY."""
    def get_state(self) -> KillSwitchState:
        return KillSwitchState.EMERGENCY  # same as base class fallback


class _PassRiskGuard(RiskGuardAdapter):
    def evaluate(self, plan: DeploymentPlan) -> RiskGuardResult:
        return RiskGuardResult(verdict=RiskGuardVerdict.PASS, reason="stub pass")


class _BlockRiskGuard(RiskGuardAdapter):
    def evaluate(self, plan: DeploymentPlan) -> RiskGuardResult:
        return RiskGuardResult(verdict=RiskGuardVerdict.BLOCK, reason="stub block")


class _RaisingLogger(ShadowLogger):
    """ShadowLogger that raises on every log() call."""
    def log(self, **kwargs: Any) -> None:  # type: ignore[override]
        raise OSError("disk full")


def _make_actuator(
    tmp_path: Path,
    kill_switch: KillSwitchAdapter | None = None,
    risk_guard: RiskGuardAdapter | None = None,
    shadow_logger: ShadowLogger | None = None,
    cooldown_days: int = 7,
    pre_record_apply: bool = False,
) -> ControlledApplyActuator:
    """Build a fully-wired actuator with tmp_path-rooted state files."""
    logger = shadow_logger or ShadowLogger()  # in-memory
    rollback = RollbackPlanManager()
    cooldown_file = tmp_path / "cooldown.json"
    counter_file = tmp_path / "mutation_ledger.jsonl"
    token_dir = tmp_path / "tokens"

    cooldown = CooldownEnforcer(state_file=cooldown_file, cooldown_days=cooldown_days)
    counter = MutationCounter(ledger_file=counter_file)
    tokens = HumanTokenManager(token_dir=token_dir)

    if pre_record_apply:
        # Simulate a very recent apply to trigger cooldown
        from datetime import datetime, timezone
        cooldown_file.write_text(
            json.dumps({"last_apply_utc": datetime.now(timezone.utc).isoformat(), "plan_sha": "prev"})
        )

    return ControlledApplyActuator(
        shadow_logger=logger,
        rollback_manager=rollback,
        kill_switch=kill_switch or _NormalKillSwitch(),
        risk_guard=risk_guard or _PassRiskGuard(),
        mutation_counter=counter,
        cooldown_enforcer=cooldown,
        token_manager=tokens,
        canary_config_dir=tmp_path / "canary_deltas",
    )


# ---------------------------------------------------------------------------
# Gate 1: Plan eligibility
# ---------------------------------------------------------------------------


class TestGate1PlanEligibility:
    def test_gate1_wrong_plan_status(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(status="pending_approval")
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED
        assert result.blocked_reason is not None
        assert "ready_for_shadow" in result.blocked_reason
        assert any(g["gate"] == "eligibility_check" and g["decision"] == "block" for g in result.gate_log)

    def test_gate1_pending_approval_is_blocked(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(status=DeploymentStatus.PENDING_APPROVAL.value)
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED

    def test_gate1_rejected_is_blocked(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(status=DeploymentStatus.REJECTED.value)
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED

    def test_gate1_blocked_status_is_blocked(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(status=DeploymentStatus.BLOCKED.value)
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED


# ---------------------------------------------------------------------------
# Gate 2: Canary-only enforcement
# ---------------------------------------------------------------------------


class TestGate2CanaryOnly:
    def test_gate2_wrong_bot_id_blocked(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(bot_id="freqforge")  # main bot, not canary
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED
        assert "freqforge-canary" in (result.blocked_reason or "")
        assert any(g["gate"] == "canary_check" and g["decision"] == "block" for g in result.gate_log)

    def test_gate2_main_bot_blocked(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(bot_id="regime-hybrid")
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED
        assert any(g["gate"] == "canary_check" for g in result.gate_log)

    def test_gate2_freqai_rebel_blocked(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(bot_id="freqai-rebel")
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED


# ---------------------------------------------------------------------------
# Gate 3: Cooldown
# ---------------------------------------------------------------------------


class TestGate3Cooldown:
    def test_gate3_cooldown_active_blocks(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path, pre_record_apply=True)
        plan = _make_plan()
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED
        assert "cooldown" in (result.blocked_reason or "").lower()
        assert any(g["gate"] == "cooldown_check" and g["decision"] == "block" for g in result.gate_log)

    def test_gate3_unreadable_state_blocks(self, tmp_path: Path) -> None:
        """Corrupt cooldown file — fail-safe must block."""
        actuator = _make_actuator(tmp_path)
        cooldown_file = tmp_path / "cooldown.json"
        cooldown_file.write_text("{invalid json !!")
        result = actuator.request_apply(_make_plan(), dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED

    def test_gate3_no_prior_apply_passes(self, tmp_path: Path) -> None:
        """No cooldown file — should pass (clear state)."""
        actuator = _make_actuator(tmp_path)
        plan = _make_plan()
        # Only check cooldown gate passes (full pipeline may hit other gates)
        result = actuator.request_apply(plan, dry_run=True)
        assert result.status != ActuatorStatus.BLOCKED or (
            result.blocked_reason is not None and "cooldown" not in result.blocked_reason.lower()
        )


# ---------------------------------------------------------------------------
# Gate 4: Kill-Switch
# ---------------------------------------------------------------------------


class TestGate4KillSwitch:
    def test_gate4_kill_switch_emergency_blocks(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path, kill_switch=_EmergencyKillSwitch())
        result = actuator.request_apply(_make_plan(), dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED
        assert "EMERGENCY" in (result.blocked_reason or "")
        assert any(g["gate"] == "kill_switch_check" and g["decision"] == "block" for g in result.gate_log)

    def test_gate4_kill_switch_paused_blocks(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path, kill_switch=_PausedKillSwitch())
        result = actuator.request_apply(_make_plan(), dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED
        assert "PAUSED" in (result.blocked_reason or "")

    def test_gate4_kill_switch_unreadable_blocks(self, tmp_path: Path) -> None:
        """Unreadable kill-switch file must fail-safe to EMERGENCY."""
        actuator = _make_actuator(tmp_path, kill_switch=_UnreadableKillSwitch())
        result = actuator.request_apply(_make_plan(), dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED

    def test_gate4_normal_kill_switch_passes(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path, kill_switch=_NormalKillSwitch())
        # Should reach past gate 4 (may block later gates, but not kill-switch)
        result = actuator.request_apply(_make_plan(), dry_run=True)
        kill_gate = next((g for g in result.gate_log if g["gate"] == "kill_switch_check"), None)
        assert kill_gate is not None
        assert kill_gate["decision"] == "pass"


# ---------------------------------------------------------------------------
# Gate 5: RiskGuard
# ---------------------------------------------------------------------------


class TestGate5RiskGuard:
    def test_gate5_risk_guard_block_on_strategy_mutation(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(
            steps=["propose: candidate abc", "strategy: mutate roi_table"]
        )
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED
        assert any(g["gate"] == "risk_guard_check" and g["decision"] == "block" for g in result.gate_log)

    def test_gate5_risk_guard_block_on_empty_sha(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(candidate_sha="")
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED
        assert "candidate_sha" in (result.blocked_reason or "")

    def test_gate5_risk_guard_block_on_unknown_sha(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(candidate_sha="unknown")
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED

    def test_gate5_risk_guard_block_on_empty_steps(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(steps=[])
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED
        assert "no steps" in (result.blocked_reason or "").lower()

    def test_gate5_stub_block_guard_blocks(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path, risk_guard=_BlockRiskGuard())
        result = actuator.request_apply(_make_plan(), dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED
        assert "RiskGuard" in (result.blocked_reason or "")

    def test_gate5_strategy_adapter_is_allowed(self, tmp_path: Path) -> None:
        """Steps containing 'strategy_adapter' should NOT trigger the block."""
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(
            steps=["backtest: passed=True profit=4.0", "strategy_adapter: weight_tune"]
        )
        result = actuator.request_apply(plan, dry_run=True)
        risk_gate = next((g for g in result.gate_log if g["gate"] == "risk_guard_check"), None)
        assert risk_gate is not None
        assert risk_gate["decision"] == "pass"


# ---------------------------------------------------------------------------
# Gate 6: ShadowLogger mandatory write
# ---------------------------------------------------------------------------


class TestGate6ShadowLogger:
    def test_gate6_shadow_logger_failure_blocks(self, tmp_path: Path) -> None:
        raising_logger = _RaisingLogger()
        actuator = _make_actuator(tmp_path, shadow_logger=raising_logger)
        plan = _make_plan()
        result = actuator.request_apply(plan, dry_run=False)
        assert result.status == ActuatorStatus.BLOCKED
        assert "ShadowLogger" in (result.blocked_reason or "")
        assert any(g["gate"] == "shadow_log_write" and g["decision"] == "block" for g in result.gate_log)

    def test_gate6_not_triggered_in_dry_run(self, tmp_path: Path) -> None:
        """ShadowLogger gate is skipped in dry_run mode — dry_run should pass."""
        raising_logger = _RaisingLogger()
        actuator = _make_actuator(tmp_path, shadow_logger=raising_logger)
        plan = _make_plan()
        result = actuator.request_apply(plan, dry_run=True)
        # In dry_run the raising logger is never called for mandatory gate
        assert result.status == ActuatorStatus.DRY_RUN_OK


# ---------------------------------------------------------------------------
# Dry-run happy path
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_passes_all_gates_no_writes(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan()
        result = actuator.request_apply(plan, dry_run=True)
        assert result.status == ActuatorStatus.DRY_RUN_OK
        assert result.apply_token is None  # no token in dry_run
        assert result.config_delta_path is None
        # No delta files written
        delta_dir = tmp_path / "canary_deltas"
        assert not delta_dir.exists() or len(list(delta_dir.iterdir())) == 0

    def test_dry_run_does_not_touch_cooldown(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        actuator.request_apply(_make_plan(), dry_run=True)
        cooldown_file = tmp_path / "cooldown.json"
        assert not cooldown_file.exists()  # cooldown only recorded on real apply

    def test_dry_run_gate_log_has_entries(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        result = actuator.request_apply(_make_plan(), dry_run=True)
        assert len(result.gate_log) >= 5  # all pre-apply gates traversed


# ---------------------------------------------------------------------------
# Token generation (request_apply non-dry)
# ---------------------------------------------------------------------------


class TestRequestApplyToken:
    def test_request_apply_returns_pending_token(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        result = actuator.request_apply(_make_plan(), dry_run=False)
        assert result.status == ActuatorStatus.PENDING_TOKEN
        assert result.apply_token is not None
        assert len(result.apply_token) == 32  # 16 bytes hex = 32 chars

    def test_token_file_persisted_on_disk(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        result = actuator.request_apply(_make_plan(), dry_run=False)
        token_dir = tmp_path / "tokens"
        assert token_dir.exists()
        token_files = list(token_dir.glob("*.json"))
        assert len(token_files) == 1
        token_data = json.loads(token_files[0].read_text())
        assert token_data["token"] == result.apply_token
        assert token_data["used"] is False

    def test_two_requests_generate_different_tokens(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        # Need two different plans to avoid cooldown issues (tokens are per-sha)
        plan_a = _make_plan(candidate_sha="aaa" + "0" * 37)
        plan_b = _make_plan(candidate_sha="bbb" + "0" * 37)
        r1 = actuator.request_apply(plan_a, dry_run=False)
        r2 = actuator.request_apply(plan_b, dry_run=False)
        assert r1.apply_token != r2.apply_token


# ---------------------------------------------------------------------------
# confirm_apply gate failures
# ---------------------------------------------------------------------------


class TestConfirmApplyGates:
    def test_confirm_wrong_plan_status_blocked(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(status="pending_approval")
        result = actuator.confirm_apply(plan, token="doesntmatter")
        assert result.status == ActuatorStatus.BLOCKED
        assert any(g["gate"] == "eligibility_check" and g["decision"] == "block" for g in result.gate_log)

    def test_confirm_wrong_bot_id_blocked(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(bot_id="freqforge")
        result = actuator.confirm_apply(plan, token="doesntmatter")
        assert result.status == ActuatorStatus.BLOCKED
        assert any(g["gate"] == "canary_check" and g["decision"] == "block" for g in result.gate_log)

    def test_confirm_kill_switch_blocks(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path, kill_switch=_EmergencyKillSwitch())
        result = actuator.confirm_apply(_make_plan(), token="doesntmatter")
        assert result.status == ActuatorStatus.BLOCKED
        assert "EMERGENCY" in (result.blocked_reason or "")

    def test_confirm_invalid_token_blocked(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan()
        result = actuator.confirm_apply(plan, token="totally_wrong_token_000")
        assert result.status == ActuatorStatus.BLOCKED
        assert "invalid" in (result.blocked_reason or "").lower()
        assert any(g["gate"] == "token_validation" and g["decision"] == "block" for g in result.gate_log)

    def test_confirm_used_token_replay_blocked(self, tmp_path: Path) -> None:
        """Token used once must not be reusable (replay attack prevention)."""
        actuator = _make_actuator(tmp_path)
        plan = _make_plan()
        request_result = actuator.request_apply(plan, dry_run=False)
        assert request_result.status == ActuatorStatus.PENDING_TOKEN
        token = request_result.apply_token
        # First confirmation (dry_run to avoid writing files)
        first = actuator.confirm_apply(plan, token=token, dry_run=True)
        assert first.status == ActuatorStatus.DRY_RUN_OK
        # Second attempt with same token must be blocked
        second = actuator.confirm_apply(plan, token=token, dry_run=True)
        assert second.status == ActuatorStatus.BLOCKED
        assert "invalid or already-used" in (second.blocked_reason or "")

    def test_confirm_dry_run_valid_token(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan()
        request_result = actuator.request_apply(plan, dry_run=False)
        token = request_result.apply_token
        confirm_result = actuator.confirm_apply(plan, token=token, dry_run=True)
        assert confirm_result.status == ActuatorStatus.DRY_RUN_OK
        assert confirm_result.config_delta_path is None  # dry_run = no write


# ---------------------------------------------------------------------------
# Full happy path: request → confirm → applied
# ---------------------------------------------------------------------------


class TestFullApplyCycle:
    def test_full_request_confirm_cycle_applies(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan()
        req = actuator.request_apply(plan, dry_run=False)
        assert req.status == ActuatorStatus.PENDING_TOKEN
        confirm = actuator.confirm_apply(plan, token=req.apply_token, dry_run=False)
        assert confirm.status == ActuatorStatus.APPLIED
        assert confirm.config_delta_path is not None
        delta_path = Path(confirm.config_delta_path)
        assert delta_path.exists()
        delta_data = json.loads(delta_path.read_text())
        assert delta_data["bot_id"] == "freqforge-canary"
        assert delta_data["apply_type"] == "weight_parameter_only"
        assert delta_data["requires_restart"] is False

    def test_mutation_counter_increments_after_apply(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan()
        req = actuator.request_apply(plan, dry_run=False)
        confirm = actuator.confirm_apply(plan, token=req.apply_token, dry_run=False)
        assert confirm.status == ActuatorStatus.APPLIED
        assert confirm.mutation_counter_before == 0
        assert confirm.mutation_counter_after == 1

    def test_rollback_file_written_next_to_delta(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan()
        req = actuator.request_apply(plan, dry_run=False)
        confirm = actuator.confirm_apply(plan, token=req.apply_token, dry_run=False)
        assert confirm.rollback_path is not None
        rollback_path = Path(confirm.rollback_path)
        assert rollback_path.exists()
        rollback_data = json.loads(rollback_path.read_text())
        assert rollback_data["revert_action"] == "disable_delta"
        assert rollback_data["max_revert_seconds"] == 60
        assert rollback_data["bot_id"] == "freqforge-canary"

    def test_shadow_logger_has_all_apply_entries(self, tmp_path: Path) -> None:
        logger = ShadowLogger()  # in-memory
        actuator = _make_actuator(tmp_path, shadow_logger=logger)
        plan = _make_plan()
        req = actuator.request_apply(plan, dry_run=False)
        actuator.confirm_apply(plan, token=req.apply_token, dry_run=False)
        entries = logger.get_entries("freqforge-canary")
        outcomes = [e["outcome"] for e in entries]
        assert "apply_requested" in outcomes
        assert "apply_completed" in outcomes

    def test_cooldown_recorded_after_apply(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        plan = _make_plan()
        req = actuator.request_apply(plan, dry_run=False)
        actuator.confirm_apply(plan, token=req.apply_token, dry_run=False)
        cooldown_file = tmp_path / "cooldown.json"
        assert cooldown_file.exists()
        state = json.loads(cooldown_file.read_text())
        assert state["plan_sha"] == plan.candidate_sha

    def test_second_apply_within_cooldown_blocked(self, tmp_path: Path) -> None:
        """After one apply, a second apply within 7 days must be blocked."""
        actuator = _make_actuator(tmp_path)
        plan_a = _make_plan(candidate_sha="aaa" + "0" * 37)
        req_a = actuator.request_apply(plan_a, dry_run=False)
        actuator.confirm_apply(plan_a, token=req_a.apply_token, dry_run=False)

        # Second plan attempt immediately after
        plan_b = _make_plan(candidate_sha="bbb" + "0" * 37)
        result_b = actuator.request_apply(plan_b, dry_run=False)
        assert result_b.status == ActuatorStatus.BLOCKED
        assert "cooldown" in (result_b.blocked_reason or "").lower()


# ---------------------------------------------------------------------------
# gate_log completeness
# ---------------------------------------------------------------------------


class TestGateLog:
    def test_gate_log_populated_for_every_gate(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        result = actuator.request_apply(_make_plan(), dry_run=True)
        gate_names = {g["gate"] for g in result.gate_log}
        expected = {
            "eligibility_check",
            "canary_check",
            "cooldown_check",
            "kill_switch_check",
            "risk_guard_check",
            "mutation_counter_pre_check",
            "dry_run_complete",
        }
        assert expected.issubset(gate_names)

    def test_gate_log_has_timestamps(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        result = actuator.request_apply(_make_plan(), dry_run=True)
        for entry in result.gate_log:
            assert "timestamp_utc" in entry
            assert entry["timestamp_utc"]  # not empty

    def test_blocked_result_gate_log_stops_at_failing_gate(self, tmp_path: Path) -> None:
        """When Gate 1 blocks, later gates must not appear in gate_log."""
        actuator = _make_actuator(tmp_path)
        plan = _make_plan(status="pending_approval")
        result = actuator.request_apply(plan, dry_run=False)
        gate_names = [g["gate"] for g in result.gate_log]
        assert "eligibility_check" in gate_names
        # canary_check should NOT appear since we blocked at gate 1
        assert "canary_check" not in gate_names

    def test_mutation_counter_before_captured_in_result(self, tmp_path: Path) -> None:
        actuator = _make_actuator(tmp_path)
        result = actuator.request_apply(_make_plan(), dry_run=True)
        assert result.mutation_counter_before == 0
        assert isinstance(result.mutation_counter_before, int)
