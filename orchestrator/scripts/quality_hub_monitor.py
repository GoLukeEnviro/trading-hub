#!/usr/bin/env python3
"""
Quality Hub Monitor v4.6

Reliable script-backed replacement for the former LLM job.
Writes a fuller Markdown audit to orchestrator/logs/quality-hub-report.md
and prints a compact Telegram/origin summary with the standard section order:
PROFITABILITÄT / FLEET STATUS / SIGNAL / SAFETY / VORSCHLÄGE
"""

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path('/home/hermes/projects/trading')
LOG_PATH = BASE / 'orchestrator/logs/quality-hub-report.md'
CRON_JSON = Path('/opt/data/profiles/orchestrator/cron/jobs.json')
SIGNAL_PATH = BASE / 'ai-hedge-fund-crypto/output/hermes_signal.json'
DRAWDOWN_PATH = BASE / 'orchestrator/state/drawdown_state.json'

BOTS = {
    'freqtrade-freqforge': {
        'label': 'FreqForge',
        'config': BASE / 'freqforge/config/config_freqforge_dryrun.json',
        'dbs': ['/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite', '/freqtrade/tradesv3.dryrun.sqlite'],
    },
    'freqtrade-freqforge-canary': {
        'label': 'Canary',
        'config': BASE / 'freqforge-canary/config/config_canary_dryrun.json',
        'dbs': ['/freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite'],
    },
    'freqtrade-regime-hybrid': {
        'label': 'Regime-Hybrid',
        'config': BASE / 'freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json',
        'dbs': ['/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite'],
    },
    'freqai-rebel': {
        'label': 'Rebel',
        'config': None,
        'dbs': ['/freqtrade/tradesv3.dryrun.sqlite', '/freqtrade/user_data/tradesv3.dryrun.sqlite'],
    },
}


def ts_utc():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def load_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None


def run(cmd, timeout=20):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def bot_stats(container, db_paths):
    sql = (
        "SELECT count(*), "
        "round(COALESCE(sum(close_profit_abs),0),4), "
        "round(100.0*COALESCE(sum(case when close_profit>0 then 1 else 0 end),0)/max(count(*),1),1), "
        "round(COALESCE(sum(case when close_profit>0 then close_profit_abs else 0 end),0)"
        "/max(abs(COALESCE(sum(case when close_profit<0 then close_profit_abs else 0 end),0)),0.0001),2) "
        "FROM trades WHERE is_open=0;"
    )
    for db in db_paths:
        rc, out, _ = run(['docker', 'exec', container, 'sqlite3', db, sql], timeout=20)
        if rc == 0 and '|' in out:
            parts = out.split('|')
            try:
                trades = int(parts[0])
                pnl = float(parts[1])
                wr = float(parts[2])
                pf = float(parts[3])
                return {'trades': trades, 'pnl': pnl, 'wr': wr, 'pf': pf, 'db_path_used': db}
            except Exception:
                continue
    return {'trades': 0, 'pnl': 0.0, 'wr': 0.0, 'pf': 0.0, 'db_path_used': None}


def bot_open_count(container, db_paths):
    sql = 'SELECT count(*) FROM trades WHERE is_open=1;'
    for db in db_paths:
        rc, out, _ = run(['docker', 'exec', container, 'sqlite3', db, sql], timeout=20)
        if rc == 0 and out.strip().isdigit():
            return int(out.strip())
    return 0


def read_rebel_config_value(key):
    rc, out, _ = run([
        'docker', 'exec', 'freqai-rebel', 'python3', '-c',
        f"import json; c=json.load(open('/freqtrade/user_data/config.json')); print(c.get({key!r}, ''))"
    ], timeout=20)
    return out.strip() if rc == 0 else ''


def config_snapshot():
    dry = []
    mot = []
    for container, info in BOTS.items():
        label = info['label']
        if info['config'] is not None and info['config'].exists():
            cfg = load_json(info['config']) or {}
            dry.append(f"{label}={'T' if cfg.get('dry_run') is True else 'F'}")
            mot.append(f"{label}={cfg.get('max_open_trades', '?')}")
        else:
            dry_val = read_rebel_config_value('dry_run')
            mot_val = read_rebel_config_value('max_open_trades')
            dry.append(f"{label}={'T' if dry_val.lower() == 'true' else 'F'}")
            mot.append(f"{label}={mot_val or '?'}")
    return ', '.join(dry), ', '.join(mot)


