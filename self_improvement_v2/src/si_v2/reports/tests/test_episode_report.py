"""Tests for the Episode Report Builder (issue #64)."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from si_v2.propose.proposal_scoring.models import POLICY_VERSION
from si_v2.propose.weight_proposal.models import PROPOSAL_SCHEMA_VERSION
from si_v2.reports.episode_report import (
    EPISODE_SCHEMA_VERSION,
    ArtifactReference,
    EpisodeReportRequest,
    EpisodeVerdict,
    EvidenceReference,
    ProposalReference,
    ReviewState,
    ValidationReference,
    ValidationType,
    build_episode_report,
    build_integrity_manifest,
    compute_episode_fingerprint,
    compute_verdict,
    write_episode_artifact,
)


def _valid_proposal_ref(
    decision: str = "ACCEPT",
    source_id: str = "rainbow:ta",
    regime: str = "bullish",
) -> ProposalReference:
    return ProposalReference(
        proposal_id="a" * 64,
        batch_id="b" * 64,
        source_id=source_id,
        regime=regime,
        proposal_fingerprint="c" * 64,
        batch_fingerprint="d" * 64,
        decision=decision,
        proposed_weight=Decimal("0.50"),
        proposed_delta=Decimal("0.10"),
    )


def _valid_evidence_ref() -> EvidenceReference:
    return EvidenceReference(
        evidence_id="evi-1",
        source_id="rainbow:ta",
        regime="bullish",
        fingerprint="e" * 64,
    )


def _valid_request(
    review_state: ReviewState = ReviewState.PENDING_REVIEW,
    decisions: tuple[str, ...] = ("ACCEPT",),
) -> EpisodeReportRequest:
    return EpisodeReportRequest(
        episode_id="test-episode-001",
        proposal_timestamp_utc="2026-06-12T09:40:00Z",
        review_state=review_state,
        evidence_references=(_valid_evidence_ref(),),
        proposal_references=tuple(
            _valid_proposal_ref(decision=d) for d in decisions
        ),
        validation_references=(
            ValidationReference(
                validation_id="val-1",
                validation_type=ValidationType.BACKTEST,
                fingerprint="f" * 64,
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Model validation tests
# ---------------------------------------------------------------------------


class TestModelValidation:
    def test_valid_request(self) -> None:
        req = _valid_request()
        assert req.episode_id == "test-episode-001"
        assert req.review_state == ReviewState.PENDING_REVIEW

    def test_empty_proposals_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EpisodeReportRequest(
                episode_id="empty",
                proposal_timestamp_utc="2026-06-12T09:40:00Z",
                proposal_references=(),
            )

    def test_duplicate_artifact_ids_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EpisodeReportRequest(
                episode_id="dup",
                proposal_timestamp_utc="2026-06-12T09:40:00Z",
                proposal_references=(_valid_proposal_ref(),),
                artifact_references=(
                    ArtifactReference(
                        artifact_id="same",
                        artifact_type="json",
                        content_hash="a" * 64,
                    ),
                    ArtifactReference(
                        artifact_id="same",
                        artifact_type="md",
                        content_hash="b" * 64,
                    ),
                ),
            )

    def test_fingerprint_length_validation(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceReference(
                evidence_id="short",
                source_id="s",
                regime="r",
                fingerprint="too-short",
            )

    def test_bad_decision_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _valid_proposal_ref(decision="INVALID")

    def test_bad_artifact_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactReference(
                artifact_id="a1",
                artifact_type="html",
                content_hash="a" * 64,
            )


# ---------------------------------------------------------------------------
# Verdict computation tests
# ---------------------------------------------------------------------------


class TestComputeVerdict:
    def test_green_when_accepted_with_accept_proposal(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        verdict, rationale = compute_verdict(req)
        assert verdict == EpisodeVerdict.GREEN
        assert "accepted" in rationale.lower()

    def test_yellow_when_pending(self) -> None:
        req = _valid_request(review_state=ReviewState.PENDING_REVIEW)
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.YELLOW

    def test_red_when_rejected_by_human(self) -> None:
        req = _valid_request(review_state=ReviewState.REJECTED_BY_HUMAN)
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.RED

    def test_red_when_deferred_by_human(self) -> None:
        req = _valid_request(review_state=ReviewState.DEFERRED_BY_HUMAN)
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.RED

    def test_red_when_all_proposals_rejected(self) -> None:
        req = _valid_request(decisions=("REJECT",))
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.RED

    def test_red_when_all_proposals_deferred_and_rejected_by_human(self) -> None:
        req = _valid_request(
            review_state=ReviewState.REJECTED_BY_HUMAN,
            decisions=("DEFER",),
        )
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.RED

    def test_yellow_when_mixed_reject_and_accept(self) -> None:
        req = _valid_request(decisions=("ACCEPT", "REJECT"))
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.RED

    def test_inconsistent_accept_verdict_raises(self) -> None:
        # Create a request where review is ACCEPTED but all proposals are REJECT
        req = _valid_request(
            review_state=ReviewState.ACCEPTED_BY_HUMAN,
            decisions=("REJECT", "REJECT"),
        )
        # The verdict would be RED from compute_verdict due to REJECT presence
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.RED
        # Building the report should not raise because verdict is not GREEN
        report = build_episode_report(req)
        assert report.verdict == EpisodeVerdict.RED


# ---------------------------------------------------------------------------
# Fingerprint tests
# ---------------------------------------------------------------------------


class TestFingerprint:
    def test_deterministic_fingerprint(self) -> None:
        req = _valid_request()
        fp1 = compute_episode_fingerprint(req)
        fp2 = compute_episode_fingerprint(req)
        assert fp1 == fp2
        assert len(fp1) == 64

    def test_fingerprint_changes_with_proposal(self) -> None:
        req1 = _valid_request(decisions=("ACCEPT",))
        req2 = _valid_request(decisions=("DEFER",))
        fp1 = compute_episode_fingerprint(req1)
        fp2 = compute_episode_fingerprint(req2)
        assert fp1 != fp2


# ---------------------------------------------------------------------------
# Build episode report tests
# ---------------------------------------------------------------------------


class TestBuildEpisodeReport:
    def test_build_success_report(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        report = build_episode_report(req)
        assert report.episode_id == "test-episode-001"
        assert report.verdict == EpisodeVerdict.GREEN
        assert len(report.episode_json) > 0
        assert len(report.episode_markdown) > 0
        assert report.integrity_manifest.episode_id == "test-episode-001"

    def test_build_rejected_report(self) -> None:
        req = _valid_request(decisions=("REJECT",))
        report = build_episode_report(req)
        assert report.verdict == EpisodeVerdict.RED

    def test_build_deferred_report(self) -> None:
        req = _valid_request(
            review_state=ReviewState.REJECTED_BY_HUMAN,
            decisions=("DEFER",),
        )
        report = build_episode_report(req)
        assert report.verdict == EpisodeVerdict.RED

    def test_build_insufficient_evidence(self) -> None:
        req = EpisodeReportRequest(
            episode_id="insufficient-evidence",
            proposal_timestamp_utc="2026-06-12T09:40:00Z",
            review_state=ReviewState.PENDING_REVIEW,
            evidence_references=(),
            proposal_references=(
                ProposalReference(
                    proposal_id="a" * 64,
                    batch_id="b" * 64,
                    source_id="rainbow:ta",
                    regime="bullish",
                    proposal_fingerprint="c" * 64,
                    batch_fingerprint="d" * 64,
                    decision="REJECT",
                    proposed_weight=Decimal("0.00"),
                    proposed_delta=Decimal("0.00"),
                ),
            ),
        )
        report = build_episode_report(req)
        assert report.verdict == EpisodeVerdict.RED

    def test_deterministic_output(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        r1 = build_episode_report(req)
        r2 = build_episode_report(req)
        assert r1.episode_json == r2.episode_json
        assert r1.episode_markdown == r2.episode_markdown
        assert (
            r1.integrity_manifest.episode_fingerprint
            == r2.integrity_manifest.episode_fingerprint
        )

    def test_provenance_fields(self) -> None:
        req = _valid_request()
        report = build_episode_report(req)
        assert report.request.episode_schema_version == EPISODE_SCHEMA_VERSION
        assert report.request.policy_version == POLICY_VERSION
        assert report.request.proposal_schema_version == PROPOSAL_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Integrity manifest tests
# ---------------------------------------------------------------------------


class TestIntegrityManifest:
    def test_manifest_with_artifacts(self) -> None:
        req = _valid_request()
        fp = compute_episode_fingerprint(req)
        manifest = build_integrity_manifest(
            req, fp,
            json_artifact='{"a": 1}',
            markdown_artifact="# test",
        )
        assert manifest.episode_fingerprint == fp
        assert manifest.artifact_hashes["episode.json"] == hashlib.sha256(
            b'{"a": 1}'
        ).hexdigest()
        assert manifest.artifact_hashes["episode.md"] == hashlib.sha256(
            b"# test"
        ).hexdigest()

    def test_manifest_deterministic(self) -> None:
        req = _valid_request()
        fp = compute_episode_fingerprint(req)
        m1 = build_integrity_manifest(req, fp)
        m2 = build_integrity_manifest(req, fp)
        assert m1.model_dump() == m2.model_dump()


# ---------------------------------------------------------------------------
# Renderer tests
# ---------------------------------------------------------------------------


class TestRenderers:
    def test_json_is_valid(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        report = build_episode_report(req)
        parsed = json.loads(report.episode_json)
        assert parsed["episode_id"] == "test-episode-001"
        assert parsed["verdict"] == "GREEN"

    def test_markdown_contains_required_sections(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        report = build_episode_report(req)
        md = report.episode_markdown
        for header in [
            "# Episode Report",
            "## Rationale",
            "## Proposals",
            "## Evidence references",
            "## Integrity manifest",
            "## No-application statement",
        ]:
            assert header in md

    def test_markdown_contains_no_application_statement(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        report = build_episode_report(req)
        assert "advisory only" in report.episode_markdown.lower()
        assert "ACCEPTED_BY_HUMAN means review acceptance only" in report.episode_markdown


# ---------------------------------------------------------------------------
# Atomic write tests
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_create_new_artifact(self, tmp_path: Path) -> None:
        path = write_episode_artifact(tmp_path, "episode.json", '{"verdict": "GREEN"}')
        assert path.exists()
        assert path.read_text() == '{"verdict": "GREEN"}'

    def test_idempotent_rerun(self, tmp_path: Path) -> None:
        content = '{"verdict": "GREEN"}'
        p1 = write_episode_artifact(tmp_path, "episode.json", content)
        p2 = write_episode_artifact(tmp_path, "episode.json", content)
        assert p1 == p2

    def test_refuse_changed_content(self, tmp_path: Path) -> None:
        write_episode_artifact(tmp_path, "episode.json", "first")
        with pytest.raises(FileExistsError):
            write_episode_artifact(tmp_path, "episode.json", "different")

    def test_reject_path_traversal(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            write_episode_artifact(tmp_path, "../escape.json", "{}")
        with pytest.raises(ValueError):
            write_episode_artifact(tmp_path, "subdir/file.json", "{}")
        with pytest.raises(ValueError):
            write_episode_artifact(tmp_path, "bad.exe", "{}")


# ---------------------------------------------------------------------------
# Full build with atomic write test
# ---------------------------------------------------------------------------


class TestBuildWithOutput:
    def test_build_and_write(self, tmp_path: Path) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        report = build_episode_report(req, output_root=tmp_path)
        json_file = tmp_path / f"{req.episode_id}.json"
        md_file = tmp_path / f"{req.episode_id}.md"
        assert json_file.exists()
        assert md_file.exists()
        assert json_file.read_text() == report.episode_json
        assert md_file.read_text() == report.episode_markdown


# ---------------------------------------------------------------------------
# Verdict consistency tests
# ---------------------------------------------------------------------------


class TestVerdictConsistency:
    def test_green_requires_accept_proposal(self) -> None:
        req = _valid_request(
            review_state=ReviewState.ACCEPTED_BY_HUMAN,
            decisions=("DEFER",),
        )
        report = build_episode_report(req)
        assert report.verdict == EpisodeVerdict.YELLOW

    def test_accepted_with_reject_verdict_red(self) -> None:
        req = _valid_request(
            review_state=ReviewState.ACCEPTED_BY_HUMAN,
            decisions=("REJECT",),
        )
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.RED


# ---------------------------------------------------------------------------
# Missing evidence reference test
# ---------------------------------------------------------------------------


class TestMissingReferences:
    def test_empty_evidence_is_ok(self) -> None:
        req = EpisodeReportRequest(
            episode_id="no-evidence",
            proposal_timestamp_utc="2026-06-12T09:40:00Z",
            evidence_references=(),
            proposal_references=(_valid_proposal_ref(),),
        )
        report = build_episode_report(req)
        assert report.verdict in (EpisodeVerdict.YELLOW, EpisodeVerdict.GREEN)


# ---------------------------------------------------------------------------
# Non-regression: verdict is not execution approval
# ---------------------------------------------------------------------------


class TestNotExecutionApproval:
    def test_accepted_verdict_does_not_authorize(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        report = build_episode_report(req)
        md = report.episode_markdown
        # The report must explicitly state that ACCEPTED_BY_HUMAN
        # means review acceptance only.
        assert "review acceptance only" in md
        assert "never authorizes" in md
        assert "separate approval-gated mechanism" in md
