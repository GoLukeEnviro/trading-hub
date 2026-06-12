"""Sanitized audit outputs for the Weight Proposal Engine (issue #63).

Outputs:

- ``render_sanitized_json_proposal`` — deterministic JSON.
- ``render_sanitized_markdown_report`` — human-review Markdown.
- ``write_proposal_artifact`` — atomic write to an explicit
  approved derived-report destination with path-traversal protection
  and source/destination aliasing rejection.

All outputs are sanitized: no filesystem paths, no raw credentials,
no full ledger records, and no environment values.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Final

from si_v2.propose.weight_proposal.models import (
    BatchFingerprint,
    WeightProposal,
    WeightProposalBatch,
)

# Characters that must NEVER appear in a sanitized free-form field.
# We strip ASCII control characters (0x00-0x1F except tab/newline) and
# DEL (0x7F).
_SANITIZE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Field-level "must never contain" patterns (case-insensitive substring).
_FORBIDDEN_SUBSTRINGS: Final[tuple[str, ...]] = (
    "api_key",
    "secret",
    "password",
    "token",
    "credential",
    "/home/",
    "/opt/data",
    "/etc/",
    "aws_",
    "ghp_",
    "gho_",
    "ssh-rsa",
    "ssh-ed25519",
    "PRIVATE KEY",
)


def _sanitize_text(value: str, max_len: int = 2000) -> str:
    """Strip control chars and reject forbidden substrings."""
    cleaned = _SANITIZE_RE.sub("?", value)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + "…"
    lower = cleaned.lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        if needle.lower() in lower:
            raise ValueError(
                f"sanitize_text: forbidden substring {needle!r} found"
            )
    return cleaned


def render_sanitized_json_proposal(
    proposal: WeightProposal,
) -> str:
    """Render a sanitized JSON proposal artifact.

    Free-form text fields are sanitized; numbers are kept verbatim.
    """
    sanitized = proposal.model_copy(
        update={
            "expected_analytical_impact": _sanitize_text(
                proposal.expected_analytical_impact
            ),
            "risk_notes": tuple(
                _sanitize_text(n) for n in proposal.risk_notes
            ),
        }
    )
    return sanitized.canonical_serialize()


def render_sanitized_markdown_report(
    batch: WeightProposalBatch,
) -> str:
    """Render a sanitized Markdown human-review report.

    The report contains:

    - batch identity and policy version;
    - stable-ordered proposals (ACCEPT first, DEFER, REJECT);
    - rejected and deferred candidate summary;
    - normalization evidence;
    - explicit no-application statement.
    """
    lines: list[str] = []
    lines.append(f"# Weight Proposal Batch — {batch.batch_id[:12]}")
    lines.append("")
    lines.append(f"- proposal_timestamp_utc: {batch.proposal_timestamp_utc}")
    lines.append(f"- policy_version: {batch.policy_version}")
    lines.append(f"- evidence_schema_version: {batch.evidence_schema_version}")
    lines.append(f"- proposal_schema_version: {batch.proposal_schema_version}")
    lines.append(f"- scoring_policy_version: {batch.scoring_policy_version}")
    lines.append(f"- batch_fingerprint: `{batch.batch_fingerprint[:16]}…`")
    lines.append("")
    lines.append("## Stable proposals (ACCEPT)")
    if batch.stable_proposals:
        for p in batch.stable_proposals:
            _append_proposal_md(lines, p)
    else:
        lines.append("_None_")
    lines.append("")
    lines.append("## Deferred candidates")
    if batch.deferred_candidates:
        for p in batch.deferred_candidates:
            _append_proposal_md(lines, p)
    else:
        lines.append("_None_")
    lines.append("")
    lines.append("## Rejected candidates")
    if batch.rejected_candidates:
        for p in batch.rejected_candidates:
            _append_proposal_md(lines, p)
    else:
        lines.append("_None_")
    lines.append("")
    lines.append("## Normalization evidence")
    for line in batch.normalization_evidence:
        lines.append(f"- {_sanitize_text(line)}")
    lines.append("")
    lines.append("## No-application statement")
    lines.append(
        "This batch is **advisory only**. It does not modify any live "
        "strategy, Freqtrade configuration, or runtime weight. Human "
        "approval is required on every ACCEPT decision; automation is "
        "explicitly forbidden. A separate approval-gated issue must act "
        "on any of these proposals."
    )
    return "\n".join(lines) + "\n"


def _append_proposal_md(lines: list[str], p: WeightProposal) -> None:
    lines.append("")
    lines.append(f"### {p.source_id} / {p.regime}  (decision: **{p.decision}**)")
    lines.append(f"- proposal_id: `{p.proposal_id[:16]}…`")
    lines.append(f"- proposal_fingerprint: `{p.proposal_fingerprint[:16]}…`")
    lines.append(f"- current_weight: {p.current_weight}")
    lines.append(f"- proposed_weight: {p.proposed_weight}")
    lines.append(f"- proposed_delta: {p.proposed_delta}")
    lines.append(f"- promotion_stage: {p.promotion_stage}")
    lines.append(f"- human_approval_required: {p.human_approval_required}")
    if p.evidence_references:
        lines.append("- evidence_references:")
        for ref in p.evidence_references:
            lines.append(f"  - `{_sanitize_text(ref, 256)}`")
    if p.typed_reasons:
        lines.append(f"- typed_reasons: {', '.join(p.typed_reasons)}")
    lines.append(
        f"- expected_analytical_impact: "
        f"{_sanitize_text(p.expected_analytical_impact, 512)}"
    )
    if p.risk_notes:
        lines.append("- risk_notes:")
        for note in p.risk_notes:
            lines.append(f"  - {_sanitize_text(note, 512)}")


def _validate_artifact_destination(output_root: Path, target: Path) -> Path:
    """Resolve and validate an artifact destination.

    Rejects:
      * paths that escape ``output_root``;
      * symlinks whose target is outside ``output_root``;
      * paths containing parent-traversal segments.
    """
    output_root = output_root.resolve()
    target_abs = target.resolve()
    try:
        target_abs.relative_to(output_root)
    except ValueError as exc:
        raise ValueError(
            f"artifact path {target} escapes output root {output_root}"
        ) from exc
    # Disallow parent-traversal segments in the *user-supplied* path
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


def write_proposal_artifact(
    output_root: Path,
    artifact_name: str,
    content: str,
) -> Path:
    """Write a sanitized proposal artifact atomically.

    The artifact is created inside ``output_root``. If the file
    already exists with different content, the existing file is left
    alone and the call returns the existing path (idempotency for
    the audit path; we never overwrite a real audit record with
    changed content). The function refuses to create paths that
    escape ``output_root`` or that use symlinks to escape the root.
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
            # Idempotent re-run: same content, return existing path.
            return validated
        raise FileExistsError(
            f"refusing to overwrite existing artifact {validated} "
            "with changed content"
        )
    # Atomic write: tmp file in the same directory, then rename.
    fd, tmp = tempfile.mkstemp(
        prefix=f".{artifact_name}.", dir=str(Path(output_root)), suffix=".tmp"
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


def compute_fingerprint_manifest(
    batch: WeightProposalBatch,
    json_artifacts: dict[str, str] | None = None,
    markdown_artifacts: dict[str, str] | None = None,
) -> BatchFingerprint:
    """Compute a SHA-256 fingerprint manifest for a batch.

    The manifest hashes:

    - the canonical JSON of the batch itself (the ``batch_fingerprint``);
    - each ``WeightProposal``'s ``proposal_fingerprint``;
    - the SHA-256 of each rendered JSON and Markdown artifact (if supplied).
    """
    canonical_batch = batch.canonical_serialize()
    batch_hash = hashlib.sha256(canonical_batch.encode("utf-8")).hexdigest()

    proposal_fps: dict[str, str] = {}
    for p in batch.stable_proposals:
        proposal_fps[p.proposal_id] = p.proposal_fingerprint
    for p in batch.deferred_candidates:
        proposal_fps[p.proposal_id] = p.proposal_fingerprint
    for p in batch.rejected_candidates:
        proposal_fps[p.proposal_id] = p.proposal_fingerprint

    artifact_hashes: dict[str, str] = {}
    for name, content in (json_artifacts or {}).items():
        artifact_hashes[name] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    for name, content in (markdown_artifacts or {}).items():
        artifact_hashes[name] = hashlib.sha256(content.encode("utf-8")).hexdigest()

    return BatchFingerprint(
        batch_id=batch.batch_id,
        batch_fingerprint=batch_hash,
        proposal_fingerprints=proposal_fps,
        artifact_hashes=artifact_hashes,
    )
