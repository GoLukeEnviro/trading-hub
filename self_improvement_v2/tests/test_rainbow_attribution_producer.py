"""Tests for the Rainbow signal-to-trade attribution producer.

Verifies that:
- valid signal + closed trade produces AttributionInput
- no signal for pair skips the trade
- stale signal (outside max_age) skips the trade
- missing required trade fields produce errors
- direction-to-regime mapping works
- multiple signals pick the freshest
- contribution weight sums to 1.0
- no fake/default credit when no valid signal exists
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from si_v2.attribution.models import RegimeLabel
from si_v2.rainbow.attribution_producer import (
    RainbowAttributionProducer,
    RainbowAttributionProducerConfig,
)


def _signal(
    symbol: str = "BTC/USDT:USDT",
    direction: str = "long",
    confidence: float = 0.85,
    source_id: str = "rainbow:ta",
    strategy_id: str = "rainbow_v1",
    timestamp_utc: str | None = None,
) -> dict[str, object]:
    if timestamp_utc is None:
        timestamp_utc = datetime.now(UTC).isoformat()
    return {
        "event_type": "signal",
        "schema_version": 1,
        "source_system": "rainbow",
        "source_id": source_id,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "timestamp_utc": timestamp_utc,
        "direction": direction,
        "confidence": confidence,
        "signal_strength": 0.72,
        "metadata": {},
        "redaction_status": "clean",
    }


def _trade(
    trade_id: str = "T001",
    pair: str = "BTC/USDT:USDT",
    close_time: str | None = None,
    realized_return: float = 0.05,
    timeframe: str = "1h",
) -> dict[str, object]:
    if close_time is None:
        close_time = datetime.now(UTC).isoformat()
    return {
        "trade_id": trade_id,
        "pair": pair,
        "close_time": close_time,
        "realized_return": realized_return,
        "timeframe": timeframe,
    }


class TestRainbowAttributionProducer:
    def test_valid_signal_produces_attribution(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        producer = RainbowAttributionProducer()
        signals = [_signal(timestamp_utc=(now - timedelta(minutes=30)).isoformat())]
        trades = [_trade(close_time=now.isoformat())]

        result = producer.produce(signals, trades, now=now)

        assert result.matched_count == 1
        assert len(result.inputs) == 1
        assert result.inputs[0].trade_id == "T001"
        assert result.inputs[0].pair == "BTC/USDT:USDT"
        assert result.inputs[0].signal_contributions[0].source_id == "rainbow:ta"
        assert result.inputs[0].signal_contributions[0].contribution_weight == 1.0
        assert result.inputs[0].regime == RegimeLabel.BULLISH

    def test_no_signal_for_pair_skips_trade(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        producer = RainbowAttributionProducer()
        signals = [_signal(symbol="ETH/USDT:USDT")]
        trades = [_trade(pair="BTC/USDT:USDT", close_time=now.isoformat())]

        result = producer.produce(signals, trades, now=now)

        assert result.matched_count == 0
        assert len(result.inputs) == 0
        assert "T001" in result.skipped_trades

    def test_stale_signal_skipped(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        config = RainbowAttributionProducerConfig(max_signal_age_seconds=3600.0)
        producer = RainbowAttributionProducer(config=config)
        # Signal is 2 hours old — outside the 1-hour window
        stale_ts = (now - timedelta(hours=2)).isoformat()
        signals = [_signal(timestamp_utc=stale_ts)]
        trades = [_trade(close_time=now.isoformat())]

        result = producer.produce(signals, trades, now=now)

        assert result.matched_count == 0
        assert "T001" in result.skipped_trades

    def test_fresh_signal_within_window_accepted(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        config = RainbowAttributionProducerConfig(max_signal_age_seconds=3600.0)
        producer = RainbowAttributionProducer(config=config)
        # Signal is 30 minutes old — within the 1-hour window
        fresh_ts = (now - timedelta(minutes=30)).isoformat()
        signals = [_signal(timestamp_utc=fresh_ts)]
        trades = [_trade(close_time=now.isoformat())]

        result = producer.produce(signals, trades, now=now)

        assert result.matched_count == 1
        assert len(result.inputs) == 1

    def test_missing_trade_fields_produce_errors(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        producer = RainbowAttributionProducer()
        signals = [_signal()]
        trades = [{"trade_id": "", "pair": "BTC/USDT:USDT", "close_time": now.isoformat(), "realized_return": 0.05}]

        result = producer.produce(signals, trades, now=now)

        assert result.matched_count == 0
        assert len(result.errors) > 0

    def test_direction_to_regime_mapping(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        producer = RainbowAttributionProducer()
        ts = (now - timedelta(minutes=30)).isoformat()

        # long → BULLISH
        signals = [_signal(direction="long", timestamp_utc=ts)]
        trades = [_trade(close_time=now.isoformat())]
        result = producer.produce(signals, trades, now=now)
        assert result.inputs[0].regime == RegimeLabel.BULLISH

        # short → BEARISH
        signals = [_signal(direction="short", timestamp_utc=ts)]
        result = producer.produce(signals, trades, now=now)
        assert result.inputs[0].regime == RegimeLabel.BEARISH

        # flat → NEUTRAL
        signals = [_signal(direction="flat", timestamp_utc=ts)]
        result = producer.produce(signals, trades, now=now)
        assert result.inputs[0].regime == RegimeLabel.NEUTRAL

        # no_signal → NEUTRAL
        signals = [_signal(direction="no_signal", timestamp_utc=ts)]
        result = producer.produce(signals, trades, now=now)
        assert result.inputs[0].regime == RegimeLabel.NEUTRAL

        # unknown → UNKNOWN
        signals = [_signal(direction="super_bullish", timestamp_utc=ts)]
        result = producer.produce(signals, trades, now=now)
        assert result.inputs[0].regime == RegimeLabel.UNKNOWN

    def test_multiple_signals_picks_freshest(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        producer = RainbowAttributionProducer()
        signals = [
            _signal(timestamp_utc=(now - timedelta(minutes=50)).isoformat(), source_id="rainbow:ta"),
            _signal(timestamp_utc=(now - timedelta(minutes=10)).isoformat(), source_id="rainbow:llm"),
        ]
        trades = [_trade(close_time=now.isoformat())]

        result = producer.produce(signals, trades, now=now)

        assert result.matched_count == 1
        # Should pick the freshest signal (rainbow:llm)
        assert result.inputs[0].signal_contributions[0].source_id == "rainbow:llm"

    def test_no_fake_credit_without_signal(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        producer = RainbowAttributionProducer()
        trades = [_trade(close_time=now.isoformat())]

        result = producer.produce([], trades, now=now)

        assert result.matched_count == 0
        assert len(result.inputs) == 0
        assert "T001" in result.skipped_trades

    def test_contribution_weight_sums_to_one(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        producer = RainbowAttributionProducer()
        signals = [_signal(timestamp_utc=(now - timedelta(minutes=30)).isoformat())]
        trades = [_trade(close_time=now.isoformat())]

        result = producer.produce(signals, trades, now=now)

        for inp in result.inputs:
            total = sum(sc.contribution_weight for sc in inp.signal_contributions)
            assert abs(total - 1.0) < 1e-9, (
                f"Contribution weights must sum to 1.0, got {total}"
            )

    def test_multiple_trades_matched(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        producer = RainbowAttributionProducer()
        signals = [
            _signal(symbol="BTC/USDT:USDT", timestamp_utc=(now - timedelta(minutes=30)).isoformat()),
            _signal(symbol="ETH/USDT:USDT", timestamp_utc=(now - timedelta(minutes=20)).isoformat()),
        ]
        trades = [
            _trade(trade_id="T001", pair="BTC/USDT:USDT", close_time=now.isoformat()),
            _trade(trade_id="T002", pair="ETH/USDT:USDT", close_time=now.isoformat()),
        ]

        result = producer.produce(signals, trades, now=now)

        assert result.matched_count == 2
        assert len(result.inputs) == 2
        trade_ids = {inp.trade_id for inp in result.inputs}
        assert trade_ids == {"T001", "T002"}
