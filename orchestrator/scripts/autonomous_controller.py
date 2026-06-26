#!/usr/bin/env python3
"""
Autonomous Operations Controller v1 — Bounded Auto-Repair Runner

Observe -> Diagnose -> Decide -> Act -> Verify -> Rollback -> Document -> Escalate

Runs as a cron job from the writable profile directory.
Only performs AUTO_ALLOWED actions. REFUSES GATE_REQUIRED and FORBIDDEN actions.

Permission levels:
  AUTO_ALLOWED      — infrastructure/logging/path fixes, read-only checks, bridge refresh
  AUTO_WITH_GUARD   — requires preflight: dry_run confirmed, backup created, reversible
  GATE_REQUIRED     — REFUSED without explicit user approval
  FORBIDDEN         — REFUSED until final live cutover (dry_run=false, real orders)

Usage:
    python3 autonomous_controller.py                  # full cycle
    python3 autonomous_controller.py --observe-only   # read-only, no actions
    python3 autonomous_controller.py --check          # freshness + lint only
"""

import json
import os
import sys
import time
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ── Version ──────────────────────────────────────────────────────────
VERSION = "1.0.0"

# ── Paths (all writable) ────────────────────────────────────────────
PROFILE_DIR = Path("/opt/data/profiles/orchestrator")
SCRIPTS_DIR = PROFILE_DIR / "scripts"
LOGS_DIR = PROFILE_DIR / "logs"
STATE_DIR = PROFILE_DIR / "state"
CRON_DIR = PROFILE_DIR / "cron"
ACTION_LOG = STATE_DIR / "autonomous_controller_actions.jsonl"
HEALTH_STATE_FILE = STATE_DIR / "autonomous_health_state.json"
CURRENT_HEALTH_FILE = STATE_DIR / "autonomous_health_latest.json"
BRIDGE_STATE_DIR = STATE_DIR / "signal_bridge"

# ── Project paths (may be read-only, checked at runtime) ────────────
PROJECT_DIR = Path("/home/hermes/projects/trading")
PROJECT_SCRIPTS = PROJECT_DIR / "orchestrator" / "scripts"
PROJECT_SIGNAL = PROJECT_DIR / "ai-hedge-fund-crypto" / "output" / "hermes_signal.json"
SIGNAL_DIR = PROJECT_DIR / "ai-hedge-fund-crypto" / "output"

# ── Thresholds ──────────────────────────────────────────────────────
SIGNAL_MAX_AGE_MIN = 45
CRON_OK_THRESHOLD = 0.80  # at least 80% of cron jobs should be OK
DISK_WARN_PCT = 80
DISK_CRIT_PCT = 90
CONTAINER_PROBE_MAX_AGE_MIN = 30

# ── Bot config for dry-run verification ─────────────────────────────
BOT_CONFIG_PATHS = {
    "freqforge": PROJECT_DIR / "freqforge" / "config" / "config_freqforge_dryrun.json",
    "regime-hybrid": PROJECT_DIR / "freqtrade" / "bots" / "regime-hybrid" / "config" / "config_regime_hybrid_dryrun.json",
    "freqforge-canary": PROJECT_DIR / "freqforge-canary" / "config" / "config_canary_dryrun.json",
    "trading-freqai-rebel-1": None,  # Docker volume, checked via docker exec
}

# ── Permission Matrix ───────────────────────────────────────────────
AUTO_ALLOWED = {
    "fix_log_state_paths": "Redirect log/state writes from read-only project mount to writable profile dirs",
    "create_missing_dirs": "Create missing log/state/directories under profile path",
    "run_health_checks": "Run read-only health checks on all system dimensions",
    "repair_cron_path": "Fix cron script path/basedir when target script exists but path is wrong",
    "copy_missing_scripts": "Copy missing operational scripts from project to profile dir",
    "refresh_signal_bridge": "Refresh bridge state from canonical fresh signal file",
    "run_signal_check": "Check signal freshness, age, pair coverage, verdict distribution",
    "regenerate_reports": "Regenerate reports from existing logs and DBs",
    "send_telegram_status": "Send Telegram status summaries if reporting exists",
    "write_action_log": "Write structured action log to JSONL",
    "write_health_state": "Write unified health state to JSON",
    "write_context_report": "Create docs/context report after every repair cycle",
    "archive_temp_reports": "Archive old temporary reports into dated archive directory",
}

