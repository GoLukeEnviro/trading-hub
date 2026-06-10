"""Tests for the environment gate (config/gate.py).

Uses monkeypatch to set / clear environment variables.
"""

from __future__ import annotations

import pytest

from si_v2.config.gate import SI_V2_ENABLE_REAL_ADAPTERS, check_env_enabled, require_env_enabled


class TestCheckEnvEnabled:
    """Tests for :func:`check_env_enabled`."""

    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Not set in env => returns False (default)."""
        monkeypatch.delenv(SI_V2_ENABLE_REAL_ADAPTERS, raising=False)
        assert check_env_enabled(SI_V2_ENABLE_REAL_ADAPTERS) is False

    def test_enabled_when_set_to_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set to ``\"1\"`` => returns True."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")
        assert check_env_enabled(SI_V2_ENABLE_REAL_ADAPTERS) is True

    def test_disabled_when_set_to_0(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set to ``\"0\"`` => returns False."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "0")
        assert check_env_enabled(SI_V2_ENABLE_REAL_ADAPTERS) is False

    def test_disabled_when_set_to_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set to ``\"true\"`` => returns False."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "true")
        assert check_env_enabled(SI_V2_ENABLE_REAL_ADAPTERS) is False

    def test_custom_default_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Not set in env => returns custom default."""
        monkeypatch.delenv(SI_V2_ENABLE_REAL_ADAPTERS, raising=False)
        assert check_env_enabled(SI_V2_ENABLE_REAL_ADAPTERS, default=True) is True

    def test_custom_flag_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Works with an arbitrary flag name."""
        monkeypatch.setenv("MY_TEST_FLAG", "1")
        assert check_env_enabled("MY_TEST_FLAG") is True


class TestRequireEnvEnabled:
    """Tests for :func:`require_env_enabled`."""

    def test_raises_when_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises RuntimeError when flag is absent."""
        monkeypatch.delenv(SI_V2_ENABLE_REAL_ADAPTERS, raising=False)
        with pytest.raises(RuntimeError, match=SI_V2_ENABLE_REAL_ADAPTERS):
            require_env_enabled(SI_V2_ENABLE_REAL_ADAPTERS, "TestComponent")

    def test_raises_when_set_to_0(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises RuntimeError when flag is ``\"0\"``."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "0")
        with pytest.raises(RuntimeError, match=SI_V2_ENABLE_REAL_ADAPTERS):
            require_env_enabled(SI_V2_ENABLE_REAL_ADAPTERS, "TestComponent")

    def test_passes_when_set_to_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No error when flag is ``\"1\"``."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")
        require_env_enabled(SI_V2_ENABLE_REAL_ADAPTERS, "TestComponent")  # should not raise

    def test_error_includes_component_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Error message includes the component name."""
        monkeypatch.delenv(SI_V2_ENABLE_REAL_ADAPTERS, raising=False)
        with pytest.raises(RuntimeError, match="MyAdapter"):
            require_env_enabled(SI_V2_ENABLE_REAL_ADAPTERS, "MyAdapter")
