"""Tests for the bounded roadmap autonomous merge controller.

These tests are hermetic: they inject tmp_path-scoped lock files, monkeypatch
all gh/subprocess interactions, and never touch production state under
``/opt/data/state/roadmap-merge-controller/`` or
``/opt/data/state/repo-writer/``.

Coverage areas (per ADR-2026-07-19 and the user-prompt contract):

- Disable switch strictness (default OFF, fail-closed on any non-canonical
  content)
- Writer lock binding (non-blocking, fail-closed on contention)
- Initial readiness via the read-only guard
- A1-only enforcement (A2/A3/live-trading triggers block)
- Two-snapshot TOCTOU protection (head drift, CI drift between snapshots)
- Parallel merge serialisation via the global writer lock
- Audit log written on every decision (merge and block)
- gh pr merge uses ``--squash --match-head-commit`` (no admin/force/auto)
- CLI contract: no admin/force/auto/merge-method switches
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import orchestrator.scripts.roadmap_merge_controller as controller
from orchestrator.scripts.roadmap_merge_controller import (
    A2_A3_TRIGGER_PATTERNS,
    ControllerDecision,
    detect_a2a3_triggers,
    is_controller_enabled,
    snapshot_drift_blockers,
)
from orchestrator.scripts.roadmap_merge_guard import (
    CheckSnapshot,
    PullRequestSnapshot,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ``repo_writer`` pulls in ``fcntl`` and ``pwd`` which are POSIX-only. On
# non-POSIX hosts (Windows dev/CI) we fall back to an in-process stub lock
# so the controller logic remains testable cross-platform. The POSIX path
# uses the real ``RepoWriterLock`` with the same interface.
try:
    from orchestrator.scripts.repo_writer import RepoWriterLock  # type: ignore
except (ImportError, ModuleNotFoundError):  # pragma: no cover - POSIX guard
    class RepoWriterLock:  # type: ignore[no-redef]
        """Minimal in-process stub mirroring the RepoWriterLock contract.

        Provides ``acquire``, ``release``, ``is_locked`` and the
        ``_lock_path`` attribute used by the parallel-merge test. Uses a
        module-level set of held paths for cross-instance serialisation
        within one process.
        """

        _held_paths: set[str] = set()

        class _Blocked(Exception):
            code = "BLOCKED_BY_ACTIVE_REPO_WRITER"

        class _Error(Exception):
            pass

        # The real RepoWriterError is exported separately; we expose it as
        # an attribute for tests that catch the broad Exception path.
        def __init__(
            self,
            lock_path: Path | None = None,
            stale_seconds: int = 60,
            enforce_sandbox: bool = False,
            test_mode: bool = False,
        ) -> None:
            self._lock_path = lock_path or Path("./stub.lock")
            self._held = False

        def acquire(self, *, branch: str, session_id: str, worktree_path: str = "") -> Any:
            key = str(self._lock_path)
            if key in self._held_paths:
                raise self._Blocked()
            self._held_paths.add(key)
            self._held = True
            holder = type(
                "Holder",
                (),
                {
                    "pid": os.getpid(),
                    "branch": branch,
                    "session_id": session_id,
                    "worktree_path": worktree_path,
                },
            )()
            return holder

        def release(self) -> None:
            if self._held:
                self._held_paths.discard(str(self._lock_path))
                self._held = False

        def is_locked(self) -> bool:
            return self._held


RepoWriterError = getattr(RepoWriterLock, "_Error", Exception)


EXPECTED_HEAD = "a" * 40
EXPECTED_HEAD_2 = "b" * 40


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def tmp_switch_path(tmp_path: Path) -> Path:
    return tmp_path / "controller-enabled"


@pytest.fixture
def tmp_audit_log(tmp_path: Path) -> Path:
    return tmp_path / "audit.jsonl"


@pytest.fixture
def tmp_lock(tmp_path: Path) -> RepoWriterLock:
    return RepoWriterLock(
        lock_path=tmp_path / "test-controller.lock",
        stale_seconds=60,
        enforce_sandbox=False,
        test_mode=True,
    )


@pytest.fixture
def enabled_switch(tmp_switch_path: Path) -> Path:
    tmp_switch_path.write_text("true\n", encoding="utf-8")
    return tmp_switch_path


def ready_snapshot(head_sha: str = EXPECTED_HEAD) -> PullRequestSnapshot:
    return PullRequestSnapshot(
        number=637,
        state="OPEN",
        is_draft=False,
        head_sha=head_sha,
        linked_issues=(634,),
        issue_state="OPEN",
        issue_labels=(),
        tracker_selected_task=634,
        checks=(
            CheckSnapshot("main-gate", "COMPLETED", "SUCCESS"),
            CheckSnapshot("offline-smoke", "COMPLETED", "SUCCESS"),
        ),
        unresolved_review_threads=0,
        review_decision="",
        comments=(),
    )


# ----------------------------------------------------------------------
# Disable switch strictness
# ----------------------------------------------------------------------


class TestDisableSwitch:
    def test_missing_file_blocks(self, tmp_switch_path: Path) -> None:
        assert is_controller_enabled(switch_path=tmp_switch_path) is False

    @pytest.mark.parametrize("content", ["yes", "1", "True", "TRUE", "on", "enabled", "1\n", ""])
    def test_non_canonical_content_blocks(self, tmp_switch_path: Path, content: str) -> None:
        tmp_switch_path.write_text(content, encoding="utf-8")
        assert is_controller_enabled(switch_path=tmp_switch_path) is False

    def test_exact_true_with_trailing_newline_enables(self, tmp_switch_path: Path) -> None:
        tmp_switch_path.write_text("true\n", encoding="utf-8")
        assert is_controller_enabled(switch_path=tmp_switch_path) is True

    def test_directory_is_not_enabled(self, tmp_switch_path: Path) -> None:
        tmp_switch_path.mkdir()
        assert is_controller_enabled(switch_path=tmp_switch_path) is False

    def test_controller_returns_disabled_when_switch_missing(
        self,
        tmp_audit_log: Path,
        tmp_lock: RepoWriterLock,
        tmp_switch_path: Path,
    ) -> None:
        decision = controller.run_controller(
            repo="GoLukeEnviro/trading-hub",
            pr_number=637,
            expected_issue=634,
            expected_head_sha=EXPECTED_HEAD,
            tracker_issue=605,
            controller_identity="roadmap-merge-controller-bot",
            audit_log_path=tmp_audit_log,
            switch_path=tmp_switch_path,
            writer_lock=tmp_lock,
        )
        assert decision.merged is False
        assert decision.decision == controller.EVENT_CONTROLLER_DISABLED
        assert "CONTROLLER_DISABLED" in decision.blockers
        # Audit was still written even though disabled.
        assert tmp_audit_log.exists()


# ----------------------------------------------------------------------
# Writer lock binding
# ----------------------------------------------------------------------


class TestWriterLockBinding:
    def test_contended_writer_lock_blocks(
        self,
        enabled_switch: Path,
        tmp_audit_log: Path,
        tmp_lock: RepoWriterLock,
    ) -> None:
        # Acquire the lock from a "different session" first.
        holder_lock = RepoWriterLock(
            lock_path=tmp_lock._lock_path,
            stale_seconds=60,
            enforce_sandbox=False,
            test_mode=True,
        )
        holder_lock.acquire(branch="ops/other", session_id="other-session")
        try:
            decision = controller.run_controller(
                repo="GoLukeEnviro/trading-hub",
                pr_number=637,
                expected_issue=634,
                expected_head_sha=EXPECTED_HEAD,
                tracker_issue=605,
                controller_identity="roadmap-merge-controller-bot",
                audit_log_path=tmp_audit_log,
                switch_path=enabled_switch,
                writer_lock=tmp_lock,
            )
            assert decision.merged is False
            assert decision.decision == controller.EVENT_WRITER_LOCK_BLOCKED
            assert "BLOCKED_BY_ACTIVE_REPO_WRITER" in decision.blockers
        finally:
            holder_lock.release()


# ----------------------------------------------------------------------
# Initial readiness via read-only guard
# ----------------------------------------------------------------------


def _patch_collect_snapshot(monkeypatch: pytest.MonkeyPatch, snapshot: PullRequestSnapshot) -> None:
    def fixed(**_kwargs: Any) -> PullRequestSnapshot:
        return snapshot

    monkeypatch.setattr(controller, "collect_snapshot", fixed)


def _patch_text_fetchers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    issue_body: str = "",
    pr_body: str = "",
    pr_comments: tuple[str, ...] = (),
) -> None:
    monkeypatch.setattr(
        controller,
        "fetch_issue_body",
        lambda **_kw: issue_body,
    )
    monkeypatch.setattr(
        controller,
        "fetch_pr_body",
        lambda **_kw: pr_body,
    )
    monkeypatch.setattr(
        controller,
        "fetch_pr_comments",
        lambda **_kw: pr_comments,
    )


def _patch_merge(
    monkeypatch: pytest.MonkeyPatch,
    *,
    merge_sha: str = "c" * 40,
    fail_with: str | None = None,
    calls: list[dict[str, Any]] | None = None,
) -> None:
    calls_list: list[dict[str, Any]] = calls if calls is not None else []

    def fake_merge(**kwargs: Any) -> str:
        calls_list.append(kwargs)
        if fail_with is not None:
            raise RuntimeError(fail_with)
        return merge_sha

    monkeypatch.setattr(controller, "perform_squash_merge", fake_merge)


class TestInitialReadiness:
    def test_pr_not_open_blocks(
        self,
        enabled_switch: Path,
        tmp_audit_log: Path,
        tmp_lock: RepoWriterLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        snapshot = replace(ready_snapshot(), state="CLOSED")
        _patch_collect_snapshot(monkeypatch, snapshot)
        decision = controller.run_controller(
            repo="GoLukeEnviro/trading-hub",
            pr_number=637,
            expected_issue=634,
            expected_head_sha=EXPECTED_HEAD,
            tracker_issue=605,
            controller_identity="roadmap-merge-controller-bot",
            audit_log_path=tmp_audit_log,
            switch_path=enabled_switch,
            writer_lock=tmp_lock,
        )
        assert decision.merged is False
        assert decision.decision == controller.EVENT_NOT_READY
        assert "PR_NOT_OPEN" in decision.blockers

    def test_required_check_failure_blocks(
        self,
        enabled_switch: Path,
        tmp_audit_log: Path,
        tmp_lock: RepoWriterLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        snapshot = replace(
            ready_snapshot(),
            checks=(
                CheckSnapshot("main-gate", "COMPLETED", "SUCCESS"),
                CheckSnapshot("offline-smoke", "COMPLETED", "FAILURE"),
            ),
        )
        _patch_collect_snapshot(monkeypatch, snapshot)
        decision = controller.run_controller(
            repo="GoLukeEnviro/trading-hub",
            pr_number=637,
            expected_issue=634,
            expected_head_sha=EXPECTED_HEAD,
            tracker_issue=605,
            controller_identity="roadmap-merge-controller-bot",
            audit_log_path=tmp_audit_log,
            switch_path=enabled_switch,
            writer_lock=tmp_lock,
        )
        assert decision.merged is False
        assert decision.decision == controller.EVENT_NOT_READY


# ----------------------------------------------------------------------
# A1-only enforcement
# ----------------------------------------------------------------------


class TestA1OnlyEnforcement:
    @pytest.mark.parametrize(
        ("issue_body", "pr_body", "pr_comments", "expected_trigger"),
        [
            ("Some A2-APPROVED marker", "", (), "A2-APPROVED"),
            ("", "dry_run=false proposal", (), "dry_run=false"),
            ("", "", ("live-trading trigger",), "live-trading"),
            (
                "APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION",
                "",
                (),
                "APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION",
            ),
            (
                "",
                "APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT",
                (),
                "APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT",
            ),
            ("A3-APPROVED", "", (), "A3-APPROVED"),
        ],
    )
    def test_trigger_detection(
        self,
        issue_body: str,
        pr_body: str,
        pr_comments: tuple[str, ...],
        expected_trigger: str,
    ) -> None:
        triggers = detect_a2a3_triggers(issue_body, pr_body, pr_comments)
        assert expected_trigger in triggers

    def test_clean_a1_pr_no_triggers(self) -> None:
        triggers = detect_a2a3_triggers(
            "Closes #634\n\nDocs-only reconciliation.",
            "Docs PR for SEC-3 reconciliation.",
            (),
        )
        assert triggers == ()

    def test_a2_marker_in_issue_blocks_controller(
        self,
        enabled_switch: Path,
        tmp_audit_log: Path,
        tmp_lock: RepoWriterLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_collect_snapshot(monkeypatch, ready_snapshot())
        _patch_text_fetchers(
            monkeypatch,
            issue_body="A2-APPROVED by Luke\n\nDeployment plan...",
            pr_body="docs PR",
            pr_comments=(),
        )
        merge_calls: list[dict[str, Any]] = []
        _patch_merge(monkeypatch, calls=merge_calls)

        decision = controller.run_controller(
            repo="GoLukeEnviro/trading-hub",
            pr_number=637,
            expected_issue=634,
            expected_head_sha=EXPECTED_HEAD,
            tracker_issue=605,
            controller_identity="roadmap-merge-controller-bot",
            audit_log_path=tmp_audit_log,
            switch_path=enabled_switch,
            writer_lock=tmp_lock,
        )
        assert decision.merged is False
        assert decision.decision == controller.EVENT_A2A3_TRIGGER_DETECTED
        assert any("A2-APPROVED" in b for b in decision.blockers)
        # Critically: no merge attempt was made.
        assert merge_calls == []

    def test_dry_run_false_in_pr_body_blocks(
        self,
        enabled_switch: Path,
        tmp_audit_log: Path,
        tmp_lock: RepoWriterLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_collect_snapshot(monkeypatch, ready_snapshot())
        _patch_text_fetchers(
            monkeypatch,
            issue_body="",
            pr_body="Config change: dry_run=false in production",
            pr_comments=(),
        )
        merge_calls: list[dict[str, Any]] = []
        _patch_merge(monkeypatch, calls=merge_calls)

        decision = controller.run_controller(
            repo="GoLukeEnviro/trading-hub",
            pr_number=637,
            expected_issue=634,
            expected_head_sha=EXPECTED_HEAD,
            tracker_issue=605,
            controller_identity="roadmap-merge-controller-bot",
            audit_log_path=tmp_audit_log,
            switch_path=enabled_switch,
            writer_lock=tmp_lock,
        )
        assert decision.merged is False
        assert decision.decision == controller.EVENT_A2A3_TRIGGER_DETECTED
        assert any("dry_run=false" in b for b in decision.blockers)
        assert merge_calls == []


# ----------------------------------------------------------------------
# TOCTOU protection
# ----------------------------------------------------------------------


class TestTOCTOUProtection:
    def test_snapshot_drift_blockers_detects_head_change(self) -> None:
        initial = ready_snapshot(head_sha=EXPECTED_HEAD)
        pre_merge = ready_snapshot(head_sha=EXPECTED_HEAD_2)
        blockers = snapshot_drift_blockers(
            initial,
            pre_merge,
            expected_head_sha=EXPECTED_HEAD,
        )
        assert "HEAD_SHA_DRIFT" in blockers
        assert "HEAD_SHA_CHANGED_BETWEEN_SNAPSHOTS" in blockers

    def test_snapshot_drift_blockers_detects_ci_drift(self) -> None:
        initial = ready_snapshot()
        pre_merge = replace(
            ready_snapshot(),
            checks=(
                CheckSnapshot("main-gate", "COMPLETED", "SUCCESS"),
                CheckSnapshot("offline-smoke", "COMPLETED", "FAILURE"),
            ),
        )
        blockers = snapshot_drift_blockers(
            initial,
            pre_merge,
            expected_head_sha=EXPECTED_HEAD,
        )
        assert "REQUIRED_CHECK_NOT_SUCCESSFUL:offline-smoke" in blockers

    def test_head_drift_between_snapshots_blocks(
        self,
        enabled_switch: Path,
        tmp_audit_log: Path,
        tmp_lock: RepoWriterLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Initial snapshot is ready with EXPECTED_HEAD.
        # Pre-merge snapshot shows head drifted to EXPECTED_HEAD_2.
        call_count = {"n": 0}

        def drifting(**_kwargs: Any) -> PullRequestSnapshot:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return ready_snapshot(head_sha=EXPECTED_HEAD)
            return ready_snapshot(head_sha=EXPECTED_HEAD_2)

        monkeypatch.setattr(controller, "collect_snapshot", drifting)
        _patch_text_fetchers(monkeypatch)
        merge_calls: list[dict[str, Any]] = []
        _patch_merge(monkeypatch, calls=merge_calls)

        decision = controller.run_controller(
            repo="GoLukeEnviro/trading-hub",
            pr_number=637,
            expected_issue=634,
            expected_head_sha=EXPECTED_HEAD,
            tracker_issue=605,
            controller_identity="roadmap-merge-controller-bot",
            audit_log_path=tmp_audit_log,
            switch_path=enabled_switch,
            writer_lock=tmp_lock,
        )
        assert decision.merged is False
        assert decision.decision == controller.EVENT_TOCTOU_DRIFT
        assert "HEAD_SHA_DRIFT" in decision.blockers
        assert merge_calls == []

    def test_ci_rerun_drift_between_snapshots_blocks(
        self,
        enabled_switch: Path,
        tmp_audit_log: Path,
        tmp_lock: RepoWriterLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        call_count = {"n": 0}

        def drifting(**_kwargs: Any) -> PullRequestSnapshot:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return ready_snapshot()
            return replace(
                ready_snapshot(),
                checks=(
                    CheckSnapshot("main-gate", "COMPLETED", "SUCCESS"),
                    CheckSnapshot("offline-smoke", "IN_PROGRESS", ""),
                ),
            )

        monkeypatch.setattr(controller, "collect_snapshot", drifting)
        _patch_text_fetchers(monkeypatch)
        merge_calls: list[dict[str, Any]] = []
        _patch_merge(monkeypatch, calls=merge_calls)

        decision = controller.run_controller(
            repo="GoLukeEnviro/trading-hub",
            pr_number=637,
            expected_issue=634,
            expected_head_sha=EXPECTED_HEAD,
            tracker_issue=605,
            controller_identity="roadmap-merge-controller-bot",
            audit_log_path=tmp_audit_log,
            switch_path=enabled_switch,
            writer_lock=tmp_lock,
        )
        assert decision.merged is False
        assert decision.decision == controller.EVENT_TOCTOU_DRIFT
        assert any("offline-smoke" in b for b in decision.blockers)
        assert merge_calls == []


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------


class TestHappyPath:
    def test_clean_a1_pr_merges_with_exact_head_binding(
        self,
        enabled_switch: Path,
        tmp_audit_log: Path,
        tmp_lock: RepoWriterLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_collect_snapshot(monkeypatch, ready_snapshot())
        _patch_text_fetchers(
            monkeypatch,
            issue_body="Closes #634\nDocs-only reconciliation.",
            pr_body="docs(state): reconcile SEC-3",
            pr_comments=(),
        )
        merge_calls: list[dict[str, Any]] = []
        _patch_merge(monkeypatch, merge_sha="d" * 40, calls=merge_calls)

        decision = controller.run_controller(
            repo="GoLukeEnviro/trading-hub",
            pr_number=637,
            expected_issue=634,
            expected_head_sha=EXPECTED_HEAD,
            tracker_issue=605,
            controller_identity="roadmap-merge-controller-bot",
            audit_log_path=tmp_audit_log,
            switch_path=enabled_switch,
            writer_lock=tmp_lock,
        )
        assert decision.merged is True
        assert decision.decision == controller.EVENT_MERGED
        assert decision.merge_sha == "d" * 40
        assert len(merge_calls) == 1
        # The merge MUST have been called with the exact expected SHA.
        assert merge_calls[0]["expected_head_sha"] == EXPECTED_HEAD
        assert merge_calls[0]["pr_number"] == 637


# ----------------------------------------------------------------------
# Audit log
# ----------------------------------------------------------------------


class TestAuditLog:
    def test_audit_record_for_block(
        self,
        tmp_switch_path: Path,
        tmp_audit_log: Path,
        tmp_lock: RepoWriterLock,
    ) -> None:
        decision = controller.run_controller(
            repo="GoLukeEnviro/trading-hub",
            pr_number=637,
            expected_issue=634,
            expected_head_sha=EXPECTED_HEAD,
            tracker_issue=605,
            controller_identity="roadmap-merge-controller-bot",
            audit_log_path=tmp_audit_log,
            switch_path=tmp_switch_path,
            writer_lock=tmp_lock,
        )
        assert tmp_audit_log.exists()
        records = [json.loads(line) for line in tmp_audit_log.read_text().splitlines()]
        assert len(records) == 1
        record = records[0]
        assert record["decision"] == controller.EVENT_CONTROLLER_DISABLED
        assert record["merged"] is False
        assert record["controller_identity"] == "roadmap-merge-controller-bot"
        assert record["pr_number"] == 637
        assert record["expected_issue"] == 634
        assert record["expected_head_sha"] == EXPECTED_HEAD

    def test_audit_record_for_merge(
        self,
        enabled_switch: Path,
        tmp_audit_log: Path,
        tmp_lock: RepoWriterLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_collect_snapshot(monkeypatch, ready_snapshot())
        _patch_text_fetchers(monkeypatch)
        _patch_merge(monkeypatch, merge_sha="e" * 40)

        decision = controller.run_controller(
            repo="GoLukeEnviro/trading-hub",
            pr_number=637,
            expected_issue=634,
            expected_head_sha=EXPECTED_HEAD,
            tracker_issue=605,
            controller_identity="roadmap-merge-controller-bot",
            audit_log_path=tmp_audit_log,
            switch_path=enabled_switch,
            writer_lock=tmp_lock,
        )
        assert decision.merged is True
        records = [json.loads(line) for line in tmp_audit_log.read_text().splitlines()]
        assert len(records) == 1
        assert records[0]["decision"] == controller.EVENT_MERGED
        assert records[0]["merged"] is True
        assert records[0]["merge_sha"] == "e" * 40


# ----------------------------------------------------------------------
# Parallel merge serialisation
# ----------------------------------------------------------------------


class TestParallelMergeSerialisation:
    def test_two_parallel_calls_serialised_by_writer_lock(
        self,
        enabled_switch: Path,
        tmp_audit_log: Path,
        tmp_lock: RepoWriterLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Two controller invocations sharing the same lock file cannot
        both reach the merge step. The second one must block on the
        writer lock and never invoke perform_squash_merge.
        """
        _patch_collect_snapshot(monkeypatch, ready_snapshot())
        _patch_text_fetchers(monkeypatch)
        merge_calls: list[dict[str, Any]] = []
        _patch_merge(monkeypatch, merge_sha="f" * 40, calls=merge_calls)

        # Hold the lock externally to simulate a concurrent controller.
        contended_lock = RepoWriterLock(
            lock_path=tmp_lock._lock_path,
            stale_seconds=60,
            enforce_sandbox=False,
            test_mode=True,
        )
        contended_lock.acquire(branch="ops/other-controller", session_id="other")
        try:
            decision = controller.run_controller(
                repo="GoLukeEnviro/trading-hub",
                pr_number=637,
                expected_issue=634,
                expected_head_sha=EXPECTED_HEAD,
                tracker_issue=605,
                controller_identity="roadmap-merge-controller-bot-A",
                audit_log_path=tmp_audit_log,
                switch_path=enabled_switch,
                writer_lock=tmp_lock,
            )
            assert decision.merged is False
            assert decision.decision == controller.EVENT_WRITER_LOCK_BLOCKED
            assert merge_calls == []
        finally:
            contended_lock.release()


