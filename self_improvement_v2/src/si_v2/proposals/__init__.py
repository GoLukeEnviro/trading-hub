"""SI v2 proposals package — candidate builder and schema."""

from si_v2.proposal.schema import (
    EvidenceReference,
    ProposalDecision,
    ProposalSource,
)
from si_v2.proposal.schema import (
    ProposalCandidate as SchemaProposalCandidate,
)
from si_v2.proposals.candidate_builder import (
    BotMetrics,
    FleetMetrics,
    ProposalCandidate,
    build_candidate_proposals,
    build_fleet_metrics_from_cycle,
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
