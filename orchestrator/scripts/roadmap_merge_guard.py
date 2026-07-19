"""Read-only readiness guard for human Trading Hub roadmap merges."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

REQUIRED_CHECKS = ("main-gate", "offline-smoke")
SELECTED_TASK_PATTERN = re.compile(
    r"<!--\s*roadmap-selected-task:(\d+)\s*-->",
    re.IGNORECASE,
)
FORMAL_BLOCK_PATTERN = re.compile(
    r"\b(?:formally_blocked(?:_[a-z0-9_]+)?|blocked_by_[a-z0-9_]+)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CheckSnapshot:
    name: str
    status: str
    conclusion: str


@dataclass(frozen=True)
class PullRequestSnapshot:
    number: int
    state: str
    is_draft: bool
    head_sha: str
    linked_issues: tuple[int, ...]
    issue_state: str
    issue_labels: tuple[str, ...]
    tracker_selected_task: int | None
    checks: tuple[CheckSnapshot, ...]
    unresolved_review_threads: int
    review_decision: str
    comments: tuple[str, ...]


@dataclass(frozen=True)
class MergeReadinessResult:
    ready: bool
    status: str
    blockers: tuple[str, ...]


def parse_selected_task(body: str) -> int | None:
    """Return the machine-selected #605 task, if present."""
    match = SELECTED_TASK_PATTERN.search(body or "")
    return int(match.group(1)) if match else None


# Phases that are considered "active enough" to be mergeable.
_ACTIVE_STATUSES = frozenset({"in_progress", "pending"})
_COMPLETE_STATUSES = frozenset({"complete", "completed", "done"})

# Path to the canonical roadmap YAML, resolved relative to the repo root.
# The guard is read-only and loads this only for dependency checks.
_CANONICAL_ROADMAP_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "governance"
    / "canonical-roadmap.yaml"
)


def _load_roadmap_dependencies() -> dict[str, list[str]]:
    """Load phase -> dependencies from the canonical roadmap YAML.

    Returns an empty dict if the file is missing or unreadable (fail-open for
    the dependency check; the status check still applies).
    """
    try:
        import yaml

        data = yaml.safe_load(_CANONICAL_ROADMAP_PATH.read_text())
        return {p["id"]: list(p.get("dependencies", [])) for p in data["phases"]}
    except Exception:
        return {}


def governance_task_compatible(
    *,
    selected_phase: str,
    roadmap_status: dict[str, str],
) -> bool:
    """Check whether a selected roadmap phase is mergeable (spec §7.4).

    Pure function. A phase is compatible only if:

    - it exists in ``roadmap_status``;
    - its status is ``in_progress`` or ``pending`` (not ``blocked``/``complete``);
    - all of its dependencies (from the canonical roadmap YAML) are in a
      complete state (``complete``/``completed``/``done``).

    The caller supplies the current status of each phase. Dependency edges are
    read from ``config/governance/canonical-roadmap.yaml``. If the roadmap file
    is unavailable, the dependency check is skipped (fail-open) and only the
    status check applies.
    """
    status = roadmap_status.get(selected_phase)
    if status is None:
        return False
    if status not in _ACTIVE_STATUSES:
        return False
    deps = _load_roadmap_dependencies().get(selected_phase, [])
    for dep in deps:
        dep_status = roadmap_status.get(dep)
        if dep_status not in _COMPLETE_STATUSES:
            return False
    return True


def evaluate_merge_readiness(
    snapshot: PullRequestSnapshot,
    *,
    expected_issue: int,
    expected_head_sha: str,
) -> MergeReadinessResult:
    """Evaluate facts only; this function never merges or mutates GitHub."""
    blockers: list[str] = []
    if snapshot.state.upper() != "OPEN":
        blockers.append("PR_NOT_OPEN")
    if snapshot.is_draft:
        blockers.append("PR_IS_DRAFT")
    if snapshot.head_sha.lower() != expected_head_sha.lower():
        blockers.append("HEAD_SHA_DRIFT")
    if expected_issue not in snapshot.linked_issues:
        blockers.append("EXPECTED_ISSUE_NOT_LINKED")
    if snapshot.issue_state.upper() != "OPEN":
        blockers.append("ISSUE_NOT_OPEN")
    if any(label.casefold() == "status:blocked" for label in snapshot.issue_labels):
        blockers.append("ISSUE_BLOCKED")
    if snapshot.tracker_selected_task != expected_issue:
        blockers.append("TRACKER_TASK_MISMATCH")

    checks = {check.name.casefold(): check for check in snapshot.checks}
    for required in REQUIRED_CHECKS:
        check = checks.get(required.casefold())
        if check is None:
            blockers.append(f"REQUIRED_CHECK_MISSING:{required}")
        elif check.status.upper() != "COMPLETED" or check.conclusion.upper() != "SUCCESS":
            blockers.append(f"REQUIRED_CHECK_NOT_SUCCESSFUL:{required}")

    if snapshot.unresolved_review_threads:
        blockers.append("UNRESOLVED_REVIEW_THREADS")
    if snapshot.review_decision.upper() == "CHANGES_REQUESTED":
        blockers.append("CHANGES_REQUESTED")
    if any(FORMAL_BLOCK_PATTERN.search(comment) for comment in snapshot.comments):
        blockers.append("FORMAL_GOVERNANCE_BLOCK")

    unique_blockers = tuple(dict.fromkeys(blockers))
    if unique_blockers:
        return MergeReadinessResult(
            ready=False,
            status="BLOCKED_BY_GOVERNANCE",
            blockers=unique_blockers,
        )
    return MergeReadinessResult(
        ready=True,
        status="READY_FOR_HUMAN_MERGE",
        blockers=(),
    )


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


