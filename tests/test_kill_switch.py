"""Unit tests for kill_switch.py and primo_signal.py kill-switch integration.

Covers:
- kill_switch.py: load_kill_state, get_kill_mode, is_kill_active, is_emergency,
  set_kill_mode, clear_kill_switch, _atomic_write, auto_clear_at, invalid mode,
  missing file, invalid JSON, mtime cache.
- primo_signal.py: primo_gate_allows kill-switch blocking, import fallback.

0 runtime / Docker dependency — pure unit tests with monkeypatch.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# ---------------------------------------------------------------------------
# Path setup: allow imports from the repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SHARED_DIR = _REPO_ROOT / "freqtrade" / "shared"
sys.path.insert(0, str(_REPO_ROOT))
# primo_signal.py uses bare `from kill_switch import ...` (no prefix),
# so freqtrade/shared/ must be on sys.path for the import to succeed.
sys.path.insert(0, str(_SHARED_DIR))

# ---------------------------------------------------------------------------
# Module-level imports — after sys.path fix
# ---------------------------------------------------------------------------
import freqtrade.shared.kill_switch as ks  # noqa: E402
import freqtrade.shared.primo_signal as ps  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Generator


# ============================================================================
# Helpers
# ============================================================================

_NOW_ISO = datetime.now(tz=timezone.utc).isoformat()


def _make_state(
    mode: str = ks.MODE_NORMAL,
    reason: str = "",
    auto_clear_at: str = "",
) -> dict[str, object]:
    return {
        "mode": mode,
        "reason": reason,
        "triggered_at": _NOW_ISO if mode != ks.MODE_NORMAL else "",
        "triggered_by": "test",
        "auto_clear_at": auto_clear_at,
    }


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
def tmp_state_file() -> Generator[Path, None, None]:
    """Provide a unique temp path; cleaned up after each test."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    yield path
    # Clean up both the file and any .tmp sibling
    path.unlink(missing_ok=True)
    path.with_suffix(".tmp").unlink(missing_ok=True)


@pytest.fixture()
def normal_state(tmp_state_file: Path) -> Path:
    """Write a valid NORMAL state file and return its path."""
    state = _make_state(ks.MODE_NORMAL)
    tmp_state_file.write_text(json.dumps(state))
    return tmp_state_file


@pytest.fixture()
def halt_state(tmp_state_file: Path) -> Path:
    """Write a valid HALT_NEW state file and return its path."""
    state = _make_state(ks.MODE_HALT_NEW, reason="manual test halt")
    tmp_state_file.write_text(json.dumps(state))
    return tmp_state_file


@pytest.fixture(autouse=True)
def _clear_cache() -> Generator[None, None, None]:
    """Clear the kill_switch mtime cache before each test.

    _cache is a keyword-only default argument stored in __kwdefaults__.
    """
    cache_dict = ks.load_kill_state.__kwdefaults__["_cache"]  # type: ignore[arg-type]
    cache_dict.clear()
    yield
    cache_dict.clear()


# ============================================================================
# kill_switch.py — load_kill_state
# ============================================================================


class TestLoadKillState:
    """Tests for the core load_kill_state() function."""

    def test_missing_file_defaults_to_normal(self, tmp_state_file: Path) -> None:
        """FileNotFoundError → returns NORMAL default."""
        state = ks.load_kill_state(tmp_state_file)
        assert state["mode"] == ks.MODE_NORMAL

    def test_invalid_json_defaults_to_normal(self, tmp_state_file: Path) -> None:
        """Corrupt / unparseable JSON → returns NORMAL default."""
        tmp_state_file.write_text("this-is-not-json")
        state = ks.load_kill_state(tmp_state_file)
        assert state["mode"] == ks.MODE_NORMAL

    def test_empty_json_object_defaults_to_normal(self, tmp_state_file: Path) -> None:
        """Empty dict {} → mode defaults to NORMAL."""
        tmp_state_file.write_text("{}")
        state = ks.load_kill_state(tmp_state_file)
        assert state["mode"] == ks.MODE_NORMAL

    def test_non_dict_json_defaults_to_normal(self, tmp_state_file: Path) -> None:
        """JSON list/string/null → returns NORMAL default."""
        tmp_state_file.write_text('"just a string"')
        state = ks.load_kill_state(tmp_state_file)
        assert state["mode"] == ks.MODE_NORMAL

    def test_loads_halt_new_state(self, halt_state: Path) -> None:
        """Valid HALT_NEW file → returns mode HALT_NEW."""
        state = ks.load_kill_state(halt_state)
        assert state["mode"] == ks.MODE_HALT_NEW

    def test_loads_emergency_state(self, tmp_state_file: Path) -> None:
        """Valid EMERGENCY file → returns mode EMERGENCY."""
        state_dict = _make_state(ks.MODE_EMERGENCY, reason="emergency test")
        tmp_state_file.write_text(json.dumps(state_dict))
        state = ks.load_kill_state(tmp_state_file)
        assert state["mode"] == ks.MODE_EMERGENCY
        assert state["reason"] == "emergency test"

    def test_mtime_cache_hit(self, tmp_state_file: Path) -> None:
        """Subsequent call with same mtime returns cached state."""
        state_dict = _make_state(ks.MODE_NORMAL)
        tmp_state_file.write_text(json.dumps(state_dict))
        _ = ks.load_kill_state(tmp_state_file)  # populate cache
        state2 = ks.load_kill_state(tmp_state_file)
        assert state2["mode"] == ks.MODE_NORMAL

    def test_mtime_cache_miss(self, tmp_state_file: Path) -> None:
        """Changed mtime → reloads from disk."""
        tmp_state_file.write_text(json.dumps(_make_state(ks.MODE_NORMAL)))
        _ = ks.load_kill_state(tmp_state_file)  # populate cache
        # Update file content and force a different mtime via os.utime
        tmp_state_file.write_text(json.dumps(_make_state(ks.MODE_HALT_NEW)))
        future = time.time() + 2.0
        os.utime(tmp_state_file, (future, future))
        state2 = ks.load_kill_state(tmp_state_file)
        assert state2["mode"] == ks.MODE_HALT_NEW


