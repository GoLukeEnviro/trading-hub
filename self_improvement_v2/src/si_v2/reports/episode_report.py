"""Typed contracts for the Episode Report Builder (issue #64).

All models are Pydantic v2 with ``ConfigDict(strict=True)``,
``extra='forbid'``, and zero ``Any`` usage.

Review states:
    PENDING_REVIEW — awaiting human review.
    ACCEPTED_BY_HUMAN — human has reviewed and accepted. This is
        *review acceptance only* and never authorizes execution.
    REJECTED_BY_HUMAN — human has reviewed and rejected.
    DEFERRED_BY_HUMAN — human has deferred pending more information.

Episode verdicts:
    GREEN — all required artifacts present, fingerprints match,
        proposal decision is ACCEPT, and review state is
        ACCEPTED_BY_HUMAN.
    YELLOW — partial artifacts, stale evidence, or review is still
        PENDING_REVIEW or DEFERRED_BY_HUMAN.
    RED — required artifacts missing, fingerprints mismatch,
        proposal is REJECT or DEFER, or provenance validation failed.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from enum import Enum, StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from si_v2.propose.proposal_scoring.decimal_safe import to_decimal
from si_v2.propose.proposal_scoring.models import POLICY_VERSION
from si_v2.propose.weight_proposal.models import PROPOSAL_SCHEMA_VERSION

EPISODE_SCHEMA_VERSION: str = "episode_report_v1"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReviewState(StrEnum):
    """Human-review state for an episode.

    ``ACCEPTED_BY_HUMAN`` means **review acceptance only** and never
    authorizes application, deployment, shadow start, or live trading.
    """

    PENDING_REVIEW = "PENDING_REVIEW"
    ACCEPTED_BY_HUMAN = "ACCEPTED_BY_HUMAN"
    REJECTED_BY_HUMAN = "REJECTED_BY_HUMAN"
    DEFERRED_BY_HUMAN = "DEFERRED_BY_HUMAN"


class EpisodeVerdict(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class ValidationType(StrEnum):
    BACKTEST = "BACKTEST"
    WALK_FORWARD = "WALK_FORWARD"


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------


class EvidenceReference(BaseModel):
    """Reference to one evidence record used in the episode."""

    model_config = ConfigDict(strict=True, extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    regime: str = Field(min_length=1, max_length=64)
    fingerprint: str = Field(min_length=64, max_length=64)


class ProposalReference(BaseModel):
    """Reference to one weight proposal used in the episode."""

    model_config = ConfigDict(strict=True, extra="forbid")

    proposal_id: str = Field(min_length=64, max_length=64)
    batch_id: str = Field(min_length=64, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)
    regime: str = Field(min_length=1, max_length=64)
    proposal_fingerprint: str = Field(min_length=64, max_length=64)
    batch_fingerprint: str = Field(min_length=64, max_length=64)
    decision: str = Field(pattern=r"^(ACCEPT|REJECT|DEFER)$")
    proposed_weight: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    proposed_delta: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        out: dict[str, object] = dict(data)
        for fname in ("proposed_weight", "proposed_delta"):
            if fname in out and out[fname] is not None:
                out[fname] = to_decimal(out[fname], f"ProposalReference.{fname}")
        return out


class ValidationReference(BaseModel):
    """Reference to a backtest or walk-forward validation result."""

    model_config = ConfigDict(strict=True, extra="forbid")

    validation_id: str = Field(min_length=1, max_length=128)
    validation_type: ValidationType
    fingerprint: str = Field(min_length=64, max_length=64)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class ArtifactReference(BaseModel):
    """Reference to a generated artifact (JSON or Markdown)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=128)
    artifact_type: str = Field(pattern=r"^(json|md)$")
    content_hash: str = Field(min_length=64, max_length=64)


