#!/usr/bin/env python3
"""
Fleet Dashboard — Unified Polymarket Trading Bot Dashboard
===========================================================
Aggregates data from:
  🌦️  WeatherHermes  (172.18.0.2:9090)
  ⚡  BTC 5-Min Bot   (172.18.0.4:9090)
  🤖  Polymarket-Fadi (172.18.0.?:9090)  — TBD after deploy

Usage:
  WEATHERHERMES_URL=http://172.18.0.2:9090 \
  BTC5M_URL=http://172.18.0.4:9090 \
  POLYFADI_URL=... \
  python3 dashboard.py
"""

import os
import json
import time
import threading
import requests
from datetime import datetime, timezone
from flask import Flask, render_template_string, jsonify, request

# Self-improvement companions
from self_improve_fadi import FadiSelfImprover
_fadi_si = FadiSelfImprover()
from self_improve_btc5m import BTC5mSelfImprover
_btc5m_si = BTC5mSelfImprover()

app = Flask(__name__)

# Config from env
WEATHERHERMES_URL = os.environ.get("WEATHERHERMES_URL", "http://172.18.0.2:9090")
BTC5M_URL = os.environ.get("BTC5M_URL", "http://172.18.0.4:9090")
POLYFADI_URL = os.environ.get("POLYFADI_URL", "http://172.18.0.6:3001")

REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "15"))

# ---------------------------------------------------------------------------
# Data Fetchers
# ---------------------------------------------------------------------------

def fetch_json(url, timeout=5):
    """Fetch JSON from a URL, return None on failure."""
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return None


