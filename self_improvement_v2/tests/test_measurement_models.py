"""Tests for SI v2 Measurement models.

Ensures BotMeasurementPoint, FleetMeasurementPoint, ProposalTrackingRecord
are typed, JSON-safe, and behave deterministically.
"""

from __future__ import annotations

from si_v2.measurement.models import (
    AttributionStatus,
    AttributionWindow,
    BotMeasurementPoint,
    FleetMeasurementPoint,
    MeasurementStatus,
    ProposalTrackingRecord,
)


class TestMeasurementStatus:
    def test_values(self) -> None:
        assert MeasurementStatus.BASELINE_ONLY.value == "BASELINE_ONLY"
        assert MeasurementStatus.PENDING_APPLICATION.value == "PENDING_APPLICATION"
        assert MeasurementStatus.INSUFFICIENT_HISTORY.value == "INSUFFICIENT_HISTORY"


class TestAttributionStatus:
    def test_values(self) -> None:
        assert AttributionStatus.PENDING_APPLICATION.value == "PENDING_APPLICATION"
        assert AttributionStatus.INSUFFICIENT_HISTORY.value == "INSUFFICIENT_HISTORY"


class TestBotMeasurementPoint:
    def test_minimal(self) -> None:
        bp = BotMeasurementPoint(
            cycle_id="20260613T165509Z",
            cycle_timestamp="2026-06-13T16:55:09",
            bot_id="test-bot",
            fleet_verdict="GREEN",
            decision_type="NO_PROPOSAL",
            hypothesis="no_action_insufficient_evidence_v1",
            approval_status="PENDING_HUMAN",
            candidate_sha256="",
            signal_depth=0.0,
            ping_ok=True,
            auth_ok=True,
            status_ok=True,
            open_trade_count=None,
            count_current=None,
            count_max=None,
            profit_all_percent=None,
            profit_all_ratio=None,
            daily_trade_count=None,
            whitelist_pair_count=None,
            runtime_mutations=0,
            config_mutations=0,
            live_trading_mutations=0,
            docker_mutations=0,
            strategy_mutations=0,
            controller_state="PAUSED / L3_REPOSITORY_ONLY",
            measurement_status="BASELINE_ONLY",
            source_artifact="reports/phase2/cycle_state/test.state.json",
        )
        assert bp.bot_id == "test-bot"
        assert bp.measurement_status == "BASELINE_ONLY"
        assert bp.signal_depth == 0.0

    def test_rich_point(self) -> None:
        bp = BotMeasurementPoint(
            cycle_id="20260613T165509Z",
            cycle_timestamp="2026-06-13T16:55:09",
            bot_id="test-bot",
            fleet_verdict="GREEN",
            decision_type="SHADOW_PROPOSAL",
            hypothesis="telemetry_status_endpoint_observable_v1",
            approval_status="PENDING_HUMAN",
            candidate_sha256="abc123",
            signal_depth=1.0,
            ping_ok=True,
            auth_ok=True,
            status_ok=True,
            open_trade_count=2,
            count_current=2,
            count_max=5,
            profit_all_percent=2.5,
            profit_all_ratio=0.025,
            daily_trade_count=7,
            whitelist_pair_count=3,
            runtime_mutations=0,
            config_mutations=0,
            live_trading_mutations=0,
            docker_mutations=0,
            strategy_mutations=0,
            controller_state="PAUSED / L3_REPOSITORY_ONLY",
            measurement_status="PENDING_APPLICATION",
            source_artifact="reports/phase2/cycle_state/test.state.json",
        )
        assert bp.decision_type == "SHADOW_PROPOSAL"
        assert bp.profit_all_percent == 2.5
        assert bp.candidate_sha256 == "abc123"

    def test_to_json_safe(self) -> None:
        bp = BotMeasurementPoint(
            cycle_id="test",
            cycle_timestamp="2026-01-01",
            bot_id="bot-1",
            fleet_verdict="GREEN",
            decision_type="NO_PROPOSAL",
            hypothesis="",
            approval_status="PENDING_HUMAN",
            candidate_sha256="",
            signal_depth=0.75,
            ping_ok=True,
            auth_ok=True,
            status_ok=True,
            open_trade_count=0,
            count_current=None,
            count_max=None,
            profit_all_percent=1.5,
            profit_all_ratio=0.015,
            daily_trade_count=None,
            whitelist_pair_count=None,
            runtime_mutations=0,
            config_mutations=0,
            live_trading_mutations=0,
            docker_mutations=0,
            strategy_mutations=0,
            controller_state="PAUSED / L3_REPOSITORY_ONLY",
            measurement_status="BASELINE_ONLY",
            source_artifact="test.json",
        )
        js = bp.to_json_safe()
        assert isinstance(js, dict)
        assert js["bot_id"] == "bot-1"
        assert js["signal_depth"] == 0.75
        assert js["profit_all_percent"] == 1.5


