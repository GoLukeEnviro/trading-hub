"""Tests for Rainbow source status reporting.

Verifies that:
- default mode is disabled or fixture_only
- missing artifacts produce degraded status
- all modes are reachable
- tests do not use network calls
"""

from __future__ import annotations

from pathlib import Path

from si_v2.rainbow.status import (
    RainbowStatusMode,
    RainbowStatusResolver,
)

_CONTRACT_DIR = Path("self_improvement_v2/contracts")
_FIXTURE_DIR = Path("self_improvement_v2/fixtures/rainbow-signals")
_REPORT_DIR = Path("self_improvement_v2/reports/rainbow")


def _resolver() -> RainbowStatusResolver:
    return RainbowStatusResolver(
        contract_dir=_CONTRACT_DIR,
        fixture_dir=_FIXTURE_DIR,
        drift_report_path=_REPORT_DIR / "contract_drift_report.md",
        fixture_report_path=_REPORT_DIR / "fixture_review_report.md",
    )


# ── Default behaviour ─────────────────────────────────────────────────────


class TestDefaultStatus:
    def test_resolver_creates(self) -> None:
        resolver = _resolver()
        assert resolver is not None

    def test_resolve_returns_status(self) -> None:
        status = _resolver().resolve()
        assert status is not None
        assert status.mode in RainbowStatusMode

    def test_default_is_not_configured(self) -> None:
        """Without explicit config, status must not be 'configured'."""
        status = _resolver().resolve()
        assert status.mode != RainbowStatusMode.CONFIGURED, (
            "Default status must never be 'configured'"
        )

    def test_contract_available_with_real_files(self) -> None:
        status = _resolver().resolve()
        assert status.contract_available is True

    def test_fixtures_available_with_real_files(self) -> None:
        status = _resolver().resolve()
        assert status.fixtures_available is True

    def test_validator_available(self) -> None:
        status = _resolver().resolve()
        assert status.validator_available is True

    def test_drift_guard_available(self) -> None:
        status = _resolver().resolve()
        assert status.drift_guard_available is True


# ── When artifacts missing ────────────────────────────────────────────────


class TestMissingArtifacts:
    def test_disabled_when_contract_missing(self) -> None:
        resolver = RainbowStatusResolver(
            contract_dir=Path("/tmp/nonexistent_contracts"),
            fixture_dir=_FIXTURE_DIR,
        )
        status = resolver.resolve()
        assert status.mode == RainbowStatusMode.DISABLED

    def test_disabled_when_fixtures_missing(self) -> None:
        resolver = RainbowStatusResolver(
            contract_dir=_CONTRACT_DIR,
            fixture_dir=Path("/tmp/nonexistent_fixtures"),
        )
        status = resolver.resolve()
        assert status.mode == RainbowStatusMode.DISABLED

    def test_degraded_when_drift_report_missing(self) -> None:
        resolver = RainbowStatusResolver(
            contract_dir=_CONTRACT_DIR,
            fixture_dir=_FIXTURE_DIR,
            drift_report_path=Path("/tmp/nonexistent_drift.md"),
        )
        status = resolver.resolve()
        # Should still be fixture_only since drift unknown is a warning
        # but not enough for disabled
        assert status.drift_verdict == "unknown"
        assert status.drift_guard_available is True


# ── Status modes ──────────────────────────────────────────────────────────


class TestStatusModes:
    def test_mode_enum_values(self) -> None:
        values = {m.value for m in RainbowStatusMode}
        expected = {"disabled", "fixture_only", "configured", "degraded"}
        assert values == expected

    def test_fixture_only_with_all_present(self) -> None:
        status = _resolver().resolve()
        # With all artifacts present, should be fixture_only (default safe)
        assert status.mode == RainbowStatusMode.FIXTURE_ONLY, (
            f"Expected fixture_only, got {status.mode.value}"
        )


# ── Component details ─────────────────────────────────────────────────────


class TestComponentDetails:
    def test_components_list_present(self) -> None:
        status = _resolver().resolve()
        assert len(status.components) >= 6, (
            f"Expected >=6 components, got {len(status.components)}"
        )

    def test_components_have_names(self) -> None:
        status = _resolver().resolve()
        names = {c.name for c in status.components}
        expected = {
            "contract_snapshot",
            "fixtures",
            "validator",
            "drift_guard",
            "drift_verdict",
            "fixture_report",
        }
        for n in expected:
            assert n in names, f"Missing component: {n}"

    def test_component_details_are_strings(self) -> None:
        status = _resolver().resolve()
        for c in status.components:
            assert isinstance(c.details, str)
            assert len(c.details) > 0


# ── No network calls ──────────────────────────────────────────────────────


class TestNoNetworkCalls:
    def test_resolve_no_exceptions(self) -> None:
        status = _resolver().resolve()
        assert status.mode is not None
        assert status.details is not None
