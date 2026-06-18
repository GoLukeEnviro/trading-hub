"""Tests for SI v2 Freqtrade signal fusion.

Tests that signal collection produces deterministic snapshots,
optional endpoints degrade gracefully, and fleet analysis works.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from si_v2.adapters.freqtrade_rest_readonly import (
    ALLOWED_GET_ENDPOINTS,
    ALLOWED_POST_ENDPOINTS,
)
from si_v2.signals.freqtrade_signals import _SIGNAL_ENDPOINTS, collect_bot_signals
from si_v2.signals.fusion import build_proposal_evidence, fuse_signals
from si_v2.signals.models import (
    BotSignalSnapshot,
    ProposalEvidenceSummary,
    SignalAvailability,
    SignalQuality,
)


def test_signal_collection_uses_readonly_allowlisted_endpoints_only() -> None:
    """Drawdown wiring must not add mutating Freqtrade endpoints."""
    assert set(_SIGNAL_ENDPOINTS).issubset(ALLOWED_GET_ENDPOINTS)
    assert "/api/v1/profit" in _SIGNAL_ENDPOINTS
    assert frozenset({"/api/v1/token/login"}) == ALLOWED_POST_ENDPOINTS
    forbidden_mutating_fragments = ("/force", "/buy", "/sell", "/cancel", "/trade")
    assert not any(
        fragment in endpoint
        for endpoint in _SIGNAL_ENDPOINTS
        for fragment in forbidden_mutating_fragments
    )


class TestCollectBotSignals:
    """collect_bot_signals with mocked connector."""

    def make_mock_connector(self, available_eps: set[str]) -> MagicMock:
        """Create a mock connector where only specified endpoints return 200."""
        connector = MagicMock()
        connector.auth_enabled = True
        connector.authenticated = True

        def fetch_side_effect(endpoint: str):
            mock_snap = MagicMock()
            mock_snap.response_json = None
            if endpoint in available_eps:
                mock_snap.ok = True
                mock_snap.status_code = 200
                if endpoint == "/api/v1/ping":
                    mock_snap.response_summary = '{"status": "pong"}'
                elif endpoint == "/api/v1/status":
                    mock_snap.response_summary = json.dumps([
                        {"pair": "BTC/USDT", "profit_ratio": 0.01}
                    ])
                elif endpoint == "/api/v1/count":
                    mock_snap.response_summary = json.dumps(
                        {"current": 1, "max": 5, "total_stake": 44.7}
                    )
                elif endpoint == "/api/v1/profit":
                    mock_snap.response_summary = json.dumps(
                        {"profit_closed_percent": 2.3, "profit_all_percent": 1.5,
                         "profit_all_ratio": 0.015, "profit_closed_coin": 22.0,
                         "profit_all_coin": 21.8, "closed_trade_count": 9,
                         "profit_factor": 1.7, "max_drawdown": 0.0825,
                         "bot_start_date": "2026-01-01"}
                    )
                elif endpoint == "/api/v1/performance":
                    mock_snap.response_summary = json.dumps([
                        {"pair": "SOL/USDT", "profit_pct": 1.27, "count": 11},
                        {"pair": "ETH/USDT", "profit_pct": 1.32, "count": 7},
                    ])
                elif endpoint == "/api/v1/daily":
                    mock_snap.response_summary = json.dumps({
                        "data": [
                            {"date": "2026-06-13", "abs_profit": 3.5, "trade_count": 4},
                            {"date": "2026-06-12", "abs_profit": 2.1, "trade_count": 3},
                        ]
                    })
                elif endpoint == "/api/v1/whitelist":
                    mock_snap.response_summary = json.dumps({
                        "whitelist": ["BTC/USDT", "ETH/USDT"],
                        "method": "StaticPairList",
                        "length": 2,
                    })
                elif endpoint == "/api/v1/version":
                    mock_snap.response_summary = '{"version": "2026.3"}'
            else:
                mock_snap.ok = False
                mock_snap.status_code = 0
                mock_snap.response_summary = "error"
            return mock_snap

        connector.fetch_snapshot.side_effect = fetch_side_effect
        return connector

    def test_all_endpoints_available(self) -> None:
        connector = self.make_mock_connector({
            "/api/v1/ping", "/api/v1/status", "/api/v1/count",
            "/api/v1/profit", "/api/v1/performance", "/api/v1/daily",
            "/api/v1/whitelist", "/api/v1/version",
        })
        snap = collect_bot_signals(connector, "test-bot", "test-cycle")
        assert snap.ping_ok is True
        assert snap.auth_outcome == "AUTHENTICATED"
        assert snap.signal_depth == 1.0
        assert snap.profit_closed_percent == 2.3
        assert snap.num_trades == 9
        assert snap.profit_factor == 1.7
        assert abs((snap.max_drawdown_pct or 0.0) - 8.25) < 1e-9
        assert snap.performance_top_pair == "ETH/USDT"  # ETH has higher profit_pct (1.32 > 1.27)
        assert snap.whitelist_pair_count == 2

    def test_profit_response_json_drawdown_survives_truncated_summary(self) -> None:
        """Parsed response_json is the real source for /profit drawdown fields."""
        connector = self.make_mock_connector({
            "/api/v1/ping", "/api/v1/status", "/api/v1/count",
            "/api/v1/profit",
        })

        def fetch_side_effect(endpoint: str):
            mock_snap = MagicMock()
            mock_snap.ok = True
            mock_snap.status_code = 200
            mock_snap.response_json = None
            mock_snap.response_summary = "{}"
            if endpoint == "/api/v1/profit":
                mock_snap.response_summary = '{"profit_closed_coin": 125.0, ... [truncated]'
                mock_snap.response_json = {
                    "profit_closed_coin": 125.0,
                    "profit_closed_percent": 3.0,
                    "profit_all_coin": 130.0,
                    "profit_all_percent": 3.2,
                    "profit_all_ratio": 0.032,
                    "closed_trade_count": 12,
                    "profit_factor": 2.1,
                    "max_drawdown": 0.045,
                    "bot_start_date": "2026-01-01",
                }
            return mock_snap

        connector.fetch_snapshot.side_effect = fetch_side_effect
        snap = collect_bot_signals(connector, "test-bot", "test-cycle")

        assert snap.num_trades == 12
        assert snap.profit_closed_coin == 125.0
        assert snap.profit_factor == 2.1
        assert snap.max_drawdown_pct == 4.5

    def test_only_ping_and_status(self) -> None:
        connector = self.make_mock_connector({"/api/v1/ping", "/api/v1/status"})
        snap = collect_bot_signals(connector, "test-bot", "test-cycle")
        assert snap.ping_ok is True
        assert snap.signal_depth == 0.25  # 2/8
        assert snap.profit_closed_percent == 0.0  # not available

    def test_no_endpoints(self) -> None:
        connector = self.make_mock_connector(set())
        snap = collect_bot_signals(connector, "test-bot", "test-cycle")
        assert snap.ping_ok is False
        assert snap.signal_depth == 0.0

    def test_signal_quality_metrics(self) -> None:
        connector = self.make_mock_connector({
            "/api/v1/ping", "/api/v1/status", "/api/v1/count", "/api/v1/profit",
        })
        snap = collect_bot_signals(connector, "test-bot", "test-cycle")
        q = snap.signal_quality
        assert q is not None
        assert q.total_endpoints == 8
        assert q.available_count == 4
        assert q.completeness_score == 0.5

    def test_to_json_safe_no_secrets(self) -> None:
        connector = self.make_mock_connector({
            "/api/v1/ping", "/api/v1/status", "/api/v1/count",
        })
        snap = collect_bot_signals(connector, "test-bot", "test-cycle")
        safe = snap.to_json_safe()
        text = json.dumps(safe)
        assert "password" not in text.lower()
        assert "secret" not in text.lower()
        assert "access_token" not in text.lower()

    def test_to_json_safe_preserves_missing_drawdown_as_null(self) -> None:
        """Missing max_drawdown_pct must serialize as None, never 0.0."""
        connector = self.make_mock_connector({"/api/v1/ping", "/api/v1/status"})
        snap = collect_bot_signals(connector, "test-bot", "test-cycle")
        safe = snap.to_json_safe()

        assert "max_drawdown_pct" in safe
        assert safe["max_drawdown_pct"] is None
        assert safe["max_drawdown_pct"] != 0.0


class TestBuildProposalEvidence:
    """build_proposal_evidence from BotSignalSnapshot."""

    def make_snap(self, depth: float = 0.75, profit_pct: float = 2.3) -> BotSignalSnapshot:
        q = SignalQuality(
            total_endpoints=8, available_count=int(depth * 8),
            completeness_score=depth,
        )
        return BotSignalSnapshot(
            bot_id="test-bot",
            cycle_id="test",
            ping_ok=True,
            ping_status_code=200,
            auth_outcome="AUTHENTICATED",
            status_ok=True,
            status_open_trades=2,
            status_response_summary=json.dumps([
                {"pair": "BTC/USDT", "profit_ratio": 0.01},
                {"pair": "ETH/USDT", "profit_ratio": 0.02},
            ]),
            count_current=2,
            profit_closed_percent=profit_pct,
            profit_all_percent=profit_pct,
            performance_top_pair="SOL/USDT",
            daily_trade_count_total=7,
            availability=(
                SignalAvailability(endpoint="/api/v1/ping", available=True, http_code=200),
                SignalAvailability(endpoint="/api/v1/status", available=True, http_code=200),
            ),
            signal_quality=q,
        )

    def test_basic_evidence(self) -> None:
        ev = build_proposal_evidence(self.make_snap())
        assert isinstance(ev, ProposalEvidenceSummary)
        assert ev.bot_id == "test-bot"
        assert ev.signal_depth > 0.5
        assert ev.ping_ok is True

    def test_open_trade_pairs_from_status(self) -> None:
        ev = build_proposal_evidence(self.make_snap())
        assert "BTC/USDT" in ev.open_trade_pairs

    def test_no_anomalies_normal_profit(self) -> None:
        ev = build_proposal_evidence(self.make_snap(profit_pct=2.3))
        assert "negative_closed_profit" not in ev.anomaly_flags

    def test_anomaly_negative_profit(self) -> None:
        ev = build_proposal_evidence(self.make_snap(profit_pct=-15.0))
        assert "profit_below_-10%" in ev.anomaly_flags

    def test_to_json_safe(self) -> None:
        ev = build_proposal_evidence(self.make_snap())
        js = ev.to_json_safe()
        assert isinstance(js, dict)
        assert "anomaly_flags" in js
        assert "signal_depth" in js


class TestFuseSignals:
    """fuse_signals fleet-level aggregation."""

    def test_empty(self) -> None:
        fleet = fuse_signals([], "test")
        assert fleet.total_bots == 0
        assert fleet.has_rich_signals is False

    def test_single_bot(self) -> None:
        q = SignalQuality(total_endpoints=8, available_count=6, completeness_score=0.75)
        snap = BotSignalSnapshot(
            bot_id="bot-1", cycle_id="test",
            ping_ok=True, ping_status_code=200,
            auth_outcome="AUTHENTICATED",
            status_ok=True, status_open_trades=1, status_response_summary="{}",
            signal_quality=q,
        )
        fleet = fuse_signals([snap], "test")
        assert fleet.total_bots == 1
        assert fleet.all_bots_reachable is True
        assert fleet.has_rich_signals is True
        assert fleet.fleet_signal_depth == 0.75

    def test_mixed_reachability(self) -> None:
        snap1 = BotSignalSnapshot(
            bot_id="bot-1", cycle_id="test",
            ping_ok=True, ping_status_code=200,
            auth_outcome="AUTHENTICATED",
            status_ok=True, status_open_trades=0, status_response_summary="{}",
        )
        snap2 = BotSignalSnapshot(
            bot_id="bot-2", cycle_id="test",
            ping_ok=False, ping_status_code=0,
            auth_outcome="FAILED",
            status_ok=False, status_open_trades=0, status_response_summary="{}",
        )
        fleet = fuse_signals([snap1, snap2], "test")
        assert fleet.all_bots_reachable is False

    def test_profit_anomaly_detection(self) -> None:
        snap1 = BotSignalSnapshot(
            bot_id="bot-1", cycle_id="test",
            ping_ok=True, ping_status_code=200,
            auth_outcome="AUTHENTICATED",
            status_ok=True, status_open_trades=0, status_response_summary="{}",
            profit_all_percent=5.0,
            profit_closed_percent=4.0,
        )
        snap2 = BotSignalSnapshot(
            bot_id="bot-2", cycle_id="test",
            ping_ok=True, ping_status_code=200,
            auth_outcome="AUTHENTICATED",
            status_ok=True, status_open_trades=0, status_response_summary="{}",
            profit_all_percent=-3.0,
            profit_closed_percent=-4.0,
        )
        fleet = fuse_signals([snap1, snap2], "test")
        # spread = 8% > 5% threshold
        assert fleet.any_profit_anomaly is True
