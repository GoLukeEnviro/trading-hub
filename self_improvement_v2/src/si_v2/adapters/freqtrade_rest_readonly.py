"""Read-only Freqtrade REST telemetry connector for SI v2.

Hard allowlist of GET-only endpoints. Rejects every non-GET method at the
code level. No auth, no retries, no persistence to a telemetry store.

Allowed endpoints (Phase 2 proof):
  - GET /api/v1/ping              (unauthenticated, health check)
  - GET /api/v1/status            (optional, safe read-only)

Every endpoint not in ALLOWED_ENDPOINTS is rejected with an explicit error.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

# ---------------------------------------------------------------------------
# Hard allowlist — only GET endpoints. Add new endpoints here after review.
# ---------------------------------------------------------------------------
ALLOWED_ENDPOINTS: Final[frozenset[str]] = frozenset({
    "/api/v1/ping",
    "/api/v1/status",
})

# Non-GET methods are rejected outright.
ALLOWED_METHODS: Final[frozenset[str]] = frozenset({"GET"})

# Timeout for every request (seconds).
REQUEST_TIMEOUT: Final[int] = 5


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
    are rejected at the method-call level, not at the HTTP level.
    """

    def __init__(self, base_url: str, bot_id: str) -> None:
        """Initialise with a Freqtrade bot endpoint.

        Args:
            base_url: Base URL of the Freqtrade instance
                      (e.g. "http://127.0.0.1:8086").
            bot_id: Bot identifier used for logging and snapshots.

        Raises:
            ValueError: If base_url does not start with http:// or https://.
        """
        if not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise ValueError(
                f"base_url must start with http:// or https://; got {base_url!r}"
            )

        self._base_url = base_url.rstrip("/")
        self._bot_id = bot_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_snapshot(self, endpoint: str) -> FreqtradeSnapshot:
        """Fetch a read-only snapshot from a single GET endpoint.

        Args:
            endpoint: The REST endpoint path (e.g. "/api/v1/ping").

        Returns:
            An immutable FreqtradeSnapshot with the response data.

        Raises:
            ValueError: If the endpoint is not in the hard allowlist.
        """
        self._validate_endpoint(endpoint)

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_endpoint(self, endpoint: str) -> None:
        """Validate that the endpoint is in the hard allowlist.

        Args:
            endpoint: The REST endpoint path to validate.

        Raises:
            ValueError: If the endpoint is not allowed.
        """
        if endpoint not in ALLOWED_ENDPOINTS:
            raise ValueError(
                f"Endpoint {endpoint!r} is not in the hard allowlist. "
                f"Allowed: {sorted(ALLOWED_ENDPOINTS)}"
            )

    @staticmethod
    def _summarise(body_bytes: bytes) -> str:
        """Truncate and summarise a response body for the snapshot.

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

        # Try to pretty-print JSON
        try:
            parsed = json.loads(text)
            text = json.dumps(parsed, sort_keys=True)
        except (json.JSONDecodeError, ValueError):
            pass

        if len(text) > 500:
            text = text[:500] + "... [truncated]"

        return text
