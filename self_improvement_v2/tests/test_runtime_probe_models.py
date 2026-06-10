"""Tests for typed runtime-probe evidence models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from si_v2.runtime_probe.models import (
    RedactionSummary,
    RedactionSummaryLine,
    RuntimeProbeCommandCategory,
    RuntimeProbeEvidence,
    RuntimeProbeSafetyVerdict,
)


def _summary() -> RedactionSummary:
    return RedactionSummary(
        line_count=1,
        redaction_count=1,
        redaction_applied=True,
        placeholders=["[REDACTED_API_KEY]"],
        lines=[
            RedactionSummaryLine(
                text="status ok key=[REDACTED_API_KEY]",
                placeholders=["[REDACTED_API_KEY]"],
            )
        ],
    )


def test_runtime_probe_evidence_defaults_raw_output_storage_to_false() -> None:
    evidence = RuntimeProbeEvidence(
        timestamp_utc=datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC),
        probe_id="phase-m-001",
        target="local-shell",
        command_category=RuntimeProbeCommandCategory.REPO_STATUS,
        sanitized_output_summary=_summary(),
        redaction_applied=True,
        safety_verdict=RuntimeProbeSafetyVerdict.YELLOW,
        abort_reason="dry-run status not yet confirmed",
    )

    assert evidence.raw_output_stored is False


def test_runtime_probe_evidence_requires_abort_reason_for_red_verdict() -> None:
    with pytest.raises(ValidationError):
        RuntimeProbeEvidence(
            timestamp_utc=datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC),
            probe_id="phase-m-002",
            target="local-shell",
            command_category=RuntimeProbeCommandCategory.LOG_SNIPPET,
            sanitized_output_summary=_summary(),
            redaction_applied=True,
            safety_verdict=RuntimeProbeSafetyVerdict.RED,
        )


def test_runtime_probe_evidence_rejects_redaction_flag_mismatch() -> None:
    with pytest.raises(ValidationError):
        RuntimeProbeEvidence(
            timestamp_utc=datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC),
            probe_id="phase-m-003",
            target="local-shell",
            command_category=RuntimeProbeCommandCategory.API_HEALTH,
            sanitized_output_summary=_summary(),
            redaction_applied=False,
            safety_verdict=RuntimeProbeSafetyVerdict.YELLOW,
            abort_reason="awaiting operator confirmation",
        )


def test_runtime_probe_evidence_roundtrip() -> None:
    evidence = RuntimeProbeEvidence(
        timestamp_utc=datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC),
        probe_id="phase-m-004",
        target="local-shell",
        command_category=RuntimeProbeCommandCategory.DRY_RUN_STATUS,
        sanitized_output_summary=_summary(),
        redaction_applied=True,
        safety_verdict=RuntimeProbeSafetyVerdict.GREEN,
    )

    restored = RuntimeProbeEvidence.model_validate_json(evidence.model_dump_json())
    assert restored == evidence
