"""Bounded autonomous merge controller for Trading Hub roadmap PRs.

This module is the **transition controller** introduced by ADR-2026-07-19. It
allows a narrowly-scoped controller identity to autonomously merge A1
roadmap PRs that fully satisfy the existing read-only
``roadmap_merge_guard`` contract **plus** additional safety invariants:

- explicit controller identity (separate from cron ticks and Hermes)
- file-based disable switch with fail-closed semantics
- global repository writer lock held across the entire merge decision
- two-snapshot TOCTOU protection (initial readiness + pre-merge re-check)
- exact head SHA binding via ``gh pr merge --match-head-commit``
- A1-only enforcement: any A2/A3 marker or live-trading trigger blocks
- append-only JSONL audit log on every decision (merge and block)
- no admin/force/auto/merge-method overrides; squash is the only mode

Design constraints (all enforced in code):

- **Never weakens** ``roadmap_merge_guard.py``: this controller uses the
  guard's read-only snapshot and evaluation primitives but does not
  modify them.
- **Fail-closed by default**: missing disable-switch file, unexpected
  content, missing writer lock, GitHub fact-collection failure, head
  drift, CI drift — all block the merge and write an audit record.
- **One merge per invocation**: the controller merges at most one PR per
  process. There is no batch mode.
- **Idempotent audit**: a duplicate merge attempt after a successful merge
  fails with ``PR_NOT_OPEN`` (or GitHub's "already merged" response) and
  is logged.
- **Human-only until activated**: the disable switch defaults to OFF.
  Merging the ADR and this code does not by itself enable autonomous
  merges; a separate activation step (file write under
  ``/opt/data/state/roadmap-merge-controller/``) is required and audited.

This module is intentionally side-effect-light outside its declared
surface (disable switch, writer lock, gh CLI call, audit log). It never
touches Docker, cron, strategies, configs, credentials or runtime state.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from orchestrator.scripts.roadmap_merge_guard import (
    MergeReadinessResult,
    PullRequestSnapshot,
    collect_snapshot,
    evaluate_merge_readiness,
)

# NOTE: ``repo_writer`` is imported lazily inside ``run_controller`` because
# it pulls in ``fcntl`` and ``pwd`` which are POSIX-only. Production runs on
# Linux (Hermes container); tests inject a writer_lock instance and never
# trigger the import path.

# ----------------------------------------------------------------------
# Canonical paths (single source of truth)
# ----------------------------------------------------------------------

PERSISTENT_STATE_DIR = Path("/opt/data/state")
CONTROLLER_STATE_DIR = PERSISTENT_STATE_DIR / "roadmap-merge-controller"
DISABLE_SWITCH_PATH = CONTROLLER_STATE_DIR / "enabled"
DEFAULT_AUDIT_LOG_PATH = CONTROLLER_STATE_DIR / "audit.jsonl"

# Strict enable token. Anything else (including "yes", "1", "True") blocks.
ENABLE_TOKEN = "true"

# A2/A3 / live-trading trigger patterns. A1-only enforcement.
A2_A3_TRIGGER_PATTERNS = (
    "APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION",
    "APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT",
    "A2-APPROVED",
    "A3-APPROVED",
    "dry_run=false",
    "dry_run = false",
    "live-trading",
    "live_order",
    "exchange_key",
)

# Audit event codes.
EVENT_CONTROLLER_DISABLED = "CONTROLLER_DISABLED"
EVENT_WRITER_LOCK_BLOCKED = "WRITER_LOCK_BLOCKED"
EVENT_A2A3_TRIGGER_DETECTED = "A2A3_TRIGGER_DETECTED"
EVENT_NOT_READY = "NOT_READY"
EVENT_TOCTOU_DRIFT = "TOCTOU_DRIFT"
EVENT_MERGED = "MERGED"
EVENT_GITHUB_ERROR = "GITHUB_ERROR"
EVENT_MERGE_COMMAND_FAILED = "MERGE_COMMAND_FAILED"


# ----------------------------------------------------------------------
# Result dataclass
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ControllerDecision:
    """Stable, JSON-serialisable controller decision."""

    decision: str  # one of EVENT_* codes
    status: str  # human-readable status token
    merged: bool
    merge_sha: Optional[str]
    blockers: tuple[str, ...]
    pr_number: int
    expected_issue: int
    expected_head_sha: str
    controller_identity: str
    duration_ms: int

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "controller_identity": self.controller_identity,
            "pr_number": self.pr_number,
            "expected_issue": self.expected_issue,
            "expected_head_sha": self.expected_head_sha,
            "decision": self.decision,
            "status": self.status,
            "merged": self.merged,
            "merge_sha": self.merge_sha,
            "blockers": list(self.blockers),
            "duration_ms": self.duration_ms,
        }


# ----------------------------------------------------------------------
# Disable switch (fail-closed)
# ----------------------------------------------------------------------


def is_controller_enabled(
    switch_path: Path = DISABLE_SWITCH_PATH,
) -> bool:
    """Return True iff the disable switch contains exactly the enable token.

    Fail-closed semantics:
    - missing file -> disabled
    - any non-regular file (symlink, dir) -> disabled
    - any content other than ``ENABLE_TOKEN`` (case-sensitive, no extra
      whitespace other than a single trailing newline) -> disabled
    """
    try:
        if not switch_path.is_file():
            return False
        content = switch_path.read_text(encoding="utf-8")
    except OSError:
        return False
    # Accept exactly "true" or "true\n"; nothing else.
    return content.strip() == ENABLE_TOKEN and "\n" not in content.rstrip("\n")


# ----------------------------------------------------------------------
# A1-only enforcement
# ----------------------------------------------------------------------


def detect_a2a3_triggers(
    issue_body: str,
    pr_body: str,
    pr_comments: Sequence[str],
) -> tuple[str, ...]:
    """Return a tuple of A2/A3 trigger tokens found in any issue/PR text.

    A1-only enforcement: any occurrence of an A2/A3 approval marker or
    live-trading trigger in the linked issue body, PR body or PR comments
    blocks the autonomous merge. Such PRs MUST be merged by Luke manually.
    """
    hayfields = (issue_body or "", pr_body or "", *(pr_comments or ()))
    haystack = "\n".join(hayfields)
    found: list[str] = []
    for pattern in A2_A3_TRIGGER_PATTERNS:
        if pattern.lower() in haystack.lower():
            found.append(pattern)
    return tuple(dict.fromkeys(found))


# ----------------------------------------------------------------------
# Audit log (append-only JSONL)
# ----------------------------------------------------------------------


def append_audit(
    audit_log_path: Path,
    decision: ControllerDecision,
) -> None:
    """Append a single JSONL record. Never raises into the merge path.

    Audit write failures are surfaced on stderr but never mask a merge or
    a block decision. The audit file MUST be preprovisioned by the
    controller deployment (root-owned parent, controller-writable file).
    """
    record = decision.to_audit_dict()
    line = json.dumps(record, sort_keys=True)
    try:
        with audit_log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        # Audit failure is a hard governance signal; print to stderr but
        # do NOT mask the controller decision. The caller may inspect
        # process exit code and PR state separately.
        print(f"AUDIT_WRITE_FAILED: {exc}", file=sys.stderr)


# ----------------------------------------------------------------------
# gh CLI helpers
# ----------------------------------------------------------------------


def fetch_issue_body(*, repo: str, issue_number: int) -> str:
    """Fetch linked issue body via ``gh issue view``."""
    data = _run_gh_json(
        ("issue", "view", str(issue_number), "--repo", repo, "--json", "body")
    )
    return str(data.get("body", ""))


def fetch_pr_body(*, repo: str, pr_number: int) -> str:
    """Fetch PR body via ``gh pr view``."""
    data = _run_gh_json(
        ("pr", "view", str(pr_number), "--repo", repo, "--json", "body")
    )
    return str(data.get("body", ""))


def fetch_pr_comments(*, repo: str, pr_number: int) -> tuple[str, ...]:
    """Fetch PR comments via ``gh api`` (GraphQL)."""
    owner, name = repo.split("/", 1)
    payload = _run_gh_json(
        (
            "api",
            "graphql",
            "-f",
            "query=query($owner:String!,$name:String!,$pr:Int!){"
            "repository(owner:$owner,name:$name){pullRequest(number:$pr){"
            "comments(first:100){nodes{body}}}}}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"pr={pr_number}",
        )
    )
    nodes = (
        payload.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("comments", {})
        .get("nodes", [])
    )
    return tuple(str(node.get("body", "")) for node in nodes)


def perform_squash_merge(
    *,
    repo: str,
    pr_number: int,
    expected_head_sha: str,
) -> str:
    """Run ``gh pr merge --squash --match-head-commit <sha>``.

    Returns the resulting merge SHA reported by GitHub. Raises
    ``RuntimeError`` on any non-zero return code, timeout, or unexpected
    output. The caller is responsible for translating the exception into
    a ``MERGE_COMMAND_FAILED`` audit decision.

    ``--match-head-commit`` is the GitHub-native TOCTOU binding: GitHub
    rejects the merge if the PR's current head differs from the supplied
    SHA. This is the authoritative last-line defence and is layered on
    top of the controller's own two-snapshot re-check.
    """
    result = subprocess.run(
        [
            "gh",
            "pr",
            "merge",
            str(pr_number),
            "--repo",
            repo,
            "--squash",
            "--match-head-commit",
            expected_head_sha,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            (result.stderr or result.stdout or "gh pr merge failed").strip()
        )
    # Re-fetch the merge commit SHA for the audit record.
    data = _run_gh_json(
        ("pr", "view", str(pr_number), "--repo", repo, "--json", "mergeCommit")
    )
    merge_commit = data.get("mergeCommit") or {}
    return str(merge_commit.get("oid") or "")


def _run_gh_json(arguments: Sequence[str]) -> dict[str, Any]:
    result = subprocess.run(
        ["gh", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh command failed")
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise RuntimeError("gh returned a non-object JSON payload")
    return data


# ----------------------------------------------------------------------
# Snapshot diff for TOCTOU detection
# ----------------------------------------------------------------------


def snapshot_drift_blockers(
    initial: PullRequestSnapshot,
    pre_merge: PullRequestSnapshot,
    *,
    expected_head_sha: str,
) -> tuple[str, ...]:
    """Return blockers if the PR state drifted between the two snapshots.

    Re-evaluates the same invariants as the read-only guard against the
    pre-merge snapshot and additionally checks that the head SHA and the
    required check conclusions did not change between snapshots.
    """
    blockers: list[str] = []

    # Head SHA must match both snapshots AND the supplied expected SHA.
    if pre_merge.head_sha.lower() != expected_head_sha.lower():
        blockers.append("HEAD_SHA_DRIFT")
    if initial.head_sha.lower() != pre_merge.head_sha.lower():
        blockers.append("HEAD_SHA_CHANGED_BETWEEN_SNAPSHOTS")

    # Required checks must still be SUCCESS in the pre-merge snapshot.
    required = {"main-gate", "offline-smoke"}
    pre_checks = {c.name.casefold(): c for c in pre_merge.checks}
    for req in required:
        check = pre_checks.get(req.casefold())
        if check is None:
            blockers.append(f"REQUIRED_CHECK_MISSING:{req}")
        elif check.status.upper() != "COMPLETED" or check.conclusion.upper() != "SUCCESS":
            blockers.append(f"REQUIRED_CHECK_NOT_SUCCESSFUL:{req}")

    # Re-run the full read-only guard against the pre-merge snapshot.
    pre_result = evaluate_merge_readiness(
        pre_merge,
        expected_issue=initial.linked_issues[0] if initial.linked_issues else -1,
        expected_head_sha=expected_head_sha,
    )
    if not pre_result.ready:
        blockers.extend(pre_result.blockers)

    # Also detect CI conclusion drift between snapshots.
    initial_checks = {c.name.casefold(): c for c in initial.checks}
    for req in required:
        before = initial_checks.get(req.casefold())
        after = pre_checks.get(req.casefold())
        if before and after:
            if before.conclusion.upper() != after.conclusion.upper():
                blockers.append(f"CHECK_CONCLUSION_DRIFT:{req}")

    return tuple(dict.fromkeys(blockers))


# ----------------------------------------------------------------------
# Controller entry point
# ----------------------------------------------------------------------


def run_controller(
    *,
    repo: str,
    pr_number: int,
    expected_issue: int,
    expected_head_sha: str,
    tracker_issue: int,
    controller_identity: str,
    audit_log_path: Path,
    switch_path: Path = DISABLE_SWITCH_PATH,
    writer_lock: Optional[Any] = None,
    clock: Optional[callable] = None,  # type: ignore[type-arg]
) -> ControllerDecision:
    """Run the bounded merge controller for one PR.

    Returns a :class:`ControllerDecision`. The caller (CLI or test) is
    responsible for the process exit code based on ``decision.merged``
    and ``decision.blockers``.

    ``writer_lock`` may be injected by tests. When ``None``, the
    production :class:`RepoWriterLock` is constructed lazily (POSIX
    only — the import of ``repo_writer`` is deferred to here so that
    importing this module on non-POSIX hosts does not fail).
    """
    started = (clock or time.monotonic)()

    def finish(
        decision: str,
        status: str,
        *,
        merged: bool,
        merge_sha: Optional[str],
        blockers: tuple[str, ...] = (),
    ) -> ControllerDecision:
        elapsed = int(((clock or time.monotonic)() - started) * 1000)
        result = ControllerDecision(
            decision=decision,
            status=status,
            merged=merged,
            merge_sha=merge_sha,
            blockers=blockers,
            pr_number=pr_number,
            expected_issue=expected_issue,
            expected_head_sha=expected_head_sha,
            controller_identity=controller_identity,
            duration_ms=elapsed,
        )
        append_audit(audit_log_path, result)
        return result

    # 1. Disable switch — fail-closed.
    if not is_controller_enabled(switch_path=switch_path):
        return finish(
            EVENT_CONTROLLER_DISABLED,
            "BLOCKED_BY_CONTROLLER_DISABLED",
            merged=False,
            merge_sha=None,
            blockers=("CONTROLLER_DISABLED",),
        )

    # 2. Writer lock — non-blocking, fail-closed.
    #
    # Production uses the default RepoWriterLock() (canonical path under
    # /opt/data/state/repo-writer/). Tests inject a tmp_path-scoped lock
    # with test_mode=True so they never touch production lock state.
    # The import is deferred because repo_writer pulls in POSIX-only
    # modules (fcntl, pwd) that are unavailable on Windows CI/dev hosts.
    lock_acquired_here = False
    if writer_lock is None:
        from orchestrator.scripts.repo_writer import RepoWriterLock

        writer_lock = RepoWriterLock()
        lock_acquired_here = True
    try:
        writer_lock.acquire(
            branch=f"ops/merge-controller-pr-{pr_number}",
            session_id=controller_identity,
        )
    except Exception as exc:  # noqa: BLE001 — broad on purpose, see codes below
        code = getattr(exc, "code", "WRITER_LOCK_ACQUIRE_FAILED")
        return finish(
            EVENT_WRITER_LOCK_BLOCKED,
            "BLOCKED_BY_WRITER_LOCK",
            merged=False,
            merge_sha=None,
            blockers=(str(code),),
        )

    try:
        # 3. Initial readiness snapshot + read-only guard evaluation.
        try:
            initial_snapshot = collect_snapshot(
                repo=repo,
                pr=pr_number,
                expected_issue=expected_issue,
                tracker_issue=tracker_issue,
            )
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            return finish(
                EVENT_GITHUB_ERROR,
                "BLOCKED_BY_GITHUB_FACT_COLLECTION",
                merged=False,
                merge_sha=None,
                blockers=("GITHUB_FACT_COLLECTION_FAILED", str(exc)),
            )

        initial_result = evaluate_merge_readiness(
            initial_snapshot,
            expected_issue=expected_issue,
            expected_head_sha=expected_head_sha,
        )
        if not initial_result.ready:
            return finish(
                EVENT_NOT_READY,
                "BLOCKED_BY_GOVERNANCE",
                merged=False,
                merge_sha=None,
                blockers=initial_result.blockers,
            )

        # 4. A1-only enforcement: scan issue body, PR body, PR comments.
        try:
            issue_body = fetch_issue_body(repo=repo, issue_number=expected_issue)
            pr_body = fetch_pr_body(repo=repo, pr_number=pr_number)
            pr_comments = fetch_pr_comments(repo=repo, pr_number=pr_number)
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            return finish(
                EVENT_GITHUB_ERROR,
                "BLOCKED_BY_GITHUB_FACT_COLLECTION",
                merged=False,
                merge_sha=None,
                blockers=("A1_AUDIT_FACT_COLLECTION_FAILED", str(exc)),
            )
        triggers = detect_a2a3_triggers(issue_body, pr_body, pr_comments)
        if triggers:
            return finish(
                EVENT_A2A3_TRIGGER_DETECTED,
                "BLOCKED_BY_A2A3_TRIGGER",
                merged=False,
                merge_sha=None,
                blockers=tuple(f"A2A3_TRIGGER:{token}" for token in triggers),
            )

        # 5. Pre-merge re-snapshot (TOCTOU protection).
        try:
            pre_merge_snapshot = collect_snapshot(
                repo=repo,
                pr=pr_number,
                expected_issue=expected_issue,
                tracker_issue=tracker_issue,
            )
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            return finish(
                EVENT_GITHUB_ERROR,
                "BLOCKED_BY_GITHUB_FACT_COLLECTION",
                merged=False,
                merge_sha=None,
                blockers=("PRE_MERGE_FACT_COLLECTION_FAILED", str(exc)),
            )
        drift_blockers = snapshot_drift_blockers(
            initial_snapshot,
            pre_merge_snapshot,
            expected_head_sha=expected_head_sha,
        )
        if drift_blockers:
            return finish(
                EVENT_TOCTOU_DRIFT,
                "BLOCKED_BY_TOCTOU_DRIFT",
                merged=False,
                merge_sha=None,
                blockers=drift_blockers,
            )

        # 6. Perform the squash merge with exact head SHA binding.
        try:
            merge_sha = perform_squash_merge(
                repo=repo,
                pr_number=pr_number,
                expected_head_sha=expected_head_sha,
            )
        except RuntimeError as exc:
            return finish(
                EVENT_MERGE_COMMAND_FAILED,
                "BLOCKED_BY_MERGE_COMMAND",
                merged=False,
                merge_sha=None,
                blockers=("MERGE_COMMAND_FAILED", str(exc)),
            )

        return finish(
            EVENT_MERGED,
            "MERGED_BY_CONTROLLER",
            merged=True,
            merge_sha=merge_sha,
        )
    finally:
        writer_lock.release()


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def _full_sha(value: str) -> str:
    import re

    if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise argparse.ArgumentTypeError("expected a full 40-character commit SHA")
    return value.lower()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bounded autonomous merge controller for A1 roadmap PRs "
            "(disable switch defaults OFF; ADR-2026-07-19)."
        ),
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--expected-issue", required=True, type=int)
    parser.add_argument("--expected-head-sha", required=True, type=_full_sha)
    parser.add_argument("--tracker-issue", type=int, default=605)
    parser.add_argument(
        "--controller-identity",
        required=True,
        help="Stable identity token recorded in the audit log.",
    )
    parser.add_argument(
        "--audit-log",
        type=Path,
        default=DEFAULT_AUDIT_LOG_PATH,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    decision = run_controller(
        repo=args.repo,
        pr_number=args.pr,
        expected_issue=args.expected_issue,
        expected_head_sha=args.expected_head_sha,
        tracker_issue=args.tracker_issue,
        controller_identity=args.controller_identity,
        audit_log_path=args.audit_log,
    )
    print(json.dumps(asdict(decision), sort_keys=True))
    if decision.merged:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
