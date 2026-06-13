"""Tests for SI v2 signal models.

Ensures BotSignalSnapshot, FleetSignalSnapshot, ProposalEvidenceSummary
are typed, JSON-safe, and behave deterministically.
"""

from __future__ import annotations

from si_v2.signals.models import (
    BotSignalSnapshot,
    FleetSignalSnapshot,
    ProposalEvidenceSummary,
    SignalAvailability,
    SignalQuality,
)


class TestSignalAvailability:
    """SignalAvailability dataclass behaviour."""

    def test_available(self) -> None:
        a = SignalAvailability(endpoint="/api/v1/ping", available=True, http_code=200)
        assert a.available is True
        assert a.http_code == 200

    def test_unavailable(self) -> None:
        a = SignalAvailability(
            endpoint="/api/v1/profit",
            available=False,
            http_code=0,
            error_summary="connection error",
        )
        assert a.available is False
        assert "error" in a.error_summary


class TestSignalQuality:
    """SignalQuality completeness calculation."""

    def test_perfect(self) -> None:
        q = SignalQuality(total_endpoints=8, available_count=8, completeness_score=1.0)
        assert q.completeness_score == 1.0
        assert q.raw_secrets_detected is False

    def test_partial(self) -> None:
        q = SignalQuality(total_endpoints=8, available_count=4, completeness_score=0.5)
        assert q.completeness_score == 0.5

    def test_zero(self) -> None:
        q = SignalQuality(total_endpoints=0, available_count=0, completeness_score=0.0)
        assert q.completeness_score == 0.0


class TestBotSignalSnapshot:
    """BotSignalSnapshot dataclass behaviour."""

    def test_minimal(self) -> None:
        snap = BotSignalSnapshot(
            bot_id="test-bot",
            cycle_id="20260613T120000Z",
            ping_ok=True,
            ping_status_code=200,
            auth_outcome="AUTHENTICATED",
            status_ok=True,
            status_open_trades=2,
            status_response_summary="[]",
        )
        assert snap.bot_id == "test-bot"
        assert snap.ping_ok
        assert snap.signal_depth == 0.0

    def test_rich_snapshot(self) -> None:
        q = SignalQuality(total_endpoints=8, available_count=8, completeness_score=1.0)
        snap = BotSignalSnapshot(
            bot_id="test-bot",
            cycle_id="20260613T120000Z",
            ping_ok=True,
            ping_status_code=200,
            auth_outcome="AUTHENTICATED",
            status_ok=True,
            status_open_trades=1,
            status_response_summary="[{\"pair\": \"BTC/USDT\"}]",
            count_current=1,
            count_max=5,
            count_total_stake=44.7,
            profit_closed_percent=2.3,
            profit_all_percent=2.3,
            profit_all_ratio=0.023,
            performance_pair_count=12,
            performance_top_pair="SOL/USDT:USDT",
            performance_top_pair_profit_pct=1.27,
            daily_trade_count_total=7,
            daily_abs_profit_sum=22.0,
            daily_abs_profit_latest=3.5,
            whitelist_pair_count=3,
            whitelist_method="StaticPairList",
            bot_version="2026.3",
            availability=(
                SignalAvailability(endpoint="/api/v1/ping", available=True, http_code=200),
                SignalAvailability(endpoint="/api/v1/status", available=True, http_code=200),
            ),
            signal_quality=q,
        )
        assert snap.signal_depth == 1.0
        assert snap.profit_all_percent == 2.3
        assert snap.performance_top_pair == "SOL/USDT:USDT"

    def test_to_json_safe(self) -> None:
        snap = BotSignalSnapshot(
            bot_id="test-bot",
            cycle_id="20260613T120000Z",
            ping_ok=True,
            ping_status_code=200,
            auth_outcome="AUTHENTICATED",
            status_ok=True,
            status_open_trades=0,
            status_response_summary="{}",
        )
        safe = snap.to_json_safe()
        assert isinstance(safe, dict)
        assert safe["bot_id"] == "test-bot"
        assert safe["signal_depth"] == 0.0


class TestFleetSignalSnapshot:
    """FleetSignalSnapshot dataclass behaviour."""

    def test_empty(self) -> None:
        fleet = FleetSignalSnapshot(cycle_id="test", total_bots=0)
        assert fleet.total_bots == 0
        assert fleet.fleet_signal_depth == 0.0
        assert fleet.has_rich_signals is False

    def test_with_bots(self) -> None:
        snap1 = BotSignalSnapshot(
            bot_id="bot-1", cycle_id="test",
            ping_ok=True, ping_status_code=200,
            auth_outcome="AUTHENTICATED",
            status_ok=True, status_open_trades=0, status_response_summary="{}",
            signal_quality=SignalQuality(
                total_endpoints=8, available_count=7, completeness_score=0.875,
            ),
        )
        snap2 = BotSignalSnapshot(
            bot_id="bot-2", cycle_id="test",
            ping_ok=True, ping_status_code=200,
            auth_outcome="AUTHENTICATED",
            status_ok=True, status_open_trades=0, status_response_summary="{}",
            signal_quality=SignalQuality(
                total_endpoints=8, available_count=3, completeness_score=0.375,
            ),
        )
        fleet = FleetSignalSnapshot(
            cycle_id="test", total_bots=2,
            bot_snapshots=(snap1, snap2),
            fleet_signal_depth=0.625,
            all_bots_reachable=True,
            all_bots_authenticated=True,
        )
        assert fleet.has_rich_signals is True  # snap1 has depth >= 0.5


class TestProposalEvidenceSummary:
    """ProposalEvidenceSummary behaviour."""

    def test_is_sufficient(self) -> None:
        ev = ProposalEvidenceSummary(
            bot_id="test",
            ping_ok=True,
            auth_outcome="AUTHENTICATED",
            status_open_trades=1,
            signal_count_available=3,  # ping + status + 1+ additional
            signal_count_total=8,
            signal_depth=0.375,
        )
        assert ev.is_sufficient() is True

    def test_is_insufficient(self) -> None:
        ev = ProposalEvidenceSummary(
            bot_id="test",
            ping_ok=True,
            auth_outcome="AUTHENTICATED",
            status_open_trades=0,
            signal_count_available=1,  # only ping available
            signal_count_total=8,
            signal_depth=0.125,
        )
        assert ev.is_sufficient() is False  # needs >=2 endpoints

    def test_no_ping(self) -> None:
        ev = ProposalEvidenceSummary(
            bot_id="test",
            ping_ok=False,
            auth_outcome="FAILED",
            status_open_trades=0,
            signal_count_available=0,
            signal_count_total=8,
        )
        assert ev.is_sufficient() is False

    def test_to_json_safe(self) -> None:
        ev = ProposalEvidenceSummary(
            bot_id="test",
            ping_ok=True,
            auth_outcome="AUTHENTICATED",
            status_open_trades=1,
            open_trade_pairs=("BTC/USDT",),
            signal_depth=0.75,
            anomaly_flags=("negative_closed_profit",),
        )
        safe = ev.to_json_safe()
        assert isinstance(safe, dict)
        assert safe["bot_id"] == "test"
        assert "anomaly_flags" in safe
        assert safe["signal_depth"] == 0.75
