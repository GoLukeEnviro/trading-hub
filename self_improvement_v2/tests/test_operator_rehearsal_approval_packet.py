"""Tests for #138: Operator approval packet template.

Verifies the approval packet template exists, defines allowed and
forbidden actions, has human approval fields, contains a non-live
statement, and references #135-#137.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

APPROVAL_PACKET_PATH = Path(__file__).resolve().parent.parent / "rehearsal" / "operator_rehearsal_approval_packet.md"


# ──────────────────────────────────────────────
# Artifact existence
# ──────────────────────────────────────────────


class TestApprovalPacketArtifactExists:
    """The approval packet markdown must exist."""

    def test_packet_file_exists(self) -> None:
        assert APPROVAL_PACKET_PATH.is_file(), (
            f"Approval packet not found: {APPROVAL_PACKET_PATH}"
        )

    def test_packet_file_nonempty(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert len(text) > 500, "Approval packet file is too short"


# ──────────────────────────────────────────────
# Required sections
# ──────────────────────────────────────────────


class TestApprovalPacketRequiredSections:
    """The approval packet must contain specific sections."""

    REQUIRED_HEADERS: ClassVar[list[str]] = [
        "Proposal Reference",
        "Planning Gate Verification",
        "Allowed Actions",
        "Forbidden Actions",
        "Human Approval Fields",
        "Non-Live Statement",
        "References",
    ]

    def test_all_required_headers_present(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        for header in self.REQUIRED_HEADERS:
            assert re.search(rf"## \d+\.\s*{re.escape(header)}\s*$", text, re.MULTILINE), (
                f"Required header '{header}' not found in approval packet"
            )


# ──────────────────────────────────────────────
# Allowed actions
# ──────────────────────────────────────────────


class TestApprovalPacketAllowedActions:
    """The packet must define allowed actions within rehearsal scope."""

    def test_allowed_actions_section_exists(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert "Allowed Actions" in text, "Missing Allowed Actions section"

    def test_read_only_file_inspection_allowed(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert "Read-only file" in text or "read-only file" in text.lower(), (
            "Missing read-only file inspection in allowed actions"
        )

    def test_read_only_sqlite_allowed(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert "SQLite" in text, "Missing SQLite query in allowed actions"


# ──────────────────────────────────────────────
# Forbidden actions
# ──────────────────────────────────────────────


class TestApprovalPacketForbiddenActions:
    """The packet must define forbidden actions."""

    FORBIDDEN_ACTIONS: ClassVar[list[str]] = [
        "dry_run",
        "live trading",
        "exchange",
        "Docker",
        "deploy",
        "secret",
        "API key",
        "financial exposure",
    ]

    def test_forbidden_actions_section_exists(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert "Forbidden Actions" in text, "Missing Forbidden Actions section"

    def test_common_forbidden_patterns_present(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        for action in self.FORBIDDEN_ACTIONS:
            assert action.lower() in text.lower(), (
                f"Forbidden action '{action}' not mentioned"
            )


# ──────────────────────────────────────────────
# Human approval fields
# ──────────────────────────────────────────────


class TestApprovalPacketHumanFields:
    """The packet must have explicit human approval fields."""

    REQUIRED_FIELDS: ClassVar[list[str]] = [
        "Operator Name",
        "Operator Role",
        "Review Date",
        "Approval Token",
        "Approval Scope",
        "Duration",
    ]

    def test_human_approval_fields_present(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        for field in self.REQUIRED_FIELDS:
            assert field.lower() in text.lower(), (
                f"Required human approval field '{field}' not found"
            )

    def test_approval_token_format_defined(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert "APPROVE_REHEARSAL_" in text, (
            "Missing approval token format (APPROVE_REHEARSAL_)"
        )


# ──────────────────────────────────────────────
# Non-live statement
# ──────────────────────────────────────────────


class TestApprovalPacketNonLive:
    """The packet must contain a non-live statement."""

    def test_non_live_statement_present(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert "Non-Live Statement" in text, "Missing Non-Live Statement section"

    def test_does_not_authorise_live_trading(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert "does not authorise" in text.lower(), (
            "Missing 'does not authorise' language in non-live statement"
        )

    def test_abort_on_violation_mentioned(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert "abort" in text.lower(), (
            "Missing abort-on-violation language"
        )


# ──────────────────────────────────────────────
# References to #135-#137
# ──────────────────────────────────────────────


class TestApprovalPacketReferences:
    """The packet must reference #135, #136, #137."""

    def test_references_section_exists(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert "References" in text, "Missing References section"

    def test_references_135(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert "#135" in text or "135" in text, "Missing reference to #135"

    def test_references_136(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert "#136" in text or "136" in text, "Missing reference to #136"

    def test_references_137(self) -> None:
        text = APPROVAL_PACKET_PATH.read_text(encoding="utf-8")
        assert "#137" in text or "137" in text, "Missing reference to #137"
