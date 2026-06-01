# Phase 2: FleetRisk, Signal-Bridge & Log-Rotation — 2026-05-30

## 1. FleetRisk Cursor reaktiviert

**Problem:** `consec_loss_state.json` hatte `analysis_cursor` auf 2026-05-23
stehen → die Consecutive-Loss-Analyse hat seit 7 Tagen keine neuen Trades
geprüft. Der `system_optimizer.py` Cron (alle 5min) rief zwar
`check_consecutive_loss_protection()` auf, aber wegen dem Cursor und der
24h-Begrenzung (`recent_filter` / `_recent_floor_dt`) wurden immer nur 0-3
Trades in `get_fleet_recent_trades()` gefunden → `len(trades) < 4` → sofortiger
`cleanup_expired_guard_state()` mit altem Cursor → Endlosschleife.

**Fix:** In `cleanup_expired_guard_state()` die Cursor-Priorität umgekehrt:
nicht mehr den `consec_state`-Cursor bevorzugen, sondern immer
`_latest_closed_trade_cursor()` als primäre Quelle nutzen.
`system_optimizer.py` Zeilen 189-190 gepatcht.

**Effekt:** Cursor auf 2026-05-30T13:56:21 fortgeschrieben. Der Optimizer
findet jetzt wieder 3+ Trades im 24h-Fenster und kann korrekt Loss-Streaks
erkennen.

## 2. Signal-Bridge Diskrepanz analysiert

**Beobachtung:** `primo_signal_state.json` zeigte alle 7 Pairs bei
`confidence=0.35` mit RG-2-Block, obwohl das ai-hedge-fund-crypto Signal
BTC/ETH/SOL mit `confidence=0.85` ausgab.

**Root Cause — keine Pipeline-Diskrepanz, sondern Signal-Timing:**
- Der ai-hedge-fund-crypto Container generiert ein neues Signal im
  60-90s Takt (deepseek-v4-pro)
- Die `trading_pipeline.py` läuft alle 10 Minuten via Cron
- Der Primo-Bridge-Status um 19:20:29 zeigt 0.35 — das war der Stand des
  hermes_signal.json zu diesem Zeitpunkt
- Erst um 19:42:28 (mein manueller Heartbeat-Trigger in Phase 1) wurde das
  Signal auf 0.85 aktualisiert
- **Kein Bridge-Bug. Die 0.35 waren ein valides, älteres Signal.**

**PG-3 Erkenntnis:** Der ShadowLogger (`shadow_decisions.jsonl`) enthält den
kompletten Entscheidungsverlauf. Der letzte Eintrag (2026-05-29T12:42) zeigt
BTC/ETH/SOL als ACCEPTED mit 0.65 confidence. Pipeline arbeitet korrekt,
RiskGuard-Gates (RG-1 bis RG-5) greifen wie designed.

## 3. Log-Rotation implementiert

**Skript:** `log_rotation.py` in `/opt/data/profiles/orchestrator/scripts/`
**Cron:** `log-rotation-daily` (b449af231ceb) — täglich 03:00 UTC

**Mechanismus:**
- .log und .jsonl Dateien > 5MB → gzip-Kompression + Rotation (.1.gz, .2.gz, .3.gz)
- .gz Backups > 30 Tage → gelöscht
- Scannt: orchestrator/logs, ai-hedge-fund-crypto/output/logs, freqtrade/logs
- Erster Lauf: 0 Rotationen (alle Dateien < 5MB, Grenzwert präventiv gewählt)
