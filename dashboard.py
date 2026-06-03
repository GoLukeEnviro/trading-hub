#!/usr/bin/env python3
"""
Trading Fleet Dashboard — Single-file Flask app.
Serves a dark-theme HTML dashboard with bot stats, AI signals, and system status.

Start: python3 dashboard.py
Open:  http://<host>:PORT
"""

import sqlite3
import subprocess
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import Flask, render_template_string

# ── Configuration (tune paths / ports here) ──────────────────────────────────
PORT = 5000
PROJECT_ROOT = Path('/home/hermes/projects/trading')
GUARDIAN_CONTAINER = 'trading-guardian'
GUARDIAN_REPO_ROOT = '/guardian/data'
SIGNAL_FRESHNESS_LIMIT_MINUTES = 45.0
PRIMO_FRESHNESS_LIMIT_MINUTES = 45.0
SHADOW_STALE_MINUTES = 24 * 60.0

# Docker container names for the trading bots
BOT_CONTAINERS = {
    'regime-hybrid': 'freqtrade-regime-hybrid',
    'freqforge': 'freqtrade-freqforge',
    'freqforge-canary': 'freqtrade-freqforge-canary',
    'freqai-rebel': 'freqai-rebel',
}

# Container-internal SQLite paths; we try a small fallback chain because the
# exact filename varies between bot images / historical deployments.
DB_CANDIDATES = {
    'regime-hybrid': [
        '/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite',
        '/freqtrade/user_data/tradesv3.regime-hybrid.dryrun.sqlite',
        '/freqtrade/user_data/tradesv3.regime.dryrun.sqlite',
    ],
    'freqforge': [
        '/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite',
    ],
    'freqforge-canary': [
        '/freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite',
        '/freqtrade/user_data/tradesv3.freqforge-canary.dryrun.sqlite',
        '/freqtrade/user_data/tradesv3.freqforge.canary.dryrun.sqlite',
    ],
    'freqai-rebel': [
        '/freqtrade/user_data/tradesv3.rebel.dryrun.sqlite',
        '/freqtrade/user_data/tradesv3.freqai-rebel.dryrun.sqlite',
    ],
}

# Mapping: bot_id -> display name (title case)
BOT_DISPLAY = {
    'regime-hybrid': 'Regime-Hybrid',
    'freqforge': 'FreqForge',
    'freqforge-canary': 'FreqForge-Canary',
    'freqai-rebel': 'FreqAI-Rebel',
}

# Additional containers shown in system status (not tied to a single DB)
EXTRA_CONTAINERS = {
    'ai-hedge-fund-crypto': 'ai-hedge-fund-crypto',
    'trading-guardian': 'trading-guardian',
}

SIGNAL_JSON = '/app/output/latest/hermes_signal.json'
OBSERVATION_REPORT = '/app/output/latest/observation_report.json'
PRIMO_SIGNAL_STATE_PATH = '/freqtrade/user_data/primo_signal_state.json'
RISKGUARD_STATE_REL = 'orchestrator/state/riskguard/riskguard_state.json'
RISKGUARD_HEALTH_REL = 'orchestrator/state/riskguard/riskguard_health.json'
SHADOW_DECISIONS_REL = 'var/freqforge/shadow_decisions.jsonl'

# ── Helpers ───────────────────────────────────────────────────────────────────

app = Flask(__name__)


def format_duration_minutes(minutes):
    """Convert minutes to HH:MM string. Returns '-' on None/0."""
    if minutes is None:
        return '-'
    try:
        value = float(minutes)
    except Exception:
        return '-'
    if value <= 0:
        return '-'
    total_minutes = int(value)
    hrs = total_minutes // 60
    mins = total_minutes % 60
    return f'{hrs}h {mins:02d}m'


