# FleetRisk Cursor Stall Fix
## 2026-06-02 00:15 UTC

### Executive Verdict

```
Orchestrierungs-Umbau:   GREEN  (Commit 8b30a80)
Scheduler Recovery:      GREEN  (Permission fix + restart)
Cursor Stall Fix:        GREEN  (Commit 33a5354)
Gesamtsystem:            WARNING (4 P2 Error-Jobs offen)
```

### Root Cause

`_latest_closed_trade_cursor()` in `system_optimizer.py` konnte keine Host-seitigen SQLite-DBs lesen.

Die `FLEET_BOTS`-Definition enthielt nur Container-interne Pfade:
```
"freqtrade-freqforge": {"dbs": ["/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite", ...]}
```

`Path("/freqtrade/user_data/...").exists()` ist im Hermes-Container **immer False**. Der Code fällt auf `docker exec python3 -c sqlite3` Fallback — aber das scheitert ebenfalls, weil `sqlite3` im container-eigenen PATH nicht via `python3` erreichbar ist. Alle Exceptions werden von `except Exception: continue` geschluckt → `latest = None` → Cursor bleibt bei `_consec_state_cursor()` hängen.

### DB Path Discovery

| Bot | Host DB Path | Lesbar? |
|-----|-------------|---------|
| FreqForge | `/home/hermes/projects/trading/freqforge/user_data/tradesv3.freqforge.dryrun.sqlite` | ✅ Ja |
| Regime-Hybrid | `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/tradesv3.regime_hybrid.dryrun.sqlite` | ✅ Ja |
| Canary | `/home/hermes/projects/trading/freqforge-canary/user_data/tradesv3.freqforge_canary.dryrun.sqlite` | ✅ Ja |
| Rebel | Docker Volume (kein Host-Pfad) | ❌ docker exec Fallback |

### Patch Summary

**Geandert: `orchestrator/scripts/system_optimizer.py`**

1. **`FLEET_BOTS`**: Jeder Bot-Eintrag bekommt `host_dbs` mit host-seitigen SQLite-Pfaden.
2. **`_latest_closed_trade_cursor()`**: Prüft zuerst `host_dbs` (direkt lesbar), `break` bei erstem Erfolg pro Bot.
3. **Fallback**: Wenn `host_dbs` leer ist (Rebel), wird der alte `docker exec` Pfad genutzt.
4. Die alte Container-Pfad-Logik (`dbs`) bleibt als **dritte Fallback-Ebene** erhalten.

### Cursor Validation

```
Vor Fix:   analysis_cursor = 2026-05-30T13:56:21  (56h frozen)
Nach Fix:  new cursor       = 2026-06-01T21:57:17  (48h forward)

Bots:
  FreqForge:     HOST_DB OK  -> latest_close=2026-06-01 06:45:31
  Regime-Hybrid: HOST_DB OK  -> latest_close=2026-06-01 18:30:02
  Canary:        HOST_DB OK  -> latest_close=2026-06-01 21:57:17  (BEST)
  Rebel:         FALLBACK OK -> latest_close=2026-05-29 23:45:03
```

### Trading Safety

| Check | Status |
|-------|--------|
| Alle Bots weiterhin `dry_run=True` | ✅ 4/4 |
| Trading-Bots restartet? | ❌ Keiner |
| Bot Configs geandert? | ❌ Nein |
| Strategien geandert? | ❌ Nein |
| Permission Drift? | ✅ Keine |
| CRON_ONLY Scripts? | ✅ Keine |

### Changed Files

```
 orchestrator/scripts/system_optimizer.py |  80 ++++++++++++++++++++-----------
 1 file changed, 58 insertions(+), 22 deletions(-)
```

### Commit Hash

```
33a5354 - fix(orchestrator): resolve FleetRisk closed-trade cursor lookup
```

### Remaining Issues

4 P2 Error-Jobs (unabhangig von diesem Fix):
- portfolio-rebalancer (nachster Lauf 08.06.)
- ghostbuster (Permission-Problem)
- daily-backup (Disk/Permission)
- daily-signal-confidence-monitor (LLM-Job Tool-Zugriff)

### Next Step

User entscheidet Reihenfolge. Optionen:
1. P2 Error-Jobs fixen (ghostbuster + daily-backup)
2. portfolio-rebalancer fixen
3. daily-signal-confidence-monitor fixen
4. Cron-Konsolidierung 30+ -> 15-20 Jobs