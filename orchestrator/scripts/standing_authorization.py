"""Standing Owner Authorization v1 — pure decision logic (ADR-2026-08-04).

Source: Issue #605 comment 5179703046 (OWNER_STANDING_AUTHORIZATION_V1),
GitHub user GoLukeEnviro (Luke).

The standing authorization replaces recurring per-task human approval markers.
It never replaces technical gates (CI, merge guard, writer lock, branch
protection, snapshot, canary, allowlist, rollback, audit, measurement,
RiskGuard, kill switch, C4 KEEP, runtime baseline, breakglass, revocation).
"""

from __future__ import annotations

REVOCATION_MARKERS = frozenset(
    {
        "OWNER_STANDING_AUTHORIZATION_REVOKED",
        "OWNER_STANDING_AUTHORIZATION_SUPERSEDED",
    }
)


def authorization_active(
    *,
    enabled: bool,
    revocation_markers: list[str] | None = None,
) -> bool:
    """True while the standing authorization is enabled and not revoked.

    Only an explicit newer owner revocation/superseding marker deactivates it.
    """
    if not enabled:
        return False
    markers = {m.strip().upper() for m in (revocation_markers or [])}
    return not (markers & REVOCATION_MARKERS)


def per_task_marker_required(*, active: bool) -> bool:
    """Missing per-task human markers are NOT blockers while standing auth is active."""
    return not active


def merge_eligible(
    *,
    active: bool,
    ci_green: bool,
    guard_ready: bool,
    head_verified: bool,
) -> bool:
    """Autonomous merge eligibility: standing auth + ALL technical gates green."""
    return active and ci_green and guard_ready and head_verified


def execution_blocked(
    *,
    active: bool,
    technical_prerequisite_met: bool,
) -> bool:
    """Technical prerequisites still gate execution even with standing auth."""
    return not (active and technical_prerequisite_met)


def live_authorized(
    *,
    active: bool,
    c4_keep: bool,
    live_candidate_pass: bool,
    runtime_baseline_green: bool,
    breakglass_operational: bool,
    revocation_proven: bool,
) -> bool:
    """A3 live: standing auth AND every live guardrail green (C4 KEEP etc.)."""
    return (
        active
        and c4_keep
        and live_candidate_pass
        and runtime_baseline_green
        and breakglass_operational
        and revocation_proven
    )
