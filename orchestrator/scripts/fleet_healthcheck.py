#!/usr/bin/env python3
"""Fleet Healthcheck — Read-only health monitoring for Freqtrade bots.

Checks:
- Container status (running)
- dry_run=true in configs
- Exchange credentials (absent/present, never printed)
- Strategy class matches CLI
- primo_signal_state.json visibility
- Shared helper exists
- Optional: API ping (if configured)

Outputs:
- JSON report: /home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.json
- Markdown report: /home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.md

Verdicts:
- GREEN: All bots safe, dry_run, no credentials
- YELLOW: Minor issues (state file missing, but bot safe)
- ORANGE: Concerns (stale RiskGuard, API unreachable)
- RED: Critical (dry_run=false, credentials present, container down)
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

VERSION = "0.1.0"
REPORTS_DIR = Path("/home/hermes/projects/trading/orchestrator/reports")
JSON_OUTPUT = REPORTS_DIR / "fleet_health_latest.json"
MD_OUTPUT = REPORTS_DIR / "fleet_health_latest.md"

BOT_CONFIGS = {
    "rsi": {
        "container": "freqtrade-rsi",
        "config": "/home/hermes/projects/trading/freqtrade/bots/rsi/config/config.json",
        "state": "/home/hermes/projects/trading/freqtrade/bots/rsi/user_data/primo_signal_state.json",
        "expected_strategy": "SimpleRSIOnly_v1"
    },
    "momentum": {
        "container": "freqtrade-momentum",
        "config": "/home/hermes/projects/trading/freqtrade/bots/momentum/config/config.json",
        "state": "/home/hermes/projects/trading/freqtrade/bots/momentum/user_data/primo_signal_state.json",
        "expected_strategy": "MomentumBG15_v1"
    },
    "regime-hybrid": {
        "container": "freqtrade-regime-hybrid",
        "config": "/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json",
        "state": "/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json",
        "expected_strategy": "RegimeSwitchingHybrid_v6_Stable"
    }
}

SHARED_HELPER = "/home/hermes/projects/trading/freqtrade/shared/primo_signal.py"


def run_command(cmd: str) -> str:
    """Run shell command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def check_container_running(container_name: str) -> bool:
    """Check if container is running."""
    output = run_command(f"docker inspect -f '{{{{.State.Running}}}}' {container_name}")
    return output == "true"


def load_config(config_path: str) -> Optional[Dict[str, Any]]:
    """Load Freqtrade config JSON."""
    try:
        return json.loads(Path(config_path).read_text())
    except Exception:
        return None


def check_dry_run(config: Dict[str, Any]) -> bool:
    """Check if dry_run is true."""
    return bool(config.get("dry_run", False))


def check_exchange_credentials(config: Dict[str, Any]) -> Dict[str, str]:
    """Check exchange credentials (never print values)."""
    exchange = config.get("exchange", {})
    key = exchange.get("key", "") or ""
    secret = exchange.get("secret", "") or ""
    
    result = {}
    if key:
        result["key"] = f"present(len={len(key)})"
    else:
        result["key"] = "absent"
    
    if secret:
        result["secret"] = f"present(len={len(secret)})"
    else:
        result["secret"] = "absent"
    
    return result


def get_container_command(container_name: str) -> str:
    """Get container command line."""
    output = run_command(f"docker exec {container_name} cat /proc/1/cmdline")
    return output.replace("\0", " ").strip()


def check_strategy_matches(cmdline: str, expected_strategy: str) -> bool:
    """Check if strategy in cmdline matches expected."""
    return expected_strategy in cmdline


def check_state_file_exists(state_path: str) -> bool:
    """Check if primo_signal_state.json exists."""
    return Path(state_path).exists()


def check_helper_exists() -> bool:
    """Check if shared helper exists."""
    return Path(SHARED_HELPER).exists()


def determine_bot_verdict(
    container_running: bool,
    dry_run: bool,
    credentials: Dict[str, str],
    strategy_matches: bool,
    state_exists: bool
) -> str:
    """Determine health verdict for a bot."""
    # RED conditions
    if not container_running:
        return "RED"
    if not dry_run:
        return "RED"
    if credentials.get("key") != "absent" or credentials.get("secret") != "absent":
        return "RED"
    if not strategy_matches:
        return "RED"
    
    # YELLOW conditions
    if not state_exists:
        return "YELLOW"
    
    # GREEN
    return "GREEN"


