#!/usr/bin/env python3
import sqlite3
import subprocess
from datetime import datetime, timezone

DB = '/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data/tradesv3.dryrun.sqlite'  # FIX-2026-06-06: switched from docker volume to bind-mount path

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
    return r.stdout.strip()

count = 0
try:
    conn = sqlite3.connect(DB)
    count = conn.execute('SELECT COUNT(*) FROM trades').fetchone()[0]
    open_count = conn.execute('SELECT COUNT(*) FROM trades WHERE is_open = 1').fetchone()[0]
except Exception:
    count = -1
    open_count = -1

logs = run("docker logs freqai-rebel --since 40m 2>&1 | grep -E 'Done training|inferencing pairlist|Bot heartbeat|Entering|Order|buy|sell' | tail -12")
now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

if count > 0:
    print(f'REBEL 30M CHECK — {now}\nTrades={count} | open={open_count}\nSTATUS: AKTIV — erste Trades vorhanden\n\nRecent logs:\n{logs}')
else:
    print(f'REBEL 30M CHECK — {now}\nTrades={count} | open={open_count}\nSTATUS: NOCH 0 TRADES — Modell trainiert/inferenced, aber noch kein Entry\n\nRecent logs:\n{logs}\n\nEmpfehlung: In ~6h Classifier-Output / Entry-Filter pr\u00fcfen, falls weiter 0 Trades.')
