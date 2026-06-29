"""Tests for proposal/schema.py — ProposalCandidate, EvidenceReference, enums, serialization.

Tests cover:
- ProposalDecision and ProposalSource enum values
- EvidenceReference creation and to_json_safe
- ProposalCandidate creation (minimal, full, edge cases)
- to_json_safe serialization
- candidate_id property
- Safety guardrails: requires_human_approval, mutation_policy, dry_run_only
"""

from __future__ import annotations

from si_v2.proposal.schema import (
    EvidenceReference,
    ProposalCandidate,
    ProposalDecision,
    ProposalSource,
)

# ======================================================================
# Enums
# ======================================================================

class TestProposalDecision:
    def test_values(self) -> None:
        assert ProposalDecision.ACCEPT.value == "accept"
        assert ProposalDecision.REJECT.value == "reject"
        assert ProposalDecision.DEFER.value == "defer"
        assert ProposalDecision.INSUFFICIENT_EVIDENCE.value == "insufficient_evidence"

    def test_all_values_covered(self) -> None:
        values = {e.value for e in ProposalDecision}
        assert values == {"accept", "reject", "defer", "insufficient_evidence"}


class TestProposalSource:
    def test_values(self) -> None:
        assert ProposalSource.FLEET_ANALYZER.value == "fleet_analyzer"
        assert ProposalSource.TELEMETRY_ANALYZER.value == "telemetry_analyzer"
        assert ProposalSource.ATTRIBUTION_ENGINE.value == "attribution_engine"
        assert ProposalSource.MANUAL.value == "manual"

    def test_all_values_covered(self) -> None:
        values = {e.value for e in ProposalSource}
        assert values == {"fleet_analyzer", "telemetry_analyzer", "attribution_engine", "manual"}


# ======================================================================
# EvidenceReference
# ======================================================================

class TestEvidenceReference:
    def test_minimal(self) -> None:
        ref = EvidenceReference(category="ping", path="evidence/cycle.json", schema_version=1)
        assert ref.category == "ping"
        assert ref.path == "evidence/cycle.json"
        assert ref.schema_version == 1
        assert ref.summary == ""

    def test_full(self) -> None:
        ref = EvidenceReference(
            category="status", path="evidence/cycle.json", schema_version=2,
            summary="All 4 bots authenticated",
        )
        assert ref.summary == "All 4 bots authenticated"

    def test_to_json_safe(self) -> None:
        ref = EvidenceReference(category="ping", path="evidence/ping.json", schema_version=1, summary="ok")
        d = ref.to_json_safe()
        assert d["category"] == "ping"
        assert d["path"] == "evidence/ping.json"
        assert d["schema_version"] == 1
        assert d["summary"] == "ok"

    def test_to_json_safe_roundtrip(self) -> None:
        import json
        ref = EvidenceReference(category="test", path="test.json", schema_version=1)
        d = ref.to_json_safe()
        json.dumps(d)  # must not raise


# ======================================================================
# ProposalCandidate
# ======================================================================

class TestProposalCandidateMinimal:
    """Minimal ProposalCandidate creation."""

    def test_minimal_creates(self) -> None:
        candidate = ProposalCandidate(
            proposal_id="prop-001",
            source=ProposalSource.FLEET_ANALYZER,
        )
        assert candidate.proposal_id == "prop-001"
        assert candidate.source == ProposalSource.FLEET_ANALYZER
        assert candidate.created_at_utc is not None
        assert candidate.requires_human_approval is True
        assert candidate.mutation_policy == "safe_parameter_overlay_only"
        assert candidate.dry_run_only is True
        assert candidate.suggested_decision == ProposalDecision.INSUFFICIENT_EVIDENCE

    def test_candidate_id_alias(self) -> None:
        candidate = ProposalCandidate(proposal_id="prop-001", source=ProposalSource.MANUAL)
        assert candidate.candidate_id == "prop-001"

    def test_default_safety_guardrails(self) -> None:
        """Default safety guardrails must be conservative."""
        candidate = ProposalCandidate(proposal_id="p1", source=ProposalSource.FLEET_ANALYZER)
        assert candidate.requires_human_approval is True
        assert candidate.mutation_policy == "safe_parameter_overlay_only"
        assert candidate.dry_run_only is True


