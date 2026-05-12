#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

TRADING_ROOT = Path('/home/hermes/projects/trading')
PRIMO_ROOT = Path('/home/hermes/primoagent')
ORCH = TRADING_ROOT / 'orchestrator'
SCRIPT_DIR = ORCH / 'scripts'
STATE_DIR = ORCH / 'state' / 'observation-12h'
LOG_DIR = ORCH / 'logs' / 'observation-12h'
REPORT_DIR = ORCH / 'reports'
DOCS_DIR = TRADING_ROOT / 'docs' / 'context'
LEDGER = STATE_DIR / 'phase-12-7-observation-ledger.jsonl'
LATEST_JSON = REPORT_DIR / 'phase-12-7-observation-latest.json'
LATEST_MD = REPORT_DIR / 'phase-12-7-observation-latest.md'
SCHEDULE_FILE = DOCS_DIR / 'phase-12-7-12h-observation-schedule-{date}.md'
CONTROLLER_CREATED = DOCS_DIR / 'phase-12-7-controller-created-{date}.md'
EXECUTION_MODE = DOCS_DIR / 'phase-12-7-execution-mode-{date}.md'
STARTED_REPORT = DOCS_DIR / 'phase-12-7-observation-started-{date}.md'
FINAL_REPORT = DOCS_DIR / 'phase-12-7-12h-observation-final-{date}.md'

WRAPPER = ORCH / 'scripts' / 'run_trading_cycle.sh'
FLEET_HEALTHCHECK = ORCH / 'scripts' / 'fleet_healthcheck.py'
MULTICYCLE_VALIDATOR = ORCH / 'scripts' / 'multicycle_validator.py'
RAW_SIGNAL = PRIMO_ROOT / 'output' / 'signals' / 'primo_multi_signal_latest.json'
RISK_SIGNAL = PRIMO_ROOT / 'output' / 'signals' / 'primo_risk_filtered_latest.json'
SHADOW_LOG = PRIMO_ROOT / 'output' / 'shadow' / 'primo_shadow_log.jsonl'
STATE_FILES = [
    TRADING_ROOT / 'freqtrade' / 'bots' / 'rsi' / 'user_data' / 'primo_signal_state.json',
    TRADING_ROOT / 'freqtrade' / 'bots' / 'momentum' / 'user_data' / 'primo_signal_state.json',
    TRADING_ROOT / 'freqtrade' / 'bots' / 'regime-hybrid' / 'user_data' / 'primo_signal_state.json',
]
FORBIDDEN_GLOBS = [
    TRADING_ROOT / 'freqtrade' / 'bots',
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def date_str(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).date().isoformat()


def ensure_dirs() -> None:
    for p in [STATE_DIR, LOG_DIR, REPORT_DIR, DOCS_DIR]:
        p.mkdir(parents=True, exist_ok=True)


def run_shell(cmd: str, timeout: int | None = None, cwd: Path = TRADING_ROOT) -> Tuple[int, str, str]:
    cp = subprocess.run(cmd, shell=True, cwd=str(cwd), text=True, capture_output=True, timeout=timeout)
    return cp.returncode, cp.stdout, cp.stderr


def run_cmd(args: List[str], timeout: int | None = None, cwd: Path = TRADING_ROOT) -> Tuple[int, str, str]:
    cp = subprocess.run(args, cwd=str(cwd), text=True, capture_output=True, timeout=timeout)
    return cp.returncode, cp.stdout, cp.stderr


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, indent=2, ensure_ascii=False))


def load_json(path: Path) -> Any:
    return json.loads(read_text(path))


def valid_json(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        json.loads(read_text(path))
        return True
    except Exception:
        return False


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.open('r', encoding='utf-8', errors='replace'))


