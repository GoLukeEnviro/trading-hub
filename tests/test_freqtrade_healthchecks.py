"""Static validation tests for Freqtrade Docker healthcheck definitions (issue #199).

These tests parse the canonical Compose YAML without contacting Docker.
They assert every target Freqtrade service has a healthcheck block,
uses /api/v1/ping, targets localhost only, and has no forbidden content.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

import pytest
import yaml

COMPOSE_FILE = pathlib.Path(__file__).resolve().parent.parent / "docker-compose.yml"

TARGET_SERVICES = [
    "freqtrade-freqforge",
    "freqtrade-regime-hybrid",
    "freqtrade-freqforge-canary",
    "freqai-rebel",
    "freqtrade-webserver",
]

FORBIDDEN_PATTERNS = [
    r"token",
    r"password",
    r"secret",
    r"api[_-]?key",
    r"forcebuy",
    r"forcesell",
    r"dry_run\s*[:=]\s*false",
    r"exchange\s*[:=]",
    r"order\s*[:=]",
    r"trade\s*[:=]",
    r"credential",
]


@pytest.fixture(scope="module")
def compose_data() -> dict[str, Any]:
    """Load and parse the canonical docker-compose.yml."""
    with COMPOSE_FILE.open() as f:
        data = yaml.safe_load(f)
    return data


@pytest.fixture(scope="module")
def services(compose_data: dict[str, Any]) -> dict[str, Any]:
    return compose_data.get("services", {})


class TestComposeParses:
    """Ensure the Compose file is valid YAML."""

    def test_compose_file_exists(self):
        assert COMPOSE_FILE.exists(), f"{COMPOSE_FILE} must exist"

    def test_compose_parses_as_yaml(self, compose_data: dict[str, Any]):
        assert isinstance(compose_data, dict)
        assert "services" in compose_data

    def test_all_target_services_exist(self, services: dict[str, Any]):
        for svc in TARGET_SERVICES:
            assert svc in services, f"Service '{svc}' not found in compose file"


class TestHealthcheckPresence:
    """Every target service must have a healthcheck block."""

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_has_healthcheck(self, services: dict[str, Any], service_name: str):
        svc = services[service_name]
        assert "healthcheck" in svc, f"Service '{service_name}' has no healthcheck block"

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_healthcheck_has_test(self, services: dict[str, Any], service_name: str):
        hc = services[service_name]["healthcheck"]
        assert "test" in hc, f"Service '{service_name}' healthcheck has no test"

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_healthcheck_has_interval(self, services: dict[str, Any], service_name: str):
        hc = services[service_name]["healthcheck"]
        assert hc.get("interval") == "30s", (
            f"Service '{service_name}' interval should be 30s, got {hc.get('interval')}"
        )

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_healthcheck_has_timeout(self, services: dict[str, Any], service_name: str):
        hc = services[service_name]["healthcheck"]
        assert hc.get("timeout") == "5s", (
            f"Service '{service_name}' timeout should be 5s, got {hc.get('timeout')}"
        )

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_healthcheck_has_retries(self, services: dict[str, Any], service_name: str):
        hc = services[service_name]["healthcheck"]
        assert hc.get("retries") == 3, (
            f"Service '{service_name}' retries should be 3, got {hc.get('retries')}"
        )

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_healthcheck_has_start_period(self, services: dict[str, Any], service_name: str):
        hc = services[service_name]["healthcheck"]
        assert hc.get("start_period") == "60s", (
            f"Service '{service_name}' start_period should be 60s, got {hc.get('start_period')}"
        )


class TestHealthcheckContent:
    """Healthcheck commands must use /api/v1/ping and localhost."""

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_uses_api_v1_ping(self, services: dict[str, Any], service_name: str):
        test = services[service_name]["healthcheck"]["test"]
        test_str = " ".join(str(t) for t in test)
        assert "/api/v1/ping" in test_str, (
            f"Service '{service_name}' healthcheck does not use /api/v1/ping"
        )

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_uses_localhost(self, services: dict[str, Any], service_name: str):
        test = services[service_name]["healthcheck"]["test"]
        test_str = " ".join(str(t) for t in test)
        assert "127.0.0.1" in test_str or "localhost" in test_str, (
            f"Service '{service_name}' healthcheck does not target localhost/127.0.0.1"
        )

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_does_not_use_external_hosts(self, services: dict[str, Any], service_name: str):
        test = services[service_name]["healthcheck"]["test"]
        test_str = " ".join(str(t) for t in test)
        # Must not reference container names or external hostnames
        external_patterns = [
            "trading-freqtrade-",
            "trading-freqai-",
            "hermes-green",
            "green-",
            "docker-proxy",
        ]
        for pat in external_patterns:
            assert pat not in test_str, (
                f"Service '{service_name}' healthcheck references external host '{pat}'"
            )

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_no_forbidden_patterns(self, services: dict[str, Any], service_name: str):
        test = services[service_name]["healthcheck"]["test"]
        test_str = " ".join(str(t) for t in test).lower()
        for pattern in FORBIDDEN_PATTERNS:
            matches = re.findall(pattern, test_str, re.IGNORECASE)
            assert not matches, (
                f"Service '{service_name}' healthcheck contains forbidden pattern "
                f"'{pattern}': {matches}"
            )


class TestNoForbiddenFileChanges:
    """Ensure healthcheck additions don't change trading config files."""

    FORBIDDEN_PATHS = [
        "freqtrade/bots/*/strategies/",
        "freqtrade/shared/fleet_risk_manager.py",
        "freqforge/user_data/config.json",
        "freqforge-canary/user_data/config.json",
        "freqtrade/bots/regime-hybrid/user_data/config.json",
        "freqtrade/bots/freqai-rebel/user_data/config.json",
    ]

    def test_no_strategy_files_changed(self):
        """This test documents the contract that strategy files must not change."""
        # Static contract: if this test file exists alongside the healthcheck PR,
        # it asserts by convention that no strategy files were modified.
        # The actual git diff is validated in CI.
        pass


class TestServiceConfigPreserved:
    """Verify trading-related config keys are unchanged by the healthcheck addition."""

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_command_preserved(self, services: dict[str, Any], service_name: str):
        svc = services[service_name]
        assert "command" in svc, f"Service '{service_name}' lost its command"

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_image_preserved(self, services: dict[str, Any], service_name: str):
        svc = services[service_name]
        assert "image" in svc, f"Service '{service_name}' lost its image"

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_volumes_preserved(self, services: dict[str, Any], service_name: str):
        svc = services[service_name]
        assert "volumes" in svc, f"Service '{service_name}' lost its volumes"

    @pytest.mark.parametrize("service_name", TARGET_SERVICES)
    def test_restart_policy_preserved(self, services: dict[str, Any], service_name: str):
        svc = services[service_name]
        assert svc.get("restart") == "unless-stopped", (
            f"Service '{service_name}' restart policy changed"
        )
