from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SHARED_DIR = ROOT / "freqtrade" / "shared"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SHARED_DIR))

import freqtrade.shared.kill_switch as kill_switch  # noqa: E402
import freqtrade.shared.primo_signal as primo_signal  # noqa: E402


def _state_file(tmp_path: Path, pairs: dict[str, object]) -> Path:
    path = tmp_path / "primo_signal_state.json"
    path.write_text(
        json.dumps(
            {
                "fresh": True,
                "age_minutes": 0.1,
                "pairs": pairs,
            }
        )
    )
    return path


@pytest.fixture(autouse=True)
def _clear_kill_cache() -> None:
    kwdefaults = kill_switch.load_kill_state.__kwdefaults__
    assert kwdefaults is not None
    cache = kwdefaults["_cache"]
    cache.clear()


def test_normal_state_keeps_strategy_fallback_when_no_signal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(primo_signal, "is_kill_active", lambda: False)
    monkeypatch.setattr(primo_signal, "is_emergency", lambda: False)

    assert primo_signal.primo_gate_allows("BTC/USDT", "long", state_file=str(tmp_path / "missing.json")) is True


def test_watch_only_signal_blocks_entries_without_exchange_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(primo_signal, "is_kill_active", lambda: False)
    monkeypatch.setattr(primo_signal, "is_emergency", lambda: False)
    state = _state_file(
        tmp_path,
        {
            "BTC/USDT": {
                "verdict": "WATCH_ONLY",
                "action": "HOLD",
                "allow_long_bias": False,
                "allow_short_bias": False,
            }
        },
    )

    assert primo_signal.primo_gate_allows("BTC/USDT:USDT", "long", state_file=str(state)) is False
    assert primo_signal.primo_gate_allows("BTC/USDT:USDT", "short", state_file=str(state)) is False


def test_emergency_state_blocks_all_entries_and_signals_exit_intent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "kill_switch.json"
    kill_switch.set_kill_mode(kill_switch.MODE_EMERGENCY, reason="dry-run integration test", path=state_path)

    monkeypatch.setattr(primo_signal, "is_kill_active", lambda: kill_switch.is_kill_active(state_path))
    monkeypatch.setattr(primo_signal, "is_emergency", lambda: kill_switch.is_emergency(state_path))

    assert kill_switch.get_kill_mode(state_path) == kill_switch.MODE_EMERGENCY
    assert kill_switch.is_emergency(state_path) is True
    assert primo_signal.primo_gate_allows("ETH/USDT:USDT", "long") is False
    assert primo_signal.primo_gate_allows("ETH/USDT:USDT", "short") is False


def test_halt_new_state_blocks_entries_but_is_not_emergency(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_path = tmp_path / "kill_switch.json"
    kill_switch.set_kill_mode(kill_switch.MODE_HALT_NEW, reason="dry-run integration test", path=state_path)

    monkeypatch.setattr(primo_signal, "is_kill_active", lambda: kill_switch.is_kill_active(state_path))
    monkeypatch.setattr(primo_signal, "is_emergency", lambda: kill_switch.is_emergency(state_path))

    assert kill_switch.get_kill_mode(state_path) == kill_switch.MODE_HALT_NEW
    assert kill_switch.is_emergency(state_path) is False
    assert primo_signal.primo_gate_allows("SOL/USDT:USDT", "long") is False
