"""Verdict contracts — explicit entry, observation and fleet safety verdicts (Phase 1E, #599).

Reconciles the mixed BLOCK_ENTRY / WATCH_ONLY / ACCEPTED semantics into
versioned, testable contracts. Every path is classified as:
- Trading authority: entry-gate decisions with fail-closed semantics.
- Observation: measurement/reporting, never trading-authoritative.
- Fleet safety: kill-switch state with precedence rules.

Observation/reporting helpers must never authorize a trade.
A BLOCK_ENTRY in trading-authority cannot be neutralized by a helper.
Unknown verdicts fail closed in trading paths, remain visible in evidence.
"""
from __future__ import annotations

from enum import Enum

# ============================================================================
# Versioned enums — single source of truth
# ============================================================================


class EntryGateVerdict(Enum):
    """Trading authority: entry-gate decision.

    BLOCK_ENTRY is a hard safety stop. There is no path from BLOCK_ENTRY
    back to ACCEPTED without an explicit, evidence-backed state change.
    """
    BLOCK_ENTRY = "BLOCK_ENTRY"
    WATCH_ONLY = "WATCH_ONLY"
    ACCEPTED = "ACCEPTED"

    def is_blocked(self) -> bool:
        return self == EntryGateVerdict.BLOCK_ENTRY

    def is_tradeable(self) -> bool:
        return self == EntryGateVerdict.ACCEPTED


class ObservationClassification(Enum):
    """Measurement/reporting only. Never trading-authoritative.

    These are neutral classification labels used in dashboards, reports,
    and performance analysis. An observer that says 'NEUTRAL' cannot
    override a BLOCK_ENTRY from the trading authority.
    """
    NEUTRAL = "NEUTRAL"
    CAUTION = "CAUTION"
    ALERT = "ALERT"


class FleetSafetyState(Enum):
    """Fleet-level kill switch state. Highest trading authority.

    Precedence: EMERGENCY > HALT_NEW > REDUCE_ONLY > NORMAL
    """
    NORMAL = "NORMAL"
    REDUCE_ONLY = "REDUCE_ONLY"
    HALT_NEW = "HALT_NEW"
    EMERGENCY = "EMERGENCY"

    def precedence(self) -> int:
        return _FLEET_PRECEDENCE[self]

    @classmethod
    def most_restrictive(cls, *states: FleetSafetyState) -> FleetSafetyState:
        return max(states, key=lambda s: s.precedence())


_FLEET_PRECEDENCE = {
    FleetSafetyState.NORMAL: 0,
    FleetSafetyState.REDUCE_ONLY: 1,
    FleetSafetyState.HALT_NEW: 2,
    FleetSafetyState.EMERGENCY: 3,
}


# ============================================================================
# Conversion rules between layers
# ============================================================================


def entry_gate_to_str(verdict: EntryGateVerdict) -> str:
    return verdict.value


def str_to_entry_gate(raw: str) -> EntryGateVerdict:
    """Convert a raw string to an EntryGateVerdict. Unknown values fail closed."""
    try:
        return EntryGateVerdict(raw)
    except ValueError:
        return EntryGateVerdict.BLOCK_ENTRY  # fail-closed


def observation_to_str(classification: ObservationClassification) -> str:
    return classification.value


def str_to_observation(raw: str) -> ObservationClassification:
    """Convert a raw string to an ObservationClassification. Unknown → NEUTRAL."""
    try:
        return ObservationClassification(raw)
    except ValueError:
        return ObservationClassification.NEUTRAL


def fleet_safety_to_str(state: FleetSafetyState) -> str:
    return state.value


def str_to_fleet_safety(raw: str) -> FleetSafetyState:
    """Convert a raw string to a FleetSafetyState. Unknown → HALT_NEW (fail-closed)."""
    try:
        return FleetSafetyState(raw)
    except ValueError:
        return FleetSafetyState.HALT_NEW


# ============================================================================
# Contract: observation must never authorize a trade
# ============================================================================


def is_trading_authoritative(verdict: EntryGateVerdict) -> bool:
    """Only EntryGateVerdict carries trading authority."""
    return isinstance(verdict, EntryGateVerdict)


def is_observation_only(classification: ObservationClassification) -> bool:
    """ObservationClassification is explicitly non-authoritative."""
    return isinstance(classification, ObservationClassification)


def entry_verdict_from_observation(
    classification: ObservationClassification,
) -> EntryGateVerdict:
    """Convert observation to entry verdict — ALWAYS returns WATCH_ONLY.

    This is intentional: an observation must NEVER authorize (ACCEPTED) or
    block (BLOCK_ENTRY) a trade. It only elevates to WATCH_ONLY at most.
    """
    # Observation is never trading-authoritative
    return EntryGateVerdict.WATCH_ONLY


# ============================================================================
# Contract: combining verdicts
# ============================================================================


def combine_entry_and_fleet(
    entry: EntryGateVerdict,
    fleet: FleetSafetyState,
) -> EntryGateVerdict:
    """Combine entry-gate verdict with fleet safety state.

    Fleet safety is higher authority. Any non-NORMAL fleet state overrides
    the entry verdict and blocks.
    """
    if fleet != FleetSafetyState.NORMAL:
        return EntryGateVerdict.BLOCK_ENTRY
    return entry


def reduce_verdicts(verdicts: list[str]) -> str:
    """Reduce multiple verdict strings to a single output.

    Most restrictive wins. Used when merging pipeline stages.
    """
    # precedence: EMERGENCY > HALT_NEW > BLOCK_ENTRY > REDUCE_ONLY > WATCH_ONLY > ACCEPTED > NEUTRAL
    prec = {"EMERGENCY": 5, "HALT_NEW": 4, "BLOCK_ENTRY": 3, "REDUCE_ONLY": 2,
            "WATCH_ONLY": 1, "ACCEPTED": 0, "NEUTRAL": -1}
    best = "NEUTRAL"
    best_p = -1
    for v in verdicts:
        p = prec.get(v, 3)  # unknown → BLOCK_ENTRY level
        if p > best_p:
            best = v
            best_p = p
    return best


# ============================================================================
# Contract map (documented reference)
# ============================================================================

CONTRACT_MAP = {
    "layers": {
        "trading_authority": {
            "enum": "EntryGateVerdict",
            "values": ["BLOCK_ENTRY", "WATCH_ONLY", "ACCEPTED"],
            "fail_closed": True,
            "can_authorize_trade": True,
            "note": "Only source of trade authorization. BLOCK_ENTRY cannot be neutralized.",
        },
        "fleet_safety": {
            "enum": "FleetSafetyState",
            "values": ["NORMAL", "REDUCE_ONLY", "HALT_NEW", "EMERGENCY"],
            "fail_closed": True,
            "can_authorize_trade": True,
            "note": "Highest authority. Overrides entry verdict.",
        },
        "observation": {
            "enum": "ObservationClassification",
            "values": ["NEUTRAL", "CAUTION", "ALERT"],
            "fail_closed": False,
            "can_authorize_trade": False,
            "note": "Measurement/reporting only. Never trading-authoritative.",
        },
    },
    "conversion_rules": {
        "observation_to_entry": "always WATCH_ONLY — cannot ACCEPT or BLOCK",
        "str_to_entry_unknown": "fail-closed → BLOCK_ENTRY",
        "str_to_fleet_unknown": "fail-closed → HALT_NEW",
        "fleet_over_entry": "non-NORMAL fleet → BLOCK_ENTRY",
    },
    "version": 1,
}
