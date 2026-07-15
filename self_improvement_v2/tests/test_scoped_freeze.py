"""R5B Path 2 — Bot-scoped freeze architecture tests (A1, no runtime)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC = _REPO_ROOT / "self_improvement_v2" / "src"
sys.path.insert(0, str(SRC))

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
def registry(tmp_path: Path) -> HaltBotRegistry:
    return HaltBotRegistry(state_path=tmp_path / "halt_state.json")


# ---------------------------------------------------------------------------
# resolve_bot_entry
# ---------------------------------------------------------------------------


class TestResolveBotEntry:
    def test_fleet_halt_new_blocks_all(self, registry: HaltBotRegistry) -> None:
        assert resolve_bot_entry("freqtrade-freqforge", fleet_mode="HALT_NEW",
                                 registry=registry) == ScopedEntryDecision.BLOCKED

    def test_fleet_normal_bot_explicitly_normal_allows(
        self, registry: HaltBotRegistry
    ) -> None:
        registry.halt("freqtrade-freqforge", reason="init", actor="test")
        registry.clear("freqtrade-freqforge", actor="test", evidence="init")
        assert resolve_bot_entry("freqtrade-freqforge", fleet_mode="NORMAL",
                                 registry=registry) == ScopedEntryDecision.ALLOWED

    def test_fleet_normal_bot_halted_blocks(
        self, registry: HaltBotRegistry
    ) -> None:
        registry.halt("freqtrade-freqforge", reason="r", actor="a")
        assert resolve_bot_entry("freqtrade-freqforge", fleet_mode="NORMAL",
                                 registry=registry) == ScopedEntryDecision.BLOCKED

    def test_fleet_normal_unknown_bot_fail_closed(
        self, registry: HaltBotRegistry
    ) -> None:
        assert resolve_bot_entry("unknown-bot-123", fleet_mode="NORMAL",
                                 registry=registry) == ScopedEntryDecision.BLOCKED

    def test_fleet_reduce_only_blocks(self, registry: HaltBotRegistry) -> None:
        assert resolve_bot_entry("freqtrade-freqforge", fleet_mode="REDUCE_ONLY",
                                 registry=registry) == ScopedEntryDecision.BLOCKED

    def test_fleet_emergency_blocks(self, registry: HaltBotRegistry) -> None:
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
    def test_freeze(self, registry: HaltBotRegistry) -> None:
        st = freeze_bot("freqtrade-freqforge", reason="t", actor="t",
                        registry=registry)
        assert st.mode == HALT_BOT_HALTED

    def test_unfreeze_requires_evidence(self, registry: HaltBotRegistry) -> None:
        freeze_bot("freqtrade-freqforge", reason="t", actor="t",
                   registry=registry)
        st = unfreeze_bot("freqtrade-freqforge", actor="op",
                          evidence="incident-123", registry=registry)
        assert st.mode == HALT_BOT_NORMAL


# ---------------------------------------------------------------------------
# list_frozen_bots
# ---------------------------------------------------------------------------


class TestListFrozenBots:
    def test_returns_only_halted(self, registry: HaltBotRegistry) -> None:
        freeze_bot("freqtrade-freqforge", reason="r", actor="a",
                   registry=registry)
        freeze_bot("freqtrade-regime-hybrid", reason="r", actor="a",
                   registry=registry)
        assert set(list_frozen_bots(registry)) == {
            "freqtrade-freqforge", "freqtrade-regime-hybrid"
        }


# ---------------------------------------------------------------------------
# freeze_all_canonical_bots
# ---------------------------------------------------------------------------


class TestFreezeAllCanonicalBots:
    def test_freezes_all_four(self, registry: HaltBotRegistry) -> None:
        results = freeze_all_canonical_bots(reason="Gate test", actor="test",
                                            registry=registry)
        assert len(results) == 4
        for st in results.values():
            assert st.mode == HALT_BOT_HALTED

    def test_custom_bot_list(self, registry: HaltBotRegistry) -> None:
        results = freeze_all_canonical_bots(
            reason="t", actor="t", registry=registry,
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
        assert resolve_bot_entry_from_states(
            fleet_mode="HALT_NEW",
            bot_state=BotSafetyState(bot_id="x", mode=HALT_BOT_NORMAL),
        ) == ScopedEntryDecision.BLOCKED


# ---------------------------------------------------------------------------
# Cross-bot isolation
# ---------------------------------------------------------------------------


class TestCrossBotIsolation:
    def test_one_bot_frozen_other_not(self, registry: HaltBotRegistry) -> None:
        freeze_bot("freqtrade-freqforge", reason="r", actor="a",
                   registry=registry)
        registry.halt("freqtrade-freqforge-canary", reason="init", actor="test")
        registry.clear("freqtrade-freqforge-canary", actor="test", evidence="init")
        assert resolve_bot_entry("freqtrade-freqforge", fleet_mode="NORMAL",
                                 registry=registry) == ScopedEntryDecision.BLOCKED
        assert resolve_bot_entry("freqtrade-freqforge-canary", fleet_mode="NORMAL",
                                 registry=registry) == ScopedEntryDecision.ALLOWED
