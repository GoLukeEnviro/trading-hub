"""Tests for #151: Cross-artifact semantic consistency engine.

Verifies that ``run_semantic_consistency`` correctly detects missing
artifacts, missing cross-references, contradictory verdicts, orphan
references, duplicate IDs, and stop-matrix default-verdict violations.
"""

from __future__ import annotations

import json
from pathlib import Path

from rehearsal.planning_models import (
    ReasonCode,
    ValidationResult,
    Verdict,
)
from rehearsal.semantic_consistency import run_semantic_consistency

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gate_doc(
    refs: str | None = None,
    verdicts: str | None = None,
) -> str:
    """Build a #135 gate doc with overridable content."""
    r = refs or "Prerequisites: #127, #128, #129, #130, #131, #132, #136, #137, #139"
    v = verdicts or (
        "### 5. Gate Verdicts\n"
        "| Verdict | Meaning | Next Action |\n"
        "|---------|---------|-------------|\n"
        "| **GREEN** | Pass | Proceed |\n"
        "| **YELLOW** | Warning | Proceed with awareness |\n"
        "| **RED** | Blocker | Do not proceed |\n"
    )
    return (
        "# Controlled Rehearsal Planning Gate\n"
        "*Created as part of #135*\n\n"
        f"{r}\n\n"
        f"{v}\n\n"
        "*Created as part of #135*\n"
    )


def _stop_matrix(
    default_verdict: str = "BLOCKED",
    conditions: list[dict[str, object]] | None = None,
) -> str:
    """Build a #136 stop-condition matrix JSON."""
    data: dict[str, object] = {
        "title": "Stop-Condition Matrix",
        "version": "1.0",
        "default_verdict": default_verdict,
        "generated_by": "SI v2 Governance (#136)",
        "conditions": conditions or [],
        "verdict_map": {},
        "action_map": {},
    }
    return json.dumps(data, indent=2)


def _evidence_plan() -> str:
    return "# Evidence Bundle Plan\n*Created as part of #137*\n"


def _approval_packet(
    refs: str | None = None,
) -> str:
    """Build a #138 approval packet doc."""
    r = refs or "References: #135, #136, #137, #139"
    return (
        "# Operator Rehearsal Approval Packet\n"
        "*Created as part of #138*\n\n"
        f"{r}\n\n"
        "*Created as part of #138*\n"
    )


def _observation_plan() -> str:
    return "# Read-Only Observation Plan\n*Created as part of #139*\n"


def _readiness_record(
    refs: str | None = None,
    verdicts: str | None = None,
) -> str:
    """Build a #140 readiness record doc."""
    r = refs or "References: #135, #136, #137, #138, #139"
    v = verdicts or (
        "### 4. Overall Readiness Verdict\n"
        "| Verdict | Meaning |\n"
        "|---------|---------|\n"
        "| **GREEN** | Proceed |\n"
        "| **YELLOW** | Proceed with operator acknowledgment |\n"
        "| **RED** | Do not proceed |\n"
    )
    return (
        "# Rehearsal Readiness Decision Record\n"
        "*Created as part of #140*\n\n"
        f"{r}\n\n"
        f"{v}\n\n"
        "*Created as part of #140*\n"
    )


def _prereq_doc(issue: str) -> str:
    """Build a minimal prerequisite artifact doc."""
    return f"# {issue} Artifact\n*Created as part of {issue}*\n"


def _valid_artifact_set() -> dict[str, str]:
    """Return a dict mapping filename → content for a valid artifact set.

    All required issues #127-#140 are present with correct cross-references
    and consistent verdicts.
    """
    return {
        "test_live_trading_invariants.py": _prereq_doc("#127"),
        "dry_run_evidence_schema.json": _prereq_doc("#128"),
        "runtime_preflight_checklist.md": _prereq_doc("#129"),
        "rehearsal_report_template.md": _prereq_doc("#130"),
        "external_adapter_boundary_audit.json": _prereq_doc("#131"),
        "rehearsal_artifact_manifest.json": _prereq_doc("#132"),
        "controlled_rehearsal_planning_gate.md": _gate_doc(),
        "rehearsal_stop_condition_matrix.json": _stop_matrix(),
        "rehearsal_evidence_bundle_plan.md": _evidence_plan(),
        "operator_rehearsal_approval_packet.md": _approval_packet(),
        "read_only_observation_plan.md": _observation_plan(),
        "rehearsal_readiness_decision_record.md": _readiness_record(),
    }


