"""SI v2 Active Cycle Runner — telemetry normalizer.

Transforms raw Freqtrade REST telemetry into a stable, typed internal model
with full secret redaction. No credential value ever enters the normalizer
output.

Schema semantics:
    - ``NormalizedTelemetry`` is the single stable evidence unit.
    - Every sensitive field (token, password, key) is handled by name
      reference only. The env-var *name* (not value) is recorded.
    - The normalizer is pure data transformation: no I/O, no network,
      no env-var reading.

Usage:
    norm = normalize_raw_evidence(
        bot_id="freqtrade-freqforge",
        base_url="http://...",
        ping_status_code=200,
        ping_response_summary='{"status":"ok"}',
        status_status_code=200,
        status_response_summary='[{"trade_id":1}]',
        status_auth_outcome="AUTHENTICATED",
        username_env="SI_V2_FREQTRADE_FREQFORGE_USERNAME",
        password_env="SI_V2_FREQTRADE_FREQFORGE_PASSWORD",
        missing_env_vars=[],
        auth_error_summary="",
        fetched_at_utc="2026-06-13T12:00:00Z",
    )
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

# ------------------------------------------------------------------
# Schema versioning
# ------------------------------------------------------------------
TELEMETRY_NORMALIZER_SCHEMA_VERSION: str = "telemetry_normalizer_v1"

# ------------------------------------------------------------------
# Typed normalizer output
# ------------------------------------------------------------------


class NormalizedTelemetry(BaseModel):
    """Stable, redacted, typed telemetry for one bot from one cycle.

    All sensitive fields are env-var **names** only. No credential values
    are stored. The ``response_summary`` fields are pre-redacted by the
    Freqtrade connector's built-in redaction (``_redact_sensitive``).

    Schema versioning is on the model itself (``schema_version``) so that
    downstream consumers (fleet analyzer, cycle state, reports) can detect
    incompatible format changes.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    # Metadata
    schema_version: str = TELEMETRY_NORMALIZER_SCHEMA_VERSION
    bot_id: str = Field(min_length=1)
    base_url: str = Field(min_length=1)

    # Auth metadata — env-var names only, never values
    auth_type: str = Field(default="none")
    username_env: str | None = None
    password_env: str | None = None
    missing_env_vars: tuple[str, ...] = Field(default_factory=tuple)

    # Ping telemetry
    ping_status_code: int = Field(ge=0)
    ping_ok: bool
    ping_response_summary: str = Field(default="")

    # Status telemetry
    status_status_code: int = Field(ge=0, default=0)
    status_ok: bool = False
    status_response_summary: str = Field(default="")
    status_auth_outcome: str = Field(default="NOT_ATTEMPTED")
    status_open_trades: int = Field(ge=0, default=0)

    # Error / diagnostic metadata (redacted, safe)
    auth_error_summary: str = Field(default="")

    # Timing
    fetched_at_utc: str = Field(default="")


# ------------------------------------------------------------------
# Derived / computed models
# ------------------------------------------------------------------


