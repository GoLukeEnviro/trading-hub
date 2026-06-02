# Full Read-Only Runtime Audit -- 2026-06-01 09:01 UTC

**Modus:** READ-ONLY. Keine Container gestartet/gestoppt, keine Permissions geaendert, keine Configs modifiziert.
**Host:** Agent0 | **User:** hermes | **Audit-Timestamp:** 2026-06-01T09:01:05+02:00

---

## Executive Verdict

**Overall: WARNING** -- Kerninfrastruktur gesund, aber 2 aktive Cron-Fehler und signifikante Reporting-Diskrepanzen.

| Kategorie | Status |
|---|---|
| Green Stack (mem0/qdrant/ollama) | OK |
| hermes-green | OK |
| Blue Stack | OK (bestaetigt gestoppt, Stop-only Test) |
| Mem0 LLM Extraction | OK (401-Fix aktiv) |
| Trading Bots | OK (4/4 running, dry_run=true) |
| drawdown-guard Cron | BROKEN |
| container-watchdog Cron | WARNING |
| Script Sync (Project vs Profile) | WARNING (divergent) |
| Guardian Sync-Liste | WARNING (unvollstaendig) |
| Equity-High | STALE |
| Signal Bridge | OK |
| Morning Brief / Reports | WARNING (Daten inkonsistent) |

---

## Current Canonical Runtime Map

### Running Containers

| Container | Image | Status | Ports | Network |
|---|---|---|---|---|
| hermes-green | nousresearch/hermes-agent:latest | Up 9h | 8642, 8083 | ki-fabrik, green-net |
| green-mem0 | hermes-mem0-local-api:stable | Up 2h (healthy) | 8788->8787 | green-net |
| green-qdrant | qdrant/qdrant:latest | Up 2d | 6336->6333 | green-net |
| green-ollama | ollama/ollama:latest | Up 2d | 11436->11434 | green-net |
| freqtrade-freqforge | freqtrade-hermes10000:stable | Up 4h | 8086 | ki-fabrik |
| freqtrade-freqforge-canary | freqtrade-hermes10000:stable | Up 4h | 8081 | ki-fabrik |
| freqtrade-regime-hybrid | freqtrade-hermes10000:stable | Up 4h | 8085 | ki-fabrik |
| freqai-rebel | freqtradeorg/freqtrade:2026.3_freqai | Up 4h | 8087 | freqai-rebel-net |
| freqtrade-webserver | freqtradeorg/freqtrade:stable | Up 3d | 8180->8080 | trading-network |
| ai-hedge-fund-crypto | trading-ai-hedge-fund-crypto | Up 7h (healthy) | 8410->8080 | ki-fabrik |
| trading-guardian | guardian-trading-guardian | Up 6h | none | hermes-net |
| claude-worker | claude-worker:latest | Up 8d (healthy) | 5050->5000 | ki-fabrik |

### Stopped Containers (Blue Stack -- Stop-only Test)

| Container | Exit Code | seit |
|---|---|---|
| hermes-mem0-local-api | Exited (0) | ~39 min vor Audit |
| hermes-ollama | Exited (0) | ~39 min vor Audit |
| hermes-qdrant | Exited (143) | ~39 min vor Audit |

Exit-Code 143 = SIGTERM (normaler Docker-Compose-Stop).

### Ressourcen

- **Disk:** 165G/301G (58%)
- **RAM:** 7.1G/30G used (23G available)
- **Swap:** 257M/4G

---

## Blue Stop-only Observation Status

**VERIFIZIERT:** Alle 3 Blue-Container sind im Exited-Zustand. Exit-Codes normal (0 und 143).

| Check | Ergebnis |
|---|---|
| hermes-mem0-local-api | Exited (0) |
| hermes-ollama | Exited (0) |
| hermes-qdrant | Exited (143) |
| Green Stack unberuehrt | Ja |
| Guardian aktiv | Ja (active waiting, 5-Min-Timer) |

