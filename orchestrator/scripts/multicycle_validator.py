#!/usr/bin/env python3
"""Multi-Cycle Validator — Read-only validation collector for repeated manual runs.

Inspects:
- orchestrator/logs/trading_cycle_*.log
- /home/hermes/primoagent/output/signals/primo_risk_filtered_latest.json
- /home/hermes/primoagent/output/shadow/primo_shadow_log.jsonl
- per-bot primo_signal_state.json files
- orchestrator/reports/fleet_health_latest.json

Outputs:
- JSON report: /home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.json
- Markdown report: /home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.md
"""

from __future__ import annotations

import json
import glob
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

VERSION = "0.1.0"
REPORTS_DIR = Path("/home/hermes/projects/trading/orchestrator/reports")
JSON_OUTPUT = REPORTS_DIR / "multicycle_validation_latest.json"
MD_OUTPUT = REPORTS_DIR / "multicycle_validation_latest.md"

TRADING_ROOT = Path("/home/hermes/projects/trading")
PRIMO_ROOT = Path("/home/hermes/primoagent")
LOGS_DIR = TRADING_ROOT / "orchestrator/logs"
RISK_FILE = PRIMO_ROOT / "output/signals/primo_risk_filtered_latest.json"
SHADOW_LOG = PRIMO_ROOT / "output/shadow/primo_shadow_log.jsonl"
STATE_FILES = [
    TRADING_ROOT / "freqtrade/bots/rsi/user_data/primo_signal_state.json",
    TRADING_ROOT / "freqtrade/bots/momentum/user_data/primo_signal_state.json",
    TRADING_ROOT / "freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json",
]
FLEET_HEALTH_JSON = REPORTS_DIR / "fleet_health_latest.json"


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load JSON file or return None."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def count_wrapper_logs() -> int:
    """Count wrapper log files."""
    return len(list(LOGS_DIR.glob("trading_cycle_*.log")))


