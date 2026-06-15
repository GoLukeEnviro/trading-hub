from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
MAIN_COMPOSE = ROOT / "docker-compose.yml"
FLEET_COMPOSE = ROOT / "freqtrade" / "docker-compose.fleet.yml"

FREQTRADE_FLEET_SERVICES = [
    "freqtrade-rsi",
    "freqtrade-momentum",
    "freqtrade-regime-hybrid",
    "freqforge-canary",
]

# Expected dashboard build context and Dockerfile
DASHBOARD_BUILD_CONTEXT = "docker/dashboard"
DASHBOARD_DOCKERFILE = "Dockerfile"


@pytest.fixture(scope="module")
def main_compose() -> dict:
    with MAIN_COMPOSE.open() as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def fleet_compose() -> dict:
    with FLEET_COMPOSE.open() as f:
        return yaml.safe_load(f)


class TestDockerComposeContracts:
    def test_compose_files_exist(self) -> None:
        assert MAIN_COMPOSE.exists()
        assert FLEET_COMPOSE.exists()

    def test_fleet_has_all_four_bots(self, fleet_compose: dict) -> None:
        services = fleet_compose["services"]
        for service_name in FREQTRADE_FLEET_SERVICES:
            assert service_name in services

    @pytest.mark.parametrize("service_name", FREQTRADE_FLEET_SERVICES)
    def test_fleet_services_run_as_non_root(self, fleet_compose: dict, service_name: str) -> None:
        svc = fleet_compose["services"][service_name]
        assert svc.get("user") == "10000:10000"

    @pytest.mark.parametrize("service_name", FREQTRADE_FLEET_SERVICES)
    def test_fleet_services_bind_to_localhost_only(self, fleet_compose: dict, service_name: str) -> None:
        ports = fleet_compose["services"][service_name].get("ports", [])
        assert ports, f"{service_name} must publish a localhost-only port"
        port_text = " ".join(str(p) for p in ports)
        assert "127.0.0.1" in port_text
        assert "0.0.0.0" not in port_text

    @pytest.mark.parametrize("service_name", FREQTRADE_FLEET_SERVICES)
    def test_fleet_configs_are_read_only_mounts(self, fleet_compose: dict, service_name: str) -> None:
        svc = fleet_compose["services"][service_name]
        volumes = svc.get("volumes", [])
        assert any(str(v).endswith(":ro") for v in volumes), f"{service_name} should mount config read-only"

    @pytest.mark.parametrize("service_name", FREQTRADE_FLEET_SERVICES)
    def test_fleet_services_are_not_privileged(self, fleet_compose: dict, service_name: str) -> None:
        svc = fleet_compose["services"][service_name]
        assert not svc.get("privileged", False)
        assert svc.get("restart") == "unless-stopped"


class TestDashboardContract:
    """Contract tests for the trading-dashboard service."""

    def test_dashboard_build_context_exists(self) -> None:
        """The Dockerfile referenced by docker-compose must exist."""
        context_path = ROOT / DASHBOARD_BUILD_CONTEXT / DASHBOARD_DOCKERFILE
        assert context_path.exists(), (
            f"Dashboard Dockerfile not found at {context_path}. "
            f"Compose references build context ./{DASHBOARD_BUILD_CONTEXT} "
            f"with dockerfile={DASHBOARD_DOCKERFILE}."
        )

    def test_dashboard_service_in_main_compose(self, main_compose: dict) -> None:
        """The trading-dashboard service exists in the main compose file."""
        services = main_compose["services"]
        assert "trading-dashboard" in services

    def test_dashboard_builds_from_correct_context(self, main_compose: dict) -> None:
        """Verify the trading-dashboard build context matches the expected path."""
        svc = main_compose["services"]["trading-dashboard"]
        build = svc.get("build", {})
        assert build.get("context") == f"./{DASHBOARD_BUILD_CONTEXT}", (
            f"Expected build context './{DASHBOARD_BUILD_CONTEXT}', "
            f"got {build.get('context')!r}"
        )
        assert build.get("dockerfile") == DASHBOARD_DOCKERFILE, (
            f"Expected dockerfile {DASHBOARD_DOCKERFILE!r}, "
            f"got {build.get('dockerfile')!r}"
        )

    def test_dashboard_mounts_dashboard_py(self, main_compose: dict) -> None:
        """The dashboard.py mount points to the correct source path."""
        svc = main_compose["services"]["trading-dashboard"]
        volumes = svc.get("volumes", [])
        dashboard_mounts = [v for v in volumes if "dashboard.py" in str(v)]
        assert len(dashboard_mounts) >= 1, (
            "No volume mount for dashboard.py found. "
            "Expected './dashboard.py:/app/dashboard.py:ro'"
        )
        mount = str(dashboard_mounts[0])
        assert mount.startswith("./dashboard.py"), (
            f"Expected mount source './dashboard.py', got {mount}"
        )

    def test_dashboard_flask_dependency(self) -> None:
        """Verify that dashboard.py imports Flask (code-level contract)."""
        dashboard_path = ROOT / "dashboard.py"
        assert dashboard_path.exists(), "dashboard.py not found"
        content = dashboard_path.read_text(encoding="utf-8")
        assert "from flask import" in content or "import flask" in content, (
            "dashboard.py does not import Flask. "
            "It requires Flask to run."
        )

    def test_dashboard_dockerfile_installs_flask(self) -> None:
        """Verify the Dockerfile installs Flask for the dashboard container."""
        dockerfile_path = ROOT / DASHBOARD_BUILD_CONTEXT / DASHBOARD_DOCKERFILE
        assert dockerfile_path.exists()
        content = dockerfile_path.read_text(encoding="utf-8")
        assert "flask" in content.lower(), (
            f"Dockerfile at {dockerfile_path} does not reference Flask. "
            f"The dashboard.py requires Flask at runtime."
        )
