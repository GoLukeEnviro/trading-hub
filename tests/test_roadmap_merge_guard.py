"""Tests for the read-only, human-only roadmap merge readiness guard."""

from __future__ import annotations

from dataclasses import replace

import pytest

import orchestrator.scripts.roadmap_merge_guard as merge_guard
from orchestrator.scripts.roadmap_merge_guard import (
    CheckSnapshot,
    PullRequestSnapshot,
    build_parser,
    evaluate_merge_readiness,
    parse_selected_task,
)

EXPECTED_HEAD = "a" * 40


def ready_snapshot() -> PullRequestSnapshot:
    return PullRequestSnapshot(
        number=622,
        state="OPEN",
        is_draft=False,
        head_sha=EXPECTED_HEAD,
        linked_issues=(621,),
        issue_state="OPEN",
        issue_labels=(),
        tracker_selected_task=621,
        checks=(
            CheckSnapshot("main-gate", "COMPLETED", "SUCCESS"),
            CheckSnapshot("offline-smoke", "COMPLETED", "SUCCESS"),
        ),
        unresolved_review_threads=0,
        review_decision="",
        comments=(),
    )


def assert_blocked(snapshot: PullRequestSnapshot, blocker: str) -> None:
    result = evaluate_merge_readiness(
        snapshot,
        expected_issue=621,
        expected_head_sha=EXPECTED_HEAD,
    )
    assert result.status == "BLOCKED_BY_GOVERNANCE"
    assert blocker in result.blockers


def test_ready_snapshot_stops_at_human_merge_boundary() -> None:
    result = evaluate_merge_readiness(
        ready_snapshot(),
        expected_issue=621,
        expected_head_sha=EXPECTED_HEAD,
    )
    assert result.ready is True
    assert result.status == "READY_FOR_HUMAN_MERGE"
    assert result.blockers == ()


@pytest.mark.parametrize(
    ("changes", "blocker"),
    [
        ({"state": "MERGED"}, "PR_NOT_OPEN"),
        ({"is_draft": True}, "PR_IS_DRAFT"),
        ({"head_sha": "b" * 40}, "HEAD_SHA_DRIFT"),
        ({"linked_issues": (604,)}, "EXPECTED_ISSUE_NOT_LINKED"),
        ({"issue_state": "CLOSED"}, "ISSUE_NOT_OPEN"),
        ({"issue_labels": ("status:blocked",)}, "ISSUE_BLOCKED"),
        ({"tracker_selected_task": 604}, "TRACKER_TASK_MISMATCH"),
        ({"unresolved_review_threads": 1}, "UNRESOLVED_REVIEW_THREADS"),
        ({"review_decision": "CHANGES_REQUESTED"}, "CHANGES_REQUESTED"),
    ],
)
def test_snapshot_contract_blockers(
    changes: dict[str, object],
    blocker: str,
) -> None:
    assert_blocked(replace(ready_snapshot(), **changes), blocker)


def test_missing_required_check_blocks() -> None:
    snapshot = replace(
        ready_snapshot(),
        checks=(CheckSnapshot("main-gate", "COMPLETED", "SUCCESS"),),
    )
    assert_blocked(snapshot, "REQUIRED_CHECK_MISSING:offline-smoke")


@pytest.mark.parametrize(
    "check",
    [
        CheckSnapshot("offline-smoke", "IN_PROGRESS", ""),
        CheckSnapshot("offline-smoke", "COMPLETED", "FAILURE"),
        CheckSnapshot("offline-smoke", "COMPLETED", "CANCELLED"),
    ],
)
def test_non_successful_required_check_blocks(check: CheckSnapshot) -> None:
    snapshot = replace(
        ready_snapshot(),
        checks=(
            CheckSnapshot("main-gate", "COMPLETED", "SUCCESS"),
            check,
        ),
    )
    assert_blocked(snapshot, "REQUIRED_CHECK_NOT_SUCCESSFUL:offline-smoke")


@pytest.mark.parametrize(
    "comment",
    [
        "FORMALLY_BLOCKED_OUT_OF_ORDER",
        "Status: BLOCKED_BY_PHASE0A_AND_599",
        "formally_blocked_by_revert_and_base_drift",
    ],
)
def test_formal_governance_comment_blocks(comment: str) -> None:
    assert_blocked(
        replace(ready_snapshot(), comments=(comment,)),
        "FORMAL_GOVERNANCE_BLOCK",
    )