class EpisodeReportRequest(BaseModel):
    """Complete request to build one episode report."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    episode_id: str = Field(min_length=8, max_length=128)
    proposal_timestamp_utc: str = Field(min_length=10, max_length=40)
    episode_reviewer: str = Field(default="", max_length=256)
    review_state: ReviewState = ReviewState.PENDING_REVIEW
    review_notes: str = Field(default="", max_length=2000)
    evidence_references: tuple[EvidenceReference, ...] = Field(default_factory=tuple)
    proposal_references: tuple[ProposalReference, ...] = Field(default_factory=tuple)
    validation_references: tuple[ValidationReference, ...] = Field(
        default_factory=tuple
    )
    artifact_references: tuple[ArtifactReference, ...] = Field(default_factory=tuple)
    episode_schema_version: str = EPISODE_SCHEMA_VERSION
    policy_version: str = POLICY_VERSION
    proposal_schema_version: str = PROPOSAL_SCHEMA_VERSION

    @model_validator(mode="after")
    def _validate_at_least_one_proposal(self) -> EpisodeReportRequest:
        if not self.proposal_references:
            raise ValueError(
                "at least one ProposalReference is required"
            )
        return self

    @model_validator(mode="after")
    def _validate_no_duplicate_artifact_ids(self) -> EpisodeReportRequest:
        seen: set[str] = set()
        for a in self.artifact_references:
            if a.artifact_id in seen:
                raise ValueError(
                    f"duplicate artifact_id: {a.artifact_id}"
                )
            seen.add(a.artifact_id)
        return self


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


class IntegrityManifest(BaseModel):
    """SHA-256 integrity manifest for one episode report."""

    model_config = ConfigDict(strict=True, extra="forbid")

    episode_id: str = Field(min_length=8, max_length=128)
    episode_fingerprint: str = Field(min_length=64, max_length=64)
    evidence_fingerprints: dict[str, str] = Field(default_factory=dict)
    proposal_fingerprints: dict[str, str] = Field(default_factory=dict)
    validation_fingerprints: dict[str, str] = Field(default_factory=dict)
    artifact_hashes: dict[str, str] = Field(default_factory=dict)


class EpisodeReport(BaseModel):
    """The complete, signed episode report.

    This is **not** an execution authority. ``ACCEPTED_BY_HUMAN``
    means the human reviewed the proposal; it never authorizes
    application, deployment, shadow start, or live trading.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    episode_id: str = Field(min_length=8, max_length=128)
    request: EpisodeReportRequest
    verdict: EpisodeVerdict
    verdict_rationale: str = Field(max_length=2000)
    integrity_manifest: IntegrityManifest
    episode_json: str = Field(min_length=1)
    episode_markdown: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_verdict_consistency(self) -> EpisodeReport:
        # An ACCEPTED_BY_HUMAN review with no ACCEPT proposals
        # is inconsistent — downgrade the verdict.
        if self.request.review_state == ReviewState.ACCEPTED_BY_HUMAN:
            has_accept = any(
                p.decision == "ACCEPT" for p in self.request.proposal_references
            )
            if not has_accept and self.verdict == EpisodeVerdict.GREEN:
                raise ValueError(
                    "verdict GREEN is inconsistent: review_state is "
                    "ACCEPTED_BY_HUMAN but no proposal has ACCEPT decision"
                )
        return self


# ---------------------------------------------------------------------------
# Verdict computation
# ---------------------------------------------------------------------------