# ----------------------------------------------------------------------
# perform_squash_merge uses --squash --match-head-commit (no admin/force)
# ----------------------------------------------------------------------


class TestMergeCommandContract:
    def test_merge_command_uses_squash_and_match_head_commit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured_argv: list[list[str]] = []

        def fake_run(argv: list[str], **_kwargs: Any) -> Any:
            captured_argv.append(list(argv))
            class _Result:
                returncode = 0
                stdout = ""
                stderr = ""

            return _Result()

        monkeypatch.setattr(controller.subprocess, "run", fake_run)
        # Also patch the JSON re-fetch that follows a successful merge.
        monkeypatch.setattr(
            controller,
            "_run_gh_json",
            lambda _args: {"mergeCommit": {"oid": "1" * 40}},
        )
        merge_sha = controller.perform_squash_merge(
            repo="GoLukeEnviro/trading-hub",
            pr_number=637,
            expected_head_sha=EXPECTED_HEAD,
        )
        assert merge_sha == "1" * 40
        # The first subprocess call is the merge itself.
        merge_call = captured_argv[0]
        assert merge_call[0:4] == ["gh", "pr", "merge", "637"]
        assert "--squash" in merge_call
        assert "--match-head-commit" in merge_call
        assert EXPECTED_HEAD in merge_call
        # Forbidden flags must NOT appear.
        joined = " ".join(merge_call)
        assert "--admin" not in joined
        assert "--force" not in joined
        assert "--auto" not in joined
        assert "--rebase" not in joined
        assert "--merge" not in joined  # only --squash is allowed


