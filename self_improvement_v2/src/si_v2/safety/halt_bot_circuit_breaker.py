"""Bot-scoped HALT_BOT circuit breaker (Phase 1B, Issue #596).

This module provides a per-bot safety registry that lets a single failing bot
be halted without forcing a fleet-wide stop. The fleet kill switch
(:mod:`freqtrade.shared.kill_switch`) remains the highest authority and always
overrides per-bot state.

Design contract
---------------

- Bot identity is explicit and validated.
- A halted bot cannot create new entries or increase risk.
- Other healthy bots continue unless a fleet-level guard also fires.
- State changes are atomic, idempotent and auditable.
- Unknown / corrupt bot-safety state fails closed for the affected bot.
- Recovery requires an explicit, evidence-backed transition; no automatic
  restart merely because a timer or daily window reset occurs.
- Fleet kill switch remains authoritative over all bot-level states.

This module is A1 repository code; it does NOT activate the capability on any
running fleet. Runtime activation requires a separate A2 approval and explicit
wiring in the strategy/adapter layer.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HALT_BOT_NORMAL = "NORMAL"
HALT_BOT_HALTED = "HALTED"
HALT_BOT_REDUCING = "REDUCING"  # future: managed-exit / reduce-only
HALT_BOT_UNKNOWN = "UNKNOWN"

VALID_HALT_BOT_STATES = frozenset(
    {HALT_BOT_NORMAL, HALT_BOT_HALTED, HALT_BOT_REDUCING, HALT_BOT_UNKNOWN}
)

# Bot-id rules: lowercase alnum + hyphen, length 3..64, must start with letter
_BOT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BotIdValidationError(ValueError):
    """Raised when a bot id fails validation."""


# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------


@dataclass
class BotSafetyState:
    bot_id: str
    mode: str = HALT_BOT_UNKNOWN
    reason: str = ""
    triggered_at: str = ""
    triggered_by: str = ""
    previous_mode: str = HALT_BOT_UNKNOWN
    cleared_at: str = ""
    cleared_by: str = ""
    cleared_evidence: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> BotSafetyState:
        return cls(
            bot_id=d.get("bot_id", ""),
            mode=d.get("mode", HALT_BOT_UNKNOWN),
            reason=d.get("reason", ""),
            triggered_at=d.get("triggered_at", ""),
            triggered_by=d.get("triggered_by", ""),
            previous_mode=d.get("previous_mode", HALT_BOT_UNKNOWN),
            cleared_at=d.get("cleared_at", ""),
            cleared_by=d.get("cleared_by", ""),
            cleared_evidence=d.get("cleared_evidence", ""),
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class HaltBotRegistry:
    """Per-bot safety registry with atomic disk persistence."""

    def __init__(self, state_path: Path) -> None:
        self.state_path = Path(state_path)
        self._cache: dict[str, BotSafetyState] = {}
        self._loaded = False

    # -- validation --------------------------------------------------------

    @staticmethod
    def _validate_bot_id(bot_id: str) -> None:
        if not isinstance(bot_id, str):
            raise BotIdValidationError(
                f"bot_id must be str, got {type(bot_id).__name__}"
            )
        if not _BOT_ID_RE.match(bot_id):
            raise BotIdValidationError(
                f"invalid bot_id {bot_id!r}: must match {_BOT_ID_RE.pattern}"
            )

    # -- IO ----------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.state_path.exists():
            return
        try:
            raw = json.loads(self.state_path.read_text())
        except Exception:
            # FAIL-CLOSED: corrupt state => treat as empty, force unknown-state
            # for all bots queried. Individual is_halted() returns True.
            return
        if not isinstance(raw, dict):
            return
        bots = raw.get("bots", {})
        if not isinstance(bots, dict):
            return
        for bot_id, payload in bots.items():
            if not isinstance(payload, dict):
                continue
            try:
                self._cache[bot_id] = BotSafetyState.from_dict(payload)
            except Exception:
                # skip malformed entry
                continue

    def _persist(self) -> None:
        payload = {
            "version": 1,
            "updated_at": datetime.now(tz=UTC).isoformat(),
            "bots": {
                bot_id: st.to_dict() for bot_id, st in self._cache.items()
            },
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        # atomic write: .tmp + os.replace
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
        os.replace(tmp, self.state_path)

    # -- public API --------------------------------------------------------

    def halt(
        self,
        bot_id: str,
        *,
        reason: str,
        actor: str,
    ) -> BotSafetyState:
        self._validate_bot_id(bot_id)
        if not reason:
            raise ValueError("reason is required to halt a bot")
        if not actor:
            raise ValueError("actor is required to halt a bot")
        self._ensure_loaded()
        prev = self._cache.get(bot_id)
        prev_mode = prev.mode if prev else HALT_BOT_UNKNOWN
        now = datetime.now(tz=UTC).isoformat()
        st = BotSafetyState(
            bot_id=bot_id,
            mode=HALT_BOT_HALTED,
            reason=reason,
            triggered_at=now,
            triggered_by=actor,
            previous_mode=prev_mode,
        )
        self._cache[bot_id] = st
        self._persist()
        return st

    def clear(
        self,
        bot_id: str,
        *,
        actor: str,
        evidence: str,
    ) -> BotSafetyState:
        self._validate_bot_id(bot_id)
        if not actor:
            raise ValueError("actor is required to clear a bot halt")
        if not evidence:
            raise ValueError("evidence is required to clear a bot halt")
        self._ensure_loaded()
        prev = self._cache.get(bot_id)
        if prev is None or prev.mode != HALT_BOT_HALTED:
            raise KeyError(
                f"bot {bot_id!r} is not currently halted; refuse to clear"
            )
        now = datetime.now(tz=UTC).isoformat()
        st = BotSafetyState(
            bot_id=bot_id,
            mode=HALT_BOT_NORMAL,
            reason="",
            triggered_at="",
            triggered_by="",
            previous_mode=HALT_BOT_HALTED,
            cleared_at=now,
            cleared_by=actor,
            cleared_evidence=evidence,
        )
        self._cache[bot_id] = st
        self._persist()
        return st

    def get_state(self, bot_id: str) -> BotSafetyState:
        self._validate_bot_id(bot_id)
        self._ensure_loaded()
        return self._cache.get(
            bot_id,
            BotSafetyState(bot_id=bot_id, mode=HALT_BOT_UNKNOWN),
        )

    def is_halted(self, bot_id: str) -> bool:
        """Fail-closed: UNKNOWN state is treated as HALTED."""
        try:
            self._validate_bot_id(bot_id)
        except BotIdValidationError:
            # invalid id => cannot be safely traded
            return True
        self._ensure_loaded()
        st = self._cache.get(bot_id)
        if st is None:
            return True  # fail-closed for unknown bots
        return st.mode in (HALT_BOT_HALTED, HALT_BOT_UNKNOWN)

    def list_halted(self) -> list[str]:
        self._ensure_loaded()
        return [
            bot_id
            for bot_id, st in self._cache.items()
            if st.mode == HALT_BOT_HALTED
        ]


# ---------------------------------------------------------------------------
# Module-level helpers (single-shot)
# ---------------------------------------------------------------------------


def is_bot_halted(state: BotSafetyState) -> bool:
    return state.mode in (HALT_BOT_HALTED, HALT_BOT_UNKNOWN)


def can_bot_open_new_position(
    state: BotSafetyState, *, fleet_kill_mode: str
) -> bool:
    """Decide whether ``state.bot_id`` may open a new position.

    Fleet kill switch is the highest authority: a non-NORMAL fleet mode
    blocks all bots, regardless of per-bot state.
    """
    if fleet_kill_mode not in ("NORMAL", "HALT_NEW", "EMERGENCY"):
        # unknown fleet state => fail-closed
        return False
    if fleet_kill_mode != "NORMAL":
        return False
    return state.mode == HALT_BOT_NORMAL


def halt_bot(bot_id: str, *, reason: str, actor: str, state_path: Path) -> BotSafetyState:
    reg = HaltBotRegistry(state_path=state_path)
    return reg.halt(bot_id, reason=reason, actor=actor)


def clear_bot_halt(
    bot_id: str, *, actor: str, evidence: str, state_path: Path
) -> BotSafetyState:
    reg = HaltBotRegistry(state_path=state_path)
    return reg.clear(bot_id, actor=actor, evidence=evidence)


def list_halted_bots(state_path: Path) -> list[str]:
    reg = HaltBotRegistry(state_path=state_path)
    return reg.list_halted()


def load_registry_from(state_path: Path) -> HaltBotRegistry:
    reg = HaltBotRegistry(state_path=state_path)
    reg._ensure_loaded()
    return reg


def save_registry_to(reg: HaltBotRegistry, state_path: Path) -> None:
    reg.state_path = Path(state_path)
    reg._persist()


def combine_with_fleet_kill_switch(
    *, bot_state: BotSafetyState, fleet_mode: str
) -> str:
    """Return 'ALLOWED' or 'BLOCKED' combining bot + fleet state.

    Fleet kill switch is authoritative. Bot halt blocks that bot.
    """
    if fleet_mode in ("HALT_NEW", "EMERGENCY"):
        return "BLOCKED"
    if fleet_mode != "NORMAL":
        return "BLOCKED"
    if bot_state.mode in (HALT_BOT_HALTED, HALT_BOT_UNKNOWN):
        return "BLOCKED"
    return "ALLOWED"
