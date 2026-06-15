"""Structured operational event/report schema for the Trading Hub.

This module defines a lightweight, deterministic schema for operational
events and reports.  It does **not** replace Shadowlock or the unified
audit trail from #259 — it provides a common shape so components that
write operational logs and reports share a consistent, correlatable format.

Schema version 1.0
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

SUPPORTED_SCHEMA_VERSIONS = {"1.0"}
DEFAULT_SCHEMA_VERSION = "1.0"

SEVERITY_DEBUG = "debug"
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"
SEVERITY_CRITICAL = "critical"

VALID_SEVERITIES = {SEVERITY_DEBUG, SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ERROR, SEVERITY_CRITICAL}

EVENT_SIGNAL_CYCLE = "signal_cycle"
EVENT_RISKGUARD_VERDICT = "riskguard_verdict"
EVENT_KILL_SWITCH = "kill_switch"
EVENT_PIPELINE_ERROR = "pipeline_error"
EVENT_HEALTHCHECK = "healthcheck"

# ---------------------------------------------------------------------------
# Sensitive-field names that must never appear in event payloads
# ---------------------------------------------------------------------------

SENSITIVE_KEY_PATTERNS = frozenset({
    "api_key",
    "api_secret",
    "password",
    "jwt_secret_key",
    "passphrase",
    "private_key",
    "exchange.key",
    "exchange.secret",
    "token",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_correlation_id() -> str:
    """Return a monotonic run-based correlation ID.

    Format: ``YYYYMMDD-HHMMSS-XXXXX`` where XXXXX is a short hex suffix.
    This is reproducible within the same second but not guaranteed globally
    unique — sufficient for operational correlation.
    """
    now = datetime.now(tz=timezone.utc)
    suffix = hex(id(now))[-5:]
    return f"{now.strftime('%Y%m%d-%H%M%S')}-{suffix}"


def validate_event(event: Dict[str, Any]) -> List[str]:
    """Validate an event dict against the schema.  Returns a list of error
    messages (empty = valid)."""
    errors: List[str] = []

    if not isinstance(event, dict):
        return ["event must be a dict"]

    # Required fields
    for field in ("schema_version", "timestamp_utc", "component", "event_type", "severity"):
        if field not in event:
            errors.append(f"missing required field: {field}")

    if errors:
        return errors

    # Schema version
    if event["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"unsupported schema_version: {event['schema_version']!r}")

    # Timestamp
    ts = event.get("timestamp_utc", "")
    try:
        datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        errors.append(f"invalid timestamp_utc: {ts!r}")

    # Severity
    if event.get("severity") not in VALID_SEVERITIES:
        errors.append(f"invalid severity: {event.get('severity')!r}")

    # Correlation id recommended
    if "correlation_id" not in event:
        errors.append("missing recommended field: correlation_id")

    # No sensitive keys in the payload
    _check_sensitive_keys(event, "", errors)

    return errors


def _check_sensitive_keys(obj: Any, path: str, errors: List[str]) -> None:
    """Recurse through ``obj`` and flag any key matching SENSITIVE_KEY_PATTERNS."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            full_path = f"{path}.{key}" if path else str(key)
            lower = key.lower()
            if lower in SENSITIVE_KEY_PATTERNS or any(
                pat in full_path.lower() for pat in SENSITIVE_KEY_PATTERNS
            ):
                errors.append(f"sensitive key found: {full_path}")
            _check_sensitive_keys(value, full_path, errors)
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            _check_sensitive_keys(item, f"{path}[{index}]", errors)


def build_event(
    component: str,
    event_type: str,
    severity: str = SEVERITY_INFO,
    message: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a schema-compliant event dict.

    Parameters
    ----------
    component : str
        Source component name, e.g. ``trading_pipeline``, ``fleet_healthcheck``.
    event_type : str
        A dotted event name, e.g. ``riskguard_verdict``, ``signal_cycle.stale``.
    severity : str
        One of ``VALID_SEVERITIES``.
    message : str
        Human-readable description.
    metadata : dict or None
        Extra structured data (must not contain sensitive keys).
    correlation_id : str or None
        Auto-generated if omitted.
    """
    if correlation_id is None:
        correlation_id = generate_correlation_id()

    event: Dict[str, Any] = {
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        "component": component,
        "event_type": event_type,
        "severity": severity,
        "message": message,
    }

    if metadata:
        event["metadata"] = metadata

    return event