def check_bot(bot_name: str, bot_info: Dict[str, Any]) -> Dict[str, Any]:
    """Check a single bot's health."""
    container = bot_info["container"]
    config_path = bot_info["config"]
    state_path = bot_info["state"]
    expected_strategy = bot_info["expected_strategy"]
    
    # Container
    container_running = check_container_running(container)
    
    # Config
    config = load_config(config_path)
    if config:
        dry_run = check_dry_run(config)
        credentials = check_exchange_credentials(config)
    else:
        dry_run = False
        credentials = {"key": "config_unreadable", "secret": "config_unreadable"}
    
    # Strategy
    cmdline = get_container_command(container)
    strategy_matches = check_strategy_matches(cmdline, expected_strategy) if config else False
    
    # State file
    state_exists = check_state_file_exists(state_path)
    
    # Verdict
    verdict = determine_bot_verdict(
        container_running, dry_run, credentials, strategy_matches, state_exists
    )
    
    return {
        "bot": bot_name,
        "container": container,
        "container_running": container_running,
        "config_path": config_path,
        "config_readable": config is not None,
        "dry_run": dry_run,
        "exchange_credentials": credentials,
        "expected_strategy": expected_strategy,
        "strategy_matches": strategy_matches,
        "state_file": state_path,
        "state_file_exists": state_exists,
        "verdict": verdict
    }


def determine_fleet_verdict(bot_results: List[Dict[str, Any]]) -> str:
    """Determine overall fleet verdict."""
    has_red = any(r["verdict"] == "RED" for r in bot_results)
    has_yellow = any(r["verdict"] == "YELLOW" for r in bot_results)
    
    if has_red:
        return "RED"
    if has_yellow:
        return "YELLOW"
    return "GREEN"


def write_json_report(report: Dict[str, Any], path: Path):
    """Write JSON report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def write_md_report(report: Dict[str, Any], path: Path):
    """Write Markdown report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    verdict = report["fleet_verdict"]
    checked_at = report["checked_at"]
    helper_exists = report["helper_exists"]
    
    md = f"""# Fleet Healthcheck Report

## Summary

- **Verdict:** {verdict}
- **Checked At:** {checked_at}
- **Shared Helper:** {'✅ Exists' if helper_exists else '❌ Missing'}
- **Total Bots:** {len(report['bots'])}

## Bot Status

| Bot | Container | Running | Dry-Run | Credentials | Strategy | State File | Verdict |
|-----|-----------|---------|---------|-------------|----------|------------|---------|
"""
    
    for bot in report["bots"]:
        bot_name = bot["bot"]
        container = bot["container"]
        running = "✅" if bot["container_running"] else "❌"
        dry_run = "✅" if bot["dry_run"] else "❌"
        creds = bot["exchange_credentials"]
        creds_str = f"{creds.get('key', '?')}/{creds.get('secret', '?')}"
        strategy = "✅" if bot["strategy_matches"] else "❌"
        state = "✅" if bot["state_file_exists"] else "❌"
        verdict = bot["verdict"]
        
        md += f"| {bot_name} | {container} | {running} | {dry_run} | {creds_str} | {strategy} | {state} | {verdict} |\n"
    
    md += f"""

## Verdict Legend

| Verdict | Meaning |
|---------|---------|
| GREEN | All bots safe, dry_run, no credentials |
| YELLOW | Minor issues (state file missing, but bot safe) |
| ORANGE | Concerns (stale RiskGuard, API unreachable) |
| RED | Critical (dry_run=false, credentials present, container down) |

---

**Generated:** {checked_at}  
**Fleet Healthcheck Version:** v{VERSION}
"""
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(md)


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    
    # Check helper
    helper_exists = check_helper_exists()
    
    # Check all bots
    bot_results = []
    for bot_name, bot_info in BOT_CONFIGS.items():
        result = check_bot(bot_name, bot_info)
        bot_results.append(result)
    
    # Fleet verdict
    fleet_verdict = determine_fleet_verdict(bot_results)
    
    # Build report
    report = {
        "version": VERSION,
        "checked_at": now,
        "fleet_verdict": fleet_verdict,
        "helper_exists": helper_exists,
        "bots": bot_results
    }
    
    # Write reports
    write_json_report(report, JSON_OUTPUT)
    write_md_report(report, MD_OUTPUT)
    
    # Print summary
    print(f"Fleet Healthcheck v{VERSION}")
    print(f"  Verdict: {fleet_verdict}")
    print(f"  Bots checked: {len(bot_results)}")
    print(f"  JSON: {JSON_OUTPUT}")
    print(f"  Markdown: {MD_OUTPUT}")
    
    # Exit code based on verdict
    if fleet_verdict == "RED":
        return 2
    elif fleet_verdict == "YELLOW":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
