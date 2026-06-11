"""Comprehensive tests for the SI v2 controller state contract.

Validates IDLE/ACTIVE invariants, schema enforcement, cross-field checks,
dependency resolution, and runner script syntax.
"""
from __future__ import annotations

import json
import os
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

# ===========================================================================
# Runner subprocess tests
# ===========================================================================


class TestRunnerSubprocess:
    """Subprocess-level tests for continuous_controller.sh.

    Each test creates a complete fake environment (schemas, state, queue,
    controller.env, fake agent) in tmp_path and runs the real runner script.
    """

    RUNNER_SCRIPT: Path = _WORKTREE / "orchestrator" / "control" / "continuous_controller.sh"
    # We re-use the real validate_control_plane.py via --config-root.

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_fake_env(
        tmp_path: Path,
        *,
        controller_status: str = "READY",
        run_timeout: int = 10,
    ) -> tuple[Path, Path, Path]:
        """Set up a complete fake controller environment.

        Returns (config_root, state_root, agent_counter_file).
        """
        config_root = tmp_path / "config"
        state_root = tmp_path / "state"
        log_root = tmp_path / "logs"
        lock_file = tmp_path / "controller.lock"

        config_root.mkdir(exist_ok=True)
        state_root.mkdir(exist_ok=True)
        log_root.mkdir(exist_ok=True)

        # Schemas (copied from repo)
        schemas_dir = config_root / "schemas"
        schemas_dir.mkdir(exist_ok=True)
        (schemas_dir / "state.schema.json").write_text(
            (_SCHEMAS_DIR / "state.schema.json").read_text()
        )
        (schemas_dir / "queue.schema.json").write_text(
            (_SCHEMAS_DIR / "queue.schema.json").read_text()
        )

        # Validator script directory
        scripts_dir = config_root / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        (scripts_dir / "validate_control_plane.py").write_text(
            (_SCRIPTS_DIR / "validate_control_plane.py").read_text()
        )

        # MASTER_AGENT_PROMPT.xml
        (config_root / "MASTER_AGENT_PROMPT.xml").write_text("<prompt>test</prompt>\n")

        # STATE.json
        state: dict
        if controller_status in ("READY", "RUNNING"):
            state = _base_state(
                controller_status=controller_status,
                current_epic="EPIC-TEST",
            )
        else:
            state = _base_state(controller_status=controller_status)
        (state_root / "STATE.json").write_text(json.dumps(state, indent=2))

        # QUEUE.json (ACTIVE mode needs items)
        queue: dict
        if controller_status in ("READY", "RUNNING"):
            queue = _base_queue(
                epic_id="EPIC-TEST",
                branch="fix/test",
                worktree=str(tmp_path / "wt"),
                items=[_active_queue_item("item-1", "READY")],
            )
        else:
            queue = _base_queue()
        (state_root / "QUEUE.json").write_text(json.dumps(queue, indent=2))

        # Fake agent — records invocation count
        agent_counter = tmp_path / "agent_counter"
        agent_counter.write_text("0")
        fake_agent = tmp_path / "fake_agent.sh"
        fake_agent.write_text(f"""#!/usr/bin/env bash
count=$(cat "{agent_counter}")
echo "$((count + 1))" > "{agent_counter}"
echo "agent invoked (count=$((count + 1)))"
exit 0
""")
        fake_agent.chmod(0o755)

        # controller.env
        env_file = tmp_path / "controller.env"
        env_file.write_text(f"""\
REPO_ROOT={tmp_path}
CONTROL_ROOT={tmp_path}/config
SI_V2_CONFIG_ROOT={config_root}
SI_V2_STATE_ROOT={state_root}
LOG_ROOT={log_root}
LOCK_FILE={lock_file}
RUN_TIMEOUT_SECONDS={run_timeout}
AGENT_COMMAND={fake_agent}
""")

        return config_root, state_root, agent_counter

    @staticmethod
    def _read_state(state_root: Path) -> dict:
        return json.loads((state_root / "STATE.json").read_text())

    @staticmethod
    def _read_queue(state_root: Path) -> dict:
        return json.loads((state_root / "QUEUE.json").read_text())

    # ------------------------------------------------------------------
    # Invocation count matrix
    # ------------------------------------------------------------------

    def test_ready_invokes_agent_once(self, tmp_path: Path) -> None:
        """READY → AGENT_COMMAND invoked exactly once."""
        _, state_root, counter = self._write_fake_env(
            tmp_path, controller_status="READY",
        )
        result = subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        invocations = int(counter.read_text())
        assert invocations == 1, (
            f"READY should invoke agent once, got {invocations}. "
            f"stdout={result.stdout[:500]} stderr={result.stderr[:500]}"
        )

    def test_running_invokes_agent_once(self, tmp_path: Path) -> None:
        """RUNNING → AGENT_COMMAND invoked exactly once (recovery re-entry)."""
        _, state_root, counter = self._write_fake_env(
            tmp_path, controller_status="RUNNING",
        )
        result = subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        invocations = int(counter.read_text())
        assert invocations == 1, (
            f"RUNNING should invoke agent once, got {invocations}"
        )

    def test_paused_invokes_zero_times(self, tmp_path: Path) -> None:
        """PAUSED → zero agent invocations."""
        _, state_root, counter = self._write_fake_env(
            tmp_path, controller_status="PAUSED",
        )
        subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        assert counter.read_text().strip() == "0"

    def test_blocked_invokes_zero_times(self, tmp_path: Path) -> None:
        """BLOCKED → zero agent invocations."""
        _, state_root, counter = self._write_fake_env(
            tmp_path, controller_status="BLOCKED",
        )
        subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        assert counter.read_text().strip() == "0"

    def test_failed_invokes_zero_times(self, tmp_path: Path) -> None:
        """FAILED → zero agent invocations (schema-runner parity)."""
        _, state_root, counter = self._write_fake_env(
            tmp_path, controller_status="FAILED",
        )
        subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        assert counter.read_text().strip() == "0"

    def test_complete_invokes_zero_times(self, tmp_path: Path) -> None:
        """COMPLETE → zero agent invocations."""
        _, state_root, counter = self._write_fake_env(
            tmp_path, controller_status="COMPLETE",
        )
        subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        assert counter.read_text().strip() == "0"

    # ------------------------------------------------------------------
    # Mandatory STATE_ROOT
    # ------------------------------------------------------------------

    def test_missing_state_root_fails_closed(self, tmp_path: Path) -> None:
        """Missing SI_V2_STATE_ROOT → non-zero exit, zero agent invocations."""
        config_root, state_root, counter = self._write_fake_env(
            tmp_path, controller_status="READY",
        )
        # Write env WITHOUT SI_V2_STATE_ROOT
        env_file = tmp_path / "controller.env"
        env_file.write_text(f"""\
REPO_ROOT={tmp_path}
CONTROL_ROOT={tmp_path}/config
SI_V2_CONFIG_ROOT={config_root}
LOG_ROOT={tmp_path}/logs
LOCK_FILE={tmp_path}/controller.lock
RUN_TIMEOUT_SECONDS=10
AGENT_COMMAND={tmp_path}/fake_agent.sh
""")
        result = subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(env_file)},
            capture_output=True, text=True,
        )
        assert result.returncode != 0, (
            f"Missing STATE_ROOT should fail, got exit={result.returncode}"
        )
        assert counter.read_text().strip() == "0", (
            "Agent must not be invoked when STATE_ROOT is missing"
        )

    # ------------------------------------------------------------------
    # Lock contention
    # ------------------------------------------------------------------

    def test_lock_contention_invokes_zero_times(self, tmp_path: Path) -> None:
        """Second concurrent run with same lock file skips agent."""
        import fcntl

        _, _state_root, counter = self._write_fake_env(
            tmp_path, controller_status="READY",
        )
        env = {"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")}
        # Hold the lock
        lock_file = tmp_path / "controller.lock"
        lock_fd = os.open(str(lock_file), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = subprocess.run(
                ["bash", str(self.RUNNER_SCRIPT)],
                env=env, capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "Another controller run is active" in (result.stdout + result.stderr)
            assert counter.read_text().strip() == "0"
        finally:
            os.close(lock_fd)

    # ------------------------------------------------------------------
    # Fail-closed handling
    # ------------------------------------------------------------------

    def _write_failing_env(
        self, tmp_path: Path, exit_code: int, controller_status: str = "READY",
    ) -> tuple[Path, Path, Path]:
        """Set up env where the fake agent exits with *exit_code*."""
        config_root, state_root, counter = self._write_fake_env(
            tmp_path, controller_status=controller_status,
        )
        fake_agent = tmp_path / "fake_agent.sh"
        fake_agent.write_text(f"""#!/usr/bin/env bash
count=$(cat "{counter}")
echo "$((count + 1))" > "{counter}"
echo "failing agent (exit={exit_code})"
exit {exit_code}
""")
        fake_agent.chmod(0o755)
        return config_root, state_root, counter

    def test_exit_1_transitions_fail_closed(self, tmp_path: Path) -> None:
        """Agent exit 1 → STATE.json transitions to BLOCKED."""
        _, state_root, counter = self._write_failing_env(
            tmp_path, exit_code=1,
        )
        result = subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert counter.read_text().strip() == "1"
        state = self._read_state(state_root)
        assert state["controller_status"] == "BLOCKED", (
            f"Expected BLOCKED, got {state['controller_status']}"
        )
        assert state["consecutive_failures"] >= 1
        assert state["last_run_status"] == "FAILED"

    def test_exit_124_transitions_fail_closed(self, tmp_path: Path) -> None:
        """Agent timeout (exit 124) → STATE.json transitions to BLOCKED."""
        _, state_root, counter = self._write_failing_env(
            tmp_path, exit_code=124,
        )
        result = subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        # Exit 124 is propagated through timeout → the script exits 124.
        # If the fake agent exits 124 immediately without being killed by
        # timeout, timeout passes 124 through.  Either way the controller
        # must update STATE.json to BLOCKED.
        assert counter.read_text().strip() == "1"
        state = self._read_state(state_root)
        assert state["controller_status"] == "BLOCKED", (
            f"Expected BLOCKED, got {state['controller_status']}. "
            f"exit_code={result.returncode} stdout={result.stdout[:300]} "
            f"stderr={result.stderr[:300]}"
        )
        assert "timeout" in (state.get("pause_reason") or "") or result.returncode == 124

    def test_successful_exit_runs_validation(self, tmp_path: Path) -> None:
        """Successful agent exit 0 → exit 0, STATE.json unchanged by runner."""
        _, state_root, counter = self._write_fake_env(
            tmp_path, controller_status="READY",
        )
        result = subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert counter.read_text().strip() == "1"
        # Successful run: runner does NOT modify STATE.json on success
        state = self._read_state(state_root)
        assert state["controller_status"] == "READY", (
            "Successful run should not change controller_status"
        )

    def test_json_remains_valid_after_all_paths(self, tmp_path: Path) -> None:
        """STATE.json is parseable JSON after success AND failure paths."""
        # Happy path
        _, state_root, _ = self._write_fake_env(tmp_path, controller_status="READY")
        subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        state = self._read_state(state_root)
        assert isinstance(state, dict)

        # Failure path — new temp dir
        fail_tmp = tmp_path / "fail"
        fail_tmp.mkdir()
        _, fail_state_root, _ = self._write_failing_env(fail_tmp, exit_code=1)
        subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(fail_tmp / "controller.env")},
            capture_output=True, text=True,
        )
        fail_state = json.loads((fail_state_root / "STATE.json").read_text())
        assert isinstance(fail_state, dict)
        assert fail_state["controller_status"] == "BLOCKED"

    def test_consecutive_failures_increments(self, tmp_path: Path) -> None:
        """consecutive_failures increases exactly once per failure."""
        _, state_root, _ = self._write_failing_env(tmp_path, exit_code=1)
        # Set initial consecutive_failures
        state = self._read_state(state_root)
        state["consecutive_failures"] = 2
        (state_root / "STATE.json").write_text(json.dumps(state, indent=2))

        subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        state_after = self._read_state(state_root)
        assert state_after["consecutive_failures"] == 3, (
            f"Expected 3, got {state_after['consecutive_failures']}"
        )

    # ------------------------------------------------------------------
    # Lock released after failure
    # ------------------------------------------------------------------

    def test_lock_released_after_failure(self, tmp_path: Path) -> None:
        """Lock is released even when agent fails."""
        _, state_root, _ = self._write_failing_env(tmp_path, exit_code=1)
        lock_file = tmp_path / "controller.lock"
        result = subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        # Lock should be released — a second run should work (no contention)
        result2 = subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        assert "Another controller run is active" not in (
            result2.stdout + result2.stderr
        ), "Lock was not released after failure"

    # ------------------------------------------------------------------
    # Pre- and post-validation run
    # ------------------------------------------------------------------

    def test_successful_run_runs_pre_and_post_validation(self, tmp_path: Path) -> None:
        """Successful agent run invokes validator before AND after agent."""
        _, state_root, counter = self._write_fake_env(
            tmp_path, controller_status="READY",
        )
        result = subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. "
            f"stderr={result.stderr[:500]}"
        )
        # All output goes to the log file (>>log_file 2>&1)
        log_files = sorted((tmp_path / "logs").glob("controller-*.log"))
        assert log_files, "No log file created"
        log_text = log_files[0].read_text()
        assert log_text.count("Control-plane validation passed") >= 2, (
            f"Expected >=2 validation passes (pre + post) in log, "
            f"got {log_text.count('Control-plane validation passed')}. "
            f"Log excerpt: {log_text[:500]}"
        )

    def test_failed_run_runs_post_validation(self, tmp_path: Path) -> None:
        """Failed agent run STILL runs post-validation."""
        _, _, _ = self._write_failing_env(tmp_path, exit_code=1)
        result = subprocess.run(
            ["bash", str(self.RUNNER_SCRIPT)],
            env={"SI_V2_CONTROLLER_ENV": str(tmp_path / "controller.env")},
            capture_output=True, text=True,
        )
        # All output goes to the log file
        log_files = sorted((tmp_path / "logs").glob("controller-*.log"))
        assert log_files, "No log file created"
        log_text = log_files[0].read_text()
        assert log_text.count("Control-plane validation passed") >= 2, (
            f"Post-validation must run after failure. "
            f"Got {log_text.count('Control-plane validation passed')} passes. "
            f"Log excerpt: {log_text[:500]}"
        )

    # ------------------------------------------------------------------
    # IN_PROGRESS / COMPLETED are NOT valid controller statuses
    # ------------------------------------------------------------------

    def test_in_progress_controller_status_rejected(self, tmp_path: Path) -> None:
        """IN_PROGRESS is a queue-item status, not a controller status.
        The schema validator rejects it before the runner status check."""
        config_root = tmp_path / "config"
        state_root = tmp_path / "state"
        config_root.mkdir()
        state_root.mkdir()
        # Copy schemas so the validator can run
        schemas_dir = config_root / "schemas"
        schemas_dir.mkdir()
        (schemas_dir / "state.schema.json").write_text(
            (_SCHEMAS_DIR / "state.schema.json").read_text()
        )
        (schemas_dir / "queue.schema.json").write_text(
            (_SCHEMAS_DIR / "queue.schema.json").read_text()
        )
        scripts_dir = config_root / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "validate_control_plane.py").write_text(
            (_SCRIPTS_DIR / "validate_control_plane.py").read_text()
        )
        # STATE.json with IN_PROGRESS (NOT in the schema enum)
        state = _base_state(controller_status="IN_PROGRESS")
        (state_root / "STATE.json").write_text(json.dumps(state, indent=2))
        queue = _base_queue()
        (state_root / "QUEUE.json").write_text(json.dumps(queue, indent=2))
        # Run validator directly
        result = subprocess.run(
            ["python3", str(scripts_dir / "validate_control_plane.py"),
             "--config-root", str(config_root),
             "--state-root", str(state_root)],
            capture_output=True, text=True,
        )
        assert result.returncode != 0, (
            f"IN_PROGRESS controller_status should be rejected. "
            f"stderr={result.stderr[:300]}"
        )

    def test_completed_controller_status_rejected(self, tmp_path: Path) -> None:
        """COMPLETED is a queue-item status, not a controller status.
        The schema validator rejects it before the runner status check."""
        config_root = tmp_path / "config"
        state_root = tmp_path / "state"
        config_root.mkdir()
        state_root.mkdir()
        schemas_dir = config_root / "schemas"
        schemas_dir.mkdir()
        (schemas_dir / "state.schema.json").write_text(
            (_SCHEMAS_DIR / "state.schema.json").read_text()
        )
        (schemas_dir / "queue.schema.json").write_text(
            (_SCHEMAS_DIR / "queue.schema.json").read_text()
        )
        scripts_dir = config_root / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "validate_control_plane.py").write_text(
            (_SCRIPTS_DIR / "validate_control_plane.py").read_text()
        )
        state = _base_state(controller_status="COMPLETED")
        (state_root / "STATE.json").write_text(json.dumps(state, indent=2))
        queue = _base_queue()
        (state_root / "QUEUE.json").write_text(json.dumps(queue, indent=2))
        result = subprocess.run(
            ["python3", str(scripts_dir / "validate_control_plane.py"),
             "--config-root", str(config_root),
             "--state-root", str(state_root)],
            capture_output=True, text=True,
        )
        assert result.returncode != 0, (
            f"COMPLETED controller_status should be rejected. "
            f"stderr={result.stderr[:300]}"
        )
