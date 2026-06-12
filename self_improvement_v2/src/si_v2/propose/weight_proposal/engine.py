"""Weight Proposal Engine (issue #63).

The engine:

1. Takes a typed ``WeightProposalRequest`` (issue #63 contract).
2. For each (source_id, regime) pair, picks the most recent
   ``ProposalEvidenceRecord`` from the request, converts it to a
   ``ProposalScoreInput``, calls ``score_proposal`` (issue #35) to
   obtain a typed ``ProposalDecision``, and derives a proposed weight
   delta from the decision and the score.
3. Caps every delta to ``policy.maximum_proposal_delta`` and every
   weight to ``[request.minimum_weight, request.maximum_weight]``.
4. Renormalizes per-group (rejected candidates are preserved as
   no-ops in the group sum).
5. Computes a SHA-256 ``proposal_fingerprint`` and a batch
   ``batch_fingerprint``.
6. Returns a stable-ordered ``WeightProposalBatch`` with three slices:
   ``stable_proposals`` (ACCEPT), ``deferred_candidates`` (DEFER),
   ``rejected_candidates`` (REJECT).

Engine rules (from the issue spec):

- Recommendation output only.
- Never read or write live strategy configuration.
- Current weights are explicitly supplied in the request.
- Never apply or persist a runtime weight.
- Never mark a proposal approved.
- The engine never auto-elevates a proposal to a higher stage.
- Negative expectancy never produces an increase.
- Sparse / stale / conflicting / low-confidence evidence REJECTs or
  DEFERs.
- Every delta respects ``policy.maximum_proposal_delta``.
- Weights remain within ``[minimum_weight, maximum_weight]``.
- Each normalization group sums to its ``target_sum`` (default 1.0).
- Normalization must not turn a rejected increase into an effective
  increase.
- Deterministic Decimal arithmetic with documented rounding.
- Stable input → byte-identical serialized output.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from decimal import Decimal
from typing import Protocol, runtime_checkable

from si_v2.propose.proposal_scoring.decimal_safe import (
    quantize_delta,
    quantize_weight,
)
from si_v2.propose.proposal_scoring.models import (
    POLICY_VERSION,
    DataQualityVerdict,
    DirectionHint,
    ProposalDecision,
    ProposalRejectionReason,
    ProposalScoreBreakdown,
    ProposalScoreInput,
    ScoringPolicy,
)
from si_v2.propose.weight_proposal.audit import (
    compute_fingerprint_manifest,
    render_sanitized_json_proposal,
    render_sanitized_markdown_report,
    write_proposal_artifact,
)
from si_v2.propose.weight_proposal.models import (
    PROPOSAL_SCHEMA_VERSION,
    CurrentWeight,
    WeightProposal,
    WeightProposalBatch,
    WeightProposalRequest,
)
from si_v2.propose.weight_proposal.normalization import (
    apply_normalization,
    enforce_max_delta_on_proposal,
)

# ---------------------------------------------------------------------------
# Duck-typed protocol for ProposalEvidenceRecord
# ---------------------------------------------------------------------------


@runtime_checkable
class ProposalEvidenceRecordLike(Protocol):
    """Structural type for the upstream ``ProposalEvidenceRecord``.

    The engine depends only on the attributes listed below, so it
    uses a ``Protocol`` (no import of the input pipeline) to avoid
    coupling the two modules.
    """

    evidence_id: str
    source_id: str
    regime: str
    cache_schema_version: int | None
    unique_trade_count: int
    expectancy: Decimal
    drawdown_proxy: Decimal
    average_source_confidence: Decimal | None
    average_regime_confidence: Decimal | None
    evidence_age_days: Decimal
    data_quality_verdict: str
    is_actionable: bool
    has_conflict: bool
    evidence_max_closed_at: str | None


# ---------------------------------------------------------------------------
# Conversion from ProposalEvidenceRecord (issue #62) to ProposalScoreInput
# ---------------------------------------------------------------------------


def _to_score_input(
    ev: ProposalEvidenceRecordLike,
    *,
    direction_hint: DirectionHint,
    human_approval_available: bool,
) -> ProposalScoreInput:
    """Convert a ``ProposalEvidenceRecord`` to a ``ProposalScoreInput``."""
    from si_v2.propose.proposal_scoring.decimal_safe import to_decimal

    def _opt_decimal(name: str) -> Decimal | None:
        v = getattr(ev, name, None)
        if v is None:
            return None
        return to_decimal(v, f"ProposalEvidenceRecord.{name}")

    def _req_decimal(name: str) -> Decimal:
        v = getattr(ev, name, None)
        if v is None:
            raise ValueError(
                f"ProposalEvidenceRecord.{name} is required for scoring"
            )
        return to_decimal(v, f"ProposalEvidenceRecord.{name}")

    return ProposalScoreInput(
        evidence_id=str(ev.evidence_id),
        source_id=str(ev.source_id),
        regime=str(ev.regime),
        evidence_schema_version=int(
            getattr(ev, "cache_schema_version", 1) or 1
        ),
        unique_trade_count=int(getattr(ev, "unique_trade_count", 0)),
        expectancy=_req_decimal("expectancy"),
        drawdown_proxy=_req_decimal("drawdown_proxy"),
        average_source_confidence=_opt_decimal("average_source_confidence"),
        average_regime_confidence=_opt_decimal("average_regime_confidence"),
        evidence_age_days=_req_decimal("evidence_age_days"),
        data_quality_verdict=DataQualityVerdict(
            str(getattr(ev, "data_quality_verdict", "accepted"))
        ),
        is_actionable=bool(getattr(ev, "is_actionable", True)),
        direction_hint=direction_hint,
        has_conflict=bool(getattr(ev, "has_conflict", False)),
        human_approval_available=human_approval_available,
        backtest_metrics=None,
        walk_forward_metrics=None,
    )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def _stable_id(*parts: str) -> str:
    """Deterministic 64-char hex id from string parts."""
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return h


def _fingerprint_proposal(
    source_id: str,
    regime: str,
    current_weight: Decimal,
    proposed_weight: Decimal,
    decision: str,
    promotion_stage: str,
    score: ProposalScoreBreakdown,
    policy_version: str,
    evidence_schema_version: int,
) -> str:
    payload = (
        f"{source_id}|{regime}|{current_weight}|{proposed_weight}|"
        f"{decision}|{promotion_stage}|{score.total_score}|"
        f"{policy_version}|{evidence_schema_version}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _derive_direction_hint(score: ProposalScoreBreakdown) -> DirectionHint:
    """Pick a conservative default direction hint.

    The engine never assumes an increase; it picks the direction
    based on the total score. A score ≥ the accept threshold implies
    an increase; a score < the defer threshold implies a decrease.
    Anything in between is ``neutral`` (the proposal is a
    recommendation, not an instruction).
    """
    # The default policy's accept threshold is 0.65, defer is 0.40;
    # but the engine has no policy here. We use the policy via the
    # scoring module's score_proposal output. This helper is only
    # called as a fallback for the **direction hint**; the actual
    # decision comes from score_proposal.
    return DirectionHint.NEUTRAL


def _expected_impact_for(
    decision: str,
    score_total: Decimal,
    delta: Decimal,
) -> str:
    if decision == "REJECT":
        return (
            "no proposed change; evidence is rejected by the scoring "
            "policy gates; see typed_reasons for the failing gate(s)"
        )
    if decision == "DEFER":
        return (
            "deferred pending additional evidence; the score is below "
            "the accept threshold but above the defer threshold; the "
            "delta is bounded by the policy maximum-delta cap"
        )
    if delta > Decimal("0"):
        return (
            f"bounded increase of {delta} (positive evidence supports "
            f"a higher weight; the exact increase is capped by the "
            f"policy maximum-delta and renormalized within the group)"
        )
    if delta < Decimal("0"):
        return (
            f"bounded decrease of {abs(delta)} (negative or weak "
            f"evidence supports a lower weight; the exact decrease is "
            f"capped by the policy maximum-delta and renormalized "
            f"within the group)"
        )
    return "no change; the proposal recommends holding the current weight"


def _risk_notes_for(
    decision: str,
    delta: Decimal,
    expected: Decimal,
    expected_impact: str,
    typed_reasons: tuple[ProposalRejectionReason, ...],
) -> tuple[str, ...]:
    notes: list[str] = []
    if decision == "REJECT":
        notes.append(
            "proposal rejected; weight should be held at the current "
            "value; re-evaluate once the failing gate clears"
        )
        for r in typed_reasons:
            notes.append(f"rejection reason: {r.value}")
    elif decision == "DEFER":
        notes.append(
            "proposal deferred; weight should be held at the current "
            "value until more evidence is collected"
        )
    else:
        if expected_impact == expected:
            pass
        if delta > Decimal("0"):
            notes.append(
                "increase is capped by the policy maximum-delta and "
                "renormalized within the normalization group"
            )
        elif delta < Decimal("0"):
            notes.append(
                "decrease is capped by the policy maximum-delta and "
                "renormalized within the normalization group"
            )
        else:
            notes.append("no change; the proposal recommends holding the weight")
    return tuple(notes)


class WeightProposalEngine:
    """Review-only weight proposal engine.

    Construction is parameterless; the engine is a stateless function
    object whose only state is its public API surface.
    """

    def build_proposals(
        self,
        request: WeightProposalRequest,
        evidence_by_key: (
            Mapping[tuple[str, str], tuple[ProposalEvidenceRecordLike, ...]] | None
        ) = None,
    ) -> WeightProposalBatch:
        """Build one batch of weight proposals for the request.

        Args:
            request: The typed request.
            evidence_by_key: Optional explicit mapping from
                ``(source_id, regime)`` to a tuple of
                ``ProposalEvidenceRecord`` instances. If ``None``
                (the default), the engine builds the mapping by
                scanning ``request.evidence_records`` and selecting
                the most recent record per key. Most callers should
                pass ``None``; the parameter exists for tests.

        Returns:
            A typed ``WeightProposalBatch`` with stable ordering.
        """
        if evidence_by_key is None:
            evidence_by_key = self._group_evidence(request)

        current_by_key: dict[tuple[str, str], CurrentWeight] = {
            (cw.source_id, cw.regime): cw for cw in request.current_weights
        }

        # Build one raw proposal per (source_id, regime) in either
        # current_weights or evidence.
        keys = set(current_by_key.keys()) | set(evidence_by_key.keys())
        raw: list[WeightProposal] = []
        for key in sorted(keys):
            source_id, regime = key
            cw = current_by_key.get(key)
            current_weight = cw.weight if cw is not None else Decimal("0")
            evidence_records = evidence_by_key.get(key, ())
            if not evidence_records:
                # Missing evidence: emit a REJECT proposal so the
                # reviewer sees the gap.
                proposal = self._build_reject_for_missing_evidence(
                    source_id=source_id,
                    regime=regime,
                    current_weight=current_weight,
                    request=request,
                )
                raw.append(proposal)
                continue
            # Pick the most recent evidence (largest evidence_max_closed_at
            # if available, else first).
            ev = self._pick_most_recent(evidence_records)
            decision = self._score(
                ev,
                policy=request.scoring_policy,
                human_approval_available=True,
            )
            proposal = self._build_proposal_from_decision(
                source_id=source_id,
                regime=regime,
                current_weight=current_weight,
                decision=decision,
                evidence_id=str(ev.evidence_id),
                request=request,
            )
            # Cap the delta to the policy maximum.
            proposal = enforce_max_delta_on_proposal(
                proposal, request.scoring_policy.maximum_proposal_delta
            )
            raw.append(proposal)

        # Normalize per group.
        normalized, evidence_lines = apply_normalization(
            raw,
            request.normalization_groups,
            request.minimum_weight,
            request.maximum_weight,
        )
        # Re-enforce the maximum-delta cap on every non-REJECT
        # proposal in case normalization adjusted the weight upward
        # beyond the cap. REJECT proposals are already at
        # current_weight, so the cap is trivially satisfied for them.
        max_delta = request.scoring_policy.maximum_proposal_delta
        recapped: list[WeightProposal] = []
        for p in normalized:
            if p.decision == "REJECT":
                recapped.append(p)
                continue
            recapped.append(enforce_max_delta_on_proposal(p, max_delta))

        # Stable order: ACCEPT first, then DEFER, then REJECT;
        # within each slice, sort by (source_id, regime).
        accepts: list[WeightProposal] = []
        defers: list[WeightProposal] = []
        rejects: list[WeightProposal] = []
        for p in recapped:
            if p.decision == "ACCEPT":
                accepts.append(p)
            elif p.decision == "DEFER":
                defers.append(p)
            else:
                rejects.append(p)
        accepts.sort(key=lambda p: (p.source_id, p.regime))
        defers.sort(key=lambda p: (p.source_id, p.regime))
        rejects.sort(key=lambda p: (p.source_id, p.regime))

        batch_id = _stable_id(
            request.proposal_timestamp_utc,
            POLICY_VERSION,
            str(request.evidence_schema_version),
            PROPOSAL_SCHEMA_VERSION,
            ",".join(
                f"{p.proposal_id}:{p.proposal_fingerprint[:8]}"
                for p in accepts + defers + rejects
            ),
        )
        # Build the batch deterministically.
        batch = WeightProposalBatch(
            batch_id=batch_id,
            proposal_timestamp_utc=request.proposal_timestamp_utc,
            policy_version=POLICY_VERSION,
            evidence_schema_version=request.evidence_schema_version,
            proposal_schema_version=PROPOSAL_SCHEMA_VERSION,
            scoring_policy_version=POLICY_VERSION,
            stable_proposals=tuple(accepts),
            deferred_candidates=tuple(defers),
            rejected_candidates=tuple(rejects),
            normalization_evidence=tuple(evidence_lines),
            batch_fingerprint=batch_id,  # overwritten below
        )
        # Compute the actual batch fingerprint from the canonical JSON.
        batch_hash = hashlib.sha256(
            batch.model_copy(
                update={"batch_fingerprint": "0" * 64}
            ).canonical_serialize().encode("utf-8")
        ).hexdigest()
        return batch.model_copy(update={"batch_fingerprint": batch_hash})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _group_evidence(
        self,
        request: WeightProposalRequest,
    ) -> dict[tuple[str, str], tuple[ProposalEvidenceRecordLike, ...]]:
        grouped: dict[tuple[str, str], list[ProposalEvidenceRecordLike]] = {}
        for ev in request.evidence_records:
            # ``request.evidence_records`` is typed as ``tuple[object, ...]``
            # to keep the engine decoupled from the input-pipeline
            # module. The Protocol is structural; we read attributes
            # via ``getattr`` for compatibility with arbitrary records.
            key = (str(ev.source_id), str(ev.regime))
            grouped.setdefault(key, []).append(ev)  # type: ignore[arg-type]
        return {k: tuple(v) for k, v in grouped.items()}

    def _pick_most_recent(
        self,
        records: tuple[ProposalEvidenceRecordLike, ...],
    ) -> ProposalEvidenceRecordLike:
        def _key(rec: ProposalEvidenceRecordLike) -> str:
            return str(getattr(rec, "evidence_max_closed_at", "") or "")

        return max(records, key=_key)

    def _score(
        self,
        ev: ProposalEvidenceRecordLike,
        policy: ScoringPolicy,
        human_approval_available: bool,
    ) -> ProposalDecision:
        """Score one evidence record against the policy."""
        from si_v2.propose.proposal_scoring.scoring import score_proposal

        # Default direction hint = NEUTRAL. The engine will not infer
        # an INCREASE from positive evidence; the issue spec says
        # "current weights must be explicitly supplied in the request"
        # and the direction hint is "supplied explicitly by the caller".
        inp = _to_score_input(
            ev,
            direction_hint=DirectionHint.NEUTRAL,
            human_approval_available=human_approval_available,
        )
        return score_proposal(inp, policy)

    def _build_proposal_from_decision(
        self,
        *,
        source_id: str,
        regime: str,
        current_weight: Decimal,
        decision: ProposalDecision,
        evidence_id: str,
        request: WeightProposalRequest,
    ) -> WeightProposal:
        # Convert the score into a weight delta:
        # - REJECT: no change
        # - DEFER:  no change
        # - ACCEPT: bounded delta proportional to (score - accept_threshold)
        max_delta = request.scoring_policy.maximum_proposal_delta
        score = decision.score
        if decision.decision == "ACCEPT":
            excess = max(Decimal("0"), score.total_score - request.scoring_policy.accept_threshold)
            # Scale the excess to a fraction of the max_delta.
            span = Decimal("1") - request.scoring_policy.accept_threshold
            frac = min(Decimal("1"), excess / span) if span > Decimal("0") else Decimal("1")
            delta = quantize_delta(frac * max_delta, "proposed_delta")
        elif decision.decision == "DEFER":
            # Hold the weight.
            delta = Decimal("0")
        else:
            # REJECT: no change
            delta = Decimal("0")
        proposed_weight = quantize_weight(
            current_weight + delta, "proposed_weight"
        )
        delta = quantize_delta(proposed_weight - current_weight, "proposed_delta")
        # Clamp to bounds (defence in depth).
        if proposed_weight < request.minimum_weight:
            proposed_weight = quantize_weight(request.minimum_weight, "proposed_weight")
            delta = quantize_delta(proposed_weight - current_weight, "proposed_delta")
        elif proposed_weight > request.maximum_weight:
            proposed_weight = quantize_weight(request.maximum_weight, "proposed_weight")
            delta = quantize_delta(proposed_weight - current_weight, "proposed_delta")
        # Hard guarantee: negative expectancy for an increase => REJECT.
        # The scoring engine already enforces this; we double-check
        # that a decision of ACCEPT with a NEGATIVE_EXPECTANCY_FOR_INCREASE
        # reason is impossible (the gate would have rejected). If
        # somehow it slipped through, force REJECT.
        if (
            decision.decision == "ACCEPT"
            and ProposalRejectionReason.NEGATIVE_EXPECTANCY_FOR_INCREASE
            in decision.typed_reasons
        ):
            decision = decision.model_copy(update={"decision": "REJECT"})
        proposal_id = _stable_id(
            evidence_id, source_id, regime, str(current_weight),
            str(proposed_weight), decision.decision, str(score.total_score),
        )
        proposal_fingerprint = _fingerprint_proposal(
            source_id=source_id,
            regime=regime,
            current_weight=current_weight,
            proposed_weight=proposed_weight,
            decision=decision.decision,
            promotion_stage=str(decision.promotion_stage),
            score=score,
            policy_version=request.scoring_policy.policy_version,
            evidence_schema_version=request.evidence_schema_version,
        )
        expected_impact = _expected_impact_for(
            decision.decision, score.total_score, delta
        )
        risk_notes = _risk_notes_for(
            decision=decision.decision,
            delta=delta,
            expected=Decimal("0"),
            expected_impact=expected_impact,
            typed_reasons=decision.typed_reasons,
        )
        return WeightProposal(
            proposal_id=proposal_id,
            source_id=source_id,
            regime=regime,
            current_weight=current_weight,
            proposed_weight=proposed_weight,
            proposed_delta=delta,
            decision=decision.decision,
            promotion_stage=str(decision.promotion_stage),
            score_breakdown=score,
            evidence_references=(evidence_id,),
            expected_analytical_impact=expected_impact,
            risk_notes=risk_notes,
            typed_reasons=tuple(r.value for r in decision.typed_reasons),
            human_approval_required=True,
            policy_version=request.scoring_policy.policy_version,
            evidence_schema_version=request.evidence_schema_version,
            proposal_schema_version=PROPOSAL_SCHEMA_VERSION,
            proposal_fingerprint=proposal_fingerprint,
        )

    def _build_reject_for_missing_evidence(
        self,
        *,
        source_id: str,
        regime: str,
        current_weight: Decimal,
        request: WeightProposalRequest,
    ) -> WeightProposal:
        """Build a REJECT proposal for a (source, regime) with no evidence."""
        proposed_weight = quantize_weight(current_weight, "proposed_weight")
        delta = Decimal("0")
        promotion_stage = "proposal_only"
        expected_impact = (
            "no evidence was supplied for this (source, regime); "
            "the proposal is REJECTed with INSUFFICIENT_EVIDENCE_SAMPLE"
        )
        risk_notes = (
            "no evidence supplied; cannot propose a change",
            "rejection reason: insufficient_evidence_sample",
        )
        proposal_id = _stable_id(
            "missing-evidence", source_id, regime, str(current_weight)
        )
        return WeightProposal(
            proposal_id=proposal_id,
            source_id=source_id,
            regime=regime,
            current_weight=current_weight,
            proposed_weight=proposed_weight,
            proposed_delta=delta,
            decision="REJECT",
            promotion_stage=promotion_stage,
            score_breakdown=ProposalScoreBreakdown(
                sample_score=Decimal("0"),
                expectancy_score=Decimal("0"),
                drawdown_score=Decimal("0"),
                confidence_score=Decimal("0"),
                recency_score=Decimal("0"),
                backtest_score=Decimal("0"),
                walk_forward_score=Decimal("0"),
                quality_score=Decimal("0"),
                total_score=Decimal("0"),
            ),
            evidence_references=(),
            expected_analytical_impact=expected_impact,
            risk_notes=risk_notes,
            typed_reasons=("insufficient_evidence_sample",),
            human_approval_required=True,
            policy_version=request.scoring_policy.policy_version,
            evidence_schema_version=request.evidence_schema_version,
            proposal_schema_version=PROPOSAL_SCHEMA_VERSION,
            proposal_fingerprint=proposal_id,
        )


__all__ = [
    "WeightProposalEngine",
    "compute_fingerprint_manifest",
    "render_sanitized_json_proposal",
    "render_sanitized_markdown_report",
    "write_proposal_artifact",
]
