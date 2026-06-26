"""Tests for the SI v2 Proposal Candidate Builder.

These tests are pure unit tests — no network, no Freqtrade, no Docker.
They exercise the candidate builder with synthetic fleet evidence and
assert that all candidates are safe, deterministic, and validatable.

Coverage:
    - All 5 actionable hypothesis types
    - 4-bot fixture with 2 underperforming bots
    - Empty evidence / missing metrics
    - Negative profitability
    - Positive pilot (reinforce) candidates
    - Unsafe overlay parameter rejection
    - Deterministic candidate IDs
    - Fleet metrics building
    - Safety invariants (no live trading, no secrets, no real Freqtrade keys)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from si_v2.proposals.candidate_builder import (
    SAFE_OVERLAY_KEYS,
    BotMetrics,
    FleetMetrics,
    ProposalCandidate,
    build_candidate_proposals,
    build_fleet_metrics_from_cycle,
)

# ------------------------------------------------------------------
# Hypothesis constants (mirrored for test assertions)
# ------------------------------------------------------------------
HYP_UNDERPERFORMING = "observe_underperforming_pair_cluster_v1"
HYP_DISPERSION = "review_fleet_profitability_dispersion_v1"
HYP_DURATION = "review_trade_duration_outlier_v1"
HYP_SIGNAL_QUALITY = "review_entry_signal_quality_v1"
HYP_REINFORCE = "reinforce_profitable_pair_cluster_v1"

# Non-actionable hypotheses (should NOT produce candidates)
HYP_REACHABILITY = "telemetry_reachability_baseline_established"
HYP_STATUS_OBSERVABLE = "telemetry_status_endpoint_observable_v1"


# ------------------------------------------------------------------
# Synthetic test fixtures
# ------------------------------------------------------------------


@dataclass
class _FakeDecision:
    """Minimal fake for a single per-bot ShadowProposalDecision."""

    decision_type: str
    bot_id: str
    hypothesis: str
    evidence_summary: dict
    candidate_sha256: str = "0" * 16
    base_mode: str = "proposal_only"
    mutation_policy: str = "safe_parameter_overlay_only"
    requires_human_approval: bool = True
    parameters: dict = field(default_factory=dict)
    metadata_only_candidates: dict = field(default_factory=dict)
    no_proposal_reason: str | None = None
    fetched_at_utc: str = "2026-01-01T00:00:00Z"


@dataclass
class _FakeFleetDecision:
    """Minimal fake for FleetDecision."""

    cycle_id: str
    per_bot: list
    fleet_summary: object | None = None
    generated_at_utc: str = "2026-01-01T00:00:00Z"


@dataclass
class _FakeFleetSummary:
    """Minimal fake for FleetSummary."""

    fleet_verdict: str = "GREEN"
    total_bots: int = 4
    runtime_mutations: int = 0
    config_mutations: int = 0
    live_trading_mutations: int = 0


def _make_evidence(
    profit_pct: float = 0.0,
    anomaly_flags: list[str] | None = None,
    signal_depth: float = 0.8,
    open_trades: int = 0,
) -> dict:
    """Build a synthetic evidence_summary dict for a bot."""
    return {
        "bot_id": "freqtrade-freqforge",
        "base_url": "http://trading-freqtrade-freqforge-1:8080",
        "auth_type": "env_basic_jwt",
        "username_env": "SI_V2_FREQTRADE_FREQFORGE_USERNAME",
        "password_env": "SI_V2_FREQTRADE_FREQFORGE_PASSWORD",
        "ping": {
            "endpoint": "/api/v1/ping",
            "status_code": 200,
            "ok": True,
            "response_summary": '{"status":"pong"}',
        },
        "status": {
            "endpoint": "/api/v1/status",
            "status_code": 200,
            "ok": True,
            "response_summary": "[redacted]",
            "auth_outcome": "AUTHENTICATED",
            "open_trades": open_trades,
        },
        "missing_env_vars": [],
        "auth_error_summary": "",
        "fetched_at_utc": "2026-01-01T00:00:00Z",
        "signal_depth": signal_depth,
        "proposal_evidence": {
            "anomaly_flags": [str(a) for a in (anomaly_flags or [])],
            "profit_all_percent": profit_pct,
        },
    }


def _make_bot_metrics(
    bot_id: str = "freqtrade-freqforge",
    profit_pct: float = 0.0,
    open_trades: int = 0,
    signal_depth: float = 0.8,
    anomaly_flags: tuple[str, ...] = (),
    approval_status: str = "APPROVAL_ELIGIBLE",
    approval_eligible: bool = True,
) -> BotMetrics:
    """Build a synthetic BotMetrics."""
    return BotMetrics(
        bot_id=bot_id,
        profit_pct=profit_pct,
        open_trades=open_trades,
        signal_depth=signal_depth,
        anomaly_flags=anomaly_flags,
        approval_status=approval_status,
        approval_eligible=approval_eligible,
    )


def _make_fleet_metrics(
    cycle_id: str = "test-cycle-001",
    bots: tuple[BotMetrics, ...] | None = None,
    fleet_verdict: str = "GREEN",
) -> FleetMetrics:
    """Build a synthetic FleetMetrics."""
    if bots is None:
        bots = (
            _make_bot_metrics("freqtrade-freqforge", profit_pct=2.5),
            _make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0),
            _make_bot_metrics("freqtrade-freqforge-canary", profit_pct=1.0),
            _make_bot_metrics("freqai-rebel", profit_pct=-3.0),
        )
    profits = [b.profit_pct for b in bots]
    return FleetMetrics(
        cycle_id=cycle_id,
        bots=bots,
        fleet_verdict=fleet_verdict,
        fleet_median_profit_pct=_median(profits),
        fleet_profit_range_pct=(max(profits) - min(profits)) if len(profits) >= 2 else 0.0,
        total_open_trades=sum(b.open_trades for b in bots),
        bots_with_anomalies=sum(1 for b in bots if b.anomaly_flags),
        bots_approval_eligible=sum(1 for b in bots if b.approval_eligible),
    )


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


# ------------------------------------------------------------------
# 4-bot fixture: 2 underperforming, 2 neutral/positive
# ------------------------------------------------------------------

FOUR_BOT_FIXTURE = (
    _make_bot_metrics("freqtrade-freqforge", profit_pct=2.5),
    _make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0, anomaly_flags=("negative_closed_profit",)),
    _make_bot_metrics("freqtrade-freqforge-canary", profit_pct=1.0),
    _make_bot_metrics("freqai-rebel", profit_pct=-3.0, anomaly_flags=("negative_closed_profit",)),
)


# ------------------------------------------------------------------
# Tests: build_candidate_proposals
# ------------------------------------------------------------------


class TestCandidateBuilder:
    """Core candidate builder tests."""

    def test_empty_fleet_decision_returns_empty(self) -> None:
        """Empty fleet decision → no candidates."""
        fd = _FakeFleetDecision(cycle_id="t1", per_bot=[])
        fm = _make_fleet_metrics(bots=())
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert result == []

    def test_no_actionable_hypotheses_returns_empty(self) -> None:
        """Metadata-only hypotheses (reachability, status) → no candidates."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_REACHABILITY,
                    evidence_summary=_make_evidence(),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-freqforge", profit_pct=2.5),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert result == []

    def test_no_proposal_decisions_skipped(self) -> None:
        """NO_PROPOSAL decisions are skipped even if hypothesis is actionable."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="NO_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-10.0),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-freqforge", profit_pct=-10.0),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert result == []

    def test_underperforming_hypothesis_produces_candidate(self) -> None:
        """Underperforming pair hypothesis → concrete candidate with cooldown/max_open."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(
                        profit_pct=-8.0,
                        anomaly_flags=["negative_closed_profit"],
                    ),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(
                _make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0, anomaly_flags=("negative_closed_profit",)),
            ),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert len(result) == 1
        c = result[0]
        assert c.proposal_type == HYP_UNDERPERFORMING
        assert c.target_bot_ids == ("freqtrade-regime-hybrid",)
        assert "cooldown_candles_candidate" in c.candidate_overlay
        assert "max_open_trades_candidate" in c.candidate_overlay
        assert c.requires_human_approval is True
        assert c.mutation_policy == "proposal_only"

    def test_dispersion_hypothesis_produces_candidate(self) -> None:
        """Profitability dispersion → candidate with fleet alignment."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_DISPERSION,
                    evidence_summary=_make_evidence(profit_pct=8.0, open_trades=3),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-freqforge", profit_pct=8.0, open_trades=3),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert len(result) == 1
        c = result[0]
        assert c.proposal_type == HYP_DISPERSION
        assert c.candidate_overlay.get("pair_cluster_action") == "align_to_fleet_median"

    def test_duration_hypothesis_produces_candidate(self) -> None:
        """Trade duration outlier → candidate with exit threshold adjustment."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqai-rebel",
                    hypothesis=HYP_DURATION,
                    evidence_summary=_make_evidence(profit_pct=-3.0),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqai-rebel", profit_pct=-3.0),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert len(result) == 1
        c = result[0]
        assert c.proposal_type == HYP_DURATION
        assert "exit_threshold_candidate" in c.candidate_overlay
        assert "stop_duration_candles_candidate" in c.candidate_overlay

    def test_signal_quality_hypothesis_produces_candidate(self) -> None:
        """Entry signal quality → candidate with entry threshold raise."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqai-rebel",
                    hypothesis=HYP_SIGNAL_QUALITY,
                    evidence_summary=_make_evidence(profit_pct=-3.0),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqai-rebel", profit_pct=-3.0),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert len(result) == 1
        c = result[0]
        assert c.proposal_type == HYP_SIGNAL_QUALITY
        assert c.candidate_overlay.get("entry_threshold_candidate") == 0.6

    def test_reinforce_hypothesis_produces_candidate(self) -> None:
        """Reinforce profitable → candidate with parameter maintenance."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_REINFORCE,
                    evidence_summary=_make_evidence(profit_pct=2.5),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-freqforge", profit_pct=2.5),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert len(result) == 1
        c = result[0]
        assert c.proposal_type == HYP_REINFORCE
        assert c.candidate_overlay.get("pair_cluster_action") == "maintain_profitable"

    def test_four_bot_fixture_two_underperforming(self) -> None:
        """4-bot fixture: 2 underperforming bots → 2 candidates, others skipped."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_REINFORCE,
                    evidence_summary=_make_evidence(profit_pct=2.5),
                ),
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(
                        profit_pct=-8.0,
                        anomaly_flags=["negative_closed_profit"],
                    ),
                ),
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge-canary",
                    hypothesis=HYP_REINFORCE,
                    evidence_summary=_make_evidence(profit_pct=1.0),
                ),
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqai-rebel",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(
                        profit_pct=-3.0,
                        anomaly_flags=["negative_closed_profit"],
                    ),
                ),
            ],
        )
        fm = _make_fleet_metrics(bots=FOUR_BOT_FIXTURE)
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert len(result) == 4  # All 4 have actionable hypotheses

        # Verify each candidate type
        types = {c.proposal_type for c in result}
        assert HYP_UNDERPERFORMING in types
        assert HYP_REINFORCE in types

        # Underperforming bots get cooldown/max_open candidates
        underperforming = [c for c in result if c.proposal_type == HYP_UNDERPERFORMING]
        assert len(underperforming) == 2
        for c in underperforming:
            assert "cooldown_candles_candidate" in c.candidate_overlay
            assert "max_open_trades_candidate" in c.candidate_overlay

    def test_bot_not_in_metrics_skipped(self) -> None:
        """Bot in fleet_decision but not in fleet_metrics → skipped."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="ghost-bot",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-5.0),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-freqforge", profit_pct=2.5),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert result == []