def latest_wrapper_log() -> str:
    logs = sorted((ORCH / 'logs').glob('trading_cycle_*.log'))
    return str(logs[-1]) if logs else ''


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def snapshot_forbidden() -> Dict[str, str]:
    files: List[Path] = []
    for p in (TRADING_ROOT / 'freqtrade' / 'bots').glob('**/config*.json'):
        files.append(p)
    for p in (TRADING_ROOT / 'freqtrade' / 'bots').glob('**/*.py'):
        files.append(p)
    snap: Dict[str, str] = {}
    for p in sorted(set(files)):
        try:
            snap[str(p)] = sha256(p)
        except Exception:
            snap[str(p)] = 'MISSING_OR_UNREADABLE'
    return snap


def diff_forbidden(baseline: Dict[str, str], current: Dict[str, str]) -> List[str]:
    diffs: List[str] = []
    keys = sorted(set(baseline) | set(current))
    for k in keys:
        if baseline.get(k) != current.get(k):
            diffs.append(k)
    return diffs


def json_tool_valid(path: Path) -> bool:
    rc, _, _ = run_cmd([sys.executable, '-m', 'json.tool', str(path)])
    return rc == 0


def validate_state_files() -> Tuple[bool, str, Dict[str, Any]]:
    versions = set()
    bridge_versions = set()
    ok = True
    data_map = {}
    for p in STATE_FILES:
        if not json_tool_valid(p):
            ok = False
            continue
        try:
            data = load_json(p)
        except Exception:
            ok = False
            continue
        data_map[str(p)] = data
        versions.add(data.get('schema_version'))
        bridge_versions.add(data.get('bridge_version'))
    version = next(iter(versions)) if len(versions) == 1 else 'mixed'
    bridge = next(iter(bridge_versions)) if len(bridge_versions) == 1 else 'mixed'
    return ok, f'{version}|{bridge}', data_map


def riskguard_counts() -> Dict[str, Any]:
    if not valid_json(RISK_SIGNAL):
        return {}
    try:
        d = load_json(RISK_SIGNAL)
    except Exception:
        return {}
    return d.get('counts', {}) if isinstance(d, dict) else {}


def multicycle_status() -> Tuple[str, str]:
    rc, out, err = run_cmd([sys.executable, str(MULTICYCLE_VALIDATOR)], timeout=120)
    text = out + err
    if 'Status: GREEN' in text or 'Status: GREEN' in text:
        return 'GREEN', text
    if rc == 0:
        return 'OK', text
    return 'FAIL', text


def fleet_health_verdict() -> Tuple[str, str]:
    rc, out, err = run_cmd([sys.executable, str(FLEET_HEALTHCHECK)], timeout=120)
    text = out + err
    verdict = 'UNKNOWN'
    for line in text.splitlines():
        if 'Verdict:' in line:
            verdict = line.split('Verdict:', 1)[1].strip()
            break
    return verdict, text


def render_schedule(start: datetime) -> str:
    runs = [start + timedelta(hours=h) for h in (0, 3, 6, 9, 12)]
    lines = [
        '# Phase 12.7 — 12-Hour Observation Schedule',
        '',
        f'- Observation start UTC: {z(start)}',
        f'- Observation end UTC: {z(runs[-1])}',
        '',
        '## Fixed Runs',
    ]
    for i, ts in enumerate(runs, 1):
        lines.append(f'- Run {i}: {z(ts)} UTC (T+{(i-1)*3}h)')
    lines.extend([
        '',
        '## Per-Run Commands',
        '- fleet_healthcheck.py before wrapper',
        '- count ShadowLogger lines before wrapper',
        '- timeout 900 run_trading_cycle.sh',
        '- validate raw PrimoAgent JSON',
        '- validate RiskGuard JSON',
        '- validate all three state files',
        '- count ShadowLogger lines after wrapper',
        '- multicycle_validator.py',
        '- fleet_healthcheck.py after wrapper',
        '- append ledger row',
        '',
        '## Phase 13 Gate Criteria',
        '- GO only if at least 4 successful scheduled runs are completed across the 12-hour window',
        '- WAIT if observation completes with fewer than 4 successful scheduled runs',
        '- BLOCKED if dry_run=false, credentials, invalid state JSON, invalid RiskGuard output, ShadowLogger failure, RED fleet health, unexpected cron changes, or container restarts appear',
        '',
        '## Safety Rules',
        '- No live trading',
        '- No Freqtrade config or strategy changes',
        '- No container restarts',
        '- No cron migration or cron edits',
        '- No secrets in output',
        '',
    ])
    return '\n'.join(lines)


