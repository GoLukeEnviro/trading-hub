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
        """The real enforcement is RainbowSettings.read_only (see
        TestRainbowConfigSchema) - "mode" and "delivery_worker" were never
        fields Rainbow's settings schema recognized and have been removed.
        """
        with RAINBOW_CONFIG.open() as f:
            cfg = cast(dict[str, object], yaml.safe_load(f))
        assert cfg.get("read_only") is True

        evaluation = cast(dict[str, object], cfg.get("evaluation", {}))
        assert evaluation.get("enabled") is False

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

    def test_trading_egress_exists_and_is_not_internal(self, compose: dict[str, object]) -> None:
        """Freqtrade and Rainbow need outbound market-data access even in
        dry-run/ta_collector mode. trading_internal alone (internal=true)
        blocks ALL external routing, so a separate, non-internal egress
        network is required alongside it - see ADR network topology note.
        """
        networks = cast(dict[str, dict[str, object]], compose.get("networks", {}))
        assert "trading_egress" in networks
        egress = networks["trading_egress"]
        assert egress.get("driver") == "bridge"
        assert not egress.get("internal"), "trading_egress must NOT be internal"

    @pytest.mark.parametrize("svc_name", list(DEFAULT_FLEET) + [REBEL_SERVICE])
    def test_fleet_service_has_both_networks(
        self, services: dict[str, dict[str, object]], svc_name: str
    ) -> None:
        if svc_name not in services:
            pytest.skip(f"{svc_name} not in compose")
        svc = services[svc_name]
        nets = cast(list[str], svc.get("networks", []))
        assert "trading_internal" in nets, f"{svc_name}: must stay on trading_internal"
        assert "trading_egress" in nets, f"{svc_name}: needs trading_egress for market-data access"

    def test_include_file_has_egress_network(self) -> None:
        with RAINBOW_INCLUDE.open() as f:
            inc = cast(dict[str, object], yaml.safe_load(f))
        networks = cast(dict[str, dict[str, object]], inc.get("networks", {}))
        assert "trading_egress" in networks
        assert not networks["trading_egress"].get("internal")
        rainbow = cast(dict[str, dict[str, object]], inc["services"])["rainbow"]
        nets = cast(list[str], rainbow.get("networks", []))
        assert "trading_egress" in nets


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


# ─── 16. Rainbow builds with rainbow.Dockerfile, not the default one ──

class TestRainbowDockerfilePinned:
    def test_main_compose_uses_rainbow_dockerfile(self, services: dict[str, dict[str, object]]) -> None:
        rainbow = services["rainbow"]
        build = cast(dict[str, object], rainbow.get("build", {}))
        assert build.get("dockerfile") == "rainbow.Dockerfile", \
            "rainbow service must build with rainbow.Dockerfile (port 8000, uvicorn), " \
            "not the default Dockerfile (port 9090, python main.py)"

    def test_include_file_uses_rainbow_dockerfile(self) -> None:
        with RAINBOW_INCLUDE.open() as f:
            inc = cast(dict[str, object], yaml.safe_load(f))
        rainbow = cast(dict[str, dict[str, object]], inc["services"])["rainbow"]
        build = cast(dict[str, object], rainbow.get("build", {}))
        assert build.get("dockerfile") == "rainbow.Dockerfile"


# ─── 17. Rainbow read_only enforcement (real mechanism, not dead env vars) ─

class TestRainbowReadOnlyEnv:
    def test_main_compose_sets_read_only(self, services: dict[str, dict[str, object]]) -> None:
        rainbow = services["rainbow"]
        env = cast(list[str], rainbow.get("environment", []))
        assert any(e.strip() == "RAINBOW_READ_ONLY=true" for e in env), \
            f"rainbow service must set RAINBOW_READ_ONLY=true, got: {env}"

    def test_main_compose_has_no_dead_env_vars(self, services: dict[str, dict[str, object]]) -> None:
        """RAINBOW_MODE / RAINBOW_EVALUATION_ENABLED / RAINBOW_DELIVERY_WORKER_ENABLED
        don't map to any RainbowSettings field or nested env delimiter and were
        never read - they gave a false impression of enforcement.
        """
        rainbow = services["rainbow"]
        env = cast(list[str], rainbow.get("environment", []))
        env_keys = {e.split("=", 1)[0].strip() for e in env}
        dead_vars = {"RAINBOW_MODE", "RAINBOW_EVALUATION_ENABLED", "RAINBOW_DELIVERY_WORKER_ENABLED"}
        present_dead = env_keys & dead_vars
        assert not present_dead, f"these env vars are never read by RainbowSettings: {present_dead}"


