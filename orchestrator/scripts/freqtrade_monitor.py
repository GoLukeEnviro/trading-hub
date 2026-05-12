#!/usr/bin/env python3
"""
Freqtrade Fleet Monitor — Collects live status from all Freqtrade dry-run containers.
Reads trades directly from the bind-mounted SQLite databases on the host.

Usage: python3 freqtrade_monitor.py
Output: JSON to stdout
"""

import json
import subprocess
import sys
import os
from datetime import datetime, timezone

# Project paths
PROJECT_ROOT = "/home/hermes/projects/trading/freqtrade"
BOTS_DIR = os.path.join(PROJECT_ROOT, "bots")

BOTS = {
    "freqtrade-momentum": {
        "bot_dir": os.path.join(BOTS_DIR, "momentum", "user_data"),
        "port": 8084,
        "db": "tradesv3.momentum.sqlite",
    },
    "freqtrade-regime-hybrid": {
        "bot_dir": os.path.join(BOTS_DIR, "regime-hybrid", "user_data"),
        "port": 8085,
        "db": "tradesv3.regime_hybrid.dryrun.sqlite",
    },
    "freqtrade-rsi": {
        "bot_dir": os.path.join(BOTS_DIR, "rsi", "user_data"),
        "port": 8081,
        "db": "tradesv3.dryrun.sqlite",
    },
}

# Docker network
DOCKER_NETWORK = "ki-fabrik"

CONTAINER_IPS = {}


def run_cmd(cmd, timeout=15):
    """Run a shell command and return stdout, stderr."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=True
        )
        return result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT"
    except Exception as e:
        return "", str(e)


def docker_exec(container, cmd, timeout=15):
    """Run a command inside a Docker container."""
    return run_cmd(f'docker exec {container} sh -c {sh_quote(cmd)}', timeout)


def sh_quote(s):
    """Minimal shell quoting for safety."""
    return "'" + s.replace("'", "'\\''") + "'"


def get_container_ip(container):
    """Get container IP on the custom Docker network."""
    if container in CONTAINER_IPS:
        return CONTAINER_IPS[container]
    out, err = run_cmd(f"docker inspect {container} --format='{{{{.NetworkSettings.Networks.{DOCKER_NETWORK}.IPAddress}}}}'", timeout=5)
    if out and out != "<no value>":
        CONTAINER_IPS[container] = out
        return out
    # Fallback: via hostname -i inside the container
    out2, _ = docker_exec(container, "hostname -i", timeout=5)
    if out2:
        CONTAINER_IPS[container] = out2
        return out2
    return None


def get_trade_db_path(bot_name, bot_info):
    """Get the absolute host path to the SQLite trade database."""
    return os.path.join(bot_info["bot_dir"], bot_info["db"])


def parse_sqlite_row(row):
    """Parse a pipe-delimited SQLite row into parts."""
    return [p.strip() for p in row.split("|")]


def get_trade_stats(bot_name, bot_info):
    """Query trade statistics from the SQLite database."""
    db_path = get_trade_db_path(bot_name, bot_info)

    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        return {"error": "DB not found or empty", "total_trades": 0, "wins": 0, "losses": 0}

    container = bot_name
    db_container_path = f"/freqtrade/user_data/{bot_info['db']}"

    # Check DB has trades table
    out, _ = docker_exec(container, f"sqlite3 \"{db_container_path}\" \".tables\" 2>/dev/null", timeout=5)
    if "trades" not in out:
        return {"error": "no trades table", "total_trades": 0, "wins": 0, "losses": 0}

    # Check container is running
    out, _ = run_cmd(f'docker inspect -f "{{{{.State.Status}}}}" {container}', timeout=5)
    if out != "running":
        return {"error": f"container status: {out}", "total_trades": 0}

    config_path = f"/freqtrade/config/config.json"
    if bot_name == "freqtrade-regime-hybrid":
        config_path = "/freqtrade/config/config_regime_hybrid_dryrun.json"

    # Get config info
    stats = {}
    out, err = docker_exec(container, f"""python3 -c "
