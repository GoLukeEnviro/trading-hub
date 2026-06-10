"""Approval gate for human-in-the-loop review of mutations.

Provides the ApprovalGateManager for managing approval state.
"""

from __future__ import annotations

from si_v2.state.schemas import ApprovalGate


class ApprovalGateManager:
    """Manages the approval state for mutation candidates."""

    def check_approval(self, gate: ApprovalGate) -> bool:
        """Check whether a mutation candidate has been approved.

        Args:
            gate: ApprovalGate state to check.

        Returns:
            True if the candidate is approved.
        """
        return gate.approved

    def create_gate(self, candidate_sha256: str, approved: bool = False) -> ApprovalGate:
        """Create a new approval gate for a candidate.

        Args:
            candidate_sha256: SHA256 hash of the candidate.
            approved: Initial approval state (default: False).

        Returns:
            New ApprovalGate instance.
        """
        return ApprovalGate(approved=approved, candidate_sha256=candidate_sha256)