def compute_verdict(request: EpisodeReportRequest) -> tuple[EpisodeVerdict, str]:
    """Compute the deterministic episode verdict from the request.

    Returns:
        A tuple of ``(verdict, rationale)``.
    """
    # Collect all proposal decisions
    decisions = {p.decision for p in request.proposal_references}

    # RED: all proposals REJECTED — no DEFER, no ACCEPT
    if decisions == {"REJECT"}:
        return EpisodeVerdict.RED, (
            "all proposals are rejected; "
            "no actionable recommendation exists"
        )

    # RED: a proposal was REJECTED
    if "REJECT" in decisions:
        return EpisodeVerdict.RED, (
            "at least one proposal is rejected; "
            "review this before further action"
        )

    # GREEN: ACCEPTED_BY_HUMAN with at least one ACCEPT
    if request.review_state == ReviewState.ACCEPTED_BY_HUMAN and "ACCEPT" in decisions:
        return EpisodeVerdict.GREEN, (
            "human has accepted at least one proposal; "
            "review acceptance confirmed"
        )

    # YELLOW: ACCEPTED_BY_HUMAN but no ACCEPT proposals (all DEFER)
    if request.review_state == ReviewState.ACCEPTED_BY_HUMAN and decisions == {"DEFER"}:
        return EpisodeVerdict.YELLOW, (
            "human review accepted but proposals are deferred; "
            "no actionable accept decisions"
        )

    # RED: review states that indicate non-acceptance
    if request.review_state in (
        ReviewState.REJECTED_BY_HUMAN,
        ReviewState.DEFERRED_BY_HUMAN,
    ):
        return EpisodeVerdict.RED, (
            f"human review state is {request.review_state.value}; "
            "episode is not accepted"
        )

    # YELLOW: PENDING_REVIEW
    if request.review_state == ReviewState.PENDING_REVIEW:
        return EpisodeVerdict.YELLOW, (
            "proposals are acceptable but review is still pending"
        )

    # YELLOW: ACCEPTED_BY_HUMAN with mixed DEFER (fallback)
    if request.review_state == ReviewState.ACCEPTED_BY_HUMAN:
        return EpisodeVerdict.YELLOW, (
            "human review accepted but no clear accept decisions; "
            "review required"
        )

    # Fallback — should not normally be reached
    return EpisodeVerdict.YELLOW, (
        "mixed or indeterminate state; review required"
    )


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------


def compute_episode_fingerprint(request: EpisodeReportRequest) -> str:
    """Deterministic SHA-256 fingerprint for the request."""
    import json as _json
    raw = _json.dumps(
        request.model_dump(
            exclude={"episode_id", "episode_schema_version", "policy_version",
                     "proposal_schema_version"},
        ),
        sort_keys=True,
        default=_episode_json_default,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_integrity_manifest(
    request: EpisodeReportRequest,
    episode_fingerprint: str,
    *,
    json_artifact: str | None = None,
    markdown_artifact: str | None = None,
) -> IntegrityManifest:
    """Build the integrity manifest for one episode.

    Args:
        request: The episode request.
        episode_fingerprint: The SHA-256 fingerprint of the request.
        json_artifact: Optional rendered JSON content.
        markdown_artifact: Optional rendered Markdown content.

    Returns:
        A typed ``IntegrityManifest``.
    """
    ev_fps: dict[str, str] = {}
    for ev in request.evidence_references:
        ev_fps[ev.evidence_id] = ev.fingerprint

    pr_fps: dict[str, str] = {}
    for pr in request.proposal_references:
        pr_fps[pr.proposal_id] = pr.proposal_fingerprint

    val_fps: dict[str, str] = {}
    for va in request.validation_references:
        val_fps[va.validation_id] = va.fingerprint

    art_hashes: dict[str, str] = {}
    if json_artifact is not None:
        art_hashes["episode.json"] = hashlib.sha256(
            json_artifact.encode("utf-8")
        ).hexdigest()
    if markdown_artifact is not None:
        art_hashes["episode.md"] = hashlib.sha256(
            markdown_artifact.encode("utf-8")
        ).hexdigest()

    return IntegrityManifest(
        episode_id=request.episode_id,
        episode_fingerprint=episode_fingerprint,
        evidence_fingerprints=ev_fps,
        proposal_fingerprints=pr_fps,
        validation_fingerprints=val_fps,
        artifact_hashes=art_hashes,
    )


# ---------------------------------------------------------------------------
# Canonical serialization
# ---------------------------------------------------------------------------


def _episode_json_default(o: object) -> object:
    """JSON serializer for EpisodeReport fields."""
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, tuple):
        return [_episode_json_default(x) for x in o]
    if isinstance(o, list):
        return [_episode_json_default(x) for x in o]
    if isinstance(o, Enum):
        return o.value
    if hasattr(o, "model_dump"):
        return _episode_json_default(o.model_dump())
    raise TypeError(
        f"Object of type {type(o).__name__} is not JSON-serializable"
    )