# ─── 18. Rainbow config only uses fields RainbowSettings actually accepts ──

# Top-level keys RainbowSettings accepts, verified against
# ai4trade-bot@a43a80cf66c7fb77e07b25a650a72c3303d26791 (rainbow/config/settings.py).
# extra="forbid" means anything outside this set fails Rainbow's startup.
RAINBOW_SETTINGS_FIELDS = {
    "log_level", "log_format", "market_data", "bitget_api_key", "claude_api_key",
    "llm_api_key", "twitter_bearer_token", "api", "scorer", "evaluation",
    "collectors", "db_path", "read_only",
    "health_grace_period_seconds", "health_max_heartbeat_age_seconds",
}


class TestRainbowConfigSchema:
    def test_config_only_uses_known_fields(self) -> None:
        with RAINBOW_CONFIG.open() as f:
            cfg = cast(dict[str, object], yaml.safe_load(f))
        unknown = set(cfg.keys()) - RAINBOW_SETTINGS_FIELDS
        assert not unknown, (
            f"config/rainbow.internal.yml has keys RainbowSettings doesn't accept "
            f'(extra="forbid" -> startup failure): {unknown}'
        )

    def test_config_no_legacy_invented_keys(self) -> None:
        with RAINBOW_CONFIG.open() as f:
            cfg = cast(dict[str, object], yaml.safe_load(f))
        for legacy_key in ("mode", "delivery_worker", "storage", "health", "freshness"):
            assert legacy_key not in cfg, f"'{legacy_key}' is not a RainbowSettings field"


# ─── 19. Heartbeat volume mount matches the canonical runtime path ────

class TestHeartbeatVolumeMatchesCanonicalPath:
    """Rainbow writes to rainbow/storage/heartbeat_rainbow.json relative to
    /app (see ai4trade-bot rainbow/paths.py). The mounted volume must cover
    that exact directory, or the heartbeat never lands in persistent storage.
    """

    def test_main_compose_storage_mount_is_canonical(self, services: dict[str, dict[str, object]]) -> None:
        rainbow = services["rainbow"]
        volumes = cast(list[str], rainbow.get("volumes", []))
        storage_mounts = [v for v in volumes if v.split(":")[0] == "rainbow-storage"]
        assert storage_mounts == ["rainbow-storage:/app/rainbow/storage"], storage_mounts

    def test_include_file_storage_mount_is_canonical(self) -> None:
        with RAINBOW_INCLUDE.open() as f:
            inc = cast(dict[str, object], yaml.safe_load(f))
        rainbow = cast(dict[str, dict[str, object]], inc["services"])["rainbow"]
        volumes = cast(list[str], rainbow.get("volumes", []))
        storage_mounts = [v for v in volumes if v.split(":")[0] == "rainbow-storage"]
        assert storage_mounts == ["rainbow-storage:/app/rainbow/storage"], storage_mounts


# ─── 20. ai4trade-bot pin is documented and current ───────────────────

class TestAi4tradeBotPinDocumented:
    def test_adr_references_current_pin(self) -> None:
        adr = ROOT / "docs" / "decisions" / "ADR-2026-07-11-hermes-r7a-dryrun-topology.md"
        content = adr.read_text(encoding="utf-8")
        assert "cd63051545e9b27235f47a3bbb5de858782fcd20" in content, (
            "ADR must reference the current pinned ai4trade-bot commit "
            "(ai4trade-bot#78 + #79)"
        )



# ─── 21. Freqtrade base image is pinned by digest ─────────────────────

class TestFreqtradeImagePinned:
    def test_dockerfile_pins_base_image_by_digest(self) -> None:
        dockerfile = ROOT / "freqtrade" / "Dockerfile.hermes10000"
        content = dockerfile.read_text(encoding="utf-8")
        from_lines = [line for line in content.splitlines() if line.startswith("FROM ")]
        assert from_lines, "Dockerfile must have a FROM line"
        assert "@sha256:" in from_lines[0], (
            f"base image must be pinned by digest, not a mutable tag: {from_lines[0]}"
        )


