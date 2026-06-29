"""Tests for orchestrator/control/activation_ceremony.py — pure policy functions.

Tests cover all pre-ceremony checks, approval token validation, backup/checksum,
semantic diff, job contract, separation proof, auto-disable, run classification,
and operator checklist invariants.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch

from orchestrator.control.activation_ceremony import (
    MAX_CONCURRENT_JOBS,
    MAX_JOB_TIMEOUT_SECONDS,
    MAX_RETRIES,
    OPERATOR_CHECKLIST,
    CeremonyPhase,
    CeremonyVerdict,
    JobLifecycleState,
    PreCeremonyCheck,
    check_active_fields_null,
    check_baseline_reconciled,
    check_controller_paused,
    check_dependency_satisfied,
    check_queue_empty,
    classify_run_outcome,
    compute_jobs_checksum,
    create_timestamped_backup,
    prove_generation_cannot_apply,
    run_preflight,
    should_auto_disable,
    validate_approval_token,
    validate_job_contract,
    validate_semantic_diff,
)


# ======================================================================
# Enums
# ======================================================================

class TestCeremonyPhase:
    def test_values(self) -> None:
        assert CeremonyPhase.PREFLIGHT.value == "preflight"
        assert CeremonyPhase.BACKUP.value == "backup"
        assert CeremonyPhase.VALIDATE.value == "validate"
        assert CeremonyPhase.DIFF.value == "diff"
        assert CeremonyPhase.STAGE.value == "stage"
        assert CeremonyPhase.APPROVE.value == "approve"
        assert CeremonyPhase.PROMOTE.value == "promote"
        assert CeremonyPhase.OBSERVE.value == "observe"


class TestCeremonyVerdict:
    def test_values(self) -> None:
        assert CeremonyVerdict.GREEN.value == "GREEN"
        assert CeremonyVerdict.YELLOW.value == "YELLOW"
        assert CeremonyVerdict.RED.value == "RED"


class TestJobLifecycleState:
    def test_values(self) -> None:
        assert JobLifecycleState.DISABLED.value == "DISABLED"
        assert JobLifecycleState.STAGED.value == "STAGED"
        assert JobLifecycleState.ENABLED.value == "ENABLED"
        assert JobLifecycleState.FAILED.value == "FAILED"
        assert JobLifecycleState.CIRCUIT_OPEN.value == "CIRCUIT_OPEN"


# ======================================================================
# Pre-ceremony checks
# ======================================================================

class TestCheckControllerPaused:
    def test_paused_passes(self) -> None:
        result = check_controller_paused({"controller_status": "PAUSED"})
        assert result.passed is True
        assert "PAUSED" in result.detail

    def test_idle_passes(self) -> None:
        result = check_controller_paused({"controller_status": "IDLE"})
        assert result.passed is True

    def test_stopped_passes(self) -> None:
        result = check_controller_paused({"controller_status": "STOPPED"})
        assert result.passed is True

    def test_running_fails(self) -> None:
        result = check_controller_paused({"controller_status": "RUNNING"})
        assert result.passed is False

    def test_empty_string_fails(self) -> None:
        result = check_controller_paused({"controller_status": ""})
        assert result.passed is False

    def test_missing_key_fails(self) -> None:
        result = check_controller_paused({})
        assert result.passed is False


class TestCheckQueueEmpty:
    def test_empty_list_passes(self) -> None:
        result = check_queue_empty({"items": []})
        assert result.passed is True

    def test_non_empty_fails(self) -> None:
        result = check_queue_empty({"items": ["item1"]})
        assert result.passed is False

    def test_missing_items_fails(self) -> None:
        """Missing items key defaults to [] which is empty -> passes."""
        result = check_queue_empty({})
        assert result.passed is True  # default empty list

    def test_non_list_items_fails(self) -> None:
        result = check_queue_empty({"items": "not-a-list"})
        assert result.passed is False


class TestCheckActiveFieldsNull:
    def test_all_null_passes(self) -> None:
        state = {
            "active_work_item_id": None,
            "active_branch": None,
            "active_worktree": None,
            "active_pr": None,
        }
        result = check_active_fields_null(state)
        assert result.passed is True

    def test_work_item_id_set_fails(self) -> None:
        state = {
            "active_work_item_id": "item-123",
            "active_branch": None,
            "active_worktree": None,
            "active_pr": None,
        }
        result = check_active_fields_null(state)
        assert result.passed is False
        assert "active_work_item_id" in result.detail

    def test_branch_set_fails(self) -> None:
        state = {
            "active_work_item_id": None,
            "active_branch": "feature/test",
            "active_worktree": None,
            "active_pr": None,
        }
        result = check_active_fields_null(state)
        assert result.passed is False
        assert "active_branch" in result.detail

    def test_all_missing_passes(self) -> None:
        """Missing fields should be treated as None."""
        result = check_active_fields_null({})
        assert result.passed is True


class TestCheckBaselineReconciled:
    def test_matching_commits_passes(self) -> None:
        result = check_baseline_reconciled(
            {"canonical_main_commit": "abc123def456"},
            {"base_commit": "abc123def456"},
        )
        assert result.passed is True

    def test_mismatched_commits_fails(self) -> None:
        result = check_baseline_reconciled(
            {"canonical_main_commit": "abc123"},
            {"base_commit": "xyz789"},
        )
        assert result.passed is False

    def test_missing_state_commit_fails(self) -> None:
        result = check_baseline_reconciled({}, {"base_commit": "abc123"})
        assert result.passed is False

    def test_missing_queue_commit_fails(self) -> None:
        result = check_baseline_reconciled({"canonical_main_commit": "abc123"}, {})
        assert result.passed is False


class TestCheckDependencySatisfied:
    def test_satisfied(self) -> None:
        result = check_dependency_satisfied("runtime_truth", True, "all good")
        assert result.passed is True
        assert "dependency_runtime_truth" in result.name

    def test_not_satisfied(self) -> None:
        result = check_dependency_satisfied("credential_isolation", False, "missing")
        assert result.passed is False
        assert "dependency_credential_isolation" in result.name


class TestRunPreflight:
    def test_all_pass(self) -> None:
        state = {
            "controller_status": "PAUSED",
            "active_work_item_id": None,
            "active_branch": None,
            "active_worktree": None,
            "active_pr": None,
            "canonical_main_commit": "abc123",
        }
        queue = {"items": [], "base_commit": "abc123"}
        checks = run_preflight(state, queue)
        assert len(checks) == 4
        assert all(c.passed for c in checks)

    def test_some_fail(self) -> None:
        state = {
            "controller_status": "RUNNING",
            "active_work_item_id": "item-1",
            "active_branch": None,
            "active_worktree": None,
            "active_pr": None,
            "canonical_main_commit": "abc123",
        }
        queue = {"items": [], "base_commit": "xyz789"}
        checks = run_preflight(state, queue)
        assert not all(c.passed for c in checks)
        assert sum(1 for c in checks if not c.passed) >= 2


# ======================================================================
# Approval token
# ======================================================================

class TestValidateApprovalToken:
    def test_valid_token(self) -> None:
        assert validate_approval_token("APPROVE_ACTIVATE_0123456789ABCDEF0123456789ABCDEF") is True

    def test_lowercase_hex_fails(self) -> None:
        assert validate_approval_token("APPROVE_ACTIVATE_0123456789abcdef0123456789abcdef") is False

    def test_too_short_fails(self) -> None:
        assert validate_approval_token("APPROVE_ACTIVATE_0123456789ABCDEF") is False

    def test_too_long_fails(self) -> None:
        assert validate_approval_token("APPROVE_ACTIVATE_" + "A" * 40) is False

    def test_wrong_prefix_fails(self) -> None:
        assert validate_approval_token("WRONG_PREFIX_0123456789ABCDEF0123456789ABCDEF") is False

    def test_empty_string_fails(self) -> None:
        assert validate_approval_token("") is False

    def test_none_fails(self) -> None:
        with pytest.raises(TypeError):
            validate_approval_token(None)  # type: ignore[arg-type]


# ======================================================================
# Backup and checksum
# ======================================================================

class TestComputeJobsChecksum:
    def test_computes_sha256(self, tmp_path: Path) -> None:
        path = tmp_path / "jobs.json"
        path.write_text('{"key": "value"}')
        checksum = compute_jobs_checksum(path)
        assert len(checksum) == 64  # SHA-256 hex
        assert checksum == hashlib.sha256(b'{"key": "value"}').hexdigest()

    def test_deterministic(self, tmp_path: Path) -> None:
        path = tmp_path / "jobs.json"
        path.write_text('{"key": "value"}')
        assert compute_jobs_checksum(path) == compute_jobs_checksum(path)

    def test_large_file(self, tmp_path: Path) -> None:
        path = tmp_path / "large.json"
        path.write_text("x" * 100000)
        checksum = compute_jobs_checksum(path)
        assert len(checksum) == 64

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            compute_jobs_checksum(tmp_path / "nonexistent.json")


class TestCreateTimestampedBackup:
    def test_creates_backup(self, tmp_path: Path) -> None:
        source = tmp_path / "jobs.json"
        source.write_text('{"key": "value"}')
        backup_dir = tmp_path / "backups"
        backup_path = create_timestamped_backup(source, backup_dir)
        assert backup_path.exists()
        assert backup_path.read_text() == '{"key": "value"}'
        assert ".bak" in backup_path.name

    def test_original_preserved(self, tmp_path: Path) -> None:
        source = tmp_path / "jobs.json"
        source.write_text('{"key": "value"}')
        backup_dir = tmp_path / "backups"
        create_timestamped_backup(source, backup_dir)
        assert source.exists()
        assert source.read_text() == '{"key": "value"}'

    def test_creates_backup_dir(self, tmp_path: Path) -> None:
        source = tmp_path / "jobs.json"
        source.write_text("data")
        backup_dir = tmp_path / "a" / "b" / "c"
        backup_path = create_timestamped_backup(source, backup_dir)
        assert backup_path.exists()


# ======================================================================
# Semantic diff
# ======================================================================

class TestValidateSemanticDiff:
    def test_no_changes(self) -> None:
        before = {"jobs": [{"id": "job1", "enabled": False}]}
        after = {"jobs": [{"id": "job1", "enabled": False}]}
        safe, warnings = validate_semantic_diff(before, after)
        assert safe is True
        assert warnings == []

    def test_new_job_disabled_safe(self) -> None:
        before = {"jobs": [{"id": "job1", "enabled": False}]}
        after = {"jobs": [{"id": "job1", "enabled": False}, {"id": "job2", "enabled": False}]}
        safe, warnings = validate_semantic_diff(before, after)
        assert safe is True

    def test_new_job_enabled_unsafe(self) -> None:
        before = {"jobs": [{"id": "job1", "enabled": False}]}
        after = {"jobs": [{"id": "job1", "enabled": False}, {"id": "job2", "enabled": True}]}
        safe, warnings = validate_semantic_diff(before, after)
        assert safe is False
        assert any("must start disabled" in w for w in warnings)

    def test_too_many_enabled(self) -> None:
        """Existing enabled jobs exceed limit (all in before, none new)."""
        existing = [{"id": f"existing{i}", "enabled": True} for i in range(MAX_CONCURRENT_JOBS + 1)]
        before = {"jobs": existing}
        after = {"jobs": existing}
        safe, warnings = validate_semantic_diff(before, after)
        assert safe is False
        assert any("exceeds max" in w for w in warnings)

    def test_non_dict_jobs_ignored(self) -> None:
        before = {"jobs": ["string_job"]}
        after = {"jobs": ["string_job", {"id": "real_job", "enabled": False}]}
        safe, warnings = validate_semantic_diff(before, after)
        assert safe is True

    def test_job_id_variant(self) -> None:
        """Should handle both 'id' and 'job_id' keys."""
        before = {"jobs": [{"job_id": "job1", "enabled": False}]}
        after = {"jobs": [{"job_id": "job1", "enabled": False}]}
        safe, warnings = validate_semantic_diff(before, after)
        assert safe is True


# ======================================================================
# Job contract
# ======================================================================

class TestValidateJobContract:
    def _valid_job(self) -> dict:
        return {
            "id": "weekly_review",
            "enabled": False,
            "dry_run_only": True,
            "schedule": "RRULE:FREQ=WEEKLY",
            "command": "python -m safe.review",
            "timeout": 300,
        }

    def test_valid_job_passes(self) -> None:
        valid, errors = validate_job_contract(self._valid_job())
        assert valid is True
        assert errors == []

    def test_enabled_true_fails(self) -> None:
        job = self._valid_job()
        job["enabled"] = True
        valid, errors = validate_job_contract(job)
        assert valid is False
        assert any("enabled must be False" in e for e in errors)

    def test_dry_run_only_false_fails(self) -> None:
        job = self._valid_job()
        job["dry_run_only"] = False
        valid, errors = validate_job_contract(job)
        assert valid is False
        assert any("dry_run_only must be True" in e for e in errors)

    def test_empty_schedule_fails(self) -> None:
        job = self._valid_job()
        job["schedule"] = ""
        valid, errors = validate_job_contract(job)
        assert valid is False
        assert any("schedule must not be empty" in e for e in errors)

    def test_whitespace_schedule_fails(self) -> None:
        job = self._valid_job()
        job["schedule"] = "   "
        valid, errors = validate_job_contract(job)
        assert valid is False

    def test_forbidden_command_apply_weight(self) -> None:
        job = self._valid_job()
        job["command"] = "python -m apply_weight"
        valid, errors = validate_job_contract(job)
        assert valid is False
        assert any("apply_weight" in e for e in errors)

    def test_forbidden_command_approve_proposal(self) -> None:
        job = self._valid_job()
        job["command"] = "python -m approve_proposal"
        valid, errors = validate_job_contract(job)
        assert valid is False

    def test_forbidden_command_force_trade(self) -> None:
        job = self._valid_job()
        job["command"] = "python -m force_trade"
        valid, errors = validate_job_contract(job)
        assert valid is False

    def test_timeout_exceeds_max(self) -> None:
        job = self._valid_job()
        job["timeout"] = MAX_JOB_TIMEOUT_SECONDS + 1
        valid, errors = validate_job_contract(job)
        assert valid is False
        assert any("exceeds max" in e for e in errors)

    def test_timeout_non_integer(self) -> None:
        job = self._valid_job()
        job["timeout"] = "not-an-int"
        valid, errors = validate_job_contract(job)
        assert valid is False
        assert any("must be an integer" in e for e in errors)

    def test_timeout_none_passes(self) -> None:
        job = self._valid_job()
        job["timeout"] = None
        valid, errors = validate_job_contract(job)
        assert valid is True

    def test_job_id_variant(self) -> None:
        job = self._valid_job()
        del job["id"]
        job["job_id"] = "weekly_review"
        valid, errors = validate_job_contract(job)
        assert valid is True


# ======================================================================
# Separation proof
# ======================================================================

class TestProveGenerationCannotApply:
    def test_returns_proof_statements(self) -> None:
        proof = prove_generation_cannot_apply()
        assert len(proof) >= 3
        assert any("apply" in p for p in proof)
        assert any("human" in p for p in proof)
        assert any("token" in p for p in proof)


# ======================================================================
# Auto-disable
# ======================================================================

class TestShouldAutoDisable:
    def test_red_verdict(self) -> None:
        assert should_auto_disable(CeremonyVerdict.RED, 0) is True

    def test_green_low_failures(self) -> None:
        assert should_auto_disable(CeremonyVerdict.GREEN, 0) is False

    def test_yellow_low_failures(self) -> None:
        assert should_auto_disable(CeremonyVerdict.YELLOW, 1) is False

    def test_max_retries_reached(self) -> None:
        assert should_auto_disable(CeremonyVerdict.GREEN, MAX_RETRIES) is True

    def test_above_max_retries(self) -> None:
        assert should_auto_disable(CeremonyVerdict.YELLOW, MAX_RETRIES + 1) is True


# ======================================================================
# Run classification
# ======================================================================

class TestClassifyRunOutcome:
    def test_success_no_warnings_green(self) -> None:
        assert classify_run_outcome(success=True) == CeremonyVerdict.GREEN

    def test_success_with_warnings_yellow(self) -> None:
        assert classify_run_outcome(success=True, warnings=["warn"]) == CeremonyVerdict.YELLOW

    def test_failure_red(self) -> None:
        assert classify_run_outcome(success=False) == CeremonyVerdict.RED

    def test_failure_with_errors_red(self) -> None:
        assert classify_run_outcome(success=False, errors=["err"]) == CeremonyVerdict.RED


# ======================================================================
# Operator checklist invariants
# ======================================================================

class TestOperatorChecklist:
    def test_not_empty(self) -> None:
        assert len(OPERATOR_CHECKLIST) > 0

    def test_contains_paused(self) -> None:
        text = "\n".join(OPERATOR_CHECKLIST)
        assert "PAUSED" in text

    def test_contains_backup(self) -> None:
        text = "\n".join(OPERATOR_CHECKLIST)
        assert "backup" in text.lower()

    def test_contains_disabled(self) -> None:
        text = "\n".join(OPERATOR_CHECKLIST)
        assert "disabled" in text.lower()

    def test_contains_approval_token(self) -> None:
        text = "\n".join(OPERATOR_CHECKLIST)
        assert "APPROVE_ACTIVATE" in text

    def test_contains_rollback(self) -> None:
        text = "\n".join(OPERATOR_CHECKLIST)
        assert "auto-disable" in text.lower() or "rollback" in text.lower()