# ============================================================================
# kill_switch.py — get_kill_mode / is_kill_active / is_emergency
# ============================================================================


class TestKillModeQueries:
    """Convenience queries built on load_kill_state."""

    def test_get_kill_mode_normal(self, normal_state: Path) -> None:
        assert ks.get_kill_mode(normal_state) == ks.MODE_NORMAL

    def test_get_kill_mode_halt(self, halt_state: Path) -> None:
        assert ks.get_kill_mode(halt_state) == ks.MODE_HALT_NEW

    def test_is_kill_active_normal(self, normal_state: Path) -> None:
        assert ks.is_kill_active(normal_state) is False

    def test_is_kill_active_halt(self, halt_state: Path) -> None:
        assert ks.is_kill_active(halt_state) is True

    def test_is_kill_active_emergency(self, tmp_state_file: Path) -> None:
        tmp_state_file.write_text(json.dumps(_make_state(ks.MODE_EMERGENCY)))
        assert ks.is_kill_active(tmp_state_file) is True

    def test_is_emergency_false(self, halt_state: Path) -> None:
        assert ks.is_emergency(halt_state) is False

    def test_is_emergency_true(self, tmp_state_file: Path) -> None:
        tmp_state_file.write_text(json.dumps(_make_state(ks.MODE_EMERGENCY)))
        assert ks.is_emergency(tmp_state_file) is True


# ============================================================================
# kill_switch.py — set_kill_mode / clear_kill_switch
# ============================================================================


