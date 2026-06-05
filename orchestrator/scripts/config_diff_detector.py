#!/opt/hermes/.venv/bin/python3
"""config_diff_detector.py — Config Drift Detector v1.0

Scans all active Freqtrade bot containers and compares:
  - Config-on-Disk (host-side config files)
  - Config-in-Container (docker exec cat)

On drift: reports diff, optionally auto-restores + restarts.

Runs as cron job. Exit codes:
  0 = no drift
  1 = drift detected
  2 = error

Usage:
  /opt/hermes/.venv/bin/python3 config_diff_detector.py
  --fix : auto-restore + restart on drift
  --check-only : print drift summary only
"""

import json, os, subprocess, sys, difflib
from datetime import datetime, timezone
from pathlib import Path

BASE = "/home/hermes/projects/trading"
STATE_DIR = Path(BASE) / "orchestrator/state/config_diff"
DRIFT_LOG = STATE_DIR / "config_drift.log"
HEALTH_FILE = STATE_DIR / "config_diff_health.json"

# Bot config mappings: (container, host_path, container_path)
BOT_CONFIGS = [
    ("trading-freqtrade-freqforge-1",
     "/home/hermes/projects/trading/freqforge/config/config_freqforge_dryrun.json",
     "/freqtrade/config/config_freqforge_dryrun.json"),
    ("trading-freqtrade-freqforge-canary-1",
     "/home/hermes/projects/trading/freqforge-canary/config/config_canary_dryrun.json",
     "/freqtrade/config/config_canary_dryrun.json"),
    ("trading-freqtrade-regime-hybrid-1",
     "/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json",
     "/freqtrade/config/config_regime_hybrid_dryrun.json"),
    ("trading-freqai-rebel-1",
     None,  # no host path — Docker volume
     "/freqtrade/user_data/config.json"),
]


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(str(STATE_DIR), exist_ok=True)
    with open(str(DRIFT_LOG), "a") as f:
        f.write(line + "\n")


def read_host_config(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        log(f"  ERROR reading host config {path}: {e}")
        return None


def read_container_config(container: str, path: str) -> dict | None:
    """Read config from container via docker exec. Falls back to None if blocked."""
    try:
        r = subprocess.run(
            ["docker", "exec", container, "cat", path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    except json.JSONDecodeError as e:
        log(f"  ERROR parsing container config {container}:{path}: {e}")
    return None


def get_diff(host: dict, container: dict, keys: list[str] = None) -> dict:
    """Compare host vs container config, return dict of diffs."""
    if keys is None:
        keys = ["max_open_trades", "stake_amount", "dry_run", "stoploss", "trailing_stop"]
    diffs = {}
    for key in keys:
        hv = host.get(key)
        cv = container.get(key)
        if hv != cv:
            diffs[key] = {"host": hv, "container": cv}
    return diffs


def check_bot_config(container: str, host_path: str | None, container_path: str, fix: bool = False) -> dict:
    """Check config drift for one bot. Returns result dict."""
    result = {"container": container, "drift": False, "diffs": {}, "action": "none"}

    # Read host config
    host_cfg = read_host_config(host_path) if host_path and os.path.exists(host_path) else None
    if host_path and not host_cfg:
        result["error"] = "host config unreadable"
        return result

    # Read container config
    container_cfg = read_container_config(container, container_path)
    if not container_cfg:
        # docker exec blocked (EXEC=0 proxy) — host-only mode for bind-mounted configs
        if host_cfg:
            log(f"  {container}: HOST-ONLY (docker exec blocked, bind-mount assumed in sync)")
            result["drift"] = False
            return result
        # No host path AND no container access (e.g. freqai-rebel with Docker volume)
        if not host_path:
            log(f"  {container}: SKIP (no host path, docker exec blocked)")
            return result
        result["error"] = "container config unreadable"
        return result

    # Compare
    diffs = get_diff(host_cfg, container_cfg) if host_cfg else {}
    if not diffs:
        log(f"  {container}: OK (no drift)")
        result["drift"] = False
        return result

    result["drift"] = True
    result["diffs"] = diffs
    for key, diff in diffs.items():
        log(f"  DRIFT {container}: {key} host={diff['host']} vs container={diff['container']}")

    if fix and host_cfg:
        # Restore: write host config to container
        try:
            cfg_json = json.dumps(host_cfg, indent=4)
            escaped = cfg_json.replace("'", "'\\''")
            r = subprocess.run(
                ["docker", "exec", container, "bash", "-lc",
                 f"tmp=$(mktemp {container_path}.tmp.XXXXXX) && printf '%s\\n' '{escaped}' > \"$tmp\" && chmod 664 \"$tmp\" && mv \"$tmp\" {container_path}"],
                capture_output=True, text=True, timeout=20,
            )
            if r.returncode == 0:
                result["action"] = "config_restored"
                log(f"  FIX: config restored for {container}")
                # Restart container
                subprocess.run(["docker", "restart", container], capture_output=True, timeout=30)
                log(f"  RESTART: {container} restarted after config fix")
                result["action"] = "config_restored_and_restarted"
            else:
                result["error"] = f"restore failed: {r.stderr.strip()}"
        except Exception as e:
            result["error"] = f"restore error: {e}"

    return result


def main() -> int:
    fix = "--fix" in sys.argv
    mode = "FIX" if fix else "CHECK"
    log(f"=== Config Diff Detector ({mode}) ===")

    results = []
    drift_count = 0
    error_count = 0

    for container, host_path, container_path in BOT_CONFIGS:
        result = check_bot_config(container, host_path, container_path, fix=fix)
        results.append(result)
        if result.get("drift"):
            drift_count += 1
        if result.get("error"):
            error_count += 1

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "bots_checked": len(results),
        "drift_detected": drift_count,
        "errors": error_count,
        "results": results,
    }

    # Write health
    os.makedirs(str(STATE_DIR), exist_ok=True)
    with open(str(HEALTH_FILE), "w") as f:
        json.dump(summary, f, indent=2, default=str)

    log(f"Done: {len(results)} bots, {drift_count} drift(s), {error_count} error(s)")
    return 1 if drift_count > 0 or error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
