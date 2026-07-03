"""Stale Evidence Gate — configurable staleness detection for SI-v2 evidence.

Phase 4 of #310: Prevents promotion or apply artifacts from being considered
valid when evidence is too old.

Supports per-domain staleness thresholds:
  - active_cycle: stale evidence blocks readiness
  - monitoring: stale monitoring evidence blocks readiness
  - dynamic_exit: stale dynamic-exit evidence blocks readiness

This is a pure function library — no I/O, no side effects, no external state.
Never mutates evidence, never auto-applies, never auto-promotes.

Safety invariants:
  - Never modifies any external state.
  - Never enables live trading or sets dry_run to false.
  - Never changes config, strategy, or Docker state.
  - Never auto-applies or auto-promotes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

# ---------------------------------------------------------------------------
# Domain identifiers
# ---------------------------------------------------------------------------

class EvidenceDomain(StrEnum):
    """Domains that have staleness requirements."""
    ACTIVE_CYCLE = "active_cycle"
    MONITORING = "monitoring"
    DYNAMIC_EXIT = "dynamic_exit"
    PROPOSAL = "proposal"
    MEASUREMENT = "measurement"


# ---------------------------------------------------------------------------
# Default staleness thresholds (in hours)
# ---------------------------------------------------------------------------

DEFAULT_STALENESS_THRESHOLDS: Final[dict[EvidenceDomain, int]] = {
    EvidenceDomain.ACTIVE_CYCLE: 24,      # Active cycle evidence older than 24h is stale
    EvidenceDomain.MONITORING: 6,          # Monitoring evidence older than 6h is stale
    EvidenceDomain.DYNAMIC_EXIT: 12,       # Dynamic exit evidence older than 12h is stale
    EvidenceDomain.PROPOSAL: 48,           # Proposal evidence older than 48h is stale
    EvidenceDomain.MEASUREMENT: 24,        # Measurement evidence older than 24h is stale
}

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class StaleEvidenceStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# Evidence item
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceItem:
    """A single piece of evidence with a timestamp.

    Attributes:
        domain: Which domain this evidence belongs to.
        evidence_id: Unique identifier for this evidence item.
        timestamp: When this evidence was created/collected.
        description: Human-readable description of the evidence.
    """
    domain: EvidenceDomain
    evidence_id: str
    timestamp: datetime
    description: str = ""


# ---------------------------------------------------------------------------
# Staleness result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StaleEvidenceResult:
    """Result of evaluating staleness for a single evidence item.

    Attributes:
        evidence_id: The evidence item's identifier.
        domain: The evidence domain.
        age_hours: How old the evidence is in hours.
        threshold_hours: The staleness threshold in hours.
        is_stale: Whether the evidence is stale.
        reason: Human-readable explanation.
    """
    evidence_id: str
    domain: EvidenceDomain
    age_hours: float
    threshold_hours: int
    is_stale: bool
    reason: str


# ---------------------------------------------------------------------------
# Gate verdict
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StaleEvidenceGateVerdict:
    """Complete verdict from the stale evidence gate.

    Attributes:
        status: PASS if all evidence is fresh, FAIL if any is stale,
                NOT_APPLICABLE if no evidence was provided.
        results: Per-evidence staleness results.
        stale_count: Number of stale evidence items.
        fresh_count: Number of fresh evidence items.
        total_count: Total number of evidence items evaluated.
        summary: Human-readable summary.
    """
    status: StaleEvidenceStatus
    results: tuple[StaleEvidenceResult, ...] = field(default_factory=tuple)
    stale_count: int = 0
    fresh_count: int = 0
    total_count: int = 0
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        """JSON-safe dict for embedding in cycle state / evidence bundles."""
        return {
            "status": str(self.status),
            "stale_count": self.stale_count,
            "fresh_count": self.fresh_count,
            "total_count": self.total_count,
            "summary": self.summary,
            "results": [
                {
                    "evidence_id": r.evidence_id,
                    "domain": str(r.domain),
                    "age_hours": round(r.age_hours, 1),
                    "threshold_hours": r.threshold_hours,
                    "is_stale": r.is_stale,
                    "reason": r.reason,
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# Core evaluation function
# ---------------------------------------------------------------------------


def evaluate_stale_evidence(
    evidence_items: list[EvidenceItem],
    *,
    now: datetime | None = None,
    thresholds: dict[EvidenceDomain, int] | None = None,
) -> StaleEvidenceGateVerdict:
    """Evaluate whether evidence items are stale.

    This is a pure function — no I/O, no side effects, no external state.

    Args:
        evidence_items: List of evidence items to evaluate.
        now: Current time (defaults to UTC now). Pass a fixed time for tests.
        thresholds: Per-domain staleness thresholds in hours.
            Falls back to DEFAULT_STALENESS_THRESHOLDS for any domain
            not explicitly provided.

    Returns:
        StaleEvidenceGateVerdict with per-item results and overall status.
    """
    if not evidence_items:
        return StaleEvidenceGateVerdict(
            status=StaleEvidenceStatus.NOT_APPLICABLE,
            summary="No evidence items to evaluate",
        )

    resolved_now = now or datetime.now(UTC)
    resolved_thresholds = dict(DEFAULT_STALENESS_THRESHOLDS)
    if thresholds:
        resolved_thresholds.update(thresholds)

    results: list[StaleEvidenceResult] = []
    stale_count = 0
    fresh_count = 0

    for item in evidence_items:
        threshold_hours = resolved_thresholds.get(item.domain, 24)
        age = resolved_now - item.timestamp
        age_hours = age.total_seconds() / 3600
        is_stale = age_hours > threshold_hours

        if is_stale:
            stale_count += 1
            reason = (
                f"Stale: evidence '{item.evidence_id}' in domain "
                f"'{item.domain.value}' is {age_hours:.1f}h old "
                f"(threshold: {threshold_hours}h)"
            )
        else:
            fresh_count += 1
            reason = (
                f"Fresh: evidence '{item.evidence_id}' in domain "
                f"'{item.domain.value}' is {age_hours:.1f}h old "
                f"(threshold: {threshold_hours}h)"
            )

        results.append(StaleEvidenceResult(
            evidence_id=item.evidence_id,
            domain=item.domain,
            age_hours=age_hours,
            threshold_hours=threshold_hours,
            is_stale=is_stale,
            reason=reason,
        ))

    if stale_count > 0:
        status = StaleEvidenceStatus.FAIL
        summary = (
            f"Stale evidence detected: {stale_count} of {len(evidence_items)} "
            f"evidence items exceed their staleness thresholds"
        )
    else:
        status = StaleEvidenceStatus.PASS
        summary = (
            f"All evidence fresh: {fresh_count} items within their "
            f"staleness thresholds"
        )

    return StaleEvidenceGateVerdict(
        status=status,
        results=tuple(results),
        stale_count=stale_count,
        fresh_count=fresh_count,
        total_count=len(evidence_items),
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Convenience: check if a single evidence item is stale
# ---------------------------------------------------------------------------


def is_evidence_stale(
    item: EvidenceItem,
    *,
    now: datetime | None = None,
    thresholds: dict[EvidenceDomain, int] | None = None,
) -> bool:
    """Quick check whether a single evidence item is stale.

    Args:
        item: The evidence item to check.
        now: Current time (defaults to UTC now).
        thresholds: Per-domain staleness thresholds.

    Returns:
        True if the evidence is stale, False otherwise.
    """
    resolved_now = now or datetime.now(UTC)
    resolved_thresholds = dict(DEFAULT_STALENESS_THRESHOLDS)
    if thresholds:
        resolved_thresholds.update(thresholds)

    threshold_hours = resolved_thresholds.get(item.domain, 24)
    age = resolved_now - item.timestamp
    age_hours = age.total_seconds() / 3600
    return age_hours > threshold_hours


# ---------------------------------------------------------------------------
# Convenience: filter stale evidence from a list
# ---------------------------------------------------------------------------


def filter_stale(
    items: list[EvidenceItem],
    *,
    now: datetime | None = None,
    thresholds: dict[EvidenceDomain, int] | None = None,
) -> list[EvidenceItem]:
    """Return only the stale evidence items from a list.

    Args:
        items: Evidence items to filter.
        now: Current time (defaults to UTC now).
        thresholds: Per-domain staleness thresholds.

    Returns:
        List of stale evidence items.
    """
    return [
        item
        for item in items
        if is_evidence_stale(item, now=now, thresholds=thresholds)
    ]


# ---------------------------------------------------------------------------
# Convenience: filter fresh evidence from a list
# ---------------------------------------------------------------------------


def filter_fresh(
    items: list[EvidenceItem],
    *,
    now: datetime | None = None,
    thresholds: dict[EvidenceDomain, int] | None = None,
) -> list[EvidenceItem]:
    """Return only the fresh (non-stale) evidence items from a list.

    Args:
        items: Evidence items to filter.
        now: Current time (defaults to UTC now).
        thresholds: Per-domain staleness thresholds.

    Returns:
        List of fresh evidence items.
    """
    return [
        item
        for item in items
        if not is_evidence_stale(item, now=now, thresholds=thresholds)
    ]


__all__ = [
    "DEFAULT_STALENESS_THRESHOLDS",
    "EvidenceDomain",
    "EvidenceItem",
    "StaleEvidenceGateVerdict",
    "StaleEvidenceResult",
    "StaleEvidenceStatus",
    "evaluate_stale_evidence",
    "filter_fresh",
    "filter_stale",
    "is_evidence_stale",
]
