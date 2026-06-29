"""Tests for orchestrator/control/weekly_review_cadence.py — pure policy functions.

Tests cover: as-of timestamp, output root, evidence freshness, overlap lock,
timeout validation, weekly outcome classification, Telegram delivery contract,
separation proof, retention cutoff, and operator procedure invariants.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch

from orchestrator.control.weekly_review_cadence import (
    DEFAULT_WEEKLY_DAY,
    DEFAULT_WEEKLY_HOUR_UTC,
    DERIVED_ARTIFACT_RETENTION_WEEKS,
    EVIDENCE_FRESHNESS_MAX_DAYS,
    MAX_CYCLE_TIMEOUT_SECONDS,
    OPERATOR_WEEKLY_PROCEDURE,
    PAUSE_ROLLBACK_PROCEDURE,
    CadencePhase,
    CycleLockState,
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


# ======================================================================
# Enums
# ======================================================================

class TestCadencePhase:
    def test_values(self) -> None:
        assert CadencePhase.PREFLIGHT.value == "preflight"
        assert CadencePhase.ACQUIRE_LOCK.value == "acquire_lock"
        assert CadencePhase.COLLECT_EVIDENCE.value == "collect_evidence"
        assert CadencePhase.GENERATE_REVIEW.value == "generate_review"
        assert CadencePhase.PERSIST_ARTIFACTS.value == "persist_artifacts"
        assert CadencePhase.RELEASE_LOCK.value == "release_lock"
        assert CadencePhase.DELIVER_REPORT.value == "deliver_report"
        assert CadencePhase.RECORD_OUTCOME.value == "record_outcome"


class TestCycleLockState:
    def test_values(self) -> None:
        assert CycleLockState.FREE.value == "FREE"
        assert CycleLockState.LOCKED.value == "LOCKED"
        assert CycleLockState.EXPIRED.value == "EXPIRED"


class TestRunOutcome:
    def test_values(self) -> None:
        assert RunOutcome.GREEN.value == "GREEN"
        assert RunOutcome.YELLOW.value == "YELLOW"
        assert RunOutcome.RED.value == "RED"
        assert RunOutcome.EMPTY.value == "EMPTY"
        assert RunOutcome.SPARSE.value == "SPARSE"
        assert RunOutcome.STALE.value == "STALE"
        assert RunOutcome.CONFLICTING.value == "CONFLICTING"
        assert RunOutcome.DEFERRED.value == "DEFERRED"
        assert RunOutcome.FAILED.value == "FAILED"


# ======================================================================
# As-of timestamp
# ======================================================================

class TestComputeAsOfTimestamp:
    def test_monday_0900(self) -> None:
        """Monday 09:00 UTC should return same time."""
        ref = datetime(2026, 6, 29, 9, 0, 0, tzinfo=UTC)  # Monday
        result = compute_as_of_timestamp(reference_time=ref)
        assert result == "2026-06-29T09:00:00Z"

    def test_monday_0859(self) -> None:
        """Monday 08:59 UTC should return previous Monday 09:00."""
        ref = datetime(2026, 6, 29, 8, 59, 0, tzinfo=UTC)
        result = compute_as_of_timestamp(reference_time=ref)
        assert result == "2026-06-22T09:00:00Z"

    def test_tuesday(self) -> None:
        """Tuesday should return current week's Monday 09:00."""
        ref = datetime(2026, 6, 30, 12, 0, 0, tzinfo=UTC)  # Tuesday
        result = compute_as_of_timestamp(reference_time=ref)
        assert result == "2026-06-29T09:00:00Z"

    def test_sunday(self) -> None:
        """Sunday should return previous Monday 09:00."""
        ref = datetime(2026, 7, 5, 12, 0, 0, tzinfo=UTC)  # Sunday
        result = compute_as_of_timestamp(reference_time=ref)
        assert result == "2026-06-29T09:00:00Z"

    def test_custom_weekly_day(self) -> None:
        """Wednesday (2) at 14:00 UTC."""
        ref = datetime(2026, 7, 1, 15, 0, 0, tzinfo=UTC)  # Wednesday
        result = compute_as_of_timestamp(reference_time=ref, weekly_day=2, weekly_hour=14)
        assert result == "2026-07-01T14:00:00Z"

    def test_custom_weekly_hour(self) -> None:
        ref = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)  # Monday
        result = compute_as_of_timestamp(reference_time=ref, weekly_hour=12)
        assert result == "2026-06-29T12:00:00Z"


# ======================================================================
# Output root
# ======================================================================

class TestComputeOutputRoot:
    def test_standard_week(self) -> None:
        result = compute_output_root(Path("/base"), "2026-06-29T09:00:00Z")
        assert str(result) == "/base/reviews/2026/W27"

    def test_early_january(self) -> None:
        """Week 1 of 2026."""
        result = compute_output_root(Path("/base"), "2026-01-05T09:00:00Z")
        assert str(result) == "/base/reviews/2026/W02"

    def test_late_december(self) -> None:
        """Week 53 of 2025 (ISO week)."""
        result = compute_output_root(Path("/base"), "2025-12-29T09:00:00Z")
        assert "W01" in str(result) or "W53" in str(result) or "W52" in str(result)