import json
c = json.load(open('{config_path}'))
print(json.dumps({{
    'dry_run': c.get('dry_run'),
    'exchange': c.get('exchange', {{}}).get('name'),
    'wallet': c.get('dry_run_wallet', 0),
    'stake_amount': c.get('stake_amount'),
    'max_open_trades': c.get('max_open_trades'),
    'strategy': c.get('strategy'),
    'timeframe': c.get('timeframe'),
}}, default=str))
" """, timeout=10)
    if out:
        try:
            stats["config"] = json.loads(out)
        except json.JSONDecodeError:
            stats["config"] = {"error": "parse failed"}

    # Query trade metrics — using close_profit (profit ratio, not percentage)
    sql_cmd = f"""
sqlite3 "{db_container_path}" "
SELECT
  COALESCE(COUNT(*), 0),
  COALESCE(SUM(CASE WHEN close_profit > 0 THEN 1 ELSE 0 END), 0),
  COALESCE(SUM(CASE WHEN close_profit <= 0 AND close_profit IS NOT NULL THEN 1 ELSE 0 END), 0),
  COALESCE(SUM(close_profit), 0.0),
  COALESCE(SUM(close_profit_abs), 0.0),
  COALESCE(AVG(CASE WHEN close_profit > 0 THEN close_profit ELSE NULL END), 0.0),
  COALESCE(AVG(CASE WHEN close_profit < 0 THEN close_profit ELSE NULL END), 0.0),
  COALESCE(MAX(close_profit), 0.0),
  COALESCE(MIN(close_profit), 0.0)
FROM trades
WHERE is_open = 0;
"
"""
    out, err = docker_exec(container, sql_cmd, timeout=15)
    if not out:
        stats["error"] = "sqlite query failed"
        stats["total_trades"] = 0
        return stats

    parts = parse_sqlite_row(out)
    if len(parts) < 9:
        stats["error"] = f"parse error: {out[:100]}"
        stats["total_trades"] = 0
        stats["wins"] = 0
        stats["losses"] = 0
        return stats

    total_trades = int(float(parts[0]))
    wins = int(float(parts[1]))
    losses = int(float(parts[2]))
    total_profit_ratio = float(parts[3])
    total_profit_abs = float(parts[4])
    avg_win = float(parts[5])
    avg_loss = float(parts[6])
    best_trade = float(parts[7])
    worst_trade = float(parts[8])

    stats["total_trades"] = total_trades
    stats["wins"] = wins
    stats["losses"] = losses
    stats["total_profit_ratio"] = round(total_profit_ratio, 4)
    stats["total_profit_pct"] = round(total_profit_ratio * 100, 2)
    stats["total_profit_usdt"] = round(total_profit_abs, 2) if total_profit_abs != 0 else round(total_profit_ratio * stats["config"].get("wallet", 1000), 2)
    stats["avg_win_pct"] = round(avg_win * 100, 2)
    stats["avg_loss_pct"] = round(avg_loss * 100, 2)
    stats["best_trade_pct"] = round(best_trade * 100, 2)
    stats["worst_trade_pct"] = round(worst_trade * 100, 2)
    stats["winrate"] = round(wins / total_trades * 100, 1) if total_trades > 0 else 0.0

    # Profit factor
    gross_profit = avg_win * wins if avg_win > 0 and wins > 0 else 0
    gross_loss = abs(avg_loss) * losses if avg_loss < 0 and losses > 0 else 0
    stats["profit_factor"] = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

    # Get open trades count
    open_out, _ = docker_exec(container,
        f'sqlite3 "{db_container_path}" "SELECT COUNT(*) FROM trades WHERE is_open = 1;"',
        timeout=5)
    stats["open_trades_count"] = int(open_out) if open_out else 0

    return stats