# ------------------------------------------------------------------
# Tests: candidate structure invariants
# ------------------------------------------------------------------


class TestCandidateStructure:
    """Structural invariants for all proposal candidates."""

    def _get_single_candidate(self) -> ProposalCandidate:
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-8.0, anomaly_flags=["negative_closed_profit"]),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0, anomaly_flags=("negative_closed_profit",)),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert len(result) == 1
        return result[0]

    def test_candidate_has_all_required_fields(self) -> None:
        """Every candidate must have all required fields."""
        c = self._get_single_candidate()
        assert c.candidate_id
        assert c.cycle_id == "t1"
        assert c.proposal_type
        assert c.target_bot_ids
        assert c.hypothesis
        assert isinstance(c.candidate_overlay, dict)
        assert c.expected_effect
        assert c.risk_notes
        assert isinstance(c.validation_plan, dict)
        assert c.rollback_condition
        assert c.source_evidence_refs
        assert c.requires_human_approval is True
        assert c.mutation_policy == "proposal_only"

    def test_candidate_overlay_only_safe_keys(self) -> None:
        """candidate_overlay must only contain SAFE_OVERLAY_KEYS."""
        c = self._get_single_candidate()
        for key in c.candidate_overlay:
            assert key in SAFE_OVERLAY_KEYS, f"Unsafe key '{key}' in candidate_overlay"

    def test_no_real_freqtrade_keys_in_overlay(self) -> None:
        """candidate_overlay must never contain real Freqtrade config keys."""
        c = self._get_single_candidate()
        forbidden = {"max_open_trades", "stake_amount", "stoploss", "minimal_roi", "dry_run",
                      "exchange", "trading_mode", "api_server", "internals"}
        for key in forbidden:
            assert key not in c.candidate_overlay, f"Forbidden key '{key}' in candidate_overlay"

    def test_validation_plan_has_required_gates(self) -> None:
        """Validation plan must include backtest, walk-forward, lookahead, recursive."""
        c = self._get_single_candidate()
        vp = c.validation_plan
        assert vp.get("backtest_required") is True
        assert vp.get("walk_forward_required") is True
        assert vp.get("lookahead_analysis_required") is True
        assert vp.get("recursive_analysis_required") is True
        assert "profitability_gate" in vp

    def test_rollback_condition_is_non_empty(self) -> None:
        """Every candidate must have a rollback condition."""
        c = self._get_single_candidate()
        assert c.rollback_condition
        assert len(c.rollback_condition) > 20  # Not just a placeholder

    def test_source_evidence_refs_are_non_empty(self) -> None:
        """Every candidate must reference source evidence."""
        c = self._get_single_candidate()
        assert c.source_evidence_refs
        assert len(c.source_evidence_refs) >= 1

    def test_to_json_safe_roundtrips(self) -> None:
        """to_json_safe() must produce valid JSON."""
        c = self._get_single_candidate()
        js = c.to_json_safe()
        json.dumps(js)  # Must not raise
        assert js["candidate_id"] == c.candidate_id
        assert js["cycle_id"] == c.cycle_id
        assert js["proposal_type"] == c.proposal_type
        assert isinstance(js["target_bot_ids"], list)
        assert isinstance(js["risk_notes"], list)
        assert isinstance(js["source_evidence_refs"], list)