def parse_sqlite_timestamp(raw):
    """Parse sqlite timestamps that may be ISO strings or epoch seconds."""
    if raw in (None, ''):
        return None
    if isinstance(raw, (int, float)):
        ts = float(raw)
        if ts > 10_000_000_000:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    text = str(raw).strip()
    if not text:
        return None
    if text.isdigit():
        return parse_sqlite_timestamp(int(text))
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
def run_docker_exec(container, args, timeout=20):
    """Run a docker exec command and return (ok, stdout, stderr)."""
    cmd = ['docker', 'exec', container, *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode == 0, proc.stdout, proc.stderr
    except Exception as exc:
        return False, '', str(exc)


def first_existing_path_in_container(container, candidates):
    """Return the first path that exists inside the container."""
    shell = 'for p in "$@"; do [ -f "$p" ] && printf "%s\n" "$p" && exit 0; done; exit 1'
    ok, stdout, _ = run_docker_exec(container, ['sh', '-lc', shell, 'sh', *candidates], timeout=12)
    return stdout.strip() if ok and stdout.strip() else None


def docker_sqlite_query(container, db_path, sql):
    """Run sqlite3 inside a container via docker exec and return stdout."""
    ok, stdout, _ = run_docker_exec(container, ['sqlite3', '-noheader', '-separator', '|', db_path, sql], timeout=20)
    if not ok:
        return None
    return stdout.strip()


def read_container_file(container, path):
    """Read a file from a container via docker exec cat."""
    ok, stdout, _ = run_docker_exec(container, ['cat', path], timeout=12)
    return stdout if ok else None



def format_display_timestamp(value):
    """Format a timestamp-like value as UTC for display."""
    if value is None or value == '':
        return None
    if isinstance(value, str) and value.endswith(' UTC'):
        return value
    dt = parse_sqlite_timestamp(value)
    if dt is None:
        return str(value)
    return dt.strftime('%Y-%m-%d %H:%M:%S UTC')



def format_age_label(minutes):
    """Render a minute value as a compact age string."""
    if minutes is None:
        return None
    try:
        value = float(minutes)
    except Exception:
        return str(minutes)
    if value < 60:
        return f'{value:.1f} min'
    hours = value / 60.0
    if hours < 24:
        return f'{hours:.1f} h'
    days = hours / 24.0
    if days < 7:
        return f'{days:.1f} d'
    whole_days = int(days)
    rem_hours = int(hours % 24)
    return f'{whole_days}d {rem_hours:02d}h'



def format_number(value, digits=2):
    """Format a numeric value or return a safe placeholder."""
    if value in (None, ''):
        return '—'
    try:
        return f'{float(value):.{digits}f}'
    except Exception:
        return str(value)



def normalize_pair_name(value):
    """Normalize pair strings like BTC/USDT:USDT -> BTC/USDT."""
    if not value:
        return ''
    text = str(value).strip().upper()
    if ':' in text:
        text = text.split(':', 1)[0]
    return text



def status_badge_class(value):
    """Map a semantic status label to one of the standard badge classes."""
    text = str(value or '').strip().lower().replace(' ', '_').replace('-', '_')
    mapping = {
        'aktiv': 'badge-aktiv',
        'running': 'badge-running',
        'fresh': 'badge-aktiv',
        'ok': 'badge-aktiv',
        'accepted': 'badge-aktiv',
        'allow': 'badge-aktiv',
        'approve': 'badge-aktiv',
        'alive': 'badge-aktiv',
        'risk_on': 'badge-aktiv',
        'active': 'badge-aktiv',
        'idle': 'badge-idle',
        'watch_only': 'badge-idle',
        'observe': 'badge-idle',
        'uncertain': 'badge-idle',
        'neutral': 'badge-idle',
        'hold': 'badge-idle',
        'reduce_size': 'badge-idle',
        'problem': 'badge-problem',
        'stale': 'badge-problem',
        'block_entry': 'badge-problem',
        'blocked': 'badge-problem',
        'risk_off': 'badge-problem',
        'veto': 'badge-problem',
        'missed_risk': 'badge-problem',
        'false_negative_review': 'badge-problem',
        'degraded': 'badge-problem',
        'missing': 'badge-missing',
        'not_found': 'badge-missing',
        'na': 'badge-missing',
        'n/a': 'badge-missing',
    }
    return mapping.get(text, 'badge-idle')



def read_project_file_via_guardian(relative_path):
    """Read a repo file via the guardian container, with a local fallback."""
    local_path = PROJECT_ROOT / relative_path
    if local_path.exists():
        try:
            return local_path.read_text(encoding='utf-8')
        except Exception:
            pass
    container_path = f'{GUARDIAN_REPO_ROOT}/{relative_path}'
    raw = read_container_file(GUARDIAN_CONTAINER, container_path)
    return raw



def get_container_mtime(container, path):
    """Return the file mtime from inside a container as a UTC datetime."""
    ok, stdout, _ = run_docker_exec(container, ['stat', '-c', '%Y', path], timeout=12)
    if not ok:
        return None
    text = stdout.strip()
    if not text:
        return None
    try:
        return datetime.fromtimestamp(int(float(text)), tz=timezone.utc)
    except Exception:
        return None



def query_bot_via_docker(bot_id):
    """Read bot trade statistics from the bot container via docker exec."""
    result = {
        'db_found': False,
        'db_path': None,
        'total_trades': 0,
        'wins': 0,
        'profit_abs': 0.0,
        'avg_profit_pct': 0.0,
        'avg_duration_minutes': None,
        'best_trade': None,
        'worst_trade': None,
        'total_stake': 0.0,
        'last_activity': None,
        'error': None,
    }

    container = BOT_CONTAINERS.get(bot_id)
    candidates = DB_CANDIDATES.get(bot_id, [])
    if not container:
        result['error'] = 'container_missing'
        return result

    try:
        db_path = first_existing_path_in_container(container, candidates)
        if not db_path:
            result['error'] = 'db_missing'
            return result
        result['db_found'] = True
        result['db_path'] = db_path

        trade_columns_raw = docker_sqlite_query(container, db_path, 'PRAGMA table_info(trades);')
        trade_columns = set()
        if trade_columns_raw:
            for line in trade_columns_raw.splitlines():
                parts = line.split('|')
                if len(parts) >= 2 and parts[1]:
                    trade_columns.add(parts[1])

        profit_abs_col = (
            'close_profit_abs' if 'close_profit_abs' in trade_columns else
            'profit_abs' if 'profit_abs' in trade_columns else
            'realized_profit' if 'realized_profit' in trade_columns else
            None
        )
        profit_ratio_col = (
            'close_profit' if 'close_profit' in trade_columns else
            'profit_ratio' if 'profit_ratio' in trade_columns else
            None
        )
        if not profit_abs_col or not profit_ratio_col:
            result['error'] = 'schema_unsupported'
            return result

        sql = f"""
        SELECT
            COUNT(id) AS total_trades,
            COALESCE(SUM(CASE WHEN {profit_ratio_col} > 0 THEN 1 ELSE 0 END), 0) AS winning_trades,
            COALESCE(SUM({profit_abs_col}), 0) AS total_profit_abs,
            COALESCE(AVG({profit_ratio_col}) * 100, 0) AS avg_profit_pct,
            COALESCE(AVG(CASE WHEN is_open = 0 AND close_date IS NOT NULL AND open_date IS NOT NULL
                              THEN (julianday(close_date) - julianday(open_date)) * 24.0 * 60.0 END), 0)
                               AS avg_duration_minutes,
            MAX({profit_abs_col}) AS best_trade,
            MIN({profit_abs_col}) AS worst_trade,
            COALESCE(SUM(stake_amount), 0) AS total_stake,
            MAX(COALESCE(close_date, open_date)) AS last_activity
        FROM trades
        """
        raw = docker_sqlite_query(container, db_path, sql)
        if not raw:
            result['error'] = 'query_failed'
            return result

        row = raw.splitlines()[0].strip()
        parts = row.split('|')
        if len(parts) < 9:
            result['error'] = 'query_parse_error'
            return result

        def as_int(value):
            try:
                return int(float(value)) if value not in (None, '') else 0
            except Exception:
                return 0

        def as_float(value):
            try:
                return float(value) if value not in (None, '') else 0.0
            except Exception:
                return 0.0

        result['total_trades'] = as_int(parts[0])
        result['wins'] = as_int(parts[1])
        result['profit_abs'] = as_float(parts[2])
        result['avg_profit_pct'] = as_float(parts[3])
        result['avg_duration_minutes'] = as_float(parts[4]) if parts[4] not in (None, '') else None
        result['best_trade'] = as_float(parts[5]) if parts[5] not in (None, '') else None
        result['worst_trade'] = as_float(parts[6]) if parts[6] not in (None, '') else None
        result['total_stake'] = abs(as_float(parts[7]))
        result['last_activity'] = parts[8] or None

        distinct_raw = docker_sqlite_query(
            container,
            db_path,
            'SELECT DISTINCT pair FROM trades WHERE pair IS NOT NULL AND pair != "" ORDER BY pair;'
        )
        distinct_pairs = []
        if distinct_raw:
            distinct_pairs = [line.strip() for line in distinct_raw.splitlines() if line.strip()]
        result['distinct_pairs'] = distinct_pairs
        result['distinct_pair_count'] = len(distinct_pairs)
        result['normalized_pairs'] = sorted({normalize_pair_name(pair) for pair in distinct_pairs if pair})
        return result
    except Exception as exc:
        result['error'] = str(exc)
        return result



def determine_bot_status_via_docker(stats, container_state='not found'):
    """Classify a bot as aktiv, problem, or idle."""
    error = stats.get('error')
    if error in {'container_missing', 'query_failed', 'query_parse_error'}:
        return 'problem'
    if not stats.get('db_found'):
        return 'idle' if container_state == 'running' else 'problem'

    if stats.get('total_trades', 0) <= 0:
        return 'idle'

    last_activity = parse_sqlite_timestamp(stats.get('last_activity'))
    if last_activity is None:
        return 'problem'

    age = datetime.now(timezone.utc) - last_activity
    if age <= timedelta(minutes=10):
        return 'aktiv'
    return 'problem'



def get_ai_signal_via_docker():
    """Read hermes_signal.json from the ai-hedge-fund-crypto container."""
    container = EXTRA_CONTAINERS.get('ai-hedge-fund-crypto', 'ai-hedge-fund-crypto')
    raw = read_container_file(container, SIGNAL_JSON)
    if raw is None:
        return None, 'Signal-Datei nicht gefunden oder Container offline', None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, 'Signal-Datei nicht gefunden oder ungültig', None
    except Exception:
        return None, 'Signal-Datei nicht gefunden oder ungültig', None

    items = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ('signals', 'results', 'data'):
            if isinstance(data.get(key), list):
                items = data[key]
                break
        if items is None and isinstance(data.get('pairs'), dict):
            items = []
            for pair_name, payload in sorted(data['pairs'].items()):
                if not isinstance(payload, dict):
                    continue
                payload = dict(payload)
                payload.setdefault('pair', pair_name)
                items.append(payload)
        if items is None and all(k in data for k in ('pair', 'signal')):
            items = [data]

    if not isinstance(items, list):
        return None, 'Signal-Datei nicht gefunden oder ungültig', data

    signals = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_signal = item.get('signal', item.get('action', 'hold'))
        signal = str(raw_signal).strip().lower()
        if signal in {'buy', 'long'}:
            signal = 'long'
        elif signal in {'sell', 'short'}:
            signal = 'short'
        elif signal not in {'hold', 'neutral', 'none'}:
            signal = 'hold'
        else:
            signal = 'hold' if signal in {'neutral', 'none'} else signal
        signals.append({
            'pair': item.get('pair', '—'),
            'signal': signal,
            'bias': item.get('bias', '—'),
            'confidence': item.get('confidence', '—'),
            'confidence_display': format_number(item.get('confidence'), 2),
            'recommendation': item.get('recommendation', '—'),
            'quantity': item.get('quantity', '—'),
            'quantity_display': format_number(item.get('quantity'), 4),
            'reason': item.get('reason', '—'),
        })

    if not signals:
        return None, 'Signal-Datei nicht gefunden oder ungültig', data
    return signals, None, data



def get_observation_report_via_docker():
    """Read observation_report.json from the ai-hedge-fund-crypto container."""
    container = EXTRA_CONTAINERS.get('ai-hedge-fund-crypto', 'ai-hedge-fund-crypto')
    raw = read_container_file(container, OBSERVATION_REPORT)
    mtime = get_container_mtime(container, OBSERVATION_REPORT)
    timestamp_display = format_display_timestamp(mtime) if mtime else None

    if raw is None:
        return {
            'ok': False,
            'error': 'fehlt',
            'timestamp': timestamp_display,
            'raw': None,
        }

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            'ok': False,
            'error': 'Fehler',
            'timestamp': timestamp_display,
            'raw': None,
        }
    except Exception:
        return {
            'ok': False,
            'error': 'Fehler',
            'timestamp': timestamp_display,
            'raw': None,
        }

    if isinstance(data, dict):
        ts = (
            data.get('timestamp')
            or data.get('generated_at')
            or data.get('last_report')
            or data.get('created_at')
            or timestamp_display
        )
    else:
        ts = timestamp_display

    return {
        'ok': True,
        'error': None,
        'timestamp': format_display_timestamp(ts) if ts else timestamp_display,
        'raw': data,
    }



