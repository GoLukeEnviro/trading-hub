"""Typed contracts for the Weight Proposal Engine (issue #63).

All models are Pydantic v2 with ``ConfigDict(strict=True)``,
``extra='forbid'``, and zero ``Any`` usage.

Decimal values are quantized at the module boundary (see
``si_v2.propose.proposal_scoring.decimal_safe`` for the shared
quantization helpers).

Numeric conventions:

- Weights are in ``[0.0, 1.0]``.
- Deltas are signed and in ``[-1.0, 1.0]``.
- All Decimal values are quantized to ``SCORING_QUANTUM = 1e-6``
  with ``ROUND_HALF_EVEN``.

Identity conventions:

- A ``(source_id, regime)`` pair is the unit of identity for
  ``CurrentWeight`` and ``WeightProposal``.
- The engine never infers a current weight from runtime
  configuration; every current weight must be supplied explicitly
  in the ``WeightProposalRequest``.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from si_v2.propose.proposal_scoring.decimal_safe import (
    to_decimal,
)
from si_v2.propose.proposal_scoring.models import (
    POLICY_VERSION,
    ScoringPolicy,
)

PROPOSAL_SCHEMA_VERSION: Final[str] = "weight_proposal_v1"

# Strict identity regexes for source_id and regime.
_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_\-:./]{1,128}$")
_REGIME_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _validate_source_id(value: str) -> str:
    if not _SOURCE_ID_RE.match(value):
        raise ValueError(
            f"source_id={value!r} does not match {_SOURCE_ID_RE.pattern!r}"
        )
    return value


def _validate_regime(value: str) -> str:
    if not _REGIME_RE.match(value):
        raise ValueError(
            f"regime={value!r} does not match {_REGIME_RE.pattern!r}"
        )
    return value


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class CurrentWeight(BaseModel):
    """A current weight for a single (source_id, regime) pair.

    The current weight is **always supplied explicitly** by the caller.
    The engine never reads it from live configuration.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    source_id: str
    regime: str
    weight: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        out: dict[str, object] = dict(data)
        if "weight" in out and out["weight"] is not None:
            out["weight"] = to_decimal(out["weight"], "CurrentWeight.weight")
        if "source_id" in out and isinstance(out["source_id"], str):
            out["source_id"] = _validate_source_id(out["source_id"])
        if "regime" in out and isinstance(out["regime"], str):
            out["regime"] = _validate_regime(out["regime"])
        return out