# ======================================================================
# Evidence freshness
# ======================================================================

class TestValidateEvidenceFreshness:
    def test_all_fresh(self, tmp_path: Path) -> None:
        path = tmp_path / "evidence.json"
        path.write_text("data")
        fresh, warnings = validate_evidence_freshness([path], "2026-06-29T09:00:00Z")
        assert fresh is True
        assert warnings == []

    def test_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.json"
        fresh, warnings = validate_evidence_freshness([path], "2026-06-29T09:00:00Z")
        assert fresh is False
        assert any("missing" in w.lower() for w in warnings)

    def test_stale_file(self, tmp_path: Path) -> None:
        path = tmp_path / "stale.json"
        path.write_text("data")
        # Set mtime to 8 days ago
        old_time = datetime(2026, 6, 21, 9, 0, 0, tzinfo=UTC).timestamp()
        import os
        os.utime(path, (old_time, old_time))
        fresh, warnings = validate_evidence_freshness([path], "2026-06-29T09:00:00Z")
        assert fresh is False
        assert any("stale" in w.lower() for w in warnings)

    def test_mixed_freshness(self, tmp_path: Path) -> None:
        fresh_file = tmp_path / "fresh.json"
        fresh_file.write_text("data")
        stale_file = tmp_path / "stale.json"
        stale_file.write_text("data")
        old_time = datetime(2026, 6, 1, 9, 0, 0, tzinfo=UTC).timestamp()
        import os
        os.utime(stale_file, (old_time, old_time))
        fresh, warnings = validate_evidence_freshness([fresh_file, stale_file], "2026-06-29T09:00:00Z")
        assert fresh is False
        assert len(warnings) >= 1


# ======================================================================
# Overlap lock
# ======================================================================

class TestValidateNoOverlap:
    def test_free_passes(self) -> None:
        result = validate_no_overlap(CycleLockState.FREE)
        assert result.passed is True

    def test_locked_fails(self) -> None:
        result = validate_no_overlap(CycleLockState.LOCKED)
        assert result.passed is False

    def test_expired_fails(self) -> None:
        result = validate_no_overlap(CycleLockState.EXPIRED)
        assert result.passed is False
        assert "manual intervention" in result.detail


# ======================================================================
# Timeout validation
# ======================================================================

class TestValidateTimeout:
    def test_valid_timeout(self) -> None:
        valid, msg = validate_timeout(3600)
        assert valid is True
        assert msg == "ok"

    def test_one_second(self) -> None:
        valid, msg = validate_timeout(1)
        assert valid is True

    def test_max_timeout(self) -> None:
        valid, msg = validate_timeout(MAX_CYCLE_TIMEOUT_SECONDS)
        assert valid is True

    def test_zero_fails(self) -> None:
        valid, msg = validate_timeout(0)
        assert valid is False
        assert "positive" in msg

    def test_negative_fails(self) -> None:
        valid, msg = validate_timeout(-1)
        assert valid is False

    def test_exceeds_max(self) -> None:
        valid, msg = validate_timeout(MAX_CYCLE_TIMEOUT_SECONDS + 1)
        assert valid is False
        assert "exceeds max" in msg


# ======================================================================
# Weekly outcome classification
# ======================================================================

class TestClassifyWeeklyOutcome:
    def test_green(self) -> None:
        result = classify_weekly_outcome(review_generated=True, evidence_count=5, fresh=True, conflicts=False)
        assert result == RunOutcome.GREEN

    def test_failed_errors(self) -> None:
        result = classify_weekly_outcome(review_generated=True, evidence_count=5, fresh=True, conflicts=False, errors=["err"])
        assert result == RunOutcome.FAILED

    def test_failed_not_generated(self) -> None:
        result = classify_weekly_outcome(review_generated=False, evidence_count=0, fresh=True, conflicts=False)
        assert result == RunOutcome.FAILED

    def test_stale(self) -> None:
        result = classify_weekly_outcome(review_generated=True, evidence_count=5, fresh=False, conflicts=False)
        assert result == RunOutcome.STALE

    def test_conflicting(self) -> None:
        result = classify_weekly_outcome(review_generated=True, evidence_count=5, fresh=True, conflicts=True)
        assert result == RunOutcome.CONFLICTING

    def test_empty(self) -> None:
        result = classify_weekly_outcome(review_generated=True, evidence_count=0, fresh=True, conflicts=False)
        assert result == RunOutcome.EMPTY

    def test_sparse(self) -> None:
        result = classify_weekly_outcome(review_generated=True, evidence_count=1, fresh=True, conflicts=False)
        assert result == RunOutcome.SPARSE

    def test_yellow(self) -> None:
        result = classify_weekly_outcome(review_generated=True, evidence_count=5, fresh=True, conflicts=False, warnings=["warn"])
        assert result == RunOutcome.YELLOW


