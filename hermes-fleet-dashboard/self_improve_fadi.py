#!/usr/bin/env python3
"""
self_improve_fadi.py — Self-Learning Companion for Polymarket-Fadi Bot
=======================================================================
Polls the bot's API, tracks wallet/strategy performance over time,
builds a persistent learning database, and outputs recommendations.

Data stored in data/self_improve_fadi.json in the fleet volume.

Run:  python3 self_improve_fadi.py [--once]
Cron: every 30 minutes
"""

import json
import os
import sys
import time
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BOT_URL = os.environ.get("POLYFADI_URL", "http://172.18.0.6:3001")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
STATE_FILE = DATA_DIR / "self_improve_fadi.json"

# How long a wallet's performance data is valid (7 days)
WALLET_MEMORY_DAYS = 7

# Minimum trades a wallet needs before we rank it
WALLET_MIN_TRADES = 10

# EWMA decay for wallet accuracy
ALPHA = 0.15

# ---------------------------------------------------------------------------
# API Helpers
# ---------------------------------------------------------------------------

def fetch_json(path: str, timeout: int = 10) -> Optional[dict]:
    try:
        req = Request(f"{BOT_URL}{path}", headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[FETCH] {path}: {e}")
        return None


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class FadiSelfImprover:
    def __init__(self):
        self.state = self._load()
        self.data_dir = DATA_DIR
        self.data_dir.mkdir(exist_ok=True)

    def _load(self) -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return self._default_state()

    def _default_state(self) -> dict:
        return {
            "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_update": None,
            "total_cycles": 0,
            # Wallet performance tracking
            "wallet_performance": {},
            # Strategy performance (smart money / arbitrage / dip arb / direct)
            "strategy_performance": {
                "smartMoney": {"trades": 0, "est_pnl": 0, "win_rate": 0.5, "avg_profit_pct": 0},
                "arbitrage": {"trades": 0, "est_pnl": 0, "win_rate": 0.5, "avg_profit_pct": 0},
                "dipArb": {"trades": 0, "est_pnl": 0, "win_rate": 0.5, "avg_profit_pct": 0},
                "directTrades": {"trades": 0, "est_pnl": 0, "win_rate": 0.5, "avg_profit_pct": 0},
            },
            # Recommended wallets to follow
            "recommended_wallets": [],
            # Recommended strategy allocation
            "recommended_allocation": {
                "smartMoney": 0.60,
                "arbitrage": 0.20,
                "dipArb": 0.10,
                "directTrades": 0.10,
            },
            # Performance history (last 100 snapshots)
            "history": [],
            # Learnings
            "learnings": [],
        }

    def _save(self):
        self.state["last_update"] = datetime.now(timezone.utc).isoformat()
        self.state["total_cycles"] += 1
        STATE_FILE.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------------
    # Core learning cycle
    # ------------------------------------------------------------------

    def learn(self):
        """Main learning cycle: fetch data, analyze, update state."""
        print(f"[FADI-SI] Learning cycle starting...")

        state_data = fetch_json("/api/state")
        if not state_data:
            print("[FADI-SI] Could not fetch /api/state")
            return

        config_data = fetch_json("/api/config")
        logs_data = fetch_json("/api/logs")

        ts = datetime.now(timezone.utc).isoformat()

        # 1. Snapshot current state
        snapshot = {
            "ts": ts,
            "total_trades": state_data.get("tradesExecuted", 0),
            "current_capital": state_data.get("currentCapital", 250),
            "daily_pnl": state_data.get("dailyPnL", 0),
            "total_pnl": state_data.get("totalPnL", 0),
            "peak_capital": state_data.get("peakCapital", 250),
            "drawdown": state_data.get("currentDrawdown", 0),
            "is_paused": state_data.get("isPaused", False),
        }
        self.state["history"].append(snapshot)
        self.state["history"] = self.state["history"][-100:]

        # 2. Track wallet performance from signals
        signals = state_data.get("smartMoneySignals", [])
        self._learn_wallets(signals)

        # 3. Track strategy performance
        self._learn_strategies(state_data)

        # 4. Generate recommendations
        self._generate_recommendations(state_data)

        # 5. Generate insights
        self._generate_learnings(state_data)

        self._save()
        print(f"[FADI-SI] Cycle complete. Wallets tracked: {len(self.state['wallet_performance'])} | "
              f"History: {len(self.state['history'])} snapshots")

    # ------------------------------------------------------------------
    # Wallet learning
    # ------------------------------------------------------------------

    def _learn_wallets(self, signals: list):
        """Track wallet performance from Smart Money Copy signals."""
        for sig in signals:
            wallet = sig.get("wallet", "")
            if not wallet:
                continue
            side = sig.get("side", "BUY")
            price = sig.get("price", 0.5)

            # Create wallet entry if new
            if wallet not in self.state["wallet_performance"]:
                self.state["wallet_performance"][wallet] = {
                    "first_seen": datetime.now(timezone.utc).isoformat(),
                    "signals": 0,
                    "buy_signals": 0,
                    "sell_signals": 0,
                    "avg_buy_price": 0,
                    "avg_sell_price": 0,
                    "last_signal": None,
                    "estimated_accuracy": 0.5,
                }

            wp = self.state["wallet_performance"][wallet]
            wp["signals"] += 1
            wp["last_signal"] = datetime.now(timezone.utc).isoformat()

            if side == "BUY":
                wp["buy_signals"] += 1
                old = wp["avg_buy_price"]
                n = wp["buy_signals"]
                wp["avg_buy_price"] = round((old * (n - 1) + price) / n, 4)
            else:
                wp["sell_signals"] += 1
                old = wp["avg_sell_price"]
                n = wp["sell_signals"]
                wp["avg_sell_price"] = round((old * (n - 1) + price) / n, 4)

    # ------------------------------------------------------------------
    # Strategy learning
    # ------------------------------------------------------------------

    def _learn_strategies(self, state: dict):
        """Track strategy-level performance."""
        sp = self.state["strategy_performance"]

        # Smart Money: signal count proxy
        signals = state.get("smartMoneySignals", [])
        trades = state.get("smartMoneyTrades", 0)
        if trades > sp["smartMoney"]["trades"]:
            new_trades = trades - sp["smartMoney"]["trades"]
            sp["smartMoney"]["trades"] = trades
            # Estimate win rate from bot's tracking (we don't know per-trade outcome)
            # Proxy: use the overall win rate of followed wallets
            sp["smartMoney"]["est_pnl"] = state.get("totalPnL", 0)

        # Arbitrage
        arb_trades = state.get("arbTrades", 0)
        if arb_trades > sp["arbitrage"]["trades"]:
            sp["arbitrage"]["trades"] = arb_trades

        # Dip Arb
        dip_trades = state.get("dipArbTrades", 0)
        if dip_trades > sp["dipArb"]["trades"]:
            sp["dipArb"]["trades"] = dip_trades

        # Direct
        direct_trades = state.get("directTrades", 0)
        if direct_trades > sp["directTrades"]["trades"]:
            sp["directTrades"]["trades"] = direct_trades

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _generate_recommendations(self, state: dict):
        """Generate actionable recommendations."""
        wallet_perf = self.state["wallet_performance"]

        # Rank all wallets by signal frequency × recency
        now = datetime.now(timezone.utc)
        scored = []
        for addr, wp in wallet_perf.items():
            if wp["signals"] < WALLET_MIN_TRADES:
                continue
            # Score: signals count × recency factor
            days_since = 0
            if wp.get("last_signal"):
                try:
                    last = datetime.fromisoformat(wp["last_signal"])
                    days_since = (now - last).total_seconds() / 86400
                except Exception:
                    pass
            recency = max(0, 1 - days_since / WALLET_MEMORY_DAYS)
            # Higher score = more active + more signals
            score = round(wp["signals"] * recency, 1)
            scored.append({
                "wallet": addr,
                "signals": wp["signals"],
                "avg_buy": wp["avg_buy_price"],
                "avg_sell": wp["avg_sell_price"],
                "score": score,
                "recency": round(recency, 2),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        self.state["recommended_wallets"] = scored[:20]

        # Recommended strategy allocation
        sp = self.state["strategy_performance"]
        total_trades = sum(s["trades"] for s in sp.values())
        if total_trades > 0:
            # Allocate proportionally to trade volume (simplified)
            # More active strategies get more capital
            alloc = {}
            for strat, perf in sp.items():
                share = perf["trades"] / max(total_trades, 1)
                alloc[strat] = round(share, 2)

            # Normalize
            total = sum(alloc.values())
            if total > 0:
                for strat in alloc:
                    alloc[strat] = round(alloc[strat] / total, 2)
                self.state["recommended_allocation"] = alloc

    # ------------------------------------------------------------------
    # Learnings / Insights
    # ------------------------------------------------------------------

    def _generate_learnings(self, state: dict):
        """Generate natural-language insights."""
        learnings = []

        # Wallet diversity
        wc = len(self.state["wallet_performance"])
        learnings.append(f"Tracking {wc} unique Smart Money wallets")

        # Capital trend
        history = self.state["history"]
        if len(history) >= 2:
            first_cap = history[0].get("current_capital", 250)
            last_cap = history[-1].get("current_capital", 250)
            cap_change = last_cap - first_cap
            if abs(cap_change) > 0:
                direction = "📈" if cap_change > 0 else "📉"
                learnings.append(f"Capital {direction} ${abs(cap_change):.1f} since tracking started")

        # Most active wallet
        if self.state["recommended_wallets"]:
            top = self.state["recommended_wallets"][0]
            learnings.append(f"Most active wallet: {top['wallet'][:10]}... ({top['signals']} signals)")

        # Strategy mix
        sp = self.state["strategy_performance"]
        for strat, perf in sp.items():
            if perf["trades"] > 0:
                learnings.append(f"{strat}: {perf['trades']} trades tracked")

        self.state["learnings"] = learnings[-20:]

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_summary(self) -> dict:
        return {
            "total_cycles": self.state["total_cycles"],
            "wallets_tracked": len(self.state["wallet_performance"]),
            "history_snapshots": len(self.state["history"]),
            "recommended_wallets": self.state["recommended_wallets"][:5],
            "recommended_allocation": self.state["recommended_allocation"],
            "strategy_performance": self.state["strategy_performance"],
            "learnings": self.state["learnings"][-5:],
        }

    def get_insights_json(self) -> dict:
        """Return clean JSON for the fleet dashboard."""
        return {
            "fadi": self.get_summary(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    once = "--once" in sys.argv

    si = FadiSelfImprover()
    print(f"[FADI-SI] Starting (mode: {'one-shot' if once else 'daemon'})")
    print(f"[FADI-SI] POLYFADI_URL = {BOT_URL}")
    print(f"[FADI-SI] DATA_DIR = {DATA_DIR}")

    if once:
        si.learn()
        summary = si.get_summary()
        print(f"\n=== Summary ===")
        print(f"Wallets tracked: {summary['wallets_tracked']}")
        print(f"History snapshots: {summary['history_snapshots']}")
        print(f"Learnings: {json.dumps(summary['learnings'], indent=2)}")
        print(f"Recommended allocation: {json.dumps(summary['recommended_allocation'], indent=2)}")
    else:
        while True:
            try:
                si.learn()
            except Exception as e:
                print(f"[FADI-SI] Error: {e}")
            print(f"[FADI-SI] Sleeping 30 min...\n")
            time.sleep(1800)  # 30 minutes