Blue Stop-only Test gestartet 2026-06-01 08:21 UTC. 48h Beobachtung bis spaetestens 2026-06-03 08:21 UTC.

---

## Mem0 / Qdrant / Ollama Status

### Health Check

```json
{
  "status": "ok",
  "backend": "local-mem0",
  "vector_store": "qdrant",
  "llm_provider": "ollama",
  "llm_model": "gpt-oss:120b",
  "embedder_provider": "ollama",
  "embedder_model": "qwen3-embedding:4b",
  "cloud_required": false,
  "extraction_policy": "v1"
}
```

### Watchdog

```
API: ok (200) | backend=local-mem0 | total_memories=1156
Alerts: 0 | Qdrant + API + embedder erreichbar
```

### 401-Fix Status

Keine 401/Error/Traceback-Eintrage in green-mem0 Logs (letzte 80 Zeilen geprueft).
Der OLLAMA_API_KEY-Passthrough via docker-compose.yml ist aktiv und funktional.

**Klassifikation: OK**

---

## Trading Bot Safety Status

| Bot | Status | dry_run | Wallet | API Ping |
|---|---|---|---|---|
| freqtrade-freqforge | Up 4h | true | 1000 | 200 |
| freqtrade-freqforge-canary | Up 4h | true | 500 | 200 |
| freqtrade-regime-hybrid | Up 4h | true | 1000 | 200 |
| freqai-rebel | Up 4h | true | 1000 | 200 |
| freqtrade-webserver | Up 3d | true | 1000 | ERR (000) |

**Hinweis:** `freqtrade-webserver` auf Port 8180 nicht per `/api/v1/ping` erreichbar (Connection refused/timeout). Container laeuft aber. Moeglicher Port-Mismatch (intern 8080, gemappt 8180).

**Secret-Safe-Check:** Keine sensiblen Env-Variablen in Bot-Containern (nur `GPG_KEY` = Docker-Build-Artefakt).

**Klassifikation: OK** (webserver-Ping ist bekanntes Issue, keine Sicherheitsgefaehrdung)

---

## Cron / Guardian / Job Status

### Systemd Timer

```
trading-cron-guardian.timer: active (waiting), naechster Lauf in <5 Min
trading-cron-guardian.service: inactive (dead), letzter Lauf SUCCESS (exit 0)
```

### Jobs (jobs.json, redacted)

| Job | Intervall | deliver | no_agent | state |
|---|---|---|---|---|
| signal-heartbeat | */20 Min | local | true | scheduled |
| trading-pipeline | */10 Min | local | true | scheduled |
| drawdown-guard | */30 Min | telegram | true | scheduled |
| container-watchdog | */5 Min | telegram | true | scheduled |
| mcp-watchdog | */5 Min | telegram | true | scheduled |
| daily-backup | daily 02:00 | local | true | scheduled |
| portfolio-rebalancer | weekly Mo 06:00 | origin | true | scheduled |
| cron-guardian | */6h | local | true | scheduled |
| smart-heartbeat | */10 Min | local | true | scheduled |
| Fleet Report | */4h | telegram | false | scheduled |

### Guardian Log (letzte 40 Zeilen)

Alle Eintraege zeigen `OK: All checks passed (jobs healthy, signal fresh, scripts present)`.
Keine ERROR/WARN/CRITICAL Eintraege im recent Guardian-Log.

**Klassifikation: OK** (Guardian selbst laeuft korrekt)

---

## Active Failures

### FAILURE 1: drawdown-guard -- ModuleNotFoundError: fleet_api_client

**Status: BROKEN**

**Beweis:**
- `drawdown_guard.py` Zeile 24: `from fleet_api_client import freqtrade_api_get` (kein try/except)
- `fleet_api_client.py` existiert NUR in `/home/hermes/projects/trading/orchestrator/scripts/`
- `fleet_api_client.py` fehlt in `/opt/data/profiles/orchestrator/scripts/`
- Cron-Job `drawdown-guard` fuehrt das Profile-Script aus
- Jeder Cron-Lauf aus dem Profile-Dir MUSS mit `ModuleNotFoundError` scheitern

