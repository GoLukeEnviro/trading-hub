# AI-Hedge-Fund-Trigger-Orchestration-Fix
## 2026-06-01 23:07 UTC

### Problem
Das System hatte zwei konkurrierende Signal-Heartbeat-Mechanismen:
- `signal-heartbeat` (*/20 Min) — rief direkt /trigger via curl auf
- `smart-heartbeat` (*/10 Min) — prüfte latest/ und triggert heartbeat-Skript bei Staleness

**Race Conditions:**
1. Beide Heartbeats konnten gleichzeitig /trigger aufrufen (keine Lock-Mechanik)
2. latest/hermes_signal.json war 7+ Stunden stale, weil signal-heartbeat failed, aber smart-heartbeat nur latest/ prüft
3. /trigger (Single-Threaded Flask) blockierte bei parallelen Aufrufen

### Änderungen

#### Neue Skripte (Git Source)

**1. `orchestrator/scripts/global_trigger_lock.sh`**
Zentraler Lock-Wrapper für /trigger. Nutzt flock(LOCK_NB) mit stale-safe Detection.
- Lock-File: `orchestrator/state/locks/trigger.lock`
- Stale-Safe: Lock älter als 180s wird automatisch entfernt
- Lock-Busy: Exit 0 mit "SKIP lock_busy" → kein Telegram-Spam
- Ruft /trigger via `docker exec` + Python urllib auf (kein curl-Dependency)
- Modi: Normal, --test (Lock-Test ohne Trigger), --force (für manuelle Nutzung)

**2. `orchestrator/scripts/unified_signal_heartbeat.sh`**
Einzige autoritative Quelle für Signal-Freshness.
- Liest CANONICAL (`output/hermes_signal.json`) als Wahrheit, NICHT latest/
- Prüft Alter gegen `UNIFIED_TRIGGER_MIN=16min`
- Wenn fresh: Exit 0, kein Trigger
- Wenn stale/missing: Trigger via global_trigger_lock.sh
- Nach erfolgreichem Trigger: atomischer Sync CANONICAL → LATEST (cp.tmp → mv)
- Modi: --validate (Report), --test (Lock-Test), --force (Sofort-Trigger), normal

#### Modifizierte Skripte

**3. `orchestrator/scripts/trading_pipeline.py`**
- Neuer Layer 3.75: Nach erfolgreichem Signal-Read und Processing wird canonical → latest/ atomisch synchronisiert
- Damit wird latest/ bei jedem Pipeline-Durchlauf refreshed (nicht nur vom Heartbeat abhängig)
- Nutzt `shutil.copy2` (erhält ModTime) + `shutil.move` (atomic)

### Job-Änderungen

| Job | Vorher | Nachher |
|-----|--------|---------|
| signal-heartbeat | enabled=true, error | **paused**, Reason: REPLACED by unified-signal-heartbeat |
| smart-heartbeat | enabled=true, error | **paused**, Reason: REPLACED by unified-signal-heartbeat |
| unified-signal-heartbeat | — (neu) | enabled=true, */15 Min, no_agent script |

### Validierte Ergebnisse

| Check | Status |
|-------|--------|
| Script-Syntax (Python) | OK |
| Script-Syntax (Bash) | OK |
| Lock-Test (--test) | PASS: lock_acquired |
| Validate-Mode | PASS: VALIDATE FRESH age=0.6min |
| Force-Trigger | PASS: triggered_and_synced |
| Canonical = Latest Sync | VERIFIED: ts match |
| ai-hedge-fund-crypto Restart | OK (healthy in 60s) |
| Kein Trading-Bot restartet | VERIFIED: 18h+ uptime |
| Alle 4 Bots dry_run=True | VERIFIED |
| trading-guardian nicht berührt | VERIFIED |

### Verbleibende P2-Jobs (nicht fixiert in diesem Durchlauf)

Stand laut System-Lageplan vom 02.06.2026:

| Job | Status | Einschätzung |
|-----|--------|-------------|
| portfolio-rebalancer (Mo 06:00) | ERROR | Trivial — Trade-Daten-Fehler. Nächster Lauf am 08.06. |
| ghostbuster (alle 2h) | ERROR | Permission-Problem. Separater Fix nötig. |
| daily-backup (02:00 UTC) | ERROR | Disk/Permission. Separater Fix nötig. |
| daily-signal-confidence-monitor (alle 6h) | ERROR | LLM-Job mit glm-5.1. Tool-Zugriffsfehler möglich. |
| daily-heartbeat (06:00 UTC) | OK | Läuft sauber |
| cron-guardian (alle 6h) | OK | Läuft sauber |

**FleetRisk Cursor Stall:** Der Cursor in `consec_loss_state.json` ist seit 56h+ frozen. Die Priority-Reversal (`_latest_closed_trade_cursor()` vor `_consec_state_cursor()`) ist bereits in system_optimizer.py Zeile 190 implementiert. Der Stall kommt daher, dass `_latest_closed_trade_cursor()` auf Container-interne SQLite-Pfade (`/freqtrade/user_data/...`) zugreift — diese sind aus dem hermes-green Container nicht lesbar. Fix erfordert entweder (a) Host-seitige DB-Pfade oder (b) docker exec für SQLite-Query.

### Architektur vorher/nachher

**Vorher:**
```
signal-heartbeat (*/20 Min) ──curl──> /trigger ──> ai-hedge-fund-crypto ──> CANONICAL
smart-heartbeat (*/10 Min) ──run──> signal-heartbeat ──curl──> /trigger   |
                 └── prüft latest/ (stale!)                                  └──> latest/ (nie kopiert bei ERROR)
```

**Nachher:**
```
unified-signal-heartbeat (*/15 Min) ── liest CANONICAL ──> fresh? ──> SKIP (exit 0)
                                                     └── stale? ──> global_trigger_lock.sh (flock)
                                                                       └── docker exec /trigger ──> ai-hedge-fund-crypto
                                                                         └── atomic sync: CANONICAL → latest/
trading_pipeline (*/10 Min) ── liest CANONICAL ──> RiskGuard ──> Bridge-Write
                                            └── Layer 3.75: CANONICAL → latest/ sync
```

**Konkurrierende Heartbeats:** beseitigt. Nur EIN Job ruft /trigger auf.
**Lock-Mechanik:** Serialisiert über flock. Lock-Busy = SKIP, kein Telegram-Spam.
**latest/-Sync:** Doppelt abgesichert: Heartbeat + Pipeline.