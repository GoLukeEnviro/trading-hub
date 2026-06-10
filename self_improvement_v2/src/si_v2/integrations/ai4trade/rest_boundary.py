"""REST client adapter for the ai4trade REST API boundary.

Provides a NetworkGuard to validate URLs (localhost only, http scheme only)
and an Ai4tradeRestBoundaryClient that makes HTTP calls to a hypothetical
ai4trade-bot Rainbow API server.

All client methods are fail-closed: they return None or raise typed
exceptions on any error. No automatic retries. No env var reading.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from si_v2.integrations.ai4trade.protocols import AdvisorySignal
from si_v2.integrations.ai4trade.rest_models import (
    HealthResponse,
    OutcomeResponse,
    RiskGateRequest,
    RiskGateResponse,
    SignalResponse,
)


class NetworkGuard:
    """Validates URLs for safe outbound HTTP connections.

    Only allows http://127.0.0.1 and http://localhost.
    Rejects: non-http schemes, credentials in URL, path traversal, file://.
    """

    ALLOWED_HOSTS = ("127.0.0.1", "localhost")

    @staticmethod
    def validate_url(url: str) -> str:
        """Validate a URL for safe outbound use.

        Args:
            url: The URL to validate.

        Returns:
            The validated URL string.

        Raises:
            ValueError: If the URL violates any safety rule.
        """
        parsed = urlparse(url)

        if parsed.scheme != "http":
            raise ValueError(f"Only http scheme allowed, got '{parsed.scheme}'")

        if parsed.hostname not in NetworkGuard.ALLOWED_HOSTS:
            raise ValueError(f"Only 127.0.0.1 and localhost allowed, got '{parsed.hostname}'")

        if parsed.username or parsed.password:
            raise ValueError("URL must not contain credentials")

        path = parsed.path
        if ".." in path or path.startswith("~"):
            raise ValueError("Path traversal not allowed")

        return url


class Ai4tradeRestBoundaryClient:
    """HTTP client for the ai4trade REST API.

    All methods are fail-closed. Does NOT discover services or read env vars.
    """

    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        NetworkGuard.validate_url(base_url)
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def get_health(self) -> HealthResponse | None:
        """GET /health — returns HealthResponse or None on failure."""
        data = self._get_dict("/health")
        if data is None:
            return None
        try:
            return HealthResponse.model_validate(data)
        except (ValidationError, TypeError, ValueError):
            return None

    def get_latest_signal(self, asset: str) -> SignalResponse | None:
        """GET /signals/latest?asset=... — returns latest signal or None."""
        items = self._get_list(f"/signals/latest?asset={asset}")
        if items is None or not items:
            return None
        try:
            return SignalResponse.model_validate(items[-1])  # last = latest
        except (ValidationError, TypeError, ValueError):
            return None

    def get_signal_by_id(self, signal_id: str) -> SignalResponse | None:
        """GET /signals/{signal_id} — returns SignalResponse or None."""
        data = self._get_dict(f"/signals/{signal_id}")
        if data is None:
            return None
        try:
            return SignalResponse.model_validate(data)
        except (ValidationError, TypeError, ValueError):
            return None

    def get_outcome(self, signal_id: str) -> OutcomeResponse | None:
        """GET /outcomes/{signal_id} — returns OutcomeResponse or None."""
        data = self._get_dict(f"/outcomes/{signal_id}")
        if data is None:
            return None
        try:
            return OutcomeResponse.model_validate(data)
        except (ValidationError, TypeError, ValueError):
            return None

    def evaluate_risk(self, signal: AdvisorySignal) -> RiskGateResponse | None:
        """POST /risk/evaluate — returns RiskGateResponse or None."""
        try:
            req = RiskGateRequest(signal=signal)
            req_data = req.model_dump(mode="json")
            data = self._post_dict("/risk/evaluate", req_data)
            if data is None:
                return None
            return RiskGateResponse.model_validate(data)
        except (ValidationError, TypeError, ValueError):
            return None

    def _get_dict(self, path: str) -> dict[str, object] | None:
        """Make a GET request expecting a JSON object."""
        return self._request("GET", path)

    def _get_list(self, path: str) -> list[dict[str, object]] | None:
        """Make a GET request expecting a JSON array."""
        try:
            url = f"{self._base_url}{path}"
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url)
            if response.status_code >= 400:
                return None
            parsed = response.json()
            if not isinstance(parsed, list):
                return None
            result: list[dict[str, object]] = []
            for item in parsed:
                if isinstance(item, dict):
                    result.append(item)
            return result
        except (httpx.TimeoutException, httpx.RequestError, json.JSONDecodeError):
            return None

    def _post_dict(self, path: str, body: dict[str, object]) -> dict[str, object] | None:
        """Make a POST request expecting a JSON object."""
        try:
            url = f"{self._base_url}{path}"
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=body)
            if response.status_code >= 400:
                return None
            parsed = response.json()
            if not isinstance(parsed, dict):
                return None
            return parsed
        except (httpx.TimeoutException, httpx.RequestError, json.JSONDecodeError):
            return None

    def _request(self, method: str, path: str) -> dict[str, object] | None:
        """Low-level GET returning a dict or None."""
        try:
            url = f"{self._base_url}{path}"
            with httpx.Client(timeout=self._timeout) as client:
                if method == "GET":
                    response = client.get(url)
                else:
                    return None
            if response.status_code >= 400:
                return None
            parsed = response.json()
            if not isinstance(parsed, dict):
                return None
            return parsed
        except (httpx.TimeoutException, httpx.RequestError, json.JSONDecodeError):
            return None


__all__ = [
    "Ai4tradeRestBoundaryClient",
    "NetworkGuard",
]
