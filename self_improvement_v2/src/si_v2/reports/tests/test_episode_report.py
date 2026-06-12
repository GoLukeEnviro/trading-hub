"""Tests for the Episode Report Builder (issue #64, hardened #185).

Covers:
- E185-01: SHA-256 hash validation
- E185-02: UTC timestamp validation
- E185-03: Canonical verdict truth table
- E185-04: Mandatory backtest/walk-forward references
- E185-05: Duplicate ID rejection
- E185-06: Fingerprint includes schema/policy versions
- E185-07: Cross-consistency of JSON, Markdown, manifest
- E185-08: Report-only safety invariants
"""

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
    EVIDENCE_SCHEMA_VERSION,
    ArtifactReference,
    EpisodeReportRequest,
    EpisodeVerdict,
    EvidenceReference,
    ProposalReference,
    ReviewState,
    Sha256Hex,
    UtcTimestamp,
    ValidationReference,
    ValidationType,
    _validate_sha256_hex,
    _validate_utc_timestamp,
    build_episode_report,
    build_integrity_manifest,
    compute_episode_fingerprint,
    compute_verdict,
    write_episode_artifact,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha(suffix: str = "a") -> str:
    """Return a valid 64-char lowercase hex string. Only hex chars a-f, 0-9."""
    # Ensure the fill character is a valid hex digit (a-f only, no 'p' or 'g' etc.)
    fill = suffix[0] if suffix and suffix[0] in "abcdef0123456789" else "a"
    return fill * 64


def _valid_proposal_ref(
    decision: str = "ACCEPT",
    source_id: str = "rainbow:ta",
    regime: str = "bullish",
) -> ProposalReference:
    return ProposalReference(
        proposal_id=_sha("a"),
        batch_id=_sha("b"),
        source_id=source_id,
        regime=regime,
        proposal_fingerprint=_sha("c"),
        batch_fingerprint=_sha("d"),
        decision=decision,
        proposed_weight=Decimal("0.50"),
        proposed_delta=Decimal("0.10"),
    )


def _valid_evidence_ref() -> EvidenceReference:
    return EvidenceReference(
        evidence_id="evi-1",
        source_id="rainbow:ta",
        regime="bullish",
        fingerprint=_sha("e"),
    )


def _valid_validation_ref(
    vtype: ValidationType = ValidationType.BACKTEST,
) -> ValidationReference:
    return ValidationReference(
        validation_id="val-1",
        validation_type=vtype,
        fingerprint=_sha("f"),
        passed=True,
    )


def _valid_request(
    review_state: ReviewState = ReviewState.PENDING_REVIEW,
    decisions: tuple[str, ...] = ("ACCEPT",),
) -> EpisodeReportRequest:
    refs = tuple(_valid_proposal_ref(decision=d) for d in decisions)
    return EpisodeReportRequest(
        episode_id="test-episode-001",
        proposal_timestamp_utc="2026-06-12T09:40:00Z",
        review_state=review_state,
        evidence_references=(_valid_evidence_ref(),),
        proposal_references=refs,
        validation_references=(_valid_validation_ref(),),
    )


# ---------------------------------------------------------------------------
# E185-01: SHA-256 hash validation
# ---------------------------------------------------------------------------


