"""Tests for drawdown_guard credential externalization (Issue #316).

Verifies that:
- _resolve_bot_auth uses environment variables as primary source
- Falls back to config files when env vars are absent
- Returns empty password (safe failure) when no source provides credentials
- No hardcoded passwords exist in the BOTS dict
- All four fleet bots have password_env keys (fleet-wide coverage)

0 runtime / Docker dependency — pure unit tests with monkeypatch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

# Path setup
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ORCH_SCRIPTS = _REPO_ROOT / "orchestrator" / "scripts"
sys.path.insert(0, str(_ORCH_SCRIPTS))


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Remove all FREQTRADE_*_PASS env vars before each test."""
    import os
    for key in list(os.environ.keys()):
        if "FREQTRADE" in key and "PASS" in key:
            monkeypatch.delenv(key, raising=False)
    yield


class TestNoHardcodedPasswords:
    """Verify no real password values are committed in the BOTS dict."""

    def test_bots_dict_has_no_password_key(self) -> None:
        """Every bot in BOTS must use 'password_env', not 'password'."""
        import drawdown_guard as dg

        for bot_id, cfg in dg.BOTS.items():
            assert "password" not in cfg, (
                f"Bot '{bot_id}' has hardcoded 'password' key — "
                "must use 'password_env' instead"
            )

    def test_bots_dict_has_password_env_key(self) -> None:
        """Every bot in BOTS must have a 'password_env' key."""
        import drawdown_guard as dg

        for bot_id, cfg in dg.BOTS.items():
            assert "password_env" in cfg, (
                f"Bot '{bot_id}' is missing 'password_env' key"
            )
            assert isinstance(cfg["password_env"], str)
            assert cfg["password_env"].startswith("FREQTRADE_"), (
                f"Bot '{bot_id}' password_env should start with 'FREQTRADE_'"
            )

    def test_all_four_fleet_bots_present(self) -> None:
        """All four active fleet bots must be in the BOTS dict."""
        import drawdown_guard as dg

        expected_bots = {"freqforge", "canary", "regime_hybrid", "rebel"}
        assert set(dg.BOTS.keys()) == expected_bots

    def test_password_env_values_are_not_real_secrets(self) -> None:
        """password_env values must be env var NAMES, not secret values."""
        import drawdown_guard as dg

        for bot_id, cfg in dg.BOTS.items():
            env_name = cfg["password_env"]
            # Env var names should be reasonable length (< 50 chars)
            assert len(env_name) < 50, (
                f"Bot '{bot_id}' password_env looks like a value, not a name: len={len(env_name)}"
            )
            # Must not contain spaces or special chars typical of passwords
            assert " " not in env_name
            assert not any(c in env_name for c in "!@#$%^&*(){}[]")


class TestResolveBotAuth:
    """Test the _resolve_bot_auth credential resolution logic."""

    def test_env_var_resolution_primary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When env var is set, it takes priority over config files."""
        import drawdown_guard as dg

        cfg = {
            "container": "test-container",
            "port": 8080,
            "user": "testuser",
            "password_env": "TEST_BOT_PASS",
            "config_host": "/nonexistent/config.json",
        }
        monkeypatch.setenv("TEST_BOT_PASS", "env-provided-password")

        result = dg._resolve_bot_auth("test_bot", cfg)
        assert result["password"] == "env-provided-password"
        assert result["user"] == "testuser"
        assert result["port"] == 8080

    def test_config_file_fallback(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When env var is absent, falls back to config file."""
        import drawdown_guard as dg

        # Create a temp config file with credentials
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "api_server": {
                "listen_port": 8085,
                "username": "configuser",
                "password": "config-provided-password",
            }
        }))

        cfg = {
            "container": "test-container",
            "port": 8080,
            "user": "default-user",
            "password_env": "ABSENT_ENV_VAR",
            "config_host": str(config_file),
        }
        monkeypatch.delenv("ABSENT_ENV_VAR", raising=False)

        result = dg._resolve_bot_auth("test_bot", cfg)
        assert result["password"] == "config-provided-password"
        assert result["user"] == "configuser"
        assert result["port"] == 8085

    @pytest.fixture(autouse=True)
    def _mock_log(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mock drawdown_guard.log to avoid filesystem access on CI runners."""
        import drawdown_guard as dg
        monkeypatch.setattr(dg, "log", lambda *a, **kw: None)

    def test_no_credentials_resolves_to_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When no source provides credentials, password is empty (safe failure)."""
        import drawdown_guard as dg

        cfg = {
            "container": "test-container",
            "port": 8080,
            "user": "testuser",
            "password_env": "ABSENT_ENV_VAR",
            "config_host": "/nonexistent/config.json",
        }
        monkeypatch.delenv("ABSENT_ENV_VAR", raising=False)

        result = dg._resolve_bot_auth("test_bot", cfg)
        assert result["password"] == "", (
            "Password must be empty when no credential source is available"
        )

    def test_empty_env_var_falls_through(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Empty env var string should fall through to config file."""
        import drawdown_guard as dg

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "api_server": {
                "listen_port": 8080,
                "username": "cfguser",
                "password": "from-config",
            }
        }))

        cfg = {
            "container": "test-container",
            "port": 8080,
            "user": "default",
            "password_env": "EMPTY_TEST_PASS",
            "config_host": str(config_file),
        }
        monkeypatch.setenv("EMPTY_TEST_PASS", "")  # Set but empty

        result = dg._resolve_bot_auth("test_bot", cfg)
        assert result["password"] == "from-config"

    def test_fleet_wide_env_var_names(self) -> None:
        """All four bots have distinct env var names (no collision)."""
        import drawdown_guard as dg

        env_names = [cfg["password_env"] for cfg in dg.BOTS.values()]
        assert len(env_names) == len(set(env_names)), (
            "Duplicate env var names across bots — fleet collision"
        )
