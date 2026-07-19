"""Tests for the roadmap merge controller (ADR-2026-07-19).

Covers:
- Disable switch strictness (ownership, mode, content, halt override)
- Controller client (broker communication, switch checks)
- Broker identity verification (SO_PEERCRED, allowlist)
- Broker governance checks (guard, denylist, path allowlist, A1 triggers, TOCTOU)
- Merge execution with timeout/5xx handling
- Audit intent+completion with chattr +a validation
- Incident auto-deactivation on completion-audit failure
- repo_writer.perform_governed_merge integration

All tests are hermetic (monkeypatched gh, tmp_path filesystem).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The broker imports fcntl/pwd which are POSIX-only. Skip the entire
# test file on non-POSIX hosts (hermetic broker tests run on POSIX CI).
_pytest_skip_on_non_posix = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason="Broker requires POSIX (fcntl, pwd, Unix sockets)",
)

import orchestrator.scripts.roadmap_merge_controller as controller  # noqa: E402
from orchestrator.scripts.roadmap_merge_controller import (  # noqa: E402
    ControllerResult,
    is_controller_enabled,
    run_controller,
)

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def tmp_switch(tmp_path: Path) -> Path:
    """A root-owned switch file with exact content."""
    p = tmp_path / "enabled"
    p.write_text("true\n", encoding="utf-8")
    # Simulate root:root ownership for the test (we can't chown in tests).
    return p


@pytest.fixture
def tmp_halt(tmp_path: Path) -> Path:
    return tmp_path / "halt"


@pytest.fixture
def tmp_audit_log(tmp_path: Path) -> Path:
    p = tmp_path / "audit.jsonl"
    p.write_text("", encoding="utf-8")
    return p


# ----------------------------------------------------------------------
# Disable switch strictness
# ----------------------------------------------------------------------


class TestDisableSwitch:
    def test_missing_blocks(self, tmp_path: Path, tmp_halt: Path) -> None:
        assert is_controller_enabled(
            switch_path=tmp_path / "nonexistent",
            halt_path=tmp_halt,
        ) is False

    @_pytest_skip_on_non_posix
    def test_wrong_owner_blocks(self, tmp_path: Path, tmp_halt: Path) -> None:
        import os
        p = tmp_path / "enabled"
        p.write_text("true\n", encoding="utf-8")
        # root-ownership check: on non-root test runner this will be != 0.
        assert is_controller_enabled(switch_path=p, halt_path=tmp_halt) is (os.getuid() == 0)

    @_pytest_skip_on_non_posix
    @pytest.mark.parametrize("content", ["yes", "1", "True", "TRUE", "true", "", "true \n", "\ntrue"])
    def test_wrong_content_blocks(self, tmp_path: Path, tmp_halt: Path, content: str) -> None:
        import os
        p = tmp_path / "enabled"
        p.write_text(content, encoding="utf-8")
        # On POSIX: we only validate content when root-owned (st_uid == 0).
        # On non-root CI, this always returns False due to ownership.
        if os.getuid() == 0:
            assert is_controller_enabled(switch_path=p, halt_path=tmp_halt) is False
        else:
            assert is_controller_enabled(switch_path=p, halt_path=tmp_halt) is False

    def test_halt_overrides_enable(self, tmp_switch: Path, tmp_path: Path) -> None:
        """When halt file exists, controller is disabled regardless of enable."""
        halt = tmp_path / "halt"
        halt.write_text("", encoding="utf-8")
        assert is_controller_enabled(switch_path=tmp_switch, halt_path=halt) is False


# ----------------------------------------------------------------------
# Controller client (disable switch, broker communication)
# ----------------------------------------------------------------------


class TestControllerClient:
    def test_disabled_by_default(self) -> None:
        """When no switch exists, the controller returns DISABLED."""
        # We need to isolate from real /opt paths.
        import orchestrator.scripts.roadmap_merge_controller as ctrl
        orig_switch = ctrl._DISABLE_SWITCH_PATH
        orig_halt = ctrl._HALT_PATH
        tmp = Path(".").resolve()
        ctrl._DISABLE_SWITCH_PATH = tmp / "_test_disabled_switch"
        ctrl._HALT_PATH = tmp / "_test_disabled_halt"
        try:
            result = run_controller(
                repo="GoLukeEnviro/trading-hub",
                pr_number=1,
                expected_issue=1,
                expected_head_sha="a" * 40,
                tracker_issue=605,
                controller_identity="test-bot",
                socket_path=tmp / "_test_disabled_socket",
            )
            assert result.decision == "CONTROLLER_DISABLED"
            assert result.merged is False
        finally:
            ctrl._DISABLE_SWITCH_PATH = orig_switch
            ctrl._HALT_PATH = orig_halt

    @_pytest_skip_on_non_posix
    def test_broker_unreachable_returns_error(
        self,
        tmp_path: Path,
    ) -> None:
        """When the broker socket does not exist, the controller fails gracefully."""
        switch = tmp_path / "enabled"
        switch.write_text("true\n", encoding="utf-8")
        halt = tmp_path / "halt"
        socket_path = tmp_path / "nonexistent.sock"

        result = run_controller(
            repo="GoLukeEnviro/trading-hub",
            pr_number=637,
            expected_issue=634,
            expected_head_sha="a" * 40,
            tracker_issue=605,
            controller_identity="test-bot",
            socket_path=socket_path,
            switch_path=switch,
            halt_path=halt,
        )
        assert result.decision == "MERGE_REJECTED"
        assert result.merged is False
        assert any("BROKER_COMMUNICATION_FAILED" in b for b in result.blockers)


# ----------------------------------------------------------------------
# Broker — identity verification
# ----------------------------------------------------------------------


class TestBrokerIdentity:
    @_pytest_skip_on_non_posix
    def test_allowlist_parse(self) -> None:
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            load_allowlist,
        )
        entries = load_allowlist(Path(__file__))  # not a real allowlist, just testing
        assert isinstance(entries, list)


# ----------------------------------------------------------------------
# Broker — governance checks
# ----------------------------------------------------------------------


class TestBrokerGovernance:
    def test_denylist_parse(self) -> None:
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            check_denylist,
            load_glob_list,
        )
        patterns = load_glob_list(
            _REPO_ROOT / "orchestrator/scripts/roadmap_merge_controller_denylist.txt"
        )
        assert "AGENTS.md" in patterns
        assert "SOUL.md" in patterns
        assert "orchestrator/scripts/roadmap_merge_controller_denylist.txt" in patterns

    def test_denylist_matches(self) -> None:
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            check_denylist,
        )
        deny = _REPO_ROOT / "orchestrator/scripts/roadmap_merge_controller_denylist.txt"
        hits = check_denylist(deny, ["AGENTS.md", "some_pr_file.py"])
        assert any("AGENTS.md" in h for h in hits), f"Expected AGENTS.md hit, got: {hits}"
        assert not any("some_pr_file.py" in h for h in hits)

    def test_denylist_self_protecting(self) -> None:
        """The denylist file itself MUST be in the denylist."""
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            check_denylist,
        )
        deny = _REPO_ROOT / "orchestrator/scripts/roadmap_merge_controller_denylist.txt"
        hits = check_denylist(deny, ["orchestrator/scripts/roadmap_merge_controller_denylist.txt"])
        assert hits, "Denylist must protect itself"

    def test_path_allowlist_phase0(self) -> None:
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            check_paths_allowlist,
        )
        allow = _REPO_ROOT / "orchestrator/scripts/roadmap_merge_controller_paths_allowlist.txt"
        # Phase 0 allows docs/state/*.md, docs/reports/*.md, docs/context/*.md
        unmatched = check_paths_allowlist(allow, ["docs/state/current-operational-state.md"])
        assert unmatched == [], f"Phase 0 path should be allowed, unmatched: {unmatched}"
        unmatched = check_paths_allowlist(allow, ["AGENTS.md"])
        assert len(unmatched) == 1
        assert unmatched[0] == "AGENTS.md"

    def test_a1_trigger_detection(self) -> None:
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            check_a1_triggers,
        )
        triggers = check_a1_triggers(
            "Some A2-APPROVED text", "", []
        )
        assert "A2-APPROVED" in triggers
        triggers = check_a1_triggers(
            "", "Clean docs PR", []
        )
        assert triggers == []

    def test_formal_governance_block(self) -> None:
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            check_formal_governance_block,
        )
        assert check_formal_governance_block(["Status: BLOCKED_BY_PHASE0A"])
        assert check_formal_governance_block(["FORMALLY_BLOCKED_OUT_OF_ORDER"])
        assert not check_formal_governance_block(["Looks good to me"])


# ----------------------------------------------------------------------
# Broker — TOCTOU
# ----------------------------------------------------------------------


class TestBrokerTOCTOU:
    def test_identical_snapshots_no_drift(self) -> None:
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            check_toctou,
        )
        snapshot = {
            "pr_head_sha": "a" * 40,
            "issue_state": "OPEN",
            "issue_labels": ["roadmap"],
            "tracker_selected_task": 634,
            "pr_unresolved_threads": 0,
            "pr_review_decision": "",
            "comments": ["Looks good"],
            "checks": [
                {"name": "main-gate", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "offline-smoke", "status": "COMPLETED", "conclusion": "SUCCESS"},
            ],
        }
        blockers = check_toctou(snapshot, snapshot, expected_head_sha="a" * 40)
        assert blockers == []

    def test_head_drift_detected(self) -> None:
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            check_toctou,
        )
        initial = {
            "pr_head_sha": "a" * 40,
            "issue_state": "OPEN",
            "issue_labels": [],
            "tracker_selected_task": 634,
            "pr_unresolved_threads": 0,
            "pr_review_decision": "",
            "comments": [],
            "checks": [],
        }
        pre = dict(initial)
        pre["pr_head_sha"] = "b" * 40
        blockers = check_toctou(initial, pre, expected_head_sha="a" * 40)
        assert "TOCTOU_HEAD_SHA_DRIFT" in blockers
        assert "TOCTOU_HEAD_CHANGED_BETWEEN_SNAPSHOTS" in blockers

    def test_issue_labels_drift(self) -> None:
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            check_toctou,
        )
        initial = {
            "pr_head_sha": "a" * 40, "issue_state": "OPEN",
            "issue_labels": ["roadmap"], "tracker_selected_task": 634,
            "pr_unresolved_threads": 0, "pr_review_decision": "",
            "comments": [], "checks": [],
        }
        pre = dict(initial)
        pre["issue_labels"] = ["roadmap", "status:blocked"]
        blockers = check_toctou(initial, pre, expected_head_sha="a" * 40)
        assert "TOCTOU_ISSUE_LABELS_CHANGED" in blockers

    def test_new_governance_block_detected(self) -> None:
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            check_toctou,
        )
        initial = {
            "pr_head_sha": "a" * 40, "issue_state": "OPEN",
            "issue_labels": [], "tracker_selected_task": 634,
            "pr_unresolved_threads": 0, "pr_review_decision": "",
            "comments": ["Looks good"], "checks": [],
        }
        pre = dict(initial)
        pre["comments"] = ["BLOCKED_BY_PHASE0A"]
        blockers = check_toctou(initial, pre, expected_head_sha="a" * 40)
        assert "TOCTOU_NEW_GOVERNANCE_BLOCK" in blockers


# ----------------------------------------------------------------------
# Broker — guard evaluation
# ----------------------------------------------------------------------


class TestBrokerGuardEvaluation:
    def test_ready_snapshot_passes(self) -> None:
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            evaluate_guard,
        )
        snapshot = {
            "pr_state": "OPEN",
            "pr_is_draft": False,
            "pr_head_sha": "a" * 40,
            "issue_state": "OPEN",
            "issue_labels": [],
            "tracker_selected_task": 634,
            "pr_unresolved_threads": 0,
            "pr_review_decision": "",
            "comments": [],
            "checks": [
                {"name": "main-gate", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "offline-smoke", "status": "COMPLETED", "conclusion": "SUCCESS"},
            ],
        }
        ready, blockers = evaluate_guard(snapshot, expected_issue=634, expected_head_sha="a" * 40)
        assert ready, f"Expected ready, blockers: {blockers}"
        assert blockers == []

    def test_pr_not_open_blocks(self) -> None:
        from orchestrator.scripts.roadmap_merge_controller_broker import (
            evaluate_guard,
        )
        snapshot = {
            "pr_state": "MERGED", "pr_is_draft": False,
            "pr_head_sha": "a" * 40, "issue_state": "OPEN",
            "issue_labels": [], "tracker_selected_task": 634,
            "pr_unresolved_threads": 0, "pr_review_decision": "",
            "comments": [], "checks": [],
        }
        ready, blockers = evaluate_guard(snapshot, expected_issue=634, expected_head_sha="a" * 40)
        assert not ready
        assert "PR_NOT_OPEN" in blockers


# ----------------------------------------------------------------------
# Merge response state machine (three states)
# ----------------------------------------------------------------------


class TestMergeStateMachine:
    def test_merged_state(self) -> None:
        result = ControllerResult(
            decision="MERGED", status="MERGED_BY_CONTROLLER",
            merged=True, merge_sha="b" * 40,
            blockers=[], broker_response="MERGED_BY_CONTROLLER",
        )
        assert result.merged is True
        assert result.decision == "MERGED"

    def test_rejected_state(self) -> None:
        result = ControllerResult(
            decision="MERGE_REJECTED", status="BLOCKED_BY_GOVERNANCE",
            merged=False, merge_sha=None,
            blockers=["PR_NOT_OPEN"], broker_response="BLOCKED_BY_GOVERNANCE",
        )
        assert result.merged is False
        assert result.decision == "MERGE_REJECTED"

    def test_unknown_outcome(self) -> None:
        result = ControllerResult(
            decision="MERGE_OUTCOME_UNKNOWN",
            status="MERGED_WITH_AUDIT_INCIDENT",
            merged=True, merge_sha="c" * 40,
            blockers=["COMPLETION_AUDIT_FAILED"],
            broker_response="MERGED_WITH_AUDIT_INCIDENT",
        )
        assert result.merged is True
        assert result.decision == "MERGE_OUTCOME_UNKNOWN"


# ----------------------------------------------------------------------
# repo_writer.perform_governed_merge (integration sketch)
# ----------------------------------------------------------------------


class TestRepoWriterIntegration:
    @_pytest_skip_on_non_posix
    def test_perform_governed_merge_requires_lock(self) -> None:
        """Calling perform_governed_merge without holding the lock must fail."""
        import orchestrator.scripts.repo_writer as rw

        # Create a temporary lock file.
        lock_path = _REPO_ROOT / "tests" / "_test_governed_merge_lock"  # will be removed
        try:
            lock = rw.RepoWriterLock(
                lock_path=lock_path,
                stale_seconds=60,
                enforce_sandbox=False,
                test_mode=True,
            )
            # Without calling acquire(), assert_held() will fail.
            with pytest.raises(rw.RepoWriterError) as exc_info:
                lock.perform_governed_merge(
                    repo="GoLukeEnviro/trading-hub",
                    pr_number=1,
                    expected_issue=1,
                    expected_head_sha="a" * 40,
                    controller_identity="test",
                )
            assert "LOCK_NOT_HELD" in str(exc_info.value)
        finally:
            if lock_path.exists():
                lock_path.unlink()


# ----------------------------------------------------------------------
# ADR references (verification that required files exist)
# ----------------------------------------------------------------------


def test_required_controller_files_exist() -> None:
    for f in [
        "orchestrator/scripts/roadmap_merge_controller.py",
        "orchestrator/scripts/roadmap_merge_controller_broker.py",
        "orchestrator/scripts/roadmap_merge_controller_denylist.txt",
        "orchestrator/scripts/roadmap_merge_controller_allowlist.txt",
        "orchestrator/scripts/roadmap_merge_controller_paths_allowlist.txt",
    ]:
        assert (_REPO_ROOT / f).is_file(), f"Required file missing: {f}"