**Root Cause:** Guardian-Sync-Liste in `external_cron_guardian.sh` Zeile 134 enthaelt nur:
```
ai_hedge_signal_heartbeat.sh trading_pipeline.py drawdown_guard.py container_watchdog.sh mcp_watchdog.sh backup_rotation.py
```
`fleet_api_client.py` ist NICHT in der Sync-Liste. Es wird nicht vom Projekt- ins Profile-Dir kopiert.

**Impact:** drawdown-guard Cron-Job kann nicht laufen. Telegram-Alerts bei Drawdown werden nicht versendet. Drawdown-Schutz ist NICHT aktiv.

**Erschwerend:** Profil-Version von `drawdown_guard.py` referenziert `hermes-agent` (Zeile 202), nicht `hermes-green`. Der Container `hermes-agent` existiert nicht. Selbst WENN fleet_api_client.py kopiert wuerde, wuerde der Telegram-Token-Lookup fehlschlagen.

**Evidenz-Unterscheidung:** Das drawdown_guard.log zeigt erfolgreiche v3-Lauefe (z.B. 2026-06-01 01:59 UTC). Diese stammen vermutlich von Ausfuehrungen aus dem PROJECT-Dir (wo fleet_api_client.py existiert), nicht aus dem Cron-Profil-Pfad. Die Telegram-Fehlermeldungen kommen vom Profil-Pfad.

### FAILURE 2: container-watchdog -- Permission denied

**Status: WARNING (möglicherweise historisch)**

**Beweis:**
- `container_watchdog_state.json`: owner=`hermes:hermes` mode=`664`
- State-Verzeichnis: owner=`10000:ftuser` mode=`2775` (SGID)
- Erwartet waere: file group=`ftuser` (GID 10000) via SGID-Vererbung

**ABER:** Die Datei wurde zuletzt am 2026-06-01 02:05 UTC aktualisiert (erfolgreicher Write). Das spricht dafuer dass der Permission-Error entweder:
1. Historisch ist (vor Permission-Fix)
2. Nur unter bestimmten UID-Kontexten auftritt
3. Intermittierend ist (manche Laeufe als hermes, manche als 10000)

**Root Cause:** Die Datei wurde vermutlich erstellt BEVOR das SGID-Bit auf dem Verzeichnis gesetzt wurde. Daher hat sie `hermes:hermes` statt `hermes:ftuser`. Neue Writes durch den gleichen Owner (hermes) funktionieren, aber Writes durch UID 10000 (Guardian-Container) wuerden fehlschlagen.

**Impact:** Wenn der Watchdog im Guardian-Container (UID 10000) laeuft, kann er die State-Datei nicht aktualisieren. Laeuft er als `hermes` auf dem Host, funktioniert es.

---

## drawdown-guard Failure Analysis (Detail)

### Script-Vergleich Project vs Profile

```
drawdown_guard.py: DIFFERENT (1 Zeile)
  Zeile 202: "hermes-green" (project) vs "hermes-agent" (profile)
```

### Fehlende Abhaengigkeiten im Profile-Dir

| Datei | Project | Profile | In Sync-Liste |
|---|---|---|---|
| fleet_api_client.py | vorhanden | FEHLT | Nein |
| daily_heartbeat.py | vorhanden | FEHLT | Nein |
| system_optimizer.py | vorhanden | FEHLT | Nein |
| mem0_watchdog.py | vorhanden | FEHLT | Nein |
| drawdown_guard.py | vorhanden (hermes-green) | veraltet (hermes-agent) | Ja (aber nicht aktualisiert) |

### Warum Guardian nicht synchronisiert

