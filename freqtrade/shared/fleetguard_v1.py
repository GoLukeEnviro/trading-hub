"""
FleetGuard v1 — Fleet-Level Entry Safety Layer
Lightweight, no network calls, no external dependencies.
All state is in-memory from trade history via Freqtrade's DataProvider.
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("fleetguard")

# ── Backtest gate bypass ──────────────────────────────────────────────
BACKTEST_GATES = os.environ.get("BACKTEST_GATES", "true").lower() not in ("false", "0", "no")

REASON_CODES = {
    "fleetguard_pass": "Entry allowed by FleetGuard",
    "fleetguard_disabled": "FleetGuard is disabled",
    "max_open_trades": "Total open trades exceeds limit",
    "max_open_shorts": "Short exposure exceeds limit",
    "max_open_longs": "Long exposure exceeds limit",
    "pair_loss_lock": "Pair has too many recent losses",
    "side_loss_lock": "Side (long/short) has too many recent losses",
    "drawdown_hard": "Hard drawdown limit exceeded",
    "drawdown_soft": "Soft drawdown warning (allowed)",
    "volatility_too_low": "ATR below minimum threshold",
    "volatility_too_high": "ATR above maximum threshold",
}

class FleetGuardConfig:
    """Configuration for FleetGuard entry checks."""
    def __init__(self, **kwargs):
        self.enabled = kwargs.get("enabled", True)
        self.max_open_trades = kwargs.get("max_open_trades", 3)
        self.max_open_shorts = kwargs.get("max_open_shorts", 3)
        self.max_open_longs = kwargs.get("max_open_longs", 3)
        self.pair_loss_lock_after_losses = kwargs.get("pair_loss_lock_after_losses", 3)
        self.side_loss_lock_after_losses = kwargs.get("side_loss_lock_after_losses", 2)
        self.daily_drawdown_soft_limit = kwargs.get("daily_drawdown_soft_limit", 0.03)
        self.daily_drawdown_hard_limit = kwargs.get("daily_drawdown_hard_limit", 0.05)
        self.volatility_atr_min_pct = kwargs.get("volatility_atr_min_pct", 0.001)
        self.volatility_atr_max_pct = kwargs.get("volatility_atr_max_pct", 0.08)

class FleetGuard:
    """Stateless entry guard. Each call should pass current context."""
    
    def __init__(self, config: Optional[FleetGuardConfig] = None):
        self.config = config or FleetGuardConfig()
    
    def check_entry(self, pair: str, side: str, open_trades: list,
                    recent_closed_trades: list, current_drawdown_pct: float,
                    atr_pct: float = None) -> tuple:
        """
        Returns (allowed: bool, reason: str).
        open_trades: list of dicts with 'pair', 'is_short' keys.
        recent_closed_trades: list of dicts with 'pair', 'is_short', 'close_profit' keys.
        """
        if not BACKTEST_GATES:
            return True, "gates_bypassed"
        if not self.config.enabled:
            return True, "fleetguard_disabled"
        
        # 1. Max open trades
        if len(open_trades) >= self.config.max_open_trades:
            return False, f"max_open_trades({len(open_trades)}/{self.config.max_open_trades})"
        
        # 2. Side exposure limits
        open_shorts = sum(1 for t in open_trades if t.get("is_short", False))
        open_longs = len(open_trades) - open_shorts
        if side == "short" and open_shorts >= self.config.max_open_shorts:
            return False, f"max_open_shorts({open_shorts}/{self.config.max_open_shorts})"
        if side == "long" and open_longs >= self.config.max_open_longs:
            return False, f"max_open_longs({open_longs}/{self.config.max_open_longs})"
        
        # 3. Pair loss lock — reject if pair has N+ consecutive losses
        pair_losses = [t for t in recent_closed_trades 
                       if t.get("pair") == pair and (t.get("close_profit") or 0) < 0]
        if len(pair_losses) >= self.config.pair_loss_lock_after_losses:
            return False, f"pair_loss_lock({pair}/{len(pair_losses)}_losses)"
        
        # 4. Side loss lock — reject side after N+ consecutive losses on that side
        is_short = side == "short"
        side_losses = [t for t in recent_closed_trades
                       if t.get("is_short") == is_short and (t.get("close_profit") or 0) < 0]
        if len(side_losses) >= self.config.side_loss_lock_after_losses:
            return False, f"side_loss_lock({side}/{len(side_losses)}_losses)"
        
        # 5. Drawdown guard
        if current_drawdown_pct >= self.config.daily_drawdown_hard_limit:
            return False, f"drawdown_hard({current_drawdown_pct:.3f}>={self.config.daily_drawdown_hard_limit})"
        if current_drawdown_pct >= self.config.daily_drawdown_soft_limit:
            logger.warning(f"FleetGuard SOFT drawdown: {current_drawdown_pct:.3f} — allowing entry")
        
        # 6. Volatility guard (if ATR available)
        if atr_pct is not None:
            if atr_pct < self.config.volatility_atr_min_pct:
                return False, f"volatility_too_low({atr_pct:.4f}<{self.config.volatility_atr_min_pct})"
            if atr_pct > self.config.volatility_atr_max_pct:
                return False, f"volatility_too_high({atr_pct:.4f}>{self.config.volatility_atr_max_pct})"
        
        return True, "fleetguard_pass"
