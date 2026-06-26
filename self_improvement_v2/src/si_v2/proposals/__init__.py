"""SI v2 proposals package — candidate builder and schema."""

from si_v2.proposals.candidate_builder import (
    BotMetrics,
    FleetMetrics,
    ProposalCandidate,
    build_candidate_proposals,
    build_fleet_metrics_from_cycle,
)
from si_v2.proposal.schema import (
    EvidenceReference,
    ProposalCandidate as SchemaProposalCandidate,
    ProposalDecision,
    ProposalSource,
)

__all__ = [
    "BotMetrics",
    "EvidenceReference",
    "FleetMetrics",
    "ProposalCandidate",
    "ProposalDecision",
    "ProposalSource",
    "SchemaProposalCandidate",
    "build_candidate_proposals",
    "build_fleet_metrics_from_cycle",
]