def get_riskguard_state_via_guardian():
    """Read RiskGuard state/health from the guardian container or local repo."""
    result = {
        'exists': False,
        'error': 'fehlt',
        'status': 'unknown',
        'badge_class': status_badge_class('missing'),
        'timestamp': None,
        'health_timestamp': None,
        'signal_source': None,
        'signal_age_minutes': None,
        'signal_age_label': None,
        'summary': {},
        'pairs': {},
        'pair_rows': [],
        'health': {},
        'health_checks': {},
        'accepted_count': 0,
        'watch_only_count': 0,
        'confidence_threshold': None,
        'max_age_minutes': None,
        'concurrent_signals': None,
        'stale': None,
        'summary_line': '—',
    }

    raw_state = read_project_file_via_guardian(RISKGUARD_STATE_REL)
    raw_health = read_project_file_via_guardian(RISKGUARD_HEALTH_REL)
    if raw_state is None and raw_health is None:
        return result

    state = None
    if raw_state is not None:
        try:
            state = json.loads(raw_state)
        except Exception:
            result['error'] = 'ungültig'
            return result

    health = None
    if raw_health is not None:
        try:
            health = json.loads(raw_health)
        except Exception:
            health = None

    if not isinstance(state, dict):
        # If only health is present, expose that minimal status.
        if isinstance(health, dict):
            health_status = str(health.get('status', 'unknown'))
            result.update({
                'exists': False,
                'error': None,
                'status': health_status,
                'badge_class': status_badge_class(health_status),
                'health': health,
                'health_checks': health.get('checks', {}) if isinstance(health.get('checks'), dict) else {},
                'health_timestamp': format_display_timestamp(health.get('timestamp')),
            })
        return result

    summary = state.get('summary', {}) if isinstance(state.get('summary'), dict) else {}
    pairs = state.get('pairs', {}) if isinstance(state.get('pairs'), dict) else {}
    health_checks = health.get('checks', {}) if isinstance(health, dict) and isinstance(health.get('checks'), dict) else {}
    health_status = str(health.get('status', 'unknown')) if isinstance(health, dict) else 'unknown'
    if health_status == 'unknown':
        health_status = str(summary.get('status', state.get('status', 'unknown')))

    pair_rows = []
    for pair_name, payload in sorted(pairs.items()):
        if not isinstance(payload, dict):
            continue
        verdict = str(payload.get('verdict', 'UNKNOWN'))
        action = str(payload.get('action', 'HOLD'))
        pair_rows.append({
            'pair': pair_name,
            'verdict': verdict,
            'action': action,
            'confidence': payload.get('confidence', '—'),
            'confidence_display': format_number(payload.get('confidence'), 2),
            'quantity': payload.get('quantity', '—'),
            'quantity_display': format_number(payload.get('quantity'), 4),
            'reason': payload.get('riskguard_reason', '—'),
            'allow_long': payload.get('allow_long_bias', False),
            'allow_short': payload.get('allow_short_bias', False),
        })

    accepted_count = int(summary.get('accepted', 0) or 0)
    watch_only_count = int(summary.get('watch_only', 0) or 0)
    signal_age_minutes = state.get('signal_age_minutes')
    stale = bool(summary.get('stale', False))
    if signal_age_minutes is not None:
        try:
            stale = float(signal_age_minutes) > float(summary.get('max_age_minutes', 25.0))
        except Exception:
            pass
    status_text = 'stale' if stale else health_status

    result.update({
        'exists': True,
        'error': None,
        'status': status_text,
        'badge_class': status_badge_class(status_text if status_text != 'unknown' else health_status),
        'timestamp': format_display_timestamp(state.get('timestamp')),
        'health_timestamp': format_display_timestamp(health.get('timestamp')) if isinstance(health, dict) else None,
        'signal_source': state.get('signal_source'),
        'signal_age_minutes': signal_age_minutes,
        'signal_age_label': format_age_label(signal_age_minutes),
        'summary': summary,
        'pairs': pairs,
        'pair_rows': pair_rows,
        'health': health or {},
        'health_checks': health_checks,
        'accepted_count': accepted_count,
        'watch_only_count': watch_only_count,
        'confidence_threshold': summary.get('confidence_threshold'),
        'max_age_minutes': summary.get('max_age_minutes'),
        'concurrent_signals': summary.get('concurrent_signals'),
        'stale': stale,
        'summary_line': f'{accepted_count} ACCEPTED / {watch_only_count} WATCH_ONLY',
    })
    return result



