from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed")

from pathlib import Path  # noqa: E402


# ===========================================================================
# Bridge auth tests
# ===========================================================================


class TestBridgeAuth:
    """Bridge endpoint auth: /status and / require API key when configured."""

    def test_health_is_always_open_without_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Health endpoint is not protected by auth."""
        import bridge.hermes_primo_bridge as bridge_mod

        monkeypatch.setattr(bridge_mod, "BRIDGE_API_KEY", "secret")
        from bridge.hermes_primo_bridge import _auth_required

        handler = _make_handler(headers={})
        assert _auth_required(handler) is False

    def test_bridge_auth_blocks_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import bridge.hermes_primo_bridge as bridge_mod

        monkeypatch.setattr(bridge_mod, "BRIDGE_API_KEY", "secret")
        from bridge.hermes_primo_bridge import _auth_required

        handler = _make_handler(headers={})
        assert _auth_required(handler) is False

    def test_bridge_auth_passes_with_correct_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import bridge.hermes_primo_bridge as bridge_mod

        monkeypatch.setattr(bridge_mod, "BRIDGE_API_KEY", "correct-key")
        from bridge.hermes_primo_bridge import _auth_required

        handler = _make_handler(headers={"X-API-Key": "correct-key"})
        assert _auth_required(handler) is True

    def test_bridge_auth_passes_without_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import bridge.hermes_primo_bridge as bridge_mod

        monkeypatch.setattr(bridge_mod, "BRIDGE_API_KEY", "")
        from bridge.hermes_primo_bridge import _auth_required

        handler = _make_handler(headers={})
        assert _auth_required(handler) is True

    def test_bridge_auth_fails_with_wrong_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import bridge.hermes_primo_bridge as bridge_mod

        monkeypatch.setattr(bridge_mod, "BRIDGE_API_KEY", "real-key")
        from bridge.hermes_primo_bridge import _auth_required

        handler = _make_handler(headers={"X-API-Key": "wrong-key"})
        assert _auth_required(handler) is False


# ===========================================================================
# Primo auth tests
# ===========================================================================


class TestPrimoAuth:
    """Primo endpoint auth: /signal and /pairs require API key when configured."""

    def test_primo_auth_blocks_without_key(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("PRIMO_LOG_DIR", str(tmp_path / "primo_logs"))
        import primo.primo_api as primo_mod

        monkeypatch.setattr(primo_mod, "PRIMO_API_KEY", "secret")
        mock_req = _make_primo_request(headers={})
        with pytest.raises(fastapi.HTTPException) as exc:
            primo_mod._require_auth(mock_req)
        assert exc.value.status_code == 401

    def test_primo_auth_passes_with_correct_key(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("PRIMO_LOG_DIR", str(tmp_path / "primo_logs"))
        import primo.primo_api as primo_mod

        monkeypatch.setattr(primo_mod, "PRIMO_API_KEY", "my-key")
        mock_req = _make_primo_request(headers={"X-API-Key": "my-key"})
        primo_mod._require_auth(mock_req)

    def test_primo_auth_passes_without_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("PRIMO_LOG_DIR", str(tmp_path / "primo_logs"))
        import primo.primo_api as primo_mod

        monkeypatch.setattr(primo_mod, "PRIMO_API_KEY", "")
        mock_req = _make_primo_request(headers={})
        primo_mod._require_auth(mock_req)

    def test_primo_auth_raises_401_with_wrong_key(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("PRIMO_LOG_DIR", str(tmp_path / "primo_logs"))
        import primo.primo_api as primo_mod

        monkeypatch.setattr(primo_mod, "PRIMO_API_KEY", "correct")
        mock_req = _make_primo_request(headers={"X-API-Key": "wrong"})
        with pytest.raises(fastapi.HTTPException) as exc:
            primo_mod._require_auth(mock_req)
        assert exc.value.status_code == 401


# ===========================================================================
# Helpers
# ===========================================================================


def _make_handler(headers: dict[str, str]):
    return type("Handler", (), {"headers": type("Headers", (), {"get": lambda self, key, default="": headers.get(key, default)})()})()


def _make_primo_request(headers: dict[str, str]):
    return type(
        "MockRequest",
        (),
        {
            "headers": type("Headers", (), {"get": lambda self, key, default="": headers.get(key, default)})()
        },
    )()