def get_open_trade_details(bot_name, bot_info):
    """Get currently open trades with details."""
    db_path = get_trade_db_path(bot_name, bot_info)
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        return []

    container = bot_name
    db_container_path = f"/freqtrade/user_data/{bot_info['db']}"

    out, _ = docker_exec(container, f"""
sqlite3 -json "{db_container_path}" "
SELECT
  pair,
  ROUND(close_profit * 100, 2) as profit_pct,
  ROUND(close_profit_abs, 2) as profit_usdt,
  ROUND(stake_amount, 2) as stake_amount,
  ROUND(amount, 4) as amount,
  strftime('%Y-%m-%d %H:%M', open_date) as open_date,
  ROUND(open_rate, 6) as open_rate,
  ROUND(stop_loss, 6) as stop_loss,
  CASE WHEN is_short THEN 'short' ELSE 'long' END as direction
FROM trades WHERE is_open = 1;
"
""", timeout=10)
    if out:
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return []
    return []


def get_pair_whitelist(bot_name, bot_info):
    """Get the pair whitelist from the bot's config."""
    config_path = "/freqtrade/config/config.json"
    if bot_name == "freqtrade-regime-hybrid":
        config_path = "/freqtrade/config/config_regime_hybrid_dryrun.json"

    out, _ = docker_exec(bot_name, f"""python3 -c "
import json
c = json.load(open('{config_path}'))
pairs = c.get('exchange', {{}}).get('pair_whitelist', [])
print(json.dumps(pairs))
" """, timeout=10)
    if out:
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return []
    return []


def get_container_uptime(container):
    """Get uptime string for a Docker container."""
    out, _ = run_cmd(f'docker inspect -f "{{{{.State.StartedAt}}}}" {container}', timeout=5)
    if out:
        started_str = out.strip('"').strip()
        try:
            started = datetime.fromisoformat(started_str.replace("Z", "+00:00"))
            uptime = datetime.now(timezone.utc) - started
            days = uptime.days
            hours = uptime.seconds // 3600
            mins = (uptime.seconds % 3600) // 60
            return f"{days}d {hours}h {mins}m"
        except (ValueError, TypeError):
            return started_str
    return "unknown"


def main():
    results = []
    summary = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total_bots": len(BOTS),
        "bots_ok": 0,
        "bots_error": 0,
        "total_trades_all": 0,
        "total_profit_all_usdt": 0.0,
        "open_trades_all": 0,
    }

    for name, bot_info in BOTS.items():
        entry = {
            "name": name,
            "port": bot_info["port"],
            "ip": get_container_ip(name),
            "uptime": get_container_uptime(name),
        }

        # Check container running
        status_out, _ = run_cmd(f'docker inspect -f "{{{{.State.Status}}}}" {name}', timeout=5)
        entry["container_status"] = status_out if status_out else "unknown"

        if status_out != "running":
            entry["status"] = "ERROR"
            entry["error"] = f"container not running ({status_out})"
            summary["bots_error"] += 1
            results.append(entry)
            continue

        # Trade stats
        stats = get_trade_stats(name, bot_info)
        entry["stats"] = stats

        if "error" in stats and stats.get("total_trades", -1) == 0:
            # No trades is OK for new/empty bots
            entry["status"] = "OK_EMPTY"
            summary["bots_ok"] += 1
        elif "error" in stats:
            entry["status"] = "WARNING"
            summary["bots_error"] += 1
        else:
            entry["status"] = "OK"
            summary["bots_ok"] += 1
            summary["total_trades_all"] += stats.get("total_trades", 0)
            summary["total_profit_all_usdt"] += stats.get("total_profit_usdt", 0)

        # Open trades detail
        if entry.get("stats", {}).get("open_trades_count", 0) > 0:
            entry["open_trades"] = get_open_trade_details(name, bot_info)
            summary["open_trades_all"] += len(entry["open_trades"])
        else:
            entry["open_trades"] = []

        # Pair whitelist
        entry["pair_whitelist"] = get_pair_whitelist(name, bot_info)

        # Primo signal check — optional, check if file exists
        entry["primo_signal_available"] = os.path.exists(
            "/home/hermes/primoagent/output/signals/primo_multi_signal_latest.json"
        )

        results.append(entry)

    output = {
        "summary": summary,
        "bots": results,
        "runtime_info": {
            "script": "freqtrade_monitor.py v2",
            "host": os.uname().nodename,
        }
    }

    print(json.dumps(output, indent=2, default=str))

    # Return exit code based on bot health
    if summary["bots_error"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