class TestProposalCandidateFull:
    """Full ProposalCandidate with all fields."""

    def _make_full(self) -> ProposalCandidate:
        return ProposalCandidate(
            proposal_id="prop-002",
            source=ProposalSource.TELEMETRY_ANALYZER,
            suggested_decision=ProposalDecision.ACCEPT,
            human_decision=None,
            title="Reduce max_open_trades to 2",
            description="Canary bot shows reduced performance at 3 open trades",
            rationale="Walk-forward analysis shows PF=1.2 at 2 trades vs 0.9 at 3",
            evidence_refs=[
                EvidenceReference(category="walk_forward", path="wf/metrics.json", schema_version=1),
            ],
            cycle_id="20260613T120000Z",
            proposal_type="parameter_change",
            target_bot_ids=("freqforge-canary",),
            hypothesis="reducing_max_open_trades_improves_risk_adjusted_returns",
            candidate_overlay={"max_open_trades": 2},
            expected_effect="Improved profit factor and reduced drawdown",
            risk_notes=("May reduce total volume",),
            validation_plan={"backtest": True, "walk_forward": True},
            rollback_condition="max_open_trades > 3 or drawdown > 5%",
            source_evidence_refs=("wf/metrics.json",),
            bot_id="freqforge-canary",
            regime_label="bullish",
            confidence_bucket="high",
            estimated_impact="positive",
            requires_human_approval=True,
            mutation_policy="safe_parameter_overlay_only",
            dry_run_only=True,
        )

    def test_full_creation(self) -> None:
        c = self._make_full()
        assert c.proposal_id == "prop-002"
        assert c.cycle_id == "20260613T120000Z"
        assert c.target_bot_ids == ("freqforge-canary",)
        assert c.bot_id == "freqforge-canary"
        assert c.requires_human_approval is True
        assert c.estimated_impact == "positive"

    def test_to_json_safe(self) -> None:
        c = self._make_full()
        d = c.to_json_safe()
        assert d["proposal_id"] == "prop-002"
        assert d["candidate_id"] == "prop-002"
        assert d["source"] == "telemetry_analyzer"
        assert d["suggested_decision"] == "accept"
        assert d["human_decision"] is None
        assert d["requires_human_approval"] is True
        assert d["mutation_policy"] == "safe_parameter_overlay_only"
        assert d["dry_run_only"] is True
        assert d["target_bot_ids"] == ["freqforge-canary"]
        assert d["bot_id"] == "freqforge-canary"
        assert d["estimated_impact"] == "positive"
        assert len(d["evidence_refs"]) == 1

    def test_to_json_safe_roundtrip(self) -> None:
        import json
        c = self._make_full()
        d = c.to_json_safe()
        json.dumps(d)  # must not raise

    def test_human_decision_serialized(self) -> None:
        c = self._make_full()
        c.human_decision = ProposalDecision.ACCEPT
        c.human_reviewer = "luke"
        c.reviewed_at_utc = "2026-06-29T12:00:00Z"
        d = c.to_json_safe()
        assert d["human_decision"] == "accept"
        assert d["human_reviewer"] == "luke"
        assert d["reviewed_at_utc"] == "2026-06-29T12:00:00Z"


class TestProposalCandidateEdgeCases:
    def test_empty_strings(self) -> None:
        c = ProposalCandidate(proposal_id="p1", source=ProposalSource.MANUAL)
        assert c.title == ""
        assert c.description == ""
        assert c.rationale == ""
        assert c.bot_id == ""
        assert c.cycle_id == ""

    def test_empty_lists(self) -> None:
        c = ProposalCandidate(proposal_id="p1", source=ProposalSource.MANUAL)
        assert c.evidence_refs == []
        assert c.target_bot_ids == ()
        assert c.risk_notes == ()
        assert c.source_evidence_refs == ()

    def test_requires_human_approval_false(self) -> None:
        """requires_human_approval=False must be preserved."""
        c = ProposalCandidate(proposal_id="p1", source=ProposalSource.MANUAL, requires_human_approval=False)
        assert c.requires_human_approval is False
        d = c.to_json_safe()
        assert d["requires_human_approval"] is False

    def test_dry_run_only_false(self) -> None:
        c = ProposalCandidate(proposal_id="p1", source=ProposalSource.MANUAL, dry_run_only=False)
        assert c.dry_run_only is False

    def test_estimated_impact_default(self) -> None:
        c = ProposalCandidate(proposal_id="p1", source=ProposalSource.MANUAL)
        assert c.estimated_impact == "unknown"

    def test_regime_label_none(self) -> None:
        c = ProposalCandidate(proposal_id="p1", source=ProposalSource.MANUAL)
        assert c.regime_label is None

    def test_confidence_bucket_none(self) -> None:
        c = ProposalCandidate(proposal_id="p1", source=ProposalSource.MANUAL)
        assert c.confidence_bucket is None

    def test_created_at_utc_format(self) -> None:
        c = ProposalCandidate(proposal_id="p1", source=ProposalSource.MANUAL)
        assert "T" in c.created_at_utc
        assert c.created_at_utc.endswith("Z")
