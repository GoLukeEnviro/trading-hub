#!/usr/bin/env python3
"""
Drawdown Guard v3 – Globaler Schutz-Layer + Alerting
Prueft Portfolio-Drawdown, Signal-Freshness, Fleet-Health.
Sendet Telegram-Alerts bei kritischen Zustaenden.

V3 Changes (2026-05-22 Cron Wiring Repair):
  - Docker-availability detection (socket + daemon reachability)
  - File-based health fallback when Docker is unavailable
  - No false "KRITISCH: Kein Bot erreichbar" when Docker socket absent
  - Signal freshness check unchanged (already file-based)
  - Log freshness as bot-liveness heuristic in no-Docker mode

KEIN Live-Trading. KEIN automatisches Pausieren ohne User-Approval.
Nur Advisory + Logging + Telegram Notification.
"""

import subprocess, json, os, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

from fleet_api_client import freqtrade_api_get

# ── Config ──────────────────────────────────────────────────────
PORTFOLIO_START = 1000.0
DRAWDOWN_LEVELS = {
    0.05: ("WARN",  "⚠️ DD Alert: {dd:.1f}%"),
    0.08: ("PAUSE", "🟠 DD PAUSE: {dd:.1f}% – Neue Entries manuell stoppen"),
    0.12: ("CLOSE", "🔴 DD CLOSE: {dd:.1f}% – Positionen manuell schliessen"),
    0.15: ("HALT",  "🚨 DD HALT: {dd:.1f}% – 7 Tage Pause empfohlen"),
}

SIGNAL_STALE_WARN_MIN = 30
SIGNAL_STALE_CRIT_MIN = 60
CONTAINER_RESTART_THRESHOLD_SEC = 300  # 5 min uptime = recently restarted
LOG_STALE_THRESHOLD_MIN = 30          # Bot log older than this = possibly down

BOTS = {
    "freqforge": {
        "container": "trading-freqtrade-freqforge-1",
        "port": 8080,  # internal container port (Docker network)
        "config_host": "/home/hermes/projects/trading/freqforge/config/config_freqforge_dryrun.json",
        "user": "freqforge",
        "password": "freqforge-local-only",
        "start_capital": 950.0,
        "log_path": "/home/hermes/projects/trading/freqtrade/logs/freqforge.log",
    },
    "canary": {
        "container": "trading-freqtrade-freqforge-canary-1",
        "port": 8080,
        "config_host": "/home/hermes/projects/trading/freqforge-canary/config/config_canary_dryrun.json",
        "user": "canary",
        "password": "I7S6ZNh2T7GE3BYjYUpvnA",
        "start_capital": 500.0,
        "log_path": "/home/hermes/projects/trading/freqtrade/logs/freqforge-canary.log",
    },
    "regime_hybrid": {
        "container": "trading-freqtrade-regime-hybrid-1",
        "port": 8080,
        "config_host": "/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json",
        "user": "research",
        "password": "RGHx9kLt4wPzNs8vBq2E",
        "start_capital": 1000.0,
        "log_path": "/home/hermes/projects/trading/freqtrade/logs/regime-hybrid.log",
    },
    # momentum: intentionally not deployed (removed 2026-05-24, was generating spam)
    "rebel": {
        "container": "trading-freqai-rebel-1",
        "port": 8080,
        "config_container": "/freqtrade/user_data/config.json",
        "user": "rebel",
        "password": "Vhaaz4y20joaAJQ71v3R7g",
        "start_capital": 1000.0,
        "log_path": "/home/hermes/projects/trading/freqtrade/logs/freqai-rebel.log",
    },
}

# Cache for Docker network IPs
_docker_ip_cache: dict[str, str | None] = {}


