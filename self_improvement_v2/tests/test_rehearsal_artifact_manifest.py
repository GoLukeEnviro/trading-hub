"""Tests for the Rehearsal Artifact Archive Manifest (#132).

Verifies that the manifest schema validates correctly:
- Valid manifests pass.
- Invalid manifests (missing fields, wrong checksum format) fail.
- Retention policy constraints are enforced.
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
    model_validator,
)

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "evidence"
SCHEMA_PATH = SCHEMA_DIR / "rehearsal_artifact_manifest.schema.json"


# ──────────────────────────────────────────────
# Pydantic model mirroring the JSON Schema
# ──────────────────────────────────────────────


class ApprovalRef(BaseModel, frozen=True):
    approval_token: str = Field(max_length=64)
    approval_scope: str | None = Field(None, max_length=512)


class Retention(BaseModel, frozen=True):
    policy: str = Field(pattern=r"^(permanent|archive_after_days|delete_after_days)$")
    retention_days: int | None = Field(None, ge=1)
    expires_at_utc: str | None = None


class ArtifactEntry(BaseModel, frozen=True):
    path: str = Field(max_length=512)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    artifact_type: str = Field(
        pattern=r"^(log|report|evidence|schema|config_snapshot|trade_history|signal_output|manifest)$"
    )
    description: str | None = Field(None, max_length=256)

    @field_validator("path")
    @classmethod
    def _path_must_be_safe(cls, v: str) -> str:
        lowered = v.lower()
        blocked_terms = ("token", "secret", "key", "credential", "wallet")
        if v.startswith("/"):
            raise ValueError("artifact path must be relative")
        if ".." in Path(v).parts:
            raise ValueError("artifact path must not contain traversal")
        if any(part == ".env" for part in Path(v).parts):
            raise ValueError("artifact path must not point at env files")
        if any(term in lowered for term in blocked_terms):
            raise ValueError("artifact path must not look like a sensitive path")
        return v


class ValidationSummary(BaseModel, frozen=True):
    all_checksums_valid: bool
    missing_artifacts: list[str] = Field(default_factory=list, max_length=512)
    extra_artifacts: list[str] = Field(default_factory=list, max_length=512)


class RehearsalArtifactManifest(BaseModel, frozen=True):
    schema_version: str = Field(pattern=r"^\d+\.\d+$")
    manifest_stage: str = Field(pattern=r"^(draft|final)$")
    manifest_id: str = Field(pattern=r"^mf-[0-9]{8}-[0-9]{6}-[a-z0-9]{8}$")
    run_ref: str = Field(pattern=r"^dr-[0-9]{8}-[0-9]{6}-[a-z0-9]{8}$")
    generated_at_utc: str
    generated_by: str = Field(max_length=64)
    approval_ref: ApprovalRef
    artifact_count: int = Field(ge=0)
    total_size_bytes: int | None = Field(None, ge=0)
    retention: Retention
    artifacts: list[ArtifactEntry]
    validation_summary: ValidationSummary

    @model_validator(mode="after")
    def _manifest_must_be_consistent(self) -> RehearsalArtifactManifest:
        if self.artifact_count != len(self.artifacts):
            raise ValueError("artifact_count must equal len(artifacts)")
        if self.manifest_stage == "final" and not self.artifacts:
            raise ValueError("final manifest must contain at least one artifact")
        return self


# ──────────────────────────────────────────────
# Test data
# ──────────────────────────────────────────────

VALID_MANIFEST = {
    "schema_version": "1.0",
    "manifest_stage": "final",
    "manifest_id": "mf-20260610-143000-a1b2c3d4",
    "run_ref": "dr-20260610-143000-a1b2c3d4",
    "generated_at_utc": "2026-06-10T14:35:00Z",
    "generated_by": "hermes-orchestrator",
    "approval_ref": {
        "approval_token": "APPROVE_PHASE_M_REHEARSAL_20260610",
        "approval_scope": "Read-only signal validation on dry-run bots",
    },
    "artifact_count": 2,
    "total_size_bytes": 8192,
    "retention": {
        "policy": "archive_after_days",
        "retention_days": 90,
    },
    "artifacts": [
        {
            "path": "reports/runtime_probe/runtime_signal_validation_report.md",
            "sha256": "362636f5a34836946783f440c823fd9b5604a42a3deebe7b9bb97dfc1084f6ed",
            "size_bytes": 4096,
            "artifact_type": "report",
            "description": "Runtime signal validation report",
        },
        {
            "path": "evidence/dry_run_evidence.json",
            "sha256": "8ce23d00a64d34e8bd5d67a51e76d818fe813be69eb1b49eb97b5a81f9e59f63",
            "size_bytes": 4096,
            "artifact_type": "evidence",
            "description": "Dry-run evidence record",
        },
    ],
    "validation_summary": {
        "all_checksums_valid": True,
        "missing_artifacts": [],
        "extra_artifacts": [],
    },
}

INVALID_MANIFESTS: list[tuple[str, dict]] = [
    (
        "missing manifest_id",
        {k: v for k, v in VALID_MANIFEST.items() if k != "manifest_id"},
    ),
    (
        "manifest_id pattern invalid",
        {**VALID_MANIFEST, "manifest_id": "invalid-id"},
    ),
    (
        "run_ref pattern invalid",
        {**VALID_MANIFEST, "run_ref": "dr-bad-format"},
    ),
    (
        "sha256 not 64 hex chars",
        {
            **VALID_MANIFEST,
            "artifacts": [
                {
                    **VALID_MANIFEST["artifacts"][0],
                    "sha256": "short",
                }
            ],
        },
    ),
    (
        "artifact_type invalid",
        {
            **VALID_MANIFEST,
            "artifacts": [
                {
                    **VALID_MANIFEST["artifacts"][0],
                    "artifact_type": "executable",
                }
            ],
        },
    ),
    (
        "retention policy invalid",
        {
            **VALID_MANIFEST,
            "retention": {
                **VALID_MANIFEST["retention"],
                "policy": "keep_forever",
            },
        },
    ),
    (
        "artifact_count negative",
        {**VALID_MANIFEST, "artifact_count": -1},
    ),
    (
        "missing approval_ref",
        {k: v for k, v in VALID_MANIFEST.items() if k != "approval_ref"},
    ),
    (
        "artifact count mismatch",
        {**VALID_MANIFEST, "artifact_count": 1},
    ),
    (
        "final manifest cannot be empty",
        {**VALID_MANIFEST, "artifact_count": 0, "artifacts": []},
    ),
    (
        "absolute artifact path rejected",
        {
            **VALID_MANIFEST,
            "artifacts": [{**VALID_MANIFEST["artifacts"][0], "path": "/tmp/report.md"}],
        },
    ),
    (
        "path traversal rejected",
        {
            **VALID_MANIFEST,
            "artifacts": [{**VALID_MANIFEST["artifacts"][0], "path": "reports/../.env"}],
            "artifact_count": 1,
        },
    ),
    (
        "env path rejected",
        {
            **VALID_MANIFEST,
            "artifacts": [{**VALID_MANIFEST["artifacts"][0], "path": "reports/.env"}],
            "artifact_count": 1,
        },
    ),
    (
        "sensitive-looking path rejected",
        {
            **VALID_MANIFEST,
            "artifacts": [{**VALID_MANIFEST["artifacts"][0], "path": "reports/token-dump.md"}],
            "artifact_count": 1,
        },
    ),
]


class TestRehearsalArtifactManifest:
    """Tests for the Rehearsal Artifact Archive Manifest."""

    def test_schema_file_exists(self) -> None:
        """The JSON schema file must exist."""
        assert SCHEMA_PATH.is_file(), f"Schema not found: {SCHEMA_PATH}"

    def test_schema_is_valid_json(self) -> None:
        """The JSON schema file must parse as valid JSON."""
        data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        assert data["title"] == "Rehearsal Artifact Archive Manifest"

    def test_valid_manifest_passes(self) -> None:
        """A valid manifest must pass Pydantic validation."""
        manifest = RehearsalArtifactManifest(**VALID_MANIFEST)
        assert manifest.manifest_id == "mf-20260610-143000-a1b2c3d4"
        assert manifest.artifact_count == 2
        assert manifest.validation_summary.all_checksums_valid is True

    def test_valid_manifest_without_optional_fields(self) -> None:
        """A manifest without optional total_size_bytes must still validate."""
        minimal = {k: v for k, v in VALID_MANIFEST.items() if k != "total_size_bytes"}
        manifest = RehearsalArtifactManifest(**minimal)
        assert manifest.total_size_bytes is None

    def test_draft_manifest_empty_artifacts(self) -> None:
        """A draft manifest may be empty when explicitly marked draft."""
        empty = {
            **VALID_MANIFEST,
            "manifest_stage": "draft",
            "artifact_count": 0,
            "artifacts": [],
        }
        manifest = RehearsalArtifactManifest(**empty)
        assert manifest.manifest_stage == "draft"
        assert manifest.artifact_count == 0
        assert len(manifest.artifacts) == 0

    @pytest.mark.parametrize("reason,manifest", INVALID_MANIFESTS)
    def test_invalid_manifests_fail(self, reason: str, manifest: dict) -> None:
        """Each invalid manifest must fail validation with a clear error."""
        with pytest.raises(ValidationError):
            RehearsalArtifactManifest(**manifest)

    def test_sha256_is_64_hex_chars(self) -> None:
        """Each SHA-256 checksum must be exactly 64 lowercase hex characters."""
        for art in VALID_MANIFEST["artifacts"]:
            assert len(art["sha256"]) == 64
            assert all(c in "0123456789abcdef" for c in art["sha256"])

    def test_run_ref_matches_manifest_id_prefix(self) -> None:
        """The run_ref should match the dr- prefix pattern."""
        manifest = RehearsalArtifactManifest(**VALID_MANIFEST)
        assert manifest.run_ref.startswith("dr-")
        assert manifest.manifest_id.startswith("mf-")