def get_primo_state_via_docker(bot_id, container_state='not found'):
    """Read the per-bot Primo signal state file from the bot container."""
    container = BOT_CONTAINERS.get(bot_id)
    result = {
        'bot_id': bot_id,
        'name': BOT_DISPLAY.get(bot_id, bot_id),
        'container': container,
        'container_state': container_state,
        'exists': False,
        'error': 'fehlt',
        'status': 'missing',
        'badge_class': status_badge_class('missing'),
        'timestamp': None,
        'generated_at': None,
        'processed_at': None,
        'source': None,
        'schema_version': None,
        'fresh': False,
        'age_minutes': None,
        'age_label': None,
        'pair_count': 0,
        'verdict_counts': {},
        'action_counts': {},
        'pair_rows': [],
    }
    if not container:
        result['error'] = 'container_missing'
        return result

    raw = read_container_file(container, PRIMO_SIGNAL_STATE_PATH)
    if raw is None:
        return result

    try:
        data = json.loads(raw)
    except Exception:
        result['error'] = 'ungültig'
        return result

    if not isinstance(data, dict):
        result['error'] = 'ungültig'
        return result

    pairs = data.get('pairs', {}) if isinstance(data.get('pairs'), dict) else {}
    verdict_counts = Counter()
    action_counts = Counter()
    pair_rows = []
    for pair_name, payload in sorted(pairs.items()):
        if not isinstance(payload, dict):
            continue
        verdict = str(payload.get('verdict', 'UNKNOWN'))
        action = str(payload.get('action', 'UNKNOWN'))
        verdict_counts[verdict] += 1
        action_counts[action] += 1
        pair_rows.append({
            'pair': pair_name,
            'verdict': verdict,
            'action': action,
            'confidence': payload.get('confidence', '—'),
            'confidence_display': format_number(payload.get('confidence'), 2),
            'allow_long': payload.get('allow_long_bias', False),
            'allow_short': payload.get('allow_short_bias', False),
        })

    age_minutes = data.get('age_minutes')
    fresh_flag = bool(data.get('fresh', False))
    if age_minutes is not None:
        try:
            fresh_flag = fresh_flag and float(age_minutes) <= PRIMO_FRESHNESS_LIMIT_MINUTES
        except Exception:
            fresh_flag = bool(data.get('fresh', False))
    status = 'fresh' if fresh_flag else 'stale'
    generated_at = format_display_timestamp(data.get('generated_at'))
    processed_at = format_display_timestamp(data.get('processed_at'))

    result.update({
        'exists': True,
        'error': None,
        'status': status,
        'badge_class': status_badge_class(status),
        'timestamp': generated_at or processed_at,
        'generated_at': generated_at,
        'processed_at': processed_at,
        'source': data.get('source', '—'),
        'schema_version': data.get('schema_version', '—'),
        'fresh': fresh_flag,
        'age_minutes': age_minutes,
        'age_label': format_age_label(age_minutes),
        'pair_count': len(pairs),
        'verdict_counts': dict(verdict_counts),
        'action_counts': dict(action_counts),
        'pair_rows': pair_rows[:6],
    })
    return result



def get_shadow_summary_via_guardian():
    """Summarize the append-only FreqForge shadow log."""
    result = {
        'exists': False,
        'error': 'fehlt',
        'status': 'missing',
        'badge_class': status_badge_class('missing'),
        'total_events': 0,
        'decision_counts': {},
        'event_type_counts': {},
        'rule_counts': {},
        'bot_counts': {},
        'top_rule_items': [],
        'top_bot_items': [],
        'recent_events': [],
        'last_timestamp': None,
        'last_age_minutes': None,
        'last_age_label': None,
        'stale': True,
        'report_path': str(PROJECT_ROOT / 'docs/context/freqforge-shadow-evaluator-v0-1-report.md'),
    }

    raw = read_project_file_via_guardian(SHADOW_DECISIONS_REL)
    if raw is None:
        return result

    events = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if isinstance(event, dict):
            events.append(event)

    if not events:
        result['error'] = 'ungültig'
        return result

    decision_counts = Counter()
    event_type_counts = Counter()
    rule_counts = Counter()
    bot_counts = Counter()
    for event in events:
        decision_counts[str(event.get('freqforge_decision', 'unknown'))] += 1
        event_type_counts[str(event.get('event_type', 'unknown'))] += 1
        bot_counts[str(event.get('bot_name', 'unknown'))] += 1
        for code in event.get('reason_codes', []) or []:
            rule_counts[str(code)] += 1

    recent_events = []
    for event in events[-5:]:
        ts_text = event.get('timestamp_utc')
        ts_dt = parse_sqlite_timestamp(ts_text)
        age_minutes = None
        if ts_dt is not None:
            age_minutes = (datetime.now(timezone.utc) - ts_dt).total_seconds() / 60.0
        recent_events.append({
            'timestamp': format_display_timestamp(ts_text),
            'age_label': format_age_label(age_minutes),
            'bot_name': event.get('bot_name', '—'),
            'event_type': event.get('event_type', '—'),
            'decision': event.get('freqforge_decision', '—'),
            'codes': ', '.join(event.get('reason_codes', []) or []),
            'pair': event.get('pair', '—'),
        })

    last_event = events[-1]
    last_dt = parse_sqlite_timestamp(last_event.get('timestamp_utc'))
    last_age_minutes = None
    if last_dt is not None:
        last_age_minutes = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60.0
    stale = last_age_minutes is None or last_age_minutes > SHADOW_STALE_MINUTES

    result.update({
        'exists': True,
        'error': None,
        'status': 'stale' if stale else 'fresh',
        'badge_class': status_badge_class('stale' if stale else 'fresh'),
        'total_events': len(events),
        'decision_counts': dict(decision_counts),
        'event_type_counts': dict(event_type_counts),
        'rule_counts': dict(rule_counts),
        'bot_counts': dict(bot_counts),
        'top_rule_items': sorted(rule_counts.items(), key=lambda x: (-x[1], x[0]))[:8],
        'top_bot_items': sorted(bot_counts.items(), key=lambda x: (-x[1], x[0]))[:8],
        'recent_events': recent_events,
        'last_timestamp': format_display_timestamp(last_event.get('timestamp_utc')),
        'last_age_minutes': last_age_minutes,
        'last_age_label': format_age_label(last_age_minutes),
        'stale': stale,
    })
    return result



