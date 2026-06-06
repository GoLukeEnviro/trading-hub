#!/usr/bin/env python3
"""
Monthly Strategy Report v4.6
Unified Telegram-friendly monthly strategy summary.
"""

import subprocess
from datetime import datetime, timezone

FLEET_BOTS = {
    'trading-freqtrade-freqforge-1': {
        'dbs': ['/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite'],  # FIX-2026-06-06: removed stale fallback /freqtrade/tradesv3.dryrun.sqlite
        'label': 'FreqForge',
        'strategy': 'FreqForge_Override',
    },
    'trading-freqtrade-regime-hybrid-1': {
        'dbs': ['/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite'],
        'label': 'Regime-Hybrid',
        'strategy': 'RegimeSwitchingHybrid_v7',
    },
    'trading-freqtrade-freqforge-canary-1': {
        'dbs': ['/freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite'],
        'label': 'Canary',
        'strategy': 'FreqForge_Override (Spot)',
    },
    'trading-freqai-rebel-1': {
        'dbs': ['/freqtrade/user_data/tradesv3.freqai_rebel.dryrun.sqlite'],  # FIX-2026-06-06: bot-specific DB name
        'label': 'Rebel',
        'strategy': 'RebelLiquidation+XGBoost',
    },
}


def run(cmd, timeout=20):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def stats(container, dbs):
    sql = (
        'SELECT count(*), '
        'round(sum(close_profit_abs),4), '
        'round(100.0*sum(case when close_profit>0 then 1 else 0 end)/max(count(*),1),1), '
        'round(avg(case when close_profit>0 then close_profit_abs end),4), '
        'round(avg(case when close_profit<0 then close_profit_abs end),4), '
        'round(COALESCE(sum(case when close_profit>0 then close_profit_abs else 0 end),0) '
        '/max(abs(COALESCE(sum(case when close_profit<0 then close_profit_abs else 0 end),0)),0.0001),2) '
        'FROM trades WHERE is_open=0;'
    )
    for db in dbs:
        rc, out, _ = run(['docker', 'exec', container, 'sqlite3', db, sql])
        if rc == 0 and '|' in out:
            parts = out.split('|')
            trades = int(parts[0])
            if trades == 0:
                continue
            return {
                'trades': trades,
                'pnl': float(parts[1]),
                'wr': float(parts[2]),
                'avg_win': float(parts[3]) if parts[3] else 0.0,
                'avg_loss': float(parts[4]) if parts[4] else 0.0,
                'pf': float(parts[5]) if len(parts) > 5 and parts[5] else 0.0,
            }
    return None


rows = []
for container, info in FLEET_BOTS.items():
    row = stats(container, info['dbs'])
    if row:
        row['label'] = info['label']
        row['strategy'] = info['strategy']
        row['status'] = 'QUARANTINE' if info['label'] == 'Rebel' else ('LOSS ASYM' if row['pnl'] < 0 and row['wr'] > 60 else ('PROFITABLE' if row['pnl'] > 0 else 'LOSING'))
        rows.append(row)

rows.sort(key=lambda x: x['pnl'], reverse=True)
now = datetime.now(timezone.utc).strftime('%Y-%m')
total_pnl = sum(r['pnl'] for r in rows)
total_trades = sum(r['trades'] for r in rows)
best = rows[0] if rows else None
worst = rows[-1] if rows else None

lines = [
    f'📆 Monthly Strategy Report — {now} UTC',
    '',
    'PROFITABILITÄT',
    f"• Fleet {total_pnl:+.2f}U | Trades {total_trades}",
    f"• Best {best['label']} {best['pnl']:+.2f}U | Worst {worst['label']} {worst['pnl']:+.2f}U" if best and worst else '• Keine Daten',
    '',
    'FLEET STATUS',
]
for row in rows[:4]:
    lines.append(f"• {row['label']}: {row['pnl']:+.2f}U | WR {row['wr']:.1f}% | PF {row['pf']:.2f} | {row['status']}")
lines += [
    '',
    'SIGNAL',
    '• Monatsreport auf abgeschlossenen Trades, nicht auf Live-Signalen',
    f"• Strategien: {', '.join(r['strategy'] for r in rows[:3]) if rows else 'n/a'}",
    '',
    'SAFETY',
    '• dry_run-Fleet vorausgesetzt | keine Live-Ausführung',
    '• Rebel max_open_trades=0 bleibt intentionale Quarantäne',
    '',
    'VORSCHLÄGE',
]
if any(r['label'] == 'Regime-Hybrid' and r['pnl'] < 0 for r in rows):
    lines.append('• Regime-Hybrid Exit-/Loss-Asymmetrie reviewen')
elif rows:
    lines.append('• Keine Sofortaktion nötig')
if any(r['label'] == 'Rebel' and r['wr'] < 35 for r in rows):
    lines.append('• Rebel weiter quarantänisieren')
else:
    lines.append('• Gewinner nur weiter beobachten, nicht hochskalieren')
print('\n'.join(lines))
