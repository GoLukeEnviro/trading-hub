"""SI v2 proposal candidate module."""

from si_v2.proposal.renderer import render_proposal_list, render_proposal_packet
from si_v2.proposal.schema import (
    EvidenceReference,
    ProposalCandidate,
    ProposalDecision,
    ProposalSource,
)

__all__ = [
    "EvidenceReference",
    "ProposalCandidate",
    "ProposalDecision",
    "ProposalSource",
    "render_proposal_list",
    "render_proposal_packet",
]
