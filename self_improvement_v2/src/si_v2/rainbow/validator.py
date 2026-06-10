"""Rainbow Signal Envelope Validator.

Validates signal envelopes against the Rainbow Signal Provider Contract
(ai4trade-bot #51 / docs/integration/rainbow-signal-provider-contract.md).

The validator performs:
  - Field presence checks
  - Type validation
  - Direction normalization
  - Confidence range validation
  - Staleness detection
  - Heartbeat / no-signal classification
  - Malformed envelope fail-closed rejection

No network, Docker, Freqtrade, Telegram, or runtime calls are made.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum

# ── Verdict ──────────────────────────────────────────────────────────────────


class ValidationVerdict(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


# ── Direction mapping ────────────────────────────────────────────────────────

_RAINBOW_TO_TRADING_HUB_DIRECTION: dict[str, str] = {
    "bullish": "long",
    "bearish": "short",
    "neutral": "flat",
    "long": "long",
    "short": "short",
    "flat": "flat",
    "no_signal": "no_signal",
    "unknown": "unknown",
}

_ALLOWED_DIRECTIONS = frozenset(_RAINBOW_TO_TRADING_HUB_DIRECTION.values())


def normalize_direction(raw: object) -> str:
    """Normalize a direction string to the trading-hub canonical form.

    Accepts both Rainbow (bullish/bearish/neutral) and trading-hub
    (long/short/flat) conventions.
    Returns ``"unknown"`` for unrecognized values.
    """
    if not isinstance(raw, str):
        return "unknown"
    return _RAINBOW_TO_TRADING_HUB_DIRECTION.get(raw.strip().lower(), "unknown")


# ── Required fields ──────────────────────────────────────────────────────────

_REQUIRED_FIELDS: tuple[str, ...] = (
    "event_type",
    "schema_version",
    "source_system",
    "source_id",
    "strategy_id",
    "symbol",
    "timestamp_utc",
    "direction",
    "confidence",
    "metadata",
    "redaction_status",
)

_OPTIONAL_FIELDS: tuple[str, ...] = (
    "model_id",
    "timeframe",
    "emitted_at_utc",
    "signal_strength",
    "regime_hint",
)

_VALID_EVENT_TYPES = frozenset({"signal", "no_signal", "heartbeat"})

_STALE_THRESHOLD_SECONDS = 3600  # 1 hour per contract default


# ── Validation result ────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Result of a single envelope validation.

    Attributes:
        verdict: Overall verdict.
        errors: Field-level error messages.  Empty on PASS/WARN.
        warnings: Non-fatal observations.
        normalized: Canonical trading-hub envelope if validation passed
            required fields.  ``None`` on FAIL.
        source_file: Optional name of the fixture file that was validated.
    """

    verdict: ValidationVerdict
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized: dict[str, object] | None = None
    source_file: str | None = None


# ── Validator ────────────────────────────────────────────────────────────────


