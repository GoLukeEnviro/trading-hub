"""Tests for the Dry-run Evidence Schema (#128).

Validates that:
- Valid evidence records pass schema validation.
- Invalid records (missing required fields, wrong types, const violations) fail.
- The dry_run_flag and live_forbidden_confirmed are always true.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
)

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "evidence"
SCHEMA_PATH = SCHEMA_DIR / "dry_run_evidence.schema.json"


# ──────────────────────────────────────────────
# Pydantic model mirroring the JSON Schema
# ──────────────────────────────────────────────


class RunIdentity(BaseModel, frozen=True):
    run_id: str = Field(pattern=r"^dr-[0-9]{8}-[0-9]{6}-[a-z0-9]{8}$")
    run_name: str = Field(max_length=128)
    created_at_utc: str
    created_by: str = Field(max_length=64)


class ApprovalRefs(BaseModel, frozen=True):
    approval_token: str = Field(max_length=64)
    approval_timestamp_utc: str
    approval_scope: str = Field(max_length=512)
    approval_expires_at_utc: str | None = None


class EnvironmentSummary(BaseModel, frozen=True):
    git_branch: str = Field(max_length=128)
    git_commit: str = Field(pattern=r"^[a-f0-9]{7,40}$")
    python_version: str | None = Field(None, max_length=16)
    si_v2_version: str | None = Field(None, max_length=16)
    dry_run_flag: bool = True

    @field_validator("dry_run_flag")
    @classmethod
    def _must_be_true(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("dry_run_flag must be True for dry-run evidence")
        return v


class CommandClass(BaseModel, frozen=True):
    category: str = Field(
        pattern=r"^(read_only_inspection|read_only_config|bot_status|trade_history_read|backtest|signal_read|config_comparison|report_generation|other_read_only)$"
    )
    target_bots: list[str] = Field(default_factory=list, max_length=64)
    commands_executed: list[str] = Field(default_factory=list, max_length=256)


class SafetyState(BaseModel, frozen=True):
    live_forbidden_confirmed: bool = True
    dry_run_mode_confirmed: bool = True
    no_secrets_exposed: bool = True
    riskguard_available: bool | None = None
    shadowlogger_available: bool | None = None
    safety_verdict: str = Field(pattern=r"^(safe|degraded|blocked)$")

    @field_validator("live_forbidden_confirmed")
    @classmethod
    def _live_must_be_true(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("live_forbidden_confirmed must be True")
        return v

    @field_validator("dry_run_mode_confirmed")
    @classmethod
    def _dry_run_must_be_true(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("dry_run_mode_confirmed must be True")
        return v

    @field_validator("no_secrets_exposed")
    @classmethod
    def _no_secrets_must_be_true(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("no_secrets_exposed must be True")
        return v


class Artifacts(BaseModel, frozen=True):
    log_paths: list[str] = Field(default_factory=list, max_length=512)
    report_paths: list[str] = Field(default_factory=list, max_length=512)
    evidence_paths: list[str] = Field(default_factory=list, max_length=512)
    artifact_count: int = Field(ge=0)


class ValidationOutcome(BaseModel, frozen=True):
    status: str = Field(pattern=r"^(passed|failed|degraded|not_run)$")
    failures: list[str] = Field(default_factory=list, max_length=1024)
    warnings: list[str] = Field(default_factory=list, max_length=1024)
    completed_at_utc: str | None = None


class DryRunEvidenceRecord(BaseModel, frozen=True):
    schema_version: int = Field(ge=1)
    run_identity: RunIdentity
    approval_refs: ApprovalRefs
    environment_summary: EnvironmentSummary
    command_class: CommandClass
    safety_state: SafetyState
    artifacts: Artifacts | None = None
    validation_outcome: ValidationOutcome
    notes: str | None = Field(None, max_length=4096)


# ──────────────────────────────────────────────
# Test data
# ──────────────────────────────────────────────

VALID_RECORD = {
    "schema_version": 1,
    "run_identity": {
        "run_id": "dr-20260610-143000-a1b2c3d4",
        "run_name": "phase-m-rehearsal-signal-validation",
        "created_at_utc": "2026-06-10T14:30:00Z",
        "created_by": "hermes-orchestrator",
    },
    "approval_refs": {
        "approval_token": "APPROVE_PHASE_M_REHEARSAL_20260610",
        "approval_timestamp_utc": "2026-06-10T14:00:00Z",
        "approval_scope": "Read-only signal validation on all production dry-run bots",
    },
    "environment_summary": {
        "git_branch": "feat/si-v2-issue-127-132",
        "git_commit": "85aa1add80d0573e5ffbb346a7ba6ce646d9cdb2",
        "python_version": "3.13",
        "si_v2_version": "0.1.0",
        "dry_run_flag": True,
    },
    "command_class": {
        "category": "signal_read",
        "target_bots": ["FreqForge", "Regime-Hybrid"],
        "commands_executed": ["GET /api/v1/status", "GET /signal"],
    },
    "safety_state": {
        "live_forbidden_confirmed": True,
        "dry_run_mode_confirmed": True,
        "no_secrets_exposed": True,
        "riskguard_available": True,
        "shadowlogger_available": True,
        "safety_verdict": "safe",
    },
    "artifacts": {
        "log_paths": ["logs/dry_run_evidence.log"],
        "report_paths": ["reports/runtime_probe/runtime_signal_validation_report.md"],
        "evidence_paths": ["evidence/dry_run_evidence.schema.json"],
        "artifact_count": 3,
    },
    "validation_outcome": {
        "status": "passed",
        "failures": [],
        "warnings": ["No RiskGuard service available"],
        "completed_at_utc": "2026-06-10T14:35:00Z",
    },
    "notes": "All signals validated successfully. No anomalies detected.",
}

INVALID_RECORDS: list[tuple[str, dict]] = [
    (
        "missing required run_identity",
        {k: v for k, v in VALID_RECORD.items() if k != "run_identity"},
    ),
    (
        "dry_run_flag is false",
        {
            **VALID_RECORD,
            "environment_summary": {
                **VALID_RECORD["environment_summary"],
                "dry_run_flag": False,
            },
        },
    ),
    (
        "live_forbidden_confirmed is false",
        {
            **VALID_RECORD,
            "safety_state": {
                **VALID_RECORD["safety_state"],
                "live_forbidden_confirmed": False,
            },
        },
    ),
    (
        "safety_verdict is invalid",
        {
            **VALID_RECORD,
            "safety_state": {
                **VALID_RECORD["safety_state"],
                "safety_verdict": "unknown",
            },
        },
    ),
    (
        "missing approval_token",
        {
            **VALID_RECORD,
            "approval_refs": {
                k: v for k, v in VALID_RECORD["approval_refs"].items()
                if k != "approval_token"
            },
        },
    ),
    (
        "validation_outcome status invalid",
        {
            **VALID_RECORD,
            "validation_outcome": {
                **VALID_RECORD["validation_outcome"],
                "status": "running",
            },
        },
    ),
    (
        "run_id pattern mismatch",
        {
            **VALID_RECORD,
            "run_identity": {
                **VALID_RECORD["run_identity"],
                "run_id": "invalid-run-id",
            },
        },
    ),
]


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────


class TestDryRunEvidenceSchema:
    """Tests that the DryRunEvidence Pydantic model validates correctly."""

    def test_schema_file_exists(self) -> None:
        """The JSON schema file must exist."""
        assert SCHEMA_PATH.is_file(), f"Schema not found: {SCHEMA_PATH}"

    def test_schema_is_valid_json(self) -> None:
        """The JSON schema file must parse as valid JSON."""
        data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        assert data["title"] == "Dry-run Evidence Record"

    def test_valid_record_passes(self) -> None:
        """A valid evidence record must pass Pydantic validation."""
        record = DryRunEvidenceRecord(**VALID_RECORD)
        assert record.run_identity.run_id == "dr-20260610-143000-a1b2c3d4"
        assert record.safety_state.safety_verdict == "safe"
        assert record.validation_outcome.status == "passed"

    def test_valid_record_without_optional_fields(self) -> None:
        """A record without optional artifacts and notes must still validate."""
        minimal = {k: v for k, v in VALID_RECORD.items() if k not in ("artifacts", "notes")}
        record = DryRunEvidenceRecord(**minimal)
        assert record.artifacts is None
        assert record.notes is None

    @pytest.mark.parametrize("reason,record", INVALID_RECORDS)
    def test_invalid_records_fail(self, reason: str, record: dict) -> None:
        """Each invalid record must fail validation with a clear error."""
        with pytest.raises(ValidationError):
            DryRunEvidenceRecord(**record)

    def test_dry_run_flag_is_always_true(self) -> None:
        """The dry_run_flag field must always be True."""
        with pytest.raises(ValidationError):
            DryRunEvidenceRecord(
                **{
                    **VALID_RECORD,
                    "environment_summary": {
                        **VALID_RECORD["environment_summary"],
                        "dry_run_flag": False,
                    },
                }
            )

    def test_live_forbidden_is_always_true(self) -> None:
        """The live_forbidden_confirmed field must always be True."""
        with pytest.raises(ValidationError):
            DryRunEvidenceRecord(
                **{
                    **VALID_RECORD,
                    "safety_state": {
                        **VALID_RECORD["safety_state"],
                        "live_forbidden_confirmed": False,
                    },
                }
            )

    def test_no_secrets_exposed_is_always_true(self) -> None:
        """The no_secrets_exposed field must always be True."""
        with pytest.raises(ValidationError):
            DryRunEvidenceRecord(
                **{
                    **VALID_RECORD,
                    "safety_state": {
                        **VALID_RECORD["safety_state"],
                        "no_secrets_exposed": False,
                    },
                }
            )