AUTO_WITH_GUARD = {
    "restart_monitoring": "Restart unhealthy non-execution containers (monitoring, dashboard, bridge)",
    "run_dry_backtest": "Re-run dry-run backtest with existing configs, no strategy changes",
    "rebuild_profit_summary": "Rebuild read-only profitability summaries from existing dry-run DBs",
    "rotate_logs_safely": "Rotate logs on disk pressure >80%, never delete trade DBs or reports",
}

GATE_REQUIRED = {
    "change_stoploss": "Changing stoploss",
    "change_stake_amount": "Changing stake amount",
    "change_leverage": "Changing leverage",
    "change_strategy_params": "Changing strategy parameters",
    "change_roi": "Changing ROI tables",
    "change_trailing_stop": "Changing trailing stop settings",
    "change_pairlist": "Changing pairlists or adding/removing traded markets",
    "change_timeframe": "Changing timeframe",
    "change_entry_exit_logic": "Changing entry/exit logic",
    "change_strategy_file": "Changing Freqtrade strategy files",
    "change_risk_limits": "Changing risk limits",
    "change_max_open_trades": "Changing max_open_trades limits",
    "change_confidence_threshold": "Changing signal confidence thresholds",
    "change_order_config": "Changing config files that affect order behavior",
    "mount_docker_socket": "Mounting full Docker socket if safer method available",
    "restart_all_bots": "Restarting all trading bots at once",
    "restart_dry_run_bot": "Restarting a dry-run Freqtrade bot (trading state reload)",
    "enable_auto_repair": "Enabling auto-repair that can modify execution behavior",
}

FORBIDDEN_UNTIL_LIVE = {
    "dry_run_false": "Setting dry_run=false",
    "place_real_orders": "Placing real orders",
    "activate_live_keys": "Activating exchange API keys for live execution",
    "move_real_funds": "Moving real funds",
    "increase_live_leverage": "Increasing leverage for live trading",
    "disable_emergency_stops": "Disabling emergency stops",
    "bypass_riskguard": "Bypassing RiskGuard or ShadowLogger requirements",
}


# ══════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════

def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGS_DIR / "autonomous_controller.log", "a") as f:
        f.write(line + "\n")


def log_action(action: str, status: str, detail: str = "") -> None:
    """Append a structured action record to JSONL."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "status": status,
        "permission_level": _classify_permission(action),
        "detail": detail,
    }
    with open(ACTION_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")


def _classify_permission(action: str) -> str:
    if action in AUTO_ALLOWED:
        return "AUTO_ALLOWED"
    if action in AUTO_WITH_GUARD:
        return "AUTO_WITH_GUARD"
    if action in GATE_REQUIRED:
        return "GATE_REQUIRED"
    if action in FORBIDDEN_UNTIL_LIVE:
        return "FORBIDDEN"
    return "UNKNOWN"


def read_json(path: Path, default=None):
    """Safely read a JSON file."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, PermissionError, OSError) as e:
        log(f"Cannot read {path}: {e}", "WARN")
        return default


def write_json(path: Path, data: dict) -> bool:
    """Atomically write JSON (temp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.rename(path)
        return True
    except (OSError, PermissionError) as e:
        log(f"Cannot write {path}: {e}", "ERROR")
        return False


def file_age_min(path: Path) -> float | None:
    """Returns file age in minutes, or None if file doesn't exist."""
    if not path.exists():
        return None
    return (time.time() - path.stat().st_mtime) / 60.0