# ─── 22. Entrypoint permission fixes are not silently swallowed ───────

class TestEntrypointErrorVisibility:
    def test_entrypoint_script_exists(self) -> None:
        entrypoint = ROOT / "freqtrade" / "entrypoint.sh"
        assert entrypoint.exists(), "freqtrade/entrypoint.sh must exist"

    def test_dockerfile_copies_entrypoint_script(self) -> None:
        dockerfile = ROOT / "freqtrade" / "Dockerfile.hermes10000"
        content = dockerfile.read_text(encoding="utf-8")
        assert "COPY entrypoint.sh" in content

    def test_entrypoint_does_not_silently_swallow_failures(self) -> None:
        """The old inline entrypoint used `2>/dev/null && ... || true`,
        which hides a real permission problem entirely. Failures must at
        least be logged (stderr) instead of vanishing.
        """
        entrypoint = ROOT / "freqtrade" / "entrypoint.sh"
        content = entrypoint.read_text(encoding="utf-8")
        assert "2>/dev/null" not in content, "must not discard stderr from permission fixes"
        assert "WARN" in content, "permission-fix failures must be logged, not just || true'd away"



# ─── 23. Freqtrade user_data ownership fixed at build time ────────────

class TestFreqtradeUserDataOwnership:
    """Live smoke test discovered: freqtradeorg/freqtrade ships
    /freqtrade/user_data owned by the pre-remap UID (1000), not the
    remapped ftuser (10000). Named volumes inherit ownership from the
    image on first creation, so this must be fixed at build time -
    the runtime entrypoint (running as UID 10000, never root) cannot
    chgrp/chown a directory it does not own.
    """

    def test_dockerfile_chowns_user_data(self) -> None:
        dockerfile = ROOT / "freqtrade" / "Dockerfile.hermes10000"
        content = dockerfile.read_text(encoding="utf-8")
        assert "chown -R 10000:10000 /freqtrade/user_data" in content

    def test_dockerfile_precreates_logs_dir(self) -> None:
        """logs/ doesn't exist in the base image, so it must be created
        before the chown, or the fresh named volume inherits root
        ownership instead (mkdir -p must precede the chown line).
        """
        dockerfile = ROOT / "freqtrade" / "Dockerfile.hermes10000"
        content = dockerfile.read_text(encoding="utf-8")
        mkdir_idx = content.find("mkdir -p /freqtrade/user_data/logs")
        chown_idx = content.find("chown -R 10000:10000 /freqtrade/user_data")
        assert mkdir_idx != -1 and chown_idx != -1 and mkdir_idx < chown_idx


# ─── 24. No per-bot Telegram token (routed via Hermes instead) ────────

class TestNoPerBotTelegramEnv:
    """FREQTRADE__TELEGRAM__ENABLED=false injected a partial telegram
    config that failed Freqtrade's own schema (requires token+chat_id
    once the key exists at all). The configs never had a telegram
    section to begin with, so the env var was both redundant and
    actively broken - removed rather than patched, since these bots
    are meant to route notifications through the shared Hermes Telegram
    bot rather than getting their own token (architecture TBD separately).
    """

    @pytest.mark.parametrize("svc_name", list(DEFAULT_FLEET) + [REBEL_SERVICE])
    def test_no_telegram_env_var(self, services: dict[str, dict[str, object]], svc_name: str) -> None:
        if svc_name not in services or svc_name == "rainbow":
            pytest.skip(f"{svc_name} not applicable")
        svc = services[svc_name]
        env = cast(list[str], svc.get("environment", []))
        env_keys = {e.split("=", 1)[0].strip() for e in env}
        assert "FREQTRADE__TELEGRAM__ENABLED" not in env_keys


# ─── 25. jwt_secret_key placeholders satisfy Freqtrade's own schema ───

class TestJwtSecretPlaceholderLength:
    @pytest.mark.parametrize("config_path", CONFIG_FILES, ids=lambda p: p.parent.parent.name)
    def test_jwt_secret_key_min_length(self, config_path: Path) -> None:
        with config_path.open() as f:
            cfg = json.load(f)
        key = cfg.get("api_server", {}).get("jwt_secret_key", "")
        assert len(key) >= 32, f"{config_path.name}: jwt_secret_key too short ({len(key)} chars)"
