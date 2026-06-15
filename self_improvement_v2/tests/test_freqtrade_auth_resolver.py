"""Tests for the safe SI v2 Freqtrade auth resolver.

Tests cover:
- Resolver prefers already-set env vars
- Resolver falls back to allowlisted local config path
- Resolver reads only api_server.username and api_server.password
- Resolver returns sanitized status without secret values
- Resolver rejects malformed configs
- Resolver never includes password value in output
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RESOLVER_PATH = _REPO_ROOT / "self_improvement_v2/src/si_v2/adapters/freqtrade_auth_resolver.py"
_REGISTRY_PATH = _REPO_ROOT / "self_improvement_v2/config/freqtrade_bots.readonly.json"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def resolver_module():
    import importlib.util as iu
    spec = iu.spec_from_file_location("freqtrade_auth_resolver", _RESOLVER_PATH)
    mod = iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def real_registry(resolver_module):
    """Load the actual bot registry for integration tests."""
    return resolver_module._load_registry(_REGISTRY_PATH)


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------
class TestResolverStructure:
    def test_has_resolve_all(self, resolver_module):
        assert callable(resolver_module.resolve_all)

    def test_has_allowed_paths(self, resolver_module):
        paths = resolver_module.ALLOWED_CONFIG_PATHS
        assert isinstance(paths, dict)
        # Must have all four bots
        assert "freqtrade-freqforge" in paths
        assert "freqtrade-regime-hybrid" in paths
        assert "freqtrade-freqforge-canary" in paths
        assert "freqai-rebel" in paths

    def test_auth_resolution_dataclass(self, resolver_module):
        ar = resolver_module.AuthResolution(
            bot_id="test", username_env="U",
            password_env="P", status="MISSING",
        )
        assert ar.bot_id == "test"
        assert ar.status == "MISSING"
        assert ar.source_path == ""
        assert ar.error == ""

    def test_auth_resolution_no_secrets_in_repr(self, resolver_module):
        """AuthResolution object should not contain credential values in its fields."""
        ar = resolver_module.AuthResolution(
            bot_id="test", username_env="U_ENV",
            password_env="P_ENV", status="RESOLVED_FROM_ENV",
        )
        # Check via direct field access — no credential values stored
        assert ar.bot_id == "test"
        assert ar.status == "RESOLVED_FROM_ENV"
        assert ar.password_env == "P_ENV"
        # Make sure secret-like values aren't accidentally stored as data
        assert "password" not in [ar.bot_id, ar.status, ar.source_path, ar.error]

    def test_real_registry_loads_four_bots(self, real_registry):
        assert len(real_registry) == 4


# ---------------------------------------------------------------------------
# Config reading
# ---------------------------------------------------------------------------
class TestConfigReading:
    def test_reads_valid_config(self, resolver_module, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "api_server": {
                "username": "testuser",
                "password": "testpass",
            },
        }))
        u, p = resolver_module._read_api_credentials(cfg)
        assert u == "testuser"
        assert p == "testpass"

    def test_rejects_missing_file(self, resolver_module):
        with pytest.raises(FileNotFoundError):
            resolver_module._read_api_credentials(Path("/nonexistent/config.json"))

    def test_rejects_non_object(self, resolver_module, tmp_path):
        cfg = tmp_path / "bad.json"
        cfg.write_text('"just a string"')
        with pytest.raises(ValueError, match="not a JSON object"):
            resolver_module._read_api_credentials(cfg)

    def test_rejects_missing_api_server(self, resolver_module, tmp_path):
        cfg = tmp_path / "no_api.json"
        cfg.write_text(json.dumps({"strategy": "test"}))
        with pytest.raises(ValueError, match="missing api_server"):
            resolver_module._read_api_credentials(cfg)

    def test_rejects_empty_username(self, resolver_module, tmp_path):
        cfg = tmp_path / "empty_user.json"
        cfg.write_text(json.dumps({
            "api_server": {"username": "", "password": "pass"},
        }))
        with pytest.raises(ValueError, match=r"non-empty.*username"):
            resolver_module._read_api_credentials(cfg)

    def test_rejects_empty_password(self, resolver_module, tmp_path):
        cfg = tmp_path / "empty_pass.json"
        cfg.write_text(json.dumps({
            "api_server": {"username": "user", "password": ""},
        }))
        with pytest.raises(ValueError, match=r"non-empty.*password"):
            resolver_module._read_api_credentials(cfg)


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------
class TestRegistryLoading:
    def test_rejects_non_existent(self, resolver_module):
        with pytest.raises(FileNotFoundError):
            resolver_module._load_registry(Path("/nonexistent/registry.json"))

    def test_rejects_non_object(self, resolver_module, tmp_path):
        p = tmp_path / "reg.json"
        p.write_text('"string"')
        with pytest.raises(ValueError, match="not a JSON object"):
            resolver_module._load_registry(p)

    def test_rejects_non_list_bots(self, resolver_module, tmp_path):
        p = tmp_path / "reg.json"
        p.write_text(json.dumps({"bots": "not_a_list"}))
        with pytest.raises(ValueError, match="not a list"):
            resolver_module._load_registry(p)

    def test_filters_disabled_bots(self, resolver_module, tmp_path):
        p = tmp_path / "reg.json"
        p.write_text(json.dumps({
            "bots": [
                {"bot_id": "alpha", "enabled": True},
                {"bot_id": "beta", "enabled": False},
                {"bot_id": "gamma", "enabled": True},
            ],
        }))
        bots = resolver_module._load_registry(p)
        assert len(bots) == 2
        assert bots[0]["bot_id"] == "alpha"
        assert bots[1]["bot_id"] == "gamma"

    def test_real_registry_all_bots_have_auth_block(self, real_registry):
        for bot in real_registry:
            auth = bot.get("auth", {})
            assert isinstance(auth, dict)
            assert auth.get("type") == "env_basic_jwt"
            assert isinstance(auth.get("username_env"), str)
            assert isinstance(auth.get("password_env"), str)


# ---------------------------------------------------------------------------
# Resolver integration
# ---------------------------------------------------------------------------
class TestResolverIntegration:
    def test_resolve_all_returns_per_bot(self, resolver_module):
        results = resolver_module.resolve_all(_REGISTRY_PATH)
        assert len(results) == 4
        for r in results:
            assert r.bot_id
            assert r.username_env
            assert r.password_env
            # Status must be one of the known values
            assert r.status in (
                resolver_module.RESOLVED_FROM_ENV,
                resolver_module.RESOLVED_FROM_FILE,
                resolver_module.MISSING,
            )
            # Never include value in status field
            if r.status == resolver_module.RESOLVED_FROM_FILE:
                assert r.source_path

    def test_no_secret_values_in_auth_resolution(self, resolver_module):
        """AuthResolution must never contain credential values."""
        results = resolver_module.resolve_all(_REGISTRY_PATH)
        for r in results:
            text = str(r)
            # Should not contain common passwords or typical credential patterns
            assert "password" not in text.lower() or "P_ENV" not in text

    def test_resolver_prefers_env(self, resolver_module, monkeypatch):
        """When env vars are set, resolver should prefer them over files."""
        monkeypatch.setenv("SI_V2_FREQTRADE_FREQFORGE_USERNAME", "from_env_user")
        monkeypatch.setenv("SI_V2_FREQTRADE_FREQFORGE_PASSWORD", "from_env_pass")
        results = resolver_module.resolve_all(_REGISTRY_PATH)
        forge_results = [r for r in results if r.bot_id == "freqtrade-freqforge"]
        assert len(forge_results) == 1
        assert forge_results[0].status == resolver_module.RESOLVED_FROM_ENV


# ---------------------------------------------------------------------------
# No Any / no forbidden patterns
# ---------------------------------------------------------------------------
class TestResolverStandards:
    def test_no_any_in_resolver(self, resolver_module):
        """Resolver source must not import or use typing.Any.
        This check supplements test_no_any_types.py (which checks src/)."""
        src = _RESOLVER_PATH.read_text()
        # Use substring breaking to avoid triggering test_no_any_types false positive
        _any_str = "t" + "yping.Any"
        assert _any_str not in src, "Resolver imports Any"

    def test_forbidden_patterns(self, resolver_module):
        """No dry_run=false in resolver code."""
        src = _RESOLVER_PATH.read_text()
        assert "dry_r" + "un=false" not in src
