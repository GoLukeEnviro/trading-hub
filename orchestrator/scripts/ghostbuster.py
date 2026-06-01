#!/usr/bin/env python3
"""
GhostBuster v2.0 — Detection & Alert Watchdog
===============================================
Runs as Hermes no_agent cron job (every 2h).

v2 philosophy: DETECT and REPORT. Never auto-destroy.
  - Scans for ghost patterns (HONCHO refs, stale containers, permission drift).
  - Reports findings via Telegram (or silent if clean).
  - Only safe, read-only actions: permission fix on cron dir files.
  - NO docker prune. NO job removal. NO script disabling.
  - Daily heartbeat: one "ALL GREEN" report at ~06:00 UTC (08:00 CEST).

Safe actions (only these):
  - Permission drift fix: chgrp 10000 + chmod 0640 on root:root files in cron dir.
    (This is the same fix trading-guardian does every 5min — just redundant safety.)

Dangerous actions REMOVED from v1:
  - docker system prune → REMOVED (can kill quarantined bots)
  - jobs.json entry removal → REMOVED (false positive risk)
  - script file renaming → REMOVED (already broke .bak file)
  - docker rm container → REMOVED (can kill intentional stopped containers)
"""

import json, os, sys, time, subprocess, glob, pwd, grp, tempfile
from datetime import datetime, timezone, timedelta

# ── Configuration ──────────────────────────────────────────────────
BASE_DIR = "/home/hermes/projects/trading"
CRON_DIR = "/opt/data/profiles/orchestrator/cron"
SCRIPTS_DIR = "/opt/data/profiles/orchestrator/scripts"
OUTPUT_DIR = "/opt/data/profiles/orchestrator/cron/output"
LOG_DIR = f"{BASE_DIR}/orchestrator/logs"
LOG_PATH = f"{LOG_DIR}/ghostbuster.log"
LOG_FILE_MODE = 0o664
LOG_DIR_MODE = 0o2775
SAFE_DETECTION_ONLY_MODE = True

# Honcho decommissioned 2026-05-14 — patterns removed to avoid false positives
# against legitimate jobs whose prompts mention "Honcho ist decommissioned".
GHOST_PATTERNS = []
GHOST_CONTAINER_PATTERNS = ["watchdog-old"]

JOBS_JSON = f"{CRON_DIR}/jobs.json"
MEM0_WATCHDOG_SCRIPT = f"{SCRIPTS_DIR}/mem0_watchdog.py"

# Daily heartbeat window (UTC): emit "ALL GREEN" once between 06:00-08:00 UTC
HEARTBEAT_WINDOW_START = 6   # 06:00 UTC = 08:00 CEST
HEARTBEAT_WINDOW_END = 8     # 08:00 UTC = 10:00 CEST
HEARTBEAT_FLAG_FILE = f"{BASE_DIR}/orchestrator/state/ghostbuster_heartbeat_sent"

now_utc = datetime.now(timezone.utc)
ts = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
date_str = now_utc.strftime("%Y-%m-%d")


def _lookup_hermes_ids():
    try:
        uid = pwd.getpwnam("hermes").pw_uid
    except KeyError:
        uid = 10000
    try:
        gid = grp.getgrnam("hermes").gr_gid
    except KeyError:
        gid = 10000
    return uid, gid


HERMES_UID, HERMES_GID = _lookup_hermes_ids()


def secure_path_permissions(path, *, mode, ensure_file=False, ensure_dir=False):
    if ensure_dir:
        os.makedirs(path, exist_ok=True)
    elif ensure_file:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            fd = os.open(path, os.O_CREAT | os.O_WRONLY, mode)
            os.close(fd)
    try:
        os.chown(path, HERMES_UID, HERMES_GID)
    except PermissionError:
        pass
    os.chmod(path, mode)


def atomic_append_log(log_path, lines):
    secure_path_permissions(LOG_DIR, mode=LOG_DIR_MODE, ensure_dir=True)
    secure_path_permissions(log_path, mode=LOG_FILE_MODE, ensure_file=True)

    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(log_path)}.",
        dir=os.path.dirname(log_path),
    )
    try:
        os.fchmod(fd, LOG_FILE_MODE)
        try:
            os.fchown(fd, HERMES_UID, HERMES_GID)
        except PermissionError:
            pass
        with os.fdopen(fd, "w") as tmp:
            try:
                with open(log_path, "r") as current:
                    tmp.write(current.read())
            except FileNotFoundError:
                pass
            for line in lines:
                tmp.write(line)
        os.replace(tmp_path, log_path)
        secure_path_permissions(log_path, mode=LOG_FILE_MODE, ensure_file=True)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


