"""Tests for Stale Evidence Gate — configurable staleness detection.

Covers all acceptance criteria from #310 Phase 4:
  - stale active-cycle evidence blocks readiness
  - stale monitoring evidence blocks readiness
  - stale dynamic-exit evidence blocks readiness
  - fresh evidence passes
  - empty evidence → NOT_APPLICABLE
  - custom thresholds
  - convenience functions (is_evidence_stale, filter_stale, filter_fresh)
  - serialization (to_dict)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from si_v2.validation.stale_evidence_gate import (
    DEFAULT_STALENESS_THRESHOLDS,
    EvidenceDomain,
    EvidenceItem,
    StaleEvidenceStatus,
    evaluate_stale_evidence,
    filter_fresh,
    filter_stale,
    is_evidence_stale,
)

# Fixed reference time for deterministic tests
_NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------


def _make_item(
    domain: EvidenceDomain,
    hours_ago: float,
    evidence_id: str | None = None,
) -> EvidenceItem:
    """Create an evidence item at a specific offset from _NOW."""
    return EvidenceItem(
        domain=domain,
        evidence_id=evidence_id or f"{domain.value}_{hours_ago}h",
        timestamp=_NOW - timedelta(hours=hours_ago),
        description=f"Test evidence for {domain.value}",
    )


# ---------------------------------------------------------------------------
# Empty / no evidence
# ---------------------------------------------------------------------------


class TestEmptyEvidence:
    def test_no_evidence_returns_not_applicable(self) -> None:
        """Empty evidence list → NOT_APPLICABLE."""
        verdict = evaluate_stale_evidence([], now=_NOW)
        assert verdict.status == StaleEvidenceStatus.NOT_APPLICABLE
        assert verdict.total_count == 0
        assert verdict.stale_count == 0
        assert verdict.fresh_count == 0
        assert "No evidence" in verdict.summary


# ---------------------------------------------------------------------------
# Fresh evidence — all domains
# ---------------------------------------------------------------------------


class TestFreshEvidence:
    def test_fresh_active_cycle_passes(self) -> None:
        """Active cycle evidence within 24h threshold → PASS."""
        items = [_make_item(EvidenceDomain.ACTIVE_CYCLE, 12)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.PASS
        assert verdict.fresh_count == 1
        assert verdict.stale_count == 0

    def test_fresh_monitoring_passes(self) -> None:
        """Monitoring evidence within 6h threshold → PASS."""
        items = [_make_item(EvidenceDomain.MONITORING, 3)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.PASS
        assert verdict.fresh_count == 1

    def test_fresh_dynamic_exit_passes(self) -> None:
        """Dynamic exit evidence within 12h threshold → PASS."""
        items = [_make_item(EvidenceDomain.DYNAMIC_EXIT, 6)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.PASS
        assert verdict.fresh_count == 1

    def test_fresh_proposal_passes(self) -> None:
        """Proposal evidence within 48h threshold → PASS."""
        items = [_make_item(EvidenceDomain.PROPOSAL, 24)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.PASS
        assert verdict.fresh_count == 1

    def test_fresh_measurement_passes(self) -> None:
        """Measurement evidence within 24h threshold → PASS."""
        items = [_make_item(EvidenceDomain.MEASUREMENT, 12)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.PASS
        assert verdict.fresh_count == 1

    def test_all_domains_fresh_passes(self) -> None:
        """All domains with fresh evidence → PASS."""
        items = [
            _make_item(EvidenceDomain.ACTIVE_CYCLE, 12),
            _make_item(EvidenceDomain.MONITORING, 3),
            _make_item(EvidenceDomain.DYNAMIC_EXIT, 6),
            _make_item(EvidenceDomain.PROPOSAL, 24),
            _make_item(EvidenceDomain.MEASUREMENT, 12),
        ]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.PASS
        assert verdict.fresh_count == 5
        assert verdict.stale_count == 0
        assert verdict.total_count == 5


# ---------------------------------------------------------------------------
# Stale evidence — each domain
# ---------------------------------------------------------------------------


class TestStaleActiveCycle:
    def test_stale_active_cycle_fails(self) -> None:
        """Active cycle evidence older than 24h → FAIL."""
        items = [_make_item(EvidenceDomain.ACTIVE_CYCLE, 30)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.FAIL
        assert verdict.stale_count == 1
        assert verdict.fresh_count == 0
        assert "Stale" in verdict.summary

    def test_stale_active_cycle_at_threshold_passes(self) -> None:
        """Active cycle evidence exactly at 24h threshold → PASS (not stale)."""
        items = [_make_item(EvidenceDomain.ACTIVE_CYCLE, 24)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.PASS
        assert verdict.fresh_count == 1

    def test_stale_active_cycle_just_over_threshold_fails(self) -> None:
        """Active cycle evidence just over 24h threshold → FAIL."""
        items = [_make_item(EvidenceDomain.ACTIVE_CYCLE, 24.1)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.FAIL
        assert verdict.stale_count == 1


class TestStaleMonitoring:
    def test_stale_monitoring_fails(self) -> None:
        """Monitoring evidence older than 6h → FAIL."""
        items = [_make_item(EvidenceDomain.MONITORING, 8)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.FAIL
        assert verdict.stale_count == 1

    def test_fresh_monitoring_at_threshold_passes(self) -> None:
        """Monitoring evidence exactly at 6h threshold → PASS."""
        items = [_make_item(EvidenceDomain.MONITORING, 6)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.PASS


class TestStaleDynamicExit:
    def test_stale_dynamic_exit_fails(self) -> None:
        """Dynamic exit evidence older than 12h → FAIL."""
        items = [_make_item(EvidenceDomain.DYNAMIC_EXIT, 18)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.FAIL
        assert verdict.stale_count == 1

    def test_fresh_dynamic_exit_at_threshold_passes(self) -> None:
        """Dynamic exit evidence exactly at 12h threshold → PASS."""
        items = [_make_item(EvidenceDomain.DYNAMIC_EXIT, 12)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.PASS


# ---------------------------------------------------------------------------
# Mixed fresh and stale
# ---------------------------------------------------------------------------


class TestMixedEvidence:
    def test_mixed_fresh_and_stale_fails(self) -> None:
        """Mix of fresh and stale evidence → FAIL (any stale = fail)."""
        items = [
            _make_item(EvidenceDomain.ACTIVE_CYCLE, 12),   # fresh
            _make_item(EvidenceDomain.MONITORING, 3),       # fresh
            _make_item(EvidenceDomain.DYNAMIC_EXIT, 18),    # stale
        ]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.FAIL
        assert verdict.fresh_count == 2
        assert verdict.stale_count == 1
        assert verdict.total_count == 3

    def test_all_stale_fails(self) -> None:
        """All evidence stale → FAIL."""
        items = [
            _make_item(EvidenceDomain.ACTIVE_CYCLE, 48),
            _make_item(EvidenceDomain.MONITORING, 12),
            _make_item(EvidenceDomain.DYNAMIC_EXIT, 24),
        ]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert verdict.status == StaleEvidenceStatus.FAIL
        assert verdict.stale_count == 3
        assert verdict.fresh_count == 0


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------


class TestCustomThresholds:
    def test_custom_threshold_overrides_default(self) -> None:
        """Custom threshold makes evidence fresh that would be stale with default."""
        # Default monitoring threshold is 6h, so 8h would be stale
        items = [_make_item(EvidenceDomain.MONITORING, 8)]
        # Override to 12h — now 8h is fresh
        verdict = evaluate_stale_evidence(
            items, now=_NOW,
            thresholds={EvidenceDomain.MONITORING: 12},
        )
        assert verdict.status == StaleEvidenceStatus.PASS
        assert verdict.fresh_count == 1

    def test_custom_threshold_makes_fresh_stale(self) -> None:
        """Custom threshold makes evidence stale that would be fresh with default."""
        # Default active_cycle threshold is 24h, so 12h would be fresh
        items = [_make_item(EvidenceDomain.ACTIVE_CYCLE, 12)]
        # Override to 6h — now 12h is stale
        verdict = evaluate_stale_evidence(
            items, now=_NOW,
            thresholds={EvidenceDomain.ACTIVE_CYCLE: 6},
        )
        assert verdict.status == StaleEvidenceStatus.FAIL
        assert verdict.stale_count == 1

    def test_partial_threshold_override(self) -> None:
        """Only override some domains; others use defaults."""
        items = [
            _make_item(EvidenceDomain.ACTIVE_CYCLE, 12),   # default 24h → fresh
            _make_item(EvidenceDomain.MONITORING, 8),       # override to 12h → fresh
        ]
        verdict = evaluate_stale_evidence(
            items, now=_NOW,
            thresholds={EvidenceDomain.MONITORING: 12},
        )
        assert verdict.status == StaleEvidenceStatus.PASS
        assert verdict.fresh_count == 2


# ---------------------------------------------------------------------------
# Per-item result details
# ---------------------------------------------------------------------------


class TestPerItemResults:
    def test_result_contains_age_and_threshold(self) -> None:
        """Each result includes age_hours, threshold_hours, and reason."""
        items = [_make_item(EvidenceDomain.ACTIVE_CYCLE, 30)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        assert len(verdict.results) == 1
        r = verdict.results[0]
        assert r.evidence_id == "active_cycle_30h"
        assert r.domain == EvidenceDomain.ACTIVE_CYCLE
        assert abs(r.age_hours - 30.0) < 0.01
        assert r.threshold_hours == 24
        assert r.is_stale is True
        assert "Stale" in r.reason

    def test_fresh_result_contains_fresh_reason(self) -> None:
        """Fresh evidence result has 'Fresh' in reason."""
        items = [_make_item(EvidenceDomain.MONITORING, 3)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        r = verdict.results[0]
        assert r.is_stale is False
        assert "Fresh" in r.reason


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


class TestIsEvidenceStale:
    def test_stale_returns_true(self) -> None:
        """Evidence older than threshold → True."""
        item = _make_item(EvidenceDomain.MONITORING, 12)
        assert is_evidence_stale(item, now=_NOW) is True

    def test_fresh_returns_false(self) -> None:
        """Evidence within threshold → False."""
        item = _make_item(EvidenceDomain.MONITORING, 3)
        assert is_evidence_stale(item, now=_NOW) is False

    def test_custom_threshold(self) -> None:
        """Custom threshold changes staleness result."""
        item = _make_item(EvidenceDomain.MONITORING, 8)
        # Default: 6h → stale
        assert is_evidence_stale(item, now=_NOW) is True
        # Custom: 12h → fresh
        assert is_evidence_stale(item, now=_NOW, thresholds={EvidenceDomain.MONITORING: 12}) is False


class TestFilterStale:
    def test_returns_only_stale_items(self) -> None:
        """filter_stale returns only items that are stale."""
        items = [
            _make_item(EvidenceDomain.ACTIVE_CYCLE, 12),   # fresh
            _make_item(EvidenceDomain.MONITORING, 8),       # stale
            _make_item(EvidenceDomain.DYNAMIC_EXIT, 6),      # fresh
        ]
        stale = filter_stale(items, now=_NOW)
        assert len(stale) == 1
        assert stale[0].domain == EvidenceDomain.MONITORING

    def test_empty_list_returns_empty(self) -> None:
        """filter_stale on empty list → empty list."""
        assert filter_stale([], now=_NOW) == []

    def test_all_fresh_returns_empty(self) -> None:
        """filter_stale with all fresh → empty list."""
        items = [
            _make_item(EvidenceDomain.ACTIVE_CYCLE, 12),
            _make_item(EvidenceDomain.MONITORING, 3),
        ]
        assert filter_stale(items, now=_NOW) == []


class TestFilterFresh:
    def test_returns_only_fresh_items(self) -> None:
        """filter_fresh returns only items that are not stale."""
        items = [
            _make_item(EvidenceDomain.ACTIVE_CYCLE, 12),   # fresh
            _make_item(EvidenceDomain.MONITORING, 8),       # stale
            _make_item(EvidenceDomain.DYNAMIC_EXIT, 6),      # fresh
        ]
        fresh = filter_fresh(items, now=_NOW)
        assert len(fresh) == 2
        assert all(i.domain != EvidenceDomain.MONITORING for i in fresh)

    def test_empty_list_returns_empty(self) -> None:
        """filter_fresh on empty list → empty list."""
        assert filter_fresh([], now=_NOW) == []

    def test_all_stale_returns_empty(self) -> None:
        """filter_fresh with all stale → empty list."""
        items = [
            _make_item(EvidenceDomain.ACTIVE_CYCLE, 48),
            _make_item(EvidenceDomain.MONITORING, 12),
        ]
        assert filter_fresh(items, now=_NOW) == []


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestToDict:
    def test_empty_verdict(self) -> None:
        """Empty verdict to_dict has correct structure."""
        verdict = evaluate_stale_evidence([], now=_NOW)
        d = verdict.to_dict()
        assert d["status"] == "NOT_APPLICABLE"
        assert d["stale_count"] == 0
        assert d["fresh_count"] == 0
        assert d["total_count"] == 0
        assert d["results"] == []

    def test_pass_verdict(self) -> None:
        """PASS verdict to_dict has correct structure."""
        items = [_make_item(EvidenceDomain.ACTIVE_CYCLE, 12)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        d = verdict.to_dict()
        assert d["status"] == "PASS"
        assert d["stale_count"] == 0
        assert d["fresh_count"] == 1
        assert len(d["results"]) == 1
        assert d["results"][0]["is_stale"] is False

    def test_fail_verdict(self) -> None:
        """FAIL verdict to_dict has correct structure."""
        items = [_make_item(EvidenceDomain.MONITORING, 8)]
        verdict = evaluate_stale_evidence(items, now=_NOW)
        d = verdict.to_dict()
        assert d["status"] == "FAIL"
        assert d["stale_count"] == 1
        assert d["fresh_count"] == 0
        assert len(d["results"]) == 1
        assert d["results"][0]["is_stale"] is True
        assert "age_hours" in d["results"][0]
        assert "threshold_hours" in d["results"][0]


# ---------------------------------------------------------------------------
# Default thresholds contract
# ---------------------------------------------------------------------------


class TestDefaultThresholds:
    def test_all_domains_have_defaults(self) -> None:
        """All EvidenceDomain values have a default threshold."""
        for domain in EvidenceDomain:
            assert domain in DEFAULT_STALENESS_THRESHOLDS, (
                f"Missing default threshold for {domain}"
            )

    def test_thresholds_are_positive(self) -> None:
        """All default thresholds are positive integers."""
        for domain, hours in DEFAULT_STALENESS_THRESHOLDS.items():
            assert isinstance(hours, int), f"{domain}: {hours} is not int"
            assert hours > 0, f"{domain}: {hours} is not positive"

    def test_monitoring_has_lowest_threshold(self) -> None:
        """Monitoring has the lowest threshold (most sensitive)."""
        monitoring = DEFAULT_STALENESS_THRESHOLDS[EvidenceDomain.MONITORING]
        for domain, hours in DEFAULT_STALENESS_THRESHOLDS.items():
            if domain != EvidenceDomain.MONITORING:
                assert monitoring <= hours, (
                    f"Monitoring threshold ({monitoring}h) should be <= "
                    f"{domain} threshold ({hours}h)"
                )