def _resolve_docker_ip(container: str) -> str | None:
    """Resolve container IP on trading_hermes-net via docker inspect."""
    if container in _docker_ip_cache:
        return _docker_ip_cache[container]
    try:
        r = subprocess.run(
            ["docker", "inspect", container, "--format",
             '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}}\n{{end}}'],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.strip().splitlines():
            parts = line.split("=", 1)
            if len(parts) == 2 and "hermes-net" in parts[0]:
                ip = parts[1].strip()
                _docker_ip_cache[container] = ip
                return ip
    except Exception:
        pass
    _docker_ip_cache[container] = None
    return None

STATE_FILE = Path("/home/hermes/projects/trading/orchestrator/state/drawdown_state.json")
LOG_FILE   = Path("/home/hermes/projects/trading/orchestrator/logs/drawdown_guard.log")
SIGNAL_FILE = Path("/home/hermes/projects/trading/freqtrade/shared/primo_signal_state.json")
ENV_FILE    = Path("/home/hermes/projects/trading/orchestrator/.env")
FLEET_HC    = Path("/home/hermes/projects/trading/orchestrator/scripts/fleet_healthcheck.py")

# ── Kill-switch auto-check config ─────────────────────────────────
KILL_SWITCH_TRIGGER = Path("/home/hermes/projects/trading/orchestrator/scripts/kill_switch_trigger.sh")
KILL_SWITCH_AUTO_CHECK_INTERVAL_MIN = 30  # How often to run auto-check
KILL_SWITCH_AUTO_CHECK_TRACKER = Path(
    "/home/hermes/projects/trading/orchestrator/state/kill_switch_auto_check_tracker.json"
)

# ── Previous state for change detection ─────────────────────────
PREV_STATE_FILE = Path("/home/hermes/projects/trading/orchestrator/state/drawdown_state_prev.json")

# ── Docker availability cache ───────────────────────────────────
_docker_available = None

def detect_docker() -> bool:
    """Check if Docker socket exists and daemon is reachable."""
    global _docker_available
    if _docker_available is not None:
        return _docker_available

    # Check socket exists
    if not Path("/var/run/docker.sock").is_socket():
        _docker_available = False
        return False

    # Check docker binary exists
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
        _docker_available = r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        _docker_available = False

    return _docker_available


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Telegram Alerting ───────────────────────────────────────────
def load_env():
    """Load .env file values into os.environ."""
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip()


def _resolve_bot_auth(bot_id: str, cfg: dict):
    """Resolve live API credentials from the bot's config file when possible.

    Host-mounted configs are preferred because they are the source of truth for
    the running dry-run fleet. Rebel uses a container-local config volume, so we
    read it via docker exec when needed.
    """
    config_host = cfg.get("config_host")
    if config_host and Path(config_host).exists():
        try:
            with open(config_host) as f:
                data = json.load(f)
            api = data.get("api_server", {})
            return {
                "port": int(api.get("listen_port", cfg.get("port", 0))),
                "user": str(api.get("username", cfg.get("user", ""))),
                "password": str(api.get("password", cfg.get("password", ""))),
            }
        except Exception as e:
            log(f"  {bot_id}: host config auth read failed: {e}")

    config_container = cfg.get("config_container")
    if config_container and detect_docker():
        try:
            py = (
                "import json; "
                f"c=json.load(open({config_container!r})); "
                "api=c.get('api_server',{}); "
                "print(json.dumps({'port': api.get('listen_port', 0), 'user': api.get('username',''), 'password': api.get('password','')}))"
            )
            r = subprocess.run(
                ["docker", "exec", cfg["container"], "python3", "-c", py],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0 and r.stdout.strip():
                api = json.loads(r.stdout)
                return {
                    "port": int(api.get("port", cfg.get("port", 0))),
                    "user": str(api.get("user", cfg.get("user", ""))),
                    "password": str(api.get("password", cfg.get("password", ""))),
                }
        except Exception as e:
            log(f"  {bot_id}: container config auth read failed: {e}")

    return {
        "port": int(cfg.get("port", 0)),
        "user": str(cfg.get("user", "")),
        "password": str(cfg.get("password", "")),
    }


def _get_telegram_creds():
    """Get Telegram token + chat_id."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token:
        b64 = os.environ.get("TELEGRAM_BOT_TOKEN_B64", "")
        if b64:
            import base64
            try:
                token = base64.b64decode(b64).decode()
            except Exception:
                pass

    if not token and detect_docker():
        try:
            r = subprocess.run(
                ["docker", "inspect", "hermes-green", "--format", "{{json .Config.Env}}"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:
                envs = json.loads(r.stdout)
                for e in envs:
                    if e.startswith("TELEGRAM_BOT_TOKEN="):
                        token = e.split("=", 1)[1]
                    if e.startswith("TELEGRAM_ALLOWED_USERS="):
                        chat_id = chat_id or e.split("=", 1)[1]
        except Exception:
            pass

    if not chat_id:
        chat_id = os.environ.get("TELEGRAM_HOME_CHANNEL", "").strip("'\"")

    return token, chat_id


def _report_keyboard(kind: str = "fleet"):
    if kind == "approval":
        return [
            [{"text": "Ja, ausführen", "callback_data": "confirm_execute"}],
            [{"text": "Nein, später", "callback_data": "defer_action"}],
            [{"text": "Fleet Report jetzt", "callback_data": "fleet_report_now"}],
        ]
    return [
        [{"text": "max_open_trades wiederherstellen", "callback_data": "restore_max_open_trades"}],
        [{"text": "Permissions jetzt fixen", "callback_data": "fix_permissions"}],
        [{"text": "Regime-Hybrid optimieren", "callback_data": "optimize_regime_hybrid"}],
        [{"text": "Canary SHORTs prüfen", "callback_data": "check_canary_shorts"}],
        [{"text": "Fleet Report jetzt", "callback_data": "fleet_report_now"}],
    ]


def send_telegram(message: str, inline_keyboard=None) -> bool:
    """Send Telegram message with optional inline keyboard."""
    token, chat_id = _get_telegram_creds()
    if not token or not chat_id:
        return False

    try:
        import json
        import urllib.request
        payload = {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
        if inline_keyboard:
            payload["reply_markup"] = json.dumps({"inline_keyboard": inline_keyboard}, ensure_ascii=False)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status == 200
    except Exception as e:
        log(f"  Telegram send failed: {e}")
        return False


# ── Log-based liveness check ────────────────────────────────────
def check_bot_log_freshness(log_path: str) -> tuple:
    """Check if bot log file was modified recently. Returns (is_fresh, age_minutes)."""
    lp = Path(log_path)
    if not lp.exists():
        return False, -1

    try:
        mtime = lp.stat().st_mtime
        age_min = (datetime.now().timestamp() - mtime) / 60
        return age_min < LOG_STALE_THRESHOLD_MIN, round(age_min, 1)
    except Exception:
        return False, -1


# ── Balance Query ───────────────────────────────────────────────
def get_balance(container, port, user, password):
    # 1. Try Docker network IP with Basic auth (bypasses EXEC=0 proxy)
    # Note: Docker network always uses internal container port 8080,
    # not the config's listen_port (which is the host-mapped port)
    docker_ip = _resolve_docker_ip(container)
    if docker_ip:
        try:
            import base64
            from urllib.request import Request, urlopen
            credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
            url = f"http://{docker_ip}:8080/api/v1/balance"
            req = Request(url, headers={"Authorization": f"Basic {credentials}"})
            resp = urlopen(req, timeout=5)
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                total = float(data.get("total", 0))
                if total > 0:
                    return total, True
        except Exception:
            pass

    # 2. Try docker exec (blocked by EXEC=0 but kept for compat)
    if detect_docker():
        try:
            r = subprocess.run(
                ["docker", "exec", container, "curl", "-s", "--retry", "2",
                 "--retry-delay", "2", "-u",
                 f"{user}:{password}", f"http://127.0.0.1:{port}/api/v1/balance"],
                capture_output=True, text=True, timeout=20
            )
            if r.returncode == 0 and r.stdout.strip():
                data = json.loads(r.stdout)
                return float(data.get("total", 0)), True
        except Exception as e:
            log(f"  {container}: docker exec query failed: {e}")

    return 0.0, False


# ── Container Uptime ────────────────────────────────────────────
def get_container_uptime_seconds(container: str) -> float:
    """Get container uptime in seconds. Returns -1 if Docker unavailable."""
    if not detect_docker():
        return -1.0

    try:
        r = subprocess.run(
            ["docker", "inspect", container, "--format", "{{.State.StartedAt}}"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0 and r.stdout.strip():
            started_str = r.stdout.strip()
            started_str = started_str.rstrip('Z').split('.')[0]
            started = datetime.fromisoformat(started_str).replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            return (now - started).total_seconds()
    except Exception:
        pass
    return -1.0


# ── Stale Signal Check ──────────────────────────────────────────
def check_signal_freshness():
    """Check primo_signal_state.json age. Returns (age_minutes, is_fresh)."""
    if not SIGNAL_FILE.exists():
        log("  Signal file not found: " + str(SIGNAL_FILE))
        return -1, False

    try:
        with open(SIGNAL_FILE) as f:
            data = json.load(f)
        ts_str = data.get("processed_at") or data.get("generated_at") or ""
        if not ts_str:
            mtime = SIGNAL_FILE.stat().st_mtime
            age_min = (datetime.now().timestamp() - mtime) / 60
        else:
            ts_str = ts_str.replace("Z", "").replace("+00:00", "")
            ts_str = ts_str.split("+")[0].split(".")[0]
            ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
            age_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60

        is_fresh = age_min < SIGNAL_STALE_WARN_MIN
        return round(age_min, 1), is_fresh
    except Exception as e:
        log(f"  Signal freshness check error: {e}")
        return -1, False


# ── Fleet Healthcheck ───────────────────────────────────────────
def run_fleet_healthcheck() -> dict:
    """Run fleet_healthcheck.py as subprocess, return parsed result."""
    if not FLEET_HC.exists():
        return {"status": "script_not_found"}

    try:
        r = subprocess.run(
            ["python3", str(FLEET_HC), "--json"],
            capture_output=True, text=True, timeout=60,
            cwd="/home/hermes/projects/trading"
        )
        if r.returncode == 0 and r.stdout.strip():
            for line in r.stdout.strip().split('\n'):
                line = line.strip()
                if line.startswith('{'):
                    return json.loads(line)
        return {"status": "completed", "raw_exit": r.returncode}
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Kill-switch auto-check ────────────────────────────────────────
def _load_kill_switch_check_tracker() -> dict:
    """Load the last auto-check timestamp from tracker file."""
    try:
        if KILL_SWITCH_AUTO_CHECK_TRACKER.exists():
            return json.loads(KILL_SWITCH_AUTO_CHECK_TRACKER.read_text())
    except Exception:
        pass
    return {"last_check_ts": 0.0}


def _save_kill_switch_check_tracker(ts: float) -> None:
    """Persist the last auto-check timestamp."""
    try:
        KILL_SWITCH_AUTO_CHECK_TRACKER.parent.mkdir(parents=True, exist_ok=True)
        KILL_SWITCH_AUTO_CHECK_TRACKER.write_text(
            json.dumps({"last_check_ts": ts}, indent=2)
        )
    except Exception as e:
        log(f"  kill-switch tracker write failed: {e}")


def _should_run_kill_switch_auto_check() -> bool:
    """Return True if enough time has elapsed since the last auto-check."""
    tracker = _load_kill_switch_check_tracker()
    last_ts = float(tracker.get("last_check_ts", 0.0))
    elapsed_min = (datetime.now().timestamp() - last_ts) / 60.0
    return elapsed_min >= KILL_SWITCH_AUTO_CHECK_INTERVAL_MIN


def run_kill_switch_auto_check() -> dict:
    """Call kill_switch_trigger.sh auto-check at configured intervals.

    Returns the subprocess result dict with keys:
      - called (bool): whether the check was actually invoked
      - returncode (int or None): exit code of the trigger script
      - stdout (str): captured stdout
      - stderr (str): captured stderr
    """
    if not _should_run_kill_switch_auto_check():
        return {"called": False, "returncode": None,
                "stdout": "", "stderr": "interval not elapsed"}

    if not KILL_SWITCH_TRIGGER.exists():
        log(f"  kill-switch trigger not found: {KILL_SWITCH_TRIGGER}")
        return {"called": False, "returncode": -1,
                "stdout": "", "stderr": "trigger script not found"}

    now_ts = datetime.now().timestamp()

    try:
        r = subprocess.run(
            [str(KILL_SWITCH_TRIGGER), "auto-check"],
            capture_output=True, text=True, timeout=60,
        )
        _save_kill_switch_check_tracker(now_ts)

        if r.returncode == 0:
            log(f"  kill-switch auto-check OK: {r.stdout.strip()}")
        else:
            log(f"  kill-switch auto-check FAIL (rc={r.returncode}): "
                f"{r.stderr.strip() or r.stdout.strip()}")

        return {
            "called": True,
            "returncode": r.returncode,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        log("  kill-switch auto-check TIMEOUT (>60s)")
        return {"called": True, "returncode": -1,
                "stdout": "", "stderr": "timeout"}
    except Exception as e:
        log(f"  kill-switch auto-check ERROR: {e}")
        return {"called": True, "returncode": -1,
                "stdout": "", "stderr": str(e)}


# ── Previous State Loading ──────────────────────────────────────
def load_prev_state() -> dict:
    try:
        if PREV_STATE_FILE.exists():
            with open(PREV_STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_prev_state(state: dict):
    try:
        with open(PREV_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


# ── Main Check ──────────────────────────────────────────────────
def check_drawdown():
    load_env()

    docker_ok = detect_docker()
    mode = "docker" if docker_ok else "file-based"

    log("=" * 55)
    log(f"DrawdownGuard v3 START [mode: {mode}]")

    alerts = []
    prev = load_prev_state()
    prev_reachable = prev.get("per_bot", {})

    total_current = 0.0
    total_start = 0.0
    bot_results = {}
    reachable = 0
    docker_unreachable_count = 0

    # ── Bot Balance + Reachability ──
    for bot_id, cfg in BOTS.items():
        auth = _resolve_bot_auth(bot_id, cfg)
        bal, ok = get_balance(cfg["container"], auth["port"],
                              auth["user"], auth["password"])

        # Container restart detection (only with Docker)
        uptime = get_container_uptime_seconds(cfg["container"])
        restarted = 0 < uptime < CONTAINER_RESTART_THRESHOLD_SEC if uptime > 0 else False

        if ok and bal > 0:
            total_current += bal
            total_start += cfg["start_capital"]
            bot_results[bot_id] = {
                "balance": round(bal, 2),
                "starting": cfg["start_capital"],
                "pnl": round(bal - cfg["start_capital"], 2),
                "reachable": True,
                "container_restarted": restarted,
            }
            reachable += 1
            log(f"  OK   {cfg['container']:35s} ${bal:.2f}"
                + ("  🔄 RESTARTED" if restarted else ""))

            if restarted:
                alerts.append(("restart", f"🔄 Container {cfg['container']} neugestartet (< 5min uptime)"))

            prev_bot = prev_reachable.get(bot_id, {})
            if prev_bot.get("reachable") is False:
                alerts.append(("recovery", f"✅ Bot {bot_id} wieder erreichbar"))

        else:
            # In file-based mode, check log freshness as liveness heuristic
            log_path = cfg.get("log_path", "")
            log_fresh, log_age = check_bot_log_freshness(log_path) if log_path else (False, -1)

            bot_results[bot_id] = {
                "balance": None,
                "reachable": False,
                "container_restarted": restarted,
                "log_fresh": log_fresh,
                "log_age_min": log_age,
            }

            if not docker_ok:
                # No Docker access — use log freshness as proxy
                if log_fresh:
                    bot_results[bot_id]["reachable"] = True
                    bot_results[bot_id]["reachability_source"] = "log_freshness"
                    log(f"  OK?  {cfg['container']:35s} (log fresh: {log_age}min, no Docker)")
                    docker_unreachable_count += 1
                else:
                    log(f"  WARN {cfg['container']:35s} (log stale: {log_age}min, no Docker)")
                    docker_unreachable_count += 1
            else:
                log(f"  FAIL {cfg['container']:35s} nicht erreichbar")
                prev_bot = prev_reachable.get(bot_id, {})
                if prev_bot.get("reachable") is not False:
                    alerts.append(("unreachable", f"❌ Bot {bot_id} ({cfg['container']}) nicht erreichbar"))

    # ── Critical check ──
    if reachable == 0 and docker_ok:
        # Docker IS available but no bots reachable = real problem
        log("KRITISCH: Kein Bot erreichbar!")
        send_telegram("🚨 TRADING FLEET: Kein einziger Bot erreichbar!", inline_keyboard=_report_keyboard("approval"))
    elif reachable == 0 and not docker_ok:
        # No Docker AND no REST access = can't determine, not a real "all down"
        log(f"NO_DOCKER: Kein Docker-Zugriff. {docker_unreachable_count}/{len(BOTS)} Bots nicht prüfbar.")
        # Do NOT send "KRITISCH" alert — this is an infrastructure issue, not a bot issue

    # ── Portfolio Drawdown (only if we have real balance data) ──
    if reachable > 0:
        portfolio_pnl = total_current - total_start
        drawdown = max(0, (total_start - total_current) / total_start) if total_start > 0 else 0
        dd_pct = drawdown * 100

        log(f"Portfolio: ${total_current:.2f} / ${total_start:.2f} start "
            f"(PnL: {'+' if portfolio_pnl>=0 else ''}${portfolio_pnl:.2f}, "
            f"DD: {dd_pct:.1f}%, Erreichbar: {reachable}/{len(BOTS)})")

        triggered_level = None
        triggered_action = "OK"
        for level, (action, template) in sorted(DRAWDOWN_LEVELS.items()):
            if drawdown >= level:
                triggered_level = level
                triggered_action = action

        if triggered_level:
            action, template = DRAWDOWN_LEVELS[triggered_level]
            msg = template.format(dd=dd_pct)
            log(f"  DRAWDOWN: {msg}")
            alerts.append(("drawdown", msg))
    else:
        portfolio_pnl = 0
        drawdown = 0
        dd_pct = 0
        triggered_level = None
        triggered_action = "NO_DATA"
        log(f"Portfolio: keine Balancedaten verfügbar [mode: {mode}]")

    # ── Signal Freshness ──
    signal_age, signal_fresh = check_signal_freshness()
    log(f"  Signal age: {signal_age:.1f} min ({'FRESH' if signal_fresh else 'STALE'})")

    if signal_age >= SIGNAL_STALE_CRIT_MIN:
        alerts.append(("stale_crit",
            f"📡 Signal stale seit {signal_age:.0f}min – Pipeline prüfen"))
        log(f"  CRITICAL: Signal stale ({signal_age:.1f} > {SIGNAL_STALE_CRIT_MIN}min)")
    elif signal_age >= SIGNAL_STALE_WARN_MIN:
        alerts.append(("stale_warn",
            f"⚠️ Signal aging: {signal_age:.0f}min – Watch"))
        log(f"  WARNING: Signal aging ({signal_age:.1f} >= {SIGNAL_STALE_WARN_MIN}min)")

    # ── Fleet Healthcheck ──
    log("  Fleet healthcheck running...")
    fleet_health = run_fleet_healthcheck()
    fleet_verdict = fleet_health.get("fleet_verdict", fleet_health.get("status", "unknown"))
    log(f"  Fleet verdict: {fleet_verdict}")

    # ── Send Telegram Alerts ──
    if alerts:
        report_text = format_drawdown_report(output={
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "mode": mode,
            "docker_available": docker_ok,
            "portfolio_current": round(total_current, 2),
            "portfolio_start": round(total_start, 2),
            "portfolio_pnl": round(portfolio_pnl, 2),
            "drawdown_pct": round(dd_pct, 2),
            "triggered_level": triggered_level,
            "action": triggered_action,
            "reachable_bots": reachable,
            "total_bots": len(BOTS),
            "per_bot": bot_results,
            "signal_age_minutes": signal_age,
            "signal_fresh": signal_fresh,
            "fleet_health": fleet_health,
            "alerts": [{"type": t, "text": m} for t, m in alerts],
        })
        if send_telegram(report_text, inline_keyboard=_report_keyboard("fleet")):
            log(f"  Telegram alert sent ({len(alerts)} alerts)")
        else:
            log(f"  Telegram not configured/alert failed ({len(alerts)} alerts queued)")

    # ── Write State ──
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "mode": mode,
        "docker_available": docker_ok,
        "portfolio_current": round(total_current, 2),
        "portfolio_start": round(total_start, 2),
        "portfolio_pnl": round(portfolio_pnl, 2),
        "drawdown_pct": round(dd_pct, 2),
        "triggered_level": triggered_level,
        "action": triggered_action,
        "reachable_bots": reachable,
        "total_bots": len(BOTS),
        "per_bot": bot_results,
        "signal_age_minutes": signal_age,
        "signal_fresh": signal_fresh,
        "fleet_health": fleet_health,
        "alerts": [{"type": t, "text": m} for t, m in alerts],
    }

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(output, f, indent=2)

    save_prev_state(output)

    # ── Kill-switch auto-check ──
    ks_result = run_kill_switch_auto_check()
    output["kill_switch_auto_check"] = ks_result
    log(f"  kill-switch auto-check called={ks_result['called']}")

    log(f"State -> {STATE_FILE}")
    log("DrawdownGuard v3 END")
    return output


def _safety_config_snapshots() -> tuple[str, str]:
    dry_parts = []
    mot_parts = []
    for bot_id, cfg in BOTS.items():
        auth = _resolve_bot_auth(bot_id, cfg)
        label = bot_id.replace('_', '-')
        config_host = cfg.get("config_host")
        if config_host and Path(config_host).exists():
            try:
                with open(config_host) as f:
                    data = json.load(f)
                dry_parts.append(f"{label}={'T' if data.get('dry_run') is True else 'F'}")
                mot_parts.append(f"{label}={data.get('max_open_trades', '?')}")
                continue
            except Exception:
                pass
        config_container = cfg.get("config_container")
        if config_container and detect_docker():
            try:
                py = (
                    "import json; c=json.load(open('/freqtrade/user_data/config.json')); "
                    "print(str(c.get('dry_run') is True)); print(c.get('max_open_trades','?'))"
                )
                r = subprocess.run(
                    ["docker", "exec", cfg["container"], "python3", "-c", py],
                    capture_output=True, text=True, timeout=15,
                )
                out = [line.strip() for line in r.stdout.splitlines() if line.strip()]
                dry_parts.append(f"{label}={'T' if out and out[0].lower() == 'true' else 'F'}")
                mot_parts.append(f"{label}={out[1] if len(out) > 1 else '?'}")
                continue
            except Exception:
                pass
        dry_parts.append(f"{label}=?")
        mot_parts.append(f"{label}=?")
    return ", ".join(dry_parts), ", ".join(mot_parts)


def format_drawdown_report(output: dict) -> str:
    alerts = output.get("alerts", [])
    per_bot = output.get("per_bot", {})
    hot_alerts = "; ".join(a.get("text", "") for a in alerts[:2]) if alerts else "Keine aktiven Alerts"
    dry_snapshot, mot_snapshot = _safety_config_snapshots()
    bot_lines = []
    for bot_id, meta in list(per_bot.items())[:4]:
        if meta.get("reachable") and meta.get("balance") is not None:
            bot_lines.append(
                f"• {bot_id}: {'+' if meta.get('pnl', 0) >= 0 else ''}{meta.get('pnl', 0):.2f}U | bal {meta.get('balance', 0):.2f}"
            )
        else:
            age = meta.get("log_age_min")
            age_txt = f" | log {age}min" if age not in (None, -1) else ""
            bot_lines.append(f"• {bot_id}: unreachable{age_txt}")

    lines = [
        f"📉 DrawdownGuard — {output['timestamp'][:16].replace('T', ' ')} UTC [{output.get('mode', 'unknown')}]",
        "",
        "PROFITABILITÄT",
        f"• Fleet {'+' if output.get('portfolio_pnl', 0) >= 0 else ''}{output.get('portfolio_pnl', 0):.2f}U | DD {output.get('drawdown_pct', 0):.1f}%",
        f"• Portfolio {output.get('portfolio_current', 0):.2f}/{output.get('portfolio_start', 0):.2f} | action={output.get('action', 'unknown')}",
        "",
        "FLEET STATUS",
        f"• Bots erreichbar: {output.get('reachable_bots', 0)}/{output.get('total_bots', 0)} | Docker={output.get('docker_available')}",
    ]
    lines.extend(bot_lines[:4])
    lines += [
        "",
        "SIGNAL",
        f"• {'fresh' if output.get('signal_fresh') else 'STALE'} | age {output.get('signal_age_minutes', -1):.1f} min",
        f"• fleet_health={output.get('fleet_health', {}).get('fleet_verdict', output.get('fleet_health', {}).get('status', 'unknown'))}",
        "",
        "SAFETY",
        f"• dry_run {dry_snapshot}",
        f"• max_open {mot_snapshot}",
        f"• {hot_alerts} | level={output.get('triggered_level') if output.get('triggered_level') is not None else 'none'}",
        "",
        "VORSCHLÄGE",
        f"• {'Drawdown-/Signal-Ursache sofort prüfen' if alerts else 'Keine Sofortaktion nötig'}",
        "• Fleet Report für Kontext gegenprüfen",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    result = check_drawdown()
    if result:
        if result.get("alerts") or not result.get("docker_available"):
            print(format_drawdown_report(result))
        # If no alerts and Docker available: silent (no stdout = no delivery)
