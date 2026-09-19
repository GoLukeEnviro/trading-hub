r"""Tests for Apply Actuator runtime binding — fleet-aware path resolution.

Ensures that bot_id → host/container path mapping is correct for all 4 bots,
and that the dead path problem (freqtrade/bots/freqforge/user_data/)
is never returned as a valid runtime binding.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from si_v2.apply_actuator.runtime_binding import (
    BOT_RUNTIME_BINDINGS,
    DEFAULT_SI_V2_COMPOSE_PROJECT,
    DEFAULT_SI_V2_REPO_ROOT,
    SI_V2_COMPOSE_PROJECT_ENV,
    SI_V2_REPO_ROOT_ENV,
    build_container_name,
    build_fleet_bindings,
    build_host_overlay_path,
    resolve_binding,
    resolve_compose_project,
    resolve_si_v2_repo_root,
    validate_fleet_bindings,
)

# ---------------------------------------------------------------------------
# Test data: the four known bots
# ---------------------------------------------------------------------------

KNOWN_BOTS = [
    "freqtrade-freqforge",
    "freqtrade-freqforge-canary",
    "freqtrade-regime-hybrid",
    "freqai-rebel",
]

CORRECT_HOST_PATHS = {
    "freqtrade-freqforge": "/home/hermes/projects/trading/freqforge/user_data",
    "freqtrade-freqforge-canary": "/home/hermes/projects/trading/freqforge-canary/user_data",
    "freqtrade-regime-hybrid": "/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data",
    "freqai-rebel": "/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data",
}

DEAD_PATHS = [
    "/home/hermes/projects/trading/freqtrade/bots/freqforge/user_data",
]


# ---------------------------------------------------------------------------
# Resolution tests
# ---------------------------------------------------------------------------


class TestResolveBinding:
    def test_all_four_bots_resolve(self) -> None:
        """All 4 known bots must return a valid verified binding."""
        for bot_id in KNOWN_BOTS:
            binding = resolve_binding(bot_id)
            assert binding is not None, f"No binding for {bot_id}"
            assert binding.confidence == "VERIFIED", f"{bot_id} not VERIFIED"
            assert binding.runtime_visible is True, f"{bot_id} not runtime visible"

    def test_unknown_bot_returns_none(self) -> None:
        """Unknown bot_id → None (fail-safe)."""
        assert resolve_binding("nonexistent-bot") is None
        assert resolve_binding("") is None

    def test_freqforge_has_correct_path(self) -> None:
        """FreqForge's actual mount is freqforge/user_data/, NOT freqtrade/bots/freqforge/user_data/."""
        binding = resolve_binding("freqtrade-freqforge")
        assert binding is not None
        assert binding.host_user_data_path == CORRECT_HOST_PATHS["freqtrade-freqforge"]
        # Critical: must NOT be the dead path!
        assert binding.host_user_data_path not in DEAD_PATHS

    def test_all_bindings_have_correct_host_paths(self) -> None:
        """All bots must use the actual Docker mount paths, not repo-inert paths."""
        for bot_id in KNOWN_BOTS:
            binding = resolve_binding(bot_id)
            assert binding is not None
            expected = CORRECT_HOST_PATHS[bot_id]
            assert binding.host_user_data_path == expected, (
                f"{bot_id}: expected {expected}, got {binding.host_user_data_path}"
            )

    def test_all_bindings_have_host_config_paths(self) -> None:
        """All bindings must have a defined host config path."""
        for bot_id in KNOWN_BOTS:
            binding = resolve_binding(bot_id)
            assert binding is not None
            assert binding.host_config_path, f"{bot_id}: host_config_path empty"
            assert "config.example.json" in binding.host_config_path, (
                f"{bot_id}: host_config_path doesn't contain config.example.json"
            )

    def test_all_bindings_have_container_config_paths(self) -> None:
        """All bindings must define container-side config paths."""
        for bot_id in KNOWN_BOTS:
            binding = resolve_binding(bot_id)
            assert binding is not None
            assert binding.container_config_path, f"{bot_id}: container_config_path empty"
            assert binding.container_config_path == "/freqtrade/user_data/config.example.json"


# ---------------------------------------------------------------------------
# Fleet validation tests
# ---------------------------------------------------------------------------


class TestValidateFleetBindings:
    def test_all_bindings_valid(self) -> None:
        """validate_fleet_bindings returns valid (structural check, no path existence)."""
        valid, issues = validate_fleet_bindings(check_paths=False)
        assert valid is True, f"Expected valid, got issues: {issues}"
        assert issues == []

    def test_binding_count(self) -> None:
        """Must have exactly 4 bot bindings."""
        assert len(BOT_RUNTIME_BINDINGS) == 4