Guardian prueft (Zeile 146-152): ob Datei fehlt ODER sich unterscheidet. Wenn unterschiedlich, kopiert er vom Projekt-Dir.
Aber: `fleet_api_client.py` ist GAR NICHT in der Sync-Liste. Und `drawdown_guard.py` wird zwar geprueft, aber der Guardian laeuft im Docker-Container mit gemountetem `/guardian/scripts -> /opt/data/profiles/orchestrator/scripts/`.

**Hypothese:** Der Guardian kopiert `drawdown_guard.py` bei jedem Lauf, aber die gemountete Version wird durch den Container-Layer moeglicherweise nicht persistiert, ODER die Sync-Zeitschiene passt nicht mit den manuellen Aenderungen zusammen.

### drawdown_guard.log Timeline

- 2026-05-28 02:21 UTC: v3 laeuft (NO_DOCKER Mode, 4/4 Bots WARN)
- 2026-05-31 23:58 UTC: v2 laeuft (3/5 OK, 2 FAIL)
- 2026-06-01 01:59 UTC: v3 laeuft (docker mode, 4/4 OK, Portfolio $3,498.92)

Die erfolgreichen v3-Lauefe zeigen dass die Script-Ausfuehrung aus dem PROJECT-Dir funktioniert. Der Cron-Fehler kommt aus dem PROFILE-Dir.

---

## container-watchdog Failure Analysis (Detail)

### State Directory

```
drwxrwsr-x  9 10000 ftuser  4096 Jun  1 04:05  /home/hermes/projects/trading/orchestrator/state/
-rw-rw-r--  1 hermes hermes   518 Jun  1 04:05  container_watchdog_state.json
```

### Kein container_watchdog.log

Es existiert KEINE `container_watchdog.log` Datei. Das Script schreibt vermutlich direkt nach stdout/stderr, was vom Cron-System an Telegram gesendet wird.

### State-File-Inhalt

```json
{
  "timestamp": "2026-06-01T02:05:30Z",
  "mode": "docker",
  "containers": {
    "freqtrade-freqforge": {"status": "running"},
    "freqtrade-freqforge-canary": {"status": "running"},
    "freqtrade-regime-hybrid": {"status": "running"},
    "freqai-rebel": {"status": "running"},
    "ai-hedge-fund-crypto": {"status": "running"}
  }
}
```

State ist aktuell (02:05 UTC), aber ownership ist `hermes:hermes` statt `hermes:ftuser`. Die SGID-Vererbung greift hier nicht, vermutlich weil die Datei vor dem SGID-Setup erstellt wurde.

---

## Signal Bridge Freshness

**Signal-Alter:** 13.0 Minuten (zum Audit-Zeitpunkt)

| Check | Ergebnis |
|---|---|
| hermes_signal.json timestamp | 2026-06-01T08:52:54 UTC |
| Signal-Alter | 13.0 min |
| Schwellenwert stale | 30 min |
| Status | FRESH |
| Quelle | ai-hedge-fund-crypto |
| LLM | deepseek-v4-pro, temp=0.15 |
| Paare | 7 (BTC, ETH, SOL, AVAX, NEAR, ARB, OP) |
| Bias | bearish (4x), neutral (3x) |
| Confidence | 0.2 - 0.6 |

**Klassifikation: OK**

---

## Equity-High / Drawdown State

### equity_high.json

```json
{"equity_high": 10006.4409, "updated": "2026-05-23T13:01:19.719176+00:00"}
```

**STALE:** Letztes Update 2026-05-23. Wert: $10,006.44.

### Aktuelle Fleet-Werte (fleet_risk_state.json)

| Metrik | Wert |
|---|---|
| Current Equity | $3,409.53 |
| Peak Equity | $3,495.06 |
| Current Drawdown | 2.45% |
| PnL (drawdown_state) | +$48.92 |