def test_tracker_marker_is_machine_readable() -> None:
    body = "Roadmap text\n<!-- roadmap-selected-task:621 -->\nMore text"
    assert parse_selected_task(body) == 621
    assert parse_selected_task("Roadmap without marker") is None


def test_parser_has_no_merge_or_execute_switch() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--repo",
            "GoLukeEnviro/trading-hub",
            "--pr",
            "622",
            "--expected-issue",
            "621",
            "--expected-head-sha",
            EXPECTED_HEAD,
        ]
    )
    assert not hasattr(args, "merge")
    assert not hasattr(args, "execute")


def test_snapshot_collects_linked_issue_through_graphql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_gh(arguments: tuple[str, ...]) -> dict[str, object]:
        if arguments[:2] == ("pr", "view"):
            assert "closingIssuesReferences" not in arguments[-1]
            return {
                "state": "OPEN",
                "isDraft": False,
                "headRefOid": EXPECTED_HEAD,
                "statusCheckRollup": [],
                "comments": [],
                "reviewDecision": "",
            }
        if arguments[:2] == ("issue", "view") and arguments[2] == "621":
            return {"state": "OPEN", "labels": []}
        if arguments[:2] == ("issue", "view"):
            return {"body": "<!-- roadmap-selected-task:621 -->"}
        return {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": []},
                        "closingIssuesReferences": {"nodes": [{"number": 621}]},
                    }
                }
            }
        }

    monkeypatch.setattr(merge_guard, "_run_gh_json", fake_gh)

    snapshot = merge_guard.collect_snapshot(
        repo="GoLukeEnviro/trading-hub",
        pr=622,
        expected_issue=621,
        tracker_issue=605,
    )

    assert snapshot.linked_issues == (621,)


def test_main_fails_closed_when_github_facts_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unavailable(**_kwargs: object) -> PullRequestSnapshot:
        raise RuntimeError("credentials")

    monkeypatch.setattr(
        merge_guard,
        "collect_snapshot",
        unavailable,
    )

    result = merge_guard.main(
        [
            "--repo",
            "GoLukeEnviro/trading-hub",
            "--pr",
            "622",
            "--expected-issue",
            "621",
            "--expected-head-sha",
            EXPECTED_HEAD,
        ]
    )

    payload = capsys.readouterr().out
    assert result == 3
    assert "GITHUB_FACT_COLLECTION_FAILED" in payload
    assert "credentials" not in payload


# ----------------------------------------------------------------------
# G0.2 governance_task_compatible (spec §7.4)
# ----------------------------------------------------------------------


def test_governance_task_compatible_blocks_blocked_phase() -> None:
    from orchestrator.scripts.roadmap_merge_guard import governance_task_compatible

    # A blocked phase with unmet dependencies must be incompatible.
    assert (
        governance_task_compatible(
            selected_phase="B",
            roadmap_status={"G0": "complete", "A": "pending", "B": "blocked"},
        )
        is False
    )


def test_governance_task_compatible_allows_in_progress() -> None:
    from orchestrator.scripts.roadmap_merge_guard import governance_task_compatible

    assert (
        governance_task_compatible(
            selected_phase="G0",
            roadmap_status={"G0": "in_progress"},
        )
        is True
    )


def test_governance_task_compatible_allows_pending_with_complete_deps() -> None:
    from orchestrator.scripts.roadmap_merge_guard import governance_task_compatible

    assert (
        governance_task_compatible(
            selected_phase="A",
            roadmap_status={"G0": "complete", "A": "pending"},
        )
        is True
    )


def test_governance_task_compatible_blocks_pending_with_incomplete_deps() -> None:
    from orchestrator.scripts.roadmap_merge_guard import governance_task_compatible

    assert (
        governance_task_compatible(
            selected_phase="A",
            roadmap_status={"G0": "in_progress", "A": "pending"},
        )
        is False
    )


# ----------------------------------------------------------------------
# #720 maintenance mode (fail-closed, independent of SI-v2 tracker)
# ----------------------------------------------------------------------


def maintenance_snapshot() -> PullRequestSnapshot:
    return replace(
        ready_snapshot(),
        tracker_selected_task=604,  # deliberately NOT the expected issue
        parent_issue=699,
        parent_issue_state="OPEN",
    )


