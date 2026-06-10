"""Rainbow Signal Source Status for SI v2 status reporting.

Defines the operational status modes for the Rainbow signal provider
within the SI v2 system. The default status is always ``disabled``
to ensure safe startup without explicit opt-in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# ── Status modes ─────────────────────────────────────────────────────────────


class RainbowStatusMode(Enum):
    """Operational status of the Rainbow signal provider.

    Modes represent increasing levels of capability:

    * ``DISABLED`` — Rainbow is not available. All client calls return empty.
    * ``FIXTURE_ONLY`` — Only fixture/offline mode is available. No live
      signals.
    * ``CONFIGURED`` — A live provider is configured and reachable.
    * ``DEGRADED`` — Something is wrong (missing contract, stale fixtures,
      drift detected).
    """

    DISABLED = "disabled"
    FIXTURE_ONLY = "fixture_only"
    CONFIGURED = "configured"
    DEGRADED = "degraded"


# ── Component status ─────────────────────────────────────────────────────────


@dataclass
class RainbowComponentStatus:
    """Status of a single Rainbow component."""

    name: str
    available: bool
    details: str = ""


# ── Rainbow status ───────────────────────────────────────────────────────────


@dataclass
class RainbowSourceStatus:
    """Aggregated Rainbow source status for SI v2 reporting."""

    mode: RainbowStatusMode
    contract_available: bool
    fixtures_available: bool
    validator_available: bool
    drift_guard_available: bool
    fixture_report_available: bool
    drift_verdict: str  # green / yellow / red / unknown
    components: list[RainbowComponentStatus] = field(default_factory=list)
    details: str = ""


# ── Status resolver ──────────────────────────────────────────────────────────


class RainbowStatusResolver:
    """Resolve current Rainbow source status from local artifacts.

    This is a purely offline check — no network, Docker, or runtime calls.
    """

    def __init__(
        self,
        contract_dir: Path | None = None,
        fixture_dir: Path | None = None,
        drift_report_path: Path | None = None,
        fixture_report_path: Path | None = None,
    ) -> None:
        self._contract_dir = contract_dir or Path(
            "self_improvement_v2/contracts"
        )
        self._fixture_dir = fixture_dir or Path(
            "self_improvement_v2/fixtures/rainbow-signals"
        )
        self._drift_report_path = drift_report_path or Path(
            "self_improvement_v2/reports/rainbow/contract_drift_report.md"
        )
        self._fixture_report_path = fixture_report_path or Path(
            "self_improvement_v2/reports/rainbow/fixture_review_report.md"
        )

    def resolve(self) -> RainbowSourceStatus:
        """Resolve current status without I/O to external services."""
        components: list[RainbowComponentStatus] = []

        # ── Contract snapshot ───────────────────────────────────────────
        contract_available = (
            self._contract_dir / "rainbow_signal_envelope.schema.json"
        ).exists()
        components.append(
            RainbowComponentStatus(
                name="contract_snapshot",
                available=contract_available,
                details=(
                    "Schema found"
                    if contract_available
                    else "Schema missing"
                ),
            )
        )

        # ── Fixtures ────────────────────────────────────────────────────
        fixture_count = len(list(self._fixture_dir.glob("*.json")))
        fixtures_available = fixture_count >= 7
        components.append(
            RainbowComponentStatus(
                name="fixtures",
                available=fixtures_available,
                details=(
                    f"{fixture_count} fixtures found"
                    if fixtures_available
                    else f"{fixture_count} fixtures (need >= 7)"
                ),
            )
        )

        # ── Validator ───────────────────────────────────────────────────
        validator_available = True
        try:
            from si_v2.rainbow.validator import (
                RainbowSignalEnvelopeValidator,
            )

            # Try instantiation
            _ = RainbowSignalEnvelopeValidator()
        except (ImportError, Exception):
            validator_available = False
        components.append(
            RainbowComponentStatus(
                name="validator",
                available=validator_available,
                details=(
                    "Importable and instantiable"
                    if validator_available
                    else "Import failed"
                ),
            )
        )

        # ── Drift guard ─────────────────────────────────────────────────
        drift_guard_available = True
        try:
            from si_v2.rainbow.drift_guard import (  # noqa: F401
                RainbowContractDriftGuard,
            )
        except (ImportError, Exception):
            drift_guard_available = False
        components.append(
            RainbowComponentStatus(
                name="drift_guard",
                available=drift_guard_available,
                details=(
                    "Importable"
                    if drift_guard_available
                    else "Import failed"
                ),
            )
        )

        # ── Drift verdict ───────────────────────────────────────────────
        drift_verdict = "unknown"
        if self._drift_report_path.exists():
            content = self._drift_report_path.read_text()
            if "GREEN" in content:
                drift_verdict = "green"
            elif "YELLOW" in content:
                drift_verdict = "yellow"
            elif "RED" in content:
                drift_verdict = "red"
        components.append(
            RainbowComponentStatus(
                name="drift_verdict",
                available=drift_verdict != "unknown",
                details=f"Last drift report: {drift_verdict}",
            )
        )

        # ── Fixture report ──────────────────────────────────────────────
        fixture_report_available = self._fixture_report_path.exists()
        components.append(
            RainbowComponentStatus(
                name="fixture_report",
                available=fixture_report_available,
                details=(
                    "Report found"
                    if fixture_report_available
                    else "Report missing"
                ),
            )
        )

        # ── Determine mode ──────────────────────────────────────────────
        if not contract_available or not fixtures_available:
            mode = RainbowStatusMode.DISABLED
            details = "Rainbow disabled: missing core artifacts"
        elif not validator_available or drift_verdict == "red":
            mode = RainbowStatusMode.DEGRADED
            details = (
                "Rainbow degraded: validator or drift check failed"
            )
        elif drift_verdict == "yellow":
            mode = RainbowStatusMode.DEGRADED
            details = "Rainbow degraded: minor drift detected"
        else:
            mode = RainbowStatusMode.FIXTURE_ONLY
            details = (
                "Rainbow active in fixture-only mode. "
                "Configure provider for live signals."
            )

        return RainbowSourceStatus(
            mode=mode,
            contract_available=contract_available,
            fixtures_available=fixtures_available,
            validator_available=validator_available,
            drift_guard_available=drift_guard_available,
            fixture_report_available=fixture_report_available,
            drift_verdict=drift_verdict,
            components=components,
            details=details,
        )