# ----------------------------------------------------------------------
# CLI contract: no admin/force/auto/merge-method switches
# ----------------------------------------------------------------------


class TestCLIContract:
    def test_parser_has_no_admin_or_force_or_auto_or_merge_method_switch(self) -> None:
        parser = controller.build_parser()
        option_strings = {option_string for action in parser._actions for option_string in action.option_strings}
        for forbidden in ("--admin", "--force", "--auto", "--merge-method", "--rebase", "--no-edit"):
            assert forbidden not in option_strings

    def test_parser_requires_controller_identity(self) -> None:
        parser = controller.build_parser()
        args = parser.parse_args(
            [
                "--repo",
                "GoLukeEnviro/trading-hub",
                "--pr",
                "637",
                "--expected-issue",
                "634",
                "--expected-head-sha",
                EXPECTED_HEAD,
                "--controller-identity",
                "roadmap-merge-controller-bot",
            ]
        )
        assert args.controller_identity == "roadmap-merge-controller-bot"
        assert args.tracker_issue == 605


# ----------------------------------------------------------------------
# Trigger pattern coverage sanity
# ----------------------------------------------------------------------


def test_a2a3_trigger_patterns_are_non_empty() -> None:
    assert A2_A3_TRIGGER_PATTERNS
    assert "dry_run=false" in A2_A3_TRIGGER_PATTERNS
    assert "A2-APPROVED" in A2_A3_TRIGGER_PATTERNS
    assert "A3-APPROVED" in A2_A3_TRIGGER_PATTERNS
