#!/usr/bin/env python3
"""
Hermes Auto-Restart Trigger v1.0 (L3-Operation, user-approved 2026-06-11)

Monitors the Hermes Heartbeat state. If heartbeat is >30min stale AND
the failure is structural (cron scheduler down or container down),
performs a controlled restart of the hermes-green container.

CRITICAL SAFETY: Must distinguish "heartbeat stale due to job error"
from "heartbeat stale due to scheduler down". Restarts ONLY when:
  1. Heartbeat file/age >30min stale
  2. AND hermes-green container is not in "Up" state OR cron scheduler
     shows no scheduled ticks
  3. AND no job-level errors (i.e., the error-alert job itself also stale
     or the system shows the scheduler is hung)

Before restart:
  - Writes HERMES_CHANGELOG.md entry
  - Sends Telegram alert: "🔄 AUTO-RESTART [UHRZEIT] — Heartbeat 30min ausgeblieben"

Runs every 10 minutes. no_agent cron with deliver=telegram:-3910189071.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

UTC_NOW = datetime.now(timezone.utc)
TS_HUMAN = UTC_NOW.strftime("%Y-%m-%d %H:%M UTC")

# Config
HEARTBEAT_AGE_LIMIT_MIN = 30      # max age of last successful heartbeat
DOCKER_CHECK_TIMEOUT = 10
HEARTBEAT_JOB_NAME = "Hermes Heartbeat (15min)"
CONTAINER_NAME = "hermes-green"
JOBS_PATH = Path("/opt/data/profiles/orchestrator/cron/jobs.json")
CHANGELOG_PATH = Path("/home/hermes/projects/trading/HERMES_CHANGELOG.md")
STATE_PATH = Path("/opt/data/profiles/orchestrator/state/hermes_restart_state.json")
COOLDOWN_FILE = Path("/opt/data/profiles/orchestrator/state/hermes_restart_cooldown.txt")
COOLDOWN_MINUTES = 60  # never restart more than once per hour


def get_heartbeat_state():
    """Get age of last Hermes Heartbeat (15min) cron run."""
    try:
        with open(JOBS_PATH) as f:
            data = json.load(f)
        for j in data.get("jobs", []):
            if j.get("name") == HEARTBEAT_JOB_NAME:
                last_run = j.get("last_run_at")
                last_status = j.get("last_status")
                if not last_run:
                    return None, "no_run_yet"
                # Parse ISO
                try:
                    ts = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age_min = (UTC_NOW - ts).total_seconds() / 60
                    return age_min, last_status
                except Exception:
                    return None, "parse_error"
        return None, "job_not_found"
    except Exception as e:
        return None, f"jobs_read_error: {e}"


def get_container_state():
    """Check if hermes-green container is running."""
    try:
        r = subprocess.run(
            ["docker", "inspect", CONTAINER_NAME, "--format",
             "{{.State.Status}} {{.State.Restarting}}"],
            capture_output=True, text=True, timeout=DOCKER_CHECK_TIMEOUT,
            env={**os.environ, "DOCKER_HOST": "unix:///var/run/docker.sock"},
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split()
            if len(parts) >= 1:
                return parts[0], (parts[1] == "true" if len(parts) > 1 else False)
        return None, None
    except Exception as e:
        return None, f"docker_error: {e}"


def check_cooldown():
    """Check if we're still in cooldown from last restart."""
    if not COOLDOWN_FILE.exists():
        return True  # no recent restart
    try:
        last_restart_ts = datetime.fromisoformat(
            COOLDOWN_FILE.read_text().strip().replace("Z", "+00:00")
        )
        if last_restart_ts.tzinfo is None:
            last_restart_ts = last_restart_ts.replace(tzinfo=timezone.utc)
        elapsed = (UTC_NOW - last_restart_ts).total_seconds() / 60
        return elapsed >= COOLDOWN_MINUTES
    except Exception:
        return True  # can't read cooldown, allow


def write_cooldown():
    """Record restart time."""
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        COOLDOWN_FILE.write_text(UTC_NOW.isoformat())
    except Exception:
        pass


