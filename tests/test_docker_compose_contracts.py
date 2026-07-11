from __future__ import annotations

import re

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
MAIN_COMPOSE = ROOT / "docker-compose.yml"
FLEET_COMPOSE = ROOT / "freqtrade" / "docker-compose.fleet.yml"
BOT_REGISTRY = ROOT / "docs" / "registry" / "bot-registry.md"


def _load_registry_services() -> list[str]:
    """Parse compose_service column from bot-registry.md.

    Each row looks like: | `trading.<id>` | `container` | `<service>` | `<strategy>` |
    The service column is the canonical Fleet-SoT per AGENTS.md conflict rule
    (Docker/Compose wins on naming, but the registry defines Fleet membership
    until an explicit R7A architecture decision supersedes it).
    """
    text = BOT_REGISTRY.read_text(encoding="utf-8")
    services: list[str] = []
    for line in text.splitlines():
        if not line.startswith("| `trading."):
            continue
        m = re.match(r"^\| `trading\.[^`]+` \| `[^`]+` \| `([^`]+)` \|", line)
        if m:
            services.append(m.group(1))
    if not services:
        raise RuntimeError(
            f"No bot-registry entries parsed from {BOT_REGISTRY} "
            f"— check table format and rerun."
        )
    return sorted(set(services))


# Compose service names that the contract MUST hold for. These are
# the same as the registry: every compose service listed in
# docs/registry/bot-registry.md is asserted below.
FREQTRADE_FLEET_SERVICES = _load_registry_services()

# Known registry-vs-compose drift that this PR does NOT fix. Documented in
# docs/registry/bot-registry-contract.md and to be resolved in the R7A
# architecture-decision PR (Compose path migration + fleet reconciliation).
# Each entry: pytest.parametrize id, list of contract properties currently
# violated. Adding entries here MUST include the reason and the tracking
# issue — the rule is "no silent xfails".
_R7A_DEFERRED_DRIFT: dict[str, list[str]] = {
    "freqtrade-freqforge": ["user:10000:10000"],
    "freqtrade-freqforge-canary": ["user:10000:10000"],
    "freqtrade-regime-hybrid": ["user:10000:10000"],
    "freqai-rebel": ["user:10000:10000"],
    "freqtrade-webserver": ["user:10000:10000", "config:ro-mount"],
}

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


def _resolve_service(
    service_name: str,
    main_compose: dict,
    fleet_compose: dict,
) -> tuple[dict | None, str | None]:
    """Locate a service in one of the compose files.

    Per the registry-as-SoT contract (docs/registry/bot-registry-contract.md),
    a registry service must exist in at least one compose file. The
    compose file that defines it is the authoritative source for its
    runtime contract (user, ports, volumes, restart, privileged).

    Returns (service_dict, source_label) on success, (None, None) if the
    service is missing from every compose file.
    """
    main_services = main_compose.get("services", {})
    if service_name in main_services:
        return main_services[service_name], "docker-compose.yml"
    fleet_services = fleet_compose.get("services", {})
    if service_name in fleet_services:
        return fleet_services[service_name], "freqtrade/docker-compose.fleet.yml"
    return None, None


class TestDockerComposeContracts:
    def test_compose_files_exist(self) -> None:
        assert MAIN_COMPOSE.exists()
        assert FLEET_COMPOSE.exists()

    def test_registry_services_defined_in_some_compose(
        self, main_compose: dict, fleet_compose: dict
    ) -> None:
        """Every registry entry must resolve to at least one compose file.

        See docs/registry/bot-registry-contract.md. A registry service
        that is missing from BOTH compose files is the canonical
        Konflikt #1 from the R7A discovery report.
        """
        main_names = set(main_compose.get("services", {}).keys())
        fleet_names = set(fleet_compose.get("services", {}).keys())
        missing = [
            s for s in FREQTRADE_FLEET_SERVICES
            if s not in main_names and s not in fleet_names
        ]
        assert not missing, (
            f"Registry services not defined in any compose file: {missing}. "
            f"Registry is the Fleet-membership SoT — add the service to "
            f"docker-compose.yml or freqtrade/docker-compose.fleet.yml, "
            f"or remove it from docs/registry/bot-registry.md."
        )

    @pytest.mark.parametrize("service_name", FREQTRADE_FLEET_SERVICES)
    def test_fleet_services_run_as_non_root(
        self, main_compose: dict, fleet_compose: dict, service_name: str
    ) -> None:
        svc, source = _resolve_service(service_name, main_compose, fleet_compose)
        assert svc is not None, f"{service_name} missing from both compose files"
        if "user:10000:10000" in _R7A_DEFERRED_DRIFT.get(service_name, []):
            pytest.xfail(
                f"{service_name} in {source} does not set user=10000:10000. "
                f"Known R7A-deferred drift, see docs/registry/bot-registry-contract.md."
            )
        assert svc.get("user") == "10000:10000", f"{service_name} in {source}"

    @pytest.mark.parametrize("service_name", FREQTRADE_FLEET_SERVICES)
    def test_fleet_services_bind_to_localhost_only(
        self, main_compose: dict, fleet_compose: dict, service_name: str
    ) -> None:
        svc, source = _resolve_service(service_name, main_compose, fleet_compose)
        assert svc is not None, f"{service_name} missing from both compose files"
        ports = svc.get("ports", [])
        assert ports, f"{service_name} in {source} must publish a localhost-only port"
        port_text = " ".join(str(p) for p in ports)
        assert "127.0.0.1" in port_text, f"{service_name} in {source}"
        assert "0.0.0.0" not in port_text, f"{service_name} in {source}"

    @pytest.mark.parametrize("service_name", FREQTRADE_FLEET_SERVICES)
    def test_fleet_configs_are_read_only_mounts(
        self, main_compose: dict, fleet_compose: dict, service_name: str
    ) -> None:
        svc, source = _resolve_service(service_name, main_compose, fleet_compose)
        assert svc is not None, f"{service_name} missing from both compose files"
        if "config:ro-mount" in _R7A_DEFERRED_DRIFT.get(service_name, []):
            pytest.xfail(
                f"{service_name} in {source} does not mount config read-only. "
                f"Known R7A-deferred drift, see docs/registry/bot-registry-contract.md."
            )
        volumes = svc.get("volumes", [])
        assert any(str(v).endswith(":ro") for v in volumes), (
            f"{service_name} in {source} should mount config read-only"
        )

    @pytest.mark.parametrize("service_name", FREQTRADE_FLEET_SERVICES)
    def test_fleet_services_are_not_privileged(
        self, main_compose: dict, fleet_compose: dict, service_name: str
    ) -> None:
        svc, source = _resolve_service(service_name, main_compose, fleet_compose)
        assert svc is not None, f"{service_name} missing from both compose files"
        assert not svc.get("privileged", False), f"{service_name} in {source}"
        assert svc.get("restart") == "unless-stopped", f"{service_name} in {source}"


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