def collect_fleet():
    fleet = []
    total_pnl = 0.0
    total_open = 0
    total_trades = 0
    for container, info in BOTS.items():
        stats = bot_stats(container, info['dbs'])
        open_count = bot_open_count(container, info['dbs'])
        if info['label'] == 'Rebel':
            rebel_mot = read_rebel_config_value('max_open_trades')
            status = 'RUNNING_INFERENCE_ONLY' if rebel_mot == '0' else 'VISIBILITY_GAP'
        else:
            status = 'LOSS' if stats['pnl'] < 0 and stats['pf'] < 1 else 'OK'
        row = {
            'label': info['label'],
            'trades': stats['trades'],
            'pnl': stats['pnl'],
            'wr': stats['wr'],
            'pf': stats['pf'],
            'open': open_count,
            'status': status,
        }
        total_pnl += row['pnl']
        total_open += row['open']
        total_trades += row['trades']
        fleet.append(row)
    fleet.sort(key=lambda x: x['pnl'], reverse=True)
    return fleet, total_pnl, total_open, total_trades


def signal_summary():
    if not SIGNAL_PATH.exists():
        return {'error': 'hermes_signal.json fehlt'}
    data = load_json(SIGNAL_PATH) or {}
    pairs = data.get('pairs', {})
    age_min = (time.time() - SIGNAL_PATH.stat().st_mtime) / 60
    accepted = 0
    watch_only = 0
    rejected = 0
    hot = []
    for pair, meta in pairs.items():
        action = str(meta.get('action', 'hold')).upper()
        conf = float(meta.get('confidence', 0) or 0)
        verdict = str(meta.get('verdict', '')).upper()
        if verdict == 'ACCEPTED':
            accepted += 1
        elif verdict == 'WATCH_ONLY':
            watch_only += 1
        elif verdict:
            rejected += 1
        if action in {'BUY', 'SELL', 'LONG', 'SHORT'} and conf > 0:
            hot.append(f"{pair.split('/')[0]} {action} {conf:.2f}")
    if not any((accepted, watch_only, rejected)) and pairs:
        for meta in pairs.values():
            action = str(meta.get('action', 'hold')).upper()
            if action in {'BUY', 'SELL', 'LONG', 'SHORT'}:
                accepted += 1
            else:
                watch_only += 1
    return {
        'age_min': age_min,
        'pair_count': len(pairs),
        'risk_mode': data.get('global_risk_mode', 'unknown'),
        'accepted': accepted,
        'watch_only': watch_only,
        'rejected': rejected,
        'hot': hot[:3],
    }


def cron_summary():
    data = load_json(CRON_JSON) or {}
    jobs = data.get('jobs', []) if isinstance(data, dict) else []
    enabled = sum(1 for j in jobs if isinstance(j, dict) and j.get('enabled'))
    errors = [j.get('name', '?') for j in jobs if isinstance(j, dict) and j.get('enabled') and j.get('last_status') == 'error']
    return enabled, errors


def permission_status():
    rc, out, _ = run(['find', '/opt/data/profiles/orchestrator/cron', '-type', 'f', '-user', '0', '-group', '0'], timeout=10)
    if rc != 0:
        return 'CHECK_FAILED'
    count = len([line for line in out.splitlines() if line.strip()])
    return 'CLEAN' if count == 0 else f'{count} drift files'


def disk_status():
    total, used, free = shutil.disk_usage('/')
    pct = (used / total) * 100 if total else 0
    return f"{used // (1024**3)}G/{total // (1024**3)}G ({pct:.0f}%)"


def drawdown_summary():
    state = load_json(DRAWDOWN_PATH) or {}
    if not state:
        return {'drawdown_pct': None, 'portfolio_pnl': None, 'reachable': None, 'total': None}
    return {
        'drawdown_pct': state.get('drawdown_pct'),
        'portfolio_pnl': state.get('portfolio_pnl'),
        'reachable': state.get('reachable_bots'),
        'total': state.get('total_bots'),
    }


