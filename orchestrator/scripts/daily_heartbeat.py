#!/usr/bin/env python3
"""
Daily Heartbeat v4.6 — Structured Telegram health snapshot.
Always emits a compact, useful report so silence means scheduler trouble.
"""

import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone

BASE = "/home/hermes/projects/trading"
CRON_DIR = "/opt/data/profiles/orchestrator/cron"
DRAWDOWN_STATE = f"{BASE}/orchestrator/state/drawdown_state.json"
SIGNAL_PATH = f"{BASE}/ai-hedge-fund-crypto/output/hermes_signal.json"

UTC_NOW = datetime.now(timezone.utc)
TS = UTC_NOW.strftime("%Y-%m-%d %H:%M UTC")

CONFIG_PATHS = {
    "FreqForge": f"{BASE}/freqforge/config/config_freqforge_dryrun.json",
    "Canary": f"{BASE}/freqforge-canary/config/config_canary_dryrun.json",
    "Regime-Hybrid": f"{BASE}/freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json",
}


def run(cmd, timeout=20):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


def load_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None


def docker_running_summary():
    rc, out, _ = run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"])
    if rc != 0:
        return "CHECK FAILED", 0, []
    rows = [line for line in out.splitlines() if line.strip()]
    active = [row for row in rows if "Up" in row]
    return f"{len(active)} running", len(active), rows


def signal_summary():
    try:
        with open(SIGNAL_PATH) as fh:
            data = json.load(fh)
        age_min = (time.time() - os.path.getmtime(SIGNAL_PATH)) / 60
        pairs = data.get("pairs", {})
        accepted = []
        for pair, meta in pairs.items():
            action = str(meta.get("action", "hold")).upper()
            conf = meta.get("confidence", 0)
            if action in {"BUY", "SELL", "LONG", "SHORT"} and conf:
                accepted.append(f"{pair.split('/')[0]} {action} {conf:.2f}")
        risk_mode = data.get("global_risk_mode", "unknown")
        return {
            "age_min": age_min,
            "pair_count": len(pairs),
            "risk_mode": risk_mode,
            "accepted": accepted[:3],
        }
    except Exception as exc:
        return {"error": str(exc)}


def permissions_summary():
    rc, out, _ = run(["find", CRON_DIR, "-type", "f", "-user", "0", "-group", "0"], timeout=10)
    if rc != 0:
        return "CHECK FAILED"
    drift = len([line for line in out.splitlines() if line.strip()])
    return "CLEAN" if drift == 0 else f"{drift} drift file(s)"


def mem0_summary():
    try:
        rc, out, _ = run([
            "docker", "inspect", "hermes-mem0-local-api", "--format",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}"
        ], timeout=10)
        ips = [ip.strip() for ip in out.split() if ip.strip()]
        ip = next((x for x in ips if x.startswith("172.18.")), ips[0] if ips else "")
        if not ip:
            return "no IP"
        resp = urllib.request.urlopen(
            f"http://{ip}:8787/memories/all?user_id=luke-hermes&limit=5",
            timeout=10,
        )
        data = json.loads(resp.read())
        results = data.get("result", {}).get("results", [])
        return f"OK ({len(results)}+ visible)"
    except Exception as exc:
        return f"ERROR ({exc})"


def cron_summary():
    data = load_json(f"{CRON_DIR}/jobs.json")
    if data is None:
        return "CHECK FAILED"
    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    enabled = sum(1 for job in jobs if isinstance(job, dict) and job.get("enabled"))
    paused = sum(1 for job in jobs if isinstance(job, dict) and not job.get("enabled"))
    errors = sum(1 for job in jobs if isinstance(job, dict) and job.get("last_status") == "error")
    return f"{enabled} active | {paused} paused | {errors} error"


def max_open_summary():
    items = []
    for label, path in CONFIG_PATHS.items():
        cfg = load_json(path)
        if cfg is None:
            items.append(f"{label}=?")
            continue
        items.append(f"{label}={cfg.get('max_open_trades', '?')}")
    rc, out, _ = run([
        "docker", "exec", "freqai-rebel", "python3", "-c",
        "import json; c=json.load(open('/freqtrade/user_data/config.json')); print(c.get('max_open_trades','?'))"
    ], timeout=20)
    items.append(f"Rebel={out if rc == 0 and out else '?'}")
    return ", ".join(items)


