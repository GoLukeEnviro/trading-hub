"""Human Approval Gate for SI v2 ShadowProposals (#276).

Determines whether a ShadowProposal is eligible for human approval based on
evidence completeness, metrics quality, and safety evaluation results.

This module is a **pure function** library — no I/O, no side effects, no
external state. It never auto-approves, auto-applies, or auto-promotes.
``APPROVED``, ``REJECTED``, and ``EXPIRED`` are human-controlled transitions
that the gate does **not** produce; it only classifies proposals as
``PENDING_HUMAN`` (eligible or not yet eligible) or ``NOT_APPLICABLE``.

Approval status model::

    PENDING_HUMAN   — Proposal is awaiting human review.
                       approval_eligible=True means evidence is complete enough
                       for a human to act; False means more evidence is needed.
    APPROVED        — Human has approved (set externally, never by this gate).
    REJECTED        — Human has rejected (set externally, never by this gate).
    EXPIRED         — Proposal has aged out (set externally, never by this gate).
    NOT_APPLICABLE  — No proposal exists or evaluation is not applicable.

Safety invariants:
    - Never modifies any external state.
    - Never enables live trading or sets ``dry_run`` to false.
    - Never changes config, strategy, or Docker state.
    - Never auto-applies or auto-promotes.
    - No secrets are read, stored, or emitted.

Integration:
    Called from ``active_cycle_runner.py`` Step 4 after walk-forward net
    metrics enrichment. The verdict's ``approval_status`` flows into the
    cycle state ``PerBotDecisionState`` and the evidence bundle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

# ---------------------------------------------------------------------------
# Approval status model
# ---------------------------------------------------------------------------


class ApprovalStatus(StrEnum):
    """Lifecycle status of a proposal in the human-approval workflow.

    The gate itself only emits ``PENDING_HUMAN`` or ``NOT_APPLICABLE``.
    ``APPROVED``, ``REJECTED``, and ``EXPIRED`` are set by external
    human-action or time-expiry code — never by this gate.
    """

    PENDING_HUMAN = "PENDING_HUMAN"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------

REASON_NO_PROPOSAL: Final[str] = "approval_no_proposal"
"""Decision is NO_PROPOSAL — nothing to approve."""

REASON_NOT_APPLICABLE_EVALUATION: Final[str] = "approval_not_applicable_evaluation"
"""Walk-forward evaluation status is NOT_APPLICABLE."""

REASON_METRICS_NOT_REAL: Final[str] = "approval_metrics_not_real"
"""metrics_source is 'not_applicable' — no real telemetry behind the proposal."""

REASON_METRICS_PARTIAL: Final[str] = "approval_metrics_partial"
"""metrics_source is 'partial' — metrics exist but drawdown is missing."""

REASON_INSUFFICIENT_EVIDENCE: Final[str] = "approval_insufficient_evidence"
"""Walk-forward evaluation returned INSUFFICIENT_EVIDENCE."""

REASON_NEGATIVE_NET_METRICS: Final[str] = "approval_negative_net_metrics"
"""Walk-forward evaluation returned NEGATIVE_NET_METRICS."""

REASON_MISSING_DRAWDOWN: Final[str] = "approval_missing_drawdown"
"""Drawdown data is missing — cannot assess risk."""

REASON_HIGH_DRAWDOWN: Final[str] = "approval_high_drawdown"
"""Drawdown exceeds the safety threshold."""

REASON_INSUFFICIENT_TRADES: Final[str] = "approval_insufficient_trades"
"""Trade count below the minimum for meaningful evaluation."""

REASON_MISSING_PNL: Final[str] = "approval_missing_pnl"
"""Net PnL value is absent."""

REASON_MISSING_PROFIT_FACTOR: Final[str] = "approval_missing_profit_factor"
"""Profit factor value is absent."""

REASON_PROMOTION_BLOCKED: Final[str] = "approval_promotion_blocked"
"""Promotion is blocked by other safety gates (catch-all)."""

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_MIN_TRADES_FOR_APPROVAL: Final[int] = 5
"""Minimum number of trades required for approval eligibility."""


# ---------------------------------------------------------------------------
# Verdict dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApprovalGateVerdict:
    """Result of approval gate evaluation for one bot's proposal.

    Attributes:
        bot_id: Identifier of the evaluated bot.
        approval_status: Lifecycle status (PENDING_HUMAN or NOT_APPLICABLE).
        approval_eligible: True when the proposal meets all evidence
            requirements and a human may approve it. False when blocked
            by insufficient evidence, negative metrics, or safety gates.
        reason_codes: Ordered list of reason codes explaining why the
            proposal is not eligible (empty when eligible).
    """

    bot_id: str
    approval_status: ApprovalStatus
    approval_eligible: bool
    reason_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """JSON-safe dict for embedding in cycle state / evidence bundles."""
        return {
            "bot_id": self.bot_id,
            "approval_status": str(self.approval_status),
            "approval_eligible": self.approval_eligible,
            "reason_codes": list(self.reason_codes),
        }


# ---------------------------------------------------------------------------
# Gate evaluation function
# ---------------------------------------------------------------------------


def evaluate_approval_eligibility(
    bot_id: str,
    decision_type: str,
    evaluation_status: str,
    metrics_source: str,
    promotion_blocked: bool,
    promotion_block_reason_codes: list[str],
    *,
    total_trades: int = 0,
    total_net_pnl: float | None = None,
    profit_factor: float | None = None,
    max_drawdown_pct: float | None = None,
    min_trades: int = _MIN_TRADES_FOR_APPROVAL,
) -> ApprovalGateVerdict:
    """Evaluate whether a ShadowProposal is eligible for human approval.

    This is a pure function — no I/O, no side effects, no external state.

    Args:
        bot_id: Identifier of the bot being evaluated.
        decision_type: ``SHADOW_PROPOSAL`` or ``NO_PROPOSAL`` (from
            fleet_analyzer).
        evaluation_status: Walk-forward evaluation status (``PASS_REVIEW``,
            ``NEGATIVE_NET_METRICS``, ``INSUFFICIENT_EVIDENCE``,
            ``NOT_APPLICABLE``).
        metrics_source: Source tag for the metrics (``real``,
            ``not_applicable``, ``partial``).
        promotion_blocked: Whether the walk-forward safety path blocks
            promotion.
        promotion_block_reason_codes: Reason codes from the safety path.
        total_trades: Total trades in the evaluation window.
        total_net_pnl: Net PnL across all trades (None if absent).
        profit_factor: Gross profit / gross loss (None if absent).
        max_drawdown_pct: Maximum drawdown percentage (None if absent).
        min_trades: Minimum trade count for approval eligibility.

    Returns:
        ``ApprovalGateVerdict`` with the formal approval status and
        eligibility assessment.
    """
    reason_codes: list[str] = []

    # -- Gate 1: NO_PROPOSAL is never approval-applicable ------------------
    if decision_type == "NO_PROPOSAL":
        return ApprovalGateVerdict(
            bot_id=bot_id,
            approval_status=ApprovalStatus.NOT_APPLICABLE,
            approval_eligible=False,
            reason_codes=[REASON_NO_PROPOSAL],
        )

    # -- Gate 2: NOT_APPLICABLE evaluation ----------------------------------
    if evaluation_status == "NOT_APPLICABLE":
        return ApprovalGateVerdict(
            bot_id=bot_id,
            approval_status=ApprovalStatus.NOT_APPLICABLE,
            approval_eligible=False,
            reason_codes=[REASON_NOT_APPLICABLE_EVALUATION],
        )

    # -- Gate 3: Metrics source quality -------------------------------------
    if metrics_source == "not_applicable":
        reason_codes.append(REASON_METRICS_NOT_REAL)
    elif metrics_source == "partial":
        reason_codes.append(REASON_METRICS_PARTIAL)

    # -- Gate 4: Walk-forward evaluation status -----------------------------
    if evaluation_status == "INSUFFICIENT_EVIDENCE":
        reason_codes.append(REASON_INSUFFICIENT_EVIDENCE)
    elif evaluation_status == "NEGATIVE_NET_METRICS":
        reason_codes.append(REASON_NEGATIVE_NET_METRICS)

    # -- Gate 5: Specific promotion block reason codes ----------------------
    wf_codes = set(promotion_block_reason_codes)
    if "walk_forward_missing_drawdown" in wf_codes:
        reason_codes.append(REASON_MISSING_DRAWDOWN)
    if "walk_forward_high_drawdown" in wf_codes:
        reason_codes.append(REASON_HIGH_DRAWDOWN)

    # -- Gate 6: Promotion blocked (catch-all) ------------------------------
    if promotion_blocked:
        # Only add generic reason if no specific reason already captured
        specific_reasons = {
            REASON_INSUFFICIENT_EVIDENCE,
            REASON_NEGATIVE_NET_METRICS,
            REASON_MISSING_DRAWDOWN,
            REASON_HIGH_DRAWDOWN,
            REASON_METRICS_NOT_REAL,
            REASON_METRICS_PARTIAL,
        }
        if not specific_reasons.intersection(reason_codes):
            reason_codes.append(REASON_PROMOTION_BLOCKED)

    # -- Gate 7: Evidence completeness --------------------------------------
    if total_trades < min_trades:
        reason_codes.append(REASON_INSUFFICIENT_TRADES)
    if total_net_pnl is None:
        reason_codes.append(REASON_MISSING_PNL)
    if profit_factor is None:
        reason_codes.append(REASON_MISSING_PROFIT_FACTOR)

    # -- Verdict -------------------------------------------------------------
    if not reason_codes:
        return ApprovalGateVerdict(
            bot_id=bot_id,
            approval_status=ApprovalStatus.PENDING_HUMAN,
            approval_eligible=True,
            reason_codes=[],
        )

    return ApprovalGateVerdict(
        bot_id=bot_id,
        approval_status=ApprovalStatus.PENDING_HUMAN,
        approval_eligible=False,
        reason_codes=reason_codes,
    )
