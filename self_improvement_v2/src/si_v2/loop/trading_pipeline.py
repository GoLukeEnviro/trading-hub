"""trading_pipeline.py — SI v2 Trading Pipeline with kill-switch integration.

This module provides the ``process_signals`` function that reads the kill-switch
state before processing trading signals.  It is the central choke point for
fleet-wide entry blocking and emergency exit behaviour.

Kill-switch modes (see ``freqtrade/shared/kill_switch.py``):

    * NORMAL      — Normal processing; no blocking.
    * HALT_NEW    — Forces WATCH_ONLY verdict on all signals; no new entries.
    * EMERGENCY   — Forces WATCH_ONLY verdict AND signals position close
                    (includes an ``exit_signal`` flag for the strategy layer).
"""

from __future__ import annotations

import copy
import logging
from typing import Any

_logger = logging.getLogger(__name__)

# ── Signal verdict constants ────────────────────────────────────────────

VERDICT_ACCEPTED: str = "ACCEPTED"
VERDICT_WATCH_ONLY: str = "WATCH_ONLY"

# ── Kill-switch wrapper (import with fallback) ──────────────────────────

try:
    from freqtrade.shared.kill_switch import (
        MODE_EMERGENCY,
        MODE_HALT_NEW,
        MODE_NORMAL,
        get_kill_mode,
        is_emergency,
        is_kill_active,
    )
except ImportError:
    _logger.warning(
        "kill_switch module not available — kill-switch checks disabled"
    )

    MODE_NORMAL = "NORMAL"
    MODE_HALT_NEW = "HALT_NEW"
    MODE_EMERGENCY = "EMERGENCY"

    def get_kill_mode() -> str:
        return MODE_NORMAL

    def is_kill_active() -> bool:
        return False

    def is_emergency() -> bool:
        return False

_KILL_ACTIVE: bool | None = None  # lazily populated


def _check_kill_switch() -> dict[str, Any]:
    """Read the kill-switch state and return a structured result.

    Returns a dict with:
        - ``kill_override`` (bool) — True when kill-switch is active
        - ``emergency`` (bool) — True when EMERGENCY mode
        - ``kill_mode`` (str) — raw mode name
        - ``forced_verdict`` (str | None) — the forced verdict if active
        - ``exit_signal`` (bool) — True when positions should be closed
    """
    mode = get_kill_mode()
    kill_active = mode != MODE_NORMAL
    emergency = mode == MODE_EMERGENCY

    return {
        "kill_override": kill_active,
        "emergency": emergency,
        "kill_mode": mode,
        "forced_verdict": VERDICT_WATCH_ONLY if kill_active else None,
        "exit_signal": emergency,
    }


# ── Public API ──────────────────────────────────────────────────────────


def process_signals(
    signals: list[dict[str, Any]] | dict[str, Any],
    kill_switch_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Process signals through the kill-switch gate.

    This is the top-level entry point for the trading pipeline.  It checks
    the kill-switch state and forces WATCH_ONLY with optional exit signals
    when HALT_NEW or EMERGENCY is active.

    Args:
        signals: A list of signal dicts (one per pair) or a dict with a
            ``pairs`` key containing the signal list.  Each signal should
            have at minimum a ``pair`` field.
        kill_switch_check: Optional pre-computed kill-switch result from
            ``_check_kill_switch()``.  When None, the kill-switch state is
            read on every call.

    Returns:
        A dict with:
            - ``pairs`` (list[dict[str, Any]]): processed signal decisions
            - ``override_active`` (bool): whether kill-switch forced changes
            - ``kill_mode`` (str): current kill-switch mode
            - ``exit_signal`` (bool): True when EMERGENCY exit signal is active
            - ``summary`` (str): human-readable summary
    """
    ks = _check_kill_switch() if kill_switch_check is None else kill_switch_check

    kill_override: bool = ks["kill_override"]
    emergency: bool = ks["emergency"]
    forced_verdict: str | None = ks["forced_verdict"]

    # Normalise input
    signal_list: list[dict[str, Any]]
    if isinstance(signals, list):
        signal_list = signals
    elif isinstance(signals, dict):
        raw = signals.get("pairs", signals.get("signals", []))
        signal_list = raw if isinstance(raw, list) else [signals]
    else:
        signal_list = []

    pairs: list[dict[str, Any]] = []

    for signal in signal_list:
        pair_key = str(signal.get("pair", signal.get("pair_key", "unknown")))

        if kill_override:
            # Force WATCH_ONLY on every signal
            entry: dict[str, Any] = {
                "pair": pair_key,
                "pair_key": pair_key,
                "verdict": forced_verdict,
                "action": "HOLD",
                "kill_switched": True,
                "kill_mode": ks["kill_mode"],
            }
            # Carry forward any existing confidence for traceability
            original_confidence = signal.get("confidence", 0.0)
            entry["original_confidence"] = original_confidence
            entry["confidence"] = 0.0
            entry["quantity"] = 0.0
            entry["allow_long_bias"] = False
            entry["allow_short_bias"] = False

            if emergency:
                entry["exit_signal"] = True
                entry["exit_reason"] = "kill_switch_emergency"

            pairs.append(entry)
        else:
            # NORMAL mode — pass through unchanged (deep copy to avoid
            # accidental mutation of caller's data)
            entry = copy.deepcopy(signal)
            entry.setdefault("pair_key", pair_key)
            entry.setdefault("kill_switched", False)
            entry["kill_mode"] = MODE_NORMAL
            pairs.append(entry)

    # Build summary
    total = len(pairs)
    if kill_override:
        if emergency:
            summary = (
                f"EMERGENCY: {total} signals forced to WATCH_ONLY "
                f"with exit signal (positions will close)"
            )
        else:
            summary = (
                f"HALT_NEW: {total} signals forced to WATCH_ONLY "
                f"(no new entries)"
            )
    else:
        summary = f"NORMAL: {total} signals processed without override"

    return {
        "pairs": pairs,
        "override_active": kill_override,
        "kill_mode": ks["kill_mode"],
        "exit_signal": emergency,
        "summary": summary,
    }