class RainbowSignalEnvelopeValidator:
    """Canonical Rainbow signal envelope validator.

    Usage::

        validator = RainbowSignalEnvelopeValidator()
        result = validator.validate_envelope(envelope_dict)
    """

    def validate_envelope(
        self,
        envelope: dict[str, object],
        source_file: str | None = None,
    ) -> ValidationResult:
        """Validate a single signal envelope.

        Args:
            envelope: The parsed JSON envelope as a Python dict.
            source_file: Optional identifier for error reporting.

        Returns:
            A ``ValidationResult`` with verdict, errors, warnings, and
            optionally the normalized envelope.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # ── Required field presence ──────────────────────────────────────
        for field_name in _REQUIRED_FIELDS:
            if field_name not in envelope or envelope[field_name] is None:
                errors.append(f"Missing required field: {field_name}")

        if errors:
            return ValidationResult(
                verdict=ValidationVerdict.FAIL,
                errors=errors,
                source_file=source_file,
            )

        # ── Event type ───────────────────────────────────────────────────
        event_type = str(envelope.get("event_type", ""))
        if event_type not in _VALID_EVENT_TYPES:
            errors.append(
                f"Invalid event_type: '{event_type}'. "
                f"Must be one of: {', '.join(sorted(_VALID_EVENT_TYPES))}"
            )

        # ── Schema version ───────────────────────────────────────────────
        schema_version = envelope.get("schema_version")
        if not isinstance(schema_version, int) or schema_version < 1:
            errors.append(
                f"schema_version must be int >= 1, got {schema_version!r}"
            )

        # ── Source system ────────────────────────────────────────────────
        source_system = str(envelope.get("source_system", ""))
        if source_system != "rainbow":
            warnings.append(
                f"Unexpected source_system: '{source_system}'. "
                f"Expected 'rainbow'."
            )

        # ── Direction ────────────────────────────────────────────────────
        raw_direction = envelope.get("direction", "")
        normalized_dir = normalize_direction(raw_direction)
        if normalized_dir == "unknown":
            errors.append(
                f"Invalid direction: '{raw_direction}'. "
                f"Must be one of: {', '.join(sorted(_ALLOWED_DIRECTIONS))}"
            )

        # ── Confidence ───────────────────────────────────────────────────
        confidence = envelope.get("confidence")
        if not isinstance(confidence, (int, float)):
            errors.append(
                f"confidence must be a number (0.0-1.0), "
                f"got {type(confidence).__name__}"
            )
        elif confidence < 0.0 or confidence > 1.0:
            errors.append(
                f"confidence must be 0.0-1.0, got {confidence}"
            )

        # ── Signal strength (optional) ───────────────────────────────────
        signal_strength = envelope.get("signal_strength")
        if signal_strength is not None:
            if not isinstance(signal_strength, (int, float)):
                errors.append(
                    f"signal_strength must be a number (0.0-1.0) or null, "
                    f"got {type(signal_strength).__name__}"
                )
            elif signal_strength < 0.0 or signal_strength > 1.0:
                errors.append(
                    f"signal_strength must be 0.0-1.0, got {signal_strength}"
                )

        # ── Timestamp ────────────────────────────────────────────────────
        ts_raw = envelope.get("timestamp_utc", "")
        try:
            if isinstance(ts_raw, str):
                datetime.datetime.fromisoformat(ts_raw)
        except (ValueError, TypeError):
            errors.append(
                f"timestamp_utc must be a valid ISO-8601 string, "
                f"got {ts_raw!r}"
            )

        # ── Symbol ───────────────────────────────────────────────────────
        symbol = envelope.get("symbol", "")
        if not isinstance(symbol, str) or not symbol.strip():
            errors.append("symbol must be a non-empty string")

        # ── Redaction status ─────────────────────────────────────────────
        redaction_status = str(envelope.get("redaction_status", ""))
        valid_statuses = {"clean", "redacted", "unchecked"}
        if redaction_status not in valid_statuses:
            warnings.append(
                f"Unexpected redaction_status: '{redaction_status}'. "
                f"Expected one of: {', '.join(sorted(valid_statuses))}"
            )

        # ── Staleness check ──────────────────────────────────────────────
        self._check_staleness(envelope, warnings)

        # ── Heartbeat / no-signal classification ─────────────────────────
        if event_type == "heartbeat":
            warnings.append("Heartbeat event — not a trading signal")
        elif event_type == "no_signal":
            warnings.append("No-signal event — not an actionable signal")

        # ── Verdict ──────────────────────────────────────────────────────
        if errors:
            return ValidationResult(
                verdict=ValidationVerdict.FAIL,
                errors=errors,
                warnings=warnings,
                source_file=source_file,
            )

        # ── Build normalized envelope ────────────────────────────────────
        normalized = self._build_normalized(
            envelope, normalized_dir, warnings,
        )

        verdict = ValidationVerdict.WARN if warnings else ValidationVerdict.PASS
        return ValidationResult(
            verdict=verdict,
            errors=errors,
            warnings=warnings,
            normalized=normalized,
            source_file=source_file,
        )

    # ── Internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _check_staleness(
        envelope: dict[str, object],
        warnings: list[str],
    ) -> None:
        """Append a staleness warning if the signal is older than threshold."""
        # Check explicit data_quality status
        metadata = envelope.get("metadata", {})
        if isinstance(metadata, dict):
            dq = metadata.get("data_quality", {})
            if isinstance(dq, dict):
                dq_status = dq.get("status", "")
                if dq_status in ("stale", "unavailable"):
                    warnings.append(
                        f"Signal marked as '{dq_status}' by data_quality "
                        f"(freshness={dq.get('freshness_seconds', '?')}s)"
                    )

        # Check age by timestamp
        ts_raw = envelope.get("timestamp_utc", "")
        if isinstance(ts_raw, str):
            try:
                ts = datetime.datetime.fromisoformat(ts_raw)
                now = datetime.datetime.now(datetime.UTC)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=datetime.UTC)
                age = (now - ts).total_seconds()
                if age > _STALE_THRESHOLD_SECONDS:
                    warnings.append(
                        f"Signal is stale: {age:.0f}s old "
                        f"(threshold={_STALE_THRESHOLD_SECONDS}s)"
                    )
            except (ValueError, TypeError):
                pass  # timestamp validation already handled above

    @staticmethod
    def _build_normalized(
        envelope: dict[str, object],
        direction: str,
        warnings: list[str],
    ) -> dict[str, object]:
        """Build a canonical trading-hub envelope dict.

        Preserves all known fields and includes extra unrecognised keys
        under a reserved key for forward compatibility.
        """
        known_keys = set(_REQUIRED_FIELDS) | set(_OPTIONAL_FIELDS)
        extra: dict[str, object] = {}
        for k in envelope:
            if k not in known_keys:
                extra[k] = envelope[k]

        if extra:
            warnings.append(
                f"Extra fields preserved in normalized envelope: "
                f"{', '.join(sorted(extra.keys()))}"
            )

        result: dict[str, object] = {
            "schema_version": envelope.get("schema_version"),
            "event_type": envelope.get("event_type"),
            "source_system": envelope.get("source_system"),
            "source_id": envelope.get("source_id"),
            "strategy_id": envelope.get("strategy_id"),
            "model_id": envelope.get("model_id"),
            "symbol": envelope.get("symbol"),
            "timeframe": envelope.get("timeframe"),
            "timestamp_utc": envelope.get("timestamp_utc"),
            "emitted_at_utc": envelope.get("emitted_at_utc"),
            "direction": direction,
            "confidence": envelope.get("confidence"),
            "signal_strength": envelope.get("signal_strength"),
            "regime_hint": envelope.get("regime_hint"),
            "metadata": envelope.get("metadata", {}),
            "redaction_status": envelope.get("redaction_status"),
        }

        # Preserve extra fields
        if extra:
            result["_extra_fields"] = extra

        return result
