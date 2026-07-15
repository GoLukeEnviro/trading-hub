"""Bot-scoped HALT_BOT circuit breaker (Phase 1B, Issue #596).

Tests are written first (TDD RED). Implementation follows in
:mod:`si_v2.safety.halt_bot_circuit_breaker`.

These tests are A1 repository code; they do not activate the capability
on any running fleet.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from si_v2.safety.halt_bot_circuit_breaker import (
    HALT_BOT_HALTED,
    HALT_BOT_NORMAL,
    HALT_BOT_REDUCING,
    HALT_BOT_UNKNOWN,
    BotIdValidationError,
    BotSafetyState,
    HaltBotRegistry,
    can_bot_open_new_position,
    combine_with_fleet_kill_switch,
    is_bot_halted,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_state_file(tmp_path: Path) -> Path:
    p = tmp_path / "bot_halt_state.json"
    return p


@pytest.fixture
def registry(tmp_state_file: Path) -> HaltBotRegistry:
    return HaltBotRegistry(state_path=tmp_state_file)


# ---------------------------------------------------------------------------
# Bot-id validation
# ---------------------------------------------------------------------------


class TestBotIdValidation:
    def test_valid_bot_id_accepted(self) -> None:
        reg = HaltBotRegistry(state_path=Path("/tmp/_unused_v.json"))
        reg.halt("freqtrade-freqforge", reason="unit-test", actor="tester")
        assert reg.is_halted("freqtrade-freqforge")

    @pytest.mark.parametrize("bad_id", [
        "",
        "   ",
        "FreqTrade-FreqForge",  # case-sensitive
        "freqtrade freqforge",  # whitespace
        "freqtrade_freqforge",  # underscore not allowed
        "../freqforge",         # path traversal
        "freqforge/canary",     # slash
        "x" * 65,               # too long
    ])
    def test_invalid_bot_id_rejected(self, registry: HaltBotRegistry, bad_id: str) -> None:
        with pytest.raises(BotIdValidationError):
            registry.halt(bad_id, reason="t", actor="t")

    def test_max_length_64(self, registry: HaltBotRegistry) -> None:
        ok = "a" * 64
        registry.halt(ok, reason="t", actor="t")
        assert registry.is_halted(ok)

    def test_min_length_3(self, registry: HaltBotRegistry) -> None:
        with pytest.raises(BotIdValidationError):
            registry.halt("ab", reason="t", actor="t")


# ---------------------------------------------------------------------------
# Halt / clear / persistence
# ---------------------------------------------------------------------------


class TestHaltAndClear:
    def test_halt_marks_state(self, registry: HaltBotRegistry) -> None:
        registry.halt("freqtrade-freqforge", reason="drawdown-breach",
                      actor="drawdown_guard")
        st = registry.get_state("freqtrade-freqforge")
        assert st.mode == HALT_BOT_HALTED
        assert st.reason == "drawdown-breach"
        assert st.triggered_by == "drawdown_guard"
        assert st.triggered_at != ""

    def test_clear_returns_to_normal(self, registry: HaltBotRegistry) -> None:
        registry.halt("freqtrade-freqforge", reason="t", actor="t")
        registry.clear("freqtrade-freqforge", actor="operator",
                       evidence="incident-report-2026-07-15")
        st = registry.get_state("freqtrade-freqforge")
        assert st.mode == HALT_BOT_NORMAL

    def test_clear_without_evidence_raises(self, registry: HaltBotRegistry) -> None:
        registry.halt("freqtrade-freqforge", reason="t", actor="t")
        with pytest.raises(ValueError):
            registry.clear("freqtrade-freqforge", actor="operator", evidence="")

    def test_clear_unknown_bot_raises(self, registry: HaltBotRegistry) -> None:
        with pytest.raises(KeyError):
            registry.clear("freqtrade-freqforge", actor="operator",
                           evidence="e")

    def test_halt_idempotent(self, registry: HaltBotRegistry) -> None:
        registry.halt("freqtrade-freqforge", reason="r1", actor="a1")
        registry.halt("freqtrade-freqforge", reason="r2", actor="a2")
        st = registry.get_state("freqtrade-freqforge")
        assert st.reason == "r2"
        assert st.triggered_by == "a2"


# ---------------------------------------------------------------------------
# Cross-bot isolation
# ---------------------------------------------------------------------------


class TestCrossBotIsolation:
    def test_one_bot_halted_other_untouched(self, registry: HaltBotRegistry) -> None:
        registry.halt("freqtrade-freqforge", reason="r", actor="a")
        # Halted target is halted
        assert registry.is_halted("freqtrade-freqforge")
        # Sibling bots are NOT explicitly halted in the registry, but
        # is_halted() is fail-closed and returns True for unknown bots.
        # We therefore verify they have NORMAL mode (not HALTED) directly.
        assert (
            registry.get_state("freqtrade-freqforge-canary").mode
            == HALT_BOT_UNKNOWN
        )
        assert (
            registry.get_state("freqtrade-regime-hybrid").mode
            == HALT_BOT_UNKNOWN
        )
        # list_halted only returns the explicitly halted bot
        assert registry.list_halted() == ["freqtrade-freqforge"]

    def test_list_halted_returns_only_halted(self, registry: HaltBotRegistry) -> None:
        registry.halt("freqtrade-freqforge", reason="r", actor="a")
        registry.halt("freqtrade-regime-hybrid", reason="r", actor="a")
        halted = registry.list_halted()
        assert set(halted) == {"freqtrade-freqforge", "freqtrade-regime-hybrid"}


# ---------------------------------------------------------------------------
# Authority precedence: fleet kill switch overrides bot state
# ---------------------------------------------------------------------------


class TestFleetKillSwitchPrecedence:
    def test_halt_new_blocks_all_bots(self, registry: HaltBotRegistry) -> None:
        # Bot is NORMAL but fleet kill is HALT_NEW -> bot must be blocked
        fleet = "HALT_NEW"
        assert combine_with_fleet_kill_switch(
            bot_state=registry.get_state("freqtrade-freqforge"),
            fleet_mode=fleet,
        ) == "BLOCKED"

    def test_emergency_blocks_all_bots(self, registry: HaltBotRegistry) -> None:
        assert combine_with_fleet_kill_switch(
            bot_state=registry.get_state("freqtrade-freqforge"),
            fleet_mode="EMERGENCY",
        ) == "BLOCKED"

    def test_normal_fleet_and_normal_bot_allows(self, registry: HaltBotRegistry) -> None:
        # Construct a bot in NORMAL state explicitly (not via get_state, which
        # returns UNKNOWN for never-halted bots and is fail-closed).
        bot = BotSafetyState(
            bot_id="freqtrade-freqforge",
            mode=HALT_BOT_NORMAL,
            reason="",
            triggered_at="",
            triggered_by="",
        )
        assert combine_with_fleet_kill_switch(
            bot_state=bot,
            fleet_mode="NORMAL",
        ) == "ALLOWED"

    def test_normal_fleet_but_halted_bot_blocks(self, registry: HaltBotRegistry) -> None:
        registry.halt("freqtrade-freqforge", reason="r", actor="a")
        assert combine_with_fleet_kill_switch(
            bot_state=registry.get_state("freqtrade-freqforge"),
            fleet_mode="NORMAL",
        ) == "BLOCKED"

    def test_reducing_state_with_halt_new_blocks(self, registry: HaltBotRegistry) -> None:
        # REDUCING is a future managed-exit mode; if fleet is HALT_NEW, the
        # more severe signal wins.
        bot = BotSafetyState(
            bot_id="freqtrade-freqforge",
            mode=HALT_BOT_REDUCING,
            reason="r",
            triggered_at="2026-07-15T00:00:00+00:00",
            triggered_by="t",
        )
        assert (
            combine_with_fleet_kill_switch(bot_state=bot, fleet_mode="HALT_NEW")
            == "BLOCKED"
        )


# ---------------------------------------------------------------------------
# Atomic write & corruption handling
# ---------------------------------------------------------------------------


class TestAtomicWriteAndCorruption:
    def test_persistence_round_trip(self, tmp_state_file: Path) -> None:
        reg1 = HaltBotRegistry(state_path=tmp_state_file)
        reg1.halt("freqtrade-freqforge", reason="r", actor="a")
        reg2 = HaltBotRegistry(state_path=tmp_state_file)
        assert reg2.is_halted("freqtrade-freqforge")

    def test_corrupt_state_fails_closed(
        self, tmp_state_file: Path, registry: HaltBotRegistry
    ) -> None:
        # Create a halt, then corrupt the on-disk file
        registry.halt("freqtrade-freqforge", reason="r", actor="a")
        tmp_state_file.write_text("not-json")
        reg2 = HaltBotRegistry(state_path=tmp_state_file)
        # Fail-closed: bot is treated as HALTED when state cannot be read
        assert reg2.is_halted("freqtrade-freqforge")

    def test_missing_state_file_fails_closed(self, tmp_path: Path) -> None:
        # No file written yet
        reg = HaltBotRegistry(state_path=tmp_path / "nope.json")
        # No halt recorded, but unknown state -> HALTED (fail-closed)
        assert reg.is_halted("freqtrade-freqforge")

    def test_atomic_write_uses_tmp_replace(
        self, tmp_state_file: Path, registry: HaltBotRegistry
    ) -> None:
        registry.halt("freqtrade-freqforge", reason="r", actor="a")
        # .tmp should not remain after write
        assert not (tmp_state_file.with_suffix(".tmp")).exists()


# ---------------------------------------------------------------------------
# Evidence — actor, reason, bot id, timestamps, prev/new state
# ---------------------------------------------------------------------------


class TestEvidence:
    def test_state_records_full_evidence(self, registry: HaltBotRegistry) -> None:
        registry.halt("freqtrade-freqforge", reason="breach",
                      actor="drawdown_guard")
        st = registry.get_state("freqtrade-freqforge")
        d = st.to_dict()
        assert d["bot_id"] == "freqtrade-freqforge"
        assert d["mode"] == HALT_BOT_HALTED
        assert d["reason"] == "breach"
        assert d["triggered_by"] == "drawdown_guard"
        assert d["triggered_at"] != ""
        assert d["previous_mode"] in (HALT_BOT_NORMAL, HALT_BOT_UNKNOWN)

    def test_transition_preserves_previous_mode(
        self, registry: HaltBotRegistry
    ) -> None:
        registry.halt("freqtrade-freqforge", reason="r1", actor="a1")
        st = registry.get_state("freqtrade-freqforge")
        assert st.previous_mode in (HALT_BOT_NORMAL, HALT_BOT_UNKNOWN)


# ---------------------------------------------------------------------------
# Module-level convenience helpers
# ---------------------------------------------------------------------------


class TestModuleLevelHelpers:
    def test_module_helpers_consistent_with_registry(
        self, registry: HaltBotRegistry
    ) -> None:
        state = registry.halt(
            "freqtrade-freqforge", reason="r", actor="a"
        )
        assert is_bot_halted(state) is True
        assert can_bot_open_new_position(
            state, fleet_kill_mode="NORMAL"
        ) is False
        assert can_bot_open_new_position(
            state, fleet_kill_mode="HALT_NEW"
        ) is False
