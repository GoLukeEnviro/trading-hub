"""SI-v2 Phase 10.6 — Next Iteration Selector.

Selects the next qualified candidate after a fleet measurement completes.
Consumes completed A4 fleet measurement decision packs (KEEP or ROLLBACK)
and A5 rollback executor results, then emits a next-iteration selection plan.

This module is **read-only and plan-only**. It does NOT:
- Execute any runtime mutation (restart, Docker, compose)
- Apply overlays to fleet bots
- Enable schedulers or watchers
- Execute rollback
- Execute next iteration
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

DEFAULT_SELECTOR_OUTPUT_DIR: str = "var/si_v2/next_iteration_selector"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompletedDecisionPack:
    """A completed fleet measurement decision pack.

    Attributes:
        event: Must be post_fleet_measurement_decision.
        change_id: Change ID from the decision pack.
        candidate_id: Candidate ID from the decision pack.
        target_bot: Bot that was measured.
        decision: KEEP_FLEET_OVERLAY or ROLLBACK_FLEET_OVERLAY.
        status: Must be FINAL_DECISION_EMITTED.
        created_at_utc: When the decision was emitted.
        runtime_mutation: Must be NONE.
    """

    event: str
    change_id: str
    candidate_id: str
    target_bot: str
    decision: Literal["KEEP_FLEET_OVERLAY", "ROLLBACK_FLEET_OVERLAY", "EXTEND_MEASUREMENT"]
    status: str
    created_at_utc: str
    runtime_mutation: str

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CompletedDecisionPack:
        return cls(
            event=str(data.get("event", "")),
            change_id=str(data.get("change_id", "")),
            candidate_id=str(data.get("candidate_id", "")),
            target_bot=str(data.get("target_bot", "")),
            decision=str(data.get("decision", "")),  # type: ignore[assignment]
            status=str(data.get("status", "")),
            created_at_utc=str(data.get("created_at_utc", "")),
            runtime_mutation=str(data.get("runtime_mutation", "")),
        )


@dataclass(frozen=True)
class CompletedRollbackRecord:
    """A completed rollback executor result.

    Attributes:
        event: Must be dry_run_rollback_executor_result.
        change_id: Change ID from the rollback.
        candidate_id: Candidate ID from the rollback.
        target_bot: Bot that was rolled back.
        status: DRY_RUN_ROLLBACK_GREEN or DRY_RUN_ROLLBACK_YELLOW.
        rollback_audit_path: Path to the rollback audit.
        rollback_effect_proof_path: Path to the rollback effect proof.
        post_rollback_measurement_start_path: Path to post-rollback measurement.
        runtime_mutation: Must be NONE.
    """

    event: str
    change_id: str
    candidate_id: str
    target_bot: str
    status: Literal["DRY_RUN_ROLLBACK_GREEN", "DRY_RUN_ROLLBACK_YELLOW"]
    rollback_audit_path: str
    rollback_effect_proof_path: str
    post_rollback_measurement_start_path: str
    runtime_mutation: str

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CompletedRollbackRecord:
        return cls(
            event=str(data.get("event", "")),
            change_id=str(data.get("change_id", "")),
            candidate_id=str(data.get("candidate_id", "")),
            target_bot=str(data.get("target_bot", "")),
            status=str(data.get("status", "")),  # type: ignore[assignment]
            rollback_audit_path=str(data.get("rollback_audit_path", "")),
            rollback_effect_proof_path=str(data.get("rollback_effect_proof_path", "")),
            post_rollback_measurement_start_path=str(
                data.get("post_rollback_measurement_start_path", "")
            ),
            runtime_mutation=str(data.get("runtime_mutation", "")),
        )


@dataclass(frozen=True)
class NextIterationSelectorInput:
    """All inputs for the next iteration selector.

    Attributes:
        decision_pack_path: Path to a completed A4 fleet measurement
            decision pack (KEEP or ROLLBACK).
        rollback_result_path: Path to a completed A5 rollback executor
            result. Required when decision is ROLLBACK_FLEET_OVERLAY.
        active_measurement_candidate_id: If set, blocks selection because
            a measurement is still open.
        previous_candidate_ids: Candidate IDs already selected in prior
            iterations. Used to avoid repeated identical candidates.
        fleet_bot_ids: All available fleet bot IDs for consideration.
    """

    decision_pack_path: str
    rollback_result_path: str | None = None
    active_measurement_candidate_id: str | None = None
    previous_candidate_ids: tuple[str, ...] = ()
    fleet_bot_ids: tuple[str, ...] = (
        "freqtrade-freqforge",
        "freqtrade-freqforge-canary",
        "freqtrade-regime-hybrid",
        "freqai-rebel",
    )


@dataclass(frozen=True)
class NextIterationSelectionPlan:
    """A plan for the next iteration.

    Attributes:
        status: Overall selection status.
        change_id: Change ID from the source decision pack.
        candidate_id: Candidate ID from the source decision pack.
        source_decision: KEEP or ROLLBACK from the source pack.
        next_candidate_id: The selected next candidate ID (empty if blocked).
        next_target_bot: The selected next target bot (empty if blocked).
        next_reason: Why this candidate was selected.
        blocked_reasons: Reasons selection was blocked.
        selection_plan_path: Path to the written selection plan artifact.
        next_step: Suggested next action.
    """

    status: Literal[
        "NEXT_ITERATION_SELECTED",
        "NEXT_ITERATION_BLOCKED",
        "NEXT_ITERATION_DEFERRED",
    ]
    change_id: str
    candidate_id: str
    source_decision: str
    next_candidate_id: str
    next_target_bot: str
    next_reason: str
    blocked_reasons: tuple[str, ...]
    selection_plan_path: str
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "next_iteration_selection_plan",
            "status": self.status,
            "change_id": self.change_id,
            "candidate_id": self.candidate_id,
            "source_decision": self.source_decision,
            "next_candidate_id": self.next_candidate_id,
            "next_target_bot": self.next_target_bot,
            "next_reason": self.next_reason,
            "blocked_reasons": list(self.blocked_reasons),
            "selection_plan_path": self.selection_plan_path,
            "next_step": self.next_step,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
    """Write JSON atomically via temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{abs(hash(str(data)))}")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


