"""Contract tests for the HermesTrader R7A Greenfield Dry-Run Compose.

These tests validate the structural and safety properties of
``docker-compose.hermestrader-dryrun.yml`` without requiring a running
Docker daemon.  They parse the YAML file and assert on its structure.

Run: ``pytest tests/test_hermestrader_dryrun_compose.py -v``

Covers ADR-2026-07-11-hermes-r7a-dryrun-topology acceptance criteria.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
GREENFIELD_COMPOSE = ROOT / "docker-compose.hermestrader-dryrun.yml"
RAINBOW_INCLUDE = ROOT / "services" / "rainbow" / "rainbow.include.yml"
RAINBOW_CONFIG = ROOT / "config" / "rainbow.internal.yml"
REGISTRY = ROOT / "docs" / "registry" / "bot-registry.md"

# ─── expected OPTION_C fleet ──────────────────────────────────────────
DEFAULT_FLEET = {
    "freqtrade-freqforge",
    "freqtrade-freqforge-canary",
    "freqtrade-regime-hybrid",
    "freqtrade-webserver",
    "rainbow",
}

REBEL_SERVICE = "freqai-rebel"

# Config files to check for dry_run=true
CONFIG_FILES = [
    ROOT / "freqforge" / "user_data" / "config.example.json",
    ROOT / "freqforge-canary" / "user_data" / "config.example.json",
    ROOT / "freqtrade" / "bots" / "regime-hybrid" / "user_data" / "config.example.json",
    ROOT / "freqtrade" / "bots" / "webserver" / "user_data" / "config.example.json",
]


# ─── fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def compose() -> dict[str, object]:
    """Load and parse the greenfield compose file."""
    with GREENFIELD_COMPOSE.open() as f:
        return cast(dict[str, object], yaml.safe_load(f))


@pytest.fixture(scope="module")
def services(compose: dict[str, object]) -> dict[str, dict[str, object]]:
    """Extract the services dict from the compose file."""
    return cast(dict[str, dict[str, object]], compose["services"])


# ─── 1. Compose renders ───────────────────────────────────────────────

class TestComposeRenders:
    def test_compose_file_exists(self) -> None:
        assert GREENFIELD_COMPOSE.exists(), "Greenfield compose must exist"

    def test_compose_is_valid_yaml(self, compose: dict[str, object]) -> None:
        assert "services" in compose
        assert "networks" in compose

    def test_compose_has_services(self, services: dict[str, dict[str, object]]) -> None:
        assert len(services) >= 5, "Must have at least 5 default services"


# ─── 2. Registry / compose agreement ──────────────────────────────────

class TestRegistryAgreement:
    def test_registry_exists(self) -> None:
        assert REGISTRY.exists()

    def test_greenfield_services_match_registry(self, services: dict[str, dict[str, object]]) -> None:
        """All greenfield services from the registry must appear in compose."""
        registry_greenfield = {
            "freqtrade-freqforge",
            "freqtrade-freqforge-canary",
            "freqtrade-regime-hybrid",
            "freqai-rebel",
            "rainbow",
        }
        compose_services = set(services.keys())
        # freqtrade-webserver may or may not be in registry greenfield table
        # but must be in compose
        missing = registry_greenfield - compose_services
        assert not missing, f"Registry services missing from compose: {missing}"


# ─── 3. Default fleet = OPTION_C ──────────────────────────────────────

class TestOptionCFleet:
    def test_default_fleet_present(self, services: dict[str, dict[str, object]]) -> None:
        for svc in DEFAULT_FLEET:
            assert svc in services, f"OPTION_C service {svc} must be in compose"

    def test_rebel_has_profile(self, services: dict[str, dict[str, object]]) -> None:
        """Rebel must have a profile so it's NOT in default start."""
        if REBEL_SERVICE in services:
            rebel = services[REBEL_SERVICE]
            profiles = rebel.get("profiles")
            assert profiles is not None, "Rebel must have profiles: [rebel]"
            assert "rebel" in cast(list[str], profiles)

    def test_no_other_profiled_services(self, services: dict[str, dict[str, object]]) -> None:
        """No default service should have a profile."""
        for name, svc in services.items():
            if name == REBEL_SERVICE:
                continue
            profiles = svc.get("profiles")
            assert profiles is None, f"Default service {name} must not have profiles"


# ─── 4. dry_run=true in all configs ───────────────────────────────────

