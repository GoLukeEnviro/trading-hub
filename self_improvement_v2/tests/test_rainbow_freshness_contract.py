from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest

from si_v2.loop import active_cycle_runner
from si_v2.loop.cycle_state import build_cycle_state
from si_v2.loop.fleet_analyzer import BotEvidence, analyze_fleet
from si_v2.rainbow.client import RainbowClientResult


BOT_IDS = [
    "freqtrade-freqforge",
    "freqtrade-regime-hybrid",
    "freqtrade-freqforge-canary",
    "freqai-rebel",
]


def _green_evidence() -> list[BotEvidence]:
    now_iso = datetime.now(UTC).isoformat()
    items: list[BotEvidence] = []
    for bot_id in BOT_IDS:
        items.append(
            BotEvidence(
                bot_id=bot_id,
                base_url=f"http://{bot_id}:8080",
                auth_type="env_basic_jwt",
                username_env=f"SI_V2_FREQTRADE_{bot_id.upper().replace('-', '_')}_USERNAME",
                password_env=f"SI_V2_FREQTRADE_{bot_id.upper().replace('-', '_')}_PASSWORD",
                ping_endpoint="/api/v1/ping",
                ping_status_code=200,
                ping_ok=True,
                ping_response_summary="{}",
                status_endpoint="/api/v1/status",
                status_status_code=200,
                status_ok=True,
                status_response_summary="[]",
                status_auth_outcome="AUTHENTICATED",
                status_open_trades=0,
                missing_env_vars=(),
                auth_error_summary="",
                fetched_at_utc=now_iso,
            )
        )
    return items


def _fake_client(signal_timestamp: str) -> object:
    result = RainbowClientResult(
        signals=[
            {
                "symbol": "BTC/USDT",
                "direction": "BUY",
                "confidence": 0.91,
                "timestamp_utc": signal_timestamp,
            }
        ],
        errors=[],
        source="read_only",
        count=1,
    )

    class _Client:
        def get_latest_signals(self) -> RainbowClientResult:
            return result

    return _Client()


class TestRainbowFreshnessContract:
    @pytest.mark.parametrize("age_seconds,expected_fresh", [(60, True), (3600, False)])
    def test_read_only_rainbow_freshness_round_trip(
        self,
        monkeypatch: pytest.MonkeyPatch,
        age_seconds: int,
        expected_fresh: bool,
    ) -> None:
        timestamp = (datetime.now(UTC) - timedelta(seconds=age_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
        monkeypatch.setenv("SI_V2_RAINBOW_ENABLED", "true")
        monkeypatch.setenv("SI_V2_RAINBOW_MODE", "read_only")
        monkeypatch.setenv("SI_V2_RAINBOW_BASE_URL", "http://127.0.0.1:9999")
        monkeypatch.setenv("SI_V2_RAINBOW_TIMEOUT_SECONDS", "1")
        monkeypatch.setattr(
            "si_v2.rainbow.client.RainbowSignalProviderClient.from_config",
            lambda config: _fake_client(timestamp),
        )

        rainbow = active_cycle_runner._load_rainbow_signals()
        assert rainbow["status"] == "SUCCESS"
        assert rainbow["source"] == "read_only"
        assert rainbow["count"] == 1
        assert rainbow["fresh"] is expected_fresh
        assert rainbow["freshness_max_seconds"] == 900
        assert isinstance(rainbow["freshness_seconds"], int)
        if expected_fresh:
            assert rainbow["freshness_seconds"] is not None and rainbow["freshness_seconds"] <= 120
        else:
            assert rainbow["freshness_seconds"] is not None and rainbow["freshness_seconds"] >= 3500

        decision = analyze_fleet(_green_evidence(), cycle_id="rainbow-freshness")
        state = build_cycle_state(
            cycle_id="rainbow-freshness",
            branch="test/phase2-critical-coverage-hardening",
            commit_sha="a" * 64,
            fleet_decision=decision,
            per_bot_decisions_raw=[asdict(d) for d in decision.per_bot],
            external_signals={"rainbow": rainbow},
        )
        assert state.external_signals["rainbow"]["fresh"] is expected_fresh
        assert state.external_signals["rainbow"]["source"] == "read_only"