# ---------------------------------------------------------------------------
# Topology derivation tests — R7A / Agent0 portability (#757)
# ---------------------------------------------------------------------------


class TestTopologyDerivation:
    def test_container_name_follows_compose_convention(self) -> None:
        """Container name is <project>-<service>-1 (verified on live stack)."""
        assert build_container_name(
            "freqtrade-freqforge-canary", compose_project="hermestrader-dryrun"
        ) == "hermestrader-dryrun-freqtrade-freqforge-canary-1"

    def test_default_container_name_uses_canonical_project(self) -> None:
        """Default compose project is hermestrader-dryrun (R7A canonical)."""
        assert DEFAULT_SI_V2_COMPOSE_PROJECT == "hermestrader-dryrun"
        assert build_container_name("freqtrade-freqforge-canary") == (
            "hermestrader-dryrun-freqtrade-freqforge-canary-1"
        )

    def test_env_overrides_repo_root_and_compose_project(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Agent0 shape: SI_V2_REPO_ROOT + SI_V2_COMPOSE_PROJECT override the defaults."""
        agent0_root = "/opt/data/projects/trading-hub"
        monkeypatch.setenv(SI_V2_REPO_ROOT_ENV, agent0_root)
        monkeypatch.setenv(SI_V2_COMPOSE_PROJECT_ENV, "agent0")
        bindings = build_fleet_bindings(
            repo_root=Path(agent0_root), compose_project="agent0"
        )
        canary = bindings["freqtrade-freqforge-canary"]
        assert canary.container_name == "agent0-freqtrade-freqforge-canary-1"
        assert canary.host_user_data_path == (
            f"{agent0_root}/freqforge-canary/user_data"
        )
        assert canary.container_config_path == "/freqtrade/user_data/config.example.json"
        assert canary.host_config_path == (
            f"{agent0_root}/freqforge-canary/user_data/config.example.json"
        )

    def test_defaults_preserved_hermestrader(self) -> None:
        """HermesTrader default repo root is the historical checkout."""
        assert DEFAULT_SI_V2_REPO_ROOT == "/home/hermes/projects/trading"
        assert resolve_si_v2_repo_root() == Path(DEFAULT_SI_V2_REPO_ROOT)
        assert resolve_compose_project() == DEFAULT_SI_V2_COMPOSE_PROJECT

    def test_default_bindings_have_example_base_config(self) -> None:
        """R7A base config is config.example.json (the compose mount target)."""
        for bot_id in KNOWN_BOTS:
            binding = resolve_binding(bot_id)
            assert binding is not None
            assert binding.container_config_path == (
                "/freqtrade/user_data/config.example.json"
            )
            assert binding.host_config_path.endswith("config.example.json")


# ---------------------------------------------------------------------------
# Overlay path building tests
# ---------------------------------------------------------------------------


class TestBuildHostOverlayPath:
    def test_returns_correct_path_for_freqforge(self) -> None:
        """Overlay must go to the actual mount path: freqforge/user_data/."""
        path = build_host_overlay_path("freqtrade-freqforge", "65502d13a99bfadd")
        assert path is not None
        assert path == (
            "/home/hermes/projects/trading/freqforge/user_data/overlay_65502d13.json"
        )
        # Critical: must NOT contain the dead path
        assert "freqtrade/bots/freqforge" not in path

    def test_returns_correct_path_for_all_bots(self) -> None:
        """All bots must use their verified mount paths."""
        for bot_id in KNOWN_BOTS:
            path = build_host_overlay_path(bot_id, "abcdef1234567890")
            assert path is not None, f"No path for {bot_id}"
            # Must use correct base path
            expected_base = CORRECT_HOST_PATHS[bot_id]
            assert path.startswith(expected_base), (
                f"{bot_id}: path {path} doesn't start with {expected_base}"
            )
            assert path.endswith("_abcdef12.json")

    def test_unknown_bot_returns_none(self) -> None:
        """Unknown bot → None (fail-safe)."""
        assert build_host_overlay_path("unknown-bot", "12345678") is None


# ---------------------------------------------------------------------------
# Immutability tests
# ---------------------------------------------------------------------------


class TestBindingImmutability:
    def test_binding_is_frozen(self) -> None:
        """BotRuntimeBinding is a frozen dataclass — cannot be mutated."""
        binding = resolve_binding("freqtrade-freqforge")
        assert binding is not None
        with pytest.raises(AttributeError):
            binding.host_user_data_path = "/bad/path"  # type: ignore[misc]