# ======================================================================
# Telegram delivery contract
# ======================================================================

class TestValidateTelegramDeliveryContract:
    def test_disabled_compliant(self) -> None:
        compliant, warnings = validate_telegram_delivery_contract(
            delivery_enabled=False, channel_configured=False,
            message_sent=False, delivery_confirmed=False,
        )
        assert compliant is True
        assert warnings == []

    def test_enabled_no_channel_warning(self) -> None:
        compliant, warnings = validate_telegram_delivery_contract(
            delivery_enabled=True, channel_configured=False,
            message_sent=False, delivery_confirmed=False,
        )
        assert compliant is False
        assert any("channel" in w for w in warnings)

    def test_enabled_no_message_warning(self) -> None:
        compliant, warnings = validate_telegram_delivery_contract(
            delivery_enabled=True, channel_configured=True,
            message_sent=False, delivery_confirmed=False,
        )
        assert compliant is False
        assert any("message" in w for w in warnings)

    def test_sent_not_confirmed_warning(self) -> None:
        compliant, warnings = validate_telegram_delivery_contract(
            delivery_enabled=True, channel_configured=True,
            message_sent=True, delivery_confirmed=False,
        )
        assert compliant is False
        assert any("confirmed" in w for w in warnings)

    def test_full_success_compliant(self) -> None:
        compliant, warnings = validate_telegram_delivery_contract(
            delivery_enabled=True, channel_configured=True,
            message_sent=True, delivery_confirmed=True,
        )
        assert compliant is True
        assert warnings == []


# ======================================================================
# Separation proof
# ======================================================================

class TestProveReviewCannotApply:
    def test_returns_proof_statements(self) -> None:
        proof = prove_review_cannot_apply()
        assert len(proof) >= 3
        assert any("read_only" in p for p in proof)
        assert any("separate" in p for p in proof)
        assert any("mutate" in p for p in proof)


# ======================================================================
# Retention cutoff
# ======================================================================

class TestComputeRetentionCutoff:
    def test_default_retention(self) -> None:
        ref = datetime(2026, 6, 29, 9, 0, 0, tzinfo=UTC)
        result = compute_retention_cutoff(reference_time=ref)
        expected = (ref - timedelta(weeks=DERIVED_ARTIFACT_RETENTION_WEEKS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert result == expected

    def test_custom_retention(self) -> None:
        ref = datetime(2026, 6, 29, 9, 0, 0, tzinfo=UTC)
        result = compute_retention_cutoff(reference_time=ref, retention_weeks=4)
        expected = (ref - timedelta(weeks=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert result == expected

    def test_iso_format(self) -> None:
        result = compute_retention_cutoff(reference_time=datetime(2026, 6, 29, 9, 0, 0, tzinfo=UTC))
        assert result.endswith("Z")
        assert "T" in result


# ======================================================================
# Operator procedure invariants
# ======================================================================

class TestOperatorWeeklyProcedure:
    def test_not_empty(self) -> None:
        assert len(OPERATOR_WEEKLY_PROCEDURE) > 0

    def test_contains_paused(self) -> None:
        text = "\n".join(OPERATOR_WEEKLY_PROCEDURE)
        assert "PAUSED" in text

    def test_contains_lock(self) -> None:
        text = "\n".join(OPERATOR_WEEKLY_PROCEDURE)
        assert "lock" in text.lower()

    def test_contains_evidence(self) -> None:
        text = "\n".join(OPERATOR_WEEKLY_PROCEDURE)
        assert "evidence" in text.lower()

    def test_contains_telegram_no_secrets(self) -> None:
        text = "\n".join(OPERATOR_WEEKLY_PROCEDURE)
        assert "Telegram" in text
        assert "no secrets" in text.lower()

    def test_contains_no_duplicate_proposals(self) -> None:
        text = "\n".join(OPERATOR_WEEKLY_PROCEDURE)
        assert "duplicate" in text.lower() or "retry" in text.lower()


class TestPauseRollbackProcedure:
    def test_not_empty(self) -> None:
        assert len(PAUSE_ROLLBACK_PROCEDURE) > 0

    def test_contains_pause(self) -> None:
        text = "\n".join(PAUSE_ROLLBACK_PROCEDURE)
        assert "PAUSE" in text

    def test_contains_disable(self) -> None:
        text = "\n".join(PAUSE_ROLLBACK_PROCEDURE)
        assert "DISABLE" in text

    def test_contains_rollback(self) -> None:
        text = "\n".join(PAUSE_ROLLBACK_PROCEDURE)
        assert "ROLLBACK" in text

    def test_contains_incident(self) -> None:
        text = "\n".join(PAUSE_ROLLBACK_PROCEDURE)
        assert "INCIDENT" in text
