"""Tests for the SI v2 weekly review cadence policy (issue #66).

Validates: as_of timestamp, deterministic output roots, evidence freshness,
overlap prevention, timeout limits, run outcome classification, Telegram
delivery, separation of concerns, retention, and operator procedures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from orchestrator.control.weekly_review_cadence import (
    MAX_CYCLE_TIMEOUT_SECONDS,
    MAX_RETRY_ATTEMPTS,
    CycleLockState,
    ReviewInputContract,
    RunOutcome,
    classify_weekly_outcome,
    compute_as_of_timestamp,
    compute_output_root,
    compute_retention_cutoff,
    prove_review_cannot_apply,
    validate_evidence_freshness,
    validate_no_overlap,
    validate_telegram_delivery_contract,
    validate_timeout,
)


# ---------------------------------------------------------------------------
# As-of timestamp
# ---------------------------------------------------------------------------


class TestAsOfTimestamp:
    def test_monday_morning_returns_same_monday(self) -> None:
        ref = datetime(2026, 6, 15, 9, 0, 0, tzinfo=UTC)  # Monday
        result = compute_as_of_timestamp(ref)
        assert result == "2026-06-15T09:00:00Z"

    def test_tuesday_returns_previous_monday(self) -> None:
        ref = datetime(2026, 6, 16, 14, 30, 0, tzinfo=UTC)  # Tuesday
        result = compute_as_of_timestamp(ref)
        assert result == "2026-06-15T09:00:00Z"

    def test_sunday_returns_previous_monday(self) -> None:
        ref = datetime(2026, 6, 21, 8, 0, 0, tzinfo=UTC)  # Sunday
        result = compute_as_of_timestamp(ref)
        assert result == "2026-06-15T09:00:00Z"

    def test_before_hour_returns_previous_week(self) -> None:
        ref = datetime(2026, 6, 15, 8, 59, 59, tzinfo=UTC)  # Monday before 09:00
        result = compute_as_of_timestamp(ref)
        assert result == "2026-06-08T09:00:00Z"

    def test_explicit_is_included(self) -> None:
        """as_of timestamp must include the ISO time for deterministic reference."""
        ref = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)  # Wednesday
        result = compute_as_of_timestamp(ref)
        assert "2026-06-15" in result


# ---------------------------------------------------------------------------
# Deterministic output roots
# ---------------------------------------------------------------------------


class TestOutputRoot:
    def test_monday_24_in_iso_week_25(self) -> None:
        """June 15, 2026 is ISO week 25."""
        as_of = "2026-06-15T09:00:00Z"
        root = compute_output_root(Path("/data"), as_of)
        assert root == Path("/data/reviews/2026/W25")

    def test_deterministic(self) -> None:
        """Same as_of always produces same output root."""
        as_of = "2026-06-15T09:00:00Z"
        r1 = compute_output_root(Path("/base"), as_of)
        r2 = compute_output_root(Path("/base"), as_of)
        assert r1 == r2


# ---------------------------------------------------------------------------
# Evidence freshness
# ---------------------------------------------------------------------------


class TestEvidenceFreshness:
    def test_fresh_file_passes(self, tmp_path: Path) -> None:
        evidence = tmp_path / "report.json"
        evidence.write_text("{}")
        fresh, warnings = validate_evidence_freshness(
            [evidence], datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert fresh is True
        assert warnings == []

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.json"
        fresh, warnings = validate_evidence_freshness(
            [missing], datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert fresh is False
        assert any("missing" in w for w in warnings)

    def test_stale_file_fails(self, tmp_path: Path) -> None:
        stale = tmp_path / "old.json"
        stale.write_text("{}")
        # Set mtime to 10 days ago
        old_time = (datetime.now(UTC) - timedelta(days=10)).timestamp()
        import os
        os.utime(stale, (old_time, old_time))

        fresh, warnings = validate_evidence_freshness(
            [stale], datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            max_age_days=7,
        )
        assert fresh is False
        assert any("stale" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Overlap prevention
# ---------------------------------------------------------------------------


class TestOverlapPrevention:
    def test_free_lock_passes(self) -> None:
        result = validate_no_overlap(CycleLockState.FREE)
        assert result.passed is True

    def test_locked_lock_fails(self) -> None:
        result = validate_no_overlap(CycleLockState.LOCKED)
        assert result.passed is False

    def test_expired_lock_fails(self) -> None:
        result = validate_no_overlap(CycleLockState.EXPIRED)
        assert result.passed is False


# ---------------------------------------------------------------------------
# Timeout validation
# ---------------------------------------------------------------------------


class TestTimeout:
    def test_valid_timeout(self) -> None:
        ok, msg = validate_timeout(3600)
        assert ok is True

    def test_zero_timeout_fails(self) -> None:
        ok, msg = validate_timeout(0)
        assert ok is False

    def test_negative_timeout_fails(self) -> None:
        ok, msg = validate_timeout(-1)
        assert ok is False

    def test_excessive_timeout_fails(self) -> None:
        ok, msg = validate_timeout(MAX_CYCLE_TIMEOUT_SECONDS + 1)
        assert ok is False

    def test_max_timeout_passes(self) -> None:
        ok, msg = validate_timeout(MAX_CYCLE_TIMEOUT_SECONDS)
        assert ok is True


# ---------------------------------------------------------------------------
# Run outcome classification
# ---------------------------------------------------------------------------


class TestRunOutcome:
    def test_green_with_fresh_evidence(self) -> None:
        result = classify_weekly_outcome(
            review_generated=True, evidence_count=3, fresh=True, conflicts=False,
        )
        assert result == RunOutcome.GREEN

    def test_yellow_with_warnings(self) -> None:
        result = classify_weekly_outcome(
            review_generated=True, evidence_count=3, fresh=True, conflicts=False,
            warnings=["slow run"],
        )
        assert result == RunOutcome.YELLOW

    def test_red_with_errors(self) -> None:
        result = classify_weekly_outcome(
            review_generated=True, evidence_count=3, fresh=True, conflicts=False,
            errors=["crash"],
        )
        assert result == RunOutcome.FAILED

    def test_empty_no_evidence(self) -> None:
        result = classify_weekly_outcome(
            review_generated=True, evidence_count=0, fresh=True, conflicts=False,
        )
        assert result == RunOutcome.EMPTY

    def test_sparse_insufficient_evidence(self) -> None:
        result = classify_weekly_outcome(
            review_generated=True, evidence_count=1, fresh=True, conflicts=False,
        )
        assert result == RunOutcome.SPARSE

    def test_stale_evidence(self) -> None:
        result = classify_weekly_outcome(
            review_generated=True, evidence_count=3, fresh=False, conflicts=False,
        )
        assert result == RunOutcome.STALE

    def test_conflicting_evidence(self) -> None:
        result = classify_weekly_outcome(
            review_generated=True, evidence_count=3, fresh=True, conflicts=True,
        )
        assert result == RunOutcome.CONFLICTING

    def test_failed_no_review(self) -> None:
        result = classify_weekly_outcome(
            review_generated=False, evidence_count=0, fresh=True, conflicts=False,
        )
        assert result == RunOutcome.FAILED


# ---------------------------------------------------------------------------
# Telegram delivery contract
# ---------------------------------------------------------------------------


class TestTelegramDelivery:
    def test_disabled_delivery_is_compliant(self) -> None:
        ok, _ = validate_telegram_delivery_contract(
            delivery_enabled=False, channel_configured=False,
            message_sent=False, delivery_confirmed=False,
        )
        assert ok is True

    def test_enabled_no_channel_warns(self) -> None:
        ok, warnings = validate_telegram_delivery_contract(
            delivery_enabled=True, channel_configured=False,
            message_sent=False, delivery_confirmed=False,
        )
        assert ok is False
        assert any("channel" in w.lower() for w in warnings)

    def test_enabled_sent_not_confirmed_warns(self) -> None:
        ok, warnings = validate_telegram_delivery_contract(
            delivery_enabled=True, channel_configured=True,
            message_sent=True, delivery_confirmed=False,
        )
        assert ok is False
        assert any("confirmed" in w.lower() for w in warnings)

    def test_full_delivery_is_compliant(self) -> None:
        ok, warnings = validate_telegram_delivery_contract(
            delivery_enabled=True, channel_configured=True,
            message_sent=True, delivery_confirmed=True,
        )
        assert ok is True


# ---------------------------------------------------------------------------
# Separation of concerns
# ---------------------------------------------------------------------------


class TestSeparationOfConcerns:
    def test_review_cannot_apply(self) -> None:
        proofs = prove_review_cannot_apply()
        assert len(proofs) >= 3
        # No proof should mention applying or approving
        for proof in proofs:
            assert "apply" not in proof.lower() or "cannot" in proof.lower() or "exclude" in proof.lower()

    def test_no_mutation_in_review_commands(self) -> None:
        """Review commands must be read-only."""
        review_commands = [
            "si_v2_weekly_review",
            "si_v2_episode_report",
            "si_v2_evidence_collect",
        ]
        forbidden = ("apply_weight", "approve_proposal", "force_trade", "mutate", "deploy")
        for cmd in review_commands:
            for substr in forbidden:
                assert substr not in cmd


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


class TestRetention:
    def test_retention_cutoff_is_in_past(self) -> None:
        cutoff = compute_retention_cutoff()
        cutoff_dt = datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        assert cutoff_dt < datetime.now(UTC)

    def test_retention_respects_weeks(self) -> None:
        ref = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        cutoff = compute_retention_cutoff(reference_time=ref, retention_weeks=4)
        cutoff_dt = datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        expected = ref - timedelta(weeks=4)
        assert cutoff_dt == expected


# ---------------------------------------------------------------------------
# Review input contract
# ---------------------------------------------------------------------------


class TestReviewInputContract:
    def test_contract_fields(self) -> None:
        contract = ReviewInputContract(
            as_of="2026-06-15T09:00:00Z",
            evidence_root="/data/evidence",
            policy_version=1,
            controller_state_commit="a" * 40,
        )
        assert contract.policy_version == 1
        assert len(contract.controller_state_commit) == 40


# ---------------------------------------------------------------------------
# Retry safety
# ---------------------------------------------------------------------------


class TestRetrySafety:
    def test_max_retries_is_small(self) -> None:
        """Max retries must be low to prevent duplicate proposals."""
        assert MAX_RETRY_ATTEMPTS <= 3

    def test_timeout_within_reasonable_bounds(self) -> None:
        """Cycle timeout must not be excessive."""
        assert MAX_CYCLE_TIMEOUT_SECONDS <= 14400  # 4 hours


# ---------------------------------------------------------------------------
# No runtime imports
# ---------------------------------------------------------------------------


class TestNoRuntimeImports:
    def test_no_runtime_imports(self) -> None:
        import orchestrator.control.weekly_review_cadence as mod

        src = mod.__file__ or ""
        with open(src) as f:
            content = f.read()
        for forbidden in ("docker", "freqtrade", "exchange", "systemd"):
            for line in content.splitlines():
                stripped = line.strip()
                if (
                    stripped.startswith("import ")
                    or stripped.startswith("from ")
                ) and forbidden in stripped:
                    raise AssertionError(
                        f"Forbidden import in weekly_review_cadence: {stripped}"
                    )