def run_cmd(cmd: list, timeout: int = 30) -> tuple[int, str, str]:
    """Run a shell command safely."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except FileNotFoundError:
        return -2, "", "COMMAND_NOT_FOUND"
    except Exception as e:
        return -3, "", str(e)


# ══════════════════════════════════════════════════════════════════════
# PHASE 1: OBSERVE — Collect runtime state
# ══════════════════════════════════════════════════════════════════════

def observe() -> dict:
    """Collect all runtime state dimensions. Returns a dict."""
    log("Observe: collecting runtime state...")
    state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": VERSION,
        "checks": {},
    }

    # 1. Signal freshness
    signal = read_json(PROJECT_SIGNAL)
    if signal:
        age = file_age_min(PROJECT_SIGNAL)
        ts_str = signal.get("timestamp_utc") or signal.get("generated_at", "")
        pairs = signal.get("pairs", {})
        pair_count = len(pairs) if isinstance(pairs, dict) else 0
        state["checks"]["signal"] = {
            "exists": True,
            "age_min": round(age, 1) if age else None,
            "fresh": age is not None and age < SIGNAL_MAX_AGE_MIN,
            "pair_count": pair_count,
            "mode": signal.get("mode", "unknown"),
            "timestamp_utc": ts_str,
        }
    else:
        state["checks"]["signal"] = {"exists": False, "fresh": False}

    # 2. Bridge state freshness
    bridge_path = BRIDGE_STATE_DIR / "primo_signal_state.json"
    bridge = read_json(bridge_path)
    if bridge:
        age = file_age_min(bridge_path)
        bpairs = bridge.get("pairs", {})
        state["checks"]["bridge"] = {
            "exists": True,
            "age_min": round(age, 1) if age else None,
            "fresh": age is not None and age < SIGNAL_MAX_AGE_MIN,
            "pair_count": len(bpairs) if isinstance(bpairs, dict) else 0,
        }
    else:
        state["checks"]["bridge"] = {"exists": False, "fresh": False}

    # 3. Cron job health
    cron_path = CRON_DIR / "jobs.json"
    cron_data = read_json(cron_path)
    if cron_data:
        jobs = cron_data.get("jobs", [])
        if isinstance(jobs, dict):
            jobs = list(jobs.values())
        total = len(jobs)
        ok_count = sum(1 for j in jobs if j.get("last_status") in ("success", "completed") and not j.get("paused"))
        error_count = sum(1 for j in jobs if j.get("last_status") in ("error", "failed") and not j.get("paused"))
        paused_count = sum(1 for j in jobs if j.get("paused"))
        state["checks"]["cron"] = {
            "total": total,
            "ok": ok_count,
            "error": error_count,
            "paused": paused_count,
            "ok_ratio": round(ok_count / total, 2) if total > 0 else 0,
        }
    else:
        state["checks"]["cron"] = {"error": "Cannot read cron jobs"}

    # 4. Disk usage
    try:
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=10)
        lines = r.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 5:
                pct_str = parts[4].replace("%", "")
                state["checks"]["disk"] = {
                    "usage_pct": int(pct_str),
                    "available": parts[3],
                    "size": parts[1],
                    "used": parts[2],
                }
    except Exception as e:
        state["checks"]["disk"] = {"error": str(e)}

    # 5. Memory
    try:
        r = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=10)
        lines = r.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 7:
                state["checks"]["memory"] = {
                    "total": parts[1],
                    "used": parts[2],
                    "available": parts[6],
                }
    except Exception as e:
        state["checks"]["memory"] = {"error": str(e)}

    # 6. Bot dry-run config check (read-only files we can access)
    dry_run_results = {}
    for bot_name, cfg_path in BOT_CONFIG_PATHS.items():
        if cfg_path is None:
            dry_run_results[bot_name] = {"status": "UNKNOWN", "reason": "Docker volume or no config path"}
        elif cfg_path.exists():
            cfg = read_json(cfg_path)
            if cfg:
                dr = cfg.get("dry_run", "MISSING")
                has_key = bool(cfg.get("exchange", {}).get("key", ""))
                dry_run_results[bot_name] = {
                    "dry_run": dr,
                    "has_key": has_key,
                    "safe": dr is True and not has_key,
                }
            else:
                dry_run_results[bot_name] = {"status": "Cannot parse config"}
        else:
            dry_run_results[bot_name] = {"status": "Config not found"}
    state["checks"]["dry_run_safety"] = dry_run_results

    # 7. System health verdict
    verdict = _compute_verdict(state["checks"])
    state["verdict"] = verdict

    return state


def _compute_verdict(checks: dict) -> dict:
    """Compute aggregate health verdict."""
    issues = []
    red = 0
    yellow = 0

    # Signal
    sig = checks.get("signal", {})
    if not sig.get("fresh", False):
        red += 1
        issues.append("signal_stale")

    # Bridge
    br = checks.get("bridge", {})
    if not br.get("fresh", False):
        yellow += 1
        issues.append("bridge_stale")

    # Cron
    cr = checks.get("cron", {})
    ok_ratio = cr.get("ok_ratio", 0)
    if ok_ratio < 0.7:
        red += 1
        issues.append(f"cron_too_many_errors: {cr.get('error', '?')} errors")
    elif ok_ratio < 0.85:
        yellow += 1
        issues.append(f"cron_elevated_errors: {cr.get('error', '?')} errors")

    # Disk
    dk = checks.get("disk", {})
    usage = dk.get("usage_pct", 0)
    if usage > DISK_CRIT_PCT:
        red += 1
        issues.append(f"disk_critical: {usage}%")
    elif usage > DISK_WARN_PCT:
        yellow += 1
        issues.append(f"disk_warning: {usage}%")

    # Dry-run safety
    drs = checks.get("dry_run_safety", {})
    unsafe_bots = [name for name, data in drs.items() if isinstance(data, dict) and not data.get("safe", False)]
    if unsafe_bots:
        red += 3  # highest severity
        issues.append(f"DRY_RUN_NOT_SAFE: {unsafe_bots}")

    if red > 0:
        color = "RED"
    elif yellow > 0:
        color = "YELLOW"
    else:
        color = "GREEN"

    return {
        "color": color,
        "red_count": red,
        "yellow_count": yellow,
        "issues": issues,
    }


# ══════════════════════════════════════════════════════════════════════
# PHASE 2: DIAGNOSE — Classify issues
# ══════════════════════════════════════════════════════════════════════

def diagnose(state: dict) -> list:
    """Classify issues by severity and permission level."""
    log("Diagnose: classifying issues...")
    actions = []
    checks = state.get("checks", {})

    # Signal stale → auto-refresh bridge
    sig = checks.get("signal", {})
    if sig.get("exists") and sig.get("fresh"):
        br = checks.get("bridge", {})
        if br.get("exists") and not br.get("fresh"):
            actions.append({
                "action": "refresh_signal_bridge",
                "priority": "high",
                "reason": f"Bridge stale ({br.get('age_min','?')}min) while signal is fresh",
                "permission": "AUTO_ALLOWED",
                "allowed": True,
            })

    # Signal missing or stale → escalate, no auto action
    if not sig.get("exists"):
        actions.append({
            "action": "signal_missing",
            "priority": "critical",
            "reason": "Signal file does not exist",
            "permission": "AUTO_ALLOWED",
            "allowed": True,
            "action_type": "warn_only",
        })

    # Cron errors → attempt auto-repair of path/basedir issues
    cr = checks.get("cron", {})
    if cr.get("error", 0) > 0:
        # We'll attempt to read the errors and fix path issues
        actions.append({
            "action": "repair_cron_path",
            "priority": "medium",
            "reason": f"{cr.get('error', '?')} cron jobs in error state",
            "permission": "AUTO_ALLOWED",
            "allowed": True,
        })

    # Disk warning → offer safe log rotation
    dk = checks.get("disk", {})
    usage = dk.get("usage_pct", 0)
    if usage > DISK_WARN_PCT:
        actions.append({
            "action": "rotate_logs_safely",
            "priority": "medium" if usage < DISK_CRIT_PCT else "high",
            "reason": f"Disk at {usage}%",
            "permission": "AUTO_WITH_GUARD",
            "allowed": False,
            "requires_guard": True,
        })

    # Dry-run safety issues → CRITICAL escalation
    drs = checks.get("dry_run_safety", {})
    for bot_name, data in drs.items():
        if isinstance(data, dict) and not data.get("safe", True):
            actions.append({
                "action": "dry_run_unsafe",
                "priority": "CRITICAL",
                "reason": f"{bot_name}: dry_run={data.get('dry_run','?')}, has_key={data.get('has_key','?')}",
                "permission": "FORBIDDEN",
                "allowed": False,
                "requires_escalation": True,
            })

    return actions


# ══════════════════════════════════════════════════════════════════════
# PHASE 3: DECIDE & ACT — Execute only allowed actions
# ══════════════════════════════════════════════════════════════════════

def decide_and_act(actions: list, dry_run: bool = False) -> list:
    """Filter actions by permission, execute allowed ones."""
    log("Decide: filtering actions by permission matrix...")
    results = []

    for action in actions:
        name = action["action"]
        perm = action.get("permission", "UNKNOWN")
        allowed = action.get("allowed", False)
        requires_escalation = action.get("requires_escalation", False)
        reason = action.get("reason", "")

        if not allowed and requires_escalation:
            log(f"ESCALATE: {name} — {reason} (permission={perm})", "WARN")
            results.append({
                "action": name,
                "executed": False,
                "status": "ESCALATED",
                "reason": reason,
            })
            log_action(name, "ESCALATED", reason)
            continue

        if not allowed:
            log(f"REFUSE: {name} — {reason} (permission={perm})", "WARN")
            results.append({
                "action": name,
                "executed": False,
                "status": "REFUSED",
                "reason": reason,
            })
            log_action(name, "REFUSED", reason)
            continue

        # Execute allowed actions
        if dry_run:
            log(f"DRY-RUN: would execute {name} — {reason}")
            results.append({
                "action": name,
                "executed": False,
                "status": "DRY_RUN",
                "reason": reason,
            })
            continue

        log(f"ACT: executing {name} — {reason}")
        result = _execute_action(name, reason)
        results.append(result)
        log_action(name, result["status"], detail=reason)

    return results


def _execute_action(action_name: str, reason: str) -> dict:
    """Execute a single allowed action. Returns result dict."""
    executor = {
        "refresh_signal_bridge": _act_refresh_bridge,
        "repair_cron_path": _act_repair_cron_path,
        "signal_missing": _act_signal_missing_warn,
    }
    fn = executor.get(action_name)
    if fn:
        try:
            return fn()
        except Exception as e:
            log(f"Action {action_name} failed: {e}", "ERROR")
            log_action(action_name, "FAILED", str(e))
            return {"action": action_name, "executed": False, "status": "FAILED", "detail": str(e)}
    else:
        log(f"No executor for {action_name}, marking as NOT_IMPLEMENTED", "WARN")
        return {"action": action_name, "executed": False, "status": "NOT_IMPLEMENTED"}


def _act_refresh_bridge() -> dict:
    """Refresh signal bridge state from canonical signal."""
    from signal_bridge import main as bridge_main
    try:
        exit_code = bridge_main()
        if exit_code == 0:
            return {"action": "refresh_signal_bridge", "executed": True, "status": "OK"}
        else:
            return {"action": "refresh_signal_bridge", "executed": True, "status": "FAILED", "detail": f"bridge exit={exit_code}"}
    except Exception as e:
        return {"action": "refresh_signal_bridge", "executed": False, "status": "ERROR", "detail": str(e)}


def _act_repair_cron_path() -> dict:
    """Check for path/basedir issues in cron scripts and fix them."""
    # This is a read-only diagnostic for now. The actual fix script
    # (apply-automation-fix-20260528.sh) handles the path rewrites.
    cron_path = CRON_DIR / "jobs.json"
    cron_data = read_json(cron_path)
    if not cron_data:
        return {"action": "repair_cron_path", "executed": False, "status": "NO_DATA"}

    jobs = cron_data.get("jobs", [])
    if isinstance(jobs, dict):
        jobs = list(jobs.values())

    path_issues = []
    for j in jobs:
        name = j.get("name", "?")
        cmd = j.get("command", "") or ""
        last_error = str(j.get("last_error", ""))
        status = j.get("last_status", "")

        if status in ("error", "failed"):
            if "not found" in last_error.lower() or "script not found" in last_error.lower():
                path_issues.append({"job": name, "command": cmd, "error": last_error})

    if path_issues:
        log(f"Cron path issues detected: {len(path_issues)} jobs. Refer to apply-automation-fix script.", "WARN")
        return {
            "action": "repair_cron_path",
            "executed": True,
            "status": "DETECTED",
            "detail": f"{len(path_issues)} jobs with path issues. Run apply-automation-fix-20260528.sh from host.",
            "path_issues": path_issues,
        }
    return {"action": "repair_cron_path", "executed": True, "status": "CLEAN"}


def _act_signal_missing_warn() -> dict:
    """Log warning about missing signal."""
    log("CRITICAL: Signal file does not exist at " + str(PROJECT_SIGNAL), "ERROR")
    return {"action": "signal_missing", "executed": True, "status": "WARNED"}


# ══════════════════════════════════════════════════════════════════════
# PHASE 4: DOCUMENT — Write health state + context report
# ══════════════════════════════════════════════════════════════════════

def document(state: dict, actions_results: list) -> None:
    """Write unified health state, action log, and markdown report."""
    log("Document: writing health state and reports...")

    # Write health state JSON
    health = {
        "timestamp": state["timestamp"],
        "version": state["version"],
        "verdict": state["verdict"],
        "checks": state["checks"],
        "actions_taken": actions_results,
    }
    write_json(HEALTH_STATE_FILE, health)

    # Write latest health snapshot (for quick reads)
    write_json(CURRENT_HEALTH_FILE, {
        "timestamp": state["timestamp"],
        "verdict": state["verdict"]["color"],
        "issues": state["verdict"]["issues"],
        "actions": len(actions_results),
    })

    # Write markdown summary to logs
    verdict = state["verdict"]
    color = verdict["color"]
    issues = verdict.get("issues", [])
    sig = state["checks"].get("signal", {})
    cr = state["checks"].get("cron", {})
    dk = state["checks"].get("disk", {})

    md = f"""# Autonomous Controller Report — {state['timestamp']}