class TestFleetMeasurementPoint:
    def test_basic(self) -> None:
        fp = FleetMeasurementPoint(
            cycle_id="test",
            cycle_timestamp="2026-01-01",
            fleet_verdict="GREEN",
            total_bots=4,
            ping_ok_count=4,
            ping_failed_count=0,
            shadow_proposal_count=4,
            no_proposal_count=0,
            mean_signal_depth=1.0,
            mean_profit_all_percent=2.5,
            total_open_trades=3,
            runtime_mutations=0,
            config_mutations=0,
            live_trading_mutations=0,
            docker_mutations=0,
            strategy_mutations=0,
            controller_state="PAUSED / L3_REPOSITORY_ONLY",
            measurement_status="BASELINE_ONLY",
            source_artifact="test.json",
        )
        assert fp.fleet_verdict == "GREEN"
        assert fp.mean_signal_depth == 1.0

    def test_to_json_safe(self) -> None:
        fp = FleetMeasurementPoint(
            cycle_id="test",
            cycle_timestamp="2026-01-01",
            fleet_verdict="GREEN",
            total_bots=4,
            ping_ok_count=4,
            ping_failed_count=0,
            shadow_proposal_count=0,
            no_proposal_count=4,
            mean_signal_depth=0.0,
            mean_profit_all_percent=None,
            total_open_trades=None,
            runtime_mutations=0,
            config_mutations=0,
            live_trading_mutations=0,
            docker_mutations=0,
            strategy_mutations=0,
            controller_state="PAUSED / L3_REPOSITORY_ONLY",
            measurement_status="BASELINE_ONLY",
            source_artifact="test.json",
        )
        js = fp.to_json_safe()
        assert js["mean_profit_all_percent"] is None


class TestProposalTrackingRecord:
    def test_basic(self) -> None:
        rec = ProposalTrackingRecord(
            proposal_id="abc123",
            bot_id="test-bot",
            hypothesis="telemetry_status_endpoint_observable_v1",
            first_cycle_id="c1",
            first_cycle_timestamp="2026-01-01",
            latest_cycle_id="c3",
            latest_cycle_timestamp="2026-01-03",
            decision_count=3,
            last_decision_type="SHADOW_PROPOSAL",
            last_approval_status="PENDING_HUMAN",
            applied=False,
            attribution_status="PENDING_APPLICATION",
            attribution_cycles=("c1", "c2", "c3"),
        )
        assert rec.proposal_id == "abc123"
        assert rec.decision_count == 3
        assert rec.applied is False


class TestAttributionWindow:
    def test_pending(self) -> None:
        w = AttributionWindow(
            proposal_id="abc123",
            bot_id="test-bot",
            hypothesis="test_hyp",
            pre_cycle_count=0,
            post_cycle_count=0,
            pre_mean_signal_depth=None,
            post_mean_signal_depth=None,
            pre_mean_profit_pct=None,
            post_mean_profit_pct=None,
            pre_trade_count_avg=None,
            post_trade_count_avg=None,
            pre_cycles=(),
            post_cycles=(),
            attribution_status="PENDING_APPLICATION",
        )
        assert w.attribution_status == "PENDING_APPLICATION"
