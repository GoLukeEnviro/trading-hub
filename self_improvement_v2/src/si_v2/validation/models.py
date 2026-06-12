"""Typed contracts for the Validation Gate Matrix (issue #65).

All models are Pydantic v2 with ``ConfigDict(strict=True)``,
``extra='forbid'``, and zero ``Any`` usage.

Status semantics:
    PASS — gate condition satisfied.
    FAIL — gate condition violated; blocks progression.
    DEFER — insufficient evidence to decide; may be resolved later.
    NOT_APPLICABLE — gate does not apply to this episode.

Overall verdict semantics:
    Any FAIL => overall FAIL.
    No FAIL, any DEFER => overall DEFER.
    All PASS or NOT_APPLICABLE => overall PASS.
    PASS means ready for human review only; it never means
    approved, deployable, executable, shadow-ready, or live-ready.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from si_v2.propose.proposal_scoring.models import POLICY_VERSION
from si_v2.reports.episode_report import (
    EPISODE_SCHEMA_VERSION as EPISODE_REPORT_SCHEMA_VERSION,
)

VALIDATION_MATRIX_VERSION: str = "gate_matrix_v1"

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ValidationGateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    DEFER = "DEFER"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ValidationGateSeverity(StrEnum):
    """Severity when a gate fails.

    ``HARD`` gates block overall PASS unconditionally.
    ``SOFT`` gates produce DEFER unless overridden by a HARD failure.
    """

    HARD = "HARD"
    SOFT = "SOFT"


# ---------------------------------------------------------------------------
# Gate inputs
# ---------------------------------------------------------------------------


class ValidationGateEvidence(BaseModel):
    """Evidence that a gate evaluator consumed or produced."""

    model_config = ConfigDict(strict=True, extra="forbid")

    key: str = Field(max_length=256)
    value: str = Field(max_length=2000)
    detail: str = Field(default="", max_length=2000)


class ValidationGateDefinition(BaseModel):
    """Static definition of a single validation gate.

    Gates are evaluated in stable registry order.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    gate_id: str = Field(min_length=1, max_length=128)
    domain: str = Field(min_length=1, max_length=128)
    description: str = Field(max_length=2000)
    severity: ValidationGateSeverity = ValidationGateSeverity.HARD


class ValidationGateResult(BaseModel):
    """Result of evaluating a single validation gate."""

    model_config = ConfigDict(strict=True, extra="forbid")

    gate_id: str = Field(min_length=1, max_length=128)
    status: ValidationGateStatus
    severity: ValidationGateSeverity
    reason: str = Field(max_length=2000)
    evidence: tuple[ValidationGateEvidence, ...] = Field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return self.status == ValidationGateStatus.PASS

    @property
    def is_blocking(self) -> bool:
        return self.status == ValidationGateStatus.FAIL and self.severity == ValidationGateSeverity.HARD


# ---------------------------------------------------------------------------
# Matrix inputs
# ---------------------------------------------------------------------------


class ValidationMatrixRequest(BaseModel):
    """Complete request to run the validation gate matrix.

    At minimum requires an ``episode_schema_version`` and
    ``policy_version``, plus the actual proposal and evidence data
    that the gates evaluate.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    episode_schema_version: str = EPISODE_REPORT_SCHEMA_VERSION
    policy_version: str = POLICY_VERSION
    matrix_version: str = VALIDATION_MATRIX_VERSION

    # Gate-specific inputs
    # Each gate picks the fields it needs; remaining fields are IGNORED.
    has_proposal_accept: bool = False
    has_proposal_reject: bool = False
    has_proposal_defer: bool = False
    evidence_fingerprints_valid: bool = True
    evidence_sufficient_sample: bool = True
    evidence_not_stale: bool = True
    evidence_not_conflicting: bool = True
    evidence_expectancy_not_negative_for_increase: bool = True
    evidence_drawdown_within_bounds: bool = True
    backtest_present_and_passed: bool = False
    walk_forward_present_and_passed: bool = False
    episode_verdict_is_hardened: bool = True
    episode_fingerprint_manifest_consistent: bool = True
    human_review_accepted: bool = False
    human_review_rejected: bool = False
    human_review_pending: bool = True
    human_review_deferred: bool = False
    shadow_readiness_metadata_ok: bool = True
    dry_run_readiness_metadata_ok: bool = True
    policy_compliant: bool = True


# ---------------------------------------------------------------------------
# Matrix outputs
# ---------------------------------------------------------------------------


class ValidationMatrixResult(BaseModel):
    """The complete result of running the validation gate matrix."""

    model_config = ConfigDict(strict=True, extra="forbid")

    matrix_version: str = VALIDATION_MATRIX_VERSION
    policy_version: str = POLICY_VERSION
    episode_schema_version: str = EPISODE_REPORT_SCHEMA_VERSION
    overall_verdict: ValidationGateStatus
    gates: tuple[ValidationGateResult, ...]
    matrix_fingerprint: str = Field(min_length=64, max_length=64)

    @property
    def passed(self) -> bool:
        return self.overall_verdict == ValidationGateStatus.PASS

    @property
    def failed(self) -> bool:
        return self.overall_verdict == ValidationGateStatus.FAIL

    @property
    def deferred(self) -> bool:
        return self.overall_verdict == ValidationGateStatus.DEFER


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------


def compute_matrix_fingerprint(result: ValidationMatrixResult) -> str:
    """Deterministic SHA-256 fingerprint for a matrix result."""
    raw = json.dumps(
        {
            "matrix_version": result.matrix_version,
            "policy_version": result.policy_version,
            "episode_schema_version": result.episode_schema_version,
            "overall_verdict": result.overall_verdict.value,
            "gates": [
                {
                    "gate_id": g.gate_id,
                    "status": g.status.value,
                    "severity": g.severity.value,
                }
                for g in result.gates
            ],
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