def write_context_file(template: Path, start: datetime, body: str) -> Path:
    p = Path(str(template).format(date=date_str(start)))
    write_text(p, body)
    return p


def emit_controller_created(start: datetime) -> Path:
    body = f"# Phase 12.7 Controller Created\n\n- Created UTC: {z(utcnow())}\n- Start UTC: {z(start)}\n- Execution mode: background / nohup if needed\n- Controller: {SCRIPT_DIR / 'run_12h_observation_gate.py'}\n- Ledger: {LEDGER}\n- Live log: {LOG_DIR / 'nohup_observation.log'}\n- Final report: {Path(str(FINAL_REPORT).format(date=date_str(start + timedelta(hours=12))))}\n"
    return write_context_file(CONTROLLER_CREATED, start, body)


def emit_execution_mode(start: datetime, mode: str, pid: int | None = None) -> Path:
    body = [
        '# Phase 12.7 Execution Mode',
        '',
        f'- Decision UTC: {z(utcnow())}',
        f'- Start UTC: {z(start)}',
        f'- End UTC: {z(start + timedelta(hours=12))}',
        f'- Mode: {mode}',
    ]
    if pid is not None:
        body.append(f'- PID: {pid}')
    body.extend([
        f'- Ledger: {LEDGER}',
        f'- Live log: {LOG_DIR / "nohup_observation.log"}',
        '',
    ])
    return write_context_file(EXECUTION_MODE, start, '\n'.join(body))


def emit_start_report(start: datetime, mode: str, pid: int | None = None) -> Path:
    runs = [start + timedelta(hours=h) for h in (0, 3, 6, 9, 12)]
    body = [
        '# Phase 12.7 Observation Started',
        '',
        'Observation status: STARTED',
        f'Execution mode: {mode}',
        f'Start UTC: {z(start)}',
        f'Expected end UTC: {z(start + timedelta(hours=12))}',
        '',
        '## Schedule',
    ]
    for i, ts in enumerate(runs, 1):
        body.append(f'- Run {i}: {z(ts)} UTC')
    if pid is not None:
        body.extend(['', f'- PID: {pid}'])
    body.extend([
        '',
        f'- Ledger: {LEDGER}',
        f'- Live log: {LOG_DIR / "nohup_observation.log"}',
        f'- Latest JSON: {LATEST_JSON}',
        f'- Latest Markdown: {LATEST_MD}',
        '',
        '- Safety: no cron migration, no live trading, no config/strategy changes, no container restarts',
        '',
    ])
    return write_context_file(STARTED_REPORT, start, '\n'.join(body))


