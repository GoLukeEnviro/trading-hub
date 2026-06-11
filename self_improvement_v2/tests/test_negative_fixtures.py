"""Negative test fixture corpus (#152).

Loads each fixture in ``tests/fixtures/proposal_package/`` and verifies
the expected behaviour: valid ones parse, invalid ones fail, unsafe
content is detected, contradictory data is flagged, and so on.

All assertions operate on the raw fixture JSON content — no schema
validator or pipeline runner is required, keeping tests lightweight
and dependency-free.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rehearsal.planning_models import ReasonCode
from rehearsal.redaction_checker import RedactionChecker

# Path to the fixtures directory
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "proposal_package"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict | None:
    """Attempt to parse *path* as JSON; return ``None`` on failure."""
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def _has_field(data: dict, field: str) -> bool:
    """Check if *data* has a top-level field (dot-separated nesting supported)."""
    parts = field.split(".")
    current: dict | list | str | int | float | bool | None = data
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return False
            current = current[part]
        else:
            return False
    return True


def _read_text(path: Path) -> str:
    """Read file content as text (even if invalid JSON)."""
    return path.read_text(encoding="utf-8")


def _count_occurrences(text: str, pattern: str) -> int:
    """Count non-overlapping occurrences of *pattern* in *text*."""
    return text.count(pattern)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidFixtures:
    """Tests for fixtures that should parse as valid JSON."""

    @pytest.mark.parametrize(
        "path",
        [
            FIXTURES_DIR / "valid" / "complete_proposal.json",
            FIXTURES_DIR / "draft" / "valid_draft.json",
        ],
    )
    def test_parses_as_valid_json(self, path: Path) -> None:
        """Valid fixtures should parse as JSON successfully."""
        data = _load_json(path)
        assert data is not None, f"Expected valid JSON at {path.name}"

    def test_complete_proposal_has_all_required_fields(self) -> None:
        """The complete proposal fixture should have all schema-required fields."""
        data = _load_json(FIXTURES_DIR / "valid" / "complete_proposal.json")
        assert data is not None

        required_fields = [
            "schema_version",
            "stage",
            "proposal",
            "planning_gate_reference",
            "stop_condition_reference",
            "evidence_plan_reference",
            "approval_packet_reference",
            "observation_plan_reference",
            "readiness_record_reference",
            "non_production_confirmation",
            "non_runtime_confirmation",
        ]
        for field in required_fields:
            assert _has_field(data, field), f"Missing required field: {field}"

    def test_draft_has_minimal_fields(self) -> None:
        """The draft fixture should have stage=draft and minimal fields."""
        data = _load_json(FIXTURES_DIR / "draft" / "valid_draft.json")
        assert data is not None
        assert data.get("stage") == "draft", "Expected stage=draft"

    def test_comment_field_present(self) -> None:
        """All fixtures should have a 'comment' field explaining what they test."""
        for fixture_dir in sorted(FIXTURES_DIR.iterdir()):
            if not fixture_dir.is_dir():
                continue
            for fixture_file in sorted(fixture_dir.iterdir()):
                if fixture_file.suffix != ".json":
                    continue
                data = _load_json(fixture_file)
                if data is not None:
                    assert "comment" in data, (
                        f"Missing 'comment' field in {fixture_file.relative_to(FIXTURES_DIR)}"
                    )


class TestMissingGateFixture:
    """Tests for the missing planning_gate_reference fixture."""

    FIXTURE_PATH = FIXTURES_DIR / "missing" / "missing_gate.json"

    def test_missing_planning_gate_reference(self) -> None:
        """The fixture should be parseable JSON but missing planning_gate_reference."""
        data = _load_json(self.FIXTURE_PATH)
        assert data is not None
        assert "planning_gate_reference" not in data, (
            "Expected planning_gate_reference to be absent"
        )


class TestMalformedFixture:
    """Tests for the malformed/bad_schema.json fixture."""

    FIXTURE_PATH = FIXTURES_DIR / "malformed" / "bad_schema.json"

    def test_parses_as_valid_json(self) -> None:
        """The fixture contains valid JSON but is missing required schema fields."""
        data = _load_json(self.FIXTURE_PATH)
        assert data is not None, "Expected fixture to be valid JSON"

    def test_missing_required_schema_fields(self) -> None:
        """The fixture is missing required fields like non_production_confirmation."""
        data = _load_json(self.FIXTURE_PATH)
        assert data is not None
        assert "non_production_confirmation" not in data, (
            "Expected fixture to be missing non_production_confirmation"
        )
        assert "non_runtime_confirmation" not in data, (
            "Expected fixture to be missing non_runtime_confirmation"
        )


class TestContradictoryFixture:
    """Tests for the contradictory verdict fixture."""

    FIXTURE_PATH = FIXTURES_DIR / "contradictory" / "red_but_green_readiness.json"

    def test_parses_as_valid_json(self) -> None:
        """The fixture should parse as valid JSON."""
        data = _load_json(self.FIXTURE_PATH)
        assert data is not None

    def test_has_contradictory_verdicts(self) -> None:
        """gate_verdict=RED but readiness_verdict=GREEN is contradictory."""
        data = _load_json(self.FIXTURE_PATH)
        assert data is not None
        assert data.get("gate_verdict") == "RED", "Expected gate_verdict=RED"

        readiness = data.get("readiness_record_reference", {})
        assert isinstance(readiness, dict), "Expected readiness_record_reference to be an object"
        assert readiness.get("readiness_verdict") == "GREEN", (
            "Expected readiness_verdict=GREEN"
        )


class TestDuplicateFixture:
    """Tests for the duplicate condition IDs fixture."""

    FIXTURE_PATH = FIXTURES_DIR / "duplicate" / "dup_condition_ids.json"

    def test_parses_as_valid_json(self) -> None:
        """The fixture should parse as valid JSON."""
        data = _load_json(self.FIXTURE_PATH)
        assert data is not None

    def test_has_duplicate_sc01_ids(self) -> None:
        """The fixture should contain two stop conditions with id=SC-01."""
        data = _load_json(self.FIXTURE_PATH)
        assert data is not None

        conditions = data.get("stop_conditions_inline", [])
        assert isinstance(conditions, list), "Expected stop_conditions_inline to be a list"
        assert len(conditions) == 2, "Expected exactly 2 stop conditions"

        ids = [c.get("id") for c in conditions]
        assert ids == ["SC-01", "SC-01"], "Expected both conditions to have id=SC-01"


class TestOrphanFixture:
    """Tests for the orphan reference fixture."""

    FIXTURE_PATH = FIXTURES_DIR / "orphan" / "orphan_reference.json"

    def test_references_non_existent_issue(self) -> None:
        """The fixture should reference #999 which does not exist."""
        data = _load_json(self.FIXTURE_PATH)
        assert data is not None

        ref = data.get("readiness_record_reference", "")
        assert ref == "#999", f"Expected readiness_record_reference='#999', got '{ref}'"


