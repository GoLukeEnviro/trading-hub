from __future__ import annotations

from si_v2.rainbow.client import RainbowClientConfig, RainbowSignalProviderClient


def _payload(asset: str) -> dict[str, object]:
    return {
        "signal_id": "signal-1",
        "timestamp": "2026-07-10T12:00:00Z",
        "source": "ta_1h",
        "asset": asset,
        "signal_type": "technical",
        "direction": "bullish",
        "strength": 0.8,
        "confidence": 0.8,
        "value": 60_000.0,
        "raw_data": {"exchange_response": "must-not-persist"},
        "metadata": {"canonical_symbol": "BTC/USDT:USDT", "timeframe": "1h"},
    }


def test_read_only_client_prefers_upstream_canonical_symbol_and_redacts_raw_data() -> None:
    client = RainbowSignalProviderClient(RainbowClientConfig(enabled=True, mode="read_only"))

    envelope, errors = client._map_crypto_signal_to_envelope(_payload("BTC"))

    assert errors == []
    assert envelope is not None
    assert envelope["symbol"] == "BTC/USDT:USDT"
    assert envelope["redaction_status"] == "unchecked"
    assert "raw_data" not in envelope["metadata"]


def test_read_only_client_rejects_unknown_upstream_symbol() -> None:
    client = RainbowSignalProviderClient(RainbowClientConfig(enabled=True, mode="read_only"))
    payload = _payload("DOGE")
    payload["metadata"] = {}

    envelope, errors = client._map_crypto_signal_to_envelope(payload)

    assert envelope is None
    assert errors == ["unknown canonical symbol"]