def append_ledger(entry: Dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def write_latest_reports(start: datetime, results: List[Dict[str, Any]]) -> None:
    payload = {
        'observation_start_utc': z(start),
        'observation_end_utc': z(start + timedelta(hours=12)),
        'runs_completed': len(results),
        'results': results,
    }
    write_json(LATEST_JSON, payload)

    lines = [
        '# Phase 12.7 Observation Report (Rolling)',
        '',
        f'- Observation start UTC: {z(start)}',
        f'- Observation end UTC: {z(start + timedelta(hours=12))}',
        f'- Runs completed: {len(results)}',
        '',
        '| Run | Scheduled UTC | Exit | Fleet | Multicycle | Shadow Δ | State | Forbidden |',
        '|---|---|---:|---|---|---:|---|---|',
    ]
    for r in results:
        lines.append(
            f"| {r['run_index']} | {r['scheduled_at_utc']} | {r['wrapper_exit_code']} | {r['fleet_health_verdict']} | {r['multicycle_status']} | {r['shadow_lines_added']} | {r['state_schema_version']} | {'YES' if r['forbidden_changes_detected'] else 'no'} |"
        )
    write_text(LATEST_MD, '\n'.join(lines) + '\n')


def final_report(start: datetime, results: List[Dict[str, Any]]) -> Path:
    date = date_str(utcnow())
    path = Path(str(FINAL_REPORT).format(date=date))
    successful = sum(1 for r in results if r['wrapper_exit_code'] == 0 and r['result'] == 'PASS')
    blocked = any(r['result'] == 'BLOCKED' for r in results)
    overall = 'BLOCKED' if blocked else ('GO' if successful >= 4 else 'WAIT')
    lines = [
        '# Phase 12.7 — 12-Hour Observation Final Report',
        '',
        f'- Overall result: {"PASS" if overall == "GO" else "PARTIAL" if overall == "WAIT" else "FAIL"}',
        f'- Phase 13 recommendation: {overall}',
        f'- Observation start UTC: {z(start)}',
        f'- Observation end UTC: {z(start + timedelta(hours=12))}',
        '',
        '## Exact Schedule',
    ]
    for i, ts in enumerate([start + timedelta(hours=h) for h in (0, 3, 6, 9, 12)], 1):
        lines.append(f'- Run {i}: {z(ts)} UTC')
    lines.extend(['', '## Run Summary'])
    for r in results:
        lines.append(
            f"- Run {r['run_index']}: exit={r['wrapper_exit_code']}, fleet={r['fleet_health_verdict']}, multicycle={r['multicycle_status']}, shadowΔ={r['shadow_lines_added']}, state={r['state_schema_version']}, forbidden={'YES' if r['forbidden_changes_detected'] else 'no'}"
        )
    lines.extend([
        '',
        '## Safety Proof',
        '- No live trading enabled',
        '- No cronjobs migrated',
        '- No Freqtrade config or strategy changes',
        '- No intentional container restarts',
        '- No exchange credentials printed',
        '',
        '## Open Risks',
        '- BLOCK_ENTRY remains neutral/no-bias in helper by design',
        '- Observation window only validates dry-run safety, not live market execution',
        '',
        '## Next Steps',
        '- If GO: prepare Phase 13 cron migration plan',
        '- If WAIT: continue observation until >=4 successful scheduled runs complete',
        '- If BLOCKED: investigate the first blocked/RED run and remediate safely',
        '',
    ])
    write_text(path, '\n'.join(lines))
    return path


def run_single(run_index: int, scheduled_at: datetime, baseline_forbidden: Dict[str, str]) -> Dict[str, Any]:
    started = utcnow()
    pre_fleet_verdict, pre_fleet_text = fleet_health_verdict()
    shadow_before = count_lines(SHADOW_LOG)
    wrapper_log_before = latest_wrapper_log()
    run_log = LOG_DIR / f'run_{run_index:02d}_{scheduled_at.strftime("%Y%m%dT%H%M%SZ")}.log'
    cmd = f'timeout 900 {shlex.quote(str(WRAPPER))}'
    rc, out, err = run_shell(cmd, timeout=950)
    run_log.write_text(out + ('\n--- STDERR ---\n' + err if err else ''), encoding='utf-8')

    wrapper_log_after = latest_wrapper_log()
    raw_ok = json_tool_valid(RAW_SIGNAL)
    risk_ok = json_tool_valid(RISK_SIGNAL)
    state_ok, state_version, state_data = validate_state_files()
    shadow_after = count_lines(SHADOW_LOG)
    multi_status, multi_text = multicycle_status()
    post_fleet_verdict, post_fleet_text = fleet_health_verdict()
    forbidden_now = snapshot_forbidden()
    forbidden_diffs = diff_forbidden(baseline_forbidden, forbidden_now)
    forbidden_changes_detected = len(forbidden_diffs) > 0

    counts = riskguard_counts()
    state_schema_version = state_version.split('|', 1)[0] if '|' in state_version else state_version
    bridge_version = state_version.split('|', 1)[1] if '|' in state_version else ''

    critical = [
        not raw_ok,
        not risk_ok,
        not state_ok,
        post_fleet_verdict == 'RED',
        forbidden_changes_detected,
        rc not in (0,),
    ]
    result = 'BLOCKED' if any(critical[:5]) else ('PASS' if rc == 0 and raw_ok and risk_ok and state_ok and post_fleet_verdict in ('GREEN', 'YELLOW') and multi_status in ('GREEN', 'OK') else 'PARTIAL')

    entry = {
        'run_index': run_index,
        'scheduled_at_utc': z(scheduled_at),
        'started_at_utc': z(started),
        'finished_at_utc': z(utcnow()),
        'duration_seconds': round((utcnow() - started).total_seconds(), 3),
        'wrapper_exit_code': rc,
        'wrapper_log_path': wrapper_log_after,
        'wrapper_stdout_log_path': str(run_log),
        'pre_fleet_health_verdict': pre_fleet_verdict,
        'post_fleet_health_verdict': post_fleet_verdict,
        'riskguard_valid': risk_ok,
        'riskguard_counts': counts,
        'shadow_lines_before': shadow_before,
        'shadow_lines_after': shadow_after,
        'shadow_lines_added': max(0, shadow_after - shadow_before),
        'state_files_valid': state_ok,
        'state_schema_version': state_schema_version,
        'bridge_version': bridge_version,
        'fleet_health_verdict': post_fleet_verdict,
        'multicycle_status': multi_status,
        'forbidden_changes_detected': forbidden_changes_detected,
        'forbidden_diff_count': len(forbidden_diffs),
        'result': result,
        'notes': {
            'raw_json_valid': raw_ok,
            'wrapper_log_before': wrapper_log_before,
            'pre_fleet_health_snippet': pre_fleet_text[:4000],
            'post_fleet_health_snippet': post_fleet_text[:4000],
            'multicycle_snippet': multi_text[:4000],
        },
    }
    write_json(STATE_DIR / f'run_{run_index:02d}.json', entry)
    append_ledger(entry)
    return entry


def sleep_until(target: datetime) -> None:
    while True:
        now = utcnow()
        delta = (target - now).total_seconds()
        if delta <= 0:
            return
        time.sleep(min(delta, 60.0))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()

    ensure_dirs()
    start = utcnow()
    schedule = [start + timedelta(hours=h) for h in (0, 3, 6, 9, 12)]
    schedule_path = write_context_file(SCHEDULE_FILE, start, render_schedule(start))
    emit_controller_created(start)

    if args.plan_only:
        print(render_schedule(start))
        print(f'SCHEDULE_FILE={schedule_path}')
        return 0

    if not args.execute:
        print(render_schedule(start))
        print('Use --execute to start the controller.')
        return 0

    mode = 'background/nohup' if os.environ.get('OBSERVATION_BACKGROUND', '') == '1' else 'foreground'
    emit_execution_mode(start, mode)
    emit_start_report(start, mode)

    baseline_forbidden = snapshot_forbidden()
    results: List[Dict[str, Any]] = []
    overall_blocked = False
    for idx, sched in enumerate(schedule, 1):
        sleep_until(sched)
        result = run_single(idx, sched, baseline_forbidden)
        results.append(result)
        write_latest_reports(start, results)
        if result['result'] == 'BLOCKED':
            overall_blocked = True
        print(json.dumps(result, ensure_ascii=False))
        sys.stdout.flush()

    final_path = final_report(start, results)
    write_latest_reports(start, results)
    print(f'FINAL_REPORT={final_path}')
    print(f'LEDGER={LEDGER}')
    print(f'LATEST_JSON={LATEST_JSON}')
    print(f'LATEST_MD={LATEST_MD}')
    return 0 if not overall_blocked else 2


if __name__ == '__main__':
    raise SystemExit(main())