def get_latest_wrapper_log() -> Optional[Path]:
    """Get most recent wrapper log."""
    logs = sorted(LOGS_DIR.glob("trading_cycle_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return logs[0] if logs else None


def extract_run_ids_from_logs() -> List[Dict[str, Any]]:
    """Extract run IDs and timestamps from all wrapper logs."""
    runs = []
    for log_path in sorted(LOGS_DIR.glob("trading_cycle_*.log")):
        try:
            content = log_path.read_text(encoding="utf-8")
            # Extract RUN_ID from log
            run_id_match = re.search(r"RUN_ID=(\w+)", content)
            run_id = run_id_match.group(1) if run_id_match else None
            
            # Extract START timestamp
            start_match = re.search(r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\] START", content)
            start_ts = start_match.group(1) if start_match else None
            
            # Extract exit status
            completed_match = re.search(r"RUN_ID=\w+ completed successfully", content)
            failed_match = re.search(r"Step \d+: FAIL", content)
            exit_status = "success" if completed_match else ("failed" if failed_match else "unknown")
            
            if run_id:
                runs.append({
                    "run_id": run_id,
                    "log_file": str(log_path),
                    "start_timestamp": start_ts,
                    "exit_status": exit_status,
                    "log_mtime": datetime.fromtimestamp(log_path.stat().st_mtime, tz=timezone.utc).isoformat()
                })
        except Exception:
            continue
    
    return sorted(runs, key=lambda r: r.get("log_mtime", ""), reverse=True)


def validate_riskguard_output() -> Dict[str, Any]:
    """Validate RiskGuard output."""
    if not RISK_FILE.exists():
        return {"exists": False, "valid_json": False, "error": "file_missing"}
    
    try:
        data = json.loads(RISK_FILE.read_text(encoding="utf-8"))
        results = data.get("results", [])
        accepted = sum(1 for r in results if r.get("verdict") == "ACCEPTED")
        watch_only = sum(1 for r in results if r.get("verdict") == "WATCH_ONLY")
        blocked = sum(1 for r in results if r.get("verdict") == "BLOCK_ENTRY")
        
        return {
            "exists": True,
            "valid_json": True,
            "total_signals": len(results),
            "accepted_count": accepted,
            "watch_only_count": watch_only,
            "blocked_count": blocked,
            "schema_version": data.get("meta", {}).get("schema_version"),
        }
    except json.JSONDecodeError:
        return {"exists": True, "valid_json": False, "error": "invalid_json"}
    except Exception as e:
        return {"exists": True, "valid_json": False, "error": str(e)}


def validate_shadow_log() -> Dict[str, Any]:
    """Validate ShadowLogger append-only log."""
    if not SHADOW_LOG.exists():
        return {"exists": False, "lines": 0, "valid_json_lines": 0, "error": "file_missing"}
    
    try:
        content = SHADOW_LOG.read_text(encoding="utf-8")
        lines = [l for l in content.strip().split("\n") if l.strip()]
        valid_count = 0
        latest_entries = []
        
        for line in lines[-10:]:  # Check last 10 lines
            try:
                entry = json.loads(line)
                valid_count += 1
                if len(latest_entries) < 3:
                    latest_entries.append({
                        "run_id": entry.get("run_id"),
                        "logged_at": entry.get("logged_at"),
                        "pairs_count": len(entry.get("signals", []))
                    })
            except json.JSONDecodeError:
                continue
        
        return {
            "exists": True,
            "total_lines": len(lines),
            "valid_json_lines": valid_count,
            "latest_entries": latest_entries,
        }
    except Exception as e:
        return {"exists": True, "error": str(e)}


def validate_state_files() -> Dict[str, Any]:
    """Validate per-bot state files for schema consistency."""
    required_top = {"schema_version", "bridge_version", "written_at", "source_type", "riskguard_available", "pairs", "summary"}
    required_pair = {"pair", "source_action", "normalized_action", "confidence", "verdict", "reasons", "age_seconds", "is_fresh", "allow_long_bias", "allow_short_bias", "watch_only", "block_entry"}
    
    results = []
    all_valid = True
    schema_versions = set()
    
    for state_path in STATE_FILES:
        if not state_path.exists():
            results.append({
                "path": str(state_path),
                "exists": False,
                "valid_json": False,
                "error": "file_missing"
            })
            all_valid = False
            continue
        
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            missing_top = required_top - set(data.keys())
            
            pairs = data.get("pairs", {})
            pair_issues = []
            for pair_name, entry in pairs.items():
                if not isinstance(entry, dict):
                    continue
                missing_pair = required_pair - set(entry.keys())
                if missing_pair:
                    pair_issues.append({"pair": pair_name, "missing": sorted(missing_pair)})
            
            schema_versions.add(data.get("schema_version"))
            
            results.append({
                "path": str(state_path),
                "exists": True,
                "valid_json": True,
                "schema_version": data.get("schema_version"),
                "bridge_version": data.get("bridge_version"),
                "source_type": data.get("source_type"),
                "missing_top_fields": sorted(missing_top),
                "pair_issues": pair_issues,
                "pairs_count": len(pairs),
            })
            
            if missing_top or pair_issues:
                all_valid = False
                
        except json.JSONDecodeError:
            results.append({
                "path": str(state_path),
                "exists": True,
                "valid_json": False,
                "error": "invalid_json"
            })
            all_valid = False
        except Exception as e:
            results.append({
                "path": str(state_path),
                "exists": True,
                "valid_json": False,
                "error": str(e)
            })
            all_valid = False
    
    return {
        "all_valid": all_valid,
        "schema_versions": list(schema_versions),
        "files": results
    }


def validate_fleet_health() -> Dict[str, Any]:
    """Validate fleet health report."""
    if not FLEET_HEALTH_JSON.exists():
        return {"exists": False, "error": "file_missing"}
    
    try:
        data = json.loads(FLEET_HEALTH_JSON.read_text(encoding="utf-8"))
        return {
            "exists": True,
            "valid_json": True,
            "fleet_verdict": data.get("fleet_verdict"),
            "bots_checked": len(data.get("bots", [])),
            "helper_exists": data.get("helper_exists"),
            "bot_verdicts": [
                {"bot": b.get("bot"), "verdict": b.get("verdict")}
                for b in data.get("bots", [])
            ]
        }
    except Exception as e:
        return {"exists": True, "valid_json": False, "error": str(e)}


def determine_overall_status(
    wrapper_count: int,
    riskguard: Dict[str, Any],
    shadow: Dict[str, Any],
    states: Dict[str, Any],
    fleet: Dict[str, Any]
) -> str:
    """Determine overall validation status."""
    # RED conditions
    if wrapper_count == 0:
        return "RED"
    if not riskguard.get("valid_json"):
        return "RED"
    if not states.get("all_valid"):
        return "RED"
    if fleet.get("fleet_verdict") == "RED":
        return "RED"
    
    # YELLOW conditions
    if shadow.get("total_lines", 0) == 0:
        return "YELLOW"
    if fleet.get("fleet_verdict") in {"YELLOW", "ORANGE"}:
        return "YELLOW"
    if len(states.get("schema_versions", [])) > 1:
        return "YELLOW"  # Schema drift
    
    # GREEN
    return "GREEN"


def write_json_report(report: Dict[str, Any], path: Path):
    """Write JSON report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def write_md_report(report: Dict[str, Any], path: Path):
    """Write Markdown report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    status = report["overall_status"]
    validated_at = report["validated_at"]
    
    md = f"""# Multi-Cycle Validation Report

## Summary

- **Status:** {status}
- **Validated At:** {validated_at}
- **Wrapper Runs Found:** {report['wrapper_runs']['count']}
- **Latest Run ID:** {report['wrapper_runs']['latest_run_id'] or 'N/A'}

## Component Status

| Component | Status | Details |
|-----------|--------|---------|
| RiskGuard | {'✅' if report['riskguard']['valid_json'] else '❌'} | {report['riskguard'].get('total_signals', 0)} signals, {report['riskguard'].get('accepted_count', 0)} ACCEPTED |
| ShadowLogger | {'✅' if report['shadow']['total_lines'] > 0 else '❌'} | {report['shadow'].get('total_lines', 0)} lines logged |
| State Files | {'✅' if report['state_files']['all_valid'] else '❌'} | Schema: {', '.join(report['state_files']['schema_versions']) or 'N/A'} |
| Fleet Health | {'✅' if report['fleet_health'].get('fleet_verdict') == 'GREEN' else '⚠️'} | {report['fleet_health'].get('fleet_verdict', 'N/A')} |

## Wrapper Runs

| Run ID | Timestamp | Status | Log |
|--------|-----------|--------|-----|
"""
    
    for run in report["wrapper_runs"]["runs"][:10]:  # Show last 10
        status_icon = "✅" if run.get("exit_status") == "success" else "❌"
        md += f"| {run.get('run_id', 'N/A')} | {run.get('start_timestamp', 'N/A')} | {status_icon} {run.get('exit_status', 'unknown')} | [log]({run.get('log_file', '')}) |\n"
    
    md += f"""

## State Files

| Bot | Exists | Valid JSON | Schema | Pairs | Issues |
|-----|--------|------------|--------|-------|--------|
"""
    
    for file_result in report["state_files"]["files"]:
        exists = "✅" if file_result.get("exists") else "❌"
        valid = "✅" if file_result.get("valid_json") else "❌"
        schema = file_result.get("schema_version", "N/A")
        pairs = file_result.get("pairs_count", 0)
        issues = "⚠️ " + str(file_result.get("pair_issues", [])) if file_result.get("pair_issues") else "✅"
        md += f"| {Path(file_result['path']).parent.parent.name} | {exists} | {valid} | {schema} | {pairs} | {issues} |\n"
    
    md += f"""

## RiskGuard Verdict Distribution

- **ACCEPTED:** {report['riskguard'].get('accepted_count', 0)}
- **WATCH_ONLY:** {report['riskguard'].get('watch_only_count', 0)}
- **BLOCK_ENTRY:** {report['riskguard'].get('blocked_count', 0)}

## Fleet Health

| Bot | Verdict |
|-----|---------|
"""
    
    for bot in report["fleet_health"].get("bot_verdicts", []):
        md += f"| {bot.get('bot', 'N/A')} | {bot.get('verdict', 'N/A')} |\n"
    
    md += f"""

## Known Limitations

- **BLOCK_ENTRY semantics:** Currently behaves neutral (same as WATCH_ONLY). Documented as deferred tech debt for explicit block-policy design.
- **Multi-cycle history:** Only current state validated. Repeated runs needed for drift detection.

---

**Generated:** {validated_at}  
**Multi-Cycle Validator Version:** v{VERSION}
"""
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(md)


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    
    # Count wrapper logs
    wrapper_count = count_wrapper_logs()
    latest_log = get_latest_wrapper_log()
    runs = extract_run_ids_from_logs()
    
    # Validate components
    riskguard = validate_riskguard_output()
    shadow = validate_shadow_log()
    state_files = validate_state_files()
    fleet_health = validate_fleet_health()
    
    # Overall status
    overall_status = determine_overall_status(wrapper_count, riskguard, shadow, state_files, fleet_health)
    
    # Build report
    report = {
        "version": VERSION,
        "validated_at": now,
        "overall_status": overall_status,
        "wrapper_runs": {
            "count": wrapper_count,
            "latest_log": str(latest_log) if latest_log else None,
            "latest_run_id": runs[0].get("run_id") if runs else None,
            "runs": runs
        },
        "riskguard": riskguard,
        "shadow": shadow,
        "state_files": state_files,
        "fleet_health": fleet_health
    }
    
    # Write reports
    write_json_report(report, JSON_OUTPUT)
    write_md_report(report, MD_OUTPUT)
    
    # Print summary
    print(f"Multi-Cycle Validator v{VERSION}")
    print(f"  Status: {overall_status}")
    print(f"  Wrapper runs found: {wrapper_count}")
    print(f"  RiskGuard: {'✅' if riskguard.get('valid_json') else '❌'}")
    print(f"  ShadowLogger: {shadow.get('total_lines', 0)} lines")
    print(f"  State Files: {'✅' if state_files.get('all_valid') else '❌'}")
    print(f"  Fleet Health: {fleet_health.get('fleet_verdict', 'N/A')}")
    print(f"  JSON: {JSON_OUTPUT}")
    print(f"  Markdown: {MD_OUTPUT}")
    
    # Exit code based on status
    if overall_status == "RED":
        return 2
    elif overall_status == "YELLOW":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