def get_weatherhermes():
    """Fetch WeatherHermes status + all profiles."""
    data = fetch_json(f"{WEATHERHERMES_URL}/api/status")
    if not data:
        return {"status": "offline", "profiles": []}

    profiles = data.get("profiles", [])
    total_balance = sum(p.get("balance", 0) for p in profiles)
    total_pnl = sum(p.get("pnl", 0) for p in profiles)
    total_pnl_pct = sum(p.get("pnl_pct", 0) for p in profiles) / max(len(profiles), 1)
    total_open = sum(len(p.get("open_positions", [])) for p in profiles)
    total_wins = sum(p.get("wins", 0) for p in profiles)
    total_losses = sum(p.get("losses", 0) for p in profiles)

    # Collect all recent trades
    all_trades = []
    for p in profiles:
        for t in p.get("recent_trades", []):
            t["_bot"] = "🌦️ WH"
            t["_profile"] = p["name"]
            t["timestamp"] = t.get("closed_at", t.get("timestamp", ""))
            all_trades.append(t)

    all_trades.sort(key=lambda x: x.get("closed_at", ""), reverse=True)

    return {
        "status": "online",
        "total_balance": round(total_balance, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "total_open": total_open,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "total_trades": total_wins + total_losses,
        "win_rate": round(total_wins / max(total_wins + total_losses, 1) * 100, 1),
        "profiles": profiles,
        "recent_trades": all_trades[:20],
        "url": WEATHERHERMES_URL,
    }


def get_btc5m():
    """Fetch BTC 5-Min Bot status."""
    data = fetch_json(f"{BTC5M_URL}/api/status")
    if not data:
        return {"status": "offline"}

    trades = data.get("recent_trades", [])
    wins = data.get("wins", 0)
    losses = data.get("losses", 0)
    total = wins + losses

    # Tag trades
    tagged_trades = []
    for t in trades:
        t["_bot"] = "⚡ BTC5M"
        t["closed_at"] = t.get("timestamp", t.get("closed_at", ""))
        tagged_trades.append(t)

    return {
        "status": "online",
        "bankroll": data.get("bankroll", 0),
        "wins": wins,
        "losses": losses,
        "total_trades": total,
        "win_rate": round(wins / max(total, 1) * 100, 1),
        "mode": data.get("mode", "PAPER"),
        "open_position": data.get("open_position"),
        "current_window": data.get("current_window"),
        "recent_trades": tagged_trades[:20],
        "avg_pnl": round((data.get("bankroll", 100) - 100) / max(total, 1), 2),
        "url": BTC5M_URL,
    }


def get_wh_self_improve():
    """Read WeatherHermes self-improvement data from shared volume."""
    import os
    result = {"profiles": {}, "status": "no_data"}
    si_dir = "/weatherhermes-data/profiles"
    if not os.path.exists(si_dir):
        result["status"] = "no_volume"
        return result
    for profile in ["conservative", "balanced", "aggressive"]:
        si_path = os.path.join(si_dir, profile, "self_improve.json")
        if os.path.exists(si_path):
            try:
                with open(si_path) as f:
                    result["profiles"][profile] = json.load(f)
                    result["profiles"][profile]["_has_data"] = True
                result["status"] = "data"
            except Exception:
                pass
        else:
            py_path = os.path.join(si_dir, profile, "self_improve.py")
            result["profiles"][profile] = {
                "_has_data": False,
                "_module_exists": os.path.exists(py_path),
                "status": "awaiting_resolved_markets"
            }
    return result


def get_polyfadi():
    """Fetch Polymarket-Fadi status."""
    if not POLYFADI_URL:
        return {"status": "not_deployed"}

    data = fetch_json(f"{POLYFADI_URL}/api/state")
    if not data:
        return {"status": "offline"}

    return {
        "status": "online",
        "data": data,
        "url": POLYFADI_URL,
    }


def get_all_bots():
    """Fetch all bots simultaneously."""
    import threading

    results = {}

    def fetch_wh():
        results["weatherhermes"] = get_weatherhermes()

    def fetch_btc():
        results["btc5m"] = get_btc5m()

    def fetch_pf():
        results["polyfadi"] = get_polyfadi()

    threads = [
        threading.Thread(target=fetch_wh),
        threading.Thread(target=fetch_btc),
        threading.Thread(target=fetch_pf),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    return results


# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fleet Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: {
    extend: {
      colors: {
        bg: '#0f0f1a',
        card: '#1a1a2e',
        card2: '#252542',
        accent: '#00d4aa',
        warn: '#f59e0b',
        danger: '#ef4444',
        cyan: '#06b6d4',
      }
    }
  }
}
</script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
* { font-family: 'Inter', system-ui, sans-serif; }
body { background: #0f0f1a; color: #e2e8f0; }
.glow { box-shadow: 0 0 20px rgba(0,212,170,0.1); }
.glow-red { box-shadow: 0 0 20px rgba(239,68,68,0.1); }
.glow-cyan { box-shadow: 0 0 20px rgba(6,182,212,0.1); }
.stat-value { font-size: 1.5rem; font-weight: 700; }
.stat-label { font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
.card-fade { transition: opacity 0.3s; }
.offline { opacity: 0.6; }
.pulse { animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
</style>
</head>
<body>
<div class="max-w-7xl mx-auto px-4 py-6">
  <!-- Header -->
  <div class="flex items-center justify-between mb-6">
    <div>
      <h1 class="text-2xl font-bold">🏠 Fleet Dashboard</h1>
      <p class="text-sm text-slate-400">Polymarket Trading Fleet · <span id="ts" class="text-slate-500"></span></p>
    </div>
    <div class="flex items-center gap-3">
      <span class="text-xs text-slate-500">Auto-refresh {{ refresh }}s</span>
      <button onclick="location.reload()" class="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-xs font-medium transition">⟳ Refresh</button>
    </div>
  </div>

  <!-- Bot Cards Row -->
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6" id="bot-cards">
    <!-- WeatherHermes -->
    <div class="rounded-xl p-5 glow card-fade {{ 'offline' if wh.status != 'online' }}" style="background:#1a1a2e" id="card-wh">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <span class="text-2xl">🌦️</span>
          <span class="font-semibold">WeatherHermes</span>
        </div>
        <span class="text-xs px-2 py-0.5 rounded {{ 'bg-emerald-500/20 text-emerald-400' if wh.status=='online' else 'bg-red-500/20 text-red-400' }}">
          {{ '● Online' if wh.status=='online' else '● Offline' if wh.status=='offline' else '○ Pending' }}
        </span>
      </div>
      {% if wh.status == 'online' %}
      <div class="grid grid-cols-3 gap-2 mb-3">
        <div><div class="stat-value text-emerald-400">${{ wh.total_balance }}</div><div class="stat-label">Balance</div></div>
        <div><div class="stat-value {{ 'text-emerald-400' if wh.total_pnl_pct>=0 else 'text-red-400' }}">{{ '%+d'|format(wh.total_pnl_pct) }}%</div><div class="stat-label">PnL</div></div>
        <div><div class="stat-value text-cyan-400">{{ wh.total_open }}</div><div class="stat-label">Open</div></div>
      </div>
      <div class="flex flex-wrap gap-1.5 mt-2">
        {% for p in wh.profiles %}
        <span class="text-xs px-2 py-1 rounded-full {{ 'bg-blue-500/20 text-blue-300' if p.name=='conservative' else 'bg-amber-500/20 text-amber-300' if p.name=='balanced' else 'bg-rose-500/20 text-rose-300' }}">
          {{ p.name[:3] }} ${{ p.balance }}
        </span>
        {% endfor %}
      </div>
      <div class="mt-2 text-xs text-slate-500">Trades: {{ wh.total_trades }} · WR: {{ wh.win_rate }}%</div>
      {% else %}
      <div class="text-sm text-slate-500">Waiting for data...</div>
      {% endif %}
      <a href="/fleet/weatherhermes" class="block mt-3 text-xs text-cyan-400 hover:text-cyan-300">→ Details</a>
    </div>

    <!-- BTC 5-Min -->
    <div class="rounded-xl p-5 glow-cyan card-fade {{ 'offline' if btc.status != 'online' }}" style="background:#1a1a2e" id="card-btc">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <span class="text-2xl">⚡</span>
          <span class="font-semibold">BTC 5-Min Bot</span>
        </div>
        <span class="text-xs px-2 py-0.5 rounded {{ 'bg-emerald-500/20 text-emerald-400' if btc.status=='online' else 'bg-red-500/20 text-red-400' if btc.status=='offline' else 'bg-slate-500/20 text-slate-400' }}">
          {{ '● Online' if btc.status=='online' else '● Offline' if btc.status=='offline' else '○ N/A' }}
        </span>
      </div>
      {% if btc.status == 'online' %}
      <div class="grid grid-cols-3 gap-2 mb-3">
        <div><div class="stat-value text-emerald-400">${{ '%.0f'|format(btc.bankroll) }}</div><div class="stat-label">Bankroll</div></div>
        <div><div class="stat-value text-cyan-400">{{ btc.win_rate }}%</div><div class="stat-label">Win Rate</div></div>
        <div><div class="stat-value">{{ btc.total_trades }}</div><div class="stat-label">Trades</div></div>
      </div>
      {% if btc.open_position %}
      <div class="text-xs bg-cyan-500/10 rounded p-2 mt-2">
        <span class="text-cyan-300 font-medium">{{ btc.open_position.direction }}</span>
        @ ${{ btc.open_position.entry_price }} · ${{ btc.open_position.cost }}
      </div>
      {% endif %}
      <div class="text-xs text-slate-500 mt-2">Mode: {{ btc.mode }} · W:{{ btc.wins }} L:{{ btc.losses }}</div>
      {% else %}
      <div class="text-sm text-slate-500">Waiting for data...</div>
      {% endif %}
      <a href="/fleet/btc5m" class="block mt-3 text-xs text-cyan-400 hover:text-cyan-300">→ Details</a>
    </div>

    <!-- Polymarket-Fadi -->
    <div class="rounded-xl p-5 glow-red card-fade {{ 'offline' if fadi.status != 'online' }}" style="background:#1a1a2e" id="card-fadi">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <span class="text-2xl">🤖</span>
          <span class="font-semibold">Polymarket-Fadi</span>
        </div>
        <span class="text-xs px-2 py-0.5 rounded {{ 'bg-emerald-500/20 text-emerald-400' if fadi.status=='online' else 'bg-amber-500/20 text-amber-400' if fadi.status=='not_deployed' else 'bg-red-500/20 text-red-400' }}">
          {{ '● Online' if fadi.status=='online' else '⊙ Not Deployed' if fadi.status=='not_deployed' else '● Offline' }}
        </span>
      </div>
      {% if fadi.status == 'online' %}
      <div class="grid grid-cols-3 gap-2 mb-3">
        <div><div class="stat-value text-emerald-400">${{ fadi.data.currentCapital if fadi.data else '?' }}</div><div class="stat-label">Capital</div></div>
        <div><div class="stat-value text-cyan-400">{{ '📄 Paper' if fadi.data and fadi.data.paper else '🔴 Live' }}</div><div class="stat-label">Mode</div></div>
        <div><div class="stat-value">{{ fadi.data.tradesExecuted if fadi.data else 0 }}</div><div class="stat-label">Trades</div></div>
      </div>
      {% elif fadi.status == 'not_deployed' %}
      <div class="text-sm text-slate-500 mt-4 mb-4">Not deployed yet — will appear here after setup.</div>
      {% else %}
      <div class="text-sm text-slate-500">Waiting for data...</div>
      {% endif %}
      <a href="/fleet/polyfadi" class="block mt-3 text-xs text-cyan-400 hover:text-cyan-300">→ Details</a>
    </div>
  </div>

  <!-- Combined Trades Table -->
  <div class="rounded-xl p-5" style="background:#1a1a2e">
    <h2 class="text-lg font-semibold mb-3">📋 Recent Trades</h2>
    {% set all_trades = (wh.recent_trades or [])[:5] + (btc.recent_trades or [])[:10] %}
    {% set all_trades = all_trades | sort(attribute='timestamp', reverse=True) if all_trades else [] %}
    {% if all_trades %}
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr class="text-slate-500 text-xs uppercase">
          <th class="text-left py-2 pr-3">Bot</th>
          <th class="text-left py-2 pr-3">City / Pair</th>
          <th class="text-right py-2 pr-3">Result</th>
          <th class="text-right py-2 pr-3">PnL</th>
          <th class="text-right py-2 pr-3">Time</th>
        </tr></thead>
        <tbody>
        {% for t in all_trades[:15] %}
        <tr class="border-t border-white/5">
          <td class="py-2 pr-3">{{ t._bot if t._bot else '—' }}</td>
          <td class="py-2 pr-3">{{ t.city if t.city else t.direction if t.direction else '—' }}</td>
          <td class="py-2 pr-3 text-right">
            <span class="px-2 py-0.5 rounded text-xs {{ 'bg-emerald-500/20 text-emerald-400' if t.won or (t.pnl and t.pnl > 0) else 'bg-red-500/20 text-red-400' }}">
              {{ 'WIN' if t.won else ('LOSS' if t.won==False else (t.close_reason or '—')) }}
            </span>
          </td>
          <td class="py-2 pr-3 text-right {{ 'text-emerald-400' if t.pnl and t.pnl > 0 else 'text-red-400' }}">
            {{ ('+' if t.pnl and t.pnl > 0 else '') + '%.2f'|format(t.pnl) if t.pnl else '—' }}
          </td>
          <td class="py-2 pr-3 text-right text-slate-500 text-xs">
            {{ (t.closed_at or t.timestamp or '')[:16] }}
          </td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="text-sm text-slate-500 py-4">No trade data yet — bots are warming up...</div>
    {% endif %}
  </div>

  <!-- Footer -->
  <div class="text-center text-xs text-slate-600 mt-6">
    Fleet Dashboard · Hermes Orchestrator · {{ now }}
  </div>
</div>

<script>
// Auto-refresh
setTimeout(function() { location.reload(); }, {{ refresh * 1000 }});

// Update timestamp
document.getElementById('ts').textContent = new Date().toLocaleTimeString();
</script>
</body>
</html>"""

DETAIL_WH_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WeatherHermes Details — Fleet Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: {
    extend: { colors: { bg: '#0f0f1a', card: '#1a1a2e', card2: '#252542', accent: '#00d4aa', warn: '#f59e0b', danger: '#ef4444', cyan: '#06b6d4' } }
  }
}
</script>
<style>
* { font-family: 'Inter', system-ui, sans-serif; }
body { background: #0f0f1a; color: #e2e8f0; }
</style>
</head>
<body>
<div class="max-w-7xl mx-auto px-4 py-6">
  <a href="/fleet" class="text-cyan-400 hover:text-cyan-300 text-sm mb-4 inline-block">← Back to Fleet</a>
  <h1 class="text-2xl font-bold mb-6">🌦️ WeatherHermes — Detail</h1>

  <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
    {% for p in wh.profiles %}
    <div class="rounded-xl p-5" style="background:#1a1a2e">
      <div class="flex items-center justify-between mb-3">
        <span class="font-semibold text-lg">{{ p.meta.icon }} {{ p.name|capitalize }}</span>
        <span class="text-xs text-slate-500">{{ p.meta.tagline }}</span>
      </div>
      <div class="grid grid-cols-2 gap-2 mb-3">
        <div><div class="stat-value text-emerald-400">${{ p.balance }}</div><div class="stat-label">Balance</div></div>
        <div><div class="stat-value {{ 'text-emerald-400' if p.pnl_pct>=0 else 'text-red-400' }}">{{ '%+.1f'|format(p.pnl_pct) }}%</div><div class="stat-label">PnL</div></div>
        <div><div class="stat-value text-cyan-400">{{ p.wins }}</div><div class="stat-label">Wins</div></div>
        <div><div class="stat-value">{{ p.losses }}</div><div class="stat-label">Losses</div></div>
      </div>
      {% if p.open_positions %}
      <div class="text-xs font-medium text-cyan-300 mb-2">📌 Open Positions</div>
      {% for pos in p.open_positions %}
      <div class="text-xs bg-cyan-500/10 rounded p-2 mb-1">
        {{ pos._pos.bucket_low }}-{{ pos._pos.bucket_high }}°{{ 'F' if p.name=='conservative' else 'C' }}
        @ ${{ pos._pos.entry_price }} · ${{ pos._pos.cost }}
      </div>
      {% endfor %}
      {% endif %}
      <div class="text-xs">
        <span class="text-slate-400">Kelly:</span> {{ p.config.kelly_fraction }}
        <span class="text-slate-400 ml-2">Max Bet:</span> ${{ '%.1f'|format(p.config.max_bet) }}
        <span class="text-slate-400 ml-2">Min EV:</span> {{ p.config.min_ev }}
      </div>
    </div>
    {% endfor %}
  </div>

  <!-- Self-Improvement Section -->
  <div class="rounded-xl p-5 mb-6" style="background:#1a1a2e">
    <h2 class="text-lg font-semibold mb-3">🧠 Self-Improvement</h2>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      {% for p in wh.profiles %}
      {% set si = wh_si.profiles.get(p.name, {}) if wh_si else {} %}
      <div class="rounded-lg p-4" style="background:#252542">
        <h3 class="text-sm font-semibold mb-2 {{ "text-blue-300" if p.name=="conservative" else "text-amber-300" if p.name=="balanced" else "text-rose-300" }}">
          {{ p.meta.icon }} {{ p.name|capitalize }}
        </h3>
        {% if si.get("_has_data") %}
          <div class="text-xs space-y-1">
            <div class="flex justify-between">
              <span class="text-slate-500">Source Accuracy:</span>
              <span>ECMWF {{ "%.0f"|format(si.source_accuracy.ecmwf*100) }}% HRRR {{ "%.0f"|format(si.source_accuracy.hrrr*100) }}%</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-500">Dynamic Weights:</span>
              <span>ECMWF {{ "%.0f"|format(si.dynamic_weights.ecmwf*100) }}% HRRR {{ "%.0f"|format(si.dynamic_weights.hrrr*100) }}%</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-500">Brier Score:</span>
              <span>{{ si.source_brier.ecmwf if si.source_brier else "—" }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-500">Dynamic Kelly:</span>
              <span class="text-cyan-300">{{ "%.1f"|format(si.dynamic_kelly * 100) if si.dynamic_kelly else "—" }}%</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-500">Win Rate:</span>
              <span>{{ "%.0f"|format(si.rolling_win_rate * 100) if si.rolling_win_rate else "—" }}%</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-500">Resolved:</span>
              <span>{{ si.total_resolved }} trades</span>
            </div>
          </div>
        {% elif si.get("_module_exists") %}
          <div class="text-xs text-slate-500">
            <p>✅ Module loaded & running</p>
            <p>⏳ Awaiting resolved markets... (warmup: 1)</p>
            <p class="mt-2 text-slate-600">EWMA weights · Brier calibration · Dynamic Kelly</p>
          </div>
        {% else %}
          <div class="text-xs text-slate-500">No self-improvement module</div>
        {% endif %}
      </div>
      {% endfor %}
    </div>
  </div>

  <!-- All Recent Trades -->
  <div class="rounded-xl p-5" style="background:#1a1a2e">
    <h2 class="text-lg font-semibold mb-3">📋 All WeatherHermes Trades</h2>
    {% set all_trades = [] %}
    {% for p in wh.profiles %}
      {% for t in p.recent_trades %}
        {% set _ = all_trades.append(dict(t, _profile=p.name)) %}
      {% endfor %}
    {% endfor %}
    {% set all_trades = all_trades | sort(attribute='closed_at', reverse=True) %}
    {% if all_trades %}
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr class="text-slate-500 text-xs uppercase">
          <th class="text-left py-2 pr-3">Profile</th>
          <th class="text-left py-2 pr-3">City</th>
          <th class="text-left py-2 pr-3">Bucket</th>
          <th class="text-right py-2 pr-3">Entry</th>
          <th class="text-right py-2 pr-3">Exit</th>
          <th class="text-right py-2 pr-3">EV</th>
          <th class="text-right py-2 pr-3">Forecast</th>
          <th class="text-right py-2 pr-3">PnL</th>
          <th class="text-right py-2 pr-3">Reason</th>
        </tr></thead>
        <tbody>
        {% for t in all_trades[:30] %}
        <tr class="border-t border-white/5">
          <td class="py-2 pr-3">{{ t._profile[:3] }}</td>
          <td class="py-2 pr-3">{{ t.city }}</td>
          <td class="py-2 pr-3">{{ t.bucket }}</td>
          <td class="py-2 pr-3 text-right">{{ t.entry }}</td>
          <td class="py-2 pr-3 text-right">{{ t.exit if t.exit else '—' }}</td>
          <td class="py-2 pr-3 text-right">{{ t.ev }}</td>
          <td class="py-2 pr-3 text-right">{{ t.forecast }}</td>
          <td class="py-2 pr-3 text-right {{ 'text-emerald-400' if t.pnl and t.pnl > 0 else 'text-red-400' }}">{{ ('+' if t.pnl and t.pnl > 0 else '') + '%.2f'|format(t.pnl) if t.pnl else '—' }}</td>
          <td class="py-2 pr-3 text-right text-xs text-slate-500">{{ t.close_reason or '—' }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="text-sm text-slate-500 py-4">No trades yet.</div>
    {% endif %}
  </div>

</div>
</body>
</html>"""

DETAIL_BTC_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BTC 5-Min Bot Details — Fleet Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: {
    extend: { colors: { bg: '#0f0f1a', card: '#1a1a2e', card2: '#252542', accent: '#00d4aa', warn: '#f59e0b', danger: '#ef4444', cyan: '#06b6d4' } }
  }
}
</script>
<style>
* { font-family: 'Inter', system-ui, sans-serif; }
body { background: #0f0f1a; color: #e2e8f0; }
</style>
</head>
<body>
<div class="max-w-7xl mx-auto px-4 py-6">
  <a href="/fleet" class="text-cyan-400 hover:text-cyan-300 text-sm mb-4 inline-block">← Back to Fleet</a>
  <h1 class="text-2xl font-bold mb-2">⚡ BTC 5-Min Bot — Detail</h1>
  <p class="text-sm text-slate-400 mb-6">Mode: {{ btc.mode }} · Last update: {{ now }}</p>

  <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
    <div class="rounded-xl p-5" style="background:#1a1a2e">
      <div class="stat-label">Bankroll</div>
      <div class="stat-value text-emerald-400">${{ '%.2f'|format(btc.bankroll) }}</div>
    </div>
    <div class="rounded-xl p-5" style="background:#1a1a2e">
      <div class="stat-label">Win Rate</div>
      <div class="stat-value text-cyan-400">{{ btc.win_rate }}%</div>
      <div class="text-xs text-slate-500">W:{{ btc.wins }} · L:{{ btc.losses }}</div>
    </div>
    <div class="rounded-xl p-5" style="background:#1a1a2e">
      <div class="stat-label">Total Trades</div>
      <div class="stat-value">{{ btc.total_trades }}</div>
    </div>
    <div class="rounded-xl p-5" style="background:#1a1a2e">
      <div class="stat-label">Avg PnL / Trade</div>
      <div class="stat-value text-slate-300">
              ${{ btc.avg_pnl }}
      </div>
    </div>
  </div>

  {% if btc.open_position %}
  <div class="rounded-xl p-5 mb-6 border border-cyan-500/30" style="background:#1a1a2e">
    <h2 class="text-sm font-semibold text-cyan-300 mb-2">📌 Open Position</h2>
    <div class="grid grid-cols-3 gap-4 text-sm">
      <div><span class="text-slate-500">Direction:</span> <span class="font-medium">{{ btc.open_position.direction }}</span></div>
      <div><span class="text-slate-500">Entry:</span> ${{ btc.open_position.entry_price }}</div>
      <div><span class="text-slate-500">Cost:</span> ${{ btc.open_position.cost }}</div>
      <div><span class="text-slate-500">Shares:</span> {{ btc.open_position.shares }}</div>
      <div><span class="text-slate-500">Confidence:</span> {{ '%.0f'|format(btc.open_position.confidence * 100) }}%</div>
      <div><span class="text-slate-500">Window:</span> {{ btc.current_window }}</div>
    </div>
  </div>
  {% endif %}

  <!-- Self-Improvement Section -->
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
    <div class="rounded-xl p-5" style="background:#1a1a2e">
      <h2 class="text-sm font-semibold text-emerald-300 mb-3">🧠 Self-Improvement Insights</h2>
      {% if btc_si and btc_si.learnings %}
      <ul class="space-y-1 text-sm">
        {% for l in btc_si.learnings %}
        <li class="flex items-start gap-2">
          <span class="text-slate-500 mt-0.5">•</span>
          <span>{{ l }}</span>
        </li>
        {% endfor %}
      </ul>
      {% else %}
      <div class="text-sm text-slate-500">Collecting data (needs {{ 10 - (btc_si.trades_analyzed if btc_si else 0) }} more trades)...</div>
      {% endif %}
    </div>
    <div class="rounded-xl p-5" style="background:#1a1a2e">
      <h2 class="text-sm font-semibold text-cyan-300 mb-3">📊 Delta Performance</h2>
      {% if btc_si and btc_si.delta_performance %}
      <div class="text-xs space-y-2">
        {% for range_key, perf in btc_si.delta_performance.items() %}
        <div>
          <div class="flex items-center justify-between mb-0.5">
            <span>Δ {{ range_key }}%</span>
            <span class="{{ 'text-emerald-400' if perf.win_rate >= 0.5 else 'text-red-400' }}">
              {{ '%.0f'|format(perf.win_rate * 100) }}% ({{ perf.trades }})
            </span>
          </div>
          <div class="w-full h-1.5 rounded-full bg-slate-700">
            <div class="h-full rounded-full {{ 'bg-emerald-500' if perf.win_rate >= 0.5 else 'bg-red-500' }}" 
                 style="width:{{ '%.0f'|format(perf.win_rate * 100) }}%"></div>
          </div>
        </div>
        {% endfor %}
      </div>
      {% else %}
      <div class="text-sm text-slate-500">Waiting for data...</div>
      {% endif %}
      {% if btc_si and btc_si.recommendations %}
      <div class="mt-3 text-xs space-y-1">
        <div class="flex justify-between">
          <span class="text-slate-500">Optimal Threshold:</span>
          <span class="font-medium text-cyan-300">{{ btc_si.recommendations.optimal_delta_threshold }}%</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-500">Dynamic Kelly:</span>
          <span class="font-medium">{{ '%.0f'|format(btc_si.recommendations.dynamic_kelly * 100) }}%</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-500">Sharpe Ratio:</span>
          <span class="font-medium {{ 'text-emerald-400' if btc_si.sharpe_ratio > 0 else 'text-red-400' }}">
            {{ btc_si.sharpe_ratio }}
          </span>
        </div>
      </div>
      {% endif %}
    </div>
  </div>

  <div class="rounded-xl p-5" style="background:#1a1a2e">
    <h2 class="text-lg font-semibold mb-3">📋 Trade History</h2>
    {% if btc.recent_trades %}
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr class="text-slate-500 text-xs uppercase">
          <th class="text-left py-2 pr-3">Time</th>
          <th class="text-left py-2 pr-3">Direction</th>
          <th class="text-right py-2 pr-3">Delta %</th>
          <th class="text-right py-2 pr-3">Conf</th>
          <th class="text-right py-2 pr-3">Entry</th>
          <th class="text-right py-2 pr-3">Cost</th>
          <th class="text-right py-2 pr-3">Result</th>
          <th class="text-right py-2 pr-3">PnL</th>
        </tr></thead>
        <tbody>
        {% for t in btc.recent_trades %}
        <tr class="border-t border-white/5">
          <td class="py-2 pr-3 text-xs text-slate-500">{{ t.timestamp[:16] if t.timestamp else '—' }}</td>
          <td class="py-2 pr-3">
            <span class="{{ 'text-emerald-400' if t.direction=='UP' else 'text-rose-400' }}">{{ t.direction }}</span>
          </td>
          <td class="py-2 pr-3 text-right text-xs">{{ '%+.4f'|format(t.delta_pct) if t.delta_pct else '—' }}</td>
          <td class="py-2 pr-3 text-right text-xs">{{ '%.0f'|format(t.confidence * 100) if t.confidence else '—' }}%</td>
          <td class="py-2 pr-3 text-right">${{ '%.2f'|format(t.entry_price) }}</td>
          <td class="py-2 pr-3 text-right">${{ '%.2f'|format(t.cost) }}</td>
          <td class="py-2 pr-3 text-right">
            <span class="px-1.5 py-0.5 rounded text-xs {{ 'bg-emerald-500/20 text-emerald-400' if t.won else 'bg-red-500/20 text-red-400' }}">
              {{ 'WIN' if t.won else 'LOSS' }}
            </span>
          </td>
          <td class="py-2 pr-3 text-right {{ 'text-emerald-400' if t.pnl and t.pnl > 0 else 'text-red-400' }}">
            {{ ('+' if t.pnl and t.pnl > 0 else '') + '%.4f'|format(t.pnl) if t.pnl else '—' }}
          </td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="text-sm text-slate-500 py-4">No trades yet.</div>
    {% endif %}
  </div>
</div>
</body>
</html>"""

DETAIL_FADI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Polymarket-Fadi — Fleet Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: {
    extend: { colors: { bg: '#0f0f1a', card: '#1a1a2e', card2: '#252542', accent: '#00d4aa', warn: '#f59e0b', danger: '#ef4444', cyan: '#06b6d4' } }
  }
}
</script>
<style>
* { font-family: 'Inter', system-ui, sans-serif; }
body { background: #0f0f1a; color: #e2e8f0; }
</style>
</head>
<body>
<div class="max-w-7xl mx-auto px-4 py-6">
  <a href="/fleet" class="text-cyan-400 hover:text-cyan-300 text-sm mb-4 inline-block">← Back to Fleet</a>
  <h1 class="text-2xl font-bold mb-6">🤖 Polymarket-Fadi — Detail</h1>

  {% if fadi.status == 'not_deployed' %}
  <div class="rounded-xl p-8 text-center" style="background:#1a1a2e">
    <div class="text-5xl mb-4">⏳</div>
    <h2 class="text-xl font-semibold mb-2">Not Deployed Yet</h2>
    <p class="text-sm text-slate-400">The Polymarket-Fadi bot will appear here once deployed.</p>
  </div>
  {% elif fadi.status == 'offline' %}
  <div class="rounded-xl p-8 text-center" style="background:#1a1a2e">
    <div class="text-5xl mb-4">😴</div>
    <h2 class="text-xl font-semibold mb-2">Bot Offline</h2>
    <p class="text-sm text-slate-400">Could not reach the Polymarket-Fadi bot at the configured URL.</p>
  </div>
  {% else %}
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
    <div class="rounded-xl p-5" style="background:#1a1a2e">
      <h2 class="text-sm font-semibold text-cyan-300 mb-3">📊 Status</h2>
      <div class="grid grid-cols-2 gap-3 text-sm">
        <div><span class="text-slate-500">Capital:</span> <span class="font-medium">\${{ fadi.data.currentCapital if fadi.data else '?' }}</span></div>
        <div><span class="text-slate-500">Peak:</span> <span class="font-medium">\${{ fadi.data.peakCapital if fadi.data else '?' }}</span></div>
        <div><span class="text-slate-500">Trades:</span> <span class="font-medium">{{ fadi.data.tradesExecuted if fadi.data else '?' }}</span></div>
        <div><span class="text-slate-500">Drawdown:</span> <span class="font-medium {{ 'text-red-400' if fadi.data and fadi.data.currentDrawdown > 0 else '' }}">{{ '%.1f'|format(fadi.data.currentDrawdown * 100) if fadi.data and fadi.data.currentDrawdown else '0' }}%</span></div>
        <div><span class="text-slate-500">Mode:</span> <span class="font-medium">{{ '📄 Paper' if fadi.data and fadi.data.paper else '🔴 Live' }}</span></div>
        <div><span class="text-slate-500">Paused:</span> <span class="font-medium {{ 'text-red-400' if fadi.data and fadi.data.isPaused else 'text-emerald-400' }}">{{ '⏸ Yes' if fadi.data and fadi.data.isPaused else '▶ No' }}</span></div>
      </div>
    </div>
    <div class="rounded-xl p-5" style="background:#1a1a2e">
      <h2 class="text-sm font-semibold text-amber-300 mb-3">📈 Strategy Allocation</h2>
      {% set alloc = fadi_si.recommended_allocation if fadi_si else {} %}
      {% if alloc %}
      <div class="space-y-2 text-sm">
        {% for strat, pct in alloc.items() %}
        <div class="flex items-center justify-between">
          <span class="text-slate-400">{{ strat }}</span>
          <span class="font-medium">{{ '%.0f'|format(pct * 100) }}%</span>
        </div>
        <div class="w-full h-1.5 rounded-full bg-slate-700">
          <div class="h-full rounded-full {{ 'bg-cyan-500' if strat=='smartMoney' else 'bg-emerald-500' if strat=='arbitrage' else 'bg-amber-500' if strat=='dipArb' else 'bg-rose-500' }}" style="width:{{ '%.0f'|format(pct * 100) }}%"></div>
        </div>
        {% endfor %}
      </div>
      {% else %}
      <div class="text-sm text-slate-500">Learning in progress... (needs data)</div>
      {% endif %}
    </div>
  </div>

  <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
    <div class="rounded-xl p-5" style="background:#1a1a2e">
      <h2 class="text-sm font-semibold text-emerald-300 mb-3">🧠 Self-Improvement Insights</h2>
      {% if fadi_si and fadi_si.learnings %}
      <ul class="space-y-1 text-sm">
        {% for l in fadi_si.learnings %}
        <li class="flex items-start gap-2">
          <span class="text-slate-500 mt-0.5">•</span>
          <span>{{ l }}</span>
        </li>
        {% endfor %}
      </ul>
      {% else %}
      <div class="text-sm text-slate-500">No insights yet — collecting data...</div>
      {% endif %}
    </div>
    <div class="rounded-xl p-5" style="background:#1a1a2e">
      <h2 class="text-sm font-semibold text-cyan-300 mb-3">🏆 Top Wallets</h2>
      {% if fadi_si and fadi_si.recommended_wallets %}
      <div class="text-xs space-y-1.5">
        {% for w in fadi_si.recommended_wallets[:5] %}
        <div class="flex items-center justify-between py-1 border-b border-white/5">
          <span class="font-mono text-slate-300">{{ w.wallet[:8] }}...</span>
          <span class="text-slate-500">{{ w.signals }} sigs · score {{ w.score }}</span>
        </div>
        {% endfor %}
      </div>
      {% else %}
      <div class="text-sm text-slate-500">Waiting for signals...</div>
      {% endif %}
      <div class="mt-2 text-xs text-slate-600">Updated every 30 min via self-improve daemon</div>
    </div>
  </div>
  {% endif %}
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
@app.route("/fleet")
@app.route("/fleet/")
def index():
    bots = get_all_bots()
    wh = bots.get("weatherhermes", {"status": "pending", "profiles": [], "recent_trades": []})
    btc = bots.get("btc5m", {"status": "pending", "recent_trades": []})
    fadi = bots.get("polyfadi", {"status": "pending"})
    return render_template_string(
        DASHBOARD_HTML,
        wh=wh, btc=btc, fadi=fadi,
        refresh=REFRESH_SECONDS,
        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


@app.route("/weatherhermes")
@app.route("/fleet/weatherhermes")
def weatherhermes_detail():
    wh = get_weatherhermes()
    if wh["status"] != "online":
        wh["profiles"] = []
    wh_si = get_wh_self_improve()
    return render_template_string(
        DETAIL_WH_HTML,
        wh=wh,
        wh_si=wh_si,
        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


@app.route("/btc5m")
@app.route("/fleet/btc5m")
def btc5m_detail():
    btc = get_btc5m()
    if btc["status"] != "online":
        btc["recent_trades"] = []
    try:
        btc_si_summary = _btc5m_si.get_summary()
    except Exception:
        btc_si_summary = {}
    return render_template_string(
        DETAIL_BTC_HTML,
        btc=btc,
        btc_si=btc_si_summary,
        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


@app.route("/polyfadi")
@app.route("/fleet/polyfadi")
def polyfadi_detail():
    fadi = get_polyfadi()
    try:
        fadi_si_summary = _fadi_si.get_summary()
    except Exception:
        fadi_si_summary = {}
    return render_template_string(
        DETAIL_FADI_HTML,
        fadi=fadi,
        fadi_si=fadi_si_summary,
        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


@app.route("/api/all")
def api_all():
    return jsonify(get_all_bots())


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "service": "fleet-dashboard"})


@app.route("/api/btc5m-learning")
def api_btc5m_learning():
    """Return self-improvement insights for BTC 5-Min Bot."""
    try:
        return jsonify({"btc5m": _btc5m_si.get_summary()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fadi-learning")
def api_fadi_learning():
    """Return self-improvement insights for Polymarket-Fadi."""
    try:
        return jsonify(_fadi_si.get_insights_json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[FLEET-DASH] Starting on :{port}")
    print(f"  WeatherHermes: {WEATHERHERMES_URL}")
    print(f"  BTC 5-Min:     {BTC5M_URL}")
    print(f"  Poly-Fadi:     {POLYFADI_URL or "NOT SET"}")

    # Start BTC5M self-improvement daemon
    def _btc5m_si_daemon():
        while True:
            try:
                _btc5m_si.learn()
            except Exception as e:
                print(f"[SI-BTC5M] Error: {e}")
            time.sleep(1800)
    btc5m_si_thread = threading.Thread(target=_btc5m_si_daemon, daemon=True)
    btc5m_si_thread.start()
    print('[FLEET-DASH] BTC5M Self-Improvement daemon started (30min cycle)')

    # Start FADI self-improvement daemon thread
    def _si_daemon():
        while True:
            try:
                _fadi_si.learn()
            except Exception as e:
                print(f"[SI] Error: {e}")
            time.sleep(1800)  # 30 min
    si_thread = threading.Thread(target=_si_daemon, daemon=True)
    si_thread.start()
    print("[FLEET-DASH] Self-Improvement daemon started (30min cycle)")

    app.run(host="0.0.0.0", port=port, debug=False)