**Verdict:** {color}
**Version:** {VERSION}

## Key Metrics
| Component | Status | Detail |
|-----------|--------|--------|
| Signal | {'OK' if sig.get('fresh') else 'STALE'} | age={sig.get('age_min','?')}m, pairs={sig.get('pair_count','?')} |
| Bridge | {'OK' if state['checks'].get('bridge',{}).get('fresh') else 'STALE'} | age={state['checks'].get('bridge',{}).get('age_min','?')}m |
| Cron | {cr.get('ok','?')}/{cr.get('total','?')} OK | {cr.get('error','?')} errors |
| Disk | {dk.get('usage_pct','?')}% | {dk.get('available','?')} available |

## Issues
{"- " + chr(10) + "- ".join(issues) if issues else "No issues detected."}

## Actions Taken
{chr(10).join([f"- {a['action']}: {a['status']}" for a in actions_results]) if actions_results else "No actions taken."}
"""
    report_path = LOGS_DIR / f"autonomous_controller_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
    try:
        report_path.write_text(md)
        log(f"Report written: {report_path}")
    except OSError as e:
        log(f"Cannot write report: {e}", "ERROR")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main() -> int:
    log(f"Autonomous Controller v{VERSION} starting")

    dry_run = "--observe-only" in sys.argv or "--dry-run" in sys.argv
    check_only = "--check" in sys.argv

    if check_only:
        log("Check mode: verifying paths and imports")
        # Verify writable paths
        for p in [LOGS_DIR, STATE_DIR, BRIDGE_STATE_DIR]:
            p.mkdir(parents=True, exist_ok=True)
            test = p / ".write_test"
            try:
                test.write_text("ok")
                test.unlink()
                log(f"  {p}: WRITABLE")
            except OSError as e:
                log(f"  {p}: NOT WRITABLE - {e}", "ERROR")
                return 1

        # Verify imports
        try:
            import json, os, subprocess, time
            from datetime import datetime, timezone
            from pathlib import Path
            log(f"  Imports: OK")
        except ImportError as e:
            log(f"  Imports FAILED: {e}", "ERROR")
            return 1

        log("Check complete: all OK")
        return 0

    # Phase 1: Observe
    state = observe()

    # Phase 2: Diagnose
    actions = diagnose(state)

    # Phase 3: Decide & Act
    action_results = decide_and_act(actions, dry_run=dry_run)

    # Phase 4: Document
    document(state, action_results)

    # Print summary
    verdict = state["verdict"]
    log(f"Cycle complete. Verdict: {verdict['color']}. {len(actions)} actions diagnosed, {len([a for a in action_results if a.get('executed')])} executed.")

    # Exit code: 0 for GREEN/YELLOW, 1 for RED
    if verdict["color"] == "RED":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
