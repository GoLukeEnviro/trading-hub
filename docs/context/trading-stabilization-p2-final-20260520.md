# Trading Automation Stabilization — Phase 2 Final Report

**Datum:** 2026-05-20
**Verbindung:** ssh neu (Root-Zugang)
**Vorangehend:** Permission Drift Recovery Phase 1 (2026-05-19)

---

## Executive Summary

Drei kritische Issues wurden behoben, die das Trading-Automation-System blockierten:

1. **Permission-Drift-Regression** — 1767 Dateien + 216 Verzeichnisse unter `/opt/hermes/config/profiles/orchestrator/` wurden vom Hermes-Hauptprozess (root:root 0600) erstellt und blockierten Cron-Jobs (UID 10000). Alle korrigiert.

2. **signal-heartbeat Docker-Socket** — `docker exec` durch `curl 127.0.0.1:8410/trigger` ersetzt. Kein Docker-Socket-Zugriff mehr noetig.

3. **trading-pipeline ccxt** — ccxt-Import optional gemacht. Paper-Trades zeigen jetzt `simulated` statt `failed`.

Zusaetzlich wurde der Guardian um automatische Drift-Korrektur erweitert (alle 5 Minuten).

**Bestaetigung:** Kein Live-Trading, kein chown -R auf Projektwurzel, kein chmod 777.

---

## Backups

Alle Backups liegen unter:
`/home/hermes/projects/trading/orchestrator/backups/20260520-010154-pre-trading-stabilization-p2/`

| Datei | Original-Pfad |
|-------|---------------|
| ai_hedge_signal_heartbeat.sh | scripts/ai_hedge_signal_heartbeat.sh |
| external_cron_guardian.sh | scripts/external_cron_guardian.sh |
| trading_pipeline.py | scripts/trading_pipeline.py |

---

## Geaenderte Dateien

### 1. ai_hedge_signal_heartbeat.sh

**Aenderung:** Docker-Socket-Zugriff durch curl ersetzt.

Vorher (Zeile ~33-45):
```bash
HTTP_CODE=$(docker exec "$CONTAINER" python3 -c "
import urllib.request, json, sys
try:
    r = urllib.request.urlopen('http://localhost:8080/trigger', timeout=120)
    data = r.read()
    sys.stdout.buffer.write(data)
    sys.exit(0 if r.status == 200 else 1)
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>>"$LOG" > "$TEMP") && HTTP_OK=true || HTTP_OK=false
```

Nachher:
```bash
HTTP_CODE=$(curl -sS -m 120 -o "$TEMP" -w '%{http_code}' http://127.0.0.1:8410/trigger 2>>"$LOG")
[ "$HTTP_CODE" = "200" ] && HTTP_OK=true || HTTP_OK=false
```

**Warum:** UID 10000 hat keinen Docker-Socket-Zugriff. Host-Port-Mapping `127.0.0.1:8410` ist vom Host aus erreichbar und aequivalent.

### 2. external_cron_guardian.sh

**Aenderung:** Neuer Abschnitt 5 (fix_config_permissions) hinzugefuegt.

```bash
# 5. Fix permission drift on config files
CONFIG_DIR="$PROFILE_BASE"
if [ -d "$CONFIG_DIR" ]; then
    find "$CONFIG_DIR" -type f -user 0 -group 0 ! -executable \
        -exec chgrp 10000 {} \; -exec chmod 640 {} \; 2>/dev/null || true
    find "$CONFIG_DIR" -type f -user 0 -group 0 -executable \
        -exec chgrp 10000 {} \; -exec chmod 750 {} \; 2>/dev/null || true
    find "$CONFIG_DIR" -type d -user 0 -group 0 \
        -exec chgrp 10000 {} \; -exec chmod 2775 {} \; 2>/dev/null || true
fi
```

**Warum:** Hermes-Hauptprozess laeuft als root und erzeugt root:root-Dateien, die seine eigenen Cron-Jobs blockieren. Guardian korrigiert jetzt automatisch alle 5 Minuten.

**Merkmale:**
- Nur root:root-Dateien werden angefasst (`-user 0 -group 0`)
- Execute-Bits bleiben erhalten: nicht-ausfuehrbar → 640, ausfuehrbar → 750
- Verzeichnisse bekommen setgid (2775)
- Fehlschlaege sind nicht-letal (`|| true`)

### 3. trading_pipeline.py

**Aenderung:** ccxt-Import in `ccxt_execute_order()` optional gemacht.

```python
try:
    import ccxt
    exchange = ccxt.bitget({...})
    exchange.set_sandbox_mode(True)
except ModuleNotFoundError:
    logger.info(f"{layer}: ccxt not available, generating simulated order")
```

**Warum:** ccxt ist nicht im Host-Python installiert. Da `MCP_DRY_RUN=True` (hardcoded Zeile 51) alle Trades simuliert, ist der ccxt-Import ohnehin ueberfluessig. Paper-Orders werden jetzt mit generierter ID erstellt statt zu failen.