def dry_run_summary():
    statuses = []
    ok = True
    for label, path in CONFIG_PATHS.items():
        cfg = load_json(path)
        state = bool(cfg and cfg.get("dry_run") is True)
        statuses.append(f"{label}={'T' if state else 'F'}")
        ok = ok and state
    rc, out, _ = run([
        "docker", "exec", "freqai-rebel", "python3", "-c",
        "import json; c=json.load(open('/freqtrade/user_data/config.json')); print(str(bool(c.get('dry_run') is True)))"
    ], timeout=20)
    rebel_ok = out.strip().lower() == "true"
    statuses.append(f"Rebel={'T' if rebel_ok else 'F'}")
    ok = ok and rebel_ok
    return ("OK" if ok else "CHECK"), ", ".join(statuses)


def profitability_summary():
    state = load_json(DRAWDOWN_STATE) or {}
    if not state:
        return "n/a", "drawdown_state missing"
    pnl = state.get("portfolio_pnl", 0.0)
    dd = state.get("drawdown_pct", 0.0)
    reachable = state.get("reachable_bots", 0)
    total = state.get("total_bots", 0)
    per_bot = state.get("per_bot", {})
    best = None
    worst = None
    for label, meta in per_bot.items():
        bot_pnl = float(meta.get("pnl", 0.0) or 0.0)
        if best is None or bot_pnl > best[1]:
            best = (label, bot_pnl)
        if worst is None or bot_pnl < worst[1]:
            worst = (label, bot_pnl)
    headline = f"Fleet {'+' if pnl >= 0 else ''}{pnl:.2f}U | DD {dd:.1f}% | Bots {reachable}/{total}"
    detail = ""
    if best and worst:
        detail = f"Best {best[0]} {'+' if best[1] >= 0 else ''}{best[1]:.2f}U | Worst {worst[0]} {'+' if worst[1] >= 0 else ''}{worst[1]:.2f}U"
    return headline, detail


def suggestions(sig, perm_text):
    tips = []
    if isinstance(sig, dict) and not sig.get("error") and sig.get("age_min", 999) >= 30:
        tips.append("Signal-Heartbeat prüfen")
    if perm_text != "CLEAN":
        tips.append("Cron-Permissions reparieren")
    if not tips:
        tips.append("Keine Sofortaktion nötig")
    tips.append("Fleet Report + DrawdownGuard normal weiterlaufen lassen")
    return tips[:2]


sig = signal_summary()
docker_text, _, _ = docker_running_summary()
perm_text = permissions_summary()
profit_head, profit_detail = profitability_summary()
dry_head, dry_detail = dry_run_summary()

lines = [
    f"🫀 Daily Heartbeat — {TS}",
    "",
    "PROFITABILITÄT",
    f"• {profit_head}",
    f"• {profit_detail or 'Keine Bot-PnL-Details verfügbar'}",
    "",
    "FLEET STATUS",
    f"• Docker: {docker_text}",
    f"• max_open_trades: {max_open_summary()}",
    "",
    "SIGNAL",
]
if sig.get("error"):
    lines.append(f"• ERROR: {sig['error']}")
else:
    freshness = "fresh" if sig["age_min"] < 30 else "STALE"
    accepted = ", ".join(sig["accepted"]) if sig["accepted"] else "keine starken Signale"
    lines.append(f"• {freshness} | {sig['age_min']:.0f} min | {sig['pair_count']} Paare | mode={sig['risk_mode']}")
    lines.append(f"• {accepted}")
lines += [
    "",
    "SAFETY",
    f"• dry_run: {dry_head} | {dry_detail}",
    f"• Permissions: {perm_text} | Cron: {cron_summary()}",
    f"• Mem0: {mem0_summary()}",
    "",
    "VORSCHLÄGE",
]
for tip in suggestions(sig, perm_text):
    lines.append(f"• {tip}")

print("\n".join(lines))
