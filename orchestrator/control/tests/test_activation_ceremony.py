"""Tests for the SI v2 scheduler activation ceremony policy (issue #26).

Validates every pre-ceremony check, approval token format, job contract
invariants, semantic diff safety, separation of concerns, rollback, and
observation evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.control.activation_ceremony import (
    MAX_CONCURRENT_JOBS,
    MAX_RETRIES,
    CeremonyVerdict,
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _valid_state(**overrides: object) -> dict:
    data: dict = {
        "controller_status": "PAUSED",
        "active_work_item_id": None,
        "active_branch": None,
        "active_worktree": None,
        "active_pr": None,
        "canonical_main_commit": "a" * 40,
        "updated_at": "20260612T000000Z",
    }
    data.update(overrides)
    return data


def _valid_queue(**overrides: object) -> dict:
    data: dict = {
        "base_commit": "a" * 40,
        "items": [],
    }
    data.update(overrides)
    return data


def _safe_job(**overrides: object) -> dict:
    data: dict = {
        "id": "test_job_analyze",
        "schedule": "0 9 * * 1",
        "command": "si_v2_analyze",
        "enabled": False,
        "dry_run_only": True,
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Pre-ceremony checks
# ---------------------------------------------------------------------------


class TestCheckControllerPaused:
    def test_paused_passes(self) -> None:
        result = check_controller_paused(_valid_state())
        assert result.passed is True

    def test_idle_passes(self) -> None:
        result = check_controller_paused(_valid_state(controller_status="IDLE"))
        assert result.passed is True

    def test_stopped_passes(self) -> None:
        result = check_controller_paused(_valid_state(controller_status="STOPPED"))
        assert result.passed is True

    def test_running_fails(self) -> None:
        result = check_controller_paused(_valid_state(controller_status="RUNNING"))
        assert result.passed is False


class TestCheckQueueEmpty:
    def test_empty_passes(self) -> None:
        result = check_queue_empty(_valid_queue())
        assert result.passed is True

    def test_non_empty_fails(self) -> None:
        result = check_queue_empty(_valid_queue(items=[{"id": "x"}]))
        assert result.passed is False


class TestCheckActiveFieldsNull:
    def test_all_null_passes(self) -> None:
        result = check_active_fields_null(_valid_state())
        assert result.passed is True

    def test_active_branch_fails(self) -> None:
        result = check_active_fields_null(_valid_state(active_branch="feature/x"))
        assert result.passed is False

    def test_active_pr_fails(self) -> None:
        result = check_active_fields_null(_valid_state(active_pr="http://pr/1"))
        assert result.passed is False

    def test_active_work_item_fails(self) -> None:
        result = check_active_fields_null(_valid_state(active_work_item_id="ITEM-1"))
        assert result.passed is False


class TestCheckBaselineReconciled:
    def test_matching_commits_passes(self) -> None:
        result = check_baseline_reconciled(_valid_state(), _valid_queue())
        assert result.passed is True

    def test_mismatched_commits_fails(self) -> None:
        queue = _valid_queue(base_commit="b" * 40)
        result = check_baseline_reconciled(_valid_state(), queue)
        assert result.passed is False


class TestCheckDependencySatisfied:
    def test_satisfied_passes(self) -> None:
        result = check_dependency_satisfied("issue_44", True, "merged")
        assert result.passed is True

    def test_unsatisfied_fails(self) -> None:
        result = check_dependency_satisfied("issue_176", False, "not yet merged")
        assert result.passed is False


class TestRunPreflight:
    def test_all_pass(self) -> None:
        checks = run_preflight(_valid_state(), _valid_queue())
        assert all(c.passed for c in checks)

    def test_running_controller_fails_preflight(self) -> None:
        checks = run_preflight(
            _valid_state(controller_status="RUNNING"),
            _valid_queue(),
        )
        assert not all(c.passed for c in checks)

    def test_non_empty_queue_fails_preflight(self) -> None:
        checks = run_preflight(
            _valid_state(),
            _valid_queue(items=[{"id": "x"}]),
        )
        assert not all(c.passed for c in checks)


# ---------------------------------------------------------------------------
# Approval token
# ---------------------------------------------------------------------------


class TestApprovalToken:
    def test_valid_token(self) -> None:
        assert validate_approval_token("APPROVE_ACTIVATE_0123456789ABCDEF0123456789ABCDEF") is True

    def test_lowercase_rejected(self) -> None:
        assert validate_approval_token("APPROVE_ACTIVATE_0123456789abcdef0123456789abcdef") is False

    def test_wrong_prefix_rejected(self) -> None:
        assert validate_approval_token("ACTIVATE_0123456789ABCDEF0123456789ABCDEF") is False

    def test_too_short_rejected(self) -> None:
        assert validate_approval_token("APPROVE_ACTIVATE_0123456789ABCDEF") is False

    def test_too_long_rejected(self) -> None:
        assert validate_approval_token("APPROVE_ACTIVATE_0123456789ABCDEF0123456789ABCDEFF") is False

    def test_non_hex_rejected(self) -> None:
        assert validate_approval_token("APPROVE_ACTIVATE_GHIJKLGH56789ABCDEF0123456789ABCDEF") is False

    def test_empty_rejected(self) -> None:
        assert validate_approval_token("") is False


# ---------------------------------------------------------------------------
# Job contract validation
# ---------------------------------------------------------------------------


class TestJobContract:
    def test_safe_job_passes(self) -> None:
        valid, errors = validate_job_contract(_safe_job())
        assert valid is True
        assert errors == []

    def test_enabled_job_fails(self) -> None:
        valid, errors = validate_job_contract(_safe_job(enabled=True))
        assert valid is False
        assert any("enabled must be False" in e for e in errors)

    def test_non_dry_run_fails(self) -> None:
        valid, errors = validate_job_contract(_safe_job(dry_run_only=False))
        assert valid is False
        assert any("dry_run_only must be True" in e for e in errors)

    def test_apply_command_fails(self) -> None:
        valid, errors = validate_job_contract(_safe_job(command="apply_weight --all"))
        assert valid is False
        assert any("apply_weight" in e for e in errors)

    def test_approve_command_fails(self) -> None:
        valid, errors = validate_job_contract(_safe_job(command="approve_proposal"))
        assert valid is False
        assert any("approve_proposal" in e for e in errors)

    def test_force_trade_command_fails(self) -> None:
        valid, errors = validate_job_contract(_safe_job(command="force_trade"))
        assert valid is False
        assert any("force_trade" in e for e in errors)

    def test_empty_schedule_fails(self) -> None:
        valid, errors = validate_job_contract(_safe_job(schedule=""))
        assert valid is False

    def test_excessive_timeout_fails(self) -> None:
        valid, errors = validate_job_contract(_safe_job(timeout=7200))
        assert valid is False

    def test_valid_timeout_passes(self) -> None:
        valid, errors = validate_job_contract(_safe_job(timeout=1800))
        assert valid is True

    def test_no_timeout_passes(self) -> None:
        valid, errors = validate_job_contract(_safe_job())
        assert valid is True


# ---------------------------------------------------------------------------
# Semantic diff validation
# ---------------------------------------------------------------------------


class TestSemanticDiff:
    def test_empty_to_disabled_safe(self) -> None:
        before = {"jobs": []}
        after = {"jobs": [_safe_job()]}
        safe, warnings = validate_semantic_diff(before, after)
        assert safe is True

    def test_new_enabled_job_unsafe(self) -> None:
        before = {"jobs": []}
        after = {"jobs": [_safe_job(enabled=True)]}
        safe, warnings = validate_semantic_diff(before, after)
        assert safe is False

    def test_too_many_enabled_unsafe(self) -> None:
        jobs = [_safe_job(id=f"job_{i}", enabled=True) for i in range(MAX_CONCURRENT_JOBS + 1)]
        before = {"jobs": []}
        after = {"jobs": jobs}
        safe, warnings = validate_semantic_diff(before, after)
        assert safe is False


# ---------------------------------------------------------------------------
# Separation of concerns
# ---------------------------------------------------------------------------


class TestSeparationOfConcerns:
    def test_generation_cannot_apply(self) -> None:
        proofs = prove_generation_cannot_apply()
        assert len(proofs) >= 3
        assert any("apply" not in p for p in proofs)

    def test_no_apply_in_safe_commands(self) -> None:
        """Safe commands must never contain apply/approve/force substrings."""
        safe_commands = [
            "si_v2_analyze",
            "si_v2_weekly_review",
            "si_v2_episode_report",
        ]
        forbidden = ("apply_weight", "approve_proposal", "force_trade")
        for cmd in safe_commands:
            for substr in forbidden:
                assert substr not in cmd, f"Command '{cmd}' contains '{substr}'"


# ---------------------------------------------------------------------------
# Rollback conditions
# ---------------------------------------------------------------------------


class TestAutoDisable:
    def test_red_verdict_triggers_disable(self) -> None:
        assert should_auto_disable(CeremonyVerdict.RED, 0) is True

    def test_green_no_failures_keeps_running(self) -> None:
        assert should_auto_disable(CeremonyVerdict.GREEN, 0) is False

    def test_yellow_keeps_running(self) -> None:
        assert should_auto_disable(CeremonyVerdict.YELLOW, 0) is False

    def test_max_retries_triggers_disable(self) -> None:
        assert should_auto_disable(CeremonyVerdict.YELLOW, MAX_RETRIES) is True

    def test_below_max_retries_keeps_running(self) -> None:
        assert should_auto_disable(CeremonyVerdict.YELLOW, MAX_RETRIES - 1) is False


# ---------------------------------------------------------------------------
# Run outcome classification
# ---------------------------------------------------------------------------


class TestRunOutcome:
    def test_success_no_warnings_is_green(self) -> None:
        assert classify_run_outcome(True) == CeremonyVerdict.GREEN

    def test_success_with_warnings_is_yellow(self) -> None:
        assert classify_run_outcome(True, warnings=["slow"]) == CeremonyVerdict.YELLOW

    def test_failure_is_red(self) -> None:
        assert classify_run_outcome(False) == CeremonyVerdict.RED

    def test_failure_with_errors_is_red(self) -> None:
        assert classify_run_outcome(False, errors=["crash"]) == CeremonyVerdict.RED


# ---------------------------------------------------------------------------
# Backup and checksum
# ---------------------------------------------------------------------------


class TestBackupAndChecksum:
    def test_checksum_matches(self, tmp_path: Path) -> None:
        p = tmp_path / "jobs.json"
        content = json.dumps({"jobs": []})
        p.write_text(content)
        import hashlib
        expected = hashlib.sha256(content.encode()).hexdigest()
        assert compute_jobs_checksum(p) == expected

    def test_backup_created(self, tmp_path: Path) -> None:
        src = tmp_path / "jobs.json"
        src.write_text('{"jobs": []}')
        backup_dir = tmp_path / "backups"
        backup = create_timestamped_backup(src, backup_dir)
        assert backup.exists()
        assert backup.read_text() == '{"jobs": []}'


# ---------------------------------------------------------------------------
# Forbidden activation paths
# ---------------------------------------------------------------------------


class TestForbiddenActivationPaths:
    def test_cannot_activate_without_paused(self) -> None:
        """Activation must fail if controller is not PAUSED."""
        checks = run_preflight(
            _valid_state(controller_status="RUNNING"),
            _valid_queue(),
        )
        assert not all(c.passed for c in checks)

    def test_cannot_activate_without_empty_queue(self) -> None:
        """Activation must fail if queue is not empty."""
        checks = run_preflight(
            _valid_state(),
            _valid_queue(items=[{"id": "active"}]),
        )
        assert not all(c.passed for c in checks)

    def test_cannot_activate_without_reconciled_baseline(self) -> None:
        """Activation must fail if baseline is not reconciled."""
        checks = run_preflight(
            _valid_state(canonical_main_commit="a" * 40),
            _valid_queue(base_commit="b" * 40),
        )
        assert not all(c.passed for c in checks)

    def test_cannot_activate_with_active_branch(self) -> None:
        """Activation must fail if active_branch is set."""
        checks = run_preflight(
            _valid_state(active_branch="feature/x"),
            _valid_queue(),
        )
        assert not all(c.passed for c in checks)

    def test_cannot_activate_without_approval_token(self) -> None:
        """Enable action requires valid approval token."""
        assert validate_approval_token("JUST_DO_IT") is False

    def test_new_job_cannot_start_enabled(self) -> None:
        """New jobs in semantic diff must start disabled."""
        before = {"jobs": []}
        after = {"jobs": [_safe_job(enabled=True)]}
        safe, _ = validate_semantic_diff(before, after)
        assert safe is False

    def test_job_with_apply_command_rejected(self) -> None:
        """Jobs containing apply/approve/force commands are rejected."""
        valid, _ = validate_job_contract(_safe_job(command="apply_weight --bot freqforge"))
        assert valid is False


# ---------------------------------------------------------------------------
# No scheduler runtime imports
# ---------------------------------------------------------------------------


class TestNoRuntimeImports:
    def test_no_runtime_imports(self) -> None:
        import orchestrator.control.activation_ceremony as mod

        src = mod.__file__ or ""
        with open(src) as f:
            content = f.read()
        for forbidden in ("docker", "freqtrade", "exchange", "cron", "systemd"):
            for line in content.splitlines():
                stripped = line.strip()
                if (
                    stripped.startswith("import ")
                    or stripped.startswith("from ")
                ) and forbidden in stripped:
                    raise AssertionError(
                        f"Forbidden import in activation_ceremony: {stripped}"
                    )