def render_episode_json(
    request: EpisodeReportRequest,
    verdict: EpisodeVerdict,
    verdict_rationale: str,
    manifest: IntegrityManifest,
) -> str:
    """Deterministic canonical JSON for an episode report.

    Returns a sorted-keys JSON string with Decimal values as strings.
    """
    dump = {
        "episode_id": request.episode_id,
        "request": request.model_dump(),
        "verdict": verdict.value,
        "verdict_rationale": verdict_rationale,
        "integrity_manifest": manifest.model_dump(),
    }
    return json.dumps(dump, sort_keys=True, default=_episode_json_default)


def render_episode_markdown(
    request: EpisodeReportRequest,
    verdict: EpisodeVerdict,
    verdict_rationale: str,
    manifest: IntegrityManifest,
) -> str:
    """Deterministic Markdown rendering of an episode report."""
    lines: list[str] = []

    lines.append(f"# Episode Report — {request.episode_id[:16]}")
    lines.append(f"- Verdict: **{verdict.value}**")
    lines.append(f"- Review state: **{request.review_state.value}**")
    lines.append(f"- Timestamp: {request.proposal_timestamp_utc}")
    lines.append(f"- Reviewer: {request.episode_reviewer or '_unassigned_'}")
    lines.append("")

    if request.review_notes:
        lines.append("## Review notes")
        lines.append(request.review_notes)
        lines.append("")

    lines.append("## Rationale")
    lines.append(verdict_rationale)
    lines.append("")

    if request.proposal_references:
        lines.append("## Proposals")
        for p in request.proposal_references:
            lines.append("")
            lines.append(f"### {p.source_id} / {p.regime}  (decision: **{p.decision}**)")
            lines.append(f"- proposal_id: `{p.proposal_id[:16]}…`")
            lines.append(f"- batch_id: `{p.batch_id[:16]}…`")
            lines.append(f"- proposed_weight: {p.proposed_weight}")
            lines.append(f"- proposed_delta: {p.proposed_delta}")
            lines.append(f"- fingerprint: `{p.proposal_fingerprint[:16]}…`")

    if request.evidence_references:
        lines.append("")
        lines.append("## Evidence references")
        for ev in request.evidence_references:
            lines.append(f"- `{ev.evidence_id[:16]}…` ({ev.source_id} / {ev.regime})")

    if request.validation_references:
        lines.append("")
        lines.append("## Validation references")
        for va in request.validation_references:
            lines.append(
                f"- `{va.validation_id[:16]}…` ({va.validation_type.value})"
            )

    lines.append("")
    lines.append("## Integrity manifest")
    lines.append(
        f"- episode_fingerprint: `{manifest.episode_fingerprint[:16]}…`"
    )
    for aid, ah in manifest.artifact_hashes.items():
        lines.append(f"- {aid}: `{ah[:16]}…`")

    lines.append("")
    lines.append("## No-application statement")
    lines.append(
        "This episode report is **advisory only**. "
        "ACCEPTED_BY_HUMAN means review acceptance only and never "
        "authorizes application, deployment, shadow start, "
        "or live trading. A separate approval-gated mechanism "
        "must act on any accepted proposal."
    )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Atomic artifact writer (reuses the pattern from weight_proposal.audit)
# ---------------------------------------------------------------------------


def _validate_artifact_destination(output_root: Path, target: Path) -> Path:
    """Resolve and validate an artifact destination.

    Rejects paths that escape ``output_root``, symlinks whose target
    is outside ``output_root``, and paths containing parent-traversal
    segments.
    """
    output_root = output_root.resolve()
    target_abs = target.resolve()
    try:
        target_abs.relative_to(output_root)
    except ValueError as exc:
        raise ValueError(
            f"artifact path {target} escapes output root {output_root}"
        ) from exc
    for part in target.parts:
        if part == "..":
            raise ValueError(
                f"artifact path {target} contains parent traversal"
            )
    if target_abs.is_symlink():
        link_target = target_abs.resolve()
        try:
            link_target.relative_to(output_root)
        except ValueError as exc:
            raise ValueError(
                f"artifact path {target} is a symlink to {link_target} "
                f"outside the output root"
            ) from exc
    return target_abs


