"""Read-only Rainbow Signal Provider Client.

Provides offline/fixture-based access to Rainbow signal envelopes.
The client is **disabled by default** and requires explicit opt-in.

Safety boundaries:
- No trading decisions.
- No Shadowlock writes.
- No network calls in fixture mode.
- No secrets required.
- Returns validator-compatible envelopes only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────


@dataclass
class RainbowClientConfig:
    """Configuration for RainbowSignalProviderClient.

    The default configuration is **disabled** — all access returns empty.
    """

    enabled: bool = False
    """Master switch. When ``False``, all client calls return empty."""

    mode: str = "fixture"
    """Operation mode: ``fixture``, ``disabled``, or ``read_only``.

    * ``fixture`` — loads local fixture files. No network calls.
    * ``read_only`` — live provider mode. Requires explicit opt-in.
    * ``disabled`` — no signals returned.
    """

    fixture_path: str | None = None
    """Path to fixture directory. Required in ``fixture`` mode."""

    provider_id: str = "rainbow"
    """Provider identifier for source tracking."""

    max_records: int | None = None
    """Optional limit on returned signals. ``None`` = no limit."""

    timeout_seconds: int = 30
    """Timeout for live provider calls. Unused in fixture mode."""


# ── Result ────────────────────────────────────────────────────────────────────


@dataclass
class RainbowClientResult:
    """Result from a Rainbow client call."""

    signals: list[dict[str, object]]
    """Validated signal envelopes."""

    errors: list[str] = field(default_factory=list)
    """Non-fatal errors encountered during loading/validation."""

    source: str = "fixture"
    """Source of the signals: ``fixture``, ``live``, or ``empty``."""

    count: int = 0
    """Number of valid signals returned."""


# ── Client ────────────────────────────────────────────────────────────────────


class RainbowSignalProviderClient:
    """Read-only Rainbow Signal Provider Client.

    Usage (fixture mode)::

        config = RainbowClientConfig(
            enabled=True,
            mode="fixture",
            fixture_path="self_improvement_v2/fixtures/rainbow-signals",
        )
        client = RainbowSignalProviderClient.from_config(config)
        result = client.get_latest_signals()
    """

    def __init__(
        self,
        config: RainbowClientConfig | None = None,
    ) -> None:
        self._config = config or RainbowClientConfig()
        self._fixtures: list[dict[str, object]] = []

    # ── Factory ─────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, config: RainbowClientConfig) -> RainbowSignalProviderClient:
        """Create a client from configuration.

        In ``fixture`` mode, immediately loads and validates fixtures.
        In ``disabled`` mode, returns an inactive client.
        """
        client = cls(config=config)

        if not config.enabled:
            return client

        if config.mode == "fixture":
            fixture_path = config.fixture_path
            if fixture_path:
                client.load_from_fixture_path(Path(fixture_path))

        return client

    # ── Fixture loading ─────────────────────────────────────────────────

    def load_from_fixture_path(self, path: Path) -> RainbowClientResult:
        """Load all JSON fixtures from a directory.

        Automatically validates each fixture through the #79 validator.
        Malformed fixtures are excluded from the signal list with errors.
        """
        if not self._config.enabled:
            return RainbowClientResult(
                signals=[],
                errors=["Client is disabled"],
                source="empty",
            )

        errors: list[str] = []
        signals: list[dict[str, object]] = []

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
                errors.append(
                    f"Failed to load {fixture_path.name}"
                )
                continue

            # Validate through #79 validator
            result = self._validate_envelope(envelope)
            if result is None:
                # Validator unavailable — still include signal
                signals.append(envelope)
            elif "error" in result:
                errors.append(
                    f"{fixture_path.name}: {result['error']}"
                )
                continue
            elif result.get("verdict") == "fail":
                errors.append(
                    f"{fixture_path.name}: validation FAILED "
                    f"({len(result.get('errors', []))} errors)"
                )
                continue
            else:
                signals.append(envelope)

        self._fixtures = signals

        return RainbowClientResult(
            signals=signals,
            errors=errors,
            source="fixture",
            count=len(signals),
        )

    # ── Signal access ───────────────────────────────────────────────────

    def get_latest_signals(
        self,
    ) -> RainbowClientResult:
        """Return the currently loaded signals.

        In ``disabled`` mode, returns empty.
        """
        if not self._config.enabled:
            return RainbowClientResult(
                signals=[],
                errors=["Client is disabled"],
                source="empty",
            )

        signals = self._fixtures
        if self._config.max_records is not None:
            signals = signals[: self._config.max_records]

        return RainbowClientResult(
            signals=signals,
            source="fixture" if self._fixtures else "empty",
            count=len(signals),
        )

    def validate_signals(
        self,
    ) -> list[dict[str, object]]:
        """Run the #79 validator on all loaded signals.

        Returns a list of validation result dicts.
        """
        results: list[dict[str, object]] = []
        for signal in self._fixtures:
            result = self._validate_envelope(signal)
            if result is not None:
                results.append(result)
        return results

    # ── Internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _load_fixture(path: Path) -> dict[str, object] | None:
        """Load a single JSON fixture, returning None on failure."""
        try:
            with open(path) as f:
                return dict(json.load(f))
        except (json.JSONDecodeError, OSError, Exception):
            return None

    @staticmethod
    def _validate_envelope(
        envelope: dict[str, object],
    ) -> dict[str, object] | None:
        """Validate a single envelope through the #79 validator.

        Returns the validation result as a dict, or ``None`` if the
        validator is unavailable.
        """
        try:
            from si_v2.rainbow.validator import (
                RainbowSignalEnvelopeValidator,
            )

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
