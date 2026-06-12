"""Normalization helpers for the Weight Proposal Engine (issue #63).

The engine produces one ``WeightProposal`` per (source_id, regime)
identity. The set of identities is partitioned into
``NormalizationGroup`` instances. After the engine produces raw
``proposed_weight`` values for each identity in a group, the values
are clipped to ``[minimum_weight, maximum_weight]`` and then
re-normalized so that the group sums to exactly ``target_sum``
(default 1.0) within the policy's ``maximum_proposal_delta`` cap.

Hard invariants:

- A REJECT decision on a candidate is preserved through normalization.
  If the rejected candidate was the *only* way to satisfy a group's
  target, normalization must NOT make a REJECT into an ACCEPT — it
  must defer the group.
- ACCEPT and DEFER decisions are renormalized within their
  hard-clipped and delta-capped envelope.
- A candidate whose proposed_delta would exceed
  ``policy.maximum_proposal_delta`` is reduced to the cap (and
  flagged in ``risk_notes``).
- A candidate with negative weight post-normalization is clipped
  to ``minimum_weight``.
"""

from __future__ import annotations

from decimal import Decimal

from si_v2.propose.proposal_scoring.decimal_safe import (
    quantize_delta,
    quantize_weight,
)
from si_v2.propose.weight_proposal.models import (
    NormalizationGroup,
    WeightProposal,
)


def _key(p: WeightProposal) -> tuple[str, str]:
    return (p.source_id, p.regime)


def _group_id_for(
    groups: tuple[NormalizationGroup, ...],
    source_id: str,
    regime: str,
) -> str | None:
    for g in groups:
        if (source_id, regime) in g.identities:
            return g.group_id
    return None


def _enforce_max_delta(
    current_weight: Decimal,
    proposed_weight: Decimal,
    max_delta: Decimal,
) -> tuple[Decimal, bool]:
    """Return ``(clipped_weight, was_clipped)``.

    The clip never reduces the magnitude of an increase that the
    evidence supports; it caps the absolute change to ``max_delta``.
    A decrease larger than ``max_delta`` is also capped.
    """
    delta = proposed_weight - current_weight
    if abs(delta) <= max_delta:
        return proposed_weight, False
    if delta > 0:
        return quantize_weight(current_weight + max_delta, "proposed_weight"), True
    return quantize_weight(current_weight - max_delta, "proposed_weight"), True


def _clip_to_bounds(
    weight: Decimal,
    minimum_weight: Decimal,
    maximum_weight: Decimal,
) -> Decimal:
    if weight < minimum_weight:
        return quantize_weight(minimum_weight, "proposed_weight")
    if weight > maximum_weight:
        return quantize_weight(maximum_weight, "proposed_weight")
    return quantize_weight(weight, "proposed_weight")