class TestUnsafeFixtures:
    """Tests for unsafe content/path fixtures using RedactionChecker."""

    @pytest.fixture
    def checker(self) -> RedactionChecker:
        return RedactionChecker()

    def test_unsafe_paths_detected(self, checker: RedactionChecker) -> None:
        """unsafe_paths.json contains /home/hermes/ paths that should be flagged."""
        text = _read_text(FIXTURES_DIR / "unsafe" / "unsafe_paths.json")
        findings = checker.check_artifact(text)

        # Should find at least 2 findings (home path + deploy path)
        assert len(findings) >= 2, (
            f"Expected at least 2 redaction findings, got {len(findings)}"
        )

        # At least one finding should be UNSAFE_PATH
        path_findings = [f for f in findings if f.reason_code == ReasonCode.UNSAFE_PATH]
        assert len(path_findings) >= 1, "Expected at least one UNSAFE_PATH finding"

    def test_unsafe_content_detected(self, checker: RedactionChecker) -> None:
        """unsafe_content.json contains unredacted api_key, api_secret, passphrase, etc."""
        text = _read_text(FIXTURES_DIR / "unsafe" / "unsafe_content.json")
        findings = checker.check_artifact(text)

        # Should find at least 3 findings (api_key, api_secret, passphrase, wallet)
        assert len(findings) >= 3, (
            f"Expected at least 3 redaction findings, got {len(findings)}"
        )

        # Should include UNSAFE_CONTENT
        content_findings = [f for f in findings if f.reason_code == ReasonCode.UNSAFE_CONTENT]
        assert len(content_findings) >= 3, (
            f"Expected at least 3 UNSAFE_CONTENT findings, got {len(content_findings)}"
        )

    def test_unsafe_paths_contain_home_and_opt_paths(self) -> None:
        """Verify the fixture contains the expected path patterns."""
        text = _read_text(FIXTURES_DIR / "unsafe" / "unsafe_paths.json")
        assert "/home/hermes/" in text, "Expected /home/hermes/ in fixture"
        assert "/opt/data/" in text, "Expected /opt/data/ in fixture"

    def test_unsafe_content_contains_sensitive_patterns(self) -> None:
        """Verify the fixture contains the expected sensitive content patterns."""
        text = _read_text(FIXTURES_DIR / "unsafe" / "unsafe_content.json")
        assert "api_key" in text, "Expected api_key in fixture"
        assert "api_secret" in text, "Expected api_secret in fixture"
        assert "passphrase" in text, "Expected passphrase in fixture"
        assert "0x" in text, "Expected wallet address ('0x') in fixture"