def query_bot_db(db_path):
    """
    Query a single Freqtrade SQLite database for trade stats.
    Returns a dict with keys: total_trades, wins, profit_abs, profit_pct,
    avg_duration_sec, best_trade, worst_trade, total_stake, last_activity.
    All defaults to 0 / None on failure.
    """
    result = {
        'total_trades': 0,
        'wins': 0,
        'profit_abs': 0.0,
        'profit_pct': 0.0,
        'avg_duration_sec': None,
        'best_trade': None,
        'worst_trade': None,
        'total_stake': 0.0,
        'last_activity': None,
    }
    if not os.path.isfile(db_path):
        return result

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check if trades table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        if not cur.fetchone():
            conn.close()
            return result

        # Aggregate stats for closed trades (profit only meaningful when closed)
        cur.execute("""
            SELECT
                COUNT(id)                                          AS total_trades,
                SUM(CASE WHEN profit_ratio > 0 THEN 1 ELSE 0 END)  AS wins,
                SUM(profit_abs)                                    AS profit_abs,
                AVG(CASE WHEN is_open = 0 THEN profit_ratio ELSE NULL END) * 100
                                                                   AS profit_pct,
                AVG(CASE WHEN is_open = 0 THEN trade_duration ELSE NULL END)
                                                                   AS avg_dur_sec,
                MAX(CASE WHEN is_open = 0 THEN profit_abs ELSE NULL END)
                                                                   AS best,
                MIN(CASE WHEN is_open = 0 THEN profit_abs ELSE NULL END)
                                                                   AS worst,
                SUM(CASE WHEN is_open = 0 THEN stake_amount ELSE 0 END)
                                                                   AS total_stake
            FROM trades
        """)
        row = cur.fetchone()
        if row and row['total_trades']:
            result['total_trades'] = row['total_trades']
            result['wins'] = row['wins'] or 0
            result['profit_abs'] = row['profit_abs'] or 0.0
            result['profit_pct'] = row['profit_pct'] or 0.0
            result['avg_duration_sec'] = row['avg_dur_sec']
            result['best_trade'] = row['best']
            result['worst_trade'] = row['worst']
            result['total_stake'] = abs(row['total_stake'] or 0.0)

        # Last activity (any trade open or close) — for status detection
        cur.execute("""
            SELECT MAX(MAX(open_time), MAX(close_time)) AS last_ts
            FROM trades
        """)
        last_row = cur.fetchone()
        if last_row and last_row['last_ts']:
            result['last_activity'] = last_row['last_ts']
        conn.close()
    except Exception:
        pass  # result stays defaulted

    return result


def determine_bot_status(stats, db_path):
    """
    Return one of: 'aktiv', 'problem', 'idle'
    - aktiv:  a trade was opened/closed within the last 10 min
    - idle:   DB missing or completely empty (0 trades)
    - problem: DB exists, has trades, but last activity > 10 min ago
    """
    if not os.path.isfile(db_path):
        return 'idle'
    if stats['total_trades'] == 0:
        return 'idle'
    if stats['last_activity'] is None:
        return 'problem'

    # last_activity can be a datetime object or ISO string from SQLite
    # Normalise to datetime
    ts = stats['last_activity']
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except Exception:
            ts = datetime.now(timezone.utc)
    if isinstance(ts, datetime) and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if (now - ts) < timedelta(minutes=10):
        return 'aktiv'
    else:
        return 'problem'


def get_docker_status():
    """
    Run 'docker ps' and parse container name -> status.
    Returns a dict: {container_name: 'running'|'stopped'|'not found'}.
    On Docker-unavailable returns empty dict.
    """
    statuses = {}
    try:
        out = subprocess.check_output(
            ['docker', 'ps', '-a', '--format', '{{.Names}} {{.Status}}'],
            stderr=subprocess.DEVNULL, timeout=10, text=True
        )
        lines = out.strip().splitlines()
        running = {}
        for line in lines:
            parts = line.split(None, 1)
            if len(parts) >= 1:
                running[parts[0]] = parts[1] if len(parts) > 1 else 'running'

        all_names = list(BOT_CONTAINERS.values()) + list(EXTRA_CONTAINERS.values())
        for name in all_names:
            if name in running:
                raw = running[name]
                if raw.lower().startswith('up'):
                    statuses[name] = 'running'
                elif raw.lower().startswith('exited') or raw.lower().startswith('created'):
                    statuses[name] = 'stopped'
                else:
                    statuses[name] = 'running'  # assume up
            else:
                statuses[name] = 'not found'
    except Exception:
        pass
    return statuses


def get_ai_signal():
    """
    Read the Hermes signal JSON file.
    Returns a list of signal dicts, or None on failure.
    """
    signals, _, _ = get_ai_signal_via_docker()
    return signals


def get_observation_report():
    """
    Read the observation report JSON.
    Returns a dict with status + timestamp, or None on failure.
    """
    return get_observation_report_via_docker()