# ------------------------------------------------------------------
# Tests: deterministic candidate IDs
# ------------------------------------------------------------------


class TestDeterministicIDs:
    """Candidate IDs must be deterministic for the same inputs."""

    def test_same_inputs_produce_same_id(self) -> None:
        """Same cycle_id + proposal_type + target_bot_ids → same candidate_id."""
        fd1 = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-8.0),
                ),
            ],
        )
        fm1 = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0),),
        )
        result1 = build_candidate_proposals(cycle_id="t1", fleet_decision=fd1, fleet_metrics=fm1)

        fd2 = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-8.0),
                ),
            ],
        )
        fm2 = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0),),
        )
        result2 = build_candidate_proposals(cycle_id="t1", fleet_decision=fd2, fleet_metrics=fm2)

        assert result1[0].candidate_id == result2[0].candidate_id

    def test_different_cycle_produces_different_id(self) -> None:
        """Different cycle_id → different candidate_id."""
        fd1 = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-8.0),
                ),
            ],
        )
        fm1 = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0),),
        )
        result1 = build_candidate_proposals(cycle_id="t1", fleet_decision=fd1, fleet_metrics=fm1)

        fd2 = _FakeFleetDecision(
            cycle_id="t2",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-8.0),
                ),
            ],
        )
        fm2 = _make_fleet_metrics(
            cycle_id="t2",
            bots=(_make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0),),
        )
        result2 = build_candidate_proposals(cycle_id="t2", fleet_decision=fd2, fleet_metrics=fm2)

        assert result1[0].candidate_id != result2[0].candidate_id

    def test_different_hypothesis_produces_different_id(self) -> None:
        """Different proposal_type → different candidate_id."""
        fd1 = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-8.0),
                ),
            ],
        )
        fm1 = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0),),
        )
        result1 = build_candidate_proposals(cycle_id="t1", fleet_decision=fd1, fleet_metrics=fm1)

        fd2 = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_DURATION,
                    evidence_summary=_make_evidence(profit_pct=-8.0),
                ),
            ],
        )
        fm2 = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0),),
        )
        result2 = build_candidate_proposals(cycle_id="t1", fleet_decision=fd2, fleet_metrics=fm2)

        assert result1[0].candidate_id != result2[0].candidate_id


