"""Tests for Rollback Executor Boundary — Phase 5B.

Tests cover:
1. canary rollback plan builds
2. non-canary rollback blocks
3. dry_run_not_confirmed blocks
4. invalid rollback plan blocks
5. missing l3 token blocks
6. generic approve token blocks
7. wrong candidate token blocks
8. correct candidate token passes token check
9. no safety_red and no luke_override blocks
10. safety_red plus valid token allows gate
11. luke_override plus valid token allows gate
12. execute_false never mutates and returns NOT_EXECUTED/READY
13. execute_true returns EXECUTION_NOT_ALLOWED_IN_PHASE_5B
14. audit renderer hides token secret
15. audit renderer includes command preview
16. audit renderer includes exactly one next_step
17. no subprocess import exists
18. no docker call exists
19. no runtime_executor mutating call imported
20. no controlled_apply_actuator execute call imported
21. result dataclasses serializable or to_dict exists
22. blocked reasons are explicit
23. rollback value old_value=3 preserved
24. current value=2 preserved
"""

from __future__ import annotations

import inspect
import sys

import pytest

from si_v2.apply_actuator.rollback_executor import (
    CANARY_BOT_ID,
    EXPECTED_L3_APPROVAL_PREFIX,
    _build_expected_token,
    _determine_restore_mode,
    build_rollback_execution_plan,
    check_rollback_execution_gate,
    execute_canary_rollback_boundary,
    render_rollback_execution_audit,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_rollback_plan() -> object:
    """A minimal object with rollback_rehearsal-compatible attributes."""

    class FakeRollbackPlan:
        dry_run_required = True
        rollback_command = (
            "freqtrade",
            "--config", "/freqtrade/user_data/config.json",
            "--strategy", "SampleStrategy",
        )

    return FakeRollbackPlan()


@pytest.fixture
def valid_rollback_plan_no_overlay() -> object:
    """A rollback plan whose command still contains overlay (invalid)."""

    class FakeRollbackPlan:
        dry_run_required = True
        rollback_command = (
            "freqtrade",
            "--config", "/freqtrade/user_data/config.json",
            "--config", "/freqtrade/user_data/overlay_test.json",
            "--strategy", "SampleStrategy",
        )

    return FakeRollbackPlan()


@pytest.fixture
def non_canary_rollback_plan() -> object:
    """A rollback plan for a non-canary bot."""

    class FakeRollbackPlan:
        dry_run_required = True
        rollback_command = (
            "freqtrade",
            "--config", "/freqtrade/user_data/config.json",
        )

    return FakeRollbackPlan()


@pytest.fixture
def plan_no_dry_run() -> object:
    """A rollback plan without dry_run_required."""

    class FakeRollbackPlan:
        dry_run_required = False
        rollback_command = (
            "freqtrade",
            "--config", "/freqtrade/user_data/config.json",
        )

    return FakeRollbackPlan()


@pytest.fixture
def plan_empty_command() -> object:
    """A rollback plan with an empty command."""

    class FakeRollbackPlan:
        dry_run_required = True
        rollback_command = ()

    return FakeRollbackPlan()


# ---------------------------------------------------------------------------
# Test 1: canary rollback plan builds
# ---------------------------------------------------------------------------


class TestBuildRollbackExecutionPlan:
    def test_canary_rollback_plan_builds(self, valid_rollback_plan: object) -> None:
        """Test 1: canary rollback plan builds successfully."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        assert plan.candidate_id == "max_open_trades_3_to_2"
        assert plan.target_bot == CANARY_BOT_ID
        assert plan.canary_only is True
        assert plan.dry_run_only is True
        assert plan.current_value == 2
        assert plan.rollback_value == 3
        assert len(plan.blocked_reasons) == 0
        assert len(plan.command_preview) > 0

    def test_non_canary_rollback_blocks(self) -> None:
        """Test 2: non-canary rollback blocks."""
        plan = build_rollback_execution_plan(
            rollback_plan=object(),
            candidate_id="some_other_bot",
            target_bot="freqtrade-freqforge-main",
            current_value=2,
            rollback_value=3,
        )
        assert plan.canary_only is False
        assert "not_canary" in " ".join(plan.blocked_reasons).lower()

    def test_dry_run_not_confirmed_blocks(self, plan_no_dry_run: object) -> None:
        """Test 3: dry_run_not_confirmed blocks."""
        plan = build_rollback_execution_plan(
            rollback_plan=plan_no_dry_run,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        assert plan.dry_run_only is False
        assert "dry_run_not_confirmed" in " ".join(plan.blocked_reasons).lower()

    def test_invalid_rollback_plan_blocks(self, plan_empty_command: object) -> None:
        """Test 4: invalid rollback plan (empty command) still builds but has blocked reasons."""
        plan = build_rollback_execution_plan(
            rollback_plan=plan_empty_command,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        # Empty command is not a blocked reason in the plan builder itself
        # but the restore mode will be 'blocked'
        assert plan.restore_mode == "blocked"

    def test_rollback_value_preserved(self, valid_rollback_plan: object) -> None:
        """Test 23: rollback value old_value=3 preserved."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        assert plan.rollback_value == 3

    def test_current_value_preserved(self, valid_rollback_plan: object) -> None:
        """Test 24: current value=2 preserved."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        assert plan.current_value == 2


# ---------------------------------------------------------------------------
# Test: Gate checks
# ---------------------------------------------------------------------------


class TestCheckRollbackExecutionGate:
    def test_missing_l3_token_blocks(self, valid_rollback_plan: object) -> None:
        """Test 5: missing l3 token blocks."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=True,
            luke_override=False,
            l3_approval=None,
        )
        assert gate.allowed is False
        assert "l3_token_missing" in " ".join(gate.blocked_reasons).lower()

    def test_generic_approve_token_blocks(self, valid_rollback_plan: object) -> None:
        """Test 6: generic approve token blocks."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=True,
            luke_override=False,
            l3_approval="APPROVE",
        )
        assert gate.allowed is False
        assert "l3_token_mismatch" in " ".join(gate.blocked_reasons).lower()

    def test_wrong_candidate_token_blocks(self, valid_rollback_plan: object) -> None:
        """Test 7: wrong candidate token blocks."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=True,
            luke_override=False,
            l3_approval="APPROVE_ROLLBACK_wrong_candidate_CANARY",
        )
        assert gate.allowed is False
        assert "l3_token_mismatch" in " ".join(gate.blocked_reasons).lower()

    def test_correct_candidate_token_passes(self, valid_rollback_plan: object) -> None:
        """Test 8: correct candidate token passes token check."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=True,
            luke_override=False,
            l3_approval="APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY",
        )
        assert gate.l3_approval_present is True

    def test_no_safety_red_no_luke_override_blocks(self, valid_rollback_plan: object) -> None:
        """Test 9: no safety_red and no luke_override blocks."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=False,
            luke_override=False,
            l3_approval="APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY",
        )
        assert gate.allowed is False
        assert "safety_not_red" in " ".join(gate.blocked_reasons).lower()

    def test_safety_red_plus_valid_token_allows_gate(self, valid_rollback_plan: object) -> None:
        """Test 10: safety_red plus valid token allows gate."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=True,
            luke_override=False,
            l3_approval="APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY",
        )
        assert gate.allowed is True
        assert gate.safety_red_required_or_luke_override is True

    def test_luke_override_plus_valid_token_allows_gate(self, valid_rollback_plan: object) -> None:
        """Test 11: luke_override plus valid token allows gate."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=False,
            luke_override=True,
            l3_approval="APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY",
        )
        assert gate.allowed is True
        assert gate.safety_red_required_or_luke_override is True


