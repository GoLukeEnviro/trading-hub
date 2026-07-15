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

This module is A1 repository code. Runtime wiring into the strategy gate
is a separate A1 follow-up PR. Runtime activation on a live fleet requires
A2 approval.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from si_v2.safety.halt_bot_circuit_breaker import (
    HALT_BOT_HALTED,
    HALT_BOT_NORMAL,
    HALT_BOT_REDUCING,
    HALT_BOT_UNKNOWN,
    BotSafetyState,
    HaltBotRegistry,
)

# Lazy import: freqtrade.shared is only on sys.path inside Freqtrade containers
# and during test runs with explicit sys.path setup. Top-level import would
# break pure unit tests that don't need the fleet kill-switch layer.


def _get_fleet_mode() -> str:
    from freqtrade.shared.kill_switch import get_kill_mode
    return get_kill_mode()


def _is_fleet_active() -> bool:
    from freqtrade.shared.kill_switch import is_kill_active
    return is_kill_active()


# Constants — stable across versions
MODE_NORMAL = "NORMAL"
SAFETY_NORMAL = "NORMAL"
SAFETY_HALT_NEW = "HALT_NEW"
SAFETY_REDUCE_ONLY = "REDUCE_ONLY"
SAFETY_EMERGENCY = "EMERGENCY"

# ---------------------------------------------------------------------------
# Decision enum
# ---------------------------------------------------------------------------


class ScopedEntryDecision(Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# Precedence resolution
# ---------------------------------------------------------------------------


def resolve_bot_entry(
    bot_id: str,
    *,
    fleet_mode: str | None = None,
    registry: HaltBotRegistry | None = None,
    registry_path: Path | None = None,
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
        Override fleet mode. If ``None``, reads from disk.
    registry:
        Pre-loaded ``HaltBotRegistry``. If ``None``, loads from *registry_path*.
    registry_path:
        Path to the bot-halt state file. Required if *registry* is ``None``.
    """
    # 1) Fleet override — authoritative
    mode = fleet_mode if fleet_mode is not None else _get_fleet_mode()
    if mode != MODE_NORMAL:
        return ScopedEntryDecision.BLOCKED

    # 2) Bot-level check
    if registry is None:
        if registry_path is None:
            raise ValueError("registry_path is required when registry is None")
        registry = HaltBotRegistry(state_path=registry_path)

    if registry.is_halted(bot_id):
        return ScopedEntryDecision.BLOCKED

    return ScopedEntryDecision.ALLOWED


def resolve_bot_entry_from_states(
    *,
    fleet_mode: str,
    bot_state: BotSafetyState,
) -> ScopedEntryDecision:
    """Pure-function variant: decide without disk I/O.

    Useful in strategy loops that already hold loaded state.
    """
    if fleet_mode != MODE_NORMAL:
        return ScopedEntryDecision.BLOCKED

    if bot_state.mode in (HALT_BOT_HALTED, HALT_BOT_UNKNOWN):
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
    registry_path: Path,
) -> BotSafetyState:
    """Halt a single bot without affecting the fleet.

    Requires the fleet kill-switch to be NORMAL; raises if fleet is
    already in a non-NORMAL state, since a bot-scoped freeze would be
    meaningless.
    """
    if _is_fleet_active():
        raise RuntimeError(
            "Fleet kill-switch is active. Bot-scoped freeze is not meaningful "
            "while the entire fleet is blocked."
        )
    reg = HaltBotRegistry(state_path=registry_path)
    return reg.halt(bot_id, reason=reason, actor=actor)


def unfreeze_bot(
    bot_id: str,
    *,
    actor: str,
    evidence: str,
    registry_path: Path,
) -> BotSafetyState:
    """Clear a bot-specific halt."""
    reg = HaltBotRegistry(state_path=registry_path)
    return reg.clear(bot_id, actor=actor, evidence=evidence)


def list_frozen_bots(registry_path: Path) -> list[str]:
    """Return bot IDs currently halted at the bot level."""
    reg = HaltBotRegistry(state_path=registry_path)
    return reg.list_halted()


# ---------------------------------------------------------------------------
# Fleet-aware bulk freeze (for Gate-style operations)
# ---------------------------------------------------------------------------


def freeze_all_canonical_bots(
    *,
    reason: str,
    actor: str,
    registry_path: Path,
    bot_ids: list[str] | None = None,
) -> dict[str, BotSafetyState]:
    """Halt a set of bots in one atomic batch.

    If *bot_ids* is ``None``, halts the canonical four-bot fleet:
    ``freqtrade-freqforge``, ``freqtrade-freqforge-canary``,
    ``freqtrade-regime-hybrid``, ``freqai-rebel``.

    Returns a dict of ``{bot_id: BotSafetyState}``.
    """
    if bot_ids is None:
        bot_ids = [
            "freqtrade-freqforge",
            "freqtrade-freqforge-canary",
            "freqtrade-regime-hybrid",
            "freqai-rebel",
        ]
    reg = HaltBotRegistry(state_path=registry_path)
    results: dict[str, BotSafetyState] = {}
    for bid in bot_ids:
        results[bid] = reg.halt(bid, reason=reason, actor=actor)
    return results


# ---------------------------------------------------------------------------
# Contract: precedence never inverted
# ---------------------------------------------------------------------------


FLEET_PRECEDENCE_ORDER = (
    SAFETY_EMERGENCY,   # highest
    SAFETY_HALT_NEW,
    SAFETY_REDUCE_ONLY,
    SAFETY_NORMAL,       # lowest
)

BOT_PRECEDENCE_ORDER = (
    HALT_BOT_HALTED,     # highest bot restriction
    HALT_BOT_REDUCING,
    HALT_BOT_NORMAL,
    HALT_BOT_UNKNOWN,    # treated as HALTED for decision purposes
)
