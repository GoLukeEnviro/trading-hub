"""
SHARED_CONSTANTS.py — Single Source of Truth für alle Trading-Komponenten.
FIX: 2026-06-05 — Ersetzt hardcoded Werte in:
  trading_pipeline.py, riskguard_service.py, fleet_risk_manager.py

USAGE:
  from freqtrade.shared.SHARED_CONSTANTS import SIGNAL_MAX_AGE_SECONDS
"""
import os

# ── Signal Staleness ──────────────────────────────────────────
SIGNAL_MAX_AGE_SECONDS   = 1200   # 20 min — konservativster Wert (war: 25/30/45 min überall anders)
SIGNAL_ALERT_AGE_SECONDS = 960    # 16 min — Alert-Schwelle

# ── RiskGuard ─────────────────────────────────────────────────
CONFIDENCE_THRESHOLD          = 0.65
MAX_ACCEPTED_PAIRS_PER_CYCLE  = 5
MAX_POSITION_SIZE_PCT         = 0.20   # 20% max pro Position

# ── Fleet Risk ────────────────────────────────────────────────
DRAWDOWN_LEVEL_1_PCT = 0.06    # 6%  → Throttle (Multiplier 0.75)
DRAWDOWN_LEVEL_2_PCT = 0.12    # 12% → Hard-Limit (Multiplier 0.25)
DRAWDOWN_LEVEL_3_PCT = 0.18    # 18% → Emergency (Multiplier 0)
MAX_DIRECTIONAL_BIAS = 0.70    # Max 70% Long oder Short im Fleet

# ── Direction ─────────────────────────────────────────────────
ALLOWED_ACTIONS = ["long", "short", "hold", "close"]

# ── Kill Switch ───────────────────────────────────────────────
KILL_SWITCH_FILE  = os.path.join(os.path.dirname(__file__), "kill_switch.json")
SYSTEM_MODE_FILE  = os.path.join(os.path.dirname(__file__), "system_mode.json")

# ── Signal Source ─────────────────────────────────────────────
PRIMARY_SIGNAL_SOURCE = "ai-hedge-fund-crypto"