### 4. Permission-Drift Fix (1767 Dateien + 216 Verzeichnisse)

Einmalige Korrektur auf `/opt/hermes/config/profiles/orchestrator/`:

- Dateien (nicht-ausfuehrbar): `chgrp 10000` + `chmod 640`
- Dateien (ausfuehrbar, 8 Stueck): `chgrp 10000` + `chmod 750`
- Verzeichnisse: `chgrp 10000` + `chmod 2775` (setgid)

---

## Vorher / Nachher

| Komponente | Vorher | Nachher |
|------------|--------|---------|
| auth.json | root:root 0600, Permission Denied | root:10000 0640, lesbar (len=8334) |
| SKILL.md | root:root 0600, Permission Denied | root:10000 0640, lesbar (len=6240) |
| root:root Dateien | 1767 Dateien + 216 Dirs | 0 verbleibend |
| signal-heartbeat | docker exec → Permission Denied | curl 127.0.0.1:8410 → HTTP 200 |
| trading-pipeline | MCP[*] SHORT: failed | MCP[*] SHORT: simulated |
| Guardian | Nur jobs.json gesichert | Alle root:root-Dateien automatisch korrigiert |
| Guardian-Log | Permission-Drift-Eintraege | "All checks passed" (kontinuierlich) |

---

## Verifikationsergebnisse

Alle Checks am 2026-05-20 durchgefuehrt:

| Check | Ergebnis |
|-------|----------|
| auth.json lesbar als UID 10000 | OK — len=8334 |
| SKILL.md lesbar als UID 10000 | OK — len=6240 |
| root:root Dateien verbleibend | 0 Dateien, 0 Verzeichnisse |
| auth.json Berechtigungen | root:10000 0640 |
| signal-heartbeat curl fix aktiv | Ja — curl -sS -m 120 -o $TEMP -w '%{http_code}' http://127.0.0.1:8410/trigger |
| Guardian Abschnitt 5 aktiv | Ja — "Fix permission drift on config files" vorhanden |
| Guardian-Log letzte Eintraege | "All checks passed" (kontinuierlich alle 5 Min) |
| Permission-Denied in Logs | 0 Treffer in allen Log-Dateien |
| MCP_DRY_RUN hardcoded | Ja — Zeile 51: `MCP_DRY_RUN = True` |
| Alle Freqtrade Bots dry_run | Ja — 5/5 Bots: regime-hybrid, fomo-phase3, rsi, momentum, mvs |
| Signal-Bridge letzte Ausfuehrung | 2026-05-19T23:12:31Z — pairs_accepted=3, writes OK |
| Smart-Heartbeat | OK — letzter erfolgreicher Check 2026-05-19T23:22:00Z |
| Backups vorhanden | Ja — 3 Dateien unter backups/20260520-010154-* |

---

## Verbleibende Risiken

### 1. Strukturelle Drift-Quelle (Mittel)

Hermes-Container laeuft als root (`uid=0`). Der Hauptprozess erzeugt selbst root:root-Dateien.
Der Guardian puffert das alle 5 Minuten, aber das ist ein Band-Aid, kein Fix.

**Langfristige Loesung:** `user: "10000:10000"` in docker-compose.yml. Risiko: Interne Container-Prozesse koennten root-Rechte erwarten (z.B. apt-Install, Systemd-Services).

### 2. MCP-Server nicht verbunden (Niedrig)

`bitget-paper` und `filesystem` MCP-Server verbinden nicht. Auswirkung: Paper-Trade-Execution verwendet Fallback-Pfad (generierte simulierte Orders).

**Aufwand:** Separate Untersuchung der MCP-Server-Konfiguration noetig.

### 3. uv-Cache als root (Niedrig)

`.cache/uv` kann als root regeneriert werden. Guardian korrigiert automatisch.

---

## Deferred Issues

| Issue | Status | Naechster Schritt |
|-------|--------|-------------------|
| MCP-Server (bitget-paper, filesystem) | Nicht verbunden | Separate Untersuchung |
| Hermes Container als root | Strukturelle Drift-Quelle | docker-compose user-Direktive pruefen |
| Docker Guardian Path Divergence | Beobachtet | Spaeter sauber entscheiden |

---

## Hard-Rules-Bestaetigung

- Kein Live-Trading ausgefuehrt
- Kein `chown -R` auf Projektwurzel verwendet
- Kein `chmod 777` verwendet
- Kein Docker-Socket broad access gewaehrt
- `MCP_DRY_RUN=True` bleibt hardcoded (Zeile 51)
- Alle 5 Freqtrade-Bots bleiben `dry_run: true`
- Backups vor jedem Fix erstellt

---

*Report erstellt: 2026-05-20 — Trading Stabilization Phase 2 Final*
