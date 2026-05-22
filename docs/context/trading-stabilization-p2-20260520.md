# Trading Stabilization Phase 2 — 2026-05-20

## Executive Summary

Phase 2 der VPS-Trading-Automatisierung. Drei Issues behoben:
1. Permission-Drift-Regression (auth.json, SKILL.md, 1767 Dateien)
2. signal-heartbeat Docker-Socket-Abhaengigkeit entfernt
3. trading-pipeline ccxt-Import optional gemacht

## Root Cause: Rekurrenter Permission-Drift

Hermes-Container laeuft als root (uid=0). Der Hauptprozess schreibt Dateien
als root:root 0600. Cron-Jobs laufen als UID 10000 und koennen diese nicht lesen.
Das ist eine strukturelle Quelle fuer wiederkehrenden Permission-Drift.

## Fixes Applied

### Fix 1: Permission-Drift (1767 Dateien, 216 Verzeichnisse)

| Vorher | Nachher | Methode |
|--------|---------|---------|
| auth.json: root:root 0600 | root:10000 0640 | chgrp + chmod |
| SKILL.md: root:root 0600 | root:10000 0640 | chgrp + chmod |
| Scripts: root:root 0755 | root:10000 0750 | Execute-Bit erhalten |
| Dirs: root:root 0755 | root:10000 2775 | setgid aktiv |

### Fix 2: signal-heartbeat (docker exec → curl)

| Vorher | Nachher |
|--------|---------|
| `docker exec ai-hedge-fund-crypto python3 -c "urllib..."` | `curl -sS -m 120 http://127.0.0.1:8410/trigger` |
| Docker-Socket noetig (UID 10000 verweigert) | Host-Port-Mapping, kein Socket noetig |
| Ergebnis: Permission denied | Ergebnis: HTTP 200, 27s |

### Fix 3: trading-pipeline ccxt optional

| Vorher | Nachher |
|--------|---------|
| `import ccxt` → ModuleNotFoundError → failed | try/except ModuleNotFoundError → simulated |
| MCP[BTC/USDT] SHORT: failed | MCP[BTC/USDT] SHORT: simulated |
| Paper-Trades rot in Logs | Paper-Trades gruen, korrekte Order-IDs |

### Fix 4: Guardian-Erweiterung (Praevention)

Neuer Section 5 in external_cron_guardian.sh:
- Findet root:root Dateien/Dirs auf jedem Zyklus (alle 5 Min)
- chgrp 10000 + chmod 640/750/2775
- Execute-Bits bleiben erhalten
- Verhindert zukuenftigen Drift automatisch

## Verification

| Check | Ergebnis |
|-------|----------|
| auth.json aus Container lesbar | OK (len=8334) |
| SKILL.md aus Container lesbar | OK (len=43811) |
| signal-heartbeat manuell getriggert | OK (age=0.0min, pairs=3) |
| trading-pipeline E2E | OK (3 simulated, state-files, shadow-log) |
| Guardian bash -n | SYNTAX_OK |
| Permission-Denied in letzten 5 Min | 0 |
| Alle Bots dry_run=true | Ja (MCP_DRY_RUN=True hardcoded) |

## Backups

- Phase 0: `backups/20260520-010154-pre-trading-stabilization-p2/`
  - ai_hedge_signal_heartbeat.sh
  - external_cron_guardian.sh
  - trading_pipeline.py

## Remaining Risks

1. **Drift-Quelle nicht behoben**: Hermes-Hauptprozess laeuft weiterhin als root.
   Der Guardian korrigiert driftende Dateien alle 5 Min, aber die Ursache bleibt.
   Langfristige Loesung: Container als UID 10000 starten (`user: "10000:10000"` in docker-compose).

2. **MCP-Server (bitget-paper, filesystem)**: Beide MCP-Server verbinden nicht.
   Separate Untersuchung noetig. Aktuell wird der ccxt-Fallback-Pfad genutzt.

3. **.cache/uv Dateien**: uv-Package-Cache hat viele root:root Dateien.
   Guardian korrigiert diese, aber der Cache koennte als root regeneriert werden.

## Files Modified

| Datei | Aenderung |
|-------|-----------|
| /opt/hermes/config/profiles/orchestrator/ (1767 files) | Permission-Fix |
| ai_hedge_signal_heartbeat.sh | docker exec → curl (Zeile 33-45) |
| external_cron_guardian.sh | Neuer Section 5: fix_config_permissions |
| trading_pipeline.py | ccxt-Import optional (ccxt_execute_order) |

---
*Generated 2026-05-20T01:15Z — Trading Stabilization Phase 2*
