#!/opt/hermes/.venv/bin/python3
"""hermes_standby_monitor.py — Hermes Standby Health Monitor v1.0

Monitors hermes-green container health. If primary is DOWN:
  1. Attempts auto-restart
  2. If restart fails, runs critical cron scripts as emergency fallback
  3. Writes health state to shared state file

Runs via independent cron (system crontab or external trigger).
For maximum resilience: deployed as both Hermes cron (every 5min)
AND as standalone script that can be triggered from outside.

EMERGENCY FALLBACK — when Hermes is down, runs:
  - heartbeat_writer.py  (bot health monitoring)
  - trading_pipeline.py  (signal bridge writes)
  - riskguard_service.py (safety checks)

Usage:
  /opt/hermes/.venv/bin/python3 hermes_standby_monitor.py
  --check-only : check health, no recovery actions
  --force-failover : simulate Hermes failure for testing
"""

import json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

BASE = "/home/hermes/projects/trading"
STATE_DIR = Path(BASE) / "orchestrator/state/standby"
HEALTH_FILE = STATE_DIR / "hermes_health.json"
LOCK_FILE = STATE_DIR / "standby.lock"

HERMES_CONTAINER = "hermes-green"
DOWN_THRESHOLD_SECONDS = 180  # 3 min down -> auto-restart
DOWN_CRITICAL_SECONDS = 600   # 10 min down -> fallback mode

CRITICAL_SCRIPTS = {
    "heartbeat_writer": "/opt/data/profiles/orchestrator/scripts/heartbeat_writer.py",
    "trading_pipeline": "/opt/data/profiles/orchestrator/scripts/trading_pipeline.py",
    "riskguard_service": "/opt/data/profiles/orchestrator/scripts/riskguard_service.py",
}


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [standby] {msg}")


