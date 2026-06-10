"""Shadowlock-compatible audit event mapper for Rainbow signal evidence.

Maps validated Rainbow signal envelopes into Shadowlock-compatible audit
event dictionaries suitable for offline review, testing, and future
integration with the Shadowlock Writer pipeline.

No production Shadowlock writes are performed. All events are
deterministically serializable to JSON.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

# ── Event categories ─────────────────────────────────────────────────────────


class RainbowAuditEventType(Enum):
    """Shadowlock-compatible event types for Rainbow signal evidence."""

    SIGNAL_VALIDATED = "rainbow_signal_validated"
    SIGNAL_REJECTED = "rainbow_signal_rejected"
    SIGNAL_STALE = "rainbow_signal_stale"
    HEARTBEAT_OBSERVED = "rainbow_heartbeat_observed"
    NO_SIGNAL_OBSERVED = "rainbow_no_signal_observed"
    FIXTURE_VALIDATION_SUMMARY = "rainbow_fixture_validation_summary"


# ── Audit event ──────────────────────────────────────────────────────────────


@dataclass
class RainbowAuditEvent:
    """A single Shadowlock-compatible audit event for Rainbow signal evidence.

    All fields are serializable. No field contains trading instructions.
    """

    event_id: str
    event_type: str
    provider_id: str
    source_id: str
    schema_version: str
    validator_verdict: str
    is_actionable: bool
    direction: str
    confidence: float
    symbol_or_pair: str
    timeframe: str | None
    timestamp_utc: str
    observed_at_utc: str
    redaction_status: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata_summary: str = ""
    bot_name: str = "rainbow"

    def to_shadowlock_entry(self) -> dict[str, object]:
        """Serialize to a Shadowlock Writer-compatible entry dict.

        The entry uses the "default" event field set (schema_version,
        event_type, timestamp_utc, bot_name) plus Rainbow-specific fields.
        """
        return {
            "schema_version": self.schema_version,
            "event_type": self.event_type,
            "timestamp_utc": self.timestamp_utc,
            "bot_name": self.bot_name,
            # Rainbow-specific fields
            "rainbow_event_id": self.event_id,
            "rainbow_provider_id": self.provider_id,
            "rainbow_source_id": self.source_id,
            "rainbow_validator_verdict": self.validator_verdict,
            "rainbow_is_actionable": self.is_actionable,
            "rainbow_direction": self.direction,
            "rainbow_confidence": self.confidence,
            "rainbow_symbol": self.symbol_or_pair,
            "rainbow_timeframe": self.timeframe or "",
            "rainbow_observed_at_utc": self.observed_at_utc,
            "rainbow_redaction_status": self.redaction_status,
            "rainbow_errors": self.errors,
            "rainbow_warnings": self.warnings,
            "rainbow_metadata_summary": self.metadata_summary,
        }


# ── Event mapper ─────────────────────────────────────────────────────────────


class RainbowShadowlockEventMapper:
    """Map Rainbow validator/client results to Shadowlock audit events.

    Usage::

        mapper = RainbowShadowlockEventMapper()
        events = mapper.map_envelope(envelope_dict)
    """

    _SHADOWLOCK_SCHEMA_VERSION: ClassVar[str] = "1.0"
    _PROVIDER_ID: ClassVar[str] = "rainbow"

    @classmethod
    def map_envelope(
        cls,
        envelope: dict[str, object],
        validator_result: dict[str, object] | None = None,
    ) -> RainbowAuditEvent:
        """Map a single Rainbow signal envelope to an audit event.

        Args:
            envelope: The signal envelope dict (from fixture or client).
            validator_result: Optional validation result dict.

        Returns:
            A populated ``RainbowAuditEvent``.
        """
        now_utc = datetime.datetime.now(datetime.UTC)
        timestamp_utc = str(
            envelope.get(
                "timestamp_utc",
                now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )
        if not timestamp_utc.endswith("Z"):
            timestamp_utc += "Z"

        # Determine verdict and event type
        verdict = "pass"
        event_type = RainbowAuditEventType.SIGNAL_VALIDATED.value
        errors: list[str] = []
        warnings: list[str] = []
        is_actionable = True

        if validator_result:
            verdict = str(
                validator_result.get("verdict", "pass")
            )
            errors = list(
                validator_result.get("errors", [])
            )
            warnings = list(
                validator_result.get("warnings", [])
            )

            # Determine event category based on content
            event_type = cls._classify_event(
                envelope, verdict, errors, warnings
            )

            # Non-actionable signals
            is_actionable = cls._is_actionable(
                event_type, verdict, errors
            )

        # Extract envelope fields
        direction = str(
            envelope.get("direction", "unknown")
        )
        confidence = float(
            envelope.get("confidence", 0.0)
        )
        symbol = str(
            envelope.get("symbol", "")
        )
        timeframe = envelope.get("timeframe")
        if timeframe is not None:
            timeframe = str(timeframe)

        redaction_status = str(
            envelope.get("redaction_status", "unchecked")
        )
        source_id = str(
            envelope.get("source_id", "rainbow:unknown")
        )

        # Build metadata summary
        metadata = envelope.get("metadata", {})
        if isinstance(metadata, dict):
            reason_codes = metadata.get("reason_codes", [])
            dq = metadata.get("data_quality", {})
            dq_status = ""
            if isinstance(dq, dict):
                dq_status = str(
                    dq.get("status", "")
                )
            summary_parts: list[str] = []
            if reason_codes and isinstance(reason_codes, list):
                summary_parts.append(
                    f"reasons={','.join(str(r) for r in reason_codes[:3])}"
                )
            if dq_status:
                summary_parts.append(f"data_quality={dq_status}")
            metadata_summary = "; ".join(summary_parts) if summary_parts else ""
        else:
            metadata_summary = ""

        return RainbowAuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            provider_id=cls._PROVIDER_ID,
            source_id=source_id,
            schema_version=cls._SHADOWLOCK_SCHEMA_VERSION,
            validator_verdict=verdict,
            is_actionable=is_actionable,
            direction=direction,
            confidence=confidence,
            symbol_or_pair=symbol,
            timeframe=timeframe,
            timestamp_utc=timestamp_utc,
            observed_at_utc=now_utc.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            redaction_status=redaction_status,
            errors=errors,
            warnings=warnings,
            metadata_summary=metadata_summary,
        )

    @classmethod
    def map_fixture_batch(
        cls,
        envelopes: list[dict[str, object]],
        validator_results: list[dict[str, object]] | None = None,
    ) -> list[RainbowAuditEvent]:
        """Map a batch of envelopes to audit events.

        Args:
            envelopes: List of signal envelope dicts.
            validator_results: Optional list of validation result dicts,
                must match length of ``envelopes``.

        Returns:
            List of audit events, one per envelope.
        """
        events: list[RainbowAuditEvent] = []
        for i, envelope in enumerate(envelopes):
            vr = (
                validator_results[i]
                if validator_results and i < len(validator_results)
                else None
            )
            events.append(cls.map_envelope(envelope, vr))
        return events

    @classmethod
    def generate_preview_report(
        cls,
        events: list[RainbowAuditEvent],
    ) -> str:
        """Generate a deterministic Markdown preview report.

        Args:
            events: List of audit events to summarize.

        Returns:
            Markdown report string.
        """
        lines: list[str] = []
        lines.append(
            "# Rainbow Shadowlock Audit Event Preview"
        )
        lines.append("")
        lines.append(
            "> **Status:** Preview/offline only — "
            "not written to Shadowlock storage."
        )
        lines.append(
            f"> **Events:** {len(events)} total"
        )
        lines.append("")

        # Category counts
        from collections import Counter

        category_counts: Counter[str] = Counter()
        actionable_count = 0
        non_actionable_count = 0
        for event in events:
            category_counts[event.event_type] += 1
            if event.is_actionable:
                actionable_count += 1
            else:
                non_actionable_count += 1

        lines.append("## Event Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total events | {len(events)} |")
        lines.append(
            f"| Actionable | {actionable_count} |"
        )
        lines.append(
            f"| Non-actionable | {non_actionable_count} |"
        )
        lines.append("")
        lines.append("### By Category")
        lines.append("")
        lines.append("| Category | Count |")
        lines.append("|----------|-------|")
        for cat, count in sorted(category_counts.items()):
            lines.append(f"| `{cat}` | {count} |")

        lines.append("")
        lines.append("## Event Details")
        lines.append("")

        for i, event in enumerate(events):
            lines.append(f"### Event {i+1}: `{event.event_type}`")
            lines.append("")
            lines.append("| Field | Value |")
            lines.append("|-------|-------|")
            lines.append(
                f"| event_id | `{event.event_id}` |"
            )
            lines.append(
                f"| provider_id | `{event.provider_id}` |"
            )
            lines.append(
                f"| source_id | `{event.source_id}` |"
            )
            lines.append(
                f"| validator_verdict | {event.validator_verdict} |"
            )
            lines.append(
                f"| is_actionable | {event.is_actionable} |"
            )
            lines.append(
                f"| direction | {event.direction} |"
            )
            lines.append(
                f"| confidence | {event.confidence} |"
            )
            lines.append(
                f"| symbol | {event.symbol_or_pair} |"
            )
            lines.append(
                f"| redaction_status | {event.redaction_status} |"
            )
            if event.errors:
                lines.append(
                    f"| errors | {'; '.join(event.errors)} |"
                )
            if event.warnings:
                lines.append(
                    f"| warnings | {'; '.join(event.warnings)} |"
                )
            lines.append("")

        lines.append(
            "*No production Shadowlock writes were performed.*"
        )
        return "\n".join(lines)

    # ── Internal classification ────────────────────────────────────────

    @staticmethod
    def _classify_event(
        envelope: dict[str, object],
        verdict: str,
        errors: list[str],
        warnings: list[str],
    ) -> str:
        """Determine the audit event type from envelope content."""
        event_type_str = str(
            envelope.get("event_type", "")
        )

        # Heartbeat first
        if event_type_str == "heartbeat":
            return (
                RainbowAuditEventType.HEARTBEAT_OBSERVED.value
            )

        # No-signal
        if event_type_str == "no_signal":
            return (
                RainbowAuditEventType.NO_SIGNAL_OBSERVED.value
            )

        # Check for stale in data_quality
        metadata = envelope.get("metadata", {})
        if isinstance(metadata, dict):
            dq = metadata.get("data_quality", {})
            if isinstance(dq, dict):
                dq_status = str(dq.get("status", ""))
                if dq_status == "stale":
                    return (
                        RainbowAuditEventType.SIGNAL_STALE.value
                    )

        # Check for stale warning
        for w in warnings:
            if "stale" in w.lower():
                return (
                    RainbowAuditEventType.SIGNAL_STALE.value
                )

        # Rejected if FAIL
        if verdict == "fail" or errors:
            return (
                RainbowAuditEventType.SIGNAL_REJECTED.value
            )

        return (
            RainbowAuditEventType.SIGNAL_VALIDATED.value
        )

    @staticmethod
    def _is_actionable(
        event_type: str,
        verdict: str,
        errors: list[str],
    ) -> bool:
        """Determine if a signal is actionable."""
        non_actionable = {
            RainbowAuditEventType.HEARTBEAT_OBSERVED.value,
            RainbowAuditEventType.NO_SIGNAL_OBSERVED.value,
            RainbowAuditEventType.SIGNAL_REJECTED.value,
            RainbowAuditEventType.SIGNAL_STALE.value,
        }
        if event_type in non_actionable:
            return False
        return not (verdict == "fail" or errors)