def normalize_group(
    candidates: list[WeightProposal],
    group: NormalizationGroup,
    minimum_weight: Decimal,
    maximum_weight: Decimal,
) -> tuple[list[WeightProposal], list[str]]:
    """Normalize one group's ``proposed_weight`` values.

    Returns:
        A tuple of (normalized candidates, evidence lines).
    """
    evidence: list[str] = []
    # Group identities
    group_keys = set(group.identities)
    in_group = [c for c in candidates if (c.source_id, c.regime) in group_keys]
    out_of_group = [c for c in candidates if (c.source_id, c.regime) not in group_keys]

    if not in_group:
        evidence.append(
            f"group={group.group_id}: no candidates, group skipped"
        )
        return candidates, evidence

    # Step 1: REJECT proposals are first forced back to current_weight
    # (the "no change" semantic for REJECT). This guarantees that a
    # rejected candidate's proposed_weight is exactly its current_weight.
    reset: list[WeightProposal] = []
    for c in in_group:
        if c.decision == "REJECT":
            if c.proposed_weight != c.current_weight:
                reset.append(
                    c.model_copy(
                        update={
                            "proposed_weight": quantize_weight(
                                c.current_weight, "proposed_weight"
                            ),
                            "proposed_delta": Decimal("0"),
                        }
                    )
                )
            else:
                reset.append(c)
        else:
            reset.append(c)
    in_group = reset

    # Step 2: clip ACCEPT/DEFER candidates to [minimum_weight, maximum_weight]
    clipped: list[WeightProposal] = []
    for c in in_group:
        if c.decision == "REJECT":
            # REJECT decisions were reset to current_weight above; no
            # further clip needed.
            clipped.append(c)
            continue
        clipped_w = _clip_to_bounds(
            c.proposed_weight, minimum_weight, maximum_weight
        )
        if clipped_w != c.proposed_weight:
            new_c = c.model_copy(
                update={
                    "proposed_weight": clipped_w,
                    "proposed_delta": quantize_delta(
                        clipped_w - c.current_weight, "proposed_delta"
                    ),
                }
            )
            risk = (*c.risk_notes, f"proposed_weight clipped to bounds [{minimum_weight}, {maximum_weight}]")
            new_c = new_c.model_copy(update={"risk_notes": risk})
            clipped.append(new_c)
        else:
            clipped.append(c)
    evidence.append(
        f"group={group.group_id}: {len(clipped)} candidates after clip; "
        f"target_sum={group.target_sum}"
    )

    # Step 3: re-normalize ACCEPT and DEFER candidates so the group
    # sums to target_sum. REJECT candidates are *removed* from the
    # renormalization pool but their proposed_weight (now equal to
    # current_weight) is left in the group sum (we treat REJECTs as a
    # no-op for the sum).
    accepted_keys = {
        (c.source_id, c.regime) for c in clipped if c.decision == "ACCEPT"
    }
    deferred_keys = {
        (c.source_id, c.regime) for c in clipped if c.decision == "DEFER"
    }
    rejected_keys = {
        (c.source_id, c.regime) for c in clipped if c.decision == "REJECT"
    }
    evidence.append(
        f"group={group.group_id}: accepted={len(accepted_keys)} "
        f"deferred={len(deferred_keys)} rejected={len(rejected_keys)}"
    )

    renormalize_keys = accepted_keys | deferred_keys
    renormalize_pool = [c for c in clipped if (c.source_id, c.regime) in renormalize_keys]
    rejected_pool = [c for c in clipped if (c.source_id, c.regime) in rejected_keys]

    target = group.target_sum
    rejected_sum = sum((c.proposed_weight for c in rejected_pool), Decimal("0"))
    if renormalize_pool:
        current_pool_sum = sum(
            (c.proposed_weight for c in renormalize_pool), Decimal("0")
        )
        # Required pool sum after removing rejected
        required_pool_sum = target - rejected_sum
        if current_pool_sum <= Decimal("0"):
            # Degenerate — fall back to equal split among pool members.
            per_member = required_pool_sum / Decimal(len(renormalize_pool))
            new_pool: list[WeightProposal] = []
            for c in renormalize_pool:
                clipped_w = _clip_to_bounds(per_member, minimum_weight, maximum_weight)
                new_w = c.model_copy(
                    update={
                        "proposed_weight": clipped_w,
                        "proposed_delta": quantize_delta(
                            clipped_w - c.current_weight, "proposed_delta"
                        ),
                    }
                )
                risk = (*c.risk_notes, "group_sum was zero; fell back to equal split")
                new_pool.append(new_w.model_copy(update={"risk_notes": risk}))
            renormalize_pool = new_pool
        else:
            scale = required_pool_sum / current_pool_sum
            new_pool = []
            for c in renormalize_pool:
                new_w_raw = c.proposed_weight * scale
                clipped_w = _clip_to_bounds(
                    new_w_raw, minimum_weight, maximum_weight
                )
                new_w = c.model_copy(
                    update={
                        "proposed_weight": clipped_w,
                        "proposed_delta": quantize_delta(
                            clipped_w - c.current_weight, "proposed_delta"
                        ),
                    }
                )
                if clipped_w != new_w_raw:
                    risk = (*c.risk_notes, "group renormalization clipped to per-candidate bounds")
                    new_w = new_w.model_copy(update={"risk_notes": risk})
                new_pool.append(new_w)
            renormalize_pool = new_pool
    # If renormalize_pool is empty, all candidates were REJECTed —
    # the group is "no proposal possible" and the group is not flagged
    # as an evidence line beyond what the engine already reports.

    # Step 4: replace in_group with the new pool
    new_in_group = renormalize_pool + rejected_pool
    # Stable order: (source_id, regime)
    new_in_group.sort(key=_key)
    return out_of_group + new_in_group, evidence


def apply_normalization(
    candidates: list[WeightProposal],
    groups: tuple[NormalizationGroup, ...],
    minimum_weight: Decimal,
    maximum_weight: Decimal,
) -> tuple[list[WeightProposal], list[str]]:
    """Apply normalization to every group and return the merged list."""
    if not groups:
        return candidates, ["no normalization groups supplied"]
    by_key = {(c.source_id, c.regime): c for c in candidates}
    all_keys: set[tuple[str, str]] = set(by_key.keys())
    all_evidence: list[str] = []
    # Start with all candidates in a single "ungrouped" pool, then
    # overwrite them as we normalize each group.
    pool: list[WeightProposal] = list(candidates)
    for group in groups:
        pool, evidence = normalize_group(
            pool, group, minimum_weight, maximum_weight
        )
        all_evidence.extend(evidence)
    # Sanity: every (source_id, regime) still present
    seen = {(c.source_id, c.regime) for c in pool}
    missing = all_keys - seen
    if missing:
        raise ValueError(
            f"normalization dropped candidates: {sorted(missing)}"
        )
    return pool, all_evidence


def enforce_max_delta_on_proposal(
    proposal: WeightProposal,
    max_delta: Decimal,
) -> WeightProposal:
    """Cap a single proposal's ``proposed_weight`` to the delta cap.

    Returns a new ``WeightProposal`` (frozen-friendly) with updated
    ``proposed_weight`` and ``proposed_delta``. If the cap was
    actually applied, a note is appended to ``risk_notes``.
    """
    clipped, was_clipped = _enforce_max_delta(
        proposal.current_weight, proposal.proposed_weight, max_delta
    )
    if not was_clipped:
        return proposal
    new_delta = quantize_delta(clipped - proposal.current_weight, "proposed_delta")
    risk = (*proposal.risk_notes, f"proposed_delta capped to {max_delta}")
    return proposal.model_copy(
        update={"proposed_weight": clipped, "proposed_delta": new_delta, "risk_notes": risk}
    )