class TestDryRunEnforced:
    @pytest.mark.parametrize("config_path", CONFIG_FILES, ids=lambda p: p.parent.parent.name)
    def test_config_has_dry_run_true(self, config_path: Path) -> None:
        assert config_path.exists(), f"Config example must exist: {config_path}"
        with config_path.open() as f:
            cfg = json.load(f)
        assert cfg.get("dry_run") is True, f"{config_path.name}: dry_run must be true"

    @pytest.mark.parametrize("config_path", CONFIG_FILES, ids=lambda p: p.parent.parent.name)
    def test_config_has_no_dry_run_false(self, config_path: Path) -> None:
        with config_path.open() as f:
            content = f.read()
        assert '"dry_run": false' not in content.lower(), \
            f"{config_path.name}: must not contain dry_run=false"

    def test_configs_have_sanitized_credentials(self) -> None:
        """All config examples must use CHANGE_ME placeholders, not real secrets."""
        for config_path in CONFIG_FILES:
            with config_path.open() as f:
                content = f.read()
            # Must contain placeholder patterns
            assert "CHANGE" in content.upper(), \
                f"{config_path.name}: credentials must be sanitized placeholders"


# ─── 5. Read-only mounts for configs and strategies ───────────────────

class TestReadOnlyMounts:
    def test_config_mounts_are_read_only(self, services: dict[str, dict[str, object]]) -> None:
        freqtrade_svcs = [
            s for s in DEFAULT_FLEET if s != "rainbow"
        ]
        if REBEL_SERVICE in services:
            freqtrade_svcs.append(REBEL_SERVICE)
        for svc_name in freqtrade_svcs:
            svc = services[svc_name]
            volumes = cast(list[str], svc.get("volumes", []))
            config_mounts = [v for v in volumes if "config" in v and ":ro" not in v]
            assert not config_mounts, \
                f"{svc_name}: config mounts must be read-only: {config_mounts}"

    def test_strategy_mounts_are_read_only(self, services: dict[str, dict[str, object]]) -> None:
        freqtrade_svcs = [
            s for s in DEFAULT_FLEET if s != "rainbow"
        ]
        if REBEL_SERVICE in services:
            freqtrade_svcs.append(REBEL_SERVICE)
        for svc_name in freqtrade_svcs:
            svc = services[svc_name]
            volumes = cast(list[str], svc.get("volumes", []))
            strat_mounts = [v for v in volumes if "strategies" in v and ":ro" not in v]
            assert not strat_mounts, \
                f"{svc_name}: strategy mounts must be read-only: {strat_mounts}"

    def test_shared_mounts_are_read_only(self, services: dict[str, dict[str, object]]) -> None:
        freqtrade_svcs = [
            s for s in DEFAULT_FLEET if s != "rainbow"
        ]
        if REBEL_SERVICE in services:
            freqtrade_svcs.append(REBEL_SERVICE)
        for svc_name in freqtrade_svcs:
            svc = services[svc_name]
            volumes = cast(list[str], svc.get("volumes", []))
            shared_mounts = [v for v in volumes if "shared" in v and ":ro" not in v]
            assert not shared_mounts, \
                f"{svc_name}: shared mounts must be read-only: {shared_mounts}"


# ─── 6. Writable DB/Log paths ─────────────────────────────────────────

class TestWritablePaths:
    def test_db_volumes_defined(self, compose: dict[str, object]) -> None:
        volumes = cast(dict[str, object], compose.get("volumes", {}))
        db_volumes = [k for k in volumes if "db" in k or "storage" in k]
        assert len(db_volumes) >= 4, f"Must have writable DB volumes, got: {db_volumes}"


# ─── 7. Non-root, unprivileged ────────────────────────────────────────