class TestSha256Validation:
    def test_valid_sha256_accepts(self) -> None:
        assert _validate_sha256_hex(_sha("a")) == _sha("a")

    def test_uppercase_rejected(self) -> None:
        with pytest.raises(ValueError, match="lowercase hex"):
            _validate_sha256_hex("A" * 64)

    def test_non_hex_rejected(self) -> None:
        with pytest.raises(ValueError, match="lowercase hex"):
            _validate_sha256_hex("z" + "a" * 63)

    def test_truncated_rejected(self) -> None:
        with pytest.raises(ValueError, match="lowercase hex"):
            _validate_sha256_hex("a" * 63)

    def test_extended_rejected(self) -> None:
        with pytest.raises(ValueError, match="lowercase hex"):
            _validate_sha256_hex("a" * 65)

    def test_whitespace_rejected(self) -> None:
        with pytest.raises(ValueError, match="lowercase hex"):
            _validate_sha256_hex(" " + "a" * 63)

    def test_empty_rejected(self) -> None:
        with pytest.raises(ValueError, match="lowercase hex"):
            _validate_sha256_hex("")

    def test_evidence_ref_fingerprint_validated(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceReference(
                evidence_id="e1",
                source_id="s",
                regime="r",
                fingerprint="UPPERCASE" + "a" * 54,
            )

    def test_proposal_ref_ids_validated(self) -> None:
        with pytest.raises(ValidationError):
            ProposalReference(
                proposal_id="short",  # not 64 hex
                batch_id=_sha("b"),
                source_id="s",
                regime="r",
                proposal_fingerprint=_sha("c"),
                batch_fingerprint=_sha("d"),
                decision="ACCEPT",
                proposed_weight=Decimal("0.5"),
                proposed_delta=Decimal("0.1"),
            )

    def test_validation_ref_fingerprint_validated(self) -> None:
        with pytest.raises(ValidationError):
            ValidationReference(
                validation_id="v1",
                validation_type=ValidationType.BACKTEST,
                fingerprint="xxx",
            )

    def test_artifact_ref_hash_validated(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactReference(
                artifact_id="a1",
                artifact_type="json",
                content_hash="not-a-sha",
            )

    def test_type_honors_sha256hex_contract(self) -> None:
        """Ensure Sha256Hex can be used in type annotations."""
        assert Sha256Hex is not None


# ---------------------------------------------------------------------------
# E185-02: UTC timestamp validation
# ---------------------------------------------------------------------------


class TestUtcTimestampValidation:
    def test_z_suffix_accepts(self) -> None:
        assert _validate_utc_timestamp("2026-06-12T09:40:00Z") == "2026-06-12T09:40:00+00:00"

    def test_positive_zero_offset_accepts(self) -> None:
        assert _validate_utc_timestamp("2026-06-12T09:40:00+00:00") == "2026-06-12T09:40:00+00:00"

    def test_negative_zero_offset_accepts(self) -> None:
        assert _validate_utc_timestamp("2026-06-12T09:40:00-00:00") == "2026-06-12T09:40:00-00:00"

    def test_with_fractional_seconds(self) -> None:
        assert _validate_utc_timestamp("2026-06-12T09:40:00.123Z") == "2026-06-12T09:40:00.123+00:00"

    def test_naive_rejected(self) -> None:
        with pytest.raises(ValueError, match="ISO 8601"):
            _validate_utc_timestamp("2026-06-12T09:40:00")

    def test_non_utc_offset_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-UTC"):
            _validate_utc_timestamp("2026-06-12T09:40:00+02:00")

    def test_malformed_date_rejected(self) -> None:
        with pytest.raises(ValueError, match="ISO 8601"):
            _validate_utc_timestamp("not-a-timestamp")

    def test_invalid_hour_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalid time"):
            _validate_utc_timestamp("2026-06-12T25:00:00Z")

    def test_invalid_minute_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalid time"):
            _validate_utc_timestamp("2026-06-12T09:60:00Z")

    def test_proposal_timestamp_type(self) -> None:
        """UtcTimestamp is usable in type annotations."""
        assert UtcTimestamp is not None

    def test_request_rejects_naive(self) -> None:
        with pytest.raises(ValidationError):
            EpisodeReportRequest(
                episode_id="naive-ts",
                proposal_timestamp_utc="2026-06-12T09:40:00",
                proposal_references=(_valid_proposal_ref(),),
            )


# ---------------------------------------------------------------------------
# E185-03: Canonical verdict truth table
# ---------------------------------------------------------------------------


class TestVerdictTruthTable:
    def test_green_with_accepted_validated(self) -> None:
        """GREEN: ACCEPT + ACCEPTED_BY_HUMAN + mandatory validation."""
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.GREEN

    def test_red_when_rejected_proposal(self) -> None:
        """RED: proposal REJECT."""
        req = _valid_request(decisions=("REJECT",))
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.RED

    def test_red_when_human_rejects(self) -> None:
        """RED: human rejection."""
        req = _valid_request(review_state=ReviewState.REJECTED_BY_HUMAN)
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.RED

    def test_yellow_when_pending_review(self) -> None:
        """YELLOW: PENDING_REVIEW."""
        req = _valid_request(review_state=ReviewState.PENDING_REVIEW)
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.YELLOW

    def test_yellow_when_deferred_by_human(self) -> None:
        """YELLOW: DEFERRED_BY_HUMAN (no hard failure)."""
        req = _valid_request(review_state=ReviewState.DEFERRED_BY_HUMAN)
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.YELLOW

    def test_red_when_accepted_but_missing_validation(self) -> None:
        """RED: ACCEPT + ACCEPTED_BY_HUMAN but no mandatory validation (E185-04)."""
        req = EpisodeReportRequest(
            episode_id="no-val-01",
            proposal_timestamp_utc="2026-06-12T09:40:00Z",
            review_state=ReviewState.ACCEPTED_BY_HUMAN,
            evidence_references=(_valid_evidence_ref(),),
            proposal_references=(_valid_proposal_ref(),),
            validation_references=(),  # no validation at all
        )
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.RED

    def test_red_when_validation_failed(self) -> None:
        """RED: validation exists but passed=False."""
        req = EpisodeReportRequest(
            episode_id="val-failed",
            proposal_timestamp_utc="2026-06-12T09:40:00Z",
            review_state=ReviewState.ACCEPTED_BY_HUMAN,
            evidence_references=(_valid_evidence_ref(),),
            proposal_references=(_valid_proposal_ref(),),
            validation_references=(
                ValidationReference(
                    validation_id="val-1",
                    validation_type=ValidationType.BACKTEST,
                    fingerprint=_sha("f"),
                    passed=False,
                ),
            ),
        )
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.RED

    def test_yellow_accepted_human_but_all_deferred(self) -> None:
        """YELLOW: ACCEPTED_BY_HUMAN but all proposals DEFER."""
        req = _valid_request(
            review_state=ReviewState.ACCEPTED_BY_HUMAN,
            decisions=("DEFER",),
        )
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.YELLOW

    def test_green_requires_accepted_human_and_accept(self) -> None:
        """GREEN cannot be from ACCEPT proposal alone without ACCEPTED_BY_HUMAN."""
        req = _valid_request(review_state=ReviewState.PENDING_REVIEW)
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.YELLOW  # not GREEN

    def test_accept_plus_human_accept_but_missing_validation_is_red(self) -> None:
        """ACCEPT + ACCEPTED_BY_HUMAN without mandatory validation → RED."""
        req = EpisodeReportRequest(
            episode_id="missing-mandatory",
            proposal_timestamp_utc="2026-06-12T09:40:00Z",
            review_state=ReviewState.ACCEPTED_BY_HUMAN,
            proposal_references=(_valid_proposal_ref(),),
            validation_references=(),  # no validation
        )
        verdict, _ = compute_verdict(req)
        assert verdict == EpisodeVerdict.RED


# ---------------------------------------------------------------------------
# E185-05: Duplicate ID rejection
# ---------------------------------------------------------------------------


class TestDuplicateRejection:
    def test_duplicate_evidence_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate evidence_id"):
            EpisodeReportRequest(
                episode_id="dup-ev-01",
                proposal_timestamp_utc="2026-06-12T09:40:00Z",
                proposal_references=(_valid_proposal_ref(),),
                evidence_references=(
                    EvidenceReference(
                        evidence_id="same",
                        source_id="s1",
                        regime="r1",
                        fingerprint=_sha("a"),
                    ),
                    EvidenceReference(
                        evidence_id="same",  # duplicate
                        source_id="s2",
                        regime="r2",
                        fingerprint=_sha("b"),
                    ),
                ),
            )

    def test_duplicate_proposal_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate proposal_id"):
            EpisodeReportRequest(
                episode_id="dup-pr-01",
                proposal_timestamp_utc="2026-06-12T09:40:00Z",
                proposal_references=(
                    _valid_proposal_ref(decision="ACCEPT"),
                    _valid_proposal_ref(decision="DEFER"),
                ),
            )

    def test_duplicate_validation_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate validation_id"):
            EpisodeReportRequest(
                episode_id="dup-va-01",
                proposal_timestamp_utc="2026-06-12T09:40:00Z",
                proposal_references=(_valid_proposal_ref(),),
                validation_references=(
                    ValidationReference(
                        validation_id="same",
                        validation_type=ValidationType.BACKTEST,
                        fingerprint=_sha("a"),
                    ),
                    ValidationReference(
                        validation_id="same",
                        validation_type=ValidationType.WALK_FORWARD,
                        fingerprint=_sha("b"),
                    ),
                ),
            )

    def test_duplicate_artifact_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate artifact_id"):
            EpisodeReportRequest(
                episode_id="dup-ar-01",
                proposal_timestamp_utc="2026-06-12T09:40:00Z",
                proposal_references=(_valid_proposal_ref(),),
                artifact_references=(
                    ArtifactReference(
                        artifact_id="same",
                        artifact_type="json",
                        content_hash=_sha("a"),
                    ),
                    ArtifactReference(
                        artifact_id="same",
                        artifact_type="md",
                        content_hash=_sha("b"),
                    ),
                ),
            )

    def test_conflicting_semantic_identity_rejected(self) -> None:
        """Duplicate (source_id, regime) with different fingerprints."""
        with pytest.raises(ValidationError, match=r"duplicate.*source_id"):
            EpisodeReportRequest(
                episode_id="conflict-semi-01",
                proposal_timestamp_utc="2026-06-12T09:40:00Z",
                proposal_references=(
                    ProposalReference(
                        proposal_id=_sha("a"),
                        batch_id=_sha("b"),
                        source_id="source:abc",
                        regime="bullish",
                        proposal_fingerprint=_sha("c"),
                        batch_fingerprint=_sha("d"),
                        decision="ACCEPT",
                        proposed_weight=Decimal("0.50"),
                        proposed_delta=Decimal("0.10"),
                    ),
                    ProposalReference(
                        proposal_id=_sha("e"),  # different from first
                        batch_id=_sha("b"),
                        source_id="source:abc",
                        regime="bullish",
                        proposal_fingerprint=_sha("f"),
                        batch_fingerprint=_sha("d"),
                        decision="ACCEPT",
                        proposed_weight=Decimal("0.50"),
                        proposed_delta=Decimal("0.10"),
                    ),
                ),
            )


# ---------------------------------------------------------------------------
# E185-06: Fingerprint includes versions
# ---------------------------------------------------------------------------


class TestFingerprintVersions:
    def test_deterministic_fingerprint(self) -> None:
        req = _valid_request()
        fp1 = compute_episode_fingerprint(req)
        fp2 = compute_episode_fingerprint(req)
        assert fp1 == fp2
        assert len(fp1) == 64

    def test_fingerprint_changes_with_policy_version(self) -> None:
        """Changing policy version changes fingerprint."""
        req1 = _valid_request()
        req2 = _valid_request()
        # Create a modified request with different policy_version
        # Since the model is frozen, we need to create a new one
        req2_dict = req2.model_dump()
        req2_dict["policy_version"] = "scoring_policy_v2"
        # Can't use frozen model constructor with different field, so we use
        # model_validate
        req2_mod = EpisodeReportRequest.model_validate(req2_dict)
        fp1 = compute_episode_fingerprint(req1)
        fp2 = compute_episode_fingerprint(req2_mod)
        assert fp1 != fp2

    def test_fingerprint_changes_with_schema_version(self) -> None:
        req1 = _valid_request()
        req2_dict = _valid_request().model_dump()
        req2_dict["episode_schema_version"] = "episode_report_v2"
        req2_mod = EpisodeReportRequest.model_validate(req2_dict)
        fp1 = compute_episode_fingerprint(req1)
        fp2 = compute_episode_fingerprint(req2_mod)
        assert fp1 != fp2

    def test_fingerprint_changes_with_proposal_schema(self) -> None:
        req1 = _valid_request()
        req2_dict = _valid_request().model_dump()
        req2_dict["proposal_schema_version"] = "weight_proposal_v2"
        req2_mod = EpisodeReportRequest.model_validate(req2_dict)
        fp1 = compute_episode_fingerprint(req1)
        fp2 = compute_episode_fingerprint(req2_mod)
        assert fp1 != fp2

    def test_fingerprint_excludes_episode_id(self) -> None:
        """episode_id is an external idempotency key, not part of fingerprint."""
        req1 = EpisodeReportRequest(
            episode_id="episode-A",
            proposal_timestamp_utc="2026-06-12T09:40:00Z",
            proposal_references=(_valid_proposal_ref(),),
            validation_references=(_valid_validation_ref(),),
        )
        req2 = EpisodeReportRequest(
            episode_id="episode-B",  # different ID
            proposal_timestamp_utc="2026-06-12T09:40:00Z",
            proposal_references=(_valid_proposal_ref(),),
            validation_references=(_valid_validation_ref(),),
        )
        fp1 = compute_episode_fingerprint(req1)
        fp2 = compute_episode_fingerprint(req2)
        # Same semantic content → same fingerprint despite different episode_id
        assert fp1 == fp2

    def test_fingerprint_includes_provenance(self) -> None:
        """Fingerprint includes all provenance versions."""
        req = _valid_request()
        # Verify the raw dump that feeds the fingerprint contains version fields
        raw = json.dumps(
            req.model_dump(exclude={"episode_id"}),
            sort_keys=True,
            default=str,
        )
        assert EPISODE_SCHEMA_VERSION in raw
        assert POLICY_VERSION in raw
        assert PROPOSAL_SCHEMA_VERSION in raw
        assert EVIDENCE_SCHEMA_VERSION in raw


# ---------------------------------------------------------------------------
# E185-07: Cross-consistency
# ---------------------------------------------------------------------------


class TestCrossConsistency:
    def test_json_and_manifest_agree_on_verdict(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        report = build_episode_report(req)
        parsed = json.loads(report.episode_json)
        assert parsed["verdict"] == report.verdict.value
        assert parsed["episode_id"] == report.episode_id
        assert parsed["integrity_manifest"]["episode_fingerprint"] == (
            report.integrity_manifest.episode_fingerprint
        )

    def test_markdown_and_json_agree_on_verdict(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        report = build_episode_report(req)
        assert "GREEN" in report.episode_markdown
        parsed = json.loads(report.episode_json)
        assert parsed["verdict"] == "GREEN"

    def test_manifest_hashes_correct(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        report = build_episode_report(req)
        m = report.integrity_manifest
        assert m.artifact_hashes["episode.json"] == hashlib.sha256(
            report.episode_json.encode("utf-8")
        ).hexdigest()
        assert m.artifact_hashes["episode.md"] == hashlib.sha256(
            report.episode_markdown.encode("utf-8")
        ).hexdigest()

    def test_canonical_reruns_byte_identical(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        r1 = build_episode_report(req)
        r2 = build_episode_report(req)
        assert r1.model_dump_json() == r2.model_dump_json()
        assert r1.episode_json == r2.episode_json
        assert r1.episode_markdown == r2.episode_markdown


# ---------------------------------------------------------------------------
# E185-08: No-execution safety invariants
# ---------------------------------------------------------------------------


class TestNoExecutionSafety:
    def test_no_application_statement_present(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        report = build_episode_report(req)
        assert "advisory only" in report.episode_markdown.lower()
        assert "review acceptance only" in report.episode_markdown
        assert "never authorizes" in report.episode_markdown

    def test_accepted_verdict_does_not_authorize(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        report = build_episode_report(req)
        assert report.verdict == EpisodeVerdict.GREEN
        # GREEN is advisory, not executable
        assert "separate approval-gated mechanism" in report.episode_markdown


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

    def test_bad_decision_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _valid_proposal_ref(decision="INVALID")

    def test_bad_artifact_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactReference(
                artifact_id="a1",
                artifact_type="html",
                content_hash=_sha("a"),
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
            review_state=ReviewState.DEFERRED_BY_HUMAN,
            decisions=("DEFER",),
        )
        report = build_episode_report(req)
        assert report.verdict == EpisodeVerdict.YELLOW

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

    def test_green_with_mandatory_validation(self) -> None:
        """GREEN requires at least one passed backtest or walk-forward."""
        req = EpisodeReportRequest(
            episode_id="green-with-val",
            proposal_timestamp_utc="2026-06-12T09:40:00Z",
            review_state=ReviewState.ACCEPTED_BY_HUMAN,
            proposal_references=(_valid_proposal_ref(),),
            validation_references=(
                ValidationReference(
                    validation_id="bt-1",
                    validation_type=ValidationType.BACKTEST,
                    fingerprint=_sha("f"),
                    passed=True,
                ),
                ValidationReference(
                    validation_id="wf-1",
                    validation_type=ValidationType.WALK_FORWARD,
                    fingerprint=_sha("g"),
                    passed=True,
                ),
            ),
        )
        report = build_episode_report(req)
        assert report.verdict == EpisodeVerdict.GREEN


# ---------------------------------------------------------------------------
# Non-regression: verdict is not execution approval
# ---------------------------------------------------------------------------


class TestNotExecutionApproval:
    def test_accepted_verdict_does_not_authorize(self) -> None:
        req = _valid_request(review_state=ReviewState.ACCEPTED_BY_HUMAN)
        report = build_episode_report(req)
        md = report.episode_markdown
        assert "review acceptance only" in md
        assert "never authorizes" in md
        assert "separate approval-gated mechanism" in md


# ---------------------------------------------------------------------------
# No-runtime import check
# ---------------------------------------------------------------------------


class TestNoRuntimeImports:
    def test_no_runtime_imports(self) -> None:
        """Verify no Docker, Freqtrade, or runtime imports exist in module."""
        import si_v2.reports.episode_report as mod
        src = mod.__file__ or ""
        with open(src) as f:
            content = f.read()
        for forbidden in ("docker", "freqtrade", "exchange", "sqlite3", "subprocess"):
            if forbidden in content:
                # Only reject if it's an import statement
                for line in content.splitlines():
                    if f"import {forbidden}" in line or f"from {forbidden}" in line:
                        pytest.fail(f"Forbidden import in episode_report: {line}")