def _read_json(path: str) -> dict[str, object] | None:
    """Read and parse a JSON file. Returns None on failure."""
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
# Decision pack reader
# ---------------------------------------------------------------------------


def _read_decision_pack(
    path: str,
) -> tuple[CompletedDecisionPack | None, tuple[str, ...]]:
    """Read and validate a completed decision pack.

    Returns (pack, reasons).
    """
    reasons: list[str] = []
    data = _read_json(path)
    if data is None:
        return None, (f"decision_pack_not_readable: {path}",)

    pack = CompletedDecisionPack.from_dict(data)

    if pack.event != "post_fleet_measurement_decision":
        reasons.append(
            f"unexpected_event: {pack.event!r} != post_fleet_measurement_decision"
        )
    if pack.status != "FINAL_DECISION_EMITTED":
        reasons.append(
            f"unexpected_status: {pack.status!r} != FINAL_DECISION_EMITTED"
        )
    if pack.runtime_mutation != "NONE":
        reasons.append(
            f"runtime_mutation_not_none: {pack.runtime_mutation!r}"
        )
    if pack.decision not in ("KEEP_FLEET_OVERLAY", "ROLLBACK_FLEET_OVERLAY", "EXTEND_MEASUREMENT"):
        reasons.append(
            f"unexpected_decision: {pack.decision!r}"
        )

    if reasons:
        return None, tuple(reasons)
    return pack, ()


# ---------------------------------------------------------------------------
# Rollback result reader
# ---------------------------------------------------------------------------


def _read_rollback_result(
    path: str,
) -> tuple[CompletedRollbackRecord | None, tuple[str, ...]]:
    """Read and validate a completed rollback executor result.

    Returns (record, reasons).
    """
    reasons: list[str] = []
    data = _read_json(path)
    if data is None:
        return None, (f"rollback_result_not_readable: {path}",)

    record = CompletedRollbackRecord.from_dict(data)

    if record.event != "dry_run_rollback_executor_result":
        reasons.append(
            f"unexpected_event: {record.event!r} != "
            f"dry_run_rollback_executor_result"
        )
    if record.status not in ("DRY_RUN_ROLLBACK_GREEN", "DRY_RUN_ROLLBACK_YELLOW"):
        reasons.append(
            f"unexpected_status: {record.status!r} not in "
            f"(DRY_RUN_ROLLBACK_GREEN, DRY_RUN_ROLLBACK_YELLOW)"
        )
    if record.runtime_mutation != "NONE":
        reasons.append(
            f"runtime_mutation_not_none: {record.runtime_mutation!r}"
        )

    if reasons:
        return None, tuple(reasons)
    return record, ()


# ---------------------------------------------------------------------------
# Main selector
# ---------------------------------------------------------------------------


