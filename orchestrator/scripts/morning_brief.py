#!/opt/hermes/.venv/bin/python3
"""morning_brief.py — Daily Morning Brief v1.0

Sends a compact 8-line Telegram briefing at 08:00 UTC.
Run as no_agent cron job with deliver=telegram.
Output is sent to Telegram by the scheduler.

Output format:
  ☀️ Hermes Morning Brief — 2026-05-31 UTC
  📊 Fleet: +X.XX USDT | Top: Bot (+Y.YY) | Bottom: Bot (-Z.ZZ)
  📡 Signal: bearish/bullish @ conf 0.XX (BTC/ETH/SOL)
  📉 Drawdown: X.XX% | ConsecLoss: Y
  🔒 Self-Healing: alles grün
"""

import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

BASE = "/home/hermes/projects/trading"
STATE_DIR = Path(BASE) / "orchestrator/state"
OUTPUT_FILE = STATE_DIR / "morning_brief.json"


def get_fleet_pnl() -> tuple:
    """Get total PnL and best/worst bot from SQLite."""
    bots = [
        ("trading-freqtrade-freqforge-1", "/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite", "FreqForge"),
        ("trading-freqtrade-freqforge-canary-1", "/freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite", "Canary"),
        ("trading-freqtrade-regime-hybrid-1", "/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite", "Regime-Hybrid"),
        ("trading-freqai-rebel-1", "/freqtrade/user_data/tradesv3.rebel.dryrun.sqlite", "Rebel"),
    ]
    results = {}
    for container, db_path, label in bots:
        try:
            r = subprocess.run(
                ["docker", "exec", container, "sqlite3", db_path,
                 "SELECT coalesce(round(sum(close_profit_abs),2),0) FROM trades WHERE is_open=0;"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                pnl = float(r.stdout.strip())
                results[label] = pnl
        except:
            results[label] = 0.0
    total = sum(results.values())
    top = max(results, key=results.get) if results else "?"
    bottom = min(results, key=results.get) if results else "?"
    return total, top, round(results.get(top, 0), 2), bottom, round(results.get(bottom, 0), 2)


def get_signal() -> tuple:
    """Get current signal status."""
    signal_path = BASE + "/ai-hedge-fund-crypto/output/latest/hermes_signal.json"
    try:
        with open(signal_path) as f:
            d = json.load(f)
        btc = d.get("pairs", {}).get("BTC/USDT:USDT", {})
        conf = btc.get("confidence", 0)
        bias = btc.get("bias", "neutral")
        age = d.get("timestamp_utc", "?")
        return bias, conf, age
    except:
        return "?", 0, "?"


def get_safety() -> tuple:
    """Get drawdown and consec losses."""
    fleet_file = BASE + "/freqtrade/shared/fleet_risk_state.json"
    consec_file = STATE_DIR / "consec_loss_state.json"
    dd = 0.0
    cl = 0
    try:
        with open(fleet_file) as f:
            d = json.load(f)
        dd = d.get("portfolio", {}).get("current_drawdown", 0) * 100
    except:
        pass
    try:
        with open(consec_file) as f:
            d = json.load(f)
        cl = d.get("consecutive_losses", 0)
    except:
        pass
    return round(dd, 2), cl


def main() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Gather data
    total_pnl, top_bot, top_pnl, bottom_bot, bottom_pnl = get_fleet_pnl()
    bias, conf, ts = get_signal()
    dd, cl = get_safety()
    
    # Build 8-line brief
    emoji = "🟢" if dd < 3 and cl < 4 else "🟡" if dd < 5 and cl < 6 else "🔴"
    pnl_sign = "+" if total_pnl >= 0 else ""
    conf_pct = int(conf * 100) if conf else 0
    
    lines = [
        f"☀️ Hermes Morning Brief — {now} UTC",
        f"📊 Fleet: {pnl_sign}{total_pnl:.2f} USDT | Top: {top_bot} ({pnl_sign}{top_pnl:.2f}) | Bottom: {bottom_bot} ({bottom_pnl:.2f})",
        f"📡 Signal: {bias} @ {conf_pct}% (BTC/ETH/SOL)",
        f"📉 Drawdown: {dd:.1f}% | ConsecLoss: {cl}",
        f"🔒 Self-Healing: {emoji} {'alles grün' if dd < 3 and cl < 4 else 'parameter aktiv' if dd < 5 else 'CRITICAL — check logs'}",
    ]
    
    # Add note for warnings
    if dd >= 3:
        lines.append(f"  ⚠️ Drawdown über 3% — Auto-Parameter prüfen")
    if cl >= 4:
        lines.append(f"  ⚠️ {cl} Verluste in Folge — MOT-Reduktion aktiv")
    
    message = "\n".join(lines[:8])  # hard cap at 8 lines
    
    # Store for reference
    os.makedirs(str(STATE_DIR), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump({"timestamp": now, "message": message, "data": {
            "total_pnl": total_pnl, "drawdown": dd, "consec_losses": cl,
            "signal_bias": bias, "signal_confidence": conf,
        }}, f)
    
    # Send via stdout (cron scheduler delivers to Telegram)
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
