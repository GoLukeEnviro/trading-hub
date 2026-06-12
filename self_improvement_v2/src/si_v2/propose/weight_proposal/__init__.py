"""SI v2 Weight Proposal Engine (issue #63).

The Weight Proposal Engine is a **review-only** recommendation engine.
It consumes ``ProposalEvidenceRecord`` instances (issue #62), scores
each (source, regime) candidate against the ``ScoringPolicy`` (issue
#35), and produces a batch of bounded, sanitized, byte-stable
``WeightProposal`` artifacts that humans (or future approval-gated
issues) may act on.

It is **never** an application path:

- It never reads or writes live strategy / Freqtrade configuration.
- It never writes a runtime weight.
- It never marks a proposal as approved.
- It never auto-promotes a proposal.
- It never imports or interacts with the Freqtrade API, the Docker
  daemon, the scheduler, the cron, or the exchange.

Hard safety rules:

- Negative expectancy never produces an increase.
- Sparse, stale, conflicting, or low-confidence evidence always
  REJECTs or DEFERs.
- Every delta respects the policy's ``maximum_proposal_delta`` cap.
- Weights remain within ``[minimum_weight, maximum_weight]``.
- Each normalization group sums exactly to ``1.0`` after rounding.
- Normalization cannot reverse a REJECT decision on a candidate.
- ``human_approval_required=True`` on every emitted proposal.
- All outputs are sanitized (no secrets, no raw ledger records, no
  filesystem paths in the rendered reports).

Public surface (re-exported from this package):

    CurrentWeight
    WeightProposalRequest
    WeightProposal
    WeightProposalBatch
    NormalizationGroup
    BatchFingerprint
    WeightProposalEngine
    render_sanitized_json_proposal
    render_sanitized_markdown_report
    write_proposal_artifact
    PROPOSAL_SCHEMA_VERSION
"""

from __future__ import annotations

from si_v2.propose.weight_proposal.audit import (
    render_sanitized_json_proposal,
    render_sanitized_markdown_report,
    write_proposal_artifact,
)
from si_v2.propose.weight_proposal.engine import WeightProposalEngine
from si_v2.propose.weight_proposal.models import (
    PROPOSAL_SCHEMA_VERSION,
    BatchFingerprint,
    CurrentWeight,
    NormalizationGroup,
    WeightProposal,
    WeightProposalBatch,
    WeightProposalRequest,
)

__all__ = [
    "PROPOSAL_SCHEMA_VERSION",
    "BatchFingerprint",
    "CurrentWeight",
    "NormalizationGroup",
    "WeightProposal",
    "WeightProposalBatch",
    "WeightProposalEngine",
    "WeightProposalRequest",
    "render_sanitized_json_proposal",
    "render_sanitized_markdown_report",
    "write_proposal_artifact",
]