class NormalizationGroup(BaseModel):
    """Definition of a normalization group.

    A group is identified by ``group_id`` and contains a set of
    (source_id, regime) identities. After the engine produces
    proposals for each identity in the group, the proposals are
    re-normalized so that the group sums to exactly ``target_sum``
    (default 1.0).
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    group_id: str = Field(min_length=1, max_length=128)
    identities: tuple[tuple[str, str], ...]
    target_sum: Decimal = Field(default=Decimal("1"))

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        out: dict[str, object] = dict(data)
        if "target_sum" in out and out["target_sum"] is not None:
            out["target_sum"] = to_decimal(
                out["target_sum"], "NormalizationGroup.target_sum"
            )
        # Normalize identities to a tuple of (source_id, regime) tuples
        raw = out.get("identities")
        if raw is not None:
            normalized: list[tuple[str, str]] = []
            for entry in raw:  # type: ignore[union-attr]
                if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                    raise ValueError(
                        f"identity entry {entry!r} must be (source_id, regime)"
                    )
                source_id, regime = entry
                if not isinstance(source_id, str):
                    raise ValueError(
                        f"identity source_id must be a string, got "
                        f"{type(source_id).__name__}"
                    )
                if not isinstance(regime, str):
                    raise ValueError(
                        f"identity regime must be a string, got "
                        f"{type(regime).__name__}"
                    )
                normalized.append(
                    (_validate_source_id(source_id), _validate_regime(regime))
                )
            out["identities"] = tuple(normalized)
        return out

    @model_validator(mode="after")
    def _validate_target_sum(self) -> NormalizationGroup:
        if self.target_sum < Decimal("0"):
            raise ValueError(
                f"NormalizationGroup.target_sum={self.target_sum} must be >= 0"
            )
        # No upper bound — the caller is responsible for sane targets.
        if not self.identities:
            raise ValueError("NormalizationGroup.identities must not be empty")
        return self


class WeightProposalRequest(BaseModel):
    """Typed request to the Weight Proposal Engine.

    All fields are required except ``scoring_policy`` and
    ``normalization_groups`` (which have documented defaults) and
    ``evidence_schema_version`` (which defaults to 1).
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    proposal_timestamp_utc: str = Field(min_length=10, max_length=40)
    current_weights: tuple[CurrentWeight, ...]
    # ``evidence_records`` is intentionally typed as ``tuple[object, ...]``
    # so the engine does not need to import the input-pipeline module.
    # The engine validates structural compatibility at the boundary
    # via its ``ProposalEvidenceRecordLike`` Protocol.
    evidence_records: tuple[object, ...]
    scoring_policy: ScoringPolicy
    evidence_schema_version: int = Field(default=1, ge=1)
    normalization_groups: tuple[NormalizationGroup, ...] = Field(
        default_factory=tuple
    )
    # Engine-level bounds enforced on every emitted proposal.
    minimum_weight: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        le=Decimal("1"),
        description=(
            "Documented minimum weight. Any candidate whose proposed "
            "weight would be below this is clamped to it."
        ),
    )
    maximum_weight: Decimal = Field(
        default=Decimal("1"),
        ge=Decimal("0"),
        le=Decimal("1"),
        description=(
            "Documented maximum weight. Any candidate whose proposed "
            "weight would be above this is clamped to it."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        out: dict[str, object] = dict(data)
        for fname in ("minimum_weight", "maximum_weight"):
            if fname in out and out[fname] is not None:
                out[fname] = to_decimal(out[fname], f"WeightProposalRequest.{fname}")
        return out

    @model_validator(mode="after")
    def _validate_bounds(self) -> WeightProposalRequest:
        if self.minimum_weight > self.maximum_weight:
            raise ValueError(
                "minimum_weight must be <= maximum_weight; got "
                f"min={self.minimum_weight}, max={self.maximum_weight}"
            )
        # Reject duplicate (source_id, regime) in current_weights
        seen: set[tuple[str, str]] = set()
        for cw in self.current_weights:
            key = (cw.source_id, cw.regime)
            if key in seen:
                raise ValueError(
                    f"duplicate current_weight for {key}"
                )
            seen.add(key)
        return self


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


class WeightProposal(BaseModel):
    """A single, bounded, deterministic weight proposal.

    The decision is one of ACCEPT, REJECT, or DEFER, and matches the
    ``score_proposal`` decision the engine produced. The
    ``score_breakdown`` is the typed ``ProposalScoreBreakdown``
    carried verbatim from the scoring policy.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    proposal_id: str = Field(min_length=64, max_length=64)
    source_id: str
    regime: str
    current_weight: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    proposed_weight: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    proposed_delta: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    decision: str = Field(pattern=r"^(ACCEPT|REJECT|DEFER)$")
    promotion_stage: str
    score_breakdown: object  # ProposalScoreBreakdown (narrow at runtime)
    evidence_references: tuple[str, ...]
    expected_analytical_impact: str
    risk_notes: tuple[str, ...]
    typed_reasons: tuple[str, ...]  # ProposalRejectionReason string values
    human_approval_required: bool = True
    policy_version: str = POLICY_VERSION
    evidence_schema_version: int = Field(ge=1)
    proposal_schema_version: str = PROPOSAL_SCHEMA_VERSION
    proposal_fingerprint: str = Field(min_length=64, max_length=64)

    def canonical_serialize(self) -> str:
        """Deterministic JSON serialization (sorted keys, Decimal as str)."""
        import json

        def _default(o: object) -> object:
            if isinstance(o, Decimal):
                return str(o)
            if isinstance(o, tuple):
                return [_default(x) for x in o]
            if isinstance(o, list):
                return [_default(x) for x in o]
            if hasattr(o, "model_dump"):
                return _default(o.model_dump())
            raise TypeError(
                f"Object of type {type(o).__name__} is not JSON-serializable"
            )

        return json.dumps(self.model_dump(), sort_keys=True, default=_default)


class WeightProposalBatch(BaseModel):
    """A typed batch of weight proposals for one request.

    The batch is **stable-ordered**: proposals are ordered by
    ``(group_id, source_id, regime)`` (groups without an explicit
    group are sorted last). Within a group, the order is by
    ``(source_id, regime)``.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    batch_id: str = Field(min_length=64, max_length=64)
    proposal_timestamp_utc: str
    policy_version: str = POLICY_VERSION
    evidence_schema_version: int = Field(ge=1)
    proposal_schema_version: str = PROPOSAL_SCHEMA_VERSION
    scoring_policy_version: str = POLICY_VERSION
    stable_proposals: tuple[WeightProposal, ...]
    rejected_candidates: tuple[WeightProposal, ...]
    deferred_candidates: tuple[WeightProposal, ...]
    normalization_evidence: tuple[str, ...]  # human-readable summary lines
    batch_fingerprint: str = Field(min_length=64, max_length=64)

    def canonical_serialize(self) -> str:
        import json

        def _default(o: object) -> object:
            if isinstance(o, Decimal):
                return str(o)
            if isinstance(o, tuple):
                return [_default(x) for x in o]
            if isinstance(o, list):
                return [_default(x) for x in o]
            if hasattr(o, "model_dump"):
                return _default(o.model_dump())
            raise TypeError(
                f"Object of type {type(o).__name__} is not JSON-serializable"
            )

        return json.dumps(self.model_dump(), sort_keys=True, default=_default)


class BatchFingerprint(BaseModel):
    """A SHA-256 fingerprint manifest for one batch.

    Hashes are over the canonical JSON serialization of each artifact,
    keyed by stable artifact identifiers.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    batch_id: str = Field(min_length=64, max_length=64)
    batch_fingerprint: str = Field(min_length=64, max_length=64)
    proposal_fingerprints: dict[str, str]
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