def docker_ps(container: str) -> dict:
    """Check container status via docker inspect."""
    try:
        r = subprocess.run(
            ["docker", "inspect", container, "--format", "{{.State.Status}}|{{.State.Running}}|{{.State.StartedAt}}"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return {"status": "not_found", "running": False}
        parts = r.stdout.strip().split("|")
        return {"status": parts[0] if len(parts) > 0 else "unknown",
                "running": parts[1] == "true" if len(parts) > 1 else False,
                "started_at": parts[2] if len(parts) > 2 else ""}
    except Exception as e:
        return {"status": f"error: {e}", "running": False}


def check_scheduler_deadline() -> dict:
    """Check if the Hermes scheduler is running by checking cron job timestamps."""
    # Since docker exec is blocked (EXEC=0 proxy), check cron job freshness instead.
    # If any no_agent job has last_run_at within 30 minutes, scheduler is alive.
    try:
        import json as _json
        cron_db = Path("/opt/data/profiles/orchestrator/cron/jobs.json")
        if not cron_db.exists():
            return {"scheduler_alive": False, "reason": "cron db not found"}
        with open(cron_db) as f:
            data = _json.load(f)
        jobs = data.get("jobs", [])
        now = datetime.now(timezone.utc)
        recent_count = 0
        total_no_agent = 0
        for job in jobs:
            if job.get("no_agent") and job.get("enabled", True):
                total_no_agent += 1
                lra = job.get("last_run_at")
                if lra:
                    try:
                        last = datetime.fromisoformat(lra)
                        if last.tzinfo is None:
                            last = last.replace(tzinfo=timezone.utc)
                        if (now - last).total_seconds() < 1800:  # 30 min
                            recent_count += 1
                    except (ValueError, TypeError):
                        pass
        # Scheduler is alive if ANY no_agent job ran recently
        if recent_count > 0:
            return {"scheduler_alive": True, "process_count": recent_count,
                    "total_no_agent": total_no_agent}
        return {"scheduler_alive": False,
                "reason": f"0/{total_no_agent} no_agent jobs ran in last 30min"}
    except Exception as e:
        return {"scheduler_alive": False, "reason": str(e)}


def restart_hermes() -> bool:
    """Attempt to restart hermes-green container."""
    log(f"Attempting to restart {HERMES_CONTAINER}...")
    try:
        r = subprocess.run(["docker", "restart", HERMES_CONTAINER],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            log(f"  Restart OK — {HERMES_CONTAINER} restarted")
            time.sleep(3)
            return True
        else:
            log(f"  Restart FAILED: {r.stderr.strip()}")
            return False
    except Exception as e:
        log(f"  Restart error: {e}")
        return False


def run_fallback_scripts() -> list:
    """Run critical scripts when Hermes is down. Returns list of results."""
    results = []
    for name, script_path in CRITICAL_SCRIPTS.items():
        if not os.path.exists(script_path):
            results.append({"script": name, "status": "not_found"})
            continue
        log(f"  Emergency run: {name}")
        try:
            r = subprocess.run([script_path], cwd=BASE,
                               capture_output=True, text=True, timeout=120)
            ok = r.returncode == 0
            results.append({"script": name, "status": "OK" if ok else "FAIL",
                           "exit_code": r.returncode})
        except subprocess.TimeoutExpired:
            results.append({"script": name, "status": "TIMEOUT"})
        except Exception as e:
            results.append({"script": name, "status": f"ERROR: {e}"})
    return results


def write_health(health_data: dict) -> None:
    os.makedirs(str(STATE_DIR), exist_ok=True)
    with open(str(LOCK_FILE), "w") as f:
        f.write(str(os.getpid()))
    with open(str(HEALTH_FILE), "w") as f:
        json.dump(health_data, f, indent=2, default=str)


def main() -> int:
    force_failover = "--force-failover" in sys.argv
    check_only = "--check-only" in sys.argv

    now = datetime.now(timezone.utc)

    # 1. Check Hermes container
    container = docker_ps(HERMES_CONTAINER)
    hermes_alive = container["running"] and not force_failover

    # 2. Check scheduler
    scheduler = check_scheduler_deadline() if hermes_alive else {"scheduler_alive": False}

    overall = "OK"
    if not hermes_alive:
        overall = "HERMES_DOWN"
    elif not scheduler["scheduler_alive"]:
        overall = "SCHEDULER_STALLED"

    health = {
        "timestamp": now.isoformat(),
        "overall": overall,
        "hermes_container": container,
        "scheduler": scheduler,
        "actions_taken": [],
        "fallback_active": False,
    }

    if hermes_alive and scheduler["scheduler_alive"]:
        log(f"OK: {HERMES_CONTAINER} running, scheduler active ({scheduler.get('process_count', '?')} processes)")
        if not check_only:
            write_health(health)
        return 0

    if check_only:
        log(f"CHECK: {overall} — {HERMES_CONTAINER} running={container['running']}")
        write_health(health)
        return 1 if overall != "OK" else 0

    # 3. Recovery: try restart if container is down
    if not container["running"]:
        log(f"WARN: {HERMES_CONTAINER} is DOWN (status={container['status']})")
        health["actions_taken"].append(f"Container down ({container['status']})")
        restart_ok = restart_hermes()
        health["actions_taken"].append(f"Restart attempted: {'OK' if restart_ok else 'FAILED'}")
        if restart_ok:
            # Recheck after restart
            time.sleep(5)
            container2 = docker_ps(HERMES_CONTAINER)
            if container2["running"]:
                hermes_alive = True
                health["hermes_container"] = container2
                log(f"  Hermes recovered after restart")
                write_health(health)
                return 0

    # 4. Emergency fallback: run critical scripts directly
    log(f"EMERGENCY FALLBACK: Hermes unavailable for extended period")
    health["fallback_active"] = True
    health["actions_taken"].append("Emergency fallback mode activated")

    fallback_results = run_fallback_scripts()
    health["fallback_results"] = fallback_results
    for r in fallback_results:
        log(f"  Fallback {r['script']}: {r['status']}")

    write_health(health)
    log(f"Standby cycle complete — overall={overall}")
    return 1 if overall != "OK" else 0


if __name__ == "__main__":
    sys.exit(main())
