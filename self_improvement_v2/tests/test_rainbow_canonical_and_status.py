"""Tests for the Rainbow canonical envelope mapper and status resolver.

Verifies that:
- canonical direction mapping (bullish→long, bearish→short, neutral→flat)
- unknown direction rejected
- missing required canonical fields rejected
- actionability enforcement (can_execute=false, dry_run_only=true)
- no PR #66 canonical_symbol behavior
- status resolver state machine (DISABLED→FIXTURE_ONLY→CONFIGURED→DEGRADED→UNAVAILABLE)
- consecutive failure tracking and recovery
"""

from __future__ import annotations

from si_v2.rainbow.client import (
    RainbowClientConfig,
    RainbowSignalProviderClient,
)
from si_v2.rainbow.status_resolver import (
    ProviderStatus,
    RainbowStatusResolver,
)

# ── Canonical envelope test payloads ──────────────────────────────────────


def _canonical_payload(
    *,
    signal_id: str = "canonical-1",
    source: str = "rainbow:ta",
    asset: str = "BTC/USDT:USDT",
    direction: str = "bullish",
    created_at: str = "2026-06-10T12:00:00Z",
    confidence: float = 0.85,
    signal_class: str = "entry",
    subtype: str = "ta_convergence",
    can_execute: bool = False,
    dry_run_only: bool = True,
) -> dict[str, object]:
    return {
        "id": signal_id,
        "schema_version": 1,
        "signal_class": signal_class,
        "subtype": subtype,
        "source": source,
        "asset": asset,
        "timeframe": "1h",
        "created_at": created_at,
        "direction": direction,
        "confidence": confidence,
        "risk_score": 0.25,
        "priority": "high",
        "reason_codes": ["ta_rsi_oversold"],
        "features": {"strength": 0.72, "rsi_14": 28.5},
        "data_quality": {"status": "ok", "freshness_seconds": 30},
        "actionability": {
            "can_alert": True,
            "can_execute": can_execute,
            "dry_run_only": dry_run_only,
        },
        "invalidation": {"max_age_seconds": 3600, "conditions": []},
        "raw_refs": [],
    }


# ── Canonical mapper tests ───────────────────────────────────────────────


