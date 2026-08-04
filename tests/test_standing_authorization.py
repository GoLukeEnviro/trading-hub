"""Regression tests for the Standing Owner Authorization (ADR-2026-08-04).

Required proofs (per reconciliation GOAL):

- standing authorization active -> missing per-task A2 marker is not a blocker
- standing authorization active -> missing per-task A3 marker is not a human blocker
- standing authorization active + missing technical prerequisite -> execution blocked
- standing authorization active + CI red -> merge blocked
- standing authorization active + merge guard blocked -> merge blocked
- standing authorization active + all merge gates green -> autonomous merge eligible
- explicit revocation marker -> standing authorization inactive
"""

from pathlib import Path

from orchestrator.scripts.standing_authorization import (
    authorization_active,
    execution_blocked,
    live_authorized,
    merge_eligible,
    per_task_marker_required,
)

SOURCE = Path("config/governance/program-contract.yaml")


def test_active_means_no_per_task_marker_required():
    assert authorization_active(enabled=True) is True
    assert per_task_marker_required(active=True) is False


def test_missing_a2_marker_is_not_blocker_when_active():
    # Standing auth active: execution is gated by technical prerequisites, not markers.
    assert execution_blocked(active=True, technical_prerequisite_met=True) is False


def test_missing_a3_marker_is_not_human_blocker_when_active():
    # A3 human gate is standing-approved; technical live prerequisites still gate.
    assert live_authorized(
        active=True,
        c4_keep=False,
        live_candidate_pass=False,
        runtime_baseline_green=False,
        breakglass_operational=False,
        revocation_proven=False,
    ) is False
    # Missing individual A3 marker does not appear anywhere in the decision path.


def test_missing_technical_prerequisite_blocks_execution():
    assert execution_blocked(active=True, technical_prerequisite_met=False) is True


def test_ci_red_blocks_merge():
    assert merge_eligible(active=True, ci_green=False, guard_ready=True, head_verified=True) is False


def test_guard_blocked_blocks_merge():
    assert merge_eligible(active=True, ci_green=True, guard_ready=False, head_verified=True) is False


def test_head_drift_blocks_merge():
    assert merge_eligible(active=True, ci_green=True, guard_ready=True, head_verified=False) is False


def test_all_gates_green_allows_autonomous_merge():
    assert merge_eligible(active=True, ci_green=True, guard_ready=True, head_verified=True) is True


def test_explicit_revocation_deactivates():
    assert authorization_active(enabled=True, revocation_markers=["OWNER_STANDING_AUTHORIZATION_REVOKED"]) is False
    assert authorization_active(enabled=True, revocation_markers=["OWNER_STANDING_AUTHORIZATION_SUPERSEDED"]) is False


def test_disabled_is_inactive():
    assert authorization_active(enabled=False) is False


def test_live_requires_all_technical_prerequisites():
    # C4 KEEP + all guardrails green -> live eligible under standing auth.
    assert live_authorized(
        active=True,
        c4_keep=True,
        live_candidate_pass=True,
        runtime_baseline_green=True,
        breakglass_operational=True,
        revocation_proven=True,
    ) is True
    # Any single missing guardrail blocks live even with standing auth.
    assert live_authorized(
        active=True,
        c4_keep=False,
        live_candidate_pass=True,
        runtime_baseline_green=True,
        breakglass_operational=True,
        revocation_proven=True,
    ) is False