# ---------------------------------------------------------------------------
# Test: Executor boundary
# ---------------------------------------------------------------------------


class TestExecuteCanaryRollbackBoundary:
    def test_execute_false_returns_not_executed(self, valid_rollback_plan: object) -> None:
        """Test 12: execute_false never mutates and returns NOT_EXECUTED/READY."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=True,
            luke_override=False,
            l3_approval="APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY",
        )
        result = execute_canary_rollback_boundary(plan=plan, gate=gate, execute=False)
        assert result.status in ("READY_FOR_L3_ROLLBACK", "NOT_EXECUTED")
        assert "No runtime mutation" in result.next_step

    def test_execute_true_returns_phase_5b_blocked(self, valid_rollback_plan: object) -> None:
        """Test 13: execute_true returns EXECUTION_NOT_ALLOWED_IN_PHASE_5B."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=True,
            luke_override=False,
            l3_approval="APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY",
        )
        result = execute_canary_rollback_boundary(plan=plan, gate=gate, execute=True)
        assert result.status == "EXECUTION_NOT_ALLOWED_IN_PHASE_5B"
        assert "Phase 5C" in result.next_step

    def test_blocked_gate_returns_blocked(self, valid_rollback_plan: object) -> None:
        """Test that a blocked gate returns BLOCKED status."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=False,
            luke_override=False,
            l3_approval=None,
        )
        result = execute_canary_rollback_boundary(plan=plan, gate=gate, execute=False)
        assert result.status == "BLOCKED"


# ---------------------------------------------------------------------------
# Test: Audit renderer
# ---------------------------------------------------------------------------


class TestRenderRollbackExecutionAudit:
    def test_audit_hides_token_secret(self, valid_rollback_plan: object) -> None:
        """Test 14: audit renderer hides token secret."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=True,
            luke_override=False,
            l3_approval="APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY",
        )
        result = execute_canary_rollback_boundary(plan=plan, gate=gate, execute=False)
        audit = render_rollback_execution_audit(result)
        # The token value should NOT appear in the audit
        assert "APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY" not in audit
        # But the boolean flag should
        assert "True" in audit

    def test_audit_includes_command_preview(self, valid_rollback_plan: object) -> None:
        """Test 15: audit renderer includes command preview."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=True,
            luke_override=False,
            l3_approval="APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY",
        )
        result = execute_canary_rollback_boundary(plan=plan, gate=gate, execute=False)
        audit = render_rollback_execution_audit(result)
        assert "Command Preview" in audit
        assert "freqtrade" in audit
        assert "--config" in audit

    def test_audit_includes_exactly_one_next_step(self, valid_rollback_plan: object) -> None:
        """Test 16: audit renderer includes exactly one next_step."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=True,
            luke_override=False,
            l3_approval="APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY",
        )
        result = execute_canary_rollback_boundary(plan=plan, gate=gate, execute=False)
        audit = render_rollback_execution_audit(result)
        assert "## Next Step" in audit
        # Count occurrences of "Next Step" heading
        count = audit.count("## Next Step")
        assert count == 1, f"Expected exactly 1 'Next Step' heading, found {count}"


