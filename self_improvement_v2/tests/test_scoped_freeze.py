"""R5B Path 2 — Bot-scoped freeze architecture tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Path setup for freqtrade.shared imports
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SHARED_DIR = _REPO_ROOT / "freqtrade" / "shared"
SRC = _REPO_ROOT / "self_improvement_v2" / "src"
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_SHARED_DIR))
sys.path.insert(0, str(SRC))

import freqtrade.shared.kill_switch as ks  # noqa: E402

from si_v2.safety.halt_bot_circuit_breaker import (  # noqa: E402
    HALT_BOT_HALTED,
    HALT_BOT_NORMAL,
    HALT_BOT_UNKNOWN,
    BotSafetyState,
    HaltBotRegistry,
)
from si_v2.safety.scoped_freeze import (  # noqa: E402
    FLEET_PRECEDENCE_ORDER,
    ScopedEntryDecision,
    freeze_all_canonical_bots,
    freeze_bot,
    list_frozen_bots,
    resolve_bot_entry,
    resolve_bot_entry_from_states,
    unfreeze_bot,
)


@pytest.fixture
def reg_path(tmp_path: Path) -> Path:
    return tmp_path / "halt_state.json"


@pytest.fixture
def registry(reg_path: Path) -> HaltBotRegistry:
    return HaltBotRegistry(state_path=reg_path)


@pytest.fixture
def fleet_normal(monkeypatch) -> None:
    """Mock fleet kill-switch to NORMAL."""
    monkeypatch.setattr(ks, "get_kill_mode", lambda *a, **kw: "NORMAL")
    monkeypatch.setattr(ks, "is_kill_active", lambda *a, **kw: False)


@pytest.fixture
def fleet_halt_new(monkeypatch) -> None:
    monkeypatch.setattr(ks, "get_kill_mode", lambda *a, **kw: "HALT_NEW")
    monkeypatch.setattr(ks, "is_kill_active", lambda *a, **kw: True)


# ---------------------------------------------------------------------------
# resolve_bot_entry
# ---------------------------------------------------------------------------


class TestResolveBotEntry:
    def test_fleet_halt_new_blocks_all(
        self, fleet_halt_new, registry: HaltBotRegistry
    ) -> None:
        assert resolve_bot_entry("freqtrade-freqforge", fleet_mode="HALT_NEW",
                                 registry=registry) == ScopedEntryDecision.BLOCKED

    def test_fleet_normal_bot_not_halted_allows(
        self, fleet_normal, registry: HaltBotRegistry
    ) -> None:
        registry.halt("freqtrade-freqforge", reason="init", actor="test")
        registry.clear("freqtrade-freqforge", actor="test", evidence="init")
        assert resolve_bot_entry("freqtrade-freqforge", fleet_mode="NORMAL",
                                 registry=registry) == ScopedEntryDecision.ALLOWED

    def test_fleet_normal_bot_halted_blocks(
        self, fleet_normal, registry: HaltBotRegistry
    ) -> None:
        registry.halt("freqtrade-freqforge", reason="r", actor="a")
        assert resolve_bot_entry("freqtrade-freqforge", fleet_mode="NORMAL",
                                 registry=registry) == ScopedEntryDecision.BLOCKED

    def test_fleet_normal_unknown_bot_fail_closed(
        self, fleet_normal, registry: HaltBotRegistry
    ) -> None:
        # unknown bot → is_halted returns True (fail-closed)
        assert resolve_bot_entry("unknown-bot-123", fleet_mode="NORMAL",
                                 registry=registry) == ScopedEntryDecision.BLOCKED

    def test_fleet_reduce_only_blocks(
        self, registry: HaltBotRegistry
    ) -> None:
        assert resolve_bot_entry("freqtrade-freqforge", fleet_mode="REDUCE_ONLY",
                                 registry=registry) == ScopedEntryDecision.BLOCKED

    def test_fleet_emergency_blocks(
        self, registry: HaltBotRegistry
    ) -> None:
        assert resolve_bot_entry("freqtrade-freqforge", fleet_mode="EMERGENCY",
                                 registry=registry) == ScopedEntryDecision.BLOCKED


# ---------------------------------------------------------------------------
# resolve_bot_entry_from_states (pure function)
# ---------------------------------------------------------------------------


class TestResolveBotEntryFromStates:
    def test_normal_and_normal_allows(self) -> None:
        bot = BotSafetyState(bot_id="test", mode=HALT_BOT_NORMAL)
        assert resolve_bot_entry_from_states(
            fleet_mode="NORMAL", bot_state=bot
        ) == ScopedEntryDecision.ALLOWED

    def test_halt_new_and_normal_bot_blocks(self) -> None:
        bot = BotSafetyState(bot_id="test", mode=HALT_BOT_NORMAL)
        assert resolve_bot_entry_from_states(
            fleet_mode="HALT_NEW", bot_state=bot
        ) == ScopedEntryDecision.BLOCKED

    def test_normal_and_unknown_bot_fail_closed(self) -> None:
        bot = BotSafetyState(bot_id="test", mode=HALT_BOT_UNKNOWN)
        assert resolve_bot_entry_from_states(
            fleet_mode="NORMAL", bot_state=bot
        ) == ScopedEntryDecision.BLOCKED


# ---------------------------------------------------------------------------
# freeze_bot / unfreeze_bot
# ---------------------------------------------------------------------------


class TestFreezeUnfreeze:
    def test_freeze_when_fleet_normal(self, fleet_normal, reg_path: Path) -> None:
        st = freeze_bot("freqtrade-freqforge", reason="t", actor="t",
                        registry_path=reg_path)
        assert st.mode == HALT_BOT_HALTED

    def test_freeze_when_fleet_not_normal_raises(
        self, fleet_halt_new, reg_path: Path
    ) -> None:
        with pytest.raises(RuntimeError, match="Fleet kill-switch is active"):
            freeze_bot("freqtrade-freqforge", reason="t", actor="t",
                       registry_path=reg_path)

    def test_unfreeze_requires_evidence(self, fleet_normal, reg_path: Path) -> None:
        freeze_bot("freqtrade-freqforge", reason="t", actor="t",
                   registry_path=reg_path)
        st = unfreeze_bot("freqtrade-freqforge", actor="op",
                          evidence="incident-123", registry_path=reg_path)
        assert st.mode == HALT_BOT_NORMAL


# ---------------------------------------------------------------------------
# list_frozen_bots
# ---------------------------------------------------------------------------


class TestListFrozenBots:
    def test_returns_only_halted(self, fleet_normal, reg_path: Path) -> None:
        freeze_bot("freqtrade-freqforge", reason="r", actor="a",
                   registry_path=reg_path)
        freeze_bot("freqtrade-regime-hybrid", reason="r", actor="a",
                   registry_path=reg_path)
        assert set(list_frozen_bots(reg_path)) == {
            "freqtrade-freqforge", "freqtrade-regime-hybrid"
        }


# ---------------------------------------------------------------------------
# freeze_all_canonical_bots
# ---------------------------------------------------------------------------


class TestFreezeAllCanonicalBots:
    def test_freezes_all_four(self, fleet_normal, reg_path: Path) -> None:
        results = freeze_all_canonical_bots(reason="Gate test", actor="test",
                                            registry_path=reg_path)
        assert len(results) == 4
        for st in results.values():
            assert st.mode == HALT_BOT_HALTED

    def test_custom_bot_list(self, fleet_normal, reg_path: Path) -> None:
        results = freeze_all_canonical_bots(
            reason="t", actor="t", registry_path=reg_path,
            bot_ids=["freqtrade-freqforge", "freqtrade-freqforge-canary"]
        )
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Precedence order contract
# ---------------------------------------------------------------------------


class TestPrecedenceOrder:
    def test_fleet_precedence_correct(self) -> None:
        assert FLEET_PRECEDENCE_ORDER[0] == "EMERGENCY"
        assert FLEET_PRECEDENCE_ORDER[-1] == "NORMAL"

    def test_fleet_halt_new_overrides_bot_halted(self) -> None:
        """Fleet HALT_NEW blocks even if bot is somehow NORMAL."""
        assert resolve_bot_entry_from_states(
            fleet_mode="HALT_NEW",
            bot_state=BotSafetyState(bot_id="x", mode=HALT_BOT_NORMAL),
        ) == ScopedEntryDecision.BLOCKED


# ---------------------------------------------------------------------------
# Cross-bot isolation
# ---------------------------------------------------------------------------


class TestCrossBotIsolation:
    def test_one_bot_frozen_other_not(
        self, fleet_normal, reg_path: Path
    ) -> None:
        freeze_bot("freqtrade-freqforge", reason="r", actor="a",
                   registry_path=reg_path)
        reg = HaltBotRegistry(state_path=reg_path)
        assert resolve_bot_entry("freqtrade-freqforge", fleet_mode="NORMAL",
                                 registry=reg) == ScopedEntryDecision.BLOCKED
        reg.halt("freqtrade-freqforge-canary", reason="init", actor="test")
        reg.clear("freqtrade-freqforge-canary", actor="test", evidence="init")
        assert resolve_bot_entry("freqtrade-freqforge-canary", fleet_mode="NORMAL",
                                 registry=reg) == ScopedEntryDecision.ALLOWED
