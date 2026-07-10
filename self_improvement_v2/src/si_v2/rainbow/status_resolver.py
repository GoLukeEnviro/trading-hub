"""Rainbow provider status resolver.

Maps the current client configuration and health state into a
provider status string used by the Active Cycle evidence pipeline.

Status values:
- DISABLED: Client is not enabled (default).
- FIXTURE_ONLY: Client is enabled in fixture mode (no network calls).
- CONFIGURED: Client is enabled in read_only mode with a valid base_url.
- DEGRADED: Client is enabled in read_only mode but health check failed
  or the provider is unreachable.
- UNAVAILABLE: Health check failed 3+ consecutive times.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


class ProviderStatus:
    """Read-only provider status constants."""

    DISABLED = "DISABLED"
    FIXTURE_ONLY = "FIXTURE_ONLY"
    CONFIGURED = "CONFIGURED"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class ProviderHealthEvidence:
    """Health/freshness evidence artifact emitted per Active Cycle."""

    provider_id: str
    status: str
    mode: str
    endpoint: str
    base_url_configured: bool
    consecutive_failures: int = 0
    last_checked_utc: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "status": self.status,
            "mode": self.mode,
            "endpoint": self.endpoint,
            "base_url_configured": self.base_url_configured,
            "consecutive_failures": self.consecutive_failures,
            "last_checked_utc": self.last_checked_utc,
            "errors": list(self.errors),
        }


class RainbowStatusResolver:
    """Resolve Rainbow provider status from client configuration and health."""

    def __init__(self, max_consecutive_failures: int = 3) -> None:
        self._max_failures = max_consecutive_failures
        self._consecutive_failures: int = 0
        self._last_checked_utc: str = ""

    def resolve(
        self,
        enabled: bool,
        mode: str,
        base_url: str | None,
        endpoint: str,
        provider_id: str = "rainbow",
    ) -> ProviderHealthEvidence:
        """Resolve provider status from configuration parameters.

        This is a read-only, deterministic check. No network calls are made.
        """
        self._last_checked_utc = datetime.now(UTC).isoformat()

        if not enabled:
            return ProviderHealthEvidence(
                provider_id=provider_id,
                status=ProviderStatus.DISABLED,
                mode=mode,
                endpoint=endpoint,
                base_url_configured=False,
                last_checked_utc=self._last_checked_utc,
            )

        if mode == "fixture":
            return ProviderHealthEvidence(
                provider_id=provider_id,
                status=ProviderStatus.FIXTURE_ONLY,
                mode=mode,
                endpoint=endpoint,
                base_url_configured=False,
                last_checked_utc=self._last_checked_utc,
            )

        if mode == "read_only":
            if not base_url:
                return ProviderHealthEvidence(
                    provider_id=provider_id,
                    status=ProviderStatus.DEGRADED,
                    mode=mode,
                    endpoint=endpoint,
                    base_url_configured=False,
                    errors=["read_only mode requires base_url"],
                    last_checked_utc=self._last_checked_utc,
                )

            return ProviderHealthEvidence(
                provider_id=provider_id,
                status=ProviderStatus.CONFIGURED,
                mode=mode,
                endpoint=endpoint,
                base_url_configured=True,
                last_checked_utc=self._last_checked_utc,
            )

        return ProviderHealthEvidence(
            provider_id=provider_id,
            status=ProviderStatus.DISABLED,
            mode=mode,
            endpoint=endpoint,
            base_url_configured=False,
            errors=[f"Unknown mode: {mode}"],
            last_checked_utc=self._last_checked_utc,
        )

    def record_failure(self) -> None:
        """Record a consecutive health check failure."""
        self._consecutive_failures += 1

    def record_success(self) -> None:
        """Reset the consecutive failure counter on success."""
        self._consecutive_failures = 0

    @property
    def is_unavailable(self) -> bool:
        """True when consecutive failures exceed the threshold."""
        return self._consecutive_failures >= self._max_failures

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