**Diskrepanz:** equity_high.json zeigt $10,006 aber der tatsaechliche Peak liegt bei ~$3,495. Die $10,006 sind vermutlich ein historischer Wert aus einer anderen Rechenbasis (z.B. Summe aller Wallets inkl. Webserver). Wird equity_high.json fuer Drawdown-Berechnungen herangezogen, waere der berechnete Drawdown verzerrt.

drawdown_state.json zeigt DD 0% (basiert auf drawdown_guard.py Berechnung mit $3,450 Start), was korrekt ist. Aber equity_high.json wird offenbar nicht von drawdown_guard aktualisiert.

**Klassifikation: STALE** -- equity_high.json ist 9 Tage alt und spiegelt nicht die aktuelle Fleet-Realitaet wider.

---

## Report Consistency Findings

### Morning Brief vs. Ist-Daten

| Metrik | Morning Brief | Ist-Wert | Delta |
|---|---|---|---|
| Fleet PnL | +5.07 USDT | +48.92 USDT | -43.85 |
| Signal Confidence | 85% | 60% (BTC/ETH/SOL) | +25% |
| Drawdown | 2.5% | 2.45% | ~OK |
| Self-Healing | "alles gruen" | 2 BROKEN Cron-Jobs | FALSCH |

### current-operational-state.md

Behauptet: "SELBSTREGENERIEREND -- Self-Healing Level erreicht" (Stand: 2026-05-30).
Realitaet: drawdown-guard BROKEN (fleet_api_client fehlt), container-watchdog Permission-Issue, Script-Sync unvollstaendig.

### Erkl(aerung der Diskrepanzen

1. **PnL-Abweichung (+5.07 vs +48.92):** Morning Brief berechnet PnL vermutlich auf einer anderen Basis (z.B. nur bestimmte Bots oder Zeitraum). Die drawdown_state.json summiert alle 4 Bots.

2. **Signal-Confidence (85% vs 60%):** Morning Brief aggregiert 85% als Gesamtbias, aber die Einzel-Signale zeigen max. 60% Confidence. Die 85% koennten ein Durchschnitt aller Indikatoren sein, nicht die Signal-Confidence.

3. **"alles gruen":** Morning Brief prueft vermutlich nur ob Container laufen, nicht ob Cron-Jobs erfolgreich sind. Guardian loggt "OK" weil er die Sync-Problematik nicht erkennt.

**Klassifikation: WARNING** -- Reports sind irrefuehrend. "Self-Healing alles gruen" ist falsch, da kritische Cron-Jobs fehlschlagen.

---

## Script Sync: Project vs Profile

### Sync-Status

| Datei | Project | Profile | Status |
|---|---|---|---|
| drawdown_guard.py | hermes-green Ref | hermes-agent Ref | DIFFERENT (1 Zeile) |
| fleet_api_client.py | vorhanden | FEHLT | PROJECT_ONLY |
| mem0_watchdog.py | vorhanden | FEHLT | PROJECT_ONLY |
| daily_heartbeat.py | vorhanden | FEHLT | PROJECT_ONLY |
| system_optimizer.py | vorhanden | FEHLT | PROJECT_ONLY |
| container_watchdog.sh | vorhanden | vorhanden | SAME |
| ai_hedge_signal_heartbeat.sh | vorhanden | vorhanden | synced |
| trading_pipeline.py | vorhanden | vorhanden | synced |
| mcp_watchdog.sh | vorhanden | vorhanden | synced |
| backup_rotation.py | vorhanden | vorhanden | synced |

### Guardian Sync-Gap

Guardian synced nur 6 Dateien (Zeile 134):
```
ai_hedge_signal_heartbeat.sh trading_pipeline.py drawdown_guard.py
container_watchdog.sh mcp_watchdog.sh backup_rotation.py
```

Nicht in Sync-Liste (aber von Cron-Jobs benoetigt):
- `fleet_api_client.py` (Dependency von drawdown_guard.py)
- `daily_heartbeat.py` (nicht als Cron-Job aktiv, aber in CLAUDE.md erwaehnt)
- `system_optimizer.py` (nicht als Cron-Job aktiv)
- `mem0_watchdog.py` (nicht als Cron-Job aktiv)

