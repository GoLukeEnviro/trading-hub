r"""SI v2 Approval-Gated Dry-Run Apply Path (#277).

Transforms a human-approved ShadowProposal into a documented dry-run apply
plan artifact — without modifying any runtime state, Freqtrade config,
strategy, Docker, cron, or live-trading settings.

Key design decisions:
  - Pure validation at the entry point (no I/O for gating).
  - Only creates artifact files (JSON) in a dedicated apply_plans/ directory.
  - Never writes to Freqtrade config directories, strategy files, or .env.
  - Never mutates Docker, compose, cron, or runtime state.
  - All mutation counters remain 0.
  - Apply Plan is the only output — no execution, no deployment, no live action.

Apply eligibility (ALL must be true):
  1. decision_type == SHADOW_PROPOSAL
  2. approval_status == APPROVED (set by human, never auto-approved)
  3. approval_eligibility == True
  4. requires_human_approval == True
  5. base_mode == proposal_only
  6. No hard-blocking promotion_block_reason_codes
  7. metrics_source is real (not "not_applicable", "synthetic", etc.)
  8. dry_run is True (never apply to live)
  9. no_proposal_reason is None

Safety invariants:
  - Never enables live trading or sets dry_run to false.
  - Never changes config, strategy, Docker, cron, or any runtime state.
  - Never reads or writes credentials, API keys, or wallet data.
  - Never executes orders or modifies Freqtrade state.
  - All mutation counters stay at 0.
  - Apply is artifact-only — no side effects beyond writing a JSON file.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Apply status constants
# ---------------------------------------------------------------------------
APPLY_STATUS_CREATED: Final[str] = "APPLY_PLAN_CREATED"
APPLY_STATUS_BLOCKED: Final[str] = "BLOCKED"
APPLY_STATUS_SKIPPED: Final[str] = "SKIPPED"

# ---------------------------------------------------------------------------
# Safety: metrics sources that are considered "real" for apply eligibility
# ---------------------------------------------------------------------------
_REAL_SOURCES: Final[tuple[str, ...]] = (
    "real",
    "freqtrade_rest",
    "freqtrade_telemetry",
    "walk_forward_net_metrics",
    "active_cycle",
)

# ---------------------------------------------------------------------------
# Promotion reason codes that are NOT hard-blocking for apply
# (codes that document info but don't block apply)
# ---------------------------------------------------------------------------
_NON_BLOCKING_CODES: Final[tuple[str, ...]] = (
    "positive_profit_hypothesis",
    "watchlist_promoted_to_shadow_proposal",
    "multi_cycle_candidate",
)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
_DEFAULT_APPLY_DIR = Path("self_improvement_v2") / "reports" / "phase2" / "apply_plans"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApplyPlan:
    """A validated, non-executed dry-run apply plan for one approved proposal.

    This artifact documents what WOULD be applied if this plan were executed.
    In v1, mutation_performed is ALWAYS False — no runtime mutation occurs.
    """

    apply_plan_id: str
    bot_id: str
    candidate_sha256: str
    hypothesis: str
    source_evidence_cycle: str
    plan_generated_at_utc: str
    approved_by: str
    approved_at_utc: str
    parameter_overlay: dict[str, object] = field(default_factory=dict)
    safety_verdict: str = APPLY_STATUS_CREATED
    safety_reasons: tuple[str, ...] = field(default_factory=tuple)
    mutation_performed: bool = False
    mutation_type: str = "none"

    def to_dict(self) -> dict[str, object]:
        return {
            "apply_plan_id": self.apply_plan_id,
            "bot_id": self.bot_id,
            "candidate_sha256": self.candidate_sha256,
            "hypothesis": self.hypothesis,
            "source_evidence_cycle": self.source_evidence_cycle,
            "plan_generated_at_utc": self.plan_generated_at_utc,
            "approved_by": self.approved_by,
            "approved_at_utc": self.approved_at_utc,
            "parameter_overlay": dict(self.parameter_overlay),
            "safety_verdict": self.safety_verdict,
            "safety_reasons": list(self.safety_reasons),
            "mutation_performed": self.mutation_performed,
            "mutation_type": self.mutation_type,
        }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_real_source(metrics_source: str) -> bool:
    """Check if a metrics source is considered real for apply eligibility."""
    return metrics_source.strip().lower() in _REAL_SOURCES


def _is_hard_block(reason_code: str) -> bool:
    """Check if a promotion_block_reason_code is a hard block for apply."""
    # Non-blocking codes are whitelisted; everything else is a hard block
    return reason_code not in _NON_BLOCKING_CODES


# ---------------------------------------------------------------------------
# Eligibility check
# ---------------------------------------------------------------------------


def check_apply_eligibility(
    proposal: dict[str, object],
) -> tuple[bool, list[str]]:
    """Check whether a proposal dict is eligible for dry-run apply.

    Args:
        proposal: A per_bot_decisions entry from an evidence bundle.
                  Must contain at minimum: decision_type, approval_status,
                  approval_eligible, requires_human_approval, base_mode,
                  walk_forward_net_metrics, promotion_block_reason_codes.

    Returns:
        Tuple of (eligible: bool, reasons: list[str]).
        If eligible is True, the proposal can proceed to apply plan creation.
        If eligible is False, reasons explain why it was blocked.
    """
    reasons: list[str] = []

    # 1. Must be a SHADOW_PROPOSAL
    dt = str(proposal.get("decision_type", ""))
    if dt != "SHADOW_PROPOSAL":
        reasons.append(f"decision_type={dt!r} != SHADOW_PROPOSAL")

    # 2. Must be APPROVED by a human
    status = str(proposal.get("approval_status", ""))
    if status != "APPROVED":
        reasons.append(f"approval_status={status!r} != APPROVED")

    # 3. Must be approval-eligible
    eligible = proposal.get("approval_eligible", False)
    if not eligible:
        reasons.append("approval_eligible=False")

    # 4. Must require human approval
    rha = proposal.get("requires_human_approval", False)
    if not rha:
        reasons.append("requires_human_approval=False")

    # 5. Must be proposal_only
    bm = str(proposal.get("base_mode", ""))
    if bm != "proposal_only":
        reasons.append(f"base_mode={bm!r} != proposal_only")

    # 6. No hard-blocking reason codes
    block_codes = proposal.get("promotion_block_reason_codes", [])
    if isinstance(block_codes, list):
        hard_blocks = [c for c in block_codes if _is_hard_block(str(c))]
        if hard_blocks:
            reasons.append(f"hard_block_codes={hard_blocks}")

    # 7. Metrics source must be real
    wf = proposal.get("walk_forward_net_metrics", {})
    if not isinstance(wf, dict):
        wf = {}
    ms = str(wf.get("metrics_source", "unknown"))
    if not _is_real_source(ms):
        reasons.append(f"metrics_source={ms!r} not real")

    # 8. No proposal reason (must not be "no_proposal" or similar)
    npr = proposal.get("no_proposal_reason")
    if npr is not None and npr != "":
        reasons.append(f"no_proposal_reason={npr!r}")

    # 9. Must be dry_run (never apply to live)
    dry_run_val = proposal.get("dry_run", True)
    if dry_run_val is False:
        reasons.append("dry_run flag is False (would enable live trading)")

    if reasons:
        return (False, reasons)

    return (True, [])


# ---------------------------------------------------------------------------
# Apply plan creation
# ---------------------------------------------------------------------------


def create_apply_plan(
    proposal: dict[str, object],
    *,
    apply_dir: str | Path = "",
    approved_by: str = "human",
    approved_at_utc: str = "",
) -> Path:
    """Validate a proposal and create a dry-run apply plan artifact.

    Args:
        proposal: Per-bot decision dict from an evidence bundle.
        apply_dir: Directory for apply plan artifacts.
                   Default: self_improvement_v2/reports/phase2/apply_plans/
        approved_by: Identifier for who approved this proposal.
        approved_at_utc: ISO timestamp of approval (default: now).

    Returns:
        Path to the created apply plan JSON artifact.

    Raises:
        ValueError: If the proposal is not eligible for apply.
    """
    eligible, reasons = check_apply_eligibility(proposal)
    if not eligible:
        raise ValueError(
            f"Proposal not eligible for apply: {'; '.join(reasons)}"
        )

    # Resolve paths
    out_dir = (
        Path(apply_dir)
        if apply_dir
        else Path(__file__).resolve().parents[4] / _DEFAULT_APPLY_DIR
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    # Generate plan
    plan_id = str(uuid.uuid4())[:8]
    now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    approved_at = approved_at_utc or now_utc

    plan = ApplyPlan(
        apply_plan_id=plan_id,
        bot_id=str(proposal.get("bot_id", "")),
        candidate_sha256=str(proposal.get("candidate_sha256", "")),
        hypothesis=str(proposal.get("hypothesis", "")),
        source_evidence_cycle=str(proposal.get("cycle_id", "")),
        plan_generated_at_utc=now_utc,
        approved_by=approved_by,
        approved_at_utc=approved_at,
        parameter_overlay={},  # v1: no executable parameters
        safety_verdict=APPLY_STATUS_CREATED,
        safety_reasons=("dry_run_apply_only", "no_mutation_performed"),
        mutation_performed=False,
        mutation_type="none",
    )

    artifact_path = out_dir / f"apply_plan_{plan_id}.json"
    with open(artifact_path, "w") as f:
        json.dump(plan.to_dict(), f, indent=2, sort_keys=True)

    return artifact_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point: python -m si_v2.apply.dry_run_apply_path.

    Reads a proposal JSON from stdin or a file, validates it, and creates
    an apply plan artifact.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="SI v2 Approval-Gated Dry-Run Apply Path",
    )
    parser.add_argument(
        "--proposal-file",
        type=str,
        default="",
        help="Path to a JSON file containing a per_bot_decisions entry",
    )
    parser.add_argument(
        "--approved-by",
        type=str,
        default="human",
        help="Identifier for who approved this proposal",
    )
    parser.add_argument(
        "--apply-dir",
        type=str,
        default="",
        help="Output directory for apply plan artifacts",
    )
    args = parser.parse_args()

    if args.proposal_file:
        with open(args.proposal_file) as f:
            proposal = json.load(f)
    else:
        import sys
        if sys.stdin.isatty():
            print("ERROR: Provide --proposal-file or pipe JSON to stdin")
            sys.exit(1)
        proposal = json.load(sys.stdin)

    try:
        artifact_path = create_apply_plan(
            proposal,
            apply_dir=args.apply_dir or "",
            approved_by=args.approved_by,
        )
        print(f"Apply plan created: {artifact_path}")
        print("  mutation_performed=False (dry-run artifact only)")
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
