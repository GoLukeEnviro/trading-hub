"""Read-only Freqtrade REST telemetry connector for SI v2.

Hard allowlist of GET-only endpoints. Rejects every non-GET method at the
code level. Supports optional JWT authentication via HTTP Basic Auth to
POST /api/v1/token/login. Tokens are held in memory only and never
persisted, printed, or logged.

Allowed endpoints (Phase 2 proof):
  - GET /api/v1/ping              (unauthenticated, health check)
  - GET /api/v1/status            (authenticated, read-only bot status)

Allowed POST (auth only):
  - POST /api/v1/token/login      (HTTP Basic Auth → JWT)

Every endpoint not in the respective allowlist is rejected with an error.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

# ------------------------------------------------------------------
# JSON-safe type aliases (no Any)
# ------------------------------------------------------------------
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]

# ---------------------------------------------------------------------------
# Hard allowlists — only specific methods to specific endpoints.
# ---------------------------------------------------------------------------
ALLOWED_GET_ENDPOINTS: Final[frozenset[str]] = frozenset({
    "/api/v1/ping",
    "/api/v1/status",
    "/api/v1/count",
    "/api/v1/profit",
    "/api/v1/performance",
    "/api/v1/daily",
    "/api/v1/whitelist",
    "/api/v1/version",
})

# /api/v1/ping does not require auth; all others do.
UNAUTHENTICATED_ENDPOINTS: Final[frozenset[str]] = frozenset({
    "/api/v1/ping",
})

# The only POST allowed — used for JWT token acquisition.
ALLOWED_POST_ENDPOINTS: Final[frozenset[str]] = frozenset({
    "/api/v1/token/login",
})

# Non-GET methods (other than the explicit login POST) are rejected outright.
ALLOWED_METHODS: Final[frozenset[str]] = frozenset({"GET", "POST"})

# Timeout for every request (seconds).
REQUEST_TIMEOUT: Final[int] = 5

# Maximum number of re-login attempts on HTTP 401.
MAX_REAUTH_ATTEMPTS: Final[int] = 1


@dataclass(frozen=True)
class FreqtradeSnapshot:
    """Immutable snapshot of a single Freqtrade REST GET call.

    Attributes:
        bot_id: Bot identifier from the registry.
        endpoint: The REST endpoint called (e.g. "/api/v1/ping").
        status_code: HTTP status code returned by the server.
        ok: True if status_code == 200.
        response_summary: Truncated string summary of the response body.
        fetched_at_utc: ISO 8601 timestamp of the fetch.
    """

    bot_id: str
    endpoint: str
    status_code: int
    ok: bool
    response_summary: str
    fetched_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class SIV2FreqtradeTelemetryConnector:
    """Strictly read-only connector to Freqtrade REST API.

    Every request is validated against the hard allowlist. Non-GET methods
    (except /api/v1/token/login) are rejected at the method-call level.

    Authentication (optional, per-bot):
      - Credentials are resolved from environment variable names declared
        in the bot registry's ``auth`` block.
      - On first authenticated call, ``token_login()`` is called with
        HTTP Basic Auth to POST /api/v1/token/login.
      - The JWT is stored in memory only (``_access_token``) and never
        written to disk, logs, or reports.
      - On HTTP 401, at most one re-login attempt is made, then fail-closed.
    """

    def __init__(
        self,
        base_url: str,
        bot_id: str,
        username_env: str | None = None,
        password_env: str | None = None,
    ) -> None:
        """Initialise with a Freqtrade bot endpoint and optional auth.

        Args:
            base_url: Base URL of the Freqtrade instance
                      (e.g. "http://trading-freqtrade-freqforge-1:8080").
            bot_id: Bot identifier used for logging and snapshots.
            username_env: Name of the environment variable holding the
                          Freqtrade username. If None, auth is disabled.
            password_env: Name of the environment variable holding the
                          Freqtrade password. If None, auth is disabled.

        Raises:
            ValueError: If base_url does not start with http:// or https://.
        """
        if not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise ValueError(
                f"base_url must start with http:// or https://; got {base_url!r}"
            )

        self._base_url = base_url.rstrip("/")
        self._bot_id = bot_id
        self._username_env = username_env
        self._password_env = password_env
        self._auth_bearer: str | None = None
        self._auth_enabled = username_env is not None and password_env is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def auth_enabled(self) -> bool:
        """Return True if auth credentials are configured for this bot."""
        return self._auth_enabled

    @property
    def authenticated(self) -> bool:
        """Return True if an in-memory JWT token is currently held."""
        return self._auth_bearer is not None

    def fetch_snapshot(self, endpoint: str) -> FreqtradeSnapshot:
        """Fetch a read-only snapshot from a single GET endpoint.

        For authenticated endpoints, performs token_login() if no token
        is held yet. On HTTP 401, retries once with a fresh token.

        Args:
            endpoint: The REST endpoint path (e.g. "/api/v1/ping").

        Returns:
            An immutable FreqtradeSnapshot with the response data.

        Raises:
            ValueError: If the endpoint is not in the hard allowlist.
            RuntimeError: If auth is required but env vars are missing.
        """
        self._validate_endpoint_get(endpoint)

        # Unauthenticated endpoints skip auth entirely.
        if endpoint in UNAUTHENTICATED_ENDPOINTS:
            return self._do_get(endpoint)

        # Authenticated endpoints require a token.
        if not self._auth_enabled:
            raise RuntimeError(
                f"Endpoint {endpoint!r} requires auth but no auth config "
                f"is set for bot {self._bot_id!r}. "
                f"Add an 'auth' block to the bot registry entry."
            )

        if self._auth_bearer is None:
            self._resolve_credentials()
            self.token_login()

        return self._do_get_authenticated(endpoint, reauth_remaining=MAX_REAUTH_ATTEMPTS)

    def token_login(self) -> None:
        """Authenticate via HTTP Basic Auth to POST /api/v1/token/login.

        Stores the JWT access_token in memory only. Never writes to disk
        or logs. Never prints secret values.

        Raises:
            RuntimeError: If auth env vars are not set, or if the login
                          request fails (non-200, network error).
        """
        self._resolve_credentials()

        login_url = f"{self._base_url}/api/v1/token/login"

        # Build Basic Auth header from env vars.
        username = os.environ[self._username_env]  # type: ignore[index]
        login_credential = os.environ[self._password_env]  # type: ignore[index]
        credentials = base64.b64encode(f"{username}:{login_credential}".encode()).decode()

        req = urllib.request.Request(
            login_url,
            method="POST",
            data=b"",  # POST with empty body
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                status_code = resp.status
                body_bytes = resp.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"token_login failed for {self._bot_id}: "
                f"HTTP {exc.code}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(
                f"token_login connection error for {self._bot_id}: {exc}"
            ) from exc

        if status_code != 200:
            raise RuntimeError(
                f"token_login unexpected status {status_code} for {self._bot_id}"
            )

        # Parse JWT from response — Freqtrade returns {"access_token": "...", "token_type": "Bearer"}
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError(
                f"token_login response parse error for {self._bot_id}: {exc}"
            ) from exc

        jwt_value = payload.get("access_token")
        if not jwt_value or not isinstance(jwt_value, str):
            raise RuntimeError(
                f"token_login response missing access_token for {self._bot_id}"
            )

        self._auth_bearer = jwt_value
        # NOTE: The bearer is never logged, printed, or persisted.

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_credentials(self) -> None:
        """Check that required auth env vars are present.

        Raises:
            RuntimeError: If any required env var is missing.
        """
        if not self._auth_enabled:
            return

        missing: list[str] = []
        if self._username_env and not os.environ.get(self._username_env):
            missing.append(self._username_env)
        if self._password_env and not os.environ.get(self._password_env):
            missing.append(self._password_env)

        if missing:
            raise RuntimeError(
                f"Missing required auth environment variables for bot "
                f"{self._bot_id!r}: {', '.join(missing)}"
            )

    def _validate_endpoint_get(self, endpoint: str) -> None:
        """Validate that the endpoint is in the GET hard allowlist.

        Args:
            endpoint: The REST endpoint path to validate.

        Raises:
            ValueError: If the endpoint is not allowed for GET.
        """
        if endpoint not in ALLOWED_GET_ENDPOINTS:
            raise ValueError(
                f"Endpoint {endpoint!r} is not in the GET hard allowlist. "
                f"Allowed: {sorted(ALLOWED_GET_ENDPOINTS)}"
            )

    def _do_get(self, endpoint: str) -> FreqtradeSnapshot:
        """Perform an unauthenticated GET request.

        Args:
            endpoint: The REST endpoint path.

        Returns:
            A FreqtradeSnapshot with the response data.
        """
        url = f"{self._base_url}{endpoint}"
        req = urllib.request.Request(url, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                status_code = resp.status
                body_bytes = resp.read()
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            body_bytes = exc.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return FreqtradeSnapshot(
                bot_id=self._bot_id,
                endpoint=endpoint,
                status_code=0,
                ok=False,
                response_summary=f"connection_error: {exc}",
            )

        response_summary = self._summarise(body_bytes)

        return FreqtradeSnapshot(
            bot_id=self._bot_id,
            endpoint=endpoint,
            status_code=status_code,
            ok=status_code == 200,
            response_summary=response_summary,
        )

    def _do_get_authenticated(
        self,
        endpoint: str,
        reauth_remaining: int,
    ) -> FreqtradeSnapshot:
        """Perform an authenticated GET request with Bearer token.

        On HTTP 401, performs one re-login attempt (fail-closed after).

        Args:
            endpoint: The REST endpoint path.
            reauth_remaining: Number of re-login retries left.

        Returns:
            A FreqtradeSnapshot with the response data.
        """
        url = f"{self._base_url}{endpoint}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {self._auth_bearer}")

        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                status_code = resp.status
                body_bytes = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and reauth_remaining > 0:
                # Token expired — re-login once, then retry.
                self._auth_bearer = None
                self.token_login()
                return self._do_get_authenticated(
                    endpoint, reauth_remaining=reauth_remaining - 1
                )
            status_code = exc.code
            body_bytes = exc.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return FreqtradeSnapshot(
                bot_id=self._bot_id,
                endpoint=endpoint,
                status_code=0,
                ok=False,
                response_summary=f"connection_error: {exc}",
            )

        response_summary = self._summarise(body_bytes)

        return FreqtradeSnapshot(
            bot_id=self._bot_id,
            endpoint=endpoint,
            status_code=status_code,
            ok=status_code == 200,
            response_summary=response_summary,
        )

    @staticmethod
    def _summarise(body_bytes: bytes) -> str:
        """Truncate and summarise a response body for the snapshot.

        Sensitive fields (access_token, refresh_token, token) are redacted.

        Args:
            body_bytes: Raw response bytes.

        Returns:
            A string summary, truncated to 500 characters.
        """
        if not body_bytes:
            return "empty_body"

        try:
            text = body_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return f"binary_body({len(body_bytes)} bytes)"

        # Try to pretty-print JSON with sensitive field redaction
        try:
            parsed: JsonValue = json.loads(text)
            text = SIV2FreqtradeTelemetryConnector._redact_sensitive(parsed)
            text = json.dumps(text, sort_keys=True)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        if len(text) > 500:
            text = text[:500] + "... [truncated]"

        return text

    @staticmethod
    def _redact_sensitive(obj: JsonValue) -> JsonValue:
        """Recursively redact sensitive fields from parsed JSON.

        Redacts keys matching: access_token, refresh_token, token, password.

        Args:
            obj: Parsed JSON value (dict, list, or primitive).

        Returns:
            The object with sensitive values replaced by "[REDACTED]".
        """
        sensitive_keys = {"access_token", "refresh_token", "token", "password"}

        if isinstance(obj, dict):
            return {
                k: "[REDACTED]" if k.lower() in sensitive_keys else SIV2FreqtradeTelemetryConnector._redact_sensitive(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [SIV2FreqtradeTelemetryConnector._redact_sensitive(item) for item in obj]
        return obj