def run_next_iteration_selector(
    input_: NextIterationSelectorInput,
    *,
    selector_output_dir: Path | None = None,
    now_utc: str | None = None,
) -> NextIterationSelectionPlan:
    """Select the next qualified iteration after fleet measurement completes.

    Args:
        input_: All inputs for the selector.
        selector_output_dir: Override for selector output directory.
        now_utc: Override for current UTC time (testing).

    Returns:
        NextIterationSelectionPlan with selection status and plan.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_dir = selector_output_dir or Path(DEFAULT_SELECTOR_OUTPUT_DIR)

    # ------------------------------------------------------------------
    # Step 1: Read and validate decision pack
    # ------------------------------------------------------------------

    pack, pack_reasons = _read_decision_pack(input_.decision_pack_path)
    if pack is None:
        return _build_blocked_result(
            change_id="",
            candidate_id="",
            source_decision="",
            blocked_reasons=pack_reasons,
            resolved_dir=resolved_dir,
            resolved_now=resolved_now,
            next_step="Provide a valid completed decision pack path and retry.",
        )

    change_id = pack.change_id
    candidate_id = pack.candidate_id
    source_decision = pack.decision

    # ------------------------------------------------------------------
    # Step 2: Block EXTEND_MEASUREMENT — measurement still open
    # ------------------------------------------------------------------

    if pack.decision == "EXTEND_MEASUREMENT":
        return _build_blocked_result(
            change_id=change_id,
            candidate_id=candidate_id,
            source_decision=source_decision,
            blocked_reasons=(
                "extend_measurement_active: measurement is still open — "
                "cannot select next iteration until measurement completes",
            ),
            resolved_dir=resolved_dir,
            resolved_now=resolved_now,
            next_step=(
                "Wait for measurement to complete (KEEP or ROLLBACK). "
                "Re-check when measurement watcher emits a final decision."
            ),
        )

    # ------------------------------------------------------------------
    # Step 3: Block if active measurement window is open
    # ------------------------------------------------------------------

    if input_.active_measurement_candidate_id is not None:
        return _build_blocked_result(
            change_id=change_id,
            candidate_id=candidate_id,
            source_decision=source_decision,
            blocked_reasons=(
                f"active_measurement_window: "
                f"{input_.active_measurement_candidate_id!r} is still "
                f"being measured — cannot select next iteration",
            ),
            resolved_dir=resolved_dir,
            resolved_now=resolved_now,
            next_step=(
                f"Wait for measurement of "
                f"{input_.active_measurement_candidate_id!r} to complete."
            ),
        )

    # ------------------------------------------------------------------
    # Step 4: If ROLLBACK, validate rollback is completed
    # ------------------------------------------------------------------

    if pack.decision == "ROLLBACK_FLEET_OVERLAY":
        if input_.rollback_result_path is None:
            return _build_blocked_result(
                change_id=change_id,
                candidate_id=candidate_id,
                source_decision=source_decision,
                blocked_reasons=(
                    "rollback_required: decision is ROLLBACK_FLEET_OVERLAY "
                    "but no rollback_result_path provided",
                ),
                resolved_dir=resolved_dir,
                resolved_now=resolved_now,
                next_step=(
                    "Execute rollback via Phase 10.5 first, then "
                    "provide the rollback result path."
                ),
            )

        rollback, rollback_reasons = _read_rollback_result(
            input_.rollback_result_path,
        )
        if rollback is None:
            return _build_blocked_result(
                change_id=change_id,
                candidate_id=candidate_id,
                source_decision=source_decision,
                blocked_reasons=rollback_reasons,
                resolved_dir=resolved_dir,
                resolved_now=resolved_now,
                next_step=(
                    "Provide a valid rollback executor result path and retry."
                ),
            )

        if rollback.status == "DRY_RUN_ROLLBACK_YELLOW":
            return _build_blocked_result(
                change_id=change_id,
                candidate_id=candidate_id,
                source_decision=source_decision,
                blocked_reasons=(
                    f"rollback_yellow: rollback completed with YELLOW "
                    f"status for {rollback.target_bot} — "
                    f"review before next iteration",
                ),
                resolved_dir=resolved_dir,
                resolved_now=resolved_now,
                next_step=(
                    "Review rollback YELLOW status and re-run rollback "
                    "if needed before selecting next iteration."
                ),
            )

    # ------------------------------------------------------------------
    # Step 5: Avoid repeated identical candidates
    # ------------------------------------------------------------------

    if candidate_id in input_.previous_candidate_ids:
        return _build_blocked_result(
            change_id=change_id,
            candidate_id=candidate_id,
            source_decision=source_decision,
            blocked_reasons=(
                f"duplicate_candidate: {candidate_id!r} was already "
                f"selected in a prior iteration",
            ),
            resolved_dir=resolved_dir,
            resolved_now=resolved_now,
            next_step=(
                "Select a different candidate or wait for new evidence "
                "that changes the candidate's parameters."
            ),
        )

    # ------------------------------------------------------------------
    # Step 6: Select next candidate
    # ------------------------------------------------------------------

    # The next candidate is derived from the completed iteration.
    # For KEEP: the overlay was successful, consider the next candidate
    #   from the fleet (e.g., regime-hybrid or freqai-rebel).
    # For ROLLBACK: the overlay was rolled back, consider the next
    #   candidate from the fleet.

    # Determine the next target bot (non-canary, non-control)
    next_target_bot = _select_next_target(
        pack.target_bot,
        input_.fleet_bot_ids,
    )

    next_candidate_id = f"next-iteration-{change_id[:16]}-{next_target_bot}"

    if pack.decision == "KEEP_FLEET_OVERLAY":
        next_reason = (
            f"KEEP_FLEET_OVERLAY completed for {pack.target_bot}. "
            f"Overlay proven safe. Selecting next candidate for "
            f"{next_target_bot}."
        )
    else:
        next_reason = (
            f"ROLLBACK_FLEET_OVERLAY completed for {pack.target_bot}. "
            f"Overlay rolled back. Selecting next candidate for "
            f"{next_target_bot}."
        )

    # ------------------------------------------------------------------
    # Step 7: Write selection plan
    # ------------------------------------------------------------------

    plan: dict[str, object] = {
        "event": "next_iteration_selection_plan",
        "status": "NEXT_ITERATION_SELECTED",
        "change_id": change_id,
        "candidate_id": candidate_id,
        "source_decision": source_decision,
        "next_candidate_id": next_candidate_id,
        "next_target_bot": next_target_bot,
        "next_reason": next_reason,
        "blocked_reasons": [],
        "created_at_utc": resolved_now,
        "runtime_mutation": "NONE",
        "next_required_component": "candidate_pipeline_or_autonomous_dry_run_executor",
    }
    plan_path = resolved_dir / f"{change_id[:24]}_selection_plan.json"
    _atomic_write_json(plan_path, plan)

    return NextIterationSelectionPlan(
        status="NEXT_ITERATION_SELECTED",
        change_id=change_id,
        candidate_id=candidate_id,
        source_decision=source_decision,
        next_candidate_id=next_candidate_id,
        next_target_bot=next_target_bot,
        next_reason=next_reason,
        blocked_reasons=(),
        selection_plan_path=str(plan_path),
        next_step=(
            f"Next iteration selected: {next_candidate_id} on "
            f"{next_target_bot}. Feed into candidate pipeline for "
            f"autonomous dry-run apply."
        ),
    )


# ---------------------------------------------------------------------------
# Helpers: blocked result builder
# ---------------------------------------------------------------------------


def _build_blocked_result(
    *,
    change_id: str,
    candidate_id: str,
    source_decision: str,
    blocked_reasons: tuple[str, ...],
    resolved_dir: Path,
    resolved_now: str,
    next_step: str,
) -> NextIterationSelectionPlan:
    """Build a blocked/deferred selection result and write audit."""
    status: str
    if any("extend" in r or "active_measurement" in r for r in blocked_reasons):
        status = "NEXT_ITERATION_DEFERRED"
    else:
        status = "NEXT_ITERATION_BLOCKED"

    plan: dict[str, object] = {
        "event": "next_iteration_selection_plan",
        "status": status,
        "change_id": change_id,
        "candidate_id": candidate_id,
        "source_decision": source_decision,
        "next_candidate_id": "",
        "next_target_bot": "",
        "next_reason": "",
        "blocked_reasons": list(blocked_reasons),
        "created_at_utc": resolved_now,
        "runtime_mutation": "NONE",
    }
    plan_path = resolved_dir / f"{change_id[:24] or 'unknown'}_selection_plan.json"
    _atomic_write_json(plan_path, plan)

    return NextIterationSelectionPlan(
        status=status,  # type: ignore[arg-type]
        change_id=change_id,
        candidate_id=candidate_id,
        source_decision=source_decision,
        next_candidate_id="",
        next_target_bot="",
        next_reason="",
        blocked_reasons=blocked_reasons,
        selection_plan_path=str(plan_path),
        next_step=next_step,
    )


# ---------------------------------------------------------------------------
# Helpers: target selection
# ---------------------------------------------------------------------------


def _select_next_target(
    current_target: str,
    fleet_bot_ids: tuple[str, ...],
) -> str:
    """Select the next target bot from the fleet.

    Prefers non-canary, non-control bots. Falls back to the first
    available bot that is not the current target.
    """
    # Preferred order: regime-hybrid, freqai-rebel, then others
    preferred = [
        "freqtrade-regime-hybrid",
        "freqai-rebel",
    ]

    for bot in preferred:
        if bot in fleet_bot_ids and bot != current_target:
            return bot

    # Fallback: first bot that is not the current target
    for bot in fleet_bot_ids:
        if bot != current_target:
            return bot

    # Last resort: return the current target (should not happen)
    return current_target
