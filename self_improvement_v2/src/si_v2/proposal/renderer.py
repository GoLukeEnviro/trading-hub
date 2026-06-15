"""Proposal packet renderer for SI v2.

Generates human-readable proposal packets from ProposalCandidate objects
for the human-review workflow.
"""

from __future__ import annotations

from datetime import UTC, datetime

from si_v2.proposal.schema import ProposalCandidate


def render_proposal_packet(candidate: ProposalCandidate) -> str:
    """Render a proposal candidate as a human-readable markdown packet.

    Args:
        candidate: ProposalCandidate to render.

    Returns:
        Markdown string suitable for display or Telegram delivery.
    """
    lines: list[str] = []
    lines.append("---")
    lines.append(f"# Proposal: {candidate.title}")
    lines.append(f"**ID:** {candidate.proposal_id}")
    lines.append(f"**Source:** {candidate.source.value}")
    lines.append(f"**Created:** {candidate.created_at_utc}")
    lines.append(f"**Bot:** {candidate.bot_id}")
    lines.append("")

    lines.append("## Description")
    lines.append(candidate.description)
    lines.append("")

    lines.append("## Rationale")
    lines.append(candidate.rationale)
    lines.append("")

    lines.append("## Suggested Decision")
    lines.append(f"- **Decision:** {candidate.suggested_decision.value}")
    lines.append(f"- **Regime:** {candidate.regime_label or 'unknown'}")
    lines.append(f"- **Confidence:** {candidate.confidence_bucket or 'unknown'}")
    lines.append(f"- **Estimated Impact:** {candidate.estimated_impact}")
    lines.append("")

    if candidate.evidence_refs:
        lines.append("## Supporting Evidence")
        for ref in candidate.evidence_refs:
            lines.append(f"- **{ref.category}:** {ref.summary}")
            lines.append(f"  - Path: `{ref.path}`")
            lines.append(f"  - Schema: v{ref.schema_version}")
        lines.append("")

    lines.append("## Safety Constraints")
    lines.append(f"- Requires human approval: {candidate.requires_human_approval}")
    lines.append(f"- Mutation policy: {candidate.mutation_policy}")
    lines.append(f"- Dry-run only: {candidate.dry_run_only}")
    lines.append("")

    lines.append("## Review Status")
    if candidate.human_decision:
        lines.append(f"- **Human decision:** {candidate.human_decision.value}")
        lines.append(f"- **Reviewer:** {candidate.human_reviewer or 'unknown'}")
        lines.append(f"- **Reviewed at:** {candidate.reviewed_at_utc or 'unknown'}")
    else:
        lines.append("- **Status:** Pending human review")
    lines.append("")

    lines.append(f"*Rendered at {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}*")
    lines.append("---")
    return "\n".join(lines)


def render_proposal_list(candidates: list[ProposalCandidate]) -> str:
    """Render a summary list of proposal candidates.

    Args:
        candidates: List of ProposalCandidate objects.

    Returns:
        Markdown summary table.
    """
    lines: list[str] = []
    lines.append("# Proposal Queue Summary")
    lines.append("")
    lines.append(f"**Total pending:** {len(candidates)}")
    lines.append("")
    lines.append("| ID | Title | Bot | Decision | Impact |")
    lines.append("|----|-------|-----|----------|--------|")
    for c in candidates:
        lines.append(
            f"| {c.proposal_id} | {c.title[:40]} | {c.bot_id} | "
            f"{c.suggested_decision.value} | {c.estimated_impact} |"
        )
    lines.append("")
    return "\n".join(lines)
