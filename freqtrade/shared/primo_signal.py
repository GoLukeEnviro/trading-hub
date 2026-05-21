"""Primo signal helper functions for Freqtrade strategies.

This module is mounted into the containers at /freqtrade/shared and used by
strategies as a conservative side-filter:
- no fresh Primo signal -> normal strategy logic (fallback)
- HOLD / missing pair -> normal strategy logic (fallback)
- explicit LONG/BUY -> allow long, block short
- explicit SHORT/SELL -> allow short, block long
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_STATE_FILE = "/freqtrade/user_data/primo_signal_state.json"

# Import canonical staleness threshold from fleet_risk_manager
try:
    from fleet_risk_manager import STALENESS_MINUTES as MAX_AGE_MINUTES
except ImportError:
    MAX_AGE_MINUTES = 30.0  # fallback — keep in sync with fleet_risk_manager


def normalize_pair(pair: Optional[str]) -> str:
    """Normalize Freqtrade pairs like BTC/USDT:USDT -> BTC/USDT."""
    if not pair:
        return ""
    pair = str(pair).strip().upper()
    if ":" in pair:
        pair = pair.split(":", 1)[0]
    return pair


def load_signal_state(state_file: str = DEFAULT_STATE_FILE) -> Optional[Dict[str, Any]]:
    """Load the latest Primo signal state JSON from the mounted user_data dir."""
    path = Path(state_file)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    return data


def primo_gate_allows(
    pair: Optional[str],
    side: str,
    state_file: str = DEFAULT_STATE_FILE,
    max_age_minutes: float = MAX_AGE_MINUTES,
) -> bool:
    """Return True when the strategy should keep its normal logic.

    The helper is intentionally conservative:
    - stale/missing signal file => fallback to normal strategy logic
    - pair not present => fallback
    - HOLD/UNKNOWN/other non-directional actions => fallback
    - WATCH_ONLY verdict => fallback (no directional bias)
    - BLOCK_ENTRY verdict => fallback (no Primo permission)
    - explicit LONG/BUY with ACCEPTED verdict => block shorts, allow longs
    - explicit SHORT/SELL with ACCEPTED verdict => block longs, allow shorts
    """
    state = load_signal_state(state_file)
    if not state:
        return True

    if not bool(state.get("fresh", False)):
        return True

    age_minutes = state.get("age_minutes")
    try:
        if age_minutes is not None and float(age_minutes) > float(max_age_minutes):
            return True
    except Exception:
        return True

    pairs = state.get("pairs") or {}
    if not isinstance(pairs, dict):
        return True

    entry = pairs.get(normalize_pair(pair))
    if not isinstance(entry, dict):
        return True

    # NEW (schema 0.2): Check verdict first
    verdict = str(entry.get("verdict", "UNKNOWN")).upper().strip()
    
    # WATCH_ONLY: check bias flags (schema 0.2) — block if bias is explicitly false
    if verdict == "WATCH_ONLY":
        if side.lower() == "long":
            return bool(entry.get("allow_long_bias", False))
        if side.lower() == "short":
            return bool(entry.get("allow_short_bias", False))
        return True  # no bias info = fallback to strategy logic
    
    # ACCEPTED verdict: use bias flags if available (schema 0.2)
    if verdict == "ACCEPTED":
        if side.lower() == "long":
            return bool(entry.get("allow_long_bias", False))
        if side.lower() == "short":
            return bool(entry.get("allow_short_bias", False))
        return True
    
    # FALLBACK (schema 0.1 backward compatibility): use action directly
    action = str(entry.get("action", "")).upper().strip()
    side = str(side).lower().strip()
    
    if action in {"BUY", "LONG"}:
        return side != "short"
    if action in {"SELL", "SHORT"}:
        return side != "long"

    return True
