#!/usr/bin/env python3
"""
Fleet Auto-Repair v2 — Autonomous health check and repair for Freqtrade fleet.

Runs every 2 hours via cron. Checks fleet health, detects:
  - Profit Factor < 1.4 on any bot with > 10 trades
  - Drawdown > 5% fleet-wide or per-bot
  - Empty/stale DBs
  - Container not running
  - Open position risk (stale positions > 48h)
  - FreqAI model drift (no recent training)

Actions (advisory only — logs and alerts, never live-trade changes):
  - Generates structured report with escalation levels (L1-L4)
  - Suggests parameter fixes
  - Detects RR problems and recommends Hyperopt

KEIN Live-Trading. KEINE automatischen Config-Aenderungen ohne User-Approval.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MONITOR_SCRIPT = os.path.join(SCRIPT_DIR, "freqtrade_monitor.py")

# Thresholds (v2 — tighter than v1)
PF_WARN = 1.4       # v2: was 1.2
PF_CRIT = 0.8
DD_WARN_PCT = 5.0
DD_CRIT_PCT = 10.0
MIN_TRADES_FOR_PF = 10
STALE_POSITION_HOURS = 48


def run_cmd(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except Exception as e:
        return "", str(e), 1


def get_fleet_status():
    """Run freqtrade_monitor.py and parse output.
    Note: monitor exits 1 when bots have errors, but still produces valid JSON.
    We only fail on missing/invalid output.
    """
    out, err, code = run_cmd(f"python3 {MONITOR_SCRIPT} 2>/dev/null", timeout=30)
    if not out:
        return None, f"Monitor produced no output (exit={code}): {err[:200]}"
    try:
        return json.loads(out), None
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"


def check_container_health():
    """Check all freqtrade containers are running."""
    issues = []
    out, _, _ = run_cmd("docker ps -a --filter 'name=freqtrade' --format '{{.Names}}|{{.Status}}'", timeout=10)
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 2:
            continue
        name, status = parts[0].strip(), parts[1].strip()
        if "Up" not in status:
            issues.append(f"CONTAINER DOWN: {name} - {status}")
    return issues


def check_freqai_freshness():
    """Check if FreqAI models were trained recently."""
    alerts = []
    out, _, _ = run_cmd("docker logs freqai-rebel --since 2h 2>&1 | grep -c 'Done training'", timeout=15)
    if out and int(out or 0) == 0:
        # Check if rebel is running at all
        status, _, _ = run_cmd("docker inspect -f '{{.State.Status}}' freqai-rebel", timeout=5)
        if status == "running":
            out2, _, _ = run_cmd("docker logs freqai-rebel --since 24h 2>&1 | grep -c 'Done training'", timeout=15)
            if out2 and int(out2 or 0) == 0:
                alerts.append("FREQAI DRIFT: No model training in last 24h")
    return alerts


def check_stale_positions(fleet_data):
    """Check for positions open longer than threshold."""
    alerts = []
    now = datetime.now(timezone.utc)
    for bot in fleet_data.get("bots", []):
        open_trades = bot.get("open_trades", [])
        for trade in open_trades:
            open_date_str = trade.get("open_date", "")
            if not open_date_str:
                continue
            try:
                open_date = datetime.fromisoformat(open_date_str.replace(" ", "T"))
                if open_date.tzinfo is None:
                    open_date = open_date.replace(tzinfo=timezone.utc)
                hours_open = (now - open_date).total_seconds() / 3600
                if hours_open > STALE_POSITION_HOURS:
                    pair = trade.get("pair", "?")
                    alerts.append(
                        f"STALE POS: {bot['name']} {pair} open {hours_open:.0f}h "
                        f"(>{STALE_POSITION_HOURS}h threshold)"
                    )
            except (ValueError, TypeError):
                pass
    return alerts


def analyze_fleet(fleet_data):
    """Analyze fleet data for risk-reward and performance issues."""
    alerts = []
    suggestions = []
    escalation_level = 0  # 0=none, 1=info, 2=warn, 3=crit, 4=halt

    for bot in fleet_data.get("bots", []):
        name = bot.get("name", "unknown")
        stats = bot.get("stats", {})
        status = bot.get("status", "")

        if status in ("ERROR",) or not isinstance(stats, dict):
            alerts.append(f"BOT ERROR: {name} - {bot.get('error', 'unknown')}")
            escalation_level = max(escalation_level, 3)
            continue

        total = stats.get("total_trades", 0)
        pf = stats.get("profit_factor", 0)
        wr = stats.get("winrate", 0)
        pnl = stats.get("total_profit_usdt", 0)
        avg_win = stats.get("avg_win_pct", 0)
        avg_loss = stats.get("avg_loss_pct", 0)
        open_count = stats.get("open_trades_count", 0)

        if total < MIN_TRADES_FOR_PF:
            # Check for warming-up bots
            if total == 0 and open_count == 0:
                pass  # Still warming up
            continue

        # Profit Factor check (v2: PF < 1.4 triggers suggestion)
        if pf < PF_CRIT:
            alerts.append(f"PF CRITICAL: {name} PF={pf:.2f} (< {PF_CRIT})")
            suggestions.append(f"  {name}: Stoploss zu weit / Takeprofit zu eng (avg_win={avg_win}% vs avg_loss={avg_loss}%)")
            suggestions.append(f"  {name}: Hyperopt auf RR-Parameter empfohlen (300 Trials)")
            escalation_level = max(escalation_level, 3)
        elif pf < PF_WARN:
            alerts.append(f"PF WARNING: {name} PF={pf:.2f} (< {PF_WARN})")
            suggestions.append(f"  {name}: Risk-Reward pruefen (avg_win={avg_win}% vs avg_loss={avg_loss}%)")
            escalation_level = max(escalation_level, 2)

        # Drawdown check per bot
        wallet = stats.get("config", {}).get("wallet", 1000)
        if wallet > 0 and pnl < 0:
            dd_pct = abs(pnl / wallet * 100)
            if dd_pct > DD_CRIT_PCT:
                alerts.append(f"DD CRITICAL: {name} DD={dd_pct:.1f}%")
                escalation_level = max(escalation_level, 4)
            elif dd_pct > DD_WARN_PCT:
                alerts.append(f"DD WARNING: {name} DD={dd_pct:.1f}%")
                escalation_level = max(escalation_level, 2)

        # RR ratio check
        if avg_win > 0 and avg_loss < 0:
            rr_ratio = abs(avg_win / avg_loss)
            if rr_ratio < 0.3:
                suggestions.append(f"  {name}: R:R={rr_ratio:.2f}:1 katastrophal (avg_win/avg_loss)")
                escalation_level = max(escalation_level, 3)

    # Fleet-wide check
    summary = fleet_data.get("summary", {})
    bots_error = summary.get("bots_error", 0)
    if bots_error > 0:
        alerts.append(f"FLEET: {bots_error} bot(s) with errors")
        escalation_level = max(escalation_level, 2)

    # Total fleet PnL
    total_pnl = summary.get("total_profit_all_usdt", 0)
    total_wallet = sum(
        bot.get("stats", {}).get("config", {}).get("wallet", 0)
        for bot in fleet_data.get("bots", [])
        if isinstance(bot.get("stats"), dict)
    )
    if total_wallet > 0 and total_pnl < 0:
        fleet_dd = abs(total_pnl / total_wallet * 100)
        if fleet_dd > DD_CRIT_PCT:
            alerts.append(f"FLEET DD CRITICAL: {fleet_dd:.1f}%")
            escalation_level = max(escalation_level, 4)

    return alerts, suggestions, escalation_level


def format_report(fleet_data, alerts, suggestions, container_issues, 
                  freqai_alerts, stale_alerts, escalation_level):
    """Format the auto-repair report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    summary = fleet_data.get("summary", {})
    
    level_names = {0: "CLEAR", 1: "INFO", 2: "WARN", 3: "CRITICAL", 4: "HALT"}
    level_emoji = {0: "GREEN", 1: "INFO", 2: "AMBER", 3: "RED", 4: "EMERGENCY"}
    level = level_names.get(escalation_level, "UNKNOWN")
    emoji = level_emoji.get(escalation_level, "?")

    lines = [
        f"FLEET AUTO-REPAIR v2 - {now}",
        f"Escalation: {emoji} L{escalation_level} ({level})",
        "=" * 40,
        "",
        "FLEET SUMMARY",
        f"  Bots: {summary.get('bots_ok', 0)}/{summary.get('total_bots', 0)} OK",
        f"  Trades: {summary.get('total_trades_all', 0)} total",
        f"  PnL: {summary.get('total_profit_all_usdt', 0):+.2f} USDT",
        f"  Open: {summary.get('open_trades_all', 0)}",
        "",
    ]

    # Per-bot status
    lines.append("PER-BOT STATUS")
    for bot in fleet_data.get("bots", []):
        stats = bot.get("stats", {})
        if isinstance(stats, dict) and stats.get("total_trades", 0) > 0:
            lines.append(
                f"  {bot['name']}: {stats.get('total_trades',0)}t "
                f"WR={stats.get('winrate',0):.0f}% "
                f"PF={stats.get('profit_factor',0):.2f} "
                f"PnL={stats.get('total_profit_usdt',0):+.2f}U "
                f"open={stats.get('open_trades_count',0)}"
            )
        else:
            lines.append(f"  {bot['name']}: {bot.get('status', 'N/A')}")

    all_issues = container_issues + freqai_alerts + stale_alerts + alerts
    if all_issues:
        lines.extend(["", "ISSUES"])
        for issue in all_issues:
            lines.append(f"  {issue}")

    if suggestions:
        lines.extend(["", "SUGGESTIONS"])
        for s in suggestions:
            lines.append(s)

    if not all_issues:
        lines.extend(["", "RESULT: All clear - no action needed"])

    lines.extend(["", f"Next check: +2h | Escalation: L{escalation_level}"])

    return "\n".join(lines)


def main():
    # 1. Check containers
    container_issues = check_container_health()

    # 2. Get fleet data
    fleet_data, err = get_fleet_status()
    if fleet_data is None:
        print(f"FLEET AUTO-REPAIR ERROR: {err}")
        sys.exit(1)

    # 3. Analyze fleet
    alerts, suggestions, escalation_level = analyze_fleet(fleet_data)

    # 4. FreqAI drift check
    freqai_alerts = check_freqai_freshness()

    # 5. Stale position check
    stale_alerts = check_stale_positions(fleet_data)

    # 6. Report — only output if there are issues (silent = healthy)
    has_issues = bool(alerts or container_issues or freqai_alerts or stale_alerts)
    report = format_report(
        fleet_data, alerts, suggestions, container_issues,
        freqai_alerts, stale_alerts, escalation_level
    )

    if has_issues:
        print(report)
    # Silent exit if healthy (no stdout = no delivery via cron)


if __name__ == "__main__":
    main()