def _check_snapshot(item: dict[str, Any]) -> CheckSnapshot:
    return CheckSnapshot(
        name=str(item.get("name") or item.get("context") or ""),
        status=str(item.get("status") or "COMPLETED"),
        conclusion=str(item.get("conclusion") or item.get("state") or ""),
    )


def collect_snapshot(*, repo: str, pr: int, expected_issue: int, tracker_issue: int) -> PullRequestSnapshot:
    """Collect current GitHub facts for one PR and its selected roadmap task."""
    pr_data = _run_gh_json(
        (
            "pr",
            "view",
            str(pr),
            "--repo",
            repo,
            "--json",
            "state,isDraft,headRefOid,statusCheckRollup,comments,reviewDecision",
        )
    )
    issue_data = _run_gh_json(
        (
            "issue",
            "view",
            str(expected_issue),
            "--repo",
            repo,
            "--json",
            "state,labels",
        )
    )
    tracker_data = _run_gh_json(
        (
            "issue",
            "view",
            str(tracker_issue),
            "--repo",
            repo,
            "--json",
            "body",
        )
    )
    owner, name = repo.split("/", 1)
    review_data = _run_gh_json(
        (
            "api",
            "graphql",
            "-f",
            "query=query($owner:String!,$name:String!,$pr:Int!){"
            "repository(owner:$owner,name:$name){pullRequest(number:$pr){"
            "reviewThreads(first:100){nodes{isResolved}}"
            "closingIssuesReferences(first:100){nodes{number}}}}}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"pr={pr}",
        )
    )
    review_threads = (
        review_data.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )
    closing_issues = (
        review_data.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("closingIssuesReferences", {})
        .get("nodes", [])
    )
    linked_issues = tuple(int(item["number"]) for item in closing_issues if "number" in item)
    labels = tuple(str(item.get("name", "")) for item in issue_data.get("labels", []))
    comments = tuple(str(item.get("body", "")) for item in pr_data.get("comments", []))
    checks = tuple(_check_snapshot(item) for item in pr_data.get("statusCheckRollup", []))
    return PullRequestSnapshot(
        number=pr,
        state=str(pr_data.get("state", "")),
        is_draft=bool(pr_data.get("isDraft", False)),
        head_sha=str(pr_data.get("headRefOid", "")),
        linked_issues=linked_issues,
        issue_state=str(issue_data.get("state", "")),
        issue_labels=labels,
        tracker_selected_task=parse_selected_task(str(tracker_data.get("body", ""))),
        checks=checks,
        unresolved_review_threads=sum(1 for thread in review_threads if not thread.get("isResolved", False)),
        review_decision=str(pr_data.get("reviewDecision") or ""),
        comments=comments,
    )


def _full_sha(value: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise argparse.ArgumentTypeError("expected a full 40-character commit SHA")
    return value.lower()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only roadmap PR readiness guard (human merge only)")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--expected-issue", required=True, type=int)
    parser.add_argument("--expected-head-sha", required=True, type=_full_sha)
    parser.add_argument("--tracker-issue", type=int, default=605)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        snapshot = collect_snapshot(
            repo=args.repo,
            pr=args.pr,
            expected_issue=args.expected_issue,
            tracker_issue=args.tracker_issue,
        )
    except (RuntimeError, ValueError, json.JSONDecodeError):
        result = MergeReadinessResult(
            ready=False,
            status="BLOCKED_BY_GOVERNANCE",
            blockers=("GITHUB_FACT_COLLECTION_FAILED",),
        )
        print(json.dumps(asdict(result), sort_keys=True))
        return 3
    result = evaluate_merge_readiness(
        snapshot,
        expected_issue=args.expected_issue,
        expected_head_sha=args.expected_head_sha,
    )
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
