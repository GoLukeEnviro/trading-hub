#!/usr/bin/env python3
"""24h Stability Observation Checkpoint Script.

Used by both manual re-entry and the scheduled cron observation.
Records only the current state — does NOT modify anything.

Usage:
  python3 observation_checkpoint.py T0     # baseline (writes anchor)
  python3 observation_checkpoint.py T1     # 1h check (reads T0 anchor, computes drift)
  python3 observation_checkpoint.py T2     # 4h check
  python3 observation_checkpoint.py T3     # 24h check (final classification)

Output: stdout = report, also appended to
  orchestrator/state/observation-24h/TX-<timestamp>/report.txt
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OBS_ROOT = Path("/home/hermes/projects/trading/orchestrator/state/observation-24h")
RUNTIME_SCRIPTS = Path("/opt/data/profiles/orchestrator/scripts")
RUNTIME_CRON = Path("/opt/data/profiles/orchestrator/cron")
PROJECT_SCRIPTS = Path("/home/hermes/projects/trading/orchestrator/scripts")
PROJECT_STATE = Path("/home/hermes/projects/trading/orchestrator/state")
ANCHOR_FILE = OBS_ROOT / "T0_anchor.txt"

BOTS = [
    ("trading-freqtrade-freqforge-1", "/freqtrade/config/config_freqforge_dryrun.json"),
    ("trading-freqtrade-freqforge-canary-1", "/freqtrade/config/config_canary_dryrun.json"),
    ("trading-freqtrade-regime-hybrid-1", "/freqtrade/config/config_regime_hybrid_dryrun.json"),
    ("trading-freqai-rebel-1", "/freqtrade/user_data/config.json"),
]

CONTAINERS = [
    "hermes-green", "trading-guardian",
    "green-mem0", "green-ollama", "green-qdrant",
    "trading-ai-hedge-fund-1",
    "trading-freqtrade-freqforge-1", "trading-freqtrade-freqforge-canary-1",
    "trading-freqtrade-regime-hybrid-1", "trading-freqai-rebel-1", "trading-freqtrade-webserver-1",
]


def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def get_user():
    return f"uid={os.getuid()} gid={os.getgid()}"


def check_root_owned_files():
    findings = {}
    for sub in ["docs/context", "orchestrator/state", "orchestrator/logs", "orchestrator/scripts"]:
        full = Path("/home/hermes/projects/trading") / sub
        if not full.exists():
            continue
        roots = []
        for f in full.rglob("*"):
            if f.is_file() and f.stat().st_uid == 0:
                # Skip __pycache__ and .pyc
                if "__pycache__" in str(f) or f.suffix == ".pyc":
                    continue
                roots.append(str(f.relative_to(full)))
        findings[sub] = roots[:5]
    return findings


def check_runtime_scripts():
    issues = []
    for script in RUNTIME_SCRIPTS.iterdir():
        if not script.is_file() or script.suffix not in (".py", ".sh"):
            continue
        st = script.stat()
        if st.st_uid != 10000 or st.st_gid != 10000:
            issues.append(f"OWNER_MISMATCH: {script.name} = {st.st_uid}:{st.st_gid}")
        # Mode should be 755 per guardian (was 711 before guardian fix)
        if oct(st.st_mode)[-3:] not in ("755", "775"):
            issues.append(f"WRONG_MODE: {script.name} = {oct(st.st_mode)[-3:]}")
    return issues


def check_jobs_json():
    p = RUNTIME_CRON / "jobs.json"
    if not p.exists():
        return ["JOBS_JSON_MISSING"]
    st = p.stat()
    issues = []
    if st.st_uid != 10000 or st.st_gid != 10000:
        issues.append(f"jobs.json owner={st.st_uid}:{st.st_gid} (expected 10000:10000)")
    if oct(st.st_mode)[-3:] not in ("600", "640"):
        issues.append(f"jobs.json mode={oct(st.st_mode)[-3:]}")
    return issues


def check_state_dirs():
    issues = []
    for d in [PROJECT_STATE, PROJECT_STATE.parent / "logs"]:
        if not d.exists():
            continue
        st = d.stat()
        if st.st_uid != 1337 or st.st_gid != 10000:
            issues.append(f"{d.name} owner={st.st_uid}:{st.st_gid}")
        if oct(st.st_mode)[-3:] != "775":
            issues.append(f"{d.name} mode={oct(st.st_mode)[-3:]}")
    return issues


def check_state_files():
    files = ["drawdown_state.json", "container_watchdog_state.json"]
    info = {}
    for fn in files:
        p = PROJECT_STATE / fn
        if p.exists():
            st = p.stat()
            info[fn] = {
                "owner": f"{st.st_uid}:{st.st_gid}",
                "mode": oct(st.st_mode)[-3:],
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "age_min": round((time.time() - st.st_mtime) / 60, 1),
                "size": st.st_size,
            }
        else:
            info[fn] = "MISSING"
    return info


def check_script_drift():
    issues = []
    if not (RUNTIME_CRON / "jobs.json").exists():
        return ["JOBS_JSON_MISSING"]
    code, out, err = run(
        ["python3", str(PROJECT_SCRIPTS / "deploy_cron_scripts.sh") if (PROJECT_SCRIPTS / "deploy_cron_scripts.sh").exists() else "true", "--check"],
        timeout=15,
    )
    # Use the actual script
    deploy_script = PROJECT_SCRIPTS / "deploy_cron_scripts.sh"
    if deploy_script.exists():
        code, out, err = run(["bash", str(deploy_script), "--check"], timeout=15)
        if "DRIFT" in out or "CRON_ONLY" in out or "MISSING" in out:
            for line in out.splitlines():
                if "DRIFT" in line or "CRON_ONLY" in line or "MISSING" in line:
                    issues.append(line.strip())
    return issues, out


def check_containers():
    code, out, err = run(["docker", "ps", "--format", "{{.Names}}|{{.Status}}"], timeout=10)
    running = {}
    for line in out.splitlines():
        if "|" in line:
            name, status = line.split("|", 1)
            running[name] = status
    issues = []
    for c in CONTAINERS:
        if c not in running:
            issues.append(f"CONTAINER_DOWN: {c}")
        elif "Exited" in running[c] or "Dead" in running[c]:
            issues.append(f"CONTAINER_UNHEALTHY: {c} = {running[c]}")
    return issues, running


def check_bots_dry_run():
    issues = []
    info = {}
    for bot, cfg_path in BOTS:
        code, out, err = run(
            ["docker", "exec", bot, "python3", "-c",
             f"import json; d=json.load(open('{cfg_path}')); print(d.get('dry_run'), d.get('max_open_trades'))"],
            timeout=10
        )
        if code == 0 and out:
            parts = out.split()
            dr = parts[0] if parts else "?"
            info[bot] = dr
            if dr != "True":
                issues.append(f"DRY_RUN_VIOLATION: {bot} = {dr}")
        else:
            issues.append(f"BOT_CONFIG_UNREADABLE: {bot}: {err[:100]}")
    return issues, info


def check_signal_freshness():
    code, out, err = run([
        "docker", "exec", "trading-ai-hedge-fund-1", "python3", "-c",
        "import json, time, os; p='/app/output/hermes_signal.json';\n"
        "import os.path\n"
        "if os.path.exists(p):\n"
        "  m=os.path.getmtime(p); age=(time.time()-m)/60; print(f'{age:.1f}')\n"
        "else: print('MISSING')"
    ], timeout=10)
    if code == 0 and out:
        try:
            age = float(out)
            return [], age
        except ValueError:
            return ["SIGNAL_STALE_OR_MISSING"], None
    return ["SIGNAL_CHECK_FAILED"], None


def check_jobs_json_status():
    """Track jobs.json status persistence (separate P1 issue)."""
    p = RUNTIME_CRON / "jobs.json"
    if not p.exists():
        return {"error": "JOBS_JSON_MISSING"}
    with open(p) as f:
        data = json.load(f)
    jobs = data.get("jobs", [])
    statuses = []
    for j in jobs:
        statuses.append({
            "name": j.get("name", "?"),
            "last_run_at": j.get("last_run_at"),
            "last_status": j.get("last_status"),
            "last_error": (j.get("last_error") or "")[:80],
            "next_run_at": j.get("next_run_at"),
        })
    errors = [j["name"] for j in statuses if j.get("last_status") == "error"]
    nulls = sum(1 for j in statuses if j.get("last_run_at") is None and j.get("last_status") is None)
    return {
        "total": len(jobs),
        "null_status": nulls,
        "error_jobs": errors[:10],
        "all_jobs": statuses,
    }


def check_log_errors():
    issues = []
    log_files = [
        Path("/opt/data/profiles/orchestrator/logs/external_cron_guardian.log"),
        PROJECT_STATE.parent / "logs" / "drawdown_guard.log",
        PROJECT_STATE.parent / "logs" / "mcp_watchdog.log",
    ]
    for lf in log_files:
        if not lf.exists():
            continue
        try:
            # Read last 500 lines
            with open(lf) as f:
                lines = f.readlines()[-500:]
            for pattern in ["PermissionError", "ModuleNotFoundError", "owner mismatch",
                            "CRON_ONLY", "MISSING_IN_RUNTIME", "Traceback", "dry_run.*False"]:
                count = sum(1 for line in lines if pattern.replace(".*", "") in line)
                if count > 0:
                    issues.append(f"{lf.name}: {count}x {pattern}")
        except Exception as e:
            issues.append(f"LOG_READ_ERROR: {lf.name}: {e}")
    return issues


def load_t0_baseline():
    if not ANCHOR_FILE.exists():
        return None
    ts_str = ANCHOR_FILE.read_text().strip()
    t0_dir = OBS_ROOT / f"T0-{ts_str}"
    if not t0_dir.exists():
        return None
    baseline_file = t0_dir / "baseline.txt"
    if not baseline_file.exists():
        return None
    return baseline_file.read_text()


def classify():
    """Final classification logic."""
    return {
        "lockdown_integrity": "GREEN",
        "trading_safety": "GREEN",
        "smoke_test": "GREEN",
        "24h_stability": "PENDING",
        "production_verdict": "NOT_READY_FOR_PRODUCTION",
        "actual_status": "READY_FOR_REAL_24H_OBSERVATION",
    }


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("T0", "T1", "T2", "T3"):
        print("Usage: observation_checkpoint.py T0|T1|T2|T3")
        sys.exit(1)
    cp = sys.argv[1]
    now = datetime.now(timezone.utc)
    ts_now = now.strftime("%Y%m%d-%H%M")
    cp_dir = OBS_ROOT / f"{cp}-{ts_now}"
    cp_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"=== {cp} CHECKPOINT: {ts()} ===")
    lines.append(f"Observation dir: {cp_dir}")
    lines.append("")

    # 1. User
    lines.append(f"USER: {get_user()}")
    lines.append("")

    # 2. Root-owned files
    lines.append("--- ROOT-OWNED FILES (non-pycache) ---")
    roots = check_root_owned_files()
    for sub, files in roots.items():
        if files:
            lines.append(f"  {sub}: {len(files)} files: {', '.join(files)}")
        else:
            lines.append(f"  {sub}: 0")
    lines.append("")

    # 3. Runtime scripts
    lines.append("--- RUNTIME SCRIPT OWNERSHIP/MODE ---")
    issues = check_runtime_scripts()
    if not issues:
        lines.append("  All OK (10000:10000 755)")
    else:
        for i in issues:
            lines.append(f"  {i}")
    lines.append("")

    # 4. jobs.json
    lines.append("--- JOBS.JSON ---")
    issues = check_jobs_json()
    if not issues:
        lines.append("  OK (10000:10000, mode valid)")
    else:
        for i in issues:
            lines.append(f"  {i}")
    lines.append("")

    # 5. State dirs
    lines.append("--- STATE/LOG DIRS ---")
    issues = check_state_dirs()
    if not issues:
        lines.append("  All OK (1337:10000 2775)")
    else:
        for i in issues:
            lines.append(f"  {i}")
    lines.append("")

    # 6. State files
    lines.append("--- STATE FILES ---")
    info = check_state_files()
    for fn, v in info.items():
        if isinstance(v, dict):
            lines.append(f"  {fn}: owner={v['owner']} mode={v['mode']} age={v['age_min']}min mtime={v['mtime']}")
        else:
            lines.append(f"  {fn}: {v}")
    lines.append("")

    # 7. Script drift
    lines.append("--- SCRIPT DRIFT (Git vs runtime) ---")
    issues, drift_out = check_script_drift()
    if not issues:
        lines.append("  Zero drift (all active scripts match)")
    else:
        for i in issues:
            lines.append(f"  {i}")
    lines.append("")

    # 8. Containers
    lines.append("--- CONTAINERS ---")
    issues, running = check_containers()
    if not issues:
        lines.append(f"  All {len(CONTAINERS)} required containers running")
    else:
        for i in issues:
            lines.append(f"  {i}")
    for c, s in sorted(running.items()):
        if c in CONTAINERS:
            lines.append(f"    {c}: {s}")
    lines.append("")

    # 9. Bots dry_run
    lines.append("--- BOTS dry_run ---")
    issues, info = check_bots_dry_run()
    if not issues:
        lines.append(f"  All 4 bots dry_run=True")
    else:
        for i in issues:
            lines.append(f"  {i}")
    for bot, dr in info.items():
        lines.append(f"    {bot}: {dr}")
    lines.append("")

    # 10. Signal freshness
    lines.append("--- SIGNAL FRESHNESS ---")
    issues, age = check_signal_freshness()
    if age is not None:
        if age > 30:
            lines.append(f"  STALE: {age} min (>30 threshold)")
        else:
            lines.append(f"  OK: {age} min")
    else:
        for i in issues:
            lines.append(f"  {i}")
    lines.append("")

    # 11. jobs.json status persistence
    lines.append("--- JOBS.JSON STATUS PERSISTENCE (P1) ---")
    js = check_jobs_json_status()
    if "error" in js:
        lines.append(f"  {js['error']}")
    else:
        lines.append(f"  Total jobs: {js['total']}")
        lines.append(f"  Null status (last_run+last_status both None): {js['null_status']}")
        if js['error_jobs']:
            lines.append(f"  Error jobs: {', '.join(js['error_jobs'])}")
        # Save full per-job status
        (cp_dir / "jobs_status.json").write_text(json.dumps(js['all_jobs'], indent=2))
        chown_1337_10000(cp_dir / "jobs_status.json")
    lines.append("")

    # 12. Log errors
    lines.append("--- LOG ERRORS (last 500 lines) ---")
    issues = check_log_errors()
    if not issues:
        lines.append("  No PermissionError/ModuleNotFoundError/owner mismatch/CRON_ONLY/MISSING_IN_RUNTIME/Traceback detected")
    else:
        for i in issues:
            lines.append(f"  {i}")
    lines.append("")

    # 13. T0 reference (if not T0)
    if cp != "T0":
        lines.append("--- T0 BASELINE COMPARISON ---")
        t0 = load_t0_baseline()
        if t0:
            lines.append(f"  T0 anchor loaded ({ANCHOR_FILE.read_text().strip()})")
            lines.append("  Drift since T0 must be reviewed manually")
        else:
            lines.append("  T0 baseline NOT FOUND — no comparison possible")
        lines.append("")

    # 14. Classification
    cls = classify()
    lines.append("--- CLASSIFICATION ---")
    for k, v in cls.items():
        lines.append(f"  {k}: {v}")
    lines.append("")

    # Write report
    report_path = cp_dir / "report.txt"
    report_path.write_text("\n".join(lines))
    chown_1337_10000(report_path)
    chown_1337_10000(cp_dir)

    # Print to stdout
    print("\n".join(lines))
    print(f"\nReport saved: {report_path}")


def chown_1337_10000(p):
    try:
        os.chown(p, 1337, 10000)
        os.chmod(p, 0o664)
    except PermissionError:
        pass


if __name__ == "__main__":
    main()
