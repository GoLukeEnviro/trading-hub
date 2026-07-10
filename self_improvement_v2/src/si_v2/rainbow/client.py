"""Read-only Rainbow Signal Provider Client.

Provides fixture-based and strictly read-only HTTP access to Rainbow signal
payloads. The client is **disabled by default** and requires explicit opt-in.

Safety boundaries:
- No trading decisions.
- No Shadowlock writes.
- Fixture mode makes no network calls.
- Read-only mode uses HTTP GET only.
- No secrets or auth headers are used.
- Returns validator-compatible envelopes only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from si_v2.rainbow.symbol_normalizer import normalize_symbol

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]
Envelope = dict[str, object]


# ── Configuration ─────────────────────────────────────────────────────────────


@dataclass
class RainbowClientConfig:
    """Configuration for RainbowSignalProviderClient.

    The default configuration is **disabled** — all access returns empty.
    """

    enabled: bool = False
    """Master switch. When ``False``, all client calls return empty."""

    mode: str = "fixture"
    """Operation mode: ``fixture``, ``disabled``, or ``read_only``."""

    fixture_path: str | None = None
    """Path to fixture directory. Required in ``fixture`` mode."""

    provider_id: str = "rainbow"
    """Provider identifier for source tracking."""

    max_records: int | None = None
    """Optional limit on returned signals. ``None`` = no limit."""

    timeout_seconds: int = 30
    """Timeout for read-only provider calls."""

    base_url: str | None = None
    """Base URL for the read-only provider, e.g. ``http://127.0.0.1:8000``."""

    endpoint_path: str = "/signals/latest"
    """Path appended to ``base_url`` for read-only signal fetches."""

    canonical_endpoint_path: str = "/signals/canonical/latest"
    """Path for the upstream canonical envelope endpoint."""

    source_type: str = "http"
    """Allowed source type. v1 only supports ``http``."""


# ── Result ────────────────────────────────────────────────────────────────────


@dataclass
class RainbowClientResult:
    """Result from a Rainbow client call."""

    signals: list[Envelope]
    """Validated signal envelopes."""

    errors: list[str] = field(default_factory=list)
    """Non-fatal errors encountered during loading/validation."""

    source: str = "fixture"
    """Source of the signals: ``fixture``, ``read_only``, or ``empty``."""

    count: int = 0
    """Number of valid signals returned."""


# ── Client ────────────────────────────────────────────────────────────────────


