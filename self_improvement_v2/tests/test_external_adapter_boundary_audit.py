"""Tests for the External Adapter Boundary Audit (#131).

Verifies that:
- All adapters are classified correctly.
- Write-capable adapters are gated and disabled-by-default.
- Read-only adapters without Docker are not gated.
- The audit JSON is valid and self-consistent.
"""

from __future__ import annotations

import json
from pathlib import Path

AUDIT_PATH = Path(__file__).resolve().parent.parent / "governance" / "external_adapter_boundary_audit.json"


class TestExternalAdapterBoundaryAudit:
    """Tests for the External Adapter Boundary Audit."""

    def test_audit_exists(self) -> None:
        """The audit file must exist."""
        assert AUDIT_PATH.is_file(), f"Audit not found: {AUDIT_PATH}"

    def test_audit_is_valid_json(self) -> None:
        """The audit file must parse as valid JSON."""
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        assert data["title"] == "External Adapter Boundary Audit"
        assert data["version"] == "1.0"

    def test_all_adapters_have_required_fields(self) -> None:
        """Every adapter entry must have all required fields."""
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        required_fields = [
            "name", "module", "class", "classification",
            "gate_required", "default_state", "safe_for_rehearsal",
            "risk_level", "write_capable",
        ]
        for adapter in data["adapters"]:
            for field in required_fields:
                assert field in adapter, (
                    f"Adapter '{adapter.get('name', 'unknown')}' missing field: {field}"
                )

    def test_write_capable_adapters_require_gate(self) -> None:
        """All write-capable adapters must have gate_required=true and be disabled-by-default."""
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        for adapter in data["adapters"]:
            if adapter["write_capable"]:
                assert adapter["gate_required"] is True, (
                    f"Write-capable adapter '{adapter['name']}' must have gate_required=true"
                )
                assert adapter["default_state"] == "disabled-by-default", (
                    f"Write-capable adapter '{adapter['name']}' must be disabled-by-default"
                )
                assert adapter["safe_for_rehearsal"] is False, (
                    f"Write-capable adapter '{adapter['name']}' must NOT be safe for rehearsal"
                )

    def test_read_only_adapters_without_docker_no_gate(self) -> None:
        """Pure read-only adapters (non-Docker) must not require a gate."""
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        for adapter in data["adapters"]:
            if adapter["classification"] == "read-only":
                assert adapter["gate_required"] is False, (
                    f"Read-only adapter '{adapter['name']}' should not require a gate"
                )
                assert adapter["default_state"] == "enabled", (
                    f"Read-only adapter '{adapter['name']}' should default to enabled"
                )

    def test_read_only_with_docker_adapters_require_gate(self) -> None:
        """Read-only adapters with Docker access must require a gate."""
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        for adapter in data["adapters"]:
            if adapter["classification"] == "read-only-with-docker":
                assert adapter["gate_required"] is True, (
                    f"Docker adapter '{adapter['name']}' must require a gate"
                )
                assert adapter["default_state"] == "disabled-by-default", (
                    f"Docker adapter '{adapter['name']}' must be disabled-by-default"
                )

    def test_no_unsafe_adapters_safe_for_rehearsal(self) -> None:
        """No adapter with risk_level >= medium may be safe for rehearsal."""
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        for adapter in data["adapters"]:
            if adapter["risk_level"] in ("medium", "high", "critical"):
                assert adapter["safe_for_rehearsal"] is False, (
                    f"Adapter '{adapter['name']}' with risk level '{adapter['risk_level']}' "
                    f"must not be safe for rehearsal"
                )

    def test_summary_counts_match(self) -> None:
        """The summary counts must be consistent with the adapter list."""
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        adapters = data["adapters"]
        summary = data["summary"]

        assert summary["total_adapters"] == len(adapters)
        assert summary["write_capable"] == sum(1 for a in adapters if a["write_capable"])
        assert summary["disabled_by_default"] == sum(
            1 for a in adapters if a["default_state"] == "disabled-by-default"
        )
        assert summary["gate_required"] == sum(1 for a in adapters if a["gate_required"])
        assert summary["safe_for_rehearsal"] == sum(
            1 for a in adapters if a["safe_for_rehearsal"]
        )

    def test_rehearsal_blocked_count(self) -> None:
        """rehearsal_blocked = total - safe_for_rehearsal."""
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        adapters = data["adapters"]
        summary = data["summary"]
        safe_count = sum(1 for a in adapters if a["safe_for_rehearsal"])
        assert summary["rehearsal_blocked"] == len(adapters) - safe_count

    def test_has_safety_notice(self) -> None:
        """Audit must contain a safety notice."""
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        assert "safety_notice" in data
        assert "does not authorise" in data["safety_notice"]

    def test_has_rules(self) -> None:
        """Audit must have safety rules."""
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        assert "rules" in data
        assert len(data["rules"]) >= 4