def signal_css(signal_str):
    """Return a CSS-friendly class for a signal value."""
    s = (signal_str or '').lower().strip()
    if s == 'long':
        return 'signal-long'
    if s == 'short':
        return 'signal-short'
    return 'signal-hold'


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    now_utc = datetime.now(timezone.utc)
    timestamp_str = now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
    update_str = now_utc.strftime('%H:%M:%S UTC')

    # ── Collect signal metadata first so all downstream panels can reuse it ─
    signals, signal_error, signal_payload = get_ai_signal_via_docker()
    signal_meta = {
        'ok': False,
        'timestamp': None,
        'age_minutes': None,
        'age_label': None,
        'fresh': False,
        'source': '—',
        'mode': '—',
        'exchange': '—',
        'schema_version': '—',
        'llm_used': None,
        'llm_model': '—',
        'global_risk_mode': '—',
        'pair_count': 0,
        'action_counts': {},
        'bias_counts': {},
        'recommendation_counts': {},
        'signal_pairs': [],
    }
    signal_pairs_norm = set()
    if isinstance(signal_payload, dict):
        raw_ts = (
            signal_payload.get('timestamp_utc')
            or signal_payload.get('timestamp')
            or signal_payload.get('generated_at')
        )
        if raw_ts:
            dt = parse_sqlite_timestamp(raw_ts)
            if dt is not None:
                age_minutes = (now_utc - dt).total_seconds() / 60.0
                signal_meta['age_minutes'] = age_minutes
                signal_meta['age_label'] = format_age_label(age_minutes)
                signal_meta['fresh'] = age_minutes <= SIGNAL_FRESHNESS_LIMIT_MINUTES
            signal_meta['timestamp'] = format_display_timestamp(raw_ts)

        signal_meta['ok'] = True
        signal_meta['source'] = signal_payload.get('source', '—')
        signal_meta['mode'] = signal_payload.get('mode', '—')
        signal_meta['exchange'] = signal_payload.get('exchange', '—')
        signal_meta['schema_version'] = signal_payload.get('schema_version', '—')
        signal_meta['llm_used'] = signal_payload.get('llm_used')
        signal_meta['llm_model'] = signal_payload.get('llm_model', '—')
        signal_meta['global_risk_mode'] = signal_payload.get('global_risk_mode', '—')

        action_counts = Counter()
        bias_counts = Counter()
        recommendation_counts = Counter()
        if isinstance(signals, list):
            for item in signals:
                if not isinstance(item, dict):
                    continue
                pair_norm = normalize_pair_name(item.get('pair'))
                if pair_norm:
                    signal_pairs_norm.add(pair_norm)
                action_counts[str(item.get('signal', 'hold')).lower()] += 1
                bias_counts[str(item.get('bias', 'unknown')).lower()] += 1
                recommendation_counts[str(item.get('recommendation', 'unknown')).lower()] += 1
        signal_meta['pair_count'] = len(signal_payload.get('pairs', {})) if isinstance(signal_payload.get('pairs', {}), dict) else len(signals or [])
        signal_meta['action_counts'] = dict(action_counts)
        signal_meta['bias_counts'] = dict(bias_counts)
        signal_meta['recommendation_counts'] = dict(recommendation_counts)
        signal_meta['signal_pairs'] = sorted(signal_pairs_norm)

        if not signal_pairs_norm and isinstance(signal_payload.get('pairs'), dict):
            signal_pairs_norm = {normalize_pair_name(pair) for pair in signal_payload['pairs'].keys() if normalize_pair_name(pair)}
            signal_meta['signal_pairs'] = sorted(signal_pairs_norm)
            signal_meta['pair_count'] = len(signal_pairs_norm)

    # ── Collect container status first so bot status can reuse it ───────────
    docker_status = get_docker_status()

    # ── Collect per-bot stats ──────────────────────────────────────────────
    bot_rows = []
    totals = {'trades': 0, 'wins': 0, 'profit_abs': 0.0, 'stake': 0.0}
    db_raw_pairs = set()
    db_norm_pairs = set()

    for bot_id in BOT_DISPLAY:
        stats = query_bot_via_docker(bot_id)
        container_name = BOT_CONTAINERS.get(bot_id, bot_id)
        container_state = docker_status.get(container_name, 'not found')
        status = determine_bot_status_via_docker(stats, container_state)

        winrate = (stats['wins'] * 100.0 / stats['total_trades']) if stats['total_trades'] > 0 else 0.0
        profit_pct = (stats['profit_abs'] / stats['total_stake'] * 100) if stats['total_stake'] > 0 else 0.0
        distinct_pairs = stats.get('distinct_pairs', []) or []
        normalized_pairs = stats.get('normalized_pairs', []) or []
        db_raw_pairs.update(distinct_pairs)
        db_norm_pairs.update(normalized_pairs)

        bot_rows.append({
            'id': bot_id,
            'name': BOT_DISPLAY[bot_id],
            'status': status,
            'trades': stats['total_trades'],
            'winrate': winrate,
            'profit_abs': stats['profit_abs'],
            'profit_pct': profit_pct,
            'duration': format_duration_minutes(stats['avg_duration_minutes']),
            'best': stats['best_trade'],
            'worst': stats['worst_trade'],
            'db_pair_count': stats.get('distinct_pair_count', len(distinct_pairs)),
            'db_pairs': distinct_pairs,
            'normalized_pairs': normalized_pairs,
            'last_activity': format_display_timestamp(stats.get('last_activity')),
        })

        # Running totals (only closed-trade figures)
        totals['trades'] += stats['total_trades']
        totals['wins'] += stats['wins']
        totals['profit_abs'] += stats['profit_abs']
        totals['stake'] += stats['total_stake']

    bot_rows.sort(key=lambda row: row['name'])

    # ── Aggregate KPIs ─────────────────────────────────────────────────────
    total_profit_pct = (totals['profit_abs'] / totals['stake'] * 100) if totals['stake'] > 0 else 0.0
    total_winrate = (totals['wins'] * 100.0 / totals['trades']) if totals['trades'] > 0 else 0.0

    # ── Coverage / surface gap analysis ────────────────────────────────────
    coverage_signal_pairs = signal_pairs_norm or {normalize_pair_name(pair) for pair in signal_meta.get('signal_pairs', [])}
    coverage_matched_pairs = sorted(db_norm_pairs & coverage_signal_pairs)
    coverage_missing_pairs = sorted(db_norm_pairs - coverage_signal_pairs)
    coverage_pct = (len(coverage_matched_pairs) * 100.0 / len(db_norm_pairs)) if db_norm_pairs else 0.0

    # ── RiskGuard ──────────────────────────────────────────────────────────
    riskguard_state = get_riskguard_state_via_guardian()

    # ── Primo signal states (per bot) ───────────────────────────────────────
    primo_states = []
    for bot_id in BOT_DISPLAY:
        primo_states.append(get_primo_state_via_docker(bot_id, docker_status.get(BOT_CONTAINERS.get(bot_id, bot_id), 'not found')))
    primo_states.sort(key=lambda row: row['name'])
    primo_available_count = sum(1 for row in primo_states if row.get('exists'))
    primo_fresh_count = sum(1 for row in primo_states if row.get('status') == 'fresh')
    primo_missing_count = len(primo_states) - primo_available_count

    # ── FreqForge Shadow logger summary ────────────────────────────────────
    shadow_summary = get_shadow_summary_via_guardian()

    # ── Observation report ─────────────────────────────────────────────────
    obs = get_observation_report_via_docker()
    obs_ok = bool(obs and obs.get('ok'))
    obs_timestamp = obs.get('timestamp') if isinstance(obs, dict) else None
    obs_error = obs.get('error') if isinstance(obs, dict) else 'fehlt'

    # ── Render ─────────────────────────────────────────────────────────────
    return render_template_string(TEMPLATE, **{
        'timestamp': timestamp_str,
        'update_time': update_str,
        'bot_rows': bot_rows,
        'total_trades': totals['trades'],
        'total_profit_abs': totals['profit_abs'],
        'total_profit_pct': total_profit_pct,
        'total_winrate': total_winrate,
        'total_stake': totals['stake'],
        'signals': signals,
        'signal_error': signal_error,
        'signal_meta': signal_meta,
        'coverage_signal_pairs': sorted(coverage_signal_pairs),
        'coverage_db_pairs': sorted(db_norm_pairs),
        'coverage_missing_pairs': coverage_missing_pairs,
        'coverage_matched_pairs': coverage_matched_pairs,
        'coverage_pct': coverage_pct,
        'db_raw_pair_count': len(db_raw_pairs),
        'db_norm_pair_count': len(db_norm_pairs),
        'riskguard_state': riskguard_state,
        'primo_states': primo_states,
        'primo_available_count': primo_available_count,
        'primo_fresh_count': primo_fresh_count,
        'primo_missing_count': primo_missing_count,
        'shadow_summary': shadow_summary,
        'docker_status': docker_status,
        'container_list': list(BOT_CONTAINERS.values()) + list(EXTRA_CONTAINERS.values()),
        'obs_ok': obs_ok,
        'obs_timestamp': obs_timestamp,
        'obs_error': obs_error,
        'signal_css': signal_css,
        'status_badge_class': status_badge_class,
        'format_age_label': format_age_label,
        'normalize_pair_name': normalize_pair_name,
    })