def append_changelog_entry(reason):
    """Append auto-restart entry to CHANGELOG."""
    try:
        CHANGELOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CHANGELOG_PATH, "a") as f:
            f.write(f"\n### 🔄 AUTO-RESTART {TS_HUMAN}\n")
            f.write(f"- Trigger: {reason}\n")
            f.write(f"- Container: {CONTAINER_NAME}\n")
            f.write(f"- Action: docker restart {CONTAINER_NAME}\n")
    except Exception:
        pass


def perform_restart(reason):
    """Restart hermes-green container."""
    append_changelog_entry(reason)
    write_cooldown()
    try:
        r = subprocess.run(
            ["docker", "restart", CONTAINER_NAME],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "DOCKER_HOST": "unix:///var/run/docker.sock"},
        )
        if r.returncode == 0:
            return True, r.stdout.strip()
        return False, r.stderr.strip() or "exit_nonzero"
    except Exception as e:
        return False, str(e)


def main():
    # Quick state read
    heartbeat_age, heartbeat_status = get_heartbeat_state()
    container_status, is_restarting = get_container_state()

    if heartbeat_age is None:
        # Cannot determine — don't act on missing data
        return

    # Cooldown check
    if not check_cooldown():
        return  # silent — cooldown active

    # Decision matrix
    if heartbeat_age < HEARTBEAT_AGE_LIMIT_MIN:
        # Heartbeat fresh — all good
        return

    # Heartbeat is stale. Why?
    #   - If container is "Up" and not restarting, scheduler may be running
    #     but the job is failing → NOT a restart case
    #   - If container is "exited" / "dead" / restarting-loop → restart
    #   - If last_status is "ok" but age is high → scheduler hung, restart

    if container_status and container_status.lower() in ("exited", "dead", "paused", "stopped", "created"):
        reason = f"container={container_status}, heartbeat={heartbeat_age:.0f}min stale"
        print(f"🔄 AUTO-RESTART {TS_HUMAN} — Heartbeat {heartbeat_age:.0f}min ausgeblieben")
        print(f"❌ Grund: {reason}")
        ok, msg = perform_restart(reason)
        print(f"{'✅' if ok else '❌'} docker restart: {msg}")
        return

    if container_status and container_status.lower() in ("up", "running") and not is_restarting:
        # Container is running. Heartbeat is stale.
        # Distinguish: is the cron scheduler hung, or just one job errored?
        # Check: do OTHER jobs (e.g. the error-alert job) show recent activity?
        try:
            with open(JOBS_PATH) as f:
                data = json.load(f)
            recent_jobs = []
            cutoff = UTC_NOW - timedelta(minutes=30)
            for j in data.get("jobs", []):
                if not j.get("enabled"):
                    continue
                last_run = j.get("last_run_at")
                if not last_run:
                    continue
                try:
                    ts = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts >= cutoff and j.get("name") != HEARTBEAT_JOB_NAME:
                        recent_jobs.append(j.get("name"))
                except Exception:
                    pass
            if recent_jobs:
                # Other jobs ARE running → heartbeat job is failing specifically
                # DO NOT restart the whole scheduler for one job failure
                # The error-alert job will already be raising alerts
                return
        except Exception:
            pass

        # Container Up, no recent job activity → scheduler is HUNG
        reason = f"container=Up, scheduler hung (no jobs <30min), heartbeat={heartbeat_age:.0f}min"
        print(f"🔄 AUTO-RESTART {TS_HUMAN} — Heartbeat {heartbeat_age:.0f}min ausgeblieben")
        print(f"❌ Grund: {reason}")
        ok, msg = perform_restart(reason)
        print(f"{'✅' if ok else '❌'} docker restart: {msg}")
        return

    # Other states (restarting-loop, etc.) — log only, do not act
    print(f"⚠️ {TS_HUMAN} — Container status '{container_status}' (restarting={is_restarting})")
    print(f"📊 Heartbeat: {heartbeat_age:.0f}min stale — manual investigation needed")


if __name__ == "__main__":
    main()
