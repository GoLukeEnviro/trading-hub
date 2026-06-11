"""Comprehensive tests for the SI v2 controller state contract.

Validates IDLE/ACTIVE invariants, schema enforcement, cross-field checks,
dependency resolution, and runner script syntax.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup: make the validator importable
# ---------------------------------------------------------------------------
_WORKTREE = Path(__file__).resolve().parents[2]  # .../si-v2-controller-state-contract
_SCRIPTS_DIR = _WORKTREE / "orchestrator" / "control" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import validate_control_plane as vcp  # noqa: E402

# ---------------------------------------------------------------------------
# Schemas (loaded once)
# ---------------------------------------------------------------------------
_SCHEMAS_DIR = _WORKTREE / "orchestrator" / "control" / "schemas"
_STATE_SCHEMA = json.loads((_SCHEMAS_DIR / "state.schema.json").read_text())
_QUEUE_SCHEMA = json.loads((_SCHEMAS_DIR / "queue.schema.json").read_text())

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_state(**overrides: object) -> dict:
    """Return a minimal valid IDLE (PAUSED) state dict."""
    state: dict = {
        "schema_version": 1,
        "project": "test-project",
        "controller_mode": "continuous_implementation",
        "controller_status": "PAUSED",
        "operation_level": "L3_REPOSITORY_ONLY",
        "runtime_policy": "FORBIDDEN",
        "merge_policy": "HUMAN_ONLY",
        "current_epic": None,
        "canonical_main_commit": "a" * 40,
        "active_work_item_id": None,
        "active_branch": None,
        "active_worktree": None,
        "active_pr": None,
        "last_completed_work_item_id": None,
        "last_run_id": None,
        "last_run_status": None,
        "consecutive_failures": 0,
        "pause_reason": "testing",
        "updated_at": "2026-06-11T12:00:00Z",
    }
    state.update(overrides)
    return state


def _base_queue(**overrides: object) -> dict:
    """Return a minimal valid IDLE queue (null epic, empty items)."""
    queue: dict = {
        "schema_version": 1,
        "epic_id": None,
        "base_commit": "a" * 40,
        "branch": None,
        "worktree": None,
        "items": [],
    }
    queue.update(overrides)
    return queue


def _active_queue_item(item_id: str = "item-1", status: str = "READY",
                       depends_on: list[str] | None = None) -> dict:
    """Return a single queue item dict."""
    return {
        "id": item_id,
        "title": f"Test item {item_id}",
        "issue_numbers": [1],
        "depends_on": depends_on or [],
        "priority": 1,
        "status": status,
        "work_package": "wp-1",
    }


def _write_control_plane(tmp_path: Path, state: dict, queue: dict) -> tuple[Path, Path]:
    """Write state.json and queue.json into tmp_path and return (config_root, state_root)."""
    # Schemas go into tmp_path/schemas/
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    (schemas_dir / "state.schema.json").write_text(json.dumps(_STATE_SCHEMA, indent=2))
    (schemas_dir / "queue.schema.json").write_text(json.dumps(_QUEUE_SCHEMA, indent=2))

    # State files
    (tmp_path / "STATE.json").write_text(json.dumps(state, indent=2))
    (tmp_path / "QUEUE.json").write_text(json.dumps(queue, indent=2))

    return tmp_path, tmp_path


def _run_validate(config_root: Path, state_root: Path) -> None:
    """Run the full validator; raises ValueError (or FileNotFoundError) on failure."""
    vcp.validate(config_root=config_root, state_root=state_root)


# ===========================================================================
# Test cases
# ===========================================================================

class TestIdleModeInvariants:
    """Tests 1, 3, 5, 7: IDLE-mode (PAUSED / COMPLETE) cross-field rules."""

    # Test 1: Valid PAUSED idle state with null epic and empty queue passes
    def test_paused_idle_state_with_null_epic_passes(self, tmp_path: Path) -> None:
        state = _base_state()  # PAUSED, current_epic=None, active_work_item_id=None
        queue = _base_queue()  # epic_id=None, items=[]
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        _run_validate(config_root, state_root)  # should not raise

    # Test 3 (variant): READY with empty queue fails
    # Moved to TestActiveModeInvariants since it's about ACTIVE mode

    # Test 5: PAUSED idle state with active_work_item_id set fails
    def test_paused_with_active_work_item_id_fails(self, tmp_path: Path) -> None:
        state = _base_state(active_work_item_id="item-1")
        queue = _base_queue()
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match="active_work_item_id"):
            _run_validate(config_root, state_root)

    # Test 7: Null queue metadata passes when controller is PAUSED
    def test_null_queue_metadata_passes_when_paused(self, tmp_path: Path) -> None:
        state = _base_state(controller_status="PAUSED")
        queue = _base_queue(epic_id=None, branch=None, worktree=None, items=[])
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        _run_validate(config_root, state_root)

    # Test 7 (variant): Null queue metadata passes when COMPLETE
    def test_null_queue_metadata_passes_when_complete(self, tmp_path: Path) -> None:
        state = _base_state(controller_status="COMPLETE")
        queue = _base_queue(epic_id=None, branch=None, worktree=None, items=[])
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        _run_validate(config_root, state_root)

    # PAUSED with current_epic set should fail
    def test_paused_with_current_epic_fails(self, tmp_path: Path) -> None:
        state = _base_state(current_epic="EPIC-123")
        queue = _base_queue()
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match="current_epic"):
            _run_validate(config_root, state_root)

    # COMPLETE with current_epic set should fail
    def test_complete_with_current_epic_fails(self, tmp_path: Path) -> None:
        state = _base_state(controller_status="COMPLETE", current_epic="EPIC-999")
        queue = _base_queue()
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match="current_epic"):
            _run_validate(config_root, state_root)


class TestActiveModeInvariants:
    """Tests 2, 3, 4: ACTIVE-mode (READY / RUNNING / IN_PROGRESS) cross-field rules."""

    # Test 2: Valid READY active state with one READY item passes
    def test_ready_active_state_with_ready_item_passes(self, tmp_path: Path) -> None:
        state = _base_state(
            controller_status="READY",
            current_epic="EPIC-100",
        )
        queue = _base_queue(
            epic_id="EPIC-100",
            branch="fix/test",
            worktree="/tmp/wt",
            items=[_active_queue_item("item-1", "READY")],
        )
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        _run_validate(config_root, state_root)

    # Test 3: READY with empty queue fails
    def test_ready_with_empty_queue_fails(self, tmp_path: Path) -> None:
        state = _base_state(
            controller_status="READY",
            current_epic="EPIC-100",
        )
        queue = _base_queue(
            epic_id="EPIC-100",
            branch="fix/test",
            worktree="/tmp/wt",
            items=[],
        )
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match="at least one queue item"):
            _run_validate(config_root, state_root)

    # Test 4: READY with null epic_id fails
    def test_ready_with_null_epic_id_fails(self, tmp_path: Path) -> None:
        state = _base_state(
            controller_status="READY",
            current_epic="EPIC-100",
        )
        queue = _base_queue(
            epic_id=None,  # <-- null
            branch="fix/test",
            worktree="/tmp/wt",
            items=[_active_queue_item("item-1", "READY")],
        )
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match=r"queue\.epic_id"):
            _run_validate(config_root, state_root)

    # Test 4 (variant): READY with null branch fails
    def test_ready_with_null_branch_fails(self, tmp_path: Path) -> None:
        state = _base_state(
            controller_status="READY",
            current_epic="EPIC-100",
        )
        queue = _base_queue(
            epic_id="EPIC-100",
            branch=None,  # <-- null
            worktree="/tmp/wt",
            items=[_active_queue_item("item-1", "READY")],
        )
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match=r"queue\.branch"):
            _run_validate(config_root, state_root)

    # Test 4 (variant): READY with null worktree fails
    def test_ready_with_null_worktree_fails(self, tmp_path: Path) -> None:
        state = _base_state(
            controller_status="READY",
            current_epic="EPIC-100",
        )
        queue = _base_queue(
            epic_id="EPIC-100",
            branch="fix/test",
            worktree=None,  # <-- null
            items=[_active_queue_item("item-1", "READY")],
        )
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match=r"queue\.worktree"):
            _run_validate(config_root, state_root)

    # READY with null current_epic fails
    def test_ready_with_null_current_epic_fails(self, tmp_path: Path) -> None:
        state = _base_state(
            controller_status="READY",
            current_epic=None,  # <-- null
        )
        queue = _base_queue(
            epic_id="EPIC-100",
            branch="fix/test",
            worktree="/tmp/wt",
            items=[_active_queue_item("item-1", "READY")],
        )
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match="current_epic"):
            _run_validate(config_root, state_root)


class TestSchemaValidation:
    """Tests 6, 12: Schema-level enforcement."""

    # Test 6: Missing schema-required state field fails
    def test_missing_required_state_field_fails(self, tmp_path: Path) -> None:
        state = _base_state()
        del state["controller_status"]  # remove a required field
        queue = _base_queue()
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match="required field missing"):
            _run_validate(config_root, state_root)

    # Test 12: Schema and validator status vocabularies remain identical
    def test_status_vocabularies_match_schema(self) -> None:
        """The VALID_CONTROLLER_STATUSES set in the validator must match the schema enum."""
        schema_state_enum = set(
            _STATE_SCHEMA["properties"]["controller_status"]["enum"]
        )
        assert schema_state_enum == vcp.VALID_CONTROLLER_STATUSES

        schema_queue_item_enum = set(
            _QUEUE_SCHEMA["properties"]["items"]["items"]["properties"]["status"]["enum"]
        )
        assert schema_queue_item_enum == vcp.VALID_ITEM_STATUSES

    # Extra (non-allowed) property on state fails
    def test_extra_state_property_fails(self, tmp_path: Path) -> None:
        state = _base_state()
        state["unexpected_field"] = "oops"
        queue = _base_queue()
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match="additional property"):
            _run_validate(config_root, state_root)

    # Invalid enum value for controller_status fails schema check
    def test_invalid_controller_status_fails(self, tmp_path: Path) -> None:
        state = _base_state(controller_status="INVALID_STATUS")
        queue = _base_queue()
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError):
            _run_validate(config_root, state_root)


class TestDependencyChecks:
    """Tests 8, 9, 10, 11: Dependency resolution and duplicate detection."""

    # Test 8: READY item whose dependency is COMPLETED passes
    def test_ready_item_with_completed_dependency_passes(self, tmp_path: Path) -> None:
        state = _base_state(
            controller_status="READY",
            current_epic="EPIC-100",
        )
        queue = _base_queue(
            epic_id="EPIC-100",
            branch="fix/test",
            worktree="/tmp/wt",
            items=[
                _active_queue_item("item-1", "COMPLETED"),
                _active_queue_item("item-2", "READY", depends_on=["item-1"]),
            ],
        )
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        _run_validate(config_root, state_root)

    # Test 9: READY item whose dependency is IN_PROGRESS fails
    def test_ready_item_with_in_progress_dependency_fails(self, tmp_path: Path) -> None:
        state = _base_state(
            controller_status="READY",
            current_epic="EPIC-100",
        )
        queue = _base_queue(
            epic_id="EPIC-100",
            branch="fix/test",
            worktree="/tmp/wt",
            items=[
                _active_queue_item("item-1", "IN_PROGRESS"),
                _active_queue_item("item-2", "READY", depends_on=["item-1"]),
            ],
        )
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match="dependencies not COMPLETED"):
            _run_validate(config_root, state_root)

    # Test 10: Unknown dependency fails
    def test_ready_item_with_unknown_dependency_fails(self, tmp_path: Path) -> None:
        state = _base_state(
            controller_status="READY",
            current_epic="EPIC-100",
        )
        queue = _base_queue(
            epic_id="EPIC-100",
            branch="fix/test",
            worktree="/tmp/wt",
            items=[
                _active_queue_item("item-1", "READY", depends_on=["nonexistent-item"]),
            ],
        )
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match="unknown dependencies"):
            _run_validate(config_root, state_root)

    # Test 11: Duplicate queue item ID fails
    def test_duplicate_queue_item_id_fails(self, tmp_path: Path) -> None:
        state = _base_state(
            controller_status="READY",
            current_epic="EPIC-100",
        )
        queue = _base_queue(
            epic_id="EPIC-100",
            branch="fix/test",
            worktree="/tmp/wt",
            items=[
                _active_queue_item("item-1", "READY"),
                _active_queue_item("item-1", "READY"),  # duplicate id
            ],
        )
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError, match="Duplicate queue item id"):
            _run_validate(config_root, state_root)


class TestRunnerScript:
    """Tests 13, 14: Runner behavior validated indirectly via cross-field invariants
    plus a bash syntax check."""

    # Test 13: Cross-field invariant ensures PAUSED state cannot have active epic.
    # The runner script's case statement skips AGENT_COMMAND for PAUSED/BLOCKED/COMPLETE.
    # We verify the validator rejects invalid PAUSED states so the runner never sees them.
    def test_paused_rejects_active_fields_runner_safety(self, tmp_path: Path) -> None:
        """PAUSED state with active fields fails validation, preventing runner invocation."""
        state = _base_state(
            controller_status="PAUSED",
            current_epic="EPIC-100",
            active_work_item_id="item-1",
        )
        queue = _base_queue()
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        with pytest.raises(ValueError):
            _run_validate(config_root, state_root)

    # Test 14: Cross-field invariant ensures READY state with valid queue passes.
    # The runner will invoke AGENT_COMMAND exactly once for READY.
    def test_ready_with_valid_queue_passes_for_runner(self, tmp_path: Path) -> None:
        """READY state with proper queue passes validation, enabling runner AGENT_COMMAND."""
        state = _base_state(
            controller_status="READY",
            current_epic="EPIC-100",
        )
        queue = _base_queue(
            epic_id="EPIC-100",
            branch="fix/test",
            worktree="/tmp/wt",
            items=[_active_queue_item("item-1", "READY")],
        )
        config_root, state_root = _write_control_plane(tmp_path, state, queue)
        _run_validate(config_root, state_root)  # runner would proceed to AGENT_COMMAND

    # Runner script bash syntax is valid (bash -n)
    def test_runner_script_has_valid_bash_syntax(self) -> None:
        """continuous_controller.sh must pass `bash -n` syntax check."""
        script_path = _WORKTREE / "orchestrator" / "control" / "continuous_controller.sh"
        result = subprocess.run(
            ["bash", "-n", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"bash -n failed for continuous_controller.sh:\n{result.stderr}"
        )


class TestCrossFieldUnitChecks:
    """Direct unit tests for _check_cross_field_invariants and _check_dependencies."""

    def test_cross_field_idle_with_epic_errors(self) -> None:
        state = {"controller_status": "PAUSED", "current_epic": "EPIC-X", "active_work_item_id": None}
        queue = {"items": []}
        errors = vcp._check_cross_field_invariants(state, queue)
        assert len(errors) == 1
        assert "current_epic" in errors[0]

    def test_cross_field_active_without_epic_errors(self) -> None:
        state = {"controller_status": "READY", "current_epic": None, "active_work_item_id": None}
        queue = {"items": [_active_queue_item()], "epic_id": "E", "branch": "b", "worktree": "w"}
        errors = vcp._check_cross_field_invariants(state, queue)
        assert len(errors) == 1
        assert "current_epic" in errors[0]

    def test_cross_field_active_empty_queue_errors(self) -> None:
        state = {"controller_status": "RUNNING", "current_epic": "EPIC-X", "active_work_item_id": None}
        queue = {"items": [], "epic_id": "E", "branch": "b", "worktree": "w"}
        errors = vcp._check_cross_field_invariants(state, queue)
        assert len(errors) == 1
        assert "queue.items is empty" in errors[0]

    def test_dependencies_unknown_dep_errors(self) -> None:
        items = [_active_queue_item("a", "READY", depends_on=["missing"])]
        errors = vcp._check_dependencies(items)
        assert len(errors) == 1
        assert "unknown dependencies" in errors[0]

    def test_dependencies_duplicate_id_errors(self) -> None:
        items = [_active_queue_item("dup", "READY"), _active_queue_item("dup", "READY")]
        errors = vcp._check_dependencies(items)
        assert any("Duplicate" in e for e in errors)