# ── Template ──────────────────────────────────────────────────────────────────
TEMPLATE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trading Fleet Dashboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html { font-size: 16px; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #121212;
    color: #E0E0E0;
    min-height: 100vh;
    padding: 1.5rem;
  }
  a { color: #00BFA6; text-decoration: none; }

  /* ── Header ───────────────────────────────── */
  .header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 1rem;
    margin-bottom: 2rem;
  }
  .header h1 {
    font-size: 1.75rem;
    font-weight: 600;
    color: #FFFFFF;
    letter-spacing: 0.02em;
  }
  .header-sub {
    font-size: 0.85rem;
    color: #9E9E9E;
    margin-top: 0.25rem;
  }
  .header-actions {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  .btn-refresh {
    background: #00BFA6;
    color: #121212;
    border: none;
    border-radius: 6px;
    padding: 0.5rem 1.25rem;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn-refresh:hover { background: #00D9BD; }
  .btn-refresh:active { background: #00A891; }

  /* ── KPI cards ────────────────────────────── */
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }
  .kpi-card {
    background: #1E1E1E;
    border-radius: 10px;
    padding: 1.25rem 1rem;
    border: 1px solid #2A2A2A;
  }
  .kpi-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #9E9E9E;
    margin-bottom: 0.35rem;
  }
  .kpi-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #FFFFFF;
  }
  .kpi-value.positive { color: #00BFA6; }
  .kpi-value.negative { color: #FF5252; }

  /* ── Sections ─────────────────────────────── */
  .section-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #FFFFFF;
    margin-bottom: 0.75rem;
    padding-bottom: 0.35rem;
    border-bottom: 1px solid #2A2A2A;
  }
  .card {
    background: #1E1E1E;
    border-radius: 10px;
    border: 1px solid #2A2A2A;
    padding: 1.25rem;
  }
  .grid-2col {
    display: grid;
    grid-template-columns: 1.35fr 0.85fr;
    gap: 1.5rem;
    margin-bottom: 2rem;
    align-items: start;
  }
  .signal-overview-grid {
    display: grid;
    grid-template-columns: 1.25fr 0.95fr;
    gap: 1.5rem;
    margin-bottom: 1.5rem;
    align-items: start;
  }
  .meta-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
    gap: 0.75rem;
  }
  .meta-item,
  .summary-card,
  .mini-card {
    background: #252525;
    border: 1px solid #2A2A2A;
    border-radius: 8px;
    padding: 0.75rem;
  }
  .meta-label,
  .summary-card .label,
  .mini-card .label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #9E9E9E;
    margin-bottom: 0.25rem;
  }
  .meta-value,
  .summary-card .value,
  .mini-card .value {
    font-size: 0.92rem;
    font-weight: 600;
    color: #FFFFFF;
    word-break: break-word;
  }
  .badge-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.85rem;
  }
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.55rem;
    border-radius: 999px;
    border: 1px solid #333;
    background: #252525;
    color: #E0E0E0;
    font-size: 0.72rem;
    white-space: nowrap;
  }
  .pill-ok {
    border-color: #1B3A2D;
    background: #1B3A2D;
    color: #8FF0DD;
  }
  .pill-missing {
    border-color: #3A1B1B;
    background: #3A1B1B;
    color: #FFB3B3;
  }
  .pill-neutral {
    border-color: #333;
    background: #2A2A2A;
    color: #D0D0D0;
  }
  .mini-note,
  .detail-line {
    margin-top: 0.75rem;
    color: #9E9E9E;
    font-size: 0.82rem;
    line-height: 1.45;
  }
  .summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr));
    gap: 0.75rem;
    margin-bottom: 0.85rem;
  }
  .list-inline {
    list-style: none;
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .list-inline li {
    display: inline-flex;
    align-items: center;
    padding: 0.2rem 0.55rem;
    border-radius: 999px;
    background: #252525;
    border: 1px solid #333;
    font-size: 0.72rem;
    color: #E0E0E0;
  }
  .mini-table thead th,
  .mini-table tbody td {
    font-size: 0.78rem;
    padding: 0.45rem 0.4rem;
  }
  .wrap {
    white-space: normal !important;
    word-break: break-word;
  }
  .table-wrap {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
    table-layout: fixed;
  }
  thead th {
    text-align: left;
    padding: 0.6rem 0.5rem;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #9E9E9E;
    border-bottom: 1px solid #333;
    white-space: nowrap;
  }
  tbody td {
    padding: 0.55rem 0.5rem;
    border-bottom: 1px solid #2A2A2A;
    white-space: nowrap;
  }
  tbody tr:nth-child(even) { background: #252525; }
  tbody tr:hover { background: #2D2D2D; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }

  /* ── Status badges ────────────────────────── */
  .badge {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    text-transform: uppercase;
  }
  .badge-aktiv   { background: #1B3A2D; color: #00BFA6; }
  .badge-idle    { background: #333;     color: #BDBDBD; }
  .badge-problem { background: #3A1B1B;  color: #FF5252; }
  .badge-running { background: #1B3A2D;  color: #00BFA6; }
  .badge-stopped { background: #3A1B1B;  color: #FF5252; }
  .badge-missing { background: #333;     color: #9E9E9E; }

  /* ── Signal colours ───────────────────────── */
  .signal-long  { color: #00BFA6; font-weight: 600; }
  .signal-short { color: #FF5252; font-weight: 600; }
  .signal-hold  { color: #9E9E9E; }

  /* ── System status list ───────────────────── */
  .sys-list { list-style: none; }
  .sys-list li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.4rem 0;
    border-bottom: 1px solid #2A2A2A;
    font-size: 0.85rem;
  }
  .sys-list li:last-child { border-bottom: none; }
  .sys-list .name { color: #E0E0E0; }
  .obs-line {
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid #2A2A2A;
    font-size: 0.85rem;
  }
  .obs-line .label { color: #9E9E9E; }
  .obs-line .value { color: #00BFA6; }
  .obs-line .error { color: #FF5252; }

  /* ── Signal empty state ───────────────────── */
  .empty-msg {
    color: #9E9E9E;
    font-size: 0.85rem;
    padding: 0.75rem 0;
    text-align: center;
  }

  /* ── Responsive ───────────────────────────── */
  @media (max-width: 768px) {
    body { padding: 1rem; }
    .header h1 { font-size: 1.35rem; }
    .kpi-row { grid-template-columns: repeat(2, 1fr); }
    .grid-2col { grid-template-columns: 1fr; }
    .signal-overview-grid { grid-template-columns: 1fr; }
    table { font-size: 0.75rem; }
  }
  @media (max-width: 480px) {
    .kpi-row { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>

<!-- ═══ Header ═════════════════════════════════ -->
<div class="header">
  <div>
    <h1>Trading Fleet Dashboard</h1>
    <div class="header-sub">{{ timestamp }} &middot; Letztes Update: {{ update_time }}</div>
  </div>
  <div class="header-actions">
    <button class="btn-refresh" onclick="location.reload()">Jetzt aktualisieren</button>
  </div>
</div>

<!-- ═══ KPI row ════════════════════════════════ -->
<div class="kpi-row">
  <div class="kpi-card">
    <div class="kpi-label">Gesamt Profit</div>
    <div class="kpi-value {{ 'positive' if total_profit_abs >= 0 else 'negative' }}">
      {{ "%.2f"|format(total_profit_abs) }} USDT
    </div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Gesamt Profit %</div>
    <div class="kpi-value {{ 'positive' if total_profit_pct >= 0 else 'negative' }}">
      {{ "%.2f"|format(total_profit_pct) }}%
    </div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Gesamte Trades</div>
    <div class="kpi-value">{{ total_trades }}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Gesamt Winrate</div>
    <div class="kpi-value">{{ "%.1f"|format(total_winrate) }}%</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Gesamter Stake</div>
    <div class="kpi-value">{{ "%.2f"|format(total_stake) }} USDT</div>
  </div>
</div>

<!-- ═══ Kernansicht ═══════════════════════════════ -->
<div class="card" style="margin-bottom:1.5rem;">
  <div class="section-title">Aktuelle AI-Signale (Hermes)</div>
  {% if signal_error %}
    <div class="empty-msg">{{ signal_error }}</div>
  {% elif signals and signals|length > 0 %}
    <div class="meta-grid" style="margin-bottom:0.85rem;">
      <div class="meta-item">
        <div class="meta-label">Zeitpunkt</div>
        <div class="meta-value">{{ signal_meta.timestamp or 'N/A' }}</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Alter</div>
        <div class="meta-value">
          {% if signal_meta.age_label %}
            <span class="badge {{ status_badge_class('fresh' if signal_meta.fresh else 'problem') }}">{{ signal_meta.age_label }}</span>
          {% else %}
            N/A
          {% endif %}
        </div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Quelle</div>
        <div class="meta-value">{{ signal_meta.source }}</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Global Risk</div>
        <div class="meta-value"><span class="badge {{ status_badge_class(signal_meta.global_risk_mode) }}">{{ signal_meta.global_risk_mode }}</span></div>
      </div>
    </div>
    <div class="detail-line">Paare: {{ signal_meta.pair_count }}{% if signal_meta.llm_used is not none %} · LLM: {{ 'an' if signal_meta.llm_used else 'aus' }}{% endif %}</div>
    <div class="table-wrap">
      <table class="mini-table">
        <thead>
          <tr>
            <th>Pair</th>
            <th>Signal</th>
            <th>Bias</th>
            <th class="num">Confidence</th>
            <th>Recommendation</th>
            <th class="num">Qty</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {% for s in signals %}
          <tr>
            <td>{{ s.get('pair', '—') }}</td>
            <td class="{{ signal_css(s.get('signal', '')) }}">{{ s.get('signal', '—')|upper }}</td>
            <td>{{ s.get('bias', '—') }}</td>
            <td class="num">{{ s.get('confidence_display', s.get('confidence', '—')) }}</td>
            <td>{{ s.get('recommendation', '—') }}</td>
            <td class="num">{{ s.get('quantity_display', s.get('quantity', '—')) }}</td>
            <td class="wrap">{{ s.get('reason', '—') }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    <div class="mini-note">Rohsignal wird bei jedem Refresh neu gelesen.</div>
  {% else %}
    <div class="empty-msg">Keine Signale vorhanden</div>
  {% endif %}
</div>

<!-- ═══ Bot table + System status (2‑col) ════ -->
<div class="grid-2col">

  <!-- Bot-Übersicht -->
  <div class="card">
    <div class="section-title">Bot-Übersicht</div>
    <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Bot</th>
          <th>Status</th>
          <th class="num">Trades</th>
          <th class="num">Winrate</th>
          <th class="num">Profit USDT</th>
          <th class="num">Profit %</th>
          <th class="num">Ø Haltedauer</th>
          <th class="num">Best</th>
          <th class="num">Worst</th>
        </tr>
      </thead>
      <tbody>
        {% for b in bot_rows %}
        <tr>
          <td>{{ b.name }}</td>
          <td><span class="badge badge-{{ b.status }}">{{ b.status }}</span></td>
          <td class="num">{{ b.trades }}</td>
          <td class="num">{{ "%.1f"|format(b.winrate) }}%</td>
          <td class="num {{ 'positive' if b.profit_abs >= 0 else 'negative' }}">
            {{ "%+.2f"|format(b.profit_abs) }}
          </td>
          <td class="num {{ 'positive' if b.profit_pct >= 0 else 'negative' }}">
            {{ "%+.2f"|format(b.profit_pct) }}
          </td>
          <td class="num">{{ b.duration }}</td>
          <td class="num {{ 'positive' if b.best and b.best >= 0 else '' }}">
            {{ "%+.2f"|format(b.best) if b.best is not none else '-' }}
          </td>
          <td class="num {{ 'negative' if b.worst and b.worst < 0 else '' }}">
            {{ "%+.2f"|format(b.worst) if b.worst is not none else '-' }}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    </div>
  </div>

  <!-- System-Status -->
  <div>
    <div class="card" style="margin-bottom:1.5rem;">
      <div class="section-title">System-Status</div>
      <ul class="sys-list">
        {% for cname in container_list %}
        {% set st = docker_status.get(cname, 'not found') %}
        <li>
          <span class="name">{{ cname }}</span>
          <span class="badge badge-{{ 'running' if st == 'running' else 'stopped' if st == 'stopped' else 'missing' }}">
            {{ st }}
          </span>
        </li>
        {% endfor %}
      </ul>
      <div class="obs-line">
        <span class="label">Observation-Report: </span>
        {% if obs_ok %}
          <span class="value">OK</span>
        {% else %}
          <span class="error">{{ obs_error or 'fehlt' }}</span>
        {% endif %}
        {% if obs_timestamp %}
          <br><span class="label">Letzter: </span><span class="value">{{ obs_timestamp }}</span>
        {% endif %}
      </div>
    </div>

    {% if riskguard_state.exists or riskguard_state.health %}
      <div class="detail-line">RiskGuard: <span class="badge {{ riskguard_state.badge_class }}">{{ riskguard_state.status }}</span>{% if riskguard_state.signal_age_label %} · Alter: {{ riskguard_state.signal_age_label }}{% endif %}{% if riskguard_state.summary_line %} · {{ riskguard_state.summary_line }}{% endif %}</div>
    {% else %}
      <div class="detail-line">RiskGuard: keine Daten verfügbar</div>
    {% endif %}
  </div>
</div>

</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print(f'[dashboard] Starting on http://0.0.0.0:{PORT}')
    print(f'[dashboard] Press Ctrl+C to stop.')
    app.run(host='0.0.0.0', port=PORT, debug=False)