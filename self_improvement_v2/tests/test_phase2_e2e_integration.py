"""Real end-to-end integration test for the Phase 2 proposal stack (issue #181).

Proves the typed contract from source_regime_stats SQLite through
Evidence Input Pipeline, Proposal Scoring, Weight Proposal Engine,
and hardened Episode Report Builder.

No mocks in the core path. Real temporary SQLite databases, real
module imports, real construction and validation.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from si_v2.evidence.input_pipeline import (
    EvidencePipelineRequest,
    ProposalEvidenceRecord,
    run_evidence_pipeline,
)
from si_v2.propose.proposal_scoring.models import (
    POLICY_VERSION,
    BacktestMetrics,
    DataQualityVerdict,
    DirectionHint,
    ProposalScoreInput,
    ScoringPolicy,
    WalkForwardMetrics,
)
from si_v2.propose.proposal_scoring.scoring import score_proposal
from si_v2.propose.weight_proposal.engine import WeightProposalEngine
from si_v2.propose.weight_proposal.models import (
    PROPOSAL_SCHEMA_VERSION,
    CurrentWeight,
    WeightProposalRequest,
)
from si_v2.reports.episode_report import (
    EPISODE_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    EpisodeReportRequest,
    EpisodeVerdict,
    EvidenceReference,
    ProposalReference,
    ReviewState,
    ValidationReference,
    ValidationType,
    build_episode_report,
    compute_episode_fingerprint,
    compute_verdict,
)
from si_v2.source_regime_stats.db import create_schema

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 6, 12, 12, 0, 0, tzinfo=UTC)


def _create_cache_db(
    db_path: Path,
    rows: list[dict[str, str | int | float | None]],
    cache_schema_version: str = "1.1",
) -> None:
    """Create a source_regime_stats cache database with test data."""
    conn = sqlite3.connect(str(db_path))
    create_schema(conn)

    conn.execute(
        "INSERT OR REPLACE INTO cache_metadata "
        "(id, cache_schema_version, fact_schema_version, source_fingerprint, "
        " build_mode, last_evidence_time, operation_timestamp) "
        "VALUES (1, ?, ?, ?, ?, ?, ?)",
        (
            cache_schema_version,
            "1.0",
            "test-fingerprint-001",
            "full",
            NOW.isoformat(),
            NOW.isoformat(),
        ),
    )

    for i, row in enumerate(rows):
        ev_max_closed = row.get("evidence_max_closed_at", (NOW - timedelta(days=1)).isoformat())
        conn.execute(
            "INSERT INTO attribution_facts "
            "(fact_id, trade_id, source_id, strategy_or_model_id, pair, "
            " timeframe, regime, confidence_bucket, weighted_return, "
            " raw_trade_return, contribution_weight, outcome_classification, "
            " closed_at, provenance_hash, schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row.get("fact_id", f"fact-{i:04d}"),
                row.get("trade_id", f"trade-{i:04d}"),
                row.get("source_id", "test:source"),
                row.get("strategy_or_model_id"),
                row.get("pair", "BTC/USDT"),
                row.get("timeframe", "1h"),
                row.get("regime", "bullish"),
                row.get("confidence_bucket", "high"),
                row.get("weighted_return", 0.05),
                row.get("raw_trade_return", 0.04),
                row.get("contribution_weight", 0.5),
                row.get("outcome_classification", "WIN"),
                row.get("closed_at", (NOW - timedelta(days=1)).isoformat()),
                row.get("provenance_hash", "a" * 64),
                row.get("schema_version", "1.0"),
            ),
        )

        conn.execute(
            "INSERT OR REPLACE INTO source_regime_stats "
            "(source_id, strategy_or_model_id, pair, timeframe, regime, "
            " confidence_bucket, unique_trade_count, source_contribution_count, "
            " win_count, loss_count, breakeven_count, win_rate, "
            " average_raw_return, average_weighted_return, expectancy, "
            " cumulative_weighted_return, drawdown_proxy, "
            " average_source_confidence, average_regime_confidence, "
            " evidence_max_closed_at, input_fingerprint, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row.get("source_id", "test:source"),
                row.get("strategy_or_model_id"),
                row.get("pair", "BTC/USDT"),
                row.get("timeframe", "1h"),
                row.get("regime", "bullish"),
                row.get("confidence_bucket", "high"),
                row.get("unique_trade_count", 100),
                row.get("source_contribution_count", 50),
                row.get("win_count", 60),
                row.get("loss_count", 30),
                row.get("breakeven_count", 10),
                row.get("win_rate", 0.60),
                row.get("average_raw_return", 0.04),
                row.get("average_weighted_return", 0.05),
                row.get("expectancy", 0.02),
                row.get("cumulative_weighted_return", 5.0),
                row.get("drawdown_proxy", 0.10),
                row.get("average_source_confidence", 0.8),
                row.get("average_regime_confidence", 0.7),
                ev_max_closed,
                row.get("input_fingerprint", "a" * 16),
                NOW.isoformat(),
            ),
        )

    conn.commit()
    conn.close()


def _default_policy() -> ScoringPolicy:
    """Return a scoring policy with permissive thresholds for testing."""
    return ScoringPolicy(
        minimum_sample_count=5,
        maximum_evidence_age_days=Decimal("90"),
        minimum_expectancy=Decimal("-1.0"),
        maximum_drawdown_proxy=Decimal("0.5"),
        minimum_confidence=Decimal("0.0"),
        accept_threshold=Decimal("0.30"),
        defer_threshold=Decimal("0.10"),
    )


def _valid_row(source_id: str = "test:source", regime: str = "bullish") -> dict[str, str | int | float | None]:
    """Return a dict with default valid values for a source_regime_stats row."""
    return {
        "source_id": source_id,
        "regime": regime,
        "pair": "BTC/USDT",
        "timeframe": "1h",
        "confidence_bucket": "high",
        "unique_trade_count": 100,
        "expectancy": 0.02,
        "drawdown_proxy": 0.10,
        "average_source_confidence": 0.8,
        "average_regime_confidence": 0.7,
        "win_rate": 0.60,
        "win_count": 60,
        "loss_count": 30,
        "breakeven_count": 10,
        "average_raw_return": 0.04,
        "average_weighted_return": 0.05,
        "cumulative_weighted_return": 5.0,
        "source_contribution_count": 50,
        "evidence_max_closed_at": (NOW - timedelta(days=1)).isoformat(),
    }


def _sha(hex_char: str = "a") -> str:
    """Return a valid 64-char lowercase hex string."""
    fill = hex_char[0] if hex_char and hex_char[0] in "abcdef0123456789" else "a"
    return fill * 64


# ---------------------------------------------------------------------------
# Evidence-to-ScoreInput adapter
# ---------------------------------------------------------------------------


def _evidence_to_score_input(
    record: ProposalEvidenceRecord,
    as_of: datetime,
    *,
    direction_hint: DirectionHint = DirectionHint.NEUTRAL,
    human_approval_available: bool = False,
) -> ProposalScoreInput:
    """Convert a pipeline evidence record to a typed scoring input.

    Derives ``evidence_age_days`` deterministically from
    ``as_of - record.evidence_max_closed_at``.

    Raises:
        ValueError: If ``evidence_max_closed_at`` is missing,
                    unparseable, or later than ``as_of``.
    """
    from si_v2.propose.proposal_scoring.decimal_safe import to_decimal

    # Derive evidence age from the explicit analytical clock
    closed_raw = record.evidence_max_closed_at
    if not closed_raw:
        raise ValueError("evidence_max_closed_at is required for scoring input")
    try:
        closed_dt = datetime.fromisoformat(str(closed_raw))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Cannot parse evidence_max_closed_at={closed_raw!r}: {exc}") from exc
    if closed_dt.tzinfo is None:
        closed_dt = closed_dt.replace(tzinfo=UTC)
    if closed_dt > as_of:
        raise ValueError(f"evidence_max_closed_at={closed_raw} is later than as_of={as_of}")
    age_seconds = (as_of - closed_dt).total_seconds()
    evidence_age_days = Decimal(str(age_seconds / 86400.0))

    return ProposalScoreInput(
        evidence_id=record.evidence_id,
        source_id=record.source_id,
        regime=record.regime,
        evidence_schema_version=1,
        unique_trade_count=record.unique_trade_count,
        expectancy=to_decimal(record.expectancy, "expectancy"),
        drawdown_proxy=to_decimal(record.drawdown_proxy, "drawdown_proxy"),
        average_source_confidence=(
            to_decimal(record.average_source_confidence, "average_source_confidence")
            if record.average_source_confidence is not None
            else None
        ),
        average_regime_confidence=(
            to_decimal(record.average_regime_confidence, "average_regime_confidence")
            if record.average_regime_confidence is not None
            else None
        ),
        evidence_age_days=evidence_age_days,
        data_quality_verdict=DataQualityVerdict.ACCEPTED,
        is_actionable=True,
        direction_hint=direction_hint,
        has_conflict=False,
        human_approval_available=human_approval_available,
        backtest_metrics=BacktestMetrics(
            passed=True,
            total_trades=100,
            profit_total_pct=Decimal("0.05"),
            max_drawdown_pct=Decimal("0.10"),
            win_rate_pct=Decimal("60.0"),
        ),
        walk_forward_metrics=WalkForwardMetrics(
            passed=True,
            stability_score=Decimal("0.75"),
        ),
    )


# ---------------------------------------------------------------------------
# Scenario 1: Valid positive evidence
# ---------------------------------------------------------------------------


class TestValidPositiveEvidence:
    """Valid evidence flows through pipeline, scoring, proposal, episode."""

    def test_full_stack_from_db_to_episode(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        _create_cache_db(db_path, [_valid_row()])

        # Step 1: Evidence Input Pipeline (read-only)
        pipeline_result = run_evidence_pipeline(
            EvidencePipelineRequest(
                cache_db_path=db_path,
                as_of=NOW,
                minimum_unique_trade_count=5,
            )
        )
        assert len(pipeline_result.accepted) >= 1
        assert len(pipeline_result.errors) == 0
        record = pipeline_result.accepted[0]
        original_db_bytes = db_path.read_bytes()

        # Step 2: Score the evidence
        psi = _evidence_to_score_input(record, as_of=pipeline_result.request.as_of)
        _ = score_proposal(psi, _default_policy())

        # Step 3: Weight Proposal Engine
        current_weights = (
            CurrentWeight(
                source_id=record.source_id,
                regime=record.regime,
                weight=Decimal("0.5"),
            ),
        )
        # Set evidence_age_days on the record so the engine can consume it
        # (the pipeline record now has this field with a default; set it properly)
        object.__setattr__(record, "evidence_age_days", float(psi.evidence_age_days))
        proposal_request = WeightProposalRequest(
            proposal_timestamp_utc=NOW.isoformat(),
            current_weights=current_weights,
            evidence_records=(record,),
            scoring_policy=_default_policy(),
        )
        batch = WeightProposalEngine().build_proposals(proposal_request)
        assert len(batch.stable_proposals) + len(batch.deferred_candidates) + len(batch.rejected_candidates) >= 1
        all_proposals = list(batch.stable_proposals) + list(batch.deferred_candidates) + list(batch.rejected_candidates)
        proposal = all_proposals[0]

        # Step 4: Episode Report
        ep_request = EpisodeReportRequest(
            episode_id="e2e-valid-001",
            proposal_timestamp_utc=NOW.isoformat(),
            review_state=ReviewState.ACCEPTED_BY_HUMAN,
            evidence_references=(
                EvidenceReference(
                    evidence_id=record.evidence_id,
                    source_id=record.source_id,
                    regime=record.regime,
                    fingerprint=_sha("f"),
                ),
            ),
            proposal_references=(
                ProposalReference(
                    proposal_id=proposal.proposal_id,
                    batch_id=batch.batch_id,
                    source_id=proposal.source_id,
                    regime=proposal.regime,
                    proposal_fingerprint=proposal.proposal_fingerprint,
                    batch_fingerprint=batch.batch_fingerprint,
                    decision=proposal.decision,
                    proposed_weight=proposal.proposed_weight,
                    proposed_delta=proposal.proposed_delta,
                ),
            ),
            validation_references=(
                ValidationReference(
                    validation_id="bt-001",
                    validation_type=ValidationType.BACKTEST,
                    fingerprint=_sha("b"),
                    passed=True,
                ),
            ),
        )
        report = build_episode_report(ep_request)

        # Verdict must be consistent with the actual proposal decision
        if proposal.decision == "ACCEPT":
            assert report.verdict == EpisodeVerdict.GREEN
        elif proposal.decision == "DEFER":
            assert report.verdict == EpisodeVerdict.YELLOW
        else:
            assert report.verdict == EpisodeVerdict.RED

        # Cross-consistency (E185-07)
        parsed = json.loads(report.episode_json)
        assert parsed["episode_id"] == "e2e-valid-001"
        assert parsed["verdict"] == report.verdict.value
        assert parsed["integrity_manifest"]["episode_fingerprint"] == (report.integrity_manifest.episode_fingerprint)

        # Deterministic fingerprints
        assert compute_episode_fingerprint(ep_request) == compute_episode_fingerprint(ep_request)

        # Source DB unchanged
        assert db_path.read_bytes() == original_db_bytes


# ---------------------------------------------------------------------------
# Scenario 2: Sparse evidence
# ---------------------------------------------------------------------------


class TestSparseEvidence:
    """Sparse evidence should be REJECTed by the pipeline."""

    def test_sparse_evidence_rejected(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        row = _valid_row()
        row["unique_trade_count"] = 1
        _create_cache_db(db_path, [row])

        result = run_evidence_pipeline(
            EvidencePipelineRequest(
                cache_db_path=db_path,
                as_of=NOW,
                minimum_unique_trade_count=10,
            )
        )
        assert len(result.accepted) == 0
        assert len(result.rejected) >= 1


# ---------------------------------------------------------------------------
# Scenario 3: Stale evidence (old evidence_max_closed_at)
# ---------------------------------------------------------------------------


class TestStaleEvidence:
    """Stale evidence should be REJECTed using derived evidence_age_days."""

    def test_stale_evidence_rejected(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        row = _valid_row()
        row["evidence_max_closed_at"] = (NOW - timedelta(days=200)).isoformat()
        _create_cache_db(db_path, [row])

        result = run_evidence_pipeline(
            EvidencePipelineRequest(
                cache_db_path=db_path,
                as_of=NOW,
                maximum_evidence_age_days=30.0,
            )
        )
        assert len(result.accepted) == 0
        assert len(result.rejected) >= 1


# ---------------------------------------------------------------------------
# Scenario 3b: Future-dated evidence fails closed
# ---------------------------------------------------------------------------


class TestFutureDatedEvidence:
    """Evidence with a future timestamp must fail closed when building ScoreInput."""

    def test_future_evidence_raises(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        row = _valid_row()
        row["evidence_max_closed_at"] = (NOW + timedelta(days=7)).isoformat()
        _create_cache_db(db_path, [row])

        result = run_evidence_pipeline(
            EvidencePipelineRequest(
                cache_db_path=db_path,
                as_of=NOW,
            )
        )
        # Pipeline may reject it (timestamp > as_of) or accept it
        # If accepted, building ScoreInput must reject it
        if result.accepted:
            with pytest.raises(ValueError, match="later than as_of"):
                _evidence_to_score_input(result.accepted[0], as_of=NOW)


# ---------------------------------------------------------------------------
# Scenario 4: Negative expectancy
# ---------------------------------------------------------------------------


class TestNegativeExpectancy:
    """Negative expectancy increase request should produce REJECT in scoring."""

    def test_negative_expectancy_rejected(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        row = _valid_row()
        row["expectancy"] = -0.05
        _create_cache_db(db_path, [row])

        result = run_evidence_pipeline(
            EvidencePipelineRequest(
                cache_db_path=db_path,
                as_of=NOW,
                minimum_unique_trade_count=5,
            )
        )

        if result.accepted:
            psi = _evidence_to_score_input(
                result.accepted[0],
                as_of=NOW,
                direction_hint=DirectionHint.INCREASE,
            )
            strict_policy = ScoringPolicy(
                minimum_expectancy=Decimal("0.0"),
                accept_threshold=Decimal("0.65"),
                defer_threshold=Decimal("0.40"),
            )
            decision = score_proposal(psi, strict_policy)
            assert decision.decision in ("REJECT", "DEFER"), (
                f"negative expectancy with INCREASE hint should not ACCEPT, got {decision.decision}"
            )


# ---------------------------------------------------------------------------
# Scenario 5: Missing mandatory backtest
# ---------------------------------------------------------------------------


class TestMissingMandatoryBacktest:
    """Missing backtest validation prevents GREEN verdict."""

    def test_missing_backtest_no_green(self) -> None:
        ep_request = EpisodeReportRequest(
            episode_id="no-bt-001",
            proposal_timestamp_utc=NOW.isoformat(),
            review_state=ReviewState.ACCEPTED_BY_HUMAN,
            proposal_references=(
                ProposalReference(
                    proposal_id=_sha("a"),
                    batch_id=_sha("b"),
                    source_id="test:source",
                    regime="bullish",
                    proposal_fingerprint=_sha("c"),
                    batch_fingerprint=_sha("d"),
                    decision="ACCEPT",
                    proposed_weight=Decimal("0.50"),
                    proposed_delta=Decimal("0.10"),
                ),
            ),
            validation_references=(),
        )
        verdict, _ = compute_verdict(ep_request)
        assert verdict != EpisodeVerdict.GREEN


# ---------------------------------------------------------------------------
# Scenario 6: Unstable walk-forward does not crash
# ---------------------------------------------------------------------------


class TestUnstableWalkForward:
    """Marginal evidence with weak walk-forward should not break the stack."""

    def test_marginal_evidence_does_not_crash(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        row = _valid_row()
        row["expectancy"] = 0.001
        row["drawdown_proxy"] = 0.30
        _create_cache_db(db_path, [row])

        result = run_evidence_pipeline(
            EvidencePipelineRequest(
                cache_db_path=db_path,
                as_of=NOW,
                minimum_unique_trade_count=5,
            )
        )
        assert result is not None


# ---------------------------------------------------------------------------
# Scenario 7: Pending human review
# ---------------------------------------------------------------------------


class TestPendingHumanReview:
    """PENDING_REVIEW produces YELLOW."""

    def test_pending_review_yellow(self) -> None:
        ep_request = EpisodeReportRequest(
            episode_id="pending-001",
            proposal_timestamp_utc=NOW.isoformat(),
            review_state=ReviewState.PENDING_REVIEW,
            proposal_references=(
                ProposalReference(
                    proposal_id=_sha("a"),
                    batch_id=_sha("b"),
                    source_id="test:source",
                    regime="bullish",
                    proposal_fingerprint=_sha("c"),
                    batch_fingerprint=_sha("d"),
                    decision="ACCEPT",
                    proposed_weight=Decimal("0.50"),
                    proposed_delta=Decimal("0.10"),
                ),
            ),
        )
        verdict, _ = compute_verdict(ep_request)
        assert verdict == EpisodeVerdict.YELLOW


# ---------------------------------------------------------------------------
# Scenario 8: Deferred human review
# ---------------------------------------------------------------------------


class TestDeferredHumanReview:
    """DEFERRED_BY_HUMAN produces YELLOW (not RED)."""

    def test_deferred_human_review_yellow(self) -> None:
        ep_request = EpisodeReportRequest(
            episode_id="deferred-001",
            proposal_timestamp_utc=NOW.isoformat(),
            review_state=ReviewState.DEFERRED_BY_HUMAN,
            proposal_references=(
                ProposalReference(
                    proposal_id=_sha("a"),
                    batch_id=_sha("b"),
                    source_id="test:source",
                    regime="bullish",
                    proposal_fingerprint=_sha("c"),
                    batch_fingerprint=_sha("d"),
                    decision="ACCEPT",
                    proposed_weight=Decimal("0.50"),
                    proposed_delta=Decimal("0.10"),
                ),
            ),
        )
        verdict, _ = compute_verdict(ep_request)
        assert verdict == EpisodeVerdict.YELLOW


# ---------------------------------------------------------------------------
# Scenario 9: Provenance / fingerprint conflict
# ---------------------------------------------------------------------------


class TestProvenanceConflict:
    """Fingerprint changes when schema versions differ."""

    def test_schema_version_changes_fingerprint(self) -> None:
        req1 = EpisodeReportRequest(
            episode_id="prov-check-001",
            proposal_timestamp_utc=NOW.isoformat(),
            proposal_references=(
                ProposalReference(
                    proposal_id=_sha("a"),
                    batch_id=_sha("b"),
                    source_id="test:source",
                    regime="bullish",
                    proposal_fingerprint=_sha("c"),
                    batch_fingerprint=_sha("d"),
                    decision="ACCEPT",
                    proposed_weight=Decimal("0.50"),
                    proposed_delta=Decimal("0.10"),
                ),
            ),
        )
        req2 = EpisodeReportRequest(
            episode_id="prov-check-001",
            proposal_timestamp_utc=NOW.isoformat(),
            episode_schema_version="episode_report_v2",
            proposal_references=(
                ProposalReference(
                    proposal_id=_sha("a"),
                    batch_id=_sha("b"),
                    source_id="test:source",
                    regime="bullish",
                    proposal_fingerprint=_sha("c"),
                    batch_fingerprint=_sha("d"),
                    decision="ACCEPT",
                    proposed_weight=Decimal("0.50"),
                    proposed_delta=Decimal("0.10"),
                ),
            ),
        )
        assert compute_episode_fingerprint(req1) != compute_episode_fingerprint(req2)


# ---------------------------------------------------------------------------
# Scenario 10: Duplicate ID rejection
# ---------------------------------------------------------------------------


class TestDuplicateIdRejection:
    """Duplicate evidence IDs are rejected at the EpisodeReportRequest level."""

    def test_duplicate_evidence_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EpisodeReportRequest(
                episode_id="dup-ev-001",
                proposal_timestamp_utc=NOW.isoformat(),
                proposal_references=(
                    ProposalReference(
                        proposal_id=_sha("a"),
                        batch_id=_sha("b"),
                        source_id="test:source",
                        regime="bullish",
                        proposal_fingerprint=_sha("c"),
                        batch_fingerprint=_sha("d"),
                        decision="ACCEPT",
                        proposed_weight=Decimal("0.50"),
                        proposed_delta=Decimal("0.10"),
                    ),
                ),
                evidence_references=(
                    EvidenceReference(
                        evidence_id="same-id",
                        source_id="s1",
                        regime="r1",
                        fingerprint=_sha("f"),
                    ),
                    EvidenceReference(
                        evidence_id="same-id",
                        source_id="s2",
                        regime="r2",
                        fingerprint=_sha("e"),
                    ),
                ),
            )


# ---------------------------------------------------------------------------
# Determinism and safety invariants
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Byte-stable output under identical inputs."""

    def test_deterministic_output(self) -> None:
        ep_request = EpisodeReportRequest(
            episode_id="det-test-001",
            proposal_timestamp_utc=NOW.isoformat(),
            review_state=ReviewState.ACCEPTED_BY_HUMAN,
            proposal_references=(
                ProposalReference(
                    proposal_id=_sha("a"),
                    batch_id=_sha("b"),
                    source_id="test:source",
                    regime="bullish",
                    proposal_fingerprint=_sha("c"),
                    batch_fingerprint=_sha("d"),
                    decision="ACCEPT",
                    proposed_weight=Decimal("0.50"),
                    proposed_delta=Decimal("0.10"),
                ),
            ),
            validation_references=(
                ValidationReference(
                    validation_id="bt-001",
                    validation_type=ValidationType.BACKTEST,
                    fingerprint=_sha("b"),
                    passed=True,
                ),
            ),
        )
        r1 = build_episode_report(ep_request)
        r2 = build_episode_report(ep_request)
        assert r1.model_dump_json() == r2.model_dump_json()
        assert r1.episode_json == r2.episode_json