class GhostBuster:
    def __init__(self):
        self.findings = []       # all detected issues
        self.warnings = []       # non-critical notes
        self.fixed = []          # only permission fixes (safe)
        self.actions = []        # log entries

    def log(self, msg):
        self.actions.append(f"[{ts}] {msg}")

    # ── Phase 1: Detection (all read-only) ────────────────────────

    def scan_jobs_json(self):
        """Scan jobs.json for HONCHO-related entries."""
        if not os.path.exists(JOBS_JSON):
            self.warnings.append("jobs.json not found")
            return
        try:
            with open(JOBS_JSON) as f:
                data = json.load(f)
            jobs = data.get("jobs", data) if isinstance(data, dict) else data
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                dump = json.dumps(job).lower()
                for pattern in GHOST_PATTERNS:
                    if pattern.lower() in dump:
                        self.findings.append({
                            "type": "GHOST_CRON_JOB",
                            "source": f"jobs.json:{job.get('name','?')}",
                            "detail": f"id={job.get('job_id','?')} pattern={pattern}",
                            "action": "MANUAL_REVIEW: remove via 'hermes cron' or agent",
                        })
                        break
        except Exception as e:
            self.warnings.append(f"jobs.json parse error: {e}")

    def scan_cron_outputs(self):
        """Scan recent cron output files for ghost patterns."""
        if not os.path.exists(OUTPUT_DIR):
            return
        cutoff = time.time() - (12 * 3600)
        for job_dir in glob.glob(f"{OUTPUT_DIR}/*/"):
            for outfile in glob.glob(f"{job_dir}*.md"):
                try:
                    if os.path.getmtime(outfile) < cutoff:
                        continue
                    with open(outfile) as f:
                        content = f.read(10000).lower()
                    for pattern in GHOST_PATTERNS[:3]:
                        if pattern.lower() in content:
                            self.findings.append({
                                "type": "GHOST_CRON_OUTPUT",
                                "source": os.path.basename(outfile),
                                "detail": f"pattern={pattern}",
                                "action": "INFO: old output, will age out naturally",
                            })
                            break
                except Exception:
                    pass

    def scan_docker_containers(self):
        """Check for exited ghost containers."""
        try:
            r = subprocess.run(
                ["docker", "ps", "-a", "--filter", "status=exited",
                 "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
                capture_output=True, text=True, timeout=15
            )
            for line in r.stdout.strip().splitlines():
                if not line.strip():
                    continue
                name = line.split("\t")[0].lower()
                for pattern in GHOST_CONTAINER_PATTERNS:
                    if pattern.lower() in name:
                        self.findings.append({
                            "type": "GHOST_CONTAINER",
                            "source": name,
                            "detail": line.replace("\t", " | "),
                            "action": "MANUAL_REVIEW: 'docker rm' if confirmed ghost",
                        })
                        break
        except Exception as e:
            self.warnings.append(f"Docker scan failed: {e}")

    def scan_scripts_dir(self):
        """Scan for active (non-backup/non-disabled) honcho scripts."""
        for f in glob.glob(f"{SCRIPTS_DIR}/honcho*"):
            basename = os.path.basename(f)
            if ".bak" in basename or basename.endswith(".disabled"):
                continue
            self.findings.append({
                "type": "GHOST_SCRIPT",
                "source": basename,
                "detail": f"path={f}",
                "action": "MANUAL_REVIEW: rename to .disabled if confirmed ghost",
            })

    def check_permission_drift(self):
        """Check cron dir for root:root permission drift. REPORT-ONLY.
        Actual repair is handled by trading-guardian container (every 5 min)
        with explicit per-file mode:group contracts. This method must NOT
        silently modify ownership — it would compete with the guardian
        and create hidden divergence.
        """
        if not os.path.exists(CRON_DIR):
            return
        try:
            r = subprocess.run(
                ["find", CRON_DIR, "-type", "f", "-user", "0", "-group", "0"],
                capture_output=True, text=True, timeout=10
            )
            drift_files = [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]
            if drift_files:
                drift_names = [os.path.basename(f) for f in drift_files]
                self.warnings.append(
                    f"PERM_DRIFT ({len(drift_files)} root:root files — guardian will auto-fix): "
                    + ", ".join(drift_names[:5])
                )
        except Exception as e:
            self.warnings.append(f"Permission scan failed: {e}")

    def check_mem0_watchdog_health(self):
        """Verify mem0-watchdog cron job and script exist."""
        if not os.path.exists(MEM0_WATCHDOG_SCRIPT):
            self.findings.append({
                "type": "MISSING_COMPONENT",
                "source": "mem0_watchdog.py",
                "detail": f"Script not found at {MEM0_WATCHDOG_SCRIPT}",
                "action": "MANUAL: restore from project scripts dir",
            })
        if os.path.exists(JOBS_JSON):
            try:
                with open(JOBS_JSON) as f:
                    data = json.load(f)
                jobs = data.get("jobs", data) if isinstance(data, dict) else data
                mem0_job = None
                for j in jobs:
                    if isinstance(j, dict) and j.get("name") == "mem0-watchdog":
                        mem0_job = j
                        break
                if not mem0_job:
                    self.findings.append({
                        "type": "MISSING_COMPONENT",
                        "source": "mem0-watchdog cron job",
                        "detail": "No mem0-watchdog entry in jobs.json",
                        "action": "MANUAL: recreate cron job",
                    })
                elif not mem0_job.get("enabled", False):
                    self.findings.append({
                        "type": "DISABLED_COMPONENT",
                        "source": "mem0-watchdog",
                        "detail": "Cron job exists but is disabled",
                        "action": "MANUAL: re-enable if intentional",
                    })
            except Exception:
                pass

    def check_docker_disk(self):
        """Report Docker disk usage (read-only, no prune)."""
        try:
            r = subprocess.run(
                ["docker", "system", "df", "--format", "{{.Type}}\t{{.Size}}\t{{.Reclaimable}}"],
                capture_output=True, text=True, timeout=15
            )
            for line in r.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 3 and parts[2].strip() != "0B":
                    self.log(f"DOCKER DISK: {line.replace(chr(9), ' | ')}")
        except Exception:
            pass

    # ── Phase 2: Heartbeat Logic ──────────────────────────────────

    def is_heartbeat_window(self):
        h = now_utc.hour
        if HEARTBEAT_WINDOW_START <= h < HEARTBEAT_WINDOW_END:
            if os.path.exists(HEARTBEAT_FLAG_FILE):
                try:
                    with open(HEARTBEAT_FLAG_FILE) as f:
                        if f.read().strip() == date_str:
                            return False
                except Exception:
                    pass
            return True
        return False

    def mark_heartbeat_sent(self):
        os.makedirs(os.path.dirname(HEARTBEAT_FLAG_FILE), exist_ok=True)
        with open(HEARTBEAT_FLAG_FILE, "w") as f:
            f.write(date_str)

    # ── Phase 3: Report ───────────────────────────────────────────

    def generate_report(self):
        is_heartbeat = self.is_heartbeat_window()
        has_issues = bool(self.findings) or bool(self.warnings)

        if not is_heartbeat and not has_issues:
            return ""  # Silent = no Telegram delivery

        try:
            r = subprocess.run(
                ["find", CRON_DIR, "-type", "f", "-user", "0", "-group", "0"],
                capture_output=True, text=True, timeout=5
            )
            drift = len([l for l in r.stdout.strip().splitlines() if l.strip()])
            perm_status = "CLEAN" if drift == 0 else f"{drift} drift files"
        except Exception:
            perm_status = "check_failed"

        status = "ALERT" if has_issues else "OK"
        next_run = (now_utc + timedelta(hours=2)).strftime("%H:%M UTC")
        top_findings = self.findings[:2]
        top_warnings = self.warnings[:2]
        top_fixes = self.fixed[:2]

        lines = [
            f"👻 GhostBuster — {now_utc.strftime('%Y-%m-%d %H:%M UTC')} | {status}",
            "",
            "PROFITABILITÄT",
            "• n/a — Detection-only watchdog",
            "",
            "FLEET STATUS",
            f"• Findings={len(self.findings)} | Warnings={len(self.warnings)} | Fixes={len(self.fixed)}",
            f"• mem0-watchdog script: {'OK' if os.path.exists(MEM0_WATCHDOG_SCRIPT) else 'MISSING'}",
            "",
            "SIGNAL",
            f"• Next run ~{next_run}",
            f"• Heartbeat window={'YES' if is_heartbeat else 'NO'} | mode=detection-only",
            "",
            "SAFETY",
            f"• Cron permissions: {perm_status}",
            f"• {'; '.join(f['type']+': '+f['source'] for f in top_findings) if top_findings else 'Keine Ghost-Funde'}",
            f"• {'; '.join(top_warnings) if top_warnings else ('Fixes: ' + '; '.join(top_fixes) if top_fixes else 'Keine Warnings')} ",
            "",
            "VORSCHLÄGE",
        ]
        if has_issues:
            lines.append("• findings im jobs/scripts/container state manuell prüfen")
            lines.append("• nur Detection-only behalten — keine Prune/Deletes aktivieren")
        else:
            lines.append("• Keine Sofortaktion nötig")
            lines.append("• Nur auf nächste Heartbeat-Ausgabe warten")

        if is_heartbeat and not has_issues:
            self.mark_heartbeat_sent()

        return "\n".join(lines)

    # ── Main ──────────────────────────────────────────────────────

    def run(self):
        secure_path_permissions(LOG_DIR, mode=LOG_DIR_MODE, ensure_dir=True)
        if not SAFE_DETECTION_ONLY_MODE:
            raise RuntimeError("GhostBuster safe detection-only mode must remain enabled")
        self.log("MODE: detection-only")

        # Detection (all read-only)
        self.scan_jobs_json()
        self.scan_cron_outputs()
        self.scan_docker_containers()
        self.scan_scripts_dir()
        self.check_permission_drift()       # safe auto-fix only
        self.check_mem0_watchdog_health()
        self.check_docker_disk()            # read-only report

        # Generate report
        report = self.generate_report()

        # Log to file
        log_lines = [f"[{ts}] findings={len(self.findings)} fixed={len(self.fixed)} warnings={len(self.warnings)}\n"]
        log_lines.extend(f"  {a}\n" for a in self.actions)
        atomic_append_log(LOG_PATH, log_lines)

        if report:
            print(report)

        return 0 if not self.findings else 1


if __name__ == "__main__":
    gb = GhostBuster()
    sys.exit(gb.run())