class NormalizedEvidenceBundle(BaseModel):
    """Aggregate bundle of normalized telemetry across the fleet.

    This is the complete input to the fleet analyzer. It is JSON-safe,
    free of secrets, and carries the schema version so downstream
    consumers can assert compatibility.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: str = TELEMETRY_NORMALIZER_SCHEMA_VERSION
    cycle_id: str
    bots: tuple[NormalizedTelemetry, ...]
    total_bots: int


# ------------------------------------------------------------------
# Secret redaction helpers
# ------------------------------------------------------------------

SENSITIVE_KEYS: frozenset[str] = frozenset({
    "access_token",
    "refresh_token",
    "token",
    "password",
    "secret",
    "api_key",
    "api_secret",
    "private_key",
    "passphrase",
    "wallet_address",
    "mnemonic",
})


def redact_dict(raw: object) -> object:
    """Recursively redact sensitive keys from a parsed JSON value.

    This is a pure function (no I/O, no env vars). It operates on the
    already-decoded JSON value. Every key matching
    ``SENSITIVE_KEYS`` (case-insensitive) has its value replaced with
    ``"[REDACTED]"``.

    Args:
        raw: Parsed JSON value (dict, list, or primitive).

    Returns:
        The same structure with sensitive values redacted.
    """
    if isinstance(raw, dict):
        return {
            k: "[REDACTED]"
            if isinstance(k, str) and k.lower() in SENSITIVE_KEYS
            else redact_dict(v)
            for k, v in raw.items()
        }
    if isinstance(raw, list):
        return [redact_dict(item) for item in raw]
    return raw


def redact_response_summary(summary: str) -> str:
    """Redact sensitive key values from a JSON response summary string.

    If the summary is valid JSON, it is parsed, redacted, and re-serialized.
    Non-JSON summaries are returned unchanged (they should already be safe).

    Args:
        summary: The raw response summary string.

    Returns:
        A redacted-safe summary string.
    """
    if not summary or summary in ("empty_body",):
        return summary

    try:
        parsed = json.loads(summary)
    except (json.JSONDecodeError, ValueError, TypeError):
        # Non-JSON — assume already safe (connector error messages, etc.)
        return summary

    redacted = redact_dict(parsed)
    return json.dumps(redacted, sort_keys=True)


def redact_env_var_name(name: str | None) -> str | None:
    """Pass through env-var names unchanged (they are not secrets).

    This function exists as an explicit marker in the codebase: env-var
    NAMES are safe to record. Only env-var VALUES are secrets.
    """
    return name


def extract_open_trades(response_summary: str) -> int:
    """Best-effort extraction of open_trades count from a /status response.

    The Freqtrade ``/api/v1/status`` endpoint returns a list of open
    trades (array of objects) or a dict wrapper.

    Args:
        response_summary: The redacted response summary string.

    Returns:
        The number of open trades, or 0 if it cannot be determined.
    """
    if not response_summary:
        return 0
    try:
        parsed = json.loads(response_summary)
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0

    if isinstance(parsed, list):
        return len(parsed)
    if isinstance(parsed, dict):
        if isinstance(parsed.get("data"), list):
            return len(parsed["data"])
        if "open_trades" in parsed:
            try:
                return int(parsed["open_trades"])
            except (TypeError, ValueError):
                return 0
    return 0


# ------------------------------------------------------------------
# Normalizer factory
# ------------------------------------------------------------------


def normalize_raw_evidence(
    bot_id: str,
    base_url: str,
    ping_status_code: int,
    ping_response_summary: str,
    status_status_code: int,
    status_response_summary: str,
    status_auth_outcome: str,
    username_env: str | None = None,
    password_env: str | None = None,
    missing_env_vars: list[str] | None = None,
    auth_error_summary: str = "",
    fetched_at_utc: str = "",
    auth_type: str = "none",
) -> NormalizedTelemetry:
    """Transform raw Freqtrade REST telemetry into a stable normalized model.

    This is the single entry point for building ``NormalizedTelemetry``
    from raw connector outputs. It applies:

    1. Secret redaction on all response summaries (belt-and-suspenders
       with the connector's built-in redaction).
    2. Best-effort open-trades extraction.
    3. Stable model construction with ``extra='forbid'`` (catches field
       typos at construction time).

    Args:
        bot_id: Bot identifier from the registry.
        base_url: Bot base URL.
        ping_status_code: HTTP status from ``/api/v1/ping``.
        ping_response_summary: Raw ping response summary.
        status_status_code: HTTP status from ``/api/v1/status``.
        status_response_summary: Raw status response summary.
        status_auth_outcome: One of ``NOT_ATTEMPTED``, ``YELLOW_MISSING_ENV_VARS``,
            ``FAILED``, ``AUTHENTICATED``, ``AUTHENTICATED_NO_STATUS``.
        username_env: Env-var name holding the Freqtrade username (not value).
        password_env: Env-var name holding the Freqtrade password (not value).
        missing_env_vars: List of env-var names that were missing.
        auth_error_summary: Redacted error summary from the auth attempt.
        fetched_at_utc: ISO 8601 timestamp of the fetch.
        auth_type: Auth type from the registry (e.g. ``env_basic_jwt``).

    Returns:
        A ``NormalizedTelemetry`` with all sensitive fields redacted.
    """
    # Belt-and-suspenders: redact summaries even though the connector
    # already redacts them. This makes the normalizer independent of
    # the connector's redaction implementation.
    safe_ping = redact_response_summary(ping_response_summary)
    safe_status = redact_response_summary(status_response_summary)

    # Best-effort open trades extraction
    open_trades = extract_open_trades(safe_status)

    # The ping is "ok" if HTTP 200. The normalizer does not interpret
    # connection errors (status_code=0) as OK.
    ping_ok = ping_status_code == 200
    status_ok = status_status_code == 200

    return NormalizedTelemetry(
        bot_id=bot_id,
        base_url=base_url,
        auth_type=auth_type,
        username_env=redact_env_var_name(username_env),
        password_env=redact_env_var_name(password_env),
        missing_env_vars=tuple(missing_env_vars or []),
        ping_status_code=ping_status_code,
        ping_ok=ping_ok,
        ping_response_summary=safe_ping,
        status_status_code=status_status_code,
        status_ok=status_ok,
        status_response_summary=safe_status,
        status_auth_outcome=status_auth_outcome,
        status_open_trades=open_trades,
        auth_error_summary=auth_error_summary[:500] if auth_error_summary else "",
        fetched_at_utc=fetched_at_utc,
    )


# ------------------------------------------------------------------
# Utility: convert NormalizedTelemetry to BotEvidence for fleet_analyzer
# ------------------------------------------------------------------


def to_bot_evidence(
    telemetry: NormalizedTelemetry,
) -> dict[str, object]:
    """Convert ``NormalizedTelemetry`` to a dict compatible with fleet_analyzer.

    The fleet analyzer receives ``BotEvidence`` dataclass instances.
    This function converts the Pydantic-normalized form into a dict
    that can be passed to the analyzer's evidence constructor.

    Args:
        telemetry: Normalized telemetry for one bot.

    Returns:
        A dict matching the ``BotEvidence`` constructor signature.
    """
    return {
        "bot_id": telemetry.bot_id,
        "base_url": telemetry.base_url,
        "auth_type": telemetry.auth_type,
        "username_env": telemetry.username_env,
        "password_env": telemetry.password_env,
        "ping_endpoint": "/api/v1/ping",
        "ping_status_code": telemetry.ping_status_code,
        "ping_ok": telemetry.ping_ok,
        "ping_response_summary": telemetry.ping_response_summary[:200],
        "status_endpoint": "/api/v1/status",
        "status_status_code": telemetry.status_status_code,
        "status_ok": telemetry.status_ok,
        "status_response_summary": telemetry.status_response_summary[:200],
        "status_auth_outcome": telemetry.status_auth_outcome,
        "status_open_trades": telemetry.status_open_trades,
        "missing_env_vars": tuple(telemetry.missing_env_vars),
        "auth_error_summary": telemetry.auth_error_summary[:200] if telemetry.auth_error_summary else "",
        "fetched_at_utc": telemetry.fetched_at_utc,
    }