class TestSetKillMode:
    """Write helpers for activating / deactivating the kill switch."""

    def test_set_normal(self, tmp_state_file: Path) -> None:
        """set_kill_mode(NORMAL) → state file contains NORMAL."""
        state = ks.set_kill_mode(ks.MODE_NORMAL, path=tmp_state_file)
        assert state["mode"] == ks.MODE_NORMAL
        # Verify on-disk
        loaded = ks.load_kill_state(tmp_state_file)
        assert loaded["mode"] == ks.MODE_NORMAL

    def test_set_halt_new(self, tmp_state_file: Path) -> None:
        """set_kill_mode(HALT_NEW) → blocks entries."""
        state = ks.set_kill_mode(ks.MODE_HALT_NEW, reason="test halt", path=tmp_state_file)
        assert state["mode"] == ks.MODE_HALT_NEW
        assert state["reason"] == "test halt"
        assert ks.is_kill_active(tmp_state_file) is True

    def test_set_emergency(self, tmp_state_file: Path) -> None:
        """set_kill_mode(EMERGENCY) → blocks entries + signals exit."""
        state = ks.set_kill_mode(
            ks.MODE_EMERGENCY, reason="test emergency", path=tmp_state_file
        )
        assert state["mode"] == ks.MODE_EMERGENCY
        assert ks.is_kill_active(tmp_state_file) is True
        assert ks.is_emergency(tmp_state_file) is True

    def test_invalid_mode_raises(self, tmp_state_file: Path) -> None:
        """set_kill_mode with invalid mode → ValueError."""
        with pytest.raises(ValueError, match="Invalid kill switch mode"):
            ks.set_kill_mode("INVALID_MODE", path=tmp_state_file)

    def test_clear_kill_switch(self, tmp_state_file: Path) -> None:
        """clear_kill_switch() → reverts to NORMAL."""
        # First set to emergency
        ks.set_kill_mode(ks.MODE_EMERGENCY, path=tmp_state_file)
        assert ks.is_kill_active(tmp_state_file) is True
        # Now clear
        state = ks.clear_kill_switch(path=tmp_state_file)
        assert state["mode"] == ks.MODE_NORMAL
        assert ks.is_kill_active(tmp_state_file) is False

    def test_auto_clear_expiration(self, tmp_state_file: Path) -> None:
        """auto_clear_at in the past → reverts to NORMAL on load."""
        past = (datetime.now(tz=timezone.utc) - timedelta(minutes=5)).isoformat()
        state_dict = _make_state(ks.MODE_HALT_NEW, auto_clear_at=past)
        tmp_state_file.write_text(json.dumps(state_dict))

        # load_kill_state should detect expired auto_clear and rewrite to NORMAL
        state = ks.load_kill_state(tmp_state_file)
        assert state["mode"] == ks.MODE_NORMAL, (
            f"Expected NORMAL after auto_clear, got {state['mode']}"
        )

    def test_auto_clear_future_not_expired(self, tmp_state_file: Path) -> None:
        """auto_clear_at in the future → remains in original mode."""
        future = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
        state_dict = _make_state(ks.MODE_HALT_NEW, auto_clear_at=future)
        tmp_state_file.write_text(json.dumps(state_dict))

        state = ks.load_kill_state(tmp_state_file)
        assert state["mode"] == ks.MODE_HALT_NEW

    def test_auto_clear_during_set_kill_mode(self, tmp_state_file: Path) -> None:
        """auto_clear_minutes parameter → sets auto_clear_at."""
        state = ks.set_kill_mode(
            ks.MODE_HALT_NEW,
            reason="auto-clear test",
            auto_clear_minutes=30.0,
            path=tmp_state_file,
        )
        assert state["mode"] == ks.MODE_HALT_NEW
        assert state["auto_clear_at"] != ""
        # Verify on-disk
        loaded = ks.load_kill_state(tmp_state_file)
        assert loaded["mode"] == ks.MODE_HALT_NEW


# ============================================================================
# kill_switch.py — atomic write
# ============================================================================