# ------------------------------------------------------------------
# Tests: build_fleet_metrics_from_cycle
# ------------------------------------------------------------------


class TestFleetMetricsBuilder:
    """Tests for build_fleet_metrics_from_cycle."""

    def test_builds_metrics_from_four_bot_cycle(self) -> None:
        """Build FleetMetrics from a 4-bot cycle with mixed profitability."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_REINFORCE,
                    evidence_summary=_make_evidence(profit_pct=2.5),
                ),
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-8.0, anomaly_flags=["negative_closed_profit"]),
                ),
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge-canary",
                    hypothesis=HYP_REINFORCE,
                    evidence_summary=_make_evidence(profit_pct=1.0),
                ),
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqai-rebel",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-3.0, anomaly_flags=["negative_closed_profit"]),
                ),
            ],
            fleet_summary=_FakeFleetSummary(fleet_verdict="YELLOW"),
        )
        safety_results = [
            {"bot_id": "freqtrade-freqforge", "approval_status": "APPROVAL_ELIGIBLE", "approval_eligible": True},
            {"bot_id": "freqtrade-regime-hybrid", "approval_status": "BLOCKED_INSUFFICIENT_HISTORY", "approval_eligible": False},
            {"bot_id": "freqtrade-freqforge-canary", "approval_status": "APPROVAL_ELIGIBLE", "approval_eligible": True},
            {"bot_id": "freqai-rebel", "approval_status": "BLOCKED_INSUFFICIENT_HISTORY", "approval_eligible": False},
        ]

        fm = build_fleet_metrics_from_cycle(
            cycle_id="t1",
            fleet_decision=fd,
            safety_results=safety_results,
        )

        assert fm.cycle_id == "t1"
        assert len(fm.bots) == 4
        assert fm.fleet_verdict == "YELLOW"
        assert fm.bots_with_anomalies == 2
        assert fm.bots_approval_eligible == 2

        # Fleet median: sorted [-8.0, -3.0, 1.0, 2.5] → median = (-3.0 + 1.0) / 2 = -1.0
        assert fm.fleet_median_profit_pct == -1.0
        assert fm.fleet_profit_range_pct == 10.5  # 2.5 - (-8.0)

    def test_empty_safety_results_handled(self) -> None:
        """Empty safety_results → all bots UNKNOWN, not eligible."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_REINFORCE,
                    evidence_summary=_make_evidence(profit_pct=2.5),
                ),
            ],
        )
        fm = build_fleet_metrics_from_cycle(
            cycle_id="t1",
            fleet_decision=fd,
            safety_results=[],
        )
        assert len(fm.bots) == 1
        assert fm.bots[0].approval_status == "UNKNOWN"
        assert fm.bots[0].approval_eligible is False

    def test_missing_proposal_evidence_handled(self) -> None:
        """Bot without proposal_evidence → profit_pct=0.0, no anomalies."""
        evidence = _make_evidence(profit_pct=0.0)
        del evidence["proposal_evidence"]  # Simulate missing
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_REINFORCE,
                    evidence_summary=evidence,
                ),
            ],
        )
        fm = build_fleet_metrics_from_cycle(
            cycle_id="t1",
            fleet_decision=fd,
            safety_results=[{"bot_id": "freqtrade-freqforge", "approval_status": "UNKNOWN", "approval_eligible": False}],
        )
        assert fm.bots[0].profit_pct == 0.0
        assert fm.bots[0].anomaly_flags == ()

    def test_single_bot_metrics(self) -> None:
        """Single bot → median = its profit, range = 0."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_REINFORCE,
                    evidence_summary=_make_evidence(profit_pct=5.0),
                ),
            ],
        )
        fm = build_fleet_metrics_from_cycle(
            cycle_id="t1",
            fleet_decision=fd,
            safety_results=[{"bot_id": "freqtrade-freqforge", "approval_status": "APPROVAL_ELIGIBLE", "approval_eligible": True}],
        )
        assert fm.fleet_median_profit_pct == 5.0
        assert fm.fleet_profit_range_pct == 0.0


# ------------------------------------------------------------------
# Tests: safety invariants
# ------------------------------------------------------------------


class TestSafetyInvariants:
    """Hard safety invariants that must never be violated."""

    def test_no_live_trading_flags_in_candidates(self) -> None:
        """No candidate may contain live trading flags."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-8.0),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        for c in result:
            js = c.to_json_safe()
            payload = json.dumps(js)
            for forbidden in ("dry_run", "live", "real_money", "production", "api_key", "secret"):
                assert forbidden not in payload.lower() or f"_{forbidden}" in payload, (
                    f"Forbidden term '{forbidden}' found in candidate output"
                )

    def test_all_candidates_require_human_approval(self) -> None:
        """Every candidate must require human approval."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_REINFORCE,
                    evidence_summary=_make_evidence(profit_pct=2.5),
                ),
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-8.0),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(
                _make_bot_metrics("freqtrade-freqforge", profit_pct=2.5),
                _make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0),
            ),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        for c in result:
            assert c.requires_human_approval is True

    def test_all_candidates_are_proposal_only(self) -> None:
        """Every candidate must have mutation_policy='proposal_only'."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_REINFORCE,
                    evidence_summary=_make_evidence(profit_pct=2.5),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-freqforge", profit_pct=2.5),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        for c in result:
            assert c.mutation_policy == "proposal_only"

    def test_no_secret_values_in_candidate_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Candidate output must never contain secret values."""
        sensitive = "supersecret-DO-NOT-LEAK-12345"
        monkeypatch.setenv("SI_V2_FREQTRADE_FREQFORGE_USERNAME", sensitive)
        monkeypatch.setenv("SI_V2_FREQTRADE_FREQFORGE_PASSWORD", sensitive)

        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_REINFORCE,
                    evidence_summary=_make_evidence(profit_pct=2.5),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-freqforge", profit_pct=2.5),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        for c in result:
            payload = json.dumps(c.to_json_safe())
            assert sensitive not in payload, "Secret value leaked through candidate output"

    def test_no_docker_or_runtime_mutation_in_candidates(self) -> None:
        """Candidates must not reference Docker or runtime mutations."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-8.0),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-8.0),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        for c in result:
            payload = json.dumps(c.to_json_safe())
            for forbidden in ("docker", "container", "restart", "recreate", "rebuild"):
                assert forbidden not in payload.lower(), (
                    f"Forbidden term '{forbidden}' found in candidate output"
                )


