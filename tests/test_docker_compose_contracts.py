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