class RainbowSignalProviderClient:
    """Read-only Rainbow Signal Provider Client."""

    def __init__(
        self,
        config: RainbowClientConfig | None = None,
    ) -> None:
        self._config = config or RainbowClientConfig()
        self._fixtures: list[Envelope] = []

    @classmethod
    def from_config(cls, config: RainbowClientConfig) -> RainbowSignalProviderClient:
        """Create a client from configuration."""
        client = cls(config=config)

        if not config.enabled:
            return client

        if config.mode == "fixture":
            fixture_path = config.fixture_path
            if fixture_path:
                client.load_from_fixture_path(Path(fixture_path))

        return client

    def load_from_fixture_path(self, path: Path) -> RainbowClientResult:
        """Load all JSON fixtures from a directory."""
        if not self._config.enabled:
            return RainbowClientResult(
                signals=[],
                errors=["Client is disabled"],
                source="empty",
            )

        errors: list[str] = []
        signals: list[Envelope] = []

        if not path.exists():
            return RainbowClientResult(
                signals=[],
                errors=[f"Fixture path not found: {path}"],
                source="empty",
            )

        fixture_files = sorted(path.glob("*.json"))
        if not fixture_files:
            return RainbowClientResult(
                signals=[],
                errors=[f"No JSON fixtures found in {path}"],
                source="empty",
            )

        for fixture_path in fixture_files:
            envelope = self._load_fixture(fixture_path)
            if envelope is None:
                errors.append(f"Failed to load {fixture_path.name}")
                continue

            result = self._validate_envelope(envelope)
            if result is None:
                signals.append(envelope)
                continue

            if "error" in result:
                errors.append(f"{fixture_path.name}: {result['error']}")
                continue

            if result.get("verdict") == "fail":
                validation_errors = result.get("errors", [])
                error_count = len(validation_errors) if isinstance(validation_errors, list) else 0
                errors.append(
                    f"{fixture_path.name}: validation FAILED ({error_count} errors)"
                )
                continue

            signals.append(envelope)

        self._fixtures = signals
        return RainbowClientResult(
            signals=signals,
            errors=errors,
            source="fixture",
            count=len(signals),
        )

    def get_latest_signals(self) -> RainbowClientResult:
        """Return the latest signals for the configured mode."""
        if not self._config.enabled:
            return RainbowClientResult(
                signals=[],
                errors=["Client is disabled"],
                source="empty",
            )

        if self._config.mode == "fixture":
            signals = self._apply_max_records(self._fixtures)
            return RainbowClientResult(
                signals=signals,
                source="fixture" if self._fixtures else "empty",
                count=len(signals),
            )

        if self._config.mode == "read_only":
            return self._get_latest_read_only_signals()

        return RainbowClientResult(
            signals=[],
            errors=[f"Unsupported mode: {self._config.mode}"],
            source="empty",
        )

    def validate_signals(self) -> list[Envelope]:
        """Run the validator on all loaded fixture signals."""
        results: list[Envelope] = []
        for signal in self._fixtures:
            result = self._validate_envelope(signal)
            if result is not None:
                results.append(result)
        return results

    @property
    def is_canonical_endpoint(self) -> bool:
        """True when the configured endpoint is the canonical envelope endpoint."""
        return self._config.endpoint_path == self._config.canonical_endpoint_path

    def _get_latest_read_only_signals(self) -> RainbowClientResult:
        if self._config.source_type != "http":
            return RainbowClientResult(
                signals=[],
                errors=[
                    "Unsupported read_only source_type: "
                    f"{self._config.source_type}"
                ],
                source="empty",
            )

        base_url = (self._config.base_url or "").strip()
        if not base_url:
            return RainbowClientResult(
                signals=[],
                errors=["read_only mode requires base_url"],
                source="empty",
            )

        payload_result = self._fetch_read_only_payloads()
        if payload_result.errors:
            return payload_result

        mapped_signals: list[Envelope] = []
        errors: list[str] = []
        for index, payload in enumerate(payload_result.signals):
            if self.is_canonical_endpoint:
                envelope, map_errors = self._map_canonical_signal_to_envelope(payload)
            else:
                envelope, map_errors = self._map_crypto_signal_to_envelope(payload)
            if map_errors:
                errors.extend(
                    f"payload[{index}]: {error}"
                    for error in map_errors
                )
                continue
            if envelope is None:
                errors.append(f"payload[{index}]: mapper returned no envelope")
                continue

            validation = self._validate_envelope_with_warnings(envelope)
            if validation is None:
                mapped_signals.append(envelope)
                continue

            if validation.error is not None:
                errors.append(f"payload[{index}]: {validation.error}")
                continue

            if validation.verdict == "fail":
                validation_errors = "; ".join(validation.errors)
                errors.append(
                    f"payload[{index}]: validation FAILED: {validation_errors}"
                )
                continue

            normalized = validation.normalized
            if normalized is None:
                errors.append(
                    f"payload[{index}]: validator returned no normalized envelope"
                )
                continue

            mapped_signals.append(normalized)

        limited_signals = self._apply_max_records(mapped_signals)
        return RainbowClientResult(
            signals=limited_signals,
            errors=errors,
            source="read_only" if mapped_signals else "empty",
            count=len(limited_signals),
        )

    def _fetch_read_only_payloads(self) -> RainbowClientResult:
        url = self._build_read_only_url()
        request = Request(
            url=url,
            headers={"Accept": "application/json"},
            method="GET",
        )

        try:
            with urlopen(request, timeout=self._config.timeout_seconds) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    return RainbowClientResult(
                        signals=[],
                        errors=[f"HTTP {status} while fetching read_only signals"],
                        source="empty",
                    )
                payload_bytes = response.read()
        except HTTPError as exc:
            return RainbowClientResult(
                signals=[],
                errors=[f"HTTP {exc.code} while fetching read_only signals"],
                source="empty",
            )
        except URLError as exc:
            return RainbowClientResult(
                signals=[],
                errors=[f"Network error while fetching read_only signals: {exc.reason}"],
                source="empty",
            )
        except OSError as exc:
            return RainbowClientResult(
                signals=[],
                errors=[f"OS error while fetching read_only signals: {exc}"],
                source="empty",
            )

        try:
            decoded = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return RainbowClientResult(
                signals=[],
                errors=[f"Invalid JSON payload from read_only source: {exc}"],
                source="empty",
            )

        payloads = self._extract_payload_list(decoded)
        if payloads is None:
            return RainbowClientResult(
                signals=[],
                errors=["read_only payload must be a list or object with 'signals' list"],
                source="empty",
            )

        return RainbowClientResult(
            signals=payloads,
            source="read_only",
            count=len(payloads),
        )

    def _build_read_only_url(self) -> str:
        base_url = (self._config.base_url or "").rstrip("/") + "/"
        endpoint_path = self._config.endpoint_path.lstrip("/")
        return urljoin(base_url, endpoint_path)

    def _apply_max_records(self, signals: list[Envelope]) -> list[Envelope]:
        if self._config.max_records is None:
            return list(signals)
        return list(signals[: self._config.max_records])

    @staticmethod
    def _load_fixture(path: Path) -> Envelope | None:
        """Load a single JSON fixture, returning None on failure."""
        try:
            with open(path) as fixture_file:
                payload = json.load(fixture_file)
        except (json.JSONDecodeError, OSError):
            return None

        if not isinstance(payload, dict):
            return None
        return dict(payload)

    @staticmethod
    def _extract_payload_list(decoded: object) -> list[Envelope] | None:
        if isinstance(decoded, list):
            return [item for item in decoded if isinstance(item, dict)]
        if isinstance(decoded, dict):
            raw_signals = decoded.get("signals")
            if isinstance(raw_signals, list):
                return [item for item in raw_signals if isinstance(item, dict)]
        return None

    @staticmethod
    def _coerce_object(value: object) -> JsonObject:
        if isinstance(value, dict):
            return {str(key): RainbowSignalProviderClient._json_value(item) for key, item in value.items()}
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {"raw": value}
            if isinstance(parsed, dict):
                return {str(key): RainbowSignalProviderClient._json_value(item) for key, item in parsed.items()}
            return {"raw": value}
        return {}

    @staticmethod
    def _json_value(value: object) -> JsonValue:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return [RainbowSignalProviderClient._json_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): RainbowSignalProviderClient._json_value(item) for key, item in value.items()}
        return str(value)

    @staticmethod
    def _coerce_float(value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @staticmethod
    def _coerce_str(value: object) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _normalize_timestamp(raw_timestamp: str) -> str:
        try:
            normalized = raw_timestamp.replace("Z", "+00:00")
            timestamp = datetime.fromisoformat(normalized)
        except ValueError:
            return raw_timestamp

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.isoformat()

    def _map_crypto_signal_to_envelope(
        self,
        payload: Envelope,
    ) -> tuple[Envelope | None, list[str]]:
        signal_id = self._coerce_str(payload.get("signal_id"))
        source = self._coerce_str(payload.get("source"))
        asset = self._coerce_str(payload.get("asset"))
        direction = self._coerce_str(payload.get("direction"))
        timestamp = self._coerce_str(payload.get("timestamp"))
        confidence = self._coerce_float(payload.get("confidence"))
        strength = self._coerce_float(payload.get("strength"))

        errors: list[str] = []
        if signal_id is None:
            errors.append("missing signal_id")
        if source is None:
            errors.append("missing source")
        if asset is None:
            errors.append("missing asset")
        if direction is None:
            errors.append("missing direction")
        if timestamp is None:
            errors.append("missing timestamp")
        if confidence is None:
            errors.append("missing confidence")

        if errors:
            return None, errors

        metadata = self._coerce_object(payload.get("metadata"))
        raw_data = self._coerce_object(payload.get("raw_data"))

        timeframe_raw = metadata.get("timeframe")
        timeframe = timeframe_raw if isinstance(timeframe_raw, str) else None

        if timestamp is None:
            return None, errors

        normalized_timestamp = self._normalize_timestamp(timestamp)
        emitted_at = datetime.now(UTC).isoformat()

        envelope: Envelope = {
            "event_type": "signal",
            "schema_version": 1,
            "source_system": self._config.provider_id,
            "source_id": signal_id,
            "strategy_id": source,
            "model_id": None,
            "symbol": normalize_symbol(asset),
            "timeframe": timeframe,
            "timestamp_utc": normalized_timestamp,
            "emitted_at_utc": emitted_at,
            "direction": direction,
            "confidence": confidence,
            "signal_strength": strength,
            "regime_hint": None,
            "metadata": {
                **metadata,
                "provider_mode": "read_only",
                "actionability": {
                    "can_execute": False,
                    "dry_run_only": True,
                },
                "upstream_signal": {
                    "signal_type": payload.get("signal_type"),
                    "value": payload.get("value"),
                    "rainbow_score": payload.get("rainbow_score"),
                    "ai_evaluation": payload.get("ai_evaluation"),
                },
                "raw_data": raw_data,
            },
            "redaction_status": "clean",
        }
        return envelope, []

    @staticmethod
    def _canonical_direction_to_hub(direction: str | None) -> str:
        """Map upstream canonical SignalDirection to trading-hub direction."""
        if direction is None:
            return "unknown"
        mapping = {
            "bullish": "long",
            "bearish": "short",
            "neutral": "flat",
        }
        return mapping.get(direction.lower(), "unknown")

    def _map_canonical_signal_to_envelope(
        self,
        payload: Envelope,
    ) -> tuple[Envelope | None, list[str]]:
        """Convert an upstream canonical envelope into a trading-hub envelope.

        This path is used when the client is configured to consume the
        ``/signals/canonical/latest`` endpoint. It does NOT import upstream
        code or merge unmerged PR #66 behaviour; it only maps already-public
        canonical fields into the local contract.
        """
        signal_id = self._coerce_str(payload.get("id"))
        source = self._coerce_str(payload.get("source"))
        asset = self._coerce_str(payload.get("asset"))
        direction_raw = self._coerce_str(payload.get("direction"))
        timestamp = self._coerce_str(payload.get("created_at"))
        confidence = self._coerce_float(payload.get("confidence"))
        features = payload.get("features", {})
        if not isinstance(features, dict):
            features = {}
        strength = self._coerce_float(features.get("strength"))
        timeframe = self._coerce_str(payload.get("timeframe"))

        errors: list[str] = []
        if signal_id is None:
            errors.append("missing id")
        if source is None:
            errors.append("missing source")
        if asset is None:
            errors.append("missing asset")
        if direction_raw is None:
            errors.append("missing direction")
        if timestamp is None:
            errors.append("missing created_at")
        if confidence is None:
            errors.append("missing confidence")

        if errors:
            return None, errors

        direction = self._canonical_direction_to_hub(direction_raw)
        if direction == "unknown":
            return None, [f"unknown direction: {direction_raw}"]

        metadata = self._coerce_object(features)
        # Preserve upstream actionability stamp if present; otherwise default fail-closed.
        upstream_actionability = payload.get("actionability", {})
        if isinstance(upstream_actionability, dict):
            can_execute = upstream_actionability.get("can_execute", False)
            dry_run_only = upstream_actionability.get("dry_run_only", True)
            if can_execute is not False or dry_run_only is not True:
                return None, [
                    "upstream actionability violates read-only contract: "
                    f"can_execute={can_execute}, dry_run_only={dry_run_only}"
                ]

        normalized_timestamp = self._normalize_timestamp(timestamp)
        emitted_at = datetime.now(UTC).isoformat()

        envelope: Envelope = {
            "event_type": "signal",
            "schema_version": 1,
            "source_system": self._config.provider_id,
            "source_id": source,
            "strategy_id": metadata.get("strategy", source),
            "model_id": metadata.get("model_id"),
            "symbol": normalize_symbol(asset),
            "timeframe": timeframe,
            "timestamp_utc": normalized_timestamp,
            "emitted_at_utc": emitted_at,
            "direction": direction,
            "confidence": confidence,
            "signal_strength": strength,
            "regime_hint": metadata.get("regime"),
            "metadata": {
                **metadata,
                "provider_mode": "read_only",
                "actionability": {
                    "can_execute": False,
                    "dry_run_only": True,
                },
                "upstream_canonical": {
                    "signal_class": payload.get("signal_class"),
                    "subtype": payload.get("subtype"),
                    "valid_until": payload.get("valid_until"),
                },
            },
            "redaction_status": "clean",
        }
        return envelope, []

    @staticmethod
    def _validate_envelope(
        envelope: Envelope,
    ) -> Envelope | None:
        """Validate a single envelope through the validator."""
        try:
            from si_v2.rainbow.validator import RainbowSignalEnvelopeValidator

            validator = RainbowSignalEnvelopeValidator()
            result = validator.validate_envelope(envelope)
            return {
                "verdict": result.verdict.value,
                "errors": result.errors,
                "warnings": result.warnings,
                "has_normalized": result.normalized is not None,
            }
        except ImportError:
            return {"error": "Validator not available"}
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _validate_envelope_with_warnings(
        envelope: Envelope,
    ) -> _ValidationSummary | None:
        try:
            from si_v2.rainbow.validator import RainbowSignalEnvelopeValidator

            validator = RainbowSignalEnvelopeValidator()
            result = validator.validate_envelope(envelope)
            return _ValidationSummary(
                verdict=result.verdict.value,
                errors=list(result.errors),
                warnings=list(result.warnings),
                normalized=result.normalized,
            )
        except ImportError:
            return _ValidationSummary(error="Validator not available")
        except Exception as exc:
            return _ValidationSummary(error=str(exc))


@dataclass
class _ValidationSummary:
    verdict: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized: Envelope | None = None
    error: str | None = None
