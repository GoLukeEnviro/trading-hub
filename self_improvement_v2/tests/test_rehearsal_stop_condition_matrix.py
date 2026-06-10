"""Tests for #136: Rehearsal stop-condition and abort matrix.

Verifies the JSON matrix exists, is valid JSON, contains required
condition fields, has hard blocker categories, verdict mapping,
and action mapping with fail-closed semantics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

MATRIX_PATH = Path(__file__).resolve().parent.parent / "rehearsal" / "rehearsal_stop_condition_matrix.json"


# ──────────────────────────────────────────────
# Artifact existence
# ──────────────────────────────────────────────


class TestMatrixArtifactExists:
    """The stop-condition matrix JSON must exist."""

    def test_matrix_file_exists(self) -> None:
        assert MATRIX_PATH.is_file(), f"Matrix file not found: {MATRIX_PATH}"

    def test_matrix_is_valid_json(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        assert isinstance(data, dict), "Matrix root must be a dict"


# ──────────────────────────────────────────────
# Top-level fields
# ──────────────────────────────────────────────


class TestMatrixTopLevelFields:
    """The matrix must have required top-level fields."""

    REQUIRED_FIELDS: ClassVar[list[str]] = [
        "title",
        "version",
        "description",
        "safety_notice",
        "default_verdict",
        "conditions",
        "verdict_map",
        "action_map",
    ]

    def test_all_required_fields_present(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        for field in self.REQUIRED_FIELDS:
            assert field in data, f"Missing required top-level field: {field}"

    def test_default_verdict_is_blocked(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        assert data.get("default_verdict") == "BLOCKED", (
            "Default verdict must be BLOCKED for fail-closed safety"
        )

    def test_safety_notice_present(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        notice = data.get("safety_notice", "")
        assert len(notice) > 50, "Safety notice is too short or missing"


# ──────────────────────────────────────────────
# Conditions
# ──────────────────────────────────────────────


class TestMatrixConditions:
    """Each condition must have required fields."""

    REQUIRED_CONDITION_FIELDS: ClassVar[list[str]] = [
        "id",
        "name",
        "description",
        "category",
        "severity",
        "action",
        "escalate",
        "verdict",
        "evidence_required",
        "fail_closed",
        "rehearsal_phase",
    ]

    VALID_CATEGORIES: ClassVar[set[str]] = {
        "hard_blocker", "safety_blocker", "evidence_gap",
        "scope_violation", "approval", "validation", "runtime_safety",
    }

    VALID_ACTIONS: ClassVar[set[str]] = {"ABORT", "STOP", "WARN"}

    VALID_VERDICTS: ClassVar[set[str]] = {"RED", "YELLOW"}

    VALID_PHASES: ClassVar[set[str]] = {"planning", "execution"}

    def test_conditions_is_list(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        conditions = data.get("conditions", [])
        assert isinstance(conditions, list), "conditions must be a list"
        assert len(conditions) >= 1, "Must have at least one condition"

    def test_each_condition_has_required_fields(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        for cond in data.get("conditions", []):
            for field in self.REQUIRED_CONDITION_FIELDS:
                assert field in cond, (
                    f"Condition '{cond.get('id', 'unknown')}' missing field: {field}"
                )

    def test_each_condition_valid_category(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        for cond in data.get("conditions", []):
            assert cond.get("category") in self.VALID_CATEGORIES, (
                f"Condition '{cond.get('id')}' has invalid category: "
                f"{cond.get('category')}"
            )

    def test_each_condition_valid_action(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        for cond in data.get("conditions", []):
            assert cond.get("action") in self.VALID_ACTIONS, (
                f"Condition '{cond.get('id')}' has invalid action: "
                f"{cond.get('action')}"
            )

    def test_each_condition_valid_verdict(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        for cond in data.get("conditions", []):
            assert cond.get("verdict") in self.VALID_VERDICTS, (
                f"Condition '{cond.get('id')}' has invalid verdict: "
                f"{cond.get('verdict')}"
            )

    def test_each_condition_valid_phase(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        for cond in data.get("conditions", []):
            assert cond.get("rehearsal_phase") in self.VALID_PHASES, (
                f"Condition '{cond.get('id')}' has invalid rehearsal_phase: "
                f"{cond.get('rehearsal_phase')}"
            )


# ──────────────────────────────────────────────
# Hard blocker existence
# ──────────────────────────────────────────────


class TestMatrixHardBlockers:
    """Some conditions must be hard blockers."""

    def test_at_least_one_hard_blocker(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        hard_blockers = [
            c for c in data.get("conditions", [])
            if c.get("category") == "hard_blocker"
        ]
        assert len(hard_blockers) >= 1, (
            "Must have at least one hard_blocker condition"
        )

    def test_hard_blockers_are_fail_closed(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        for cond in data.get("conditions", []):
            if cond.get("category") == "hard_blocker":
                assert cond.get("fail_closed") is True, (
                    f"Hard blocker '{cond.get('id')}' must be fail_closed"
                )

    def test_dry_run_false_blocker_exists(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        names = [c.get("name") for c in data.get("conditions", [])]
        assert any("dry_run" in name for name in names), (
            "Missing dry_run false blocker condition"
        )

    def test_live_state_blocker_exists(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        names = [c.get("name") for c in data.get("conditions", [])]
        assert any("live" in name for name in names), (
            "Missing live state blocker condition"
        )


# ──────────────────────────────────────────────
# Verdict map
# ──────────────────────────────────────────────


class TestMatrixVerdictMap:
    """The verdict map must define RED, YELLOW, GREEN."""

    REQUIRED_VERDICTS: ClassVar[set[str]] = {"RED", "YELLOW", "GREEN"}

    def test_all_verdicts_defined(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        verdict_map = data.get("verdict_map", {})
        for verdict in self.REQUIRED_VERDICTS:
            assert verdict in verdict_map, (
                f"Missing verdict definition: {verdict}"
            )

    def test_red_proceed_false(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        assert data["verdict_map"]["RED"].get("proceed_without_resolution") is False, (
            "RED verdict must not allow proceed_without_resolution"
        )


# ──────────────────────────────────────────────
# Action map
# ──────────────────────────────────────────────


class TestMatrixActionMap:
    """The action map must define ABORT, STOP, WARN."""

    REQUIRED_ACTIONS: ClassVar[set[str]] = {"ABORT", "STOP", "WARN"}

    def test_all_actions_defined(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        action_map = data.get("action_map", {})
        for action in self.REQUIRED_ACTIONS:
            assert action in action_map, (
                f"Missing action definition: {action}"
            )

    def test_abort_not_reversible(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        assert data["action_map"]["ABORT"].get("reversible") is False, (
            "ABORT must be irreversible"
        )

    def test_abort_requires_escalation(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        assert data["action_map"]["ABORT"].get("requires_escalation") is True, (
            "ABORT must require escalation"
        )


# ──────────────────────────────────────────────
# Fail-closed invariant
# ──────────────────────────────────────────────


class TestMatrixFailClosed:
    """Missing-evidence conditions must have fail_closed=True."""

    def test_evidence_missing_is_fail_closed(self) -> None:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        for cond in data.get("conditions", []):
            if "evidence" in cond.get("name", "") and "missing" in cond.get("name", ""):
                msg = f"Condition '{cond.get('id')}' must be fail_closed"
                assert cond.get("fail_closed") is True, msg