def build_markdown(fleet, total_pnl, total_open, total_trades, sig, dry_snapshot, mot_snapshot, perm, cron_enabled, cron_errors, dd):
    lines = [
        f"# Quality-Hub Report — {ts_utc()}",
        '',
        '## PROFITABILITÄT',
        '',
        f"- Fleet-PnL gesamt: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f} USDT",
        f"- Trades gesamt: {total_trades}",
        f"- Offene Trades: {total_open}",
        f"- Drawdown: {dd['drawdown_pct'] if dd['drawdown_pct'] is not None else 'n/a'}%",
        '',
        '| Bot | Trades | PnL | Winrate | PF | Open | Status |',
        '|---|---:|---:|---:|---:|---:|---|',
    ]
    for bot in fleet:
        lines.append(f"| {bot['label']} | {bot['trades']} | {bot['pnl']:+.2f} | {bot['wr']:.1f}% | {bot['pf']:.2f} | {bot['open']} | {bot['status']} |")
    lines += [
        '',
        '## FLEET STATUS',
        '',
        f"- Bots mit Daten: {len(fleet)}",
        f"- Erreichbarkeit aus Drawdown-State: {dd['reachable']}/{dd['total']}" if dd['reachable'] is not None else '- Erreichbarkeit: n/a',
        '',
        '## SIGNAL',
        '',
    ]
    if sig.get('error'):
        lines.append(f"- Fehler: {sig['error']}")
    else:
        lines.append(f"- Alter: {sig['age_min']:.1f} min")
        lines.append(f"- Risk-Mode: {sig['risk_mode']}")
        lines.append(f"- ACCEPTED/WATCH_ONLY/REJECTED: {sig['accepted']}/{sig['watch_only']}/{sig['rejected']}")
        lines.append(f"- Top-Signale: {', '.join(sig['hot']) if sig['hot'] else 'keine starken Signale'}")
    lines += [
        '',
        '## SAFETY',
        '',
        f"- dry_run: {dry_snapshot}",
        f"- max_open_trades: {mot_snapshot}",
        f"- Cron aktiv: {cron_enabled}",
        f"- Cron-Fehler: {', '.join(cron_errors) if cron_errors else 'keine'}",
        f"- Permissions: {perm}",
        f"- Disk: {disk_status()}",
        '',
        '## VORSCHLÄGE',
        '',
    ]
    suggestions = []
    if cron_errors:
        suggestions.append(f"Cron-Fehler priorisieren: {cron_errors[0]}")
    if any(bot['pnl'] < 0 and bot['pf'] < 1 for bot in fleet if bot['label'] != 'Rebel'):
        bad = next(bot['label'] for bot in fleet if bot['pnl'] < 0 and bot['pf'] < 1 and bot['label'] != 'Rebel')
        suggestions.append(f"{bad}: Exit-/Loss-Asymmetrie prüfen")
    if not suggestions:
        suggestions.append('Keine Sofortaktion nötig')
    suggestions.append('Rebel VISIBILITY_GAP dokumentieren; inference-only nur bei explizitem max_open_trades=0')
    for item in suggestions[:2]:
        lines.append(f"1. {item}" if item == suggestions[0] else f"2. {item}")
    return '\n'.join(lines) + '\n'


def build_compact(fleet, total_pnl, total_open, sig, dry_snapshot, mot_snapshot, perm, cron_errors, dd):
    best = fleet[0] if fleet else None
    worst = fleet[-1] if fleet else None
    lines = [
        f"🧭 Quality Hub — {ts_utc()}",
        '',
        'PROFITABILITÄT',
        f"• Fleet {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}U | Open {total_open} | DD {dd['drawdown_pct'] if dd['drawdown_pct'] is not None else 'n/a'}%",
        f"• Best {best['label']} {best['pnl']:+.2f}U | Worst {worst['label']} {worst['pnl']:+.2f}U" if best and worst else '• Keine Fleet-Daten',
        '',
        'FLEET STATUS',
    ]
    for bot in fleet[:4]:
        lines.append(f"• {bot['label']}: {bot['pnl']:+.2f}U | WR {bot['wr']:.1f}% | PF {bot['pf']:.2f} | open {bot['open']} | {bot['status']}")
    lines += ['', 'SIGNAL']
    if sig.get('error'):
        lines.append(f"• ERROR: {sig['error']}")
    else:
        lines.append(f"• {'fresh' if sig['age_min'] < 30 else 'STALE'} | {sig['age_min']:.0f} min | mode={sig['risk_mode']} | A/W/R {sig['accepted']}/{sig['watch_only']}/{sig['rejected']}")
        lines.append(f"• {', '.join(sig['hot']) if sig['hot'] else 'keine starken Signale'}")
    lines += [
        '',
        'SAFETY',
        f"• dry_run {dry_snapshot}",
        f"• max_open {mot_snapshot}",
        f"• Cron {'; '.join(cron_errors[:2]) if cron_errors else 'ok'} | Permissions {perm} | Disk {disk_status()}",
        '',
        'VORSCHLÄGE',
    ]
    suggestions = []
    if cron_errors:
        suggestions.append(f"{cron_errors[0]} fix/verify")
    if any(bot['pnl'] < 0 and bot['pf'] < 1 for bot in fleet if bot['label'] != 'Rebel'):
        bad = next(bot['label'] for bot in fleet if bot['pnl'] < 0 and bot['pf'] < 1 and bot['label'] != 'Rebel')
        suggestions.append(f"{bad} Exit-/RR-Review")
    if not suggestions:
        suggestions.append('Keine Sofortaktion nötig')
    suggestions.append('Rebel-Quarantäne beibehalten')
    for item in suggestions[:2]:
        lines.append(f"• {item}")
    return '\n'.join(lines)


def main():
    fleet, total_pnl, total_open, total_trades = collect_fleet()
    sig = signal_summary()
    dry_snapshot, mot_snapshot = config_snapshot()
    perm = permission_status()
    cron_enabled, cron_errors = cron_summary()
    dd = drawdown_summary()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(build_markdown(fleet, total_pnl, total_open, total_trades, sig, dry_snapshot, mot_snapshot, perm, cron_enabled, cron_errors, dd), encoding='utf-8')
    print(build_compact(fleet, total_pnl, total_open, sig, dry_snapshot, mot_snapshot, perm, cron_errors, dd))


if __name__ == '__main__':
    main()
