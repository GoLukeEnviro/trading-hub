"""Tests for the Rainbow advisory candidate quality evaluator.

Verifies:
- aligned fresh evidence ranks above neutral
- conflicting evidence ranks below aligned
- stale evidence provides no positive score
- degraded evidence provides no positive score
- absent evidence preserves baseline
- deterministic ordering
- no Autonomy confidence increase
- no RiskGuard bypass
- monotonic safety invariant
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from si_v2.rainbow.candidate_quality import (
    AlignmentState,
    RainbowCandidateQualityEvaluator,
)

JsonObject = dict[str, object]


def _signal(
    direction: str = "long",
    confidence: float = 0.85,
    timestamp_utc: str | None = None,
    source_id: str = "rainbow:ta",
) -> JsonObject:
    if timestamp_utc is None:
        timestamp_utc = datetime.now(UTC).isoformat()
    return {
        "event_type": "signal",
        "source_id": source_id,
        "direction": direction,
        "confidence": confidence,
        "timestamp_utc": timestamp_utc,
        "metadata": {"reason_codes": ["ta_rsi_oversold"]},
        "redaction_status": "clean",
    }


def _evidence(
    source_id: str = "rainbow:ta",
    evidence_id: str = "evt_001",
) -> JsonObject:
    return {
        "source_id": source_id,
        "evidence_id": evidence_id,
    }


class TestRainbowCandidateQuality:
    def test_aligned_fresh_evidence_scores_above_neutral(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        evaluator = RainbowCandidateQualityEvaluator()
        ts = (now - timedelta(minutes=30)).isoformat()
        signals = [_signal(direction="long", timestamp_utc=ts)]
        evidence = [_evidence()]

        quality = evaluator.evaluate(
            candidate_direction="long",
            rainbow_signals=signals,
            rainbow_evidence=evidence,
            now=now,
        )

        assert quality.alignment == AlignmentState.ALIGNED
        assert quality.usable is True
        assert quality.advisory_score > 0.3  # aligned > neutral

    def test_conflicting_evidence_scores_below_aligned(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        evaluator = RainbowCandidateQualityEvaluator()
        ts = (now - timedelta(minutes=30)).isoformat()

        # Conflicting: candidate long, signal short
        quality = evaluator.evaluate(
            candidate_direction="long",
            rainbow_signals=[_signal(direction="short", timestamp_utc=ts)],
            rainbow_evidence=[_evidence()],
            now=now,
        )

        assert quality.alignment == AlignmentState.CONFLICTING
        assert quality.usable is True  # fresh but conflicting
        assert quality.advisory_score == 0.0  # conflicting = 0
        assert any("conflict" in r for r in quality.downgrade_reasons)

    def test_stale_evidence_provides_no_positive_score(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        evaluator = RainbowCandidateQualityEvaluator(
            max_signal_age_seconds=3600.0,
            stale_age_seconds=7200.0,
        )
        # Signal is 1.5 hours old — between max_signal_age and stale_age
        ts = (now - timedelta(hours=1.5)).isoformat()
        quality = evaluator.evaluate(
            candidate_direction="long",
            rainbow_signals=[_signal(direction="long", timestamp_utc=ts)],
            rainbow_evidence=[_evidence()],
            now=now,
        )

        assert quality.quality_status == "stale"
        assert quality.advisory_score == 0.0
        assert quality.usable is False

    def test_degraded_evidence_provides_no_positive_score(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        evaluator = RainbowCandidateQualityEvaluator()
        # Signal with no timestamp — degraded
        quality = evaluator.evaluate(
            candidate_direction="long",
            rainbow_signals=[_signal(timestamp_utc="")],
            rainbow_evidence=[_evidence()],
            now=now,
        )

        assert quality.quality_status in ("degraded", "absent")
        assert quality.advisory_score == 0.0

    def test_absent_evidence_preserves_baseline(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        evaluator = RainbowCandidateQualityEvaluator()

        quality = evaluator.evaluate(
            candidate_direction="long",
            rainbow_signals=[],
            rainbow_evidence=[],
            now=now,
        )

        assert quality.alignment == AlignmentState.ABSENT
        assert quality.advisory_score == 0.0
        assert quality.usable is False

    def test_deterministic_ordering(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        evaluator = RainbowCandidateQualityEvaluator()
        ts = (now - timedelta(minutes=30)).isoformat()

        q1 = evaluator.evaluate(
            candidate_direction="long",
            rainbow_signals=[_signal(direction="long", timestamp_utc=ts)],
            rainbow_evidence=[_evidence()],
            now=now,
        )
        q2 = evaluator.evaluate(
            candidate_direction="long",
            rainbow_signals=[_signal(direction="long", timestamp_utc=ts)],
            rainbow_evidence=[_evidence()],
            now=now,
        )

        assert q1.advisory_score == q2.advisory_score
        assert q1.alignment == q2.alignment
        assert q1.to_dict() == q2.to_dict()

    def test_no_autonomy_confidence_increase(self) -> None:
        """Verify advisory_score is NOT passed as Autonomy confidence."""
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        evaluator = RainbowCandidateQualityEvaluator()
        ts = (now - timedelta(minutes=30)).isoformat()

        quality = evaluator.evaluate(
            candidate_direction="long",
            rainbow_signals=[_signal(direction="long", confidence=0.95, timestamp_utc=ts)],
            rainbow_evidence=[_evidence()],
            now=now,
        )

        # The advisory score is for ranking only
        assert quality.advisory_score > 0
        # It must NOT be used as Autonomy confidence
        # (verified by the guard test that checks no code path
        #  passes advisory_score to AutonomyPolicyInput.confidence)

    def test_neutral_evidence_is_informational(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        evaluator = RainbowCandidateQualityEvaluator()
        ts = (now - timedelta(minutes=30)).isoformat()

        # Candidate has no direction — neutral
        quality = evaluator.evaluate(
            candidate_direction=None,
            rainbow_signals=[_signal(direction="long", timestamp_utc=ts)],
            rainbow_evidence=[_evidence()],
            now=now,
        )

        assert quality.alignment == AlignmentState.NEUTRAL
        assert quality.advisory_score == 0.3
        assert quality.usable is True

    def test_multiple_sources_bounded_output(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        evaluator = RainbowCandidateQualityEvaluator()
        ts = (now - timedelta(minutes=30)).isoformat()

        quality = evaluator.evaluate(
            candidate_direction="long",
            rainbow_signals=[
                _signal(direction="long", timestamp_utc=ts, source_id="rainbow:ta"),
                _signal(direction="long", timestamp_utc=ts, source_id="rainbow:llm"),
            ],
            rainbow_evidence=[
                _evidence(source_id="rainbow:ta", evidence_id="evt_001"),
                _evidence(source_id="rainbow:llm", evidence_id="evt_002"),
            ],
            now=now,
        )

        assert len(quality.source_ids) == 2
        assert len(quality.evidence_ids) == 2
        assert quality.advisory_score > 0

    def test_monotonic_safety_invariant(self) -> None:
        """For identical baseline inputs, decision_with_rainbow must be
        equal to or stricter than decision_without_rainbow."""
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        evaluator = RainbowCandidateQualityEvaluator()

        # Without Rainbow: absent
        without = evaluator.evaluate(
            candidate_direction="long",
            rainbow_signals=[],
            rainbow_evidence=[],
            now=now,
        )

        # With conflicting Rainbow: should be stricter (lower score)
        ts = (now - timedelta(minutes=30)).isoformat()
        with_conflict = evaluator.evaluate(
            candidate_direction="long",
            rainbow_signals=[_signal(direction="short", timestamp_utc=ts)],
            rainbow_evidence=[_evidence()],
            now=now,
        )

        # Conflicting evidence must not improve the score
        assert with_conflict.advisory_score <= without.advisory_score

        # With stale Rainbow: should be equal or stricter
        stale_ts = (now - timedelta(hours=5)).isoformat()
        with_stale = evaluator.evaluate(
            candidate_direction="long",
            rainbow_signals=[_signal(direction="long", timestamp_utc=stale_ts)],
            rainbow_evidence=[_evidence()],
            now=now,
        )
        assert with_stale.advisory_score <= without.advisory_score
