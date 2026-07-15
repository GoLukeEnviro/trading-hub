"""Bot-scoped freeze architecture (R5B Path 2, Issue #580 follow-up).

Resolves the fleet-wide-only limitation of kill_switch.json by layering
a per-bot HaltBotRegistry underneath the authoritative fleet kill-switch.

Precedence:
    Fleet kill-switch (NORMAL|REDUCE_ONLY|HALT_NEW|EMERGENCY)
      │  HIGHEST — overrides all bot-level states
      ▼
    HaltBotRegistry per-bot state (NORMAL|HALTED|REDUCING|UNKNOWN)
      │  Bot-scoped — only affects specific bot when fleet is NORMAL
      ▼
    Decision: ALLOWED | BLOCKED (fail-closed for UNKNOWN)

This module is A1 repository code and has NO import dependency on
freqtrade.shared.kill_switch. Fleet state is always passed explicitly
by the caller (strategy gate or test). Runtime wiring is a separate
A1 follow-up PR.
"""
from __future__ import annotations

from enum import Enum

from si_v2.safety.halt_bot_circuit_breaker import (
    HALT_BOT_HALTED,
    HALT_BOT_UNKNOWN,
    BotSafetyState,
    HaltBotRegistry,
)

# ---------------------------------------------------------------------------
# Constants — stable across versions, no freqtrade import needed
# ---------------------------------------------------------------------------

MODE_NORMAL = "NORMAL"
SAFETY_NORMAL = "NORMAL"
SAFETY_HALT_NEW = "HALT_NEW"
SAFETY_REDUCE_ONLY = "REDUCE_ONLY"
SAFETY_EMERGENCY = "EMERGENCY"

FLEET_PRECEDENCE_ORDER = (
    SAFETY_EMERGENCY,
    SAFETY_HALT_NEW,
    SAFETY_REDUCE_ONLY,
    SAFETY_NORMAL,
)

# ---------------------------------------------------------------------------
# Decision enum
# ---------------------------------------------------------------------------


class ScopedEntryDecision(Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# Precedence resolution (pure functions, no disk I/O)
# ---------------------------------------------------------------------------


def resolve_bot_entry_from_states(
    *,
    fleet_mode: str,
    bot_state: BotSafetyState,
) -> ScopedEntryDecision:
    """Pure-function variant: decide without disk I/O.

    Useful in strategy loops that already hold loaded state.
    Fleet state must be passed explicitly — this module has no
    dependency on freqtrade.shared.kill_switch.
    """
    if fleet_mode != MODE_NORMAL:
        return ScopedEntryDecision.BLOCKED

    if bot_state.mode in (HALT_BOT_HALTED, HALT_BOT_UNKNOWN):
        return ScopedEntryDecision.BLOCKED

    return ScopedEntryDecision.ALLOWED


def resolve_bot_entry(
    bot_id: str,
    *,
    fleet_mode: str,
    registry: HaltBotRegistry,
) -> ScopedEntryDecision:
    """Decide whether *bot_id* may enter a new position.

    Precedence:
    1. Fleet kill-switch > all
    2. Bot halt state (if fleet is NORMAL)
    3. Unknown state → fail-closed (BLOCKED)

    Parameters
    ----------
    bot_id:
        Canonical bot identity (e.g. ``freqtrade-freqforge``).
    fleet_mode:
        Current fleet kill-switch mode. Must be passed explicitly.
    registry:
        Pre-loaded ``HaltBotRegistry``.
    """
    if fleet_mode != MODE_NORMAL:
        return ScopedEntryDecision.BLOCKED

    if registry.is_halted(bot_id):
        return ScopedEntryDecision.BLOCKED

    return ScopedEntryDecision.ALLOWED


# ---------------------------------------------------------------------------
# Freeze operations
# ---------------------------------------------------------------------------


def freeze_bot(
    bot_id: str,
    *,
    reason: str,
    actor: str,
    registry: HaltBotRegistry,
) -> BotSafetyState:
    """Halt a single bot without affecting the fleet.

    The caller is responsible for verifying the fleet kill-switch is
    NORMAL before calling this function.
    """
    return registry.halt(bot_id, reason=reason, actor=actor)


def unfreeze_bot(
    bot_id: str,
    *,
    actor: str,
    evidence: str,
    registry: HaltBotRegistry,
) -> BotSafetyState:
    """Clear a bot-specific halt."""
    return registry.clear(bot_id, actor=actor, evidence=evidence)


def list_frozen_bots(registry: HaltBotRegistry) -> list[str]:
    """Return bot IDs currently halted at the bot level."""
    return registry.list_halted()


# ---------------------------------------------------------------------------
# Fleet-aware bulk freeze (for Gate-style operations)
# ---------------------------------------------------------------------------


def freeze_all_canonical_bots(
    *,
    reason: str,
    actor: str,
    registry: HaltBotRegistry,
    bot_ids: list[str] | None = None,
) -> dict[str, BotSafetyState]:
    """Halt a set of bots in one batch.

    If *bot_ids* is ``None``, halts the canonical four-bot fleet.
    """
    if bot_ids is None:
        bot_ids = [
            "freqtrade-freqforge",
            "freqtrade-freqforge-canary",
            "freqtrade-regime-hybrid",
            "freqai-rebel",
        ]
    results: dict[str, BotSafetyState] = {}
    for bid in bot_ids:
        results[bid] = registry.halt(bid, reason=reason, actor=actor)
    return results