class TestNonRootUnprivileged:
    @pytest.mark.parametrize("svc_name", list(DEFAULT_FLEET) + [REBEL_SERVICE])
    def test_service_runs_as_10000(
        self, services: dict[str, dict[str, object]], svc_name: str
    ) -> None:
        if svc_name not in services:
            pytest.skip(f"{svc_name} not in compose")
        svc = services[svc_name]
        assert svc.get("user") == "10000:10000", f"{svc_name} must run as 10000:10000"

    @pytest.mark.parametrize("svc_name", list(DEFAULT_FLEET) + [REBEL_SERVICE])
    def test_service_not_privileged(
        self, services: dict[str, dict[str, object]], svc_name: str
    ) -> None:
        if svc_name not in services:
            pytest.skip(f"{svc_name} not in compose")
        svc = services[svc_name]
        assert not svc.get("privileged", False), f"{svc_name} must not be privileged"

    @pytest.mark.parametrize("svc_name", list(DEFAULT_FLEET) + [REBEL_SERVICE])
    def test_service_has_cap_drop_all(
        self, services: dict[str, dict[str, object]], svc_name: str
    ) -> None:
        if svc_name not in services:
            pytest.skip(f"{svc_name} not in compose")
        svc = services[svc_name]
        cap_drop = cast(list[str], svc.get("cap_drop", []))
        assert "ALL" in cap_drop, f"{svc_name} must cap_drop: ALL"

    @pytest.mark.parametrize("svc_name", list(DEFAULT_FLEET) + [REBEL_SERVICE])
    def test_service_has_no_new_privileges(
        self, services: dict[str, dict[str, object]], svc_name: str
    ) -> None:
        if svc_name not in services:
            pytest.skip(f"{svc_name} not in compose")
        svc = services[svc_name]
        sec_opt = cast(list[str], svc.get("security_opt", []))
        assert "no-new-privileges:true" in sec_opt, \
            f"{svc_name} must have no-new-privileges:true"


# ─── 8. No Docker socket, no 0.0.0.0 ports ────────────────────────────

class TestNoDockerSocketOrExternalPorts:
    def test_no_docker_sock_mount(self, services: dict[str, dict[str, object]]) -> None:
        for name, svc in services.items():
            volumes = cast(list[str], svc.get("volumes", []))
            for v in volumes:
                assert "docker.sock" not in v, \
                    f"{name}: must not mount docker.sock"

    def test_no_port_binds_to_0000(self, services: dict[str, dict[str, object]]) -> None:
        for name, svc in services.items():
            ports = cast(list[str], svc.get("ports", []))
            for p in ports:
                assert "0.0.0.0" not in str(p), \
                    f"{name}: must not bind to 0.0.0.0: {p}"
                assert "127.0.0.1" in str(p), \
                    f"{name}: ports must bind to 127.0.0.1 only: {p}"

    def test_rainbow_has_no_published_ports(self, services: dict[str, dict[str, object]]) -> None:
        assert "rainbow" in services
        rainbow = services["rainbow"]
        ports = rainbow.get("ports")
        assert not ports, "Rainbow must NOT have published ports"


# ─── 9. No legacy paths ───────────────────────────────────────────────

class TestNoLegacyPaths:
    def test_no_home_hermes_projects(self, services: dict[str, dict[str, object]]) -> None:
        for name, svc in services.items():
            volumes = cast(list[str], svc.get("volumes", []))
            for v in volumes:
                assert "/home/hermes/projects" not in v, \
                    f"{name}: must not reference legacy /home/hermes/projects path"


# ─── 10. Healthchecks use python3, not curl ───────────────────────────

class TestHealthchecks:
    @pytest.mark.parametrize("svc_name", list(DEFAULT_FLEET) + [REBEL_SERVICE])
    def test_no_curl_in_healthcheck(
        self, services: dict[str, dict[str, object]], svc_name: str
    ) -> None:
        if svc_name not in services:
            pytest.skip(f"{svc_name} not in compose")
        svc = services[svc_name]
        hc = svc.get("healthcheck")
        if hc is None:
            return
        test_cmd = cast(list[str], hc.get("test", []))
        cmd_text = " ".join(test_cmd)
        assert "curl" not in cmd_text, \
            f"{svc_name}: healthcheck must not use curl"

    def test_healthchecks_use_python(self, services: dict[str, dict[str, object]]) -> None:
        for name, svc in services.items():
            hc = svc.get("healthcheck")
            if hc is None:
                continue
            test_cmd = cast(list[str], hc.get("test", []))
            cmd_text = " ".join(test_cmd)
            assert "python3" in cmd_text, \
                f"{name}: healthcheck must use python3"


# ─── 11. Log rotation ─────────────────────────────────────────────────

