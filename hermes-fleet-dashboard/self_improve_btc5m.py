#!/usr/bin/env python3
"""
self_improve_btc5m.py — Self-Learning Companion for BTC 5-Min Bot
================================================================
Analyzes historical trades to find optimal delta thresholds,
confidence calibration, and dynamic bet sizing.

Data stored in data/self_improve_btc5m.json in the volume.

Usage:
  python3 self_improve_btc5m.py [--once]
  cron: every 30 minutes
"""

import json
import os
import sys
import math
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request

BOT_URL = os.environ.get("BTC5M_URL", "http://172.18.0.4:9090")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
STATE_FILE = DATA_DIR / "self_improve_btc5m.json"

# Minimum trades before making recommendations
MIN_TRADES = 10

# EWMA decay for rolling metrics
ALPHA = 0.15


def fetch_json(path: str, timeout: int = 10) -> Optional[dict]:
    try:
        req = Request(f"{BOT_URL}{path}", headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return None


class BTC5mSelfImprover:
    def __init__(self):
        self.state = self._load()

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
            # Delta range buckets: performance per delta threshold range
            "delta_performance": {},  # { "0.03-0.05": {"trades": N, "wins": N, "win_rate": 0.5, ...} }
            # Confidence calibration
            "confidence_calibration": [],  # [{ "confidence": 0.8, "won": true, "delta": 0.05 }, ...]
            # Hour-of-day performance
            "hour_performance": {},  # { "3": {"trades": N, "wins": N}, ... }
            # Direction performance
            "direction_performance": {
                "UP": {"trades": 0, "wins": 0, "avg_delta": 0, "avg_entry": 0},
                "DOWN": {"trades": 0, "wins": 0, "avg_delta": 0, "avg_entry": 0},
            },
            # Recommended parameters
            "recommendations": {
                "optimal_delta_threshold": 0.03,
                "recommended_bet_size_pct": 0.05,
                "dynamic_kelly": 0.25,
                "best_hours": [],
                "worst_hours": [],
                "confidence_bias": {},  # calibration offset per confidence range
            },
            # Performance metrics
            "current_streak": 0,
            "rolling_win_rate": 0.5,
            "rolling_avg_pnl": 0,
            "sharpe_ratio": 0,
            # History
            "history": [],
            "learnings": [],
        }

    def _save(self):
        self.state["last_update"] = datetime.now(timezone.utc).isoformat()
        self.state["total_cycles"] += 1
        STATE_FILE.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def learn(self):
        status = fetch_json("/api/status")
        if not status:
            print("[BTC5M-SI] Could not fetch /api/status")
            return

        trades = status.get("recent_trades", [])
        wins = status.get("wins", 0)
        losses = status.get("losses", 0)
        total = wins + losses
        bankroll = status.get("bankroll", 100)

        if total < MIN_TRADES:
            print(f"[BTC5M-SI] Only {total} trades, need {MIN_TRADES} (warmup)")
            return

        # 1. Delta range performance
        self._analyze_delta_ranges(trades)

        # 2. Confidence calibration
        self._calibrate_confidence(trades)

        # 3. Hour-of-day analysis
        self._analyze_hours(trades)

        # 4. Direction performance
        self._analyze_directions(trades)

        # 5. Generate recommendations
        self._generate_recommendations(trades, total, wins, losses, bankroll)

        # 6. Snapshot
        self.state["history"].append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "total_trades": total,
            "bankroll": round(bankroll, 2),
            "pct_change": round((bankroll - 100) / 100 * 100, 1),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / max(total, 1) * 100, 1),
            "recommended_threshold": self.state["recommendations"]["optimal_delta_threshold"],
            "recommended_kelly": self.state["recommendations"]["dynamic_kelly"],
        })
        self.state["history"] = self.state["history"][-100:]

        self._generate_learnings(trades, total, wins, losses)
        self._save()
        print(f"[BTC5M-SI] Cycle done. {total} trades analyzed. "
              f"Optimal threshold: {self.state['recommendations']['optimal_delta_threshold']}%")

    def _analyze_delta_ranges(self, trades: list):
        """Group trades by delta percentage ranges and calculate win rates."""
        ranges = [(0.0, 0.03), (0.03, 0.05), (0.05, 0.08), (0.08, 0.12),
                  (0.12, 0.20), (0.20, 0.50), (0.50, 999)]
        dp = {}

        for low, high in ranges:
            key = f"{low:.2f}-{high:.2f}"
            group = [t for t in trades if abs(t.get("delta_pct", 0)) > low and abs(t.get("delta_pct", 0)) <= high]
            if not group:
                continue
            wins = sum(1 for t in group if t.get("won"))
            dp[key] = {
                "trades": len(group),
                "wins": wins,
                "win_rate": round(wins / len(group), 3),
                "avg_delta": round(sum(abs(t.get("delta_pct", 0)) for t in group) / len(group), 4),
                "avg_entry": round(sum(t.get("entry_price", 0) for t in group) / len(group), 4),
            }

        self.state["delta_performance"] = dp

    def _calibrate_confidence(self, trades: list):
        """Calibrate confidence formula against actual outcomes."""
        cal = []
        for t in trades:
            cal.append({
                "confidence": t.get("confidence", 0),
                "won": t.get("won"),
                "delta_pct": t.get("delta_pct", 0),
            })
        self.state["confidence_calibration"] = cal[-200:]

        # Calculate bias per confidence bracket
        brackets = [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.0)]
        bias = {}
        for lo, hi in brackets:
            group = [c for c in cal if lo <= c["confidence"] < hi and c["won"] is not None]
            if group:
                actual_wr = sum(1 for c in group if c["won"]) / len(group)
                predicted_wr = (lo + hi) / 2  # mid-point
                bias[f"{lo:.1f}-{hi:.1f}"] = round(actual_wr - predicted_wr, 3)
        self.state["recommendations"]["confidence_bias"] = bias

    def _analyze_hours(self, trades: list):
        """Analyze performance by hour of day (UTC)."""
        hp = {}
        for t in trades:
            ts = t.get("timestamp", "")
            if not ts:
                continue
            try:
                hour = datetime.fromisoformat(ts).hour
            except Exception:
                continue
            if hour not in hp:
                hp[hour] = {"trades": 0, "wins": 0, "avg_delta": 0}
            hp[hour]["trades"] += 1
            if t.get("won"):
                hp[hour]["wins"] += 1
            hp[hour]["avg_delta"] = (hp[hour]["avg_delta"] * (hp[hour]["trades"] - 1)
                                      + abs(t.get("delta_pct", 0))) / hp[hour]["trades"]

        # Calculate win rates
        for h in hp:
            hp[h]["win_rate"] = round(hp[h]["wins"] / hp[h]["trades"], 3) if hp[h]["trades"] > 0 else 0

        self.state["hour_performance"] = hp

    def _analyze_directions(self, trades: list):
        """Analyze UP vs DOWN performance."""
        dp = self.state["direction_performance"]
        for t in trades:
            direction = t.get("direction", "UP")
            if direction not in dp:
                dp[direction] = {"trades": 0, "wins": 0, "avg_delta": 0, "avg_entry": 0}
            d = dp[direction]
            d["trades"] += 1
            if t.get("won"):
                d["wins"] += 1
            n = d["trades"]
            d["avg_delta"] = (d["avg_delta"] * (n - 1) + abs(t.get("delta_pct", 0))) / n
            d["avg_entry"] = (d["avg_entry"] * (n - 1) + t.get("entry_price", 0)) / n

        for direction in dp:
            d = dp[direction]
            d["win_rate"] = round(d["wins"] / max(d["trades"], 1), 3)

    def _generate_recommendations(self, trades: list, total: int, wins: int, losses: int, bankroll: float):
        """Calculate optimal threshold and sizing."""
        rec = self.state["recommendations"]

        # Optimal delta threshold: find the range with best WR that has enough trades
        best_threshold = 0.03  # default
        best_wr = 0
        for key, perf in self.state["delta_performance"].items():
            if perf["trades"] >= 5 and perf["win_rate"] > best_wr:
                best_wr = perf["win_rate"]
                # Extract the low bound from the key
                low = float(key.split("-")[0])
                if low > 0:
                    best_threshold = low

        rec["optimal_delta_threshold"] = best_threshold

        # Dynamic Kelly
        wr = wins / max(total, 1)
        loss_rate = 1 - wr
        if losses > 0 and wins > 0:
            avg_win = sum(t.get("pnl", 0) for t in trades if t.get("won") and t.get("pnl", 0) > 0) / max(wins, 1)
            avg_loss = sum(abs(t.get("pnl", 0)) for t in trades if not t.get("won") and t.get("pnl", 0) is not None) / max(losses, 1)
            if avg_loss > 0:
                # Kelly formula: f = (p * b - (1-p)) / b where b = avg_win / avg_loss
                b = avg_win / avg_loss if avg_loss > 0 else 1
                kelly = (wr * b - (1 - wr)) / b
                kelly = max(0.05, min(kelly * 0.5, 0.50))  # half-kelly, capped
            else:
                kelly = 0.50  # no losses yet - optimistic
        else:
            kelly = 0.25

        rec["dynamic_kelly"] = round(kelly, 4)
        rec["recommended_bet_size_pct"] = round(kelly * 0.5, 4)  # half-kelly of bankroll

        # Best/worst hours
        hp = self.state["hour_performance"]
        sorted_hours = sorted(hp.items(), key=lambda x: x[1].get("win_rate", 0), reverse=True)
        rec["best_hours"] = [{"hour": int(h), "win_rate": d["win_rate"], "avg_delta": round(d["avg_delta"], 3)}
                             for h, d in sorted_hours[:3] if d["trades"] >= 3]
        rec["worst_hours"] = [{"hour": int(h), "win_rate": d["win_rate"], "avg_delta": round(d["avg_delta"], 3)}
                              for h, d in sorted_hours[-3:] if d["trades"] >= 3]

        # Rolling metrics
        self.state["rolling_win_rate"] = round(wr, 4)
        pnls = [t.get("pnl", 0) for t in trades if t.get("pnl") is not None]
        self.state["rolling_avg_pnl"] = round(sum(pnls) / max(len(pnls), 1), 4)

        # Simple Sharpe ratio
        if len(pnls) > 1:
            mean = sum(pnls) / len(pnls)
            std = math.sqrt(sum((p - mean) ** 2 for p in pnls) / len(pnls))
            self.state["sharpe_ratio"] = round(mean / max(std, 0.001), 2)
        else:
            self.state["sharpe_ratio"] = 0

    def _generate_learnings(self, trades: list, total: int, wins: int, losses: int):
        learnings = []
        wr = wins / max(total, 1) * 100

        learnings.append(f"Overall WR: {wr:.1f}% ({wins}W/{losses}L from {total} trades)")

        rec = self.state["recommendations"]
        if rec["optimal_delta_threshold"] != 0.03:
            learnings.append(f"📈 Optimal delta threshold: {rec['optimal_delta_threshold']}% (current: 0.03%)")
        else:
            learnings.append(f"Delta threshold of 0.03% confirmed optimal")

        if rec["dynamic_kelly"] != 0.25:
            learnings.append(f"💰 Dynamic Kelly suggests: {rec['dynamic_kelly']:.0%} (current: fixed $5)")

        # Best hour
        if rec["best_hours"]:
            bh = rec["best_hours"][0]
            learnings.append(f"⏰ Best hour: {bh['hour']}:00 UTC (WR: {bh['win_rate']:.0%})")

        # Confidence bias
        cb = rec.get("confidence_bias", {})
        for bracket, bias in cb.items():
            if abs(bias) > 0.1:
                learnings.append(f"⚠️ Confidence bias in {bracket}: {bias:+.0%} (over/under-confident)")

        # Direction bias
        dp = self.state["direction_performance"]
        for direction, perf in dp.items():
            if perf["trades"] >= 5:
                learnings.append(f"{'📈' if direction=='UP' else '📉'} {direction}: {perf['win_rate']:.0%} WR ({perf['trades']} trades)")

        self.state["learnings"] = learnings[-20:]

    def get_summary(self) -> dict:
        return {
            "total_cycles": self.state["total_cycles"],
            "trades_analyzed": self.state["history"][-1]["total_trades"] if self.state["history"] else 0,
            "delta_performance": dict(list(self.state["delta_performance"].items())[:8]),
            "direction_performance": self.state["direction_performance"],
            "recommendations": self.state["recommendations"],
            "hour_performance": dict(list(self.state["hour_performance"].items())),
            "sharpe_ratio": self.state["sharpe_ratio"],
            "rolling_win_rate": self.state["rolling_win_rate"],
            "rolling_avg_pnl": self.state["rolling_avg_pnl"],
            "history": self.state["history"][-5:],
            "learnings": self.state["learnings"],
        }


if __name__ == "__main__":
    once = "--once" in sys.argv
    si = BTC5mSelfImprover()
    print(f"[BTC5M-SI] Starting (mode: {'one-shot' if once else 'daemon'})")

    if once:
        si.learn()
        summary = si.get_summary()
        print(f"\n=== Summary ===")
        print(f"Trades analyzed: {summary['trades_analyzed']}")
        for l in summary['learnings']:
            print(f"  • {l}")
    else:
        while True:
            try:
                si.learn()
            except Exception as e:
                print(f"[BTC5M-SI] Error: {e}")
            time.sleep(1800)