# ---------------------------------------------------------------------------
# Test: No dangerous imports
# ---------------------------------------------------------------------------


class TestNoDangerousImports:
    def test_no_subprocess_import(self) -> None:
        """Test 17: no subprocess import exists in rollback_executor."""
        source = inspect.getsource(sys.modules["si_v2.apply_actuator.rollback_executor"])
        assert "import subprocess" not in source
        assert "from subprocess" not in source

    def test_no_docker_call(self) -> None:
        """Test 18: no docker call exists in rollback_executor."""
        source = inspect.getsource(sys.modules["si_v2.apply_actuator.rollback_executor"])
        # Check for actual Docker command patterns, not the word in docstrings
        assert "subprocess.run" not in source
        assert "subprocess.Popen" not in source
        assert "os.system" not in source
        assert "docker compose" not in source.lower()
        assert "docker run" not in source.lower()

    def test_no_runtime_executor_mutating_call(self) -> None:
        """Test 19: no runtime_executor mutating call imported."""
        source = inspect.getsource(sys.modules["si_v2.apply_actuator.rollback_executor"])
        # The module should NOT import run_canary_restart_with_overlay
        assert "run_canary_restart_with_overlay" not in source
        assert "runtime_executor" not in source

    def test_no_controlled_apply_actuator_execute_call(self) -> None:
        """Test 20: no controlled_apply_actuator execute call imported."""
        source = inspect.getsource(sys.modules["si_v2.apply_actuator.rollback_executor"])
        assert "controlled_apply_actuator" not in source
        assert "execute_apply" not in source


# ---------------------------------------------------------------------------
# Test: Dataclass serialization
# ---------------------------------------------------------------------------