class TestLogRotation:
    @pytest.mark.parametrize("svc_name", list(DEFAULT_FLEET) + [REBEL_SERVICE])
    def test_log_rotation_configured(
        self, services: dict[str, dict[str, object]], svc_name: str
    ) -> None:
        if svc_name not in services:
            pytest.skip(f"{svc_name} not in compose")
        svc = services[svc_name]
        logging_cfg = cast(dict[str, object], svc.get("logging", {}))
        options = cast(dict[str, str], logging_cfg.get("options", {}))
        assert "max-size" in options, f"{svc_name}: must have log max-size"
        assert "max-file" in options, f"{svc_name}: must have log max-file"


# ─── 12. Rainbow properties ───────────────────────────────────────────

class TestRainbowProperties:
    def test_rainbow_config_internal_only(self) -> None:
        with RAINBOW_CONFIG.open() as f:
            cfg = cast(dict[str, object], yaml.safe_load(f))
        assert cfg.get("mode") == "ta_collector"

        evaluation = cast(dict[str, object], cfg.get("evaluation", {}))
        assert evaluation.get("enabled") is False

        delivery = cast(dict[str, object], cfg.get("delivery_worker", {}))
        assert delivery.get("enabled") is False

    def test_rainbow_no_exchange_credentials(self) -> None:
        with RAINBOW_CONFIG.open() as f:
            content = f.read()
        # Should not contain api_key, api_secret, etc.
        lower = content.lower()
        assert "api_key" not in lower or "api_key" not in content
        assert "api_secret" not in lower
        assert "exchange_secret" not in lower

    def test_rainbow_include_exists(self) -> None:
        assert RAINBOW_INCLUDE.exists()

    def test_rainbow_include_no_ports(self) -> None:
        with RAINBOW_INCLUDE.open() as f:
            inc = cast(dict[str, object], yaml.safe_load(f))
        svc = cast(dict[str, dict[str, object]], inc["services"])["rainbow"]
        assert not svc.get("ports"), "Rainbow include must have no ports"


# ─── 13. Network is internal ──────────────────────────────────────────

class TestNetworkInternal:
    def test_trading_internal_exists(self, compose: dict[str, object]) -> None:
        networks = cast(dict[str, dict[str, object]], compose.get("networks", {}))
        assert "trading_internal" in networks

    def test_trading_internal_is_bridge(self, compose: dict[str, object]) -> None:
        networks = cast(dict[str, dict[str, object]], compose.get("networks", {}))
        net = networks["trading_internal"]
        assert net.get("driver") == "bridge"
        assert net.get("internal") is True


# ─── 14. Build context files exist ────────────────────────────────────

class TestBuildContexts:
    def test_dockerfile_hermes10000_exists(self) -> None:
        dockerfile = ROOT / "freqtrade" / "Dockerfile.hermes10000"
        assert dockerfile.exists(), "Dockerfile.hermes10000 must exist"

    def test_all_strategy_dirs_exist(self, services: dict[str, dict[str, object]]) -> None:
        freqtrade_svcs = [
            s for s in DEFAULT_FLEET if s != "rainbow"
        ]
        if REBEL_SERVICE in services:
            freqtrade_svcs.append(REBEL_SERVICE)
        for svc_name in freqtrade_svcs:
            svc = services[svc_name]
            volumes = cast(list[str], svc.get("volumes", []))
            strat_volumes = [v for v in volumes if "strategies" in v]
            for sv in strat_volumes:
                # Extract host path (first part before ':')
                host_path = sv.split(":")[0].lstrip("./")
                full = ROOT / host_path
                assert full.exists(), f"{svc_name}: strategy dir must exist: {full}"


# ─── 15. No secrets committed ─────────────────────────────────────────

class TestNoSecrets:
    @pytest.mark.parametrize("config_path", CONFIG_FILES, ids=lambda p: p.parent.parent.name)
    def test_no_real_api_keys(self, config_path: Path) -> None:
        with config_path.open() as f:
            content = f.read()
        # Must not contain real-looking API keys (typically 32+ alphanumeric)
        # The example configs should only have CHANGE_ME placeholders
        assert "CHANGE" in content.upper(), \
            f"{config_path.name}: must use CHANGE_ME placeholders"
        # Should not contain "key" fields with non-placeholder values
        cfg = json.loads(content)
        exchange = cfg.get("exchange", {})
        assert "key" not in exchange or "CHANGE" in str(exchange.get("key", "")).upper(), \
            f"{config_path.name}: exchange must not have real API key"
        assert "secret" not in exchange or "CHANGE" in str(exchange.get("secret", "")).upper(), \
            f"{config_path.name}: exchange must not have real API secret"
