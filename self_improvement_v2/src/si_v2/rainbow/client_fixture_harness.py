"""Read-only client fixture harness for Rainbow signals.

Wraps the existing RainbowSignalProviderClient in fixture-only mode,
providing a simplified interface for loading, validating, and accessing
signal envelopes from local fixture files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from si_v2.rainbow.client import (
    RainbowClientConfig,
    RainbowSignalProviderClient,
)

# ── Harness result ────────────────────────────────────────────────────────────


@dataclass
class FixtureHarnessResult:
    """Result from the fixture harness."""

    total_fixtures: int = 0
    valid_signals: int = 0
    malformed_signals: int = 0
    errors: list[str] = field(default_factory=list)
    signals: list[dict[str, object]] = field(default_factory=list)
    source: str = "fixture_harness"


# ── Harness ───────────────────────────────────────────────────────────────────


class RainbowClientFixtureHarness:
    """Simplified fixture harness wrapping the #80 read-only client.

    Usage::

        harness = RainbowClientFixtureHarness(
            fixture_dir=Path("self_improvement_v2/fixtures/rainbow-signals"),
        )
        result = harness.run()
    """

    def __init__(self, fixture_dir: Path) -> None:
        self._fixture_dir = fixture_dir

    def run(self) -> FixtureHarnessResult:
        """Load fixtures through the #80 client and collect results."""
        config = RainbowClientConfig(
            enabled=True,
            mode="fixture",
            fixture_path=str(self._fixture_dir),
        )
        client = RainbowSignalProviderClient.from_config(config)

        # Try to load from fixture path
        load_result = client.load_from_fixture_path(self._fixture_dir)

        signals = load_result.signals
        errors = list(load_result.errors)

        # Determine malformed count from errors mentioning FAILED
        malformed = sum(
            1
            for e in errors
            if "FAILED" in e or "malformed" in e.lower()
        )

        return FixtureHarnessResult(
            total_fixtures=len(load_result.signals)
            + malformed,
            valid_signals=len(load_result.signals),
            malformed_signals=malformed,
            errors=errors,
            signals=signals,
        )

    def get_valid_signals(self) -> list[dict[str, object]]:
        """Return only valid (validated) signals."""
        result = self.run()
        return result.signals