def _write_artifacts(artifacts: dict[str, str], tmpdir: Path) -> list[str]:
    """Write artifacts to *tmpdir* and return sorted list of absolute paths."""
    paths: list[str] = []
    for name, content in artifacts.items():
        p = tmpdir / name
        p.write_text(content, encoding="utf-8")
        paths.append(str(p.resolve()))
    return sorted(paths)


# ---------------------------------------------------------------------------
# Pass / happy path
# ---------------------------------------------------------------------------


class TestSemanticConsistencyPass:
    """A complete, valid artifact set should produce zero BLOCKED findings."""

    def test_valid_artifact_set_passes(self, tmp_path: Path) -> None:
        paths = _write_artifacts(_valid_artifact_set(), tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        blocked = [f for f in result.findings if f.verdict == Verdict.BLOCKED]
        assert not blocked, f"Expected zero BLOCKED findings, got: {blocked}"

    def test_valid_artifact_set_no_missing_prereqs(self, tmp_path: Path) -> None:
        paths = _write_artifacts(_valid_artifact_set(), tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        prereq_missing = [f for f in result.findings if f.reason_code == ReasonCode.ARTIFACT_MISSING]
        assert not prereq_missing, f"Expected no ARTIFACT_MISSING, got: {prereq_missing}"

    def test_valid_artifact_set_no_orphans(self, tmp_path: Path) -> None:
        paths = _write_artifacts(_valid_artifact_set(), tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        orphans = [f for f in result.findings if f.reason_code == ReasonCode.REFERENCE_ORPHAN]
        assert not orphans, f"Expected no orphan refs, got: {orphans}"


# ---------------------------------------------------------------------------
# Missing prerequisite artifacts
# ---------------------------------------------------------------------------


class TestMissingPrerequisites:
    """When #127-#132 artifacts are missing, engine should report ARTIFACT_MISSING."""

    def test_missing_all_prereqs(self, tmp_path: Path) -> None:
        artifacts = _valid_artifact_set()
        for key in list(artifacts.keys()):
            prereq_iss = ("#127", "#128", "#129", "#130", "#131", "#132")
            if any(iss in artifacts[key] for iss in prereq_iss) and key != "controlled_rehearsal_planning_gate.md":
                del artifacts[key]
        # Also drop the prereq docs themselves
        for iss in ("#127", "#128", "#129", "#130", "#131", "#132"):
            artifacts = {k: v for k, v in artifacts.items() if iss not in v}
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        missing = [f for f in result.findings if f.reason_code == ReasonCode.ARTIFACT_MISSING]
        assert len(missing) >= 1, "Expected at least one ARTIFACT_MISSING finding"

    def test_missing_single_prereq(self, tmp_path: Path) -> None:
        artifacts = _valid_artifact_set()
        # Remove #128 artifact
        artifacts = {k: v for k, v in artifacts.items() if "#128" not in v}
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        missing = [f for f in result.findings if f.reason_code == ReasonCode.ARTIFACT_MISSING]
        assert any("#128" in f.message for f in missing), "Expected ARTIFACT_MISSING for #128"


# ---------------------------------------------------------------------------
# Missing cross-references
# ---------------------------------------------------------------------------


class TestMissingCrossReferences:
    """When #135, #138, or #140 omit required references, engine flags REFERENCE_MISSING."""

    def test_gate_missing_stop_condition_ref(self, tmp_path: Path) -> None:
        artifacts = _valid_artifact_set()
        # Gate doc without #136 reference
        artifacts["controlled_rehearsal_planning_gate.md"] = _gate_doc(
            refs="Prerequisites: #127, #128, #129, #130, #131, #132, #137, #139"
        )
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        ref_missing = [f for f in result.findings if f.reason_code == ReasonCode.REFERENCE_MISSING]
        assert any("#136" in f.message for f in ref_missing), "Expected REFERENCE_MISSING for #136"

    def test_approval_missing_gate_ref(self, tmp_path: Path) -> None:
        artifacts = _valid_artifact_set()
        artifacts["operator_rehearsal_approval_packet.md"] = _approval_packet(
            refs="References: #136, #137, #139"
        )
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        ref_missing = [f for f in result.findings if f.reason_code == ReasonCode.REFERENCE_MISSING]
        assert any("#135" in f.message for f in ref_missing), "Expected REFERENCE_MISSING for #135"

    def test_readiness_missing_approval_ref(self, tmp_path: Path) -> None:
        artifacts = _valid_artifact_set()
        artifacts["rehearsal_readiness_decision_record.md"] = _readiness_record(
            refs="References: #135, #136, #137, #139"
        )
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        ref_missing = [f for f in result.findings if f.reason_code == ReasonCode.REFERENCE_MISSING]
        assert any("#138" in f.message for f in ref_missing), "Expected REFERENCE_MISSING for #138"


# ---------------------------------------------------------------------------
# Verdict consistency
# ---------------------------------------------------------------------------


class TestVerdictConsistency:
    """Checks around verdict definitions and stop-matrix default."""

    def test_stop_matrix_not_blocked_fails(self, tmp_path: Path) -> None:
        artifacts = _valid_artifact_set()
        artifacts["rehearsal_stop_condition_matrix.json"] = _stop_matrix(
            default_verdict="GREEN"
        )
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        not_blocked = [
            f for f in result.findings
            if f.reason_code == ReasonCode.STOP_MATRIX_NOT_BLOCKED
        ]
        assert len(not_blocked) == 1, "Expected STOP_MATRIX_NOT_BLOCKED finding"

    def test_gate_missing_verdict(self, tmp_path: Path) -> None:
        artifacts = _valid_artifact_set()
        artifacts["controlled_rehearsal_planning_gate.md"] = _gate_doc(
            verdicts=(
                "### 5. Gate Verdicts\n"
                "| Verdict | Meaning | Next Action |\n"
                "|---------|---------|-------------|\n"
                "| **GREEN** | Pass | Proceed |\n"
            )
        )
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        missing = [f for f in result.findings if f.reason_code == ReasonCode.MISSING_REQUIRED_FIELD]
        verdict_missing = [f for f in missing if "135" in f.check_id]
        assert len(verdict_missing) >= 1, "Expected MISSING_REQUIRED_FIELD for gate verdicts"

    def test_readiness_missing_verdict(self, tmp_path: Path) -> None:
        artifacts = _valid_artifact_set()
        artifacts["rehearsal_readiness_decision_record.md"] = _readiness_record(
            verdicts=(
                "### 4. Overall Readiness Verdict\n"
                "| Verdict | Meaning |\n"
                "|---------|---------|\n"
                "| **GREEN** | Proceed |\n"
            )
        )
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        missing = [f for f in result.findings if f.reason_code == ReasonCode.MISSING_REQUIRED_FIELD]
        verdict_missing = [f for f in missing if "140" in f.check_id]
        assert len(verdict_missing) >= 1, "Expected MISSING_REQUIRED_FIELD for readiness verdicts"


# ---------------------------------------------------------------------------
# Contradictory verdicts
# ---------------------------------------------------------------------------


class TestContradictoryVerdicts:
    """Gate RED associated with proceed, or readiness GREEN with block."""

    def test_gate_red_with_proceed_contradicts(self, tmp_path: Path) -> None:
        artifacts = _valid_artifact_set()
        # Make gate doc associate RED with "proceed" (contradictory)
        artifacts["controlled_rehearsal_planning_gate.md"] = _gate_doc(
            verdicts=(
                "### 5. Gate Verdicts\n"
                "| Verdict | Meaning | Next Action |\n"
                "|---------|---------|-------------|\n"
                "| **GREEN** | Pass | Proceed |\n"
                "| **YELLOW** | Warning | Proceed with awareness |\n"
                "| **RED** | Warning | Proceed with caution |\n"
            )
        )
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        contradict = [
            f for f in result.findings
            if f.reason_code == ReasonCode.CONTRADICTORY_VERDICT
        ]
        assert any("135" in f.check_id for f in contradict), (
            "Expected CONTRADICTORY_VERDICT for #135 RED with proceed"
        )

    def test_readiness_green_with_block_contradicts(self, tmp_path: Path) -> None:
        artifacts = _valid_artifact_set()
        # Make readiness doc associate GREEN with "do not proceed" (contradictory)
        artifacts["rehearsal_readiness_decision_record.md"] = _readiness_record(
            verdicts=(
                "### 4. Overall Readiness Verdict\n"
                "| Verdict | Meaning |\n"
                "|---------|---------|\n"
                "| **GREEN** | Do not proceed |\n"
                "| **YELLOW** | Proceed with operator acknowledgment |\n"
                "| **RED** | Do not proceed |\n"
            )
        )
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        contradict = [
            f for f in result.findings
            if f.reason_code == ReasonCode.CONTRADICTORY_VERDICT
        ]
        assert any("140" in f.check_id for f in contradict), (
            "Expected CONTRADICTORY_VERDICT for #140 GREEN with do-not-proceed"
        )


# ---------------------------------------------------------------------------
# Orphan references
# ---------------------------------------------------------------------------


class TestOrphanReferences:
    """References to issues not in the artifact set should be flagged."""

    def test_orphan_ref_in_gate(self, tmp_path: Path) -> None:
        artifacts = _valid_artifact_set()
        # Gate doc references an issue #999 that doesn't exist in the set
        artifacts["controlled_rehearsal_planning_gate.md"] = _gate_doc(
            refs="Prerequisites: #127, #128, #129, #130, #131, #132, #136, #137, #139, #999"
        )
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        orphans = [f for f in result.findings if f.reason_code == ReasonCode.REFERENCE_ORPHAN]
        assert any("#999" in f.message for f in orphans), (
            "Expected orphan reference for #999"
        )


# ---------------------------------------------------------------------------
# Duplicate IDs
# ---------------------------------------------------------------------------


class TestDuplicateIDs:
    """Duplicate IDs within an artifact should be detected."""

    def test_duplicate_sc_id_in_stop_matrix(self, tmp_path: Path) -> None:
        artifacts = _valid_artifact_set()
        conditions = [
            {"id": "SC-01", "name": "dup_check", "severity": "critical"},
            {"id": "SC-01", "name": "dup_check_again", "severity": "high"},
        ]
        artifacts["rehearsal_stop_condition_matrix.json"] = _stop_matrix(
            conditions=conditions
        )
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        dupes = [f for f in result.findings if f.reason_code == ReasonCode.ID_DUPLICATE]
        assert any("SC-01" in f.message for f in dupes), (
            "Expected duplicate ID for SC-01"
        )

    def test_duplicate_markdown_table_id(self, tmp_path: Path) -> None:
        """Duplicate P-NN IDs in a markdown table in the gate doc."""
        artifacts = _valid_artifact_set()
        artifacts["controlled_rehearsal_planning_gate.md"] = (
            "# Controlled Rehearsal Planning Gate\n"
            "*Created as part of #135*\n"
            "| # | Artifact |\n"
            "|---|----------|\n"
            "| P-01 | test |\n"
            "| P-01 | dup |\n"
            "*Created as part of #135*\n"
        )
        paths = _write_artifacts(artifacts, tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        dupes = [f for f in result.findings if f.reason_code == ReasonCode.ID_DUPLICATE]
        assert any("P-01" in f.message for f in dupes), (
            "Expected duplicate ID for P-01"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty paths list, unreadable files, etc."""

    def test_empty_artifact_list(self) -> None:
        result = run_semantic_consistency(ValidationResult(), [])
        assert result.verdict == Verdict.BLOCKED, (
            "Empty artifact list should produce BLOCKED verdict"
        )
        prereq_missing = [f for f in result.findings if f.reason_code == ReasonCode.ARTIFACT_MISSING]
        assert len(prereq_missing) >= 1, "Expected ARTIFACT_MISSING with empty paths"

    def test_nonexistent_paths(self, tmp_path: Path) -> None:
        paths = [str(tmp_path / "nonexistent_file.md")]
        result = run_semantic_consistency(ValidationResult(), paths)
        assert any(f.verdict == Verdict.BLOCKED for f in result.findings)

    def test_deterministic_order(self, tmp_path: Path) -> None:
        paths = _write_artifacts(_valid_artifact_set(), tmp_path)
        result1 = run_semantic_consistency(ValidationResult(), paths)
        result2 = run_semantic_consistency(ValidationResult(), paths)
        msgs1 = [(f.check_id, f.message, str(f.reason_code)) for f in result1.findings]
        msgs2 = [(f.check_id, f.message, str(f.reason_code)) for f in result2.findings]
        assert msgs1 == msgs2, "Findings order must be deterministic"

    def test_reason_code_enum_used(self, tmp_path: Path) -> None:
        paths = _write_artifacts(_valid_artifact_set(), tmp_path)
        result = run_semantic_consistency(ValidationResult(), paths)
        for f in result.findings:
            assert isinstance(f.reason_code, ReasonCode), (
                f"Finding {f.check_id} must use ReasonCode, got {type(f.reason_code)}"
            )