class TestDataclassSerialization:
    def test_rollback_execution_plan_to_dict(self, valid_rollback_plan: object) -> None:
        """Test 21a: RollbackExecutionPlan has to_dict()."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        d = plan.to_dict()
        assert isinstance(d, dict)
        assert d["candidate_id"] == "max_open_trades_3_to_2"
        assert d["current_value"] == 2
        assert d["rollback_value"] == 3
        assert isinstance(d["command_preview"], list)

    def test_rollback_execution_gate_to_dict(self, valid_rollback_plan: object) -> None:
        """Test 21b: RollbackExecutionGate has to_dict()."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=True,
            luke_override=False,
            l3_approval="APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY",
        )
        d = gate.to_dict()
        assert isinstance(d, dict)
        assert d["allowed"] is True
        assert d["candidate_id"] == "max_open_trades_3_to_2"

    def test_rollback_execution_result_to_dict(self, valid_rollback_plan: object) -> None:
        """Test 21c: RollbackExecutionResult has to_dict()."""
        plan = build_rollback_execution_plan(
            rollback_plan=valid_rollback_plan,
            candidate_id="max_open_trades_3_to_2",
            target_bot=CANARY_BOT_ID,
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=True,
            luke_override=False,
            l3_approval="APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY",
        )
        result = execute_canary_rollback_boundary(plan=plan, gate=gate, execute=False)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["status"] == "READY_FOR_L3_ROLLBACK"
        assert d["candidate_id"] == "max_open_trades_3_to_2"


# ---------------------------------------------------------------------------
# Test: Blocked reasons are explicit
# ---------------------------------------------------------------------------


class TestBlockedReasonsExplicit:
    def test_blocked_reasons_are_explicit(self) -> None:
        """Test 22: blocked reasons are explicit."""
        plan = build_rollback_execution_plan(
            rollback_plan=object(),
            candidate_id="unknown",
            target_bot="wrong-bot",
            current_value=2,
            rollback_value=3,
        )
        gate = check_rollback_execution_gate(
            plan=plan,
            safety_red=False,
            luke_override=False,
            l3_approval=None,
        )
        assert len(gate.blocked_reasons) > 0
        for reason in gate.blocked_reasons:
            assert isinstance(reason, str)
            assert len(reason) > 5  # not empty or trivial


# ---------------------------------------------------------------------------
# Test: Token builder
# ---------------------------------------------------------------------------


class TestTokenBuilder:
    def test_build_expected_token(self) -> None:
        """Test that the expected token follows the correct pattern."""
        token = _build_expected_token("max_open_trades_3_to_2")
        assert token == "APPROVE_ROLLBACK_max_open_trades_3_to_2_CANARY"
        assert token.startswith(EXPECTED_L3_APPROVAL_PREFIX)
        assert token.endswith("_CANARY")

    def test_build_expected_token_with_dashes(self) -> None:
        """Test that dashes are replaced with underscores."""
        token = _build_expected_token("test-candidate-123")
        assert "test-candidate-123" not in token
        assert "test_candidate_123" in token


# ---------------------------------------------------------------------------
# Test: Restore mode determination
# ---------------------------------------------------------------------------


class TestRestoreMode:
    def test_remove_overlay_from_command(self) -> None:
        """Test that a command without overlay returns remove_overlay_from_command."""

        class Plan:
            rollback_command = ("freqtrade", "--config", "/base.json")

        mode = _determine_restore_mode(Plan())
        assert mode == "remove_overlay_from_command"

    def test_blocked_when_overlay_still_present(self) -> None:
        """Test that a command with overlay returns blocked."""

        class Plan:
            rollback_command = ("freqtrade", "--config", "/base.json",
                                "--config", "/overlay_test.json")

        mode = _determine_restore_mode(Plan())
        assert mode == "blocked"

    def test_blocked_when_no_command(self) -> None:
        """Test that an object without rollback_command returns blocked."""

        class Plan:
            pass

        mode = _determine_restore_mode(Plan())
        assert mode == "blocked"

    def test_blocked_when_empty_command(self) -> None:
        """Test that an empty command returns blocked."""

        class Plan:
            rollback_command = ()

        mode = _determine_restore_mode(Plan())
        assert mode == "blocked"
