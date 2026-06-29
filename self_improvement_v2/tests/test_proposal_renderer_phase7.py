"""Tests for proposal/renderer.py — proposal packet and list rendering.

Tests cover:
- render_proposal_packet (minimal, full, blocked, missing fields)
- render_proposal_list (empty, single, multiple)
- Deterministic output
- Safety guardrails visible in output
"""

from __future__ import annotations

from datetime import UTC, datetime

from si_v2.proposal.renderer import render_proposal_list, render_proposal_packet
from si_v2.proposal.schema import (
    EvidenceReference,
    ProposalCandidate,
    ProposalDecision,
    ProposalSource,
)


def _make_candidate(
    proposal_id: str = "prop-001",
    title: str = "Test Proposal",
    description: str = "A test proposal",
    rationale: str = "Because testing is important",
    bot_id: str = "freqforge",
    source: ProposalSource = ProposalSource.FLEET_ANALYZER,
    suggested_decision: ProposalDecision = ProposalDecision.INSUFFICIENT_EVIDENCE,
    requires_human_approval: bool = True,
    **overrides: object,
) -> ProposalCandidate:
    kwargs: dict = {
        "proposal_id": proposal_id,
        "source": source,
        "title": title,
        "description": description,
        "rationale": rationale,
        "bot_id": bot_id,
        "suggested_decision": suggested_decision,
        "requires_human_approval": requires_human_approval,
    }
    kwargs.update(overrides)
    return ProposalCandidate(**kwargs)


class TestRenderProposalPacket:
    def test_minimal_proposal(self) -> None:
        c = _make_candidate()
        output = render_proposal_packet(c)
        assert "prop-001" in output
        assert "Test Proposal" in output
        assert "A test proposal" in output
        assert "Because testing is important" in output
        assert "freqforge" in output
        assert "Pending human review" in output

    def test_full_proposal(self) -> None:
        c = _make_candidate(
            proposal_id="prop-002",
            title="Reduce max_open_trades",
            description="Canary shows reduced performance",
            rationale="PF=1.2 at 2 trades vs 0.9 at 3",
            bot_id="freqforge-canary",
            source=ProposalSource.TELEMETRY_ANALYZER,
            suggested_decision=ProposalDecision.ACCEPT,
            regime_label="bullish",
            confidence_bucket="high",
            estimated_impact="positive",
            evidence_refs=[
                EvidenceReference(category="walk_forward", path="wf/metrics.json", schema_version=1, summary="PF improved"),
            ],
        )
        output = render_proposal_packet(c)
        assert "prop-002" in output
        assert "Reduce max_open_trades" in output
        assert "freqforge-canary" in output
        assert "telemetry_analyzer" in output
        assert "accept" in output
        assert "bullish" in output
        assert "high" in output
        assert "positive" in output
        assert "walk_forward" in output
        assert "wf/metrics.json" in output
        assert "Pending human review" in output

    def test_blocked_proposal(self) -> None:
        c = _make_candidate(
            suggested_decision=ProposalDecision.REJECT,
            rationale="Drawdown exceeds threshold",
        )
        output = render_proposal_packet(c)
        assert "reject" in output
        assert "Drawdown exceeds threshold" in output
        assert "Pending human review" in output

    def test_reviewed_proposal(self) -> None:
        c = _make_candidate(
            suggested_decision=ProposalDecision.ACCEPT,
            human_decision=ProposalDecision.ACCEPT,
            human_reviewer="luke",
            reviewed_at_utc="2026-06-29T12:00:00Z",
        )
        output = render_proposal_packet(c)
        assert "accept" in output
        assert "luke" in output
        assert "2026-06-29" in output
        assert "Pending human review" not in output

    def test_safety_guardrails_visible(self) -> None:
        c = _make_candidate()
        output = render_proposal_packet(c)
        assert "True" in output  # requires_human_approval=True
        assert "safe_parameter_overlay_only" in output
        assert "Dry-run only" in output

    def test_missing_optional_fields(self) -> None:
        """Missing optional fields should not crash."""
        c = _make_candidate(regime_label=None, confidence_bucket=None, evidence_refs=[])
        output = render_proposal_packet(c)
        assert "unknown" in output  # regime and confidence fallback
        assert "prop-001" in output

    def test_no_evidence_refs(self) -> None:
        c = _make_candidate(evidence_refs=[])
        output = render_proposal_packet(c)
        assert "Supporting Evidence" not in output

    def test_deterministic_output(self) -> None:
        """Same input produces same output (time-dependent line excluded)."""
        c = _make_candidate()
        output1 = render_proposal_packet(c)
        output2 = render_proposal_packet(c)
        # Remove the timestamp line before comparing
        lines1 = [l for l in output1.split("\n") if not l.startswith("*Rendered at")]
        lines2 = [l for l in output2.split("\n") if not l.startswith("*Rendered at")]
        assert lines1 == lines2


class TestRenderProposalList:
    def test_empty_list(self) -> None:
        output = render_proposal_list([])
        assert "0" in output or "Total pending: 0" in output

    def test_single_proposal(self) -> None:
        c = _make_candidate()
        output = render_proposal_list([c])
        assert "prop-001" in output
        assert "Test Proposal" in output
        assert "freqforge" in output
        assert "insufficient_evidence" in output

    def test_multiple_proposals(self) -> None:
        candidates = [
            _make_candidate(proposal_id="p1", title="First", bot_id="bot-1"),
            _make_candidate(proposal_id="p2", title="Second", bot_id="bot-2"),
        ]
        output = render_proposal_list(candidates)
        assert "p1" in output
        assert "p2" in output
        assert "First" in output
        assert "Second" in output
        assert "bot-1" in output
        assert "bot-2" in output
        assert "2" in output  # total pending

    def test_deterministic_order(self) -> None:
        """List order should match input order."""
        candidates = [
            _make_candidate(proposal_id="p2", title="B", bot_id="bot-2"),
            _make_candidate(proposal_id="p1", title="A", bot_id="bot-1"),
        ]
        output = render_proposal_list(candidates)
        # p2 should appear before p1 (input order preserved)
        assert output.index("p2") < output.index("p1")