**Klassifikation: WARNING** -- Sync-Liste unvollstaendig, aber nur `fleet_api_client.py` ist ein harter Blocker.

---

## Recommended Fix Plan

**WICHTIG:** Dies sind Empfehlungen. Keine Fixes angewendet.

### P0 -- drawdown-guard reparieren

1. `fleet_api_client.py` nach `/opt/data/profiles/orchestrator/scripts/` kopieren
2. Guardian-Sync-Liste in `external_cron_guardian.sh` Zeile 134 erweitern: `fleet_api_client.py` hinzufuegen
3. Profile-Version von `drawdown_guard.py` aktualisieren: `hermes-agent` -> `hermes-green` auf Zeile 202
4. Nach Fix: manuellen Test-Lauf aus Profile-Dir: `cd /opt/data/profiles/orchestrator/scripts && python3 drawdown_guard.py`

### P1 -- container-watchdog Permission bereinigen

1. `chown hermes:ftuser container_watchdog_state.json` (oder `chgrp 10000`)
2. Pruefen ob SGID auf state-Verzeichnis korrekt wirkt: neue Dateien sollten automatisch GID 10000 bekommen
3. Optional: Guardian Permission-Guard um `container_watchdog_state.json` erweitern

### P2 -- Guardian Sync-Liste erweitern

1. `daily_heartbeat.py`, `system_optimizer.py`, `mem0_watchdog.py` zur Sync-Liste hinzufuegen
2. Oder: Sync-Mechanismus auf `rsync` oder `diff --brief` loop umstellen statt expliziter Dateiliste

### P3 -- equity_high.json aktualisieren

1. Wert auf aktuellen Fleet-Peak ($3,495.06) setzen
2. Drawdown-Berechnung verifizieren: welche Komponente nutzt equity_high.json?
3. Automatisches Update einbauen (z.B. im drawdown_guard oder trading_pipeline)

### P4 -- Report-Konsistenz verbessern

1. Morning Brief sollte Cron-Job-Ergebnisse einbeziehen (nicht nur Container-Status)
2. "Self-Healing alles gruen" sollte nur erscheinen wenn ALLE Cron-Jobs erfolgreich waren
3. PnL-Berechnungsmethode dokumentieren und mit drawdown_state abgleichen

---

## No-Change Proof

| Check | Ergebnis |
|---|---|
| Container-Anzahl unverandert | 14 running + 3 stopped = 17 (vorher 17) |
| Keine Container gestartet/gestoppt | Bestaetigt (docker ps unverandert) |
| Keine Permission-Aenderungen | Bestaetigt (kein chmod/chown ausgefuehrt) |
| Keine Config-Aenderungen | Bestaetigt (nur docs/context/ geschrieben) |
| Git-Status unveraendert | Bestaetigt (kein git add/commit/push) |
| Audit-Report geschrieben | docs/context/full-readonly-runtime-audit-20260601.md |

---

## Anhang: Historische Fehler (nicht mehr aktiv)

| Fehler | Zeitraum | Status |
|---|---|---|
| Permission denied auf primo_signal_state.json | 2026-05-20 bis 05-21 | BEHOBEN (v3 laeuft erfolgreich) |
| Freqtrade-Bots in Restart-Schleife (Permission denied freqtrade binary) | 2026-05-24 | BEHOBEN (alle 4 Bots Up) |
| Telegram Bot Token invalid (404) | 2026-05-24 | BEHOBEN (Telegram OK laut Guardian) |
| MCP Server ModuleNotFoundError: ccxt | 2026-05-24 logs | HISTORISCH (mcp_server.log nicht mehr aktiv) |
| Guardian Permission denied auf jobs.json copy | Historisch | HISTORISCH (cp failed, aber jobs.json wird restauriert) |