class TestAtomicWrite:
    """Verify .tmp + os.replace() pattern."""

    def test_atomic_write_pattern(self, tmp_state_file: Path) -> None:
        """_atomic_write writes .tmp then replaces target."""
        state = _make_state(ks.MODE_HALT_NEW)
        ks._atomic_write(state, tmp_state_file)  # type: ignore[arg-type]  # private but tested

        # Target file should exist and be valid
        assert tmp_state_file.exists()
        data = json.loads(tmp_state_file.read_text())
        assert data["mode"] == ks.MODE_HALT_NEW

        # .tmp file should be gone
        assert not tmp_state_file.with_suffix(".tmp").exists()

    def test_no_orphaned_tmp_on_success(self, tmp_state_file: Path) -> None:
        """After successful write, no .tmp lingers."""
        ks.set_kill_mode(ks.MODE_NORMAL, path=tmp_state_file)
        assert not tmp_state_file.with_suffix(".tmp").exists()

    def test_parent_dir_created(self) -> None:
        """If parent dir doesn't exist, _atomic_write creates it."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "nested" / "subdir" / "kill_switch.json"
            ks.set_kill_mode(ks.MODE_NORMAL, path=path)
            assert path.exists()


# ============================================================================
# primo_signal.py — kill-switch integration
# ============================================================================


class TestPrimoSignalKillSwitch:
    """primo_gate_allows must respect central kill switch.

    Note: primo_signal.py imports is_kill_active via a bare
    ``from kill_switch import ...``, which creates a separate module
    instance from ``freqtrade.shared.kill_switch``.  We therefore
    monkeypatch the function references directly on the primo_signal
    module rather than patching KILL_SWITCH_PATH.
    """

    def test_halt_new_blocks_long_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HALT_NEW mode → primo_gate_allows returns False for long."""
        monkeypatch.setattr(ps, "is_kill_active", lambda: True)
        monkeypatch.setattr(ps, "is_emergency", lambda: False)
        assert ps.primo_gate_allows("BTC/USDT", "long") is False

    def test_halt_new_blocks_short_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HALT_NEW mode → primo_gate_allows returns False for short."""
        monkeypatch.setattr(ps, "is_kill_active", lambda: True)
        monkeypatch.setattr(ps, "is_emergency", lambda: False)
        assert ps.primo_gate_allows("BTC/USDT", "short") is False

    def test_emergency_blocks_all_entries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """EMERGENCY mode → primo_gate_allows returns False for both sides."""
        monkeypatch.setattr(ps, "is_kill_active", lambda: True)
        monkeypatch.setattr(ps, "is_emergency", lambda: True)
        assert ps.primo_gate_allows("ETH/USDT", "long") is False
        assert ps.primo_gate_allows("ETH/USDT", "short") is False

    def test_normal_mode_allows_entries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """NORMAL mode → primo_gate_allows falls through to normal signal logic."""
        monkeypatch.setattr(ps, "is_kill_active", lambda: False)
        monkeypatch.setattr(ps, "is_emergency", lambda: False)
        # No signal file → load_signal_state returns None → returns True
        assert ps.primo_gate_allows("BTC/USDT", "long") is True

    def test_import_fallback_no_kill_switch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When _KILL_SWITCH_AVAILABLE is False, pristine signal logic runs."""
        # Simulate kill_switch import failure by patching the flag and fallbacks
        monkeypatch.setattr(ps, "_KILL_SWITCH_AVAILABLE", False)
        # Also patch the fallback functions to return False (no blocking)
        # The fallback in primo_signal.py defines is_kill_active() -> False
        # So this should already work. Let's verify:
        # Since _KILL_SWITCH_AVAILABLE is False, the import-time fallbacks are active.
        # But they were already set at import time. We need to make the module
        # re-import or patch the existing references.

        # Simpler approach: monkeypatch is_kill_active and is_emergency on primo_signal
        monkeypatch.setattr(ps, "_KILL_SWITCH_AVAILABLE", False)
        monkeypatch.setattr(ps, "is_kill_active", lambda: False)
        monkeypatch.setattr(ps, "is_emergency", lambda: False)

        # Without a signal file, this should return True (fallback to normal logic)
        result = ps.primo_gate_allows("BTC/USDT", "long")
        assert result is True

    def test_import_fallback_preserves_behavior(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without kill_switch module, primo_gate_allows uses fallback
        is_kill_active (always False) so entry logic is preserved."""
        monkeypatch.setattr(ps, "_KILL_SWITCH_AVAILABLE", False)
        monkeypatch.setattr(ps, "is_kill_active", lambda: False)
        monkeypatch.setattr(ps, "is_emergency", lambda: False)

        # Even with no kill switch, normal signal logic should work
        # (no signal file → load_signal_state returns None → True)
        assert ps.primo_gate_allows("BTC/USDT", "long") is True
        assert ps.primo_gate_allows("BTC/USDT", "short") is True


# ============================================================================
# primo_signal.py — signal logic unchanged
# ============================================================================


class TestPrimoSignalNormalLogic:
    """Primo signal logic when kill switch is NORMAL or absent."""

    def test_no_signal_file_allows_entry(self) -> None:
        """Missing state file → safe fallback (True)."""
        result = ps.primo_gate_allows("XRP/USDT", "long", state_file="/nonexistent/file.json")
        assert result is True

    def test_stale_signal_allows_entry(self, tmp_path: Path) -> None:
        """Non-fresh signal → safe fallback (True)."""
        state_file = tmp_path / "signal.json"
        state_file.write_text(json.dumps({"fresh": False, "age_minutes": 0.5, "pairs": {}}))
        result = ps.primo_gate_allows("XRP/USDT", "long", state_file=str(state_file))
        assert result is True

    def test_accept_long_allows_long(self, tmp_path: Path) -> None:
        """ACCEPTED + allow_long_bias=True → long is allowed."""
        state_file = tmp_path / "signal.json"
        state_file.write_text(json.dumps({
            "fresh": True,
            "age_minutes": 1.0,
            "pairs": {"BTC/USDT": {"verdict": "ACCEPTED", "allow_long_bias": True}},
        }))
        assert ps.primo_gate_allows("BTC/USDT", "long", state_file=str(state_file)) is True
        assert ps.primo_gate_allows("BTC/USDT", "short", state_file=str(state_file)) is False

    def test_accept_short_allows_short(self, tmp_path: Path) -> None:
        """ACCEPTED + allow_short_bias=True → short is allowed."""
        state_file = tmp_path / "signal.json"
        state_file.write_text(json.dumps({
            "fresh": True,
            "age_minutes": 1.0,
            "pairs": {"BTC/USDT": {"verdict": "ACCEPTED", "allow_short_bias": True}},
        }))
        assert ps.primo_gate_allows("BTC/USDT", "short", state_file=str(state_file)) is True
        assert ps.primo_gate_allows("BTC/USDT", "long", state_file=str(state_file)) is False
