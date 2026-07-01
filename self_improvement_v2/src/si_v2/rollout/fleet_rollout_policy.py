"""SI-v2 Phase 9A — Controlled Fleet Rollout Policy.

Read-only policy evaluator that consumes enriched Measurement Watcher
decision packs, validates KEEP + statistical evidence, blocks HARD
conflicts, selects eligible fleet target bots, and writes a rollout
policy artifact.

This module is **read-only**. It does NOT:
- Execute any runtime mutation (restart, Docker, compose)
- Apply overlays to fleet bots
- Enable schedulers or watchers
- Execute rollback
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANARY_BOT: str = "freqtrade-freqforge-canary"
CONTROL_BOT: str = "freqtrade-freqforge"
REGIME_HYBRID_BOT: str = "freqtrade-regime-hybrid"
FREQAI_REBEL_BOT: str = "freqai-rebel"

GRADE_ORDER: dict[str, int] = {
    "STRONG": 4,
    "MODERATE": 3,
    "WEAK": 2,
    "INSUFFICIENT": 1,
    "BLOCKED": 0,
}

DEFAULT_FLEET_BOTS: tuple[FleetBot, ...] = ()

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FleetBot:
    """A single bot in the fleet."""

    bot_id: str
    role: Literal["control", "canary", "experimental", "freqai"]
    dry_run: bool
    allow_rollout_target: bool


@dataclass(frozen=True)
class FleetRolloutPolicyInput:
    """All inputs for the fleet rollout policy evaluator."""

    decision_pack_path: str
    """Path to the Measurement Watcher decision pack JSON file."""

    fleet_bots: tuple[FleetBot, ...]
    """Available fleet bots with roles and flags."""

    allowed_target_bots: tuple[str, ...]
    """Bot IDs that are explicitly allowed as promotion targets."""

    min_stat_evidence_grade: Literal["STRONG", "MODERATE", "WEAK"] = "MODERATE"
    """Minimum statistical evidence grade required for promotion."""

    require_statistical_evidence: bool = True
    """If True, statistical_evidence must be present and STAT_KEEP."""

    allow_control_promotion: bool = False
    """If True, the control bot can be a promotion target."""

    allow_experimental_promotion: bool = True
    """If True, experimental bots can be promotion targets."""

    max_targets: int = 1
    """Maximum number of targets for a single rollout."""


@dataclass(frozen=True)
class FleetRolloutPolicyResult:
    """Structured result from the fleet rollout policy evaluator."""

    status: Literal[
        "PROMOTION_ELIGIBLE",
        "PROMOTION_NOT_ELIGIBLE",
        "PROMOTION_BLOCKED",
        "PROMOTION_EXTEND_MEASUREMENT",
    ]
    change_id: str
    candidate_id: str
    source_bot: str
    simple_decision: str
    stat_recommendation: str | None
    stat_grade: str | None
    selected_targets: tuple[str, ...]
    blocked_reasons: tuple[str, ...]
    rollout_policy_path: str
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "fleet_rollout_policy_decision",
            "status": self.status,
            "change_id": self.change_id,
            "candidate_id": self.candidate_id,
            "source_bot": self.source_bot,
            "simple_decision": self.simple_decision,
            "stat_recommendation": self.stat_recommendation,
            "stat_grade": self.stat_grade,
            "selected_targets": list(self.selected_targets),
            "blocked_reasons": list(self.blocked_reasons),
            "rollout_policy_path": self.rollout_policy_path,
            "next_step": self.next_step,
        }


# ---------------------------------------------------------------------------
# Grade comparison helper
# ---------------------------------------------------------------------------


def _grade_meets_minimum(
    actual_grade: str | None,
    min_grade: str,
) -> tuple[bool, str | None]:
    """Check if ``actual_grade`` meets or exceeds ``min_grade``.

    Grade strength order: STRONG > MODERATE > WEAK > INSUFFICIENT > BLOCKED.

    Returns (meets, reason_if_not).
    """
    if actual_grade is None:
        return False, "stat_grade_missing: statistical evidence grade is None"

    actual = GRADE_ORDER.get(actual_grade.upper(), -1)
    minimum = GRADE_ORDER.get(min_grade.upper(), -1)

    if actual < 0:
        return False, f"unknown_stat_grade: {actual_grade!r}"

    if actual >= minimum:
        return True, None

    return (
        False,
        f"stat_grade_below_minimum: {actual_grade} < {min_grade}",
    )


# ---------------------------------------------------------------------------
# Decision pack reader
# ---------------------------------------------------------------------------


def _read_decision_pack(path: str) -> dict[str, object] | None:
    """Read and parse a decision pack JSON file.

    Returns None if the file cannot be read or parsed.
    """
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Target selector
# ---------------------------------------------------------------------------


def _select_targets(
    fleet_bots: tuple[FleetBot, ...],
    allowed_target_bots: tuple[str, ...],
    *,
    max_targets: int,
    allow_control: bool,
    allow_experimental: bool,
) -> tuple[list[str], tuple[str, ...]]:
    """Select eligible target bots from the fleet.

    Returns (selected_targets, blocked_reasons).
    """
    selected: list[str] = []
    reasons: list[str] = []

    # Filter eligible bots
    candidates: list[FleetBot] = []
    for bot in fleet_bots:
        # Canary is never a target
        if bot.role == "canary":
            continue
        # Must be dry-run
        if not bot.dry_run:
            reasons.append(
                f"not_dry_run: {bot.bot_id} is not dry-run"
            )
            continue
        # Must allow rollout
        if not bot.allow_rollout_target:
            reasons.append(
                f"not_allowed_target: {bot.bot_id} has allow_rollout_target=False"
            )
            continue
        # Must be in allowed list
        if bot.bot_id not in allowed_target_bots:
            reasons.append(
                f"not_in_allowed_list: {bot.bot_id} not in "
                f"allowed_target_bots={list(allowed_target_bots)}"
            )
            continue
        # Control only if allowed
        if bot.role == "control" and not allow_control:
            reasons.append(
                f"control_not_allowed: {bot.bot_id} requires "
                f"allow_control_promotion=True"
            )
            continue
        # Experimental only if allowed
        if bot.role in ("experimental", "freqai") and not allow_experimental:
            reasons.append(
                f"experimental_not_allowed: {bot.bot_id} requires "
                f"allow_experimental_promotion=True"
            )
            continue

        candidates.append(bot)

    # Sort: control first (if allowed), then regime-hybrid, then freqai-rebel
    priority = {CONTROL_BOT: 0, REGIME_HYBRID_BOT: 1, FREQAI_REBEL_BOT: 2}
    candidates.sort(key=lambda b: priority.get(b.bot_id, 99))

    # Select up to max_targets
    for bot in candidates[:max_targets]:
        selected.append(bot.bot_id)

    if not selected:
        reasons.append("no_eligible_targets: no bots passed all target filters")
        return [], tuple(reasons)

    return selected, tuple(reasons)


# ---------------------------------------------------------------------------
# Artifact writer
# ---------------------------------------------------------------------------


def _write_rollout_policy_artifact(
    *,
    change_id: str,
    candidate_id: str,
    source_bot: str,
    status: str,
    selected_targets: tuple[str, ...],
    simple_decision: str,
    decision_pack: dict[str, object],
    allowed_target_bots: tuple[str, ...],
    blocked_reasons: tuple[str, ...],
    rollout_policy_dir: Path,
    now_utc: str,
) -> str:
    """Write a rollout policy artifact JSON file.

    Returns the path to the written file.
    """
    rollout_policy_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "event": "fleet_rollout_policy_decision",
        "change_id": change_id,
        "candidate_id": candidate_id,
        "source_bot": source_bot,
        "status": status,
        "selected_targets": list(selected_targets),
        "simple_decision": simple_decision,
        "statistical_evidence": decision_pack.get("statistical_evidence"),
        "statistical_conflict": decision_pack.get("statistical_conflict"),
        "allowed_target_bots": list(allowed_target_bots),
        "blocked_reasons": list(blocked_reasons),
        "runtime_mutation": "NONE",
        "next_required_component": "fleet_rollout_artifact_planner",
        "created_at_utc": now_utc,
    }
    filename = f"rollout_policy_{change_id[:24]}.json"
    path = rollout_policy_dir / filename
    tmp = path.with_suffix(f".json.tmp.{abs(hash(now_utc))}")
    tmp.write_text(json.dumps(artifact, indent=2))
    tmp.replace(path)
    return str(path)


# ---------------------------------------------------------------------------
# Main policy evaluator
# ---------------------------------------------------------------------------


def evaluate_fleet_rollout_policy(
    input_: FleetRolloutPolicyInput,
    *,
    rollout_policy_dir: Path | None = None,
    now_utc: str | None = None,
) -> FleetRolloutPolicyResult:
    """Evaluate fleet rollout policy from a Measurement Watcher decision pack.

    This function is PURE and READ-ONLY. It does not:
    - Execute runtime actions
    - Apply overlays
    - Touch Docker or Docker Compose
    - Enable schedulers

    Args:
        input_: All inputs for policy evaluation.
        rollout_policy_dir: Override for artifact output directory.
        now_utc: Override for current UTC time (testing).

    Returns:
        ``FleetRolloutPolicyResult`` with eligibility and targets.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    # Resolved after reading the pack
    resolved_dir = rollout_policy_dir or Path("var/si_v2/fleet_rollout_policy")

    blocked: list[str] = []
    change_id = ""
    candidate_id = ""
    source_bot = ""
    simple_decision = ""
    stat_rec: str | None = None
    stat_grade: str | None = None
    selected_targets: tuple[str, ...] = ()

    # ------------------------------------------------------------------
    # Step 1: Read decision pack
    # ------------------------------------------------------------------

    pack = _read_decision_pack(input_.decision_pack_path)

    if pack is None:
        return FleetRolloutPolicyResult(
            status="PROMOTION_BLOCKED",
            change_id="",
            candidate_id="",
            source_bot="",
            simple_decision="",
            stat_recommendation=None,
            stat_grade=None,
            selected_targets=(),
            blocked_reasons=(
                f"decision_pack_not_readable: "
                f"{input_.decision_pack_path}",
            ),
            rollout_policy_path="",
            next_step="Provide a valid decision pack path and retry.",
        )

    change_id = str(pack.get("change_id", ""))
    candidate_id = str(pack.get("candidate_id", ""))
    source_bot = str(pack.get("target_bot", ""))
    simple_decision = str(pack.get("decision", ""))

    # ------------------------------------------------------------------
    # Step 2: Validate decision pack structure
    # ------------------------------------------------------------------

    if not change_id:
        blocked.append("change_id_missing: decision pack has no change_id")
    if not candidate_id:
        blocked.append(
            "candidate_id_missing: decision pack has no candidate_id"
        )

    event = pack.get("event")
    if event != "autonomous_measurement_decision":
        blocked.append(
            f"unexpected_event: {event!r} != autonomous_measurement_decision"
        )

    if simple_decision == "ROLLBACK_CANARY_OVERLAY":
        return FleetRolloutPolicyResult(
            status="PROMOTION_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            source_bot=source_bot,
            simple_decision=simple_decision,
            stat_recommendation=None,
            stat_grade=None,
            selected_targets=(),
            blocked_reasons=(
                "rollback_decision: decision pack says ROLLBACK — "
                "promotion not possible",
            ),
            rollout_policy_path="",
            next_step="Resolve the rollback before considering promotion.",
        )

    if simple_decision == "EXTEND_MEASUREMENT":
        return FleetRolloutPolicyResult(
            status="PROMOTION_EXTEND_MEASUREMENT",
            change_id=change_id,
            candidate_id=candidate_id,
            source_bot=source_bot,
            simple_decision=simple_decision,
            stat_recommendation=None,
            stat_grade=None,
            selected_targets=(),
            blocked_reasons=(),
            rollout_policy_path="",
            next_step="Extend measurement before considering promotion.",
        )

    if simple_decision != "KEEP_CANARY_OVERLAY":
        blocked.append(
            f"unexpected_decision: {simple_decision!r} != "
            f"KEEP_CANARY_OVERLAY"
        )

    pack_status = pack.get("status")
    if pack_status != "FINAL_DECISION_EMITTED":
        blocked.append(
            f"unexpected_pack_status: {pack_status!r} != "
            f"FINAL_DECISION_EMITTED"
        )

    if source_bot != CANARY_BOT:
        blocked.append(
            f"source_not_canary: {source_bot!r} != {CANARY_BOT!r}"
        )

    runtime_mutation = pack.get("runtime_mutation")
    if runtime_mutation != "NONE":
        blocked.append(
            f"runtime_mutation_not_none: {runtime_mutation!r}"
        )

    # ------------------------------------------------------------------
    # Step 3: Statistical evidence validation
    # ------------------------------------------------------------------

    stat_conflict = pack.get("statistical_conflict")
    if isinstance(stat_conflict, dict):
        conflict_severity = str(stat_conflict.get("severity", "NONE"))
        conflict_has = bool(stat_conflict.get("has_conflict", False))
        if conflict_severity == "HARD" and conflict_has:
            blocked.append(
                "hard_statistical_conflict: promotion blocked by "
                "HARD conflict between simple and stat decisions"
            )
    elif input_.require_statistical_evidence:
        blocked.append(
            "statistical_conflict_missing: required for promotion"
        )

    stat_ev = pack.get("statistical_evidence")
    if input_.require_statistical_evidence:
        if stat_ev is None or not isinstance(stat_ev, dict):
            blocked.append(
                "statistical_evidence_missing: required when "
                "require_statistical_evidence=True"
            )
        else:
            stat_status = str(stat_ev.get("status", ""))
            if stat_status != "STAT_READY":
                blocked.append(
                    f"stat_status_not_ready: {stat_status!r} != STAT_READY"
                )

            stat_rec_raw = stat_ev.get("recommendation")
            stat_rec = str(stat_rec_raw) if stat_rec_raw is not None else None
            if stat_rec != "STAT_KEEP":
                blocked.append(
                    f"stat_recommendation_not_keep: {stat_rec!r} != STAT_KEEP"
                )

            stat_grade_raw = stat_ev.get("evidence_grade")
            stat_grade = str(stat_grade_raw) if stat_grade_raw is not None else None

            grade_ok, grade_reason = _grade_meets_minimum(
                stat_grade, input_.min_stat_evidence_grade,
            )
            if not grade_ok and grade_reason:
                blocked.append(grade_reason)
    else:
        # Not required — grab stat info if available
        if isinstance(stat_ev, dict):
            rec_raw = stat_ev.get("recommendation")
            stat_rec = str(rec_raw) if rec_raw is not None else None
            grade_raw = stat_ev.get("evidence_grade")
            stat_grade = str(grade_raw) if grade_raw is not None else None

    # ------------------------------------------------------------------
    # Step 4: Check for blockers before target selection
    # ------------------------------------------------------------------

    if blocked:
        return FleetRolloutPolicyResult(
            status="PROMOTION_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            source_bot=source_bot,
            simple_decision=simple_decision,
            stat_recommendation=stat_rec,
            stat_grade=stat_grade,
            selected_targets=(),
            blocked_reasons=tuple(blocked),
            rollout_policy_path="",
            next_step="Review blocked reasons and fix before retrying promotion evaluation.",
        )

    # ------------------------------------------------------------------
    # Step 5: Target selection
    # ------------------------------------------------------------------

    fleet_targets, target_reasons = _select_targets(
        fleet_bots=input_.fleet_bots,
        allowed_target_bots=input_.allowed_target_bots,
        max_targets=input_.max_targets,
        allow_control=input_.allow_control_promotion,
        allow_experimental=input_.allow_experimental_promotion,
    )

    if not fleet_targets:
        return FleetRolloutPolicyResult(
            status="PROMOTION_NOT_ELIGIBLE",
            change_id=change_id,
            candidate_id=candidate_id,
            source_bot=source_bot,
            simple_decision=simple_decision,
            stat_recommendation=stat_rec,
            stat_grade=stat_grade,
            selected_targets=(),
            blocked_reasons=target_reasons,
            rollout_policy_path="",
            next_step="No eligible target bots available. Review fleet configuration and allowlists.",
        )

    selected_targets = tuple(fleet_targets)

    # ------------------------------------------------------------------
    # Step 6: Write rollout policy artifact
    # ------------------------------------------------------------------

    try:
        artifact_path = _write_rollout_policy_artifact(
            change_id=change_id,
            candidate_id=candidate_id,
            source_bot=source_bot,
            status="PROMOTION_ELIGIBLE",
            selected_targets=selected_targets,
            simple_decision=simple_decision,
            decision_pack=pack,
            allowed_target_bots=input_.allowed_target_bots,
            blocked_reasons=(),
            rollout_policy_dir=resolved_dir / change_id[:24],
            now_utc=resolved_now,
        )
    except OSError as e:
        return FleetRolloutPolicyResult(
            status="PROMOTION_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            source_bot=source_bot,
            simple_decision=simple_decision,
            stat_recommendation=stat_rec,
            stat_grade=stat_grade,
            selected_targets=(),
            blocked_reasons=(f"artifact_write_error: {e}",),
            rollout_policy_path="",
            next_step="Fix artifact write path and retry.",
        )

    return FleetRolloutPolicyResult(
        status="PROMOTION_ELIGIBLE",
        change_id=change_id,
        candidate_id=candidate_id,
        source_bot=source_bot,
        simple_decision=simple_decision,
        stat_recommendation=stat_rec,
        stat_grade=stat_grade,
        selected_targets=selected_targets,
        blocked_reasons=(),
        rollout_policy_path=artifact_path,
        next_step=(
            f"PROMOTION_ELIGIBLE for candidate {candidate_id}. "
            f"Selected targets: {list(selected_targets)}. "
            f"Proceed to Phase 9B Fleet Rollout Artifact Planner."
        ),
    )