class TestCombinedErrorsFixture:
    """Tests for the combined multiple-errors fixture."""

    FIXTURE_PATH = FIXTURES_DIR / "combined" / "multiple_errors.json"

    def test_parses_as_valid_json(self) -> None:
        """The fixture should parse as valid JSON."""
        data = _load_json(self.FIXTURE_PATH)
        assert data is not None

    def test_missing_planning_gate_reference(self) -> None:
        """Should be missing planning_gate_reference field."""
        data = _load_json(self.FIXTURE_PATH)
        assert data is not None
        assert "planning_gate_reference" not in data, (
            "Expected planning_gate_reference to be absent"
        )

    def test_contains_unsafe_paths(self) -> None:
        """Should contain /home/ and /opt/data/ path patterns."""
        text = _read_text(self.FIXTURE_PATH)
        assert "/home/hermes/" in text or "/home/" in text, (
            "Expected /home/ path pattern"
        )
        assert "/opt/data/" in text, "Expected /opt/data/ path pattern"

    def test_contains_unsafe_content(self) -> None:
        """Should contain unredacted sensitive patterns (api_key, api_secret, wallet)."""
        text = _read_text(self.FIXTURE_PATH)
        assert "api_key" in text, "Expected api_key"
        assert "api_secret" in text, "Expected api_secret"
        assert "0x" in text, "Expected wallet hex pattern"

    def test_redaction_checker_finds_multiple_issues(self) -> None:
        """The redaction checker should find at least 3 issues."""
        checker = RedactionChecker()
        text = _read_text(self.FIXTURE_PATH)
        findings = checker.check_artifact(text)
        assert len(findings) >= 3, (
            f"Expected at least 3 findings for combined errors, got {len(findings)}"
        )

    def test_has_comment_field(self) -> None:
        """Should have a comment field explaining what it tests."""
        data = _load_json(self.FIXTURE_PATH)
        assert data is not None
        assert "comment" in data, "Missing comment field"


class TestOutputDeterminism:
    """Verify that the RedactionChecker produces deterministic (sorted) output."""

    def test_deterministic_finding_order(self) -> None:
        """Calling check_artifact twice on the same input should produce the same output."""
        checker = RedactionChecker()
        text = _read_text(FIXTURES_DIR / "combined" / "multiple_errors.json")

        findings1 = checker.check_artifact(text)
        findings2 = checker.check_artifact(text)

        assert len(findings1) == len(findings2), "Finding count differs between runs"
        for f1, f2 in zip(findings1, findings2, strict=True):
            assert f1.reason_code == f2.reason_code, "ReasonCode order differs"
            assert f1.check_id == f2.check_id, "Check ID order differs"
            assert f1.verdict == f2.verdict, "Verdict order differs"

    def test_findings_sorted_by_reason_code(self) -> None:
        """Findings should be sorted by reason_code, then check_id."""
        checker = RedactionChecker()
        text = _read_text(FIXTURES_DIR / "combined" / "multiple_errors.json")

        findings = checker.check_artifact(text)
        for i in range(len(findings) - 1):
            assert (findings[i].reason_code.value, findings[i].check_id) <= (
                findings[i + 1].reason_code.value,
                findings[i + 1].check_id,
            ), "Findings are not sorted deterministically"