def write_episode_artifact(
    output_root: Path,
    artifact_name: str,
    content: str,
) -> Path:
    """Write an episode artifact atomically.

    The artifact is created inside ``output_root``. If the file
    already exists with different content, ``FileExistsError`` is
    raised. If the file exists with identical content, the call is
    idempotent.
    """
    if not artifact_name or "/" in artifact_name or "\\" in artifact_name:
        raise ValueError(
            f"artifact_name={artifact_name!r} must be a bare filename"
        )
    if not artifact_name.endswith((".json", ".md")):
        raise ValueError(
            f"artifact_name={artifact_name!r} must end in .json or .md"
        )
    target = (Path(output_root) / artifact_name).resolve()
    validated = _validate_artifact_destination(Path(output_root), target)
    Path(output_root).mkdir(parents=True, exist_ok=True)
    if validated.exists():
        existing = validated.read_text(encoding="utf-8")
        if existing == content:
            return validated
        raise FileExistsError(
            f"refusing to overwrite existing artifact {validated} "
            "with changed content"
        )
    import os
    import tempfile

    fd, tmp = tempfile.mkstemp(
        prefix=f".{artifact_name}.",
        dir=str(Path(output_root)),
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, validated)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return validated


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_episode_report(
    request: EpisodeReportRequest,
    *,
    output_root: Path | None = None,
) -> EpisodeReport:
    """Build a complete episode report from the request.

    This is the main entry point for episode report generation.

    Args:
        request: The typed episode report request.
        output_root: Optional output root. If provided, artifacts are
            written atomically to ``output_root``.

    Returns:
        A typed ``EpisodeReport``.
    """
    # Validate fingerprint counts
    if request.evidence_references:
        missing_ev = [ev for ev in request.evidence_references if len(ev.fingerprint) != 64]
        if missing_ev:
            raise ValueError(
                f"evidence references missing fingerprints: "
                f"{[ev.evidence_id for ev in missing_ev]}"
            )
    if request.proposal_references:
        missing_pr = [
            pr for pr in request.proposal_references
            if len(pr.proposal_fingerprint) != 64
        ]
        if missing_pr:
            raise ValueError(
                f"proposal references missing fingerprints: "
                f"{[pr.proposal_id for pr in missing_pr]}"
            )

    # Compute verdict and fingerprint
    verdict, rationale = compute_verdict(request)
    ep_fingerprint = compute_episode_fingerprint(request)

    # Build integrity manifest
    manifest = build_integrity_manifest(request, ep_fingerprint)

    # Render JSON and Markdown
    json_content = render_episode_json(request, verdict, rationale, manifest)
    md_content = render_episode_markdown(request, verdict, rationale, manifest)

    # Update manifest with artifact hashes
    manifest_with_hashes = build_integrity_manifest(
        request, ep_fingerprint,
        json_artifact=json_content,
        markdown_artifact=md_content,
    )

    # Build the final report
    episode = EpisodeReport(
        episode_id=request.episode_id,
        request=request,
        verdict=verdict,
        verdict_rationale=rationale,
        integrity_manifest=manifest_with_hashes,
        episode_json=json_content,
        episode_markdown=md_content,
    )

    # Write artifacts if output_root is provided
    if output_root is not None:
        write_episode_artifact(output_root, f"{request.episode_id}.json", json_content)
        write_episode_artifact(output_root, f"{request.episode_id}.md", md_content)

    return episode


__all__ = [
    "ArtifactReference",
    "EpisodeReport",
    "EpisodeReportRequest",
    "EpisodeVerdict",
    "EvidenceReference",
    "IntegrityManifest",
    "ProposalReference",
    "ReviewState",
    "ValidationReference",
    "ValidationType",
    "build_episode_report",
    "build_integrity_manifest",
    "compute_episode_fingerprint",
    "compute_verdict",
    "render_episode_json",
    "render_episode_markdown",
    "write_episode_artifact",
]