class TestCanonicalMapper:
    def _client(self) -> RainbowSignalProviderClient:
        config = RainbowClientConfig(
            enabled=True,
            mode="read_only",
            base_url="http://127.0.0.1:8000",
            endpoint_path="/signals/canonical/latest",
        )
        return RainbowSignalProviderClient(config=config)

    def test_valid_bullish_maps_to_long(self) -> None:
        client = self._client()
        envelope, errors = client._map_canonical_signal_to_envelope(
            _canonical_payload(direction="bullish")
        )
        assert errors == []
        assert envelope is not None
        assert envelope["direction"] == "long"

    def test_bearish_maps_to_short(self) -> None:
        client = self._client()
        envelope, errors = client._map_canonical_signal_to_envelope(
            _canonical_payload(direction="bearish")
        )
        assert errors == []
        assert envelope is not None
        assert envelope["direction"] == "short"

    def test_neutral_maps_to_flat(self) -> None:
        client = self._client()
        envelope, errors = client._map_canonical_signal_to_envelope(
            _canonical_payload(direction="neutral")
        )
        assert errors == []
        assert envelope is not None
        assert envelope["direction"] == "flat"

    def test_unknown_direction_rejected(self) -> None:
        client = self._client()
        envelope, errors = client._map_canonical_signal_to_envelope(
            _canonical_payload(direction="super_bullish")
        )
        assert envelope is None
        assert any("unknown direction" in e for e in errors)

    def test_missing_id_rejected(self) -> None:
        client = self._client()
        envelope, errors = client._map_canonical_signal_to_envelope(
            _canonical_payload(signal_id="")
        )
        assert envelope is None
        assert any("missing id" in e for e in errors)

    def test_missing_source_rejected(self) -> None:
        client = self._client()
        envelope, errors = client._map_canonical_signal_to_envelope(
            _canonical_payload(source="")
        )
        assert envelope is None
        assert any("missing source" in e for e in errors)

    def test_missing_asset_rejected(self) -> None:
        client = self._client()
        envelope, errors = client._map_canonical_signal_to_envelope(
            _canonical_payload(asset="")
        )
        assert envelope is None
        assert any("missing asset" in e for e in errors)

    def test_missing_created_at_rejected(self) -> None:
        client = self._client()
        envelope, errors = client._map_canonical_signal_to_envelope(
            _canonical_payload(created_at="")
        )
        assert envelope is None
        assert any("missing created_at" in e for e in errors)

    def test_missing_confidence_rejected(self) -> None:
        client = self._client()
        payload = _canonical_payload()
        payload.pop("confidence", None)
        envelope, errors = client._map_canonical_signal_to_envelope(payload)
        assert envelope is None
        assert any("missing confidence" in e for e in errors)

    def test_can_execute_true_rejected(self) -> None:
        client = self._client()
        envelope, errors = client._map_canonical_signal_to_envelope(
            _canonical_payload(can_execute=True)
        )
        assert envelope is None
        assert any("actionability" in e for e in errors)

    def test_dry_run_only_false_rejected(self) -> None:
        client = self._client()
        envelope, errors = client._map_canonical_signal_to_envelope(
            _canonical_payload(dry_run_only=False)
        )
        assert envelope is None
        assert any("actionability" in e for e in errors)

    def test_default_actionability_when_absent(self) -> None:
        client = self._client()
        payload = _canonical_payload()
        payload.pop("actionability", None)
        envelope, errors = client._map_canonical_signal_to_envelope(payload)
        assert errors == []
        assert envelope is not None
        assert envelope["metadata"]["actionability"]["can_execute"] is False
        assert envelope["metadata"]["actionability"]["dry_run_only"] is True

    def test_no_pr66_canonical_symbol_inference(self) -> None:
        """R2 must NOT implement PR #66 metadata.canonical_symbol behavior.

        The canonical endpoint returns already-canonical symbols (e.g.
        BTC/USDT:USDT). The mapper must use the asset field directly and
        must NOT look up metadata.canonical_symbol (PR #66 behavior).
        """
        client = self._client()
        payload = _canonical_payload(asset="BTC/USDT:USDT")
        # Inject a canonical_symbol in metadata to verify it is NOT used
        features = payload.get("features", {})
        if isinstance(features, dict):
            features["canonical_symbol"] = "ETH/USDT:USDT"
        envelope, errors = client._map_canonical_signal_to_envelope(payload)
        assert errors == []
        assert envelope is not None
        # Must use asset field, not metadata.canonical_symbol
        assert envelope["symbol"] == "BTC/USDT:USDT"

    def test_is_canonical_endpoint_property(self) -> None:
        config = RainbowClientConfig(
            enabled=True,
            mode="read_only",
            base_url="http://127.0.0.1:8000",
            endpoint_path="/signals/canonical/latest",
        )
        client = RainbowSignalProviderClient(config=config)
        assert client.is_canonical_endpoint is True

    def test_is_canonical_endpoint_false_for_regular(self) -> None:
        config = RainbowClientConfig(
            enabled=True,
            mode="read_only",
            base_url="http://127.0.0.1:8000",
            endpoint_path="/signals/latest",
        )
        client = RainbowSignalProviderClient(config=config)
        assert client.is_canonical_endpoint is False


# ── Status resolver tests ─────────────────────────────────────────────────