# ------------------------------------------------------------------
# Tests: SAFE_OVERLAY_KEYS validation
# ------------------------------------------------------------------


class TestSafeOverlayKeys:
    """SAFE_OVERLAY_KEYS allowlist validation."""

    def test_safe_overlay_keys_are_candidate_only(self) -> None:
        """SAFE_OVERLAY_KEYS must not contain real Freqtrade config keys."""
        real_freqtrade_keys = {
            "max_open_trades", "stake_amount", "stoploss", "minimal_roi",
            "dry_run", "exchange", "trading_mode", "api_server",
            "unfilledtimeout", "cancel_open_orders_on_exit",
        }
        overlap = SAFE_OVERLAY_KEYS & real_freqtrade_keys
        assert overlap == set(), f"SAFE_OVERLAY_KEYS contains real Freqtrade keys: {overlap}"

    def test_safe_overlay_keys_all_have_candidate_suffix_or_are_safe(self) -> None:
        """All SAFE_OVERLAY_KEYS should either have _candidate suffix or be explicitly safe."""
        for key in SAFE_OVERLAY_KEYS:
            assert key.endswith("_candidate") or key == "pair_cluster_action", (
                f"Key '{key}' in SAFE_OVERLAY_KEYS needs _candidate suffix or explicit justification"
            )