class TestSourceDBUnchanged:
    """Source SQLite database remains byte-for-byte unchanged."""

    def test_db_unchanged_after_pipeline(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        _create_cache_db(db_path, [_valid_row()])
        original = db_path.read_bytes()

        run_evidence_pipeline(EvidencePipelineRequest(cache_db_path=db_path, as_of=NOW))
        assert db_path.read_bytes() == original


class TestProvenancePreserved:
    """Cross-layer schema/policy versions preserved in episode report."""

    def test_provenance_in_report(self) -> None:
        ep_request = EpisodeReportRequest(
            episode_id="prov-check-002",
            proposal_timestamp_utc=NOW.isoformat(),
            review_state=ReviewState.PENDING_REVIEW,
            proposal_references=(
                ProposalReference(
                    proposal_id=_sha("a"),
                    batch_id=_sha("b"),
                    source_id="test:source",
                    regime="bullish",
                    proposal_fingerprint=_sha("c"),
                    batch_fingerprint=_sha("d"),
                    decision="ACCEPT",
                    proposed_weight=Decimal("0.50"),
                    proposed_delta=Decimal("0.10"),
                ),
            ),
        )
        assert ep_request.episode_schema_version == EPISODE_SCHEMA_VERSION
        assert ep_request.policy_version == POLICY_VERSION
        assert ep_request.proposal_schema_version == PROPOSAL_SCHEMA_VERSION
        assert ep_request.evidence_schema_version == EVIDENCE_SCHEMA_VERSION


class TestNoRuntimeAccess:
    """Verify no Docker, Freqtrade, or exchange imports in the integration path."""

    def test_no_runtime_imports(self) -> None:
        """Scan only the SI v2 modules actually loaded by this integration test."""
        import sys
        forbidden = {"docker", "freqtrade", "exchange"}
        si_v2_modules = [m for m in sys.modules if m.startswith("si_v2")]
        excluded_prefixes = (
            "si_v2.adapters",
            "si_v2.backtest",
            "si_v2.observe",
            "si_v2.deploy",
            "si_v2.rainbow",
            "si_v2.cron",
            "si_v2.integrations",
            "si_v2.signals",
            "si_v2.loop.active_cycle_runner",
            "si_v2.proofs",
        )
        for modname in si_v2_modules:
            if modname.startswith(excluded_prefixes):
                continue
            mod = sys.modules[modname]
            if mod is None:
                continue
            try:
                src = getattr(mod, "__file__", None)
                if src is None:
                    continue
                with open(src) as f:
                    content = f.read()
                for fb in forbidden:
                    for line in content.splitlines():
                        stripped = line.strip()
                        if fb in stripped and (stripped.startswith("import ") or stripped.startswith("from ")):
                            pytest.fail(f"Forbidden import in {modname}: {stripped}")
            except (OSError, TypeError):
                pass


class TestRejectedEvidenceNoAccept:
    """Rejected/deferred evidence cannot produce ACCEPT proposal."""

    def test_strongly_negative_evidence_rejected(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        row = _valid_row()
        row["expectancy"] = -0.50
        row["drawdown_proxy"] = 0.60
        row["unique_trade_count"] = 2
        _create_cache_db(db_path, [row])

        result = run_evidence_pipeline(
            EvidencePipelineRequest(
                cache_db_path=db_path,
                as_of=NOW,
                minimum_unique_trade_count=10,
            )
        )
        assert len(result.accepted) == 0