def test_maintenance_mode_skips_tracker_mismatch() -> None:
    result = evaluate_merge_readiness(
        maintenance_snapshot(),
        expected_issue=621,
        expected_head_sha=EXPECTED_HEAD,
        maintenance_mode=True,
    )
    assert result.ready is True
    assert result.status == "READY_FOR_HUMAN_MERGE"
    assert result.blockers == ()


def test_roadmap_mode_still_blocks_tracker_mismatch() -> None:
    # Default (roadmap) mode must remain unchanged: tracker mismatch blocks.
    assert_blocked(maintenance_snapshot(), "TRACKER_TASK_MISMATCH")


def test_maintenance_mode_requires_parent_issue() -> None:
    snapshot = replace(maintenance_snapshot(), parent_issue=None)
    result = evaluate_merge_readiness(
        snapshot,
        expected_issue=621,
        expected_head_sha=EXPECTED_HEAD,
        maintenance_mode=True,
    )
    assert result.status == "BLOCKED_BY_GOVERNANCE"
    assert "MAINTENANCE_PARENT_MISSING" in result.blockers


def test_maintenance_mode_requires_open_parent() -> None:
    snapshot = replace(maintenance_snapshot(), parent_issue_state="CLOSED")
    result = evaluate_merge_readiness(
        snapshot,
        expected_issue=621,
        expected_head_sha=EXPECTED_HEAD,
        maintenance_mode=True,
    )
    assert result.status == "BLOCKED_BY_GOVERNANCE"
    assert "MAINTENANCE_PARENT_NOT_OPEN" in result.blockers


def test_maintenance_mode_keeps_other_gates_fail_closed() -> None:
    snapshot = replace(maintenance_snapshot(), head_sha="b" * 40)
    result = evaluate_merge_readiness(
        snapshot,
        expected_issue=621,
        expected_head_sha=EXPECTED_HEAD,
        maintenance_mode=True,
    )
    assert result.status == "BLOCKED_BY_GOVERNANCE"
    assert "HEAD_SHA_DRIFT" in result.blockers
    assert "TRACKER_TASK_MISMATCH" not in result.blockers


def test_parser_accepts_maintenance_mode_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--repo",
            "GoLukeEnviro/trading-hub",
            "--pr",
            "622",
            "--expected-issue",
            "621",
            "--expected-head-sha",
            EXPECTED_HEAD,
            "--maintenance-mode",
        ]
    )
    assert args.maintenance_mode is True
    assert not hasattr(args, "merge")
    assert not hasattr(args, "execute")


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("## Goal\n\nClose the gate.\n\nParent: #699\n", 699),
        ("## Parent\n\n- #699\n\n## Goal\n", 699),
        ("Parent maintenance issue: #699 remains open.\n", 699),
        ("No parent here.\n", None),
        ("", None),
    ],
)
def test_parse_parent_issue(body: str, expected: int | None) -> None:
    assert merge_guard.parse_parent_issue(body) == expected


def test_snapshot_collects_parent_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_gh(arguments: tuple[str, ...]) -> dict[str, object]:
        if arguments[:2] == ("pr", "view"):
            return {
                "state": "OPEN",
                "isDraft": False,
                "headRefOid": EXPECTED_HEAD,
                "statusCheckRollup": [],
                "comments": [],
                "reviewDecision": "",
            }
        if arguments[:2] == ("issue", "view") and arguments[2] == "621":
            return {"state": "OPEN", "labels": [], "body": "Parent: #699"}
        if arguments[:2] == ("issue", "view") and arguments[2] == "699":
            return {"state": "OPEN", "labels": []}
        if arguments[:2] == ("issue", "view"):
            return {"body": "<!-- roadmap-selected-task:621 -->"}
        return {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": []},
                        "closingIssuesReferences": {"nodes": [{"number": 621}]},
                    }
                }
            }
        }

    monkeypatch.setattr(merge_guard, "_run_gh_json", fake_gh)

    snapshot = merge_guard.collect_snapshot(
        repo="GoLukeEnviro/trading-hub",
        pr=622,
        expected_issue=621,
        tracker_issue=605,
    )

    assert snapshot.parent_issue == 699
    assert snapshot.parent_issue_state == "OPEN"