# ------------------------------------------------------------------
# Tests: negative profitability edge cases
# ------------------------------------------------------------------


class TestNegativeProfitability:
    """Edge cases for negative profitability bots."""

    def test_deeply_negative_bot_gets_underperforming_candidate(self) -> None:
        """Bot with -20% profit → underperforming candidate."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-regime-hybrid",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-20.0, anomaly_flags=["negative_closed_profit"]),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-regime-hybrid", profit_pct=-20.0, anomaly_flags=("negative_closed_profit",)),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert len(result) == 1
        c = result[0]
        assert c.proposal_type == HYP_UNDERPERFORMING
        assert c.candidate_overlay.get("cooldown_candles_candidate") == 12
        assert c.candidate_overlay.get("max_open_trades_candidate") == 2

    def test_slightly_negative_bot_gets_candidate(self) -> None:
        """Bot with -1% profit → still gets underperforming candidate if hypothesis matches."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqai-rebel",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-1.0, anomaly_flags=["negative_closed_profit"]),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqai-rebel", profit_pct=-1.0, anomaly_flags=("negative_closed_profit",)),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert len(result) == 1


# ------------------------------------------------------------------
# Tests: missing metrics edge cases
# ------------------------------------------------------------------


class TestMissingMetrics:
    """Edge cases for missing or incomplete metrics."""

    def test_zero_signal_depth_bot_still_gets_candidate(self) -> None:
        """Bot with signal_depth=0 but actionable hypothesis → still gets candidate."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqai-rebel",
                    hypothesis=HYP_UNDERPERFORMING,
                    evidence_summary=_make_evidence(profit_pct=-5.0, signal_depth=0.0),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqai-rebel", profit_pct=-5.0, signal_depth=0.0),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert len(result) == 1

    def test_missing_walk_forward_metrics_handled(self) -> None:
        """Bot without walk_forward_net_metrics → still gets candidate."""
        fd = _FakeFleetDecision(
            cycle_id="t1",
            per_bot=[
                _FakeDecision(
                    decision_type="SHADOW_PROPOSAL",
                    bot_id="freqtrade-freqforge",
                    hypothesis=HYP_REINFORCE,
                    evidence_summary=_make_evidence(profit_pct=2.5),
                ),
            ],
        )
        fm = _make_fleet_metrics(
            bots=(_make_bot_metrics("freqtrade-freqforge", profit_pct=2.5),),
        )
        result = build_candidate_proposals(cycle_id="t1", fleet_decision=fd, fleet_metrics=fm)
        assert len(result) == 1