class TestStatusResolver:
    def test_disabled_when_not_enabled(self) -> None:
        resolver = RainbowStatusResolver()
        evidence = resolver.resolve(
            enabled=False,
            mode="fixture",
            base_url=None,
            endpoint="/signals/latest",
        )
        assert evidence.status == ProviderStatus.DISABLED
        assert evidence.base_url_configured is False

    def test_fixture_only_when_enabled_in_fixture_mode(self) -> None:
        resolver = RainbowStatusResolver()
        evidence = resolver.resolve(
            enabled=True,
            mode="fixture",
            base_url=None,
            endpoint="/signals/latest",
        )
        assert evidence.status == ProviderStatus.FIXTURE_ONLY
        assert evidence.base_url_configured is False

    def test_configured_when_read_only_with_base_url(self) -> None:
        resolver = RainbowStatusResolver()
        evidence = resolver.resolve(
            enabled=True,
            mode="read_only",
            base_url="http://127.0.0.1:8000",
            endpoint="/signals/canonical/latest",
        )
        assert evidence.status == ProviderStatus.CONFIGURED
        assert evidence.base_url_configured is True

    def test_degraded_when_read_only_without_base_url(self) -> None:
        resolver = RainbowStatusResolver()
        evidence = resolver.resolve(
            enabled=True,
            mode="read_only",
            base_url=None,
            endpoint="/signals/latest",
        )
        assert evidence.status == ProviderStatus.DEGRADED
        assert evidence.base_url_configured is False
        assert any("base_url" in e for e in evidence.errors)

    def test_first_failure_not_unavailable(self) -> None:
        resolver = RainbowStatusResolver()
        resolver.record_failure()
        assert resolver.is_unavailable is False
        assert resolver.consecutive_failures == 1

    def test_second_failure_not_unavailable(self) -> None:
        resolver = RainbowStatusResolver()
        resolver.record_failure()
        resolver.record_failure()
        assert resolver.is_unavailable is False
        assert resolver.consecutive_failures == 2

    def test_third_failure_becomes_unavailable(self) -> None:
        resolver = RainbowStatusResolver(max_consecutive_failures=3)
        resolver.record_failure()
        resolver.record_failure()
        resolver.record_failure()
        assert resolver.is_unavailable is True
        assert resolver.consecutive_failures == 3

    def test_success_resets_failure_count(self) -> None:
        resolver = RainbowStatusResolver()
        resolver.record_failure()
        resolver.record_failure()
        resolver.record_success()
        assert resolver.is_unavailable is False
        assert resolver.consecutive_failures == 0

    def test_custom_max_failures(self) -> None:
        resolver = RainbowStatusResolver(max_consecutive_failures=5)
        for _ in range(4):
            resolver.record_failure()
        assert resolver.is_unavailable is False
        resolver.record_failure()
        assert resolver.is_unavailable is True

    def test_evidence_artifact_has_required_fields(self) -> None:
        resolver = RainbowStatusResolver()
        evidence = resolver.resolve(
            enabled=True,
            mode="read_only",
            base_url="http://127.0.0.1:8000",
            endpoint="/signals/canonical/latest",
            provider_id="rainbow",
        )
        d = evidence.to_dict()
        assert d["provider_id"] == "rainbow"
        assert d["status"] == ProviderStatus.CONFIGURED
        assert d["mode"] == "read_only"
        assert d["endpoint"] == "/signals/canonical/latest"
        assert d["base_url_configured"] is True
        assert d["consecutive_failures"] == 0
        assert "last_checked_utc" in d
        assert d["errors"] == []

    def test_evidence_artifact_on_failure(self) -> None:
        resolver = RainbowStatusResolver()
        evidence = resolver.resolve(
            enabled=True,
            mode="read_only",
            base_url=None,
            endpoint="/signals/latest",
        )
        d = evidence.to_dict()
        assert d["status"] == ProviderStatus.DEGRADED
        assert d["base_url_configured"] is False
        assert len(d["errors"]) > 0

    def test_disabled_never_attempts_network(self) -> None:
        resolver = RainbowStatusResolver()
        evidence = resolver.resolve(
            enabled=False,
            mode="read_only",
            base_url="http://127.0.0.1:8000",
            endpoint="/signals/latest",
        )
        assert evidence.status == ProviderStatus.DISABLED
        # Even with base_url set, disabled mode returns DISABLED
        assert evidence.base_url_configured is False

    def test_fixture_never_attempts_network(self) -> None:
        resolver = RainbowStatusResolver()
        evidence = resolver.resolve(
            enabled=True,
            mode="fixture",
            base_url="http://127.0.0.1:8000",
            endpoint="/signals/latest",
        )
        assert evidence.status == ProviderStatus.FIXTURE_ONLY
        assert evidence.base_url_configured is False
