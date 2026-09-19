r"""Tests for Apply Actuator runtime binding — repo-relative, R7A-aware.

Ensures that bot_id → host/container path mapping is correct for all 4 bots:

- host paths resolve **repo-relative** (no historical absolute root),
- container names derive from the compose project
  (``SI_V2_COMPOSE_PROJECT``, default ``hermestrader-dryrun``),
- the container base config is the R7A mount target
  (``/freqtrade/user_data/config.example.json``),
- and the dead path problem (``freqtrade/bots/freqforge/user_data/``)
  is never returned as a valid runtime binding.
"""

from __future__ import annotations

import pytest

from si_v2.apply_actuator.runtime_binding import (
    BOT_RUNTIME_BINDINGS,
    CONTAINER_CONFIG_PATH,
    DEFAULT_COMPOSE_PROJECT,
    REPO_ROOT,
    build_host_overlay_path,
    compose_project_name,
    container_name_for_service,
    resolve_binding,
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
    "freqtrade-freqforge": str(REPO_ROOT / "freqforge" / "user_data"),
    "freqtrade-freqforge-canary": str(REPO_ROOT / "freqforge-canary" / "user_data"),
    "freqtrade-regime-hybrid": str(
        REPO_ROOT / "freqtrade" / "bots" / "regime-hybrid" / "user_data"
    ),
    "freqai-rebel": str(
        REPO_ROOT / "freqtrade" / "bots" / "freqai-rebel" / "user_data"
    ),
}

HISTORICAL_ROOT = "/home/hermes/projects/trading"

DEAD_PATHS = [
    f"{HISTORICAL_ROOT}/freqtrade/bots/freqforge/user_data",
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

    def test_host_paths_are_repo_relative(self) -> None:
        """No binding may point at the historical absolute root."""
        for bot_id in KNOWN_BOTS:
            binding = resolve_binding(bot_id)
            assert binding is not None
            assert binding.host_user_data_path.startswith(str(REPO_ROOT))
            assert not binding.host_user_data_path.startswith(HISTORICAL_ROOT), (
                f"{bot_id}: historical root leaked into {binding.host_user_data_path}"
            )

    def test_all_bindings_have_host_config_paths(self) -> None:
        """All bindings must have a defined host config path."""
        for bot_id in KNOWN_BOTS:
            binding = resolve_binding(bot_id)
            assert binding is not None
            assert binding.host_config_path, f"{bot_id}: host_config_path empty"
            assert "config.json" in binding.host_config_path, (
                f"{bot_id}: host_config_path doesn't contain config.json"
            )

    def test_all_bindings_have_container_config_paths(self) -> None:
        """All bindings must define the R7A container-side base config path."""
        for bot_id in KNOWN_BOTS:
            binding = resolve_binding(bot_id)
            assert binding is not None
            assert binding.container_config_path, f"{bot_id}: container_config_path empty"
            assert binding.container_config_path == CONTAINER_CONFIG_PATH
            assert binding.container_config_path.endswith("config.example.json")

    def test_container_names_derive_from_compose_project(self) -> None:
        """Container names must be <project>-<service>-1 (R7A default project)."""
        for bot_id in KNOWN_BOTS:
            binding = resolve_binding(bot_id)
            assert binding is not None
            assert binding.container_name == container_name_for_service(bot_id)
            assert binding.container_name.startswith(f"{DEFAULT_COMPOSE_PROJECT}-")
            assert binding.container_name.endswith("-1")

    def test_loaded_config_args_are_compose_style(self) -> None:
        """loaded_config_args must be the base compose command (starting with trade)."""
        for bot_id in KNOWN_BOTS:
            binding = resolve_binding(bot_id)
            assert binding is not None
            args = binding.loaded_config_args
            assert args[0] == "trade", f"{bot_id}: command must start with trade"
            assert "--config" in args
            cfg_index = args.index("--config")
            assert args[cfg_index + 1] == CONTAINER_CONFIG_PATH
            assert "--strategy" in args


class TestComposeProjectDerivation:
    def test_default_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SI_V2_COMPOSE_PROJECT", raising=False)
        assert compose_project_name() == DEFAULT_COMPOSE_PROJECT
        assert (
            container_name_for_service("freqtrade-freqforge-canary")
            == "hermestrader-dryrun-freqtrade-freqforge-canary-1"
        )

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SI_V2_COMPOSE_PROJECT", "trading")
        assert compose_project_name() == "trading"
        assert (
            container_name_for_service("freqtrade-freqforge")
            == "trading-freqtrade-freqforge-1"
        )


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
# Overlay path building tests
# ---------------------------------------------------------------------------


class TestBuildHostOverlayPath:
    def test_returns_correct_path_for_freqforge(self) -> None:
        """Overlay must go to the actual mount path: freqforge/user_data/."""
        path = build_host_overlay_path("freqtrade-freqforge", "65502d13a99bfadd")
        assert path is not None
        assert path == (
            f"{CORRECT_HOST_PATHS['freqtrade-freqforge']}/overlay_65502d13.json"
        )
        # Critical: must NOT contain the dead path
        assert "freqtrade/bots/freqforge" not in path
        assert not path.startswith(HISTORICAL_ROOT)

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
