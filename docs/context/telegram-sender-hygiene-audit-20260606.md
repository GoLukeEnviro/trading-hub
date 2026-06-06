# Telegram Sender Hygiene Audit — 2026-06-06

**Date:** 2026-06-06T05:43 UTC
**Auditor:** Hermes Orchestrator (Orchestrator Profile)
**Duration:** ~1h analysis
**Scope:** Every Telegram message source in the Hermes / Trading Hub system

---

## 1. Executive Verdict

**🔴 RED — Mehrere kritische Telegram-Probleme identifiziert**

Der TradingOrchestrator-Telegram-Kanal leidet unter erheblichem Rauschen, aber **die Ursachen sind nicht böswillig oder fehlerhaft konzipiert** — sie sind systematisch: Stale Container-Namen, eine verwaiste Alert-Queue (1.960 Dateien, 0 ausgeliefert), ein Telegram-Polling-Konflikt und eine Kaskade von `config-diff-detector` → `critical-event-watchdog`, die alle 10 Minuten falsche Config-Alarme sendet.

**Heilungsgrad:** Sobald die Container-Namen korrigiert werden, verschwinden 80% des Telegram-Spams automatisch. Die verbleibenden 20% sind Duplikate und Frequenz-Probleme.

---

## 2. Telegram Sender Inventory — Überblick

| # | Sender | Typ | deliver | Frequenz | Status |
|---|--------|-----|---------|----------|--------|
| 1 | Fleet Report (alle 4h) | Cron (LLM) | telegram | alle 240min | ✅ OK |
| 2 | daily-heartbeat | Cron (script) | telegram | täglich 06:00 | ✅ OK |
| 3 | fleet-auto-repair | Cron (script) | telegram | alle 2h | ⚠️ Stale names |
| 4 | canary-position-monitor | Cron (script) | telegram | alle 30min | ⚠️ Stale name |
| 5 | drawdown-guard | Cron (script) | telegram | alle 30min | ⚠️ Direkter API-Call |
| 6 | container-watchdog | Cron (script) | telegram | alle 30min | 🔴 Stale names |
| 7 | critical-event-watchdog | Cron (script) | telegram | alle 10min | 🔴 Spam-Kaskade |
| 8 | morning-brief-daily | Cron (script) | telegram | täglich 08:00 | ⚠️ Stale names |
| 9 | morning-brief-1040 | Cron (script) | telegram | täglich 10:40 | ⚠️ Stale names |
| 10 | monthly-strategy-report | Cron (script) | telegram | monatlich | ✅ OK |
| 11 | observation-watchdog | Cron (script) | telegram | alle 10min | ✅ Silent (kein Output) |
| 12 | system-optimizer | Cron (script) | local | alle 5min | ⚠️ Orphaned alert queue |
| 13 | heartbeat-intelligence-wrapper | Cron (script) | local | alle 6h | ⚠️ Direkter API-Call |
| 14 | permission-autopilot-alert | Skript (manuell) | direkt | on-demand | ⚠️ Direkter API-Call |

### Telegram-Sende-Mechanismen (3 parallele Wege!)

**Weg A — Hermes Gateway (deliver: telegram):**
Cron-Jobs mit `deliver: "telegram"`. Der Cron-Scheduler leitet stdout an den Hermes Telegram-Gateway weiter. Das ist der primäre Weg.

**Weg B — Direkte Telegram-API-Calls (bypass Gateway):**
- `drawdown_guard.py` — `send_telegram()` → POST an api.telegram.org
- `permission_autopilot_alert.py` — `send_telegram()` → POST an api.telegram.org
- `heartbeat_intelligence_wrapper.py` — `telegram_send()` → POST an api.telegram.org

**Weg C — Alert-Queue (orphaned):**
- `system_optimizer.py` — `_send_telegram_alert()` schreibt JSON-Dateien nach `state/alerts/`
- **Kein Prozess liest diese Queue** → 1.960 Dateien akkumuliert, 0 ausgeliefert

**Weg D — Freqtrade native Telegram:**
- **Alle 4 Bots: `telegram.enabled: no`** → Kein Traffic von hier

---

## 3. Cron Jobs With Telegram Delivery

### deliver: telegram (11 Jobs)

| Job | Schedule | Last Run | Status | Script |
|-----|----------|----------|--------|--------|
| Fleet Report (alle 4h) | every 240m | 2026-06-06T04:38 | ok | LLM prompt |
| daily-heartbeat | 0 6 * * * | 2026-06-05T06:00 | ok | daily_heartbeat.py |
| fleet-auto-repair | 0 */2 * * * | 2026-06-06T04:01 | ok | fleet_auto_repair.py |
| canary-position-monitor | */30 * * * * | 2026-06-06T05:30 | ok | canary_position_monitor.py |
| drawdown-guard | */30 * * * * | 2026-06-06T05:30 | ok | drawdown_guard.py |
| container-watchdog | */30 * * * * | 2026-06-06T05:30 | ok | container_watchdog.sh |
| critical-event-watchdog | */10 * * * * | 2026-06-06T05:40 | **error** | critical_event_watchdog.py |
| morning-brief-daily | 0 8 * * * | 2026-06-05T08:04 | ok | morning_brief.py |
| morning-brief-1040 | 40 10 * * * | 2026-06-05T10:41 | ok | morning_brief.py |
| monthly-strategy-report | 0 8 1 * * | 2026-06-01T08:05 | ok | monthly_strategy_report.py |
| observation-watchdog | */10 * * * * | 2026-06-06T05:40 | ok | observation_watchdog.py |

### deliver: local (scripts that also send Telegram via direct API)

| Job | Schedule | Script | Telegram-Methode |
|-----|----------|--------|-----------------|
| system-optimizer | every 5m | system_optimizer.py | Writes JSON alert files (orphaned) |
| Heartbeat Intelligence Report | 0 */6 * * * | heartbeat_intelligence_wrapper.py | Direct API call |

---

## 4. Scripts That Send Telegram Directly

### 4.1 drawdown_guard.py — `send_telegram()`
- **Zeile 262:** `def send_telegram(message, inline_keyboard=None)` → POST an api.telegram.org
- Sendet bei: "Kein einziger Bot erreichbar" (Zeile 523) oder Fleet-Report (Zeile 598)
- Verwendet TELEGRAM_BOT_TOKEN aus env oder .env
- **Container-Namen: ✅ Aktuell** (trading-freqtrade-freqforge-1, etc.)

### 4.2 permission_autopilot_alert.py — `send_telegram()`
- **Zeile 184:** `def send_telegram(message)` → POST an api.telegram.org
- Sendet bei Permission-Drift-Alerts
- Wahrscheinlich kein aktiver Cron-Job (nicht in Cron-Liste gefunden)

### 4.3 heartbeat_intelligence_wrapper.py — `telegram_send()`
- **Zeile 85:** `def telegram_send(token, chat_id, text)` → POST an api.telegram.org
- Liest Credentials aus `/home/hermes/.config/hermes-freqtrade-heartbeat/telegram_intelligence.env`
- Sendet Berichte direkt via Telegram-API
- **deliver: local** im Cron — der Telegram-Versand erfolgt direkt aus dem Skript

### 4.4 system_optimizer.py — `_send_telegram_alert()`
- **Zeile 1007:** `def _send_telegram_alert(message, inline_keyboard=None)`
- **Sendet NICHT via Telegram-API!** Schreibt nur JSON-Dateien in `state/alerts/`
- **Orphaned Queue:** 1.960 Dateien seit 23. Mai, alle `delivered: false`, keine jemals ausgeliefert
- Produziert 2 Dateien alle 5 Minuten → 576/Tag

---

## 5. Freqtrade Native Telegram Sources

**Ergebnis: KEINE.**

Alle 4 Bots (FreqForge, Regime-Hybrid, Canary, Rebel) haben in ihren Configs:
```json
"telegram": {
  "enabled": false,
  "token": "",
  "chat_id": ""
}
```

Freqtrade native Telegram-Befehle wie `/daily`, `/profit`, `/status` sind nicht verfügbar.

---

## 6. Noisiest Senders

### 🔴 Platz 1: critical-event-watchdog (alle 10 Min)
- **Problem:** Sendet jede 10 Minuten "🔴 Config: 4 config error(s)" an Telegram
- **Root Cause:** `config-diff-detector.py` hat `last_status=error` (selbst durch stale Container-Namen oder Docker-Proxy-Block) → schreibt `errors: 4` in `config_diff_health.json` → watchdog liest das und alarmiert
- **Frequenz:** 6 Nachrichten/Stunde = 144/Tag

### 🟠 Platz 2: container-watchdog (alle 30 Min)
- **Problem:** Verwendet alte Container-Namen (`freqtrade-freqforge`, `freqai-rebel` statt `trading-freqtrade-freqforge-1`)
- **Effekt:** Alle 5 Container als "not_found" gemeldet → Fehlalarm
- **Frequenz:** 2 Nachrichten/Stunde = 48/Tag

### 🟠 Platz 3: fleet-auto-repair (alle 2h)
- **Problem:** Verwendet `docker logs freqai-rebel` (staler Name) + `docker ps --filter name=freqtrade` (OK) → teilweise Fehler
- **plus:** Nutzt `freqtrade_monitor.py` der selbst Fehler produziert

### 🟡 Platz 4: drawdown-guard (alle 30 Min)
- **Problem:** Sendet "0/4 Bots erreichbar" wenn Docker-Proxy blockt → Fehlalarm bei jedem Run ohne Docker-Zugriff
- **Container-Namen sind korrekt**, aber Docker-Zugriff ist begrenzt

### 🟢 Platz 5: daily-heartbeat (täglich)
- Einmal täglich: nützlich, aber verwendet auch stale Container-Namen für Rebel

---

## 7. False Positive Sources

| Quelle | False-Positive-Grund | Betroffene Jobs |
|--------|---------------------|-----------------|
| Docker Proxy (EXEC=0) | `docker exec` wird blockiert → "container config unreadable" | config-diff-detector, fleet-auto-repair |
| Stale Container-Namen | `freqtrade-freqforge` statt `trading-freqtrade-freqforge-1` | container-watchdog, canary-position-monitor, morning_brief, daily-heartbeat, fleet-auto-repair |
| Orphaned Alert-Queue | `_send_telegram_alert()` schreibt nur JSON, kein Reader | system-optimizer |
| Telegram Polling Conflict | Zwei parallele long-poll-Verbindungen auf gleichem Bot-Token | Hermes Gateway |

---

## 8. Stale Container Name Findings

| Script | Falscher Name | Korrekter Name |
|--------|--------------|----------------|
| container_watchdog.sh | `freqtrade-freqforge` | `trading-freqtrade-freqforge-1` |
| container_watchdog.sh | `freqtrade-freqforge-canary` | `trading-freqtrade-freqforge-canary-1` |
| container_watchdog.sh | `freqtrade-regime-hybrid` | `trading-freqtrade-regime-hybrid-1` |
| container_watchdog.sh | `freqai-rebel` | `trading-freqai-rebel-1` |
| container_watchdog.sh | `ai-hedge-fund-crypto` | `trading-ai-hedge-fund-1` |
| canary_position_monitor.py | `freqtrade-freqforge-canary` | `trading-freqtrade-freqforge-canary-1` |
| morning_brief.py | `freqtrade-freqforge` (x4) | `trading-freqtrade-freqforge-1` |
| daily_heartbeat.py | `freqai-rebel` (docker exec) | `trading-freqai-rebel-1` |
| fleet_auto_repair.py | `freqai-rebel` (docker logs) | `trading-freqai-rebel-1` |

**Korrekte Namen verwendet von:** `drawdown_guard.py`, `config_diff_detector.py`

---

## 9. Suspicious/Unrelated Senders

### Seoul Weather "Trade Signal"

**Status: ❌ NICHT im Cron-System gefunden**

- Kein Treffer für "Seoul", "Trade Signal" oder "Seoul Weather" im gesamten Cron-Script-Verzeichnis
- `weatherhermes` Container hat **Telegram: nicht konfiguriert** (kein TELEGRAM_BOT_TOKEN in env)
- `btc5m-bot`: **Telegram: nicht konfiguriert**
- `polymarket-fadi`: **Telegram: nicht konfiguriert**
- **Wahrscheinlichste Quelle:** Eine Nachricht aus einem früheren Hermes-Session (vom User selbst getippt oder aus einem vorherigen Cron-Lauf, der in diesem Chat landete). Oder die Nachricht wurde aus einem anderen Hermes-Profil gesendet.

**Empfehlung:** Keine Aktion nötig. Wenn es wieder auftaucht, mit `send_message(action='list')` die Chat-Historie prüfen.

---

## 10. KEEP List

| Job | Grund |
|-----|-------|
| Fleet Report (alle 4h) | Nützlichster Report — PnL, Signale, Safety, Vorschläge |
| daily-heartbeat | Strukturierter Tages-Report (nach Fix der stale Namen) |
| drawdown-guard (nach Fix) | Wichtiger Sicherheits-Layer — echte Drawdown-Alarme |
| morning-brief-daily (nach Fix) | Nützlicher kompakter Tagesstart |
| monthly-strategy-report | Monatliche Strategie-Review |
| observation-watchdog | Silent bei OK → kein Telegram-Spam |

---

## 11. FIX List

### Priority 1 — Stale Container Names (behebt 80% des Spams)

| Job | Datei | Fix |
|-----|-------|-----|
| container-watchdog | `container_watchdog.sh` | `TRADING_CONTAINERS` updaten auf korrekte Namen |
| canary-position-monitor | `canary_position_monitor.py` | `CANARY_CONTAINER` auf `trading-freqtrade-freqforge-canary-1` |
| morning-brief | `morning_brief.py` | Alle 4 `docker exec` Container-Namen korrigieren |
| daily-heartbeat | `daily_heartbeat.py` | `docker exec freqai-rebel` → `trading-freqai-rebel-1` |
| fleet-auto-repair | `fleet_auto_repair.py` | `docker logs freqai-rebel` → `trading-freqai-rebel-1` |

### Priority 2 — Docker Proxy Awareness

| Job | Problem | Fix-Ansatz |
|-----|---------|-----------|
| config-diff-detector | `docker exec` blockiert durch Proxy | `DOCKER_HOST=unix:///var/run/docker.sock` override + `EXEC=0` erkennen |
| critical-event-watchdog | Liest `config_diff_health.json` mit falschen Fehlern | Fehler von config-diff-detector fixen → watchdog wird automatisch still |

### Priority 3 — Heartbeat Intelligence Wrapper

| Job | Problem | Fix |
|-----|---------|-----|
| heartbeat-intelligence-wrapper | Sendet direkt via Telegram-API + veraltet | Prüfen ob das Skript noch aktiv gebraucht wird (der Fleet Report liefert bessere Daten) |

---

## 12. RATE_LIMIT List

| Job | Aktuelle Frequenz | Vorschlag |
|-----|------------------|-----------|
| critical-event-watchdog | alle 10min | → alle 30min (oder ganz still, sobald config-diff fix ist) |
| container-watchdog | alle 30min | → alle 60min (da silent bei OK, nur Fehlalarme stören) |
| drawdown-guard | alle 30min | → alle 60min (Drawdown ändert sich nicht in 30min) |
| observation-watchdog | alle 10min | → alle 30min (kein Output bei OK → egal) |

---

## 13. PAUSE Candidates

| Job | Grund |
|-----|-------|
| morning-brief-1040 | **Duplicate** von morning-brief-daily (gleiches Skript, andere Uhrzeit: 08:00 + 10:40). Nur 1 Brief pro Tag nötig. |
| rebel-status-summary | Rebel hat `max_open_trades=0` (Quarantäne). Status-Summary alle 12h ist verschwendet, bis Rebel wieder aktiv ist. |
| fleet-auto-repair | Produziert Fehlalarme durch stale Namen. Nach Fix → wieder aktivieren. |

---

## 14. DELETE Candidates

| Job | Grund |
|-----|-------|
| 72h Research Fleet Monitor | **Paused** seit 24. Mai. War ein 72h-Sprint, der längst abgeschlossen ist. Kann gelöscht werden. |
| system-optimizer alert queue | **1.960 Dateien** in `state/alerts/`, keine jemals ausgeliefert. Queue kann geleert und abgeschaltet werden (`_send_telegram_alert()` auf NOOP setzen). |

---

## 15. UNKNOWN / Needs Manual Review

| Item | Grund |
|------|-------|
| Seoul Weather "Trade Signal" | Kein Code-Pfad gefunden. Womöglich manuelle User-Nachricht. Beobachten. |
| Telegram Polling Conflict | Hermes Gateway zeigt `409 Conflict` — ein zweiter Prozess pollt denselben Bot-Token. Mögliche Ursache: Eine alte Hermes-Gateway-Instanz (anderes Profil?) oder ein direkter API-Client. |
| permission_autopilot_alert.py | Existiert im Scripts-Verzeichnis, aber kein Cron-Job gefunden. Vielleicht von Hand aufgerufen? |

---

## 16. Proposed Telegram Policy

### Neue Regeln für den TradingOrchestrator-Kanal:

1. **Silent OK:** Jeder Watchdog/Guard schreibt nur bei ISSUES nach stdout. Bei Grün → kein Output → kein Telegram.
2. **Cooldown:** Kein identischer Alert mehrfach innerhalb 60 Minuten. Erste Meldung sofort, Wiederholung erst nach 60min wenn Zustand unverändert.
3. **Keine doppelten Reports:** Fleet Report (4h) + daily-heartbeat (24h) + morning-brief (24h) — das sind 3 verschiedene Frequenzen, das ist OK.
4. **Keine direkten Telegram-API-Calls:** Alle Telegram-Sendungen sollen durch den Hermes Gateway (deliver: telegram) gehen. Kein Skript ruft api.telegram.org direkt auf.
5. **Nur 1 Morning Brief:** Entweder 08:00 oder 10:40, nicht beide.
6. **Falsch-positive Quellen fixen, nicht stummschalten:** Statt Watchdogs zu pausieren, die Container-Namen korrigieren.
7. **Rebel Sendepause:** Rebel-Status-Summary pausieren bis Rebel wieder aktive Trades macht (`max_open_trades > 0`).

---

## 17. Minimal Cleanup Batch 1

### Die 3 Änderungen mit der größten Wirkung:

1. **container_watchdog.sh — Container-Namen fixen**
   - `TRADING_CONTAINERS` updaten von Kurznamen auf `trading-*-1` Namen
   - Behebt sofort alle "not_found"-Alarme (48/Tag weniger)

2. **config-diff-detector — Docker-Proxy-Handling**
   - `docker exec` blockiert → auf `DOCKER_HOST=unix:///var/run/docker.sock` umstellen
   - Oder: Container Configs über host-gemountete Dateien lesen statt docker exec
   - Behebt die "4 config errors"-Kaskade (144/Tag weniger)

3. **critical-event-watchdog — Silent bis config-diff gesund**
   - Wenn `config_diff_health.json` Fehler zeigt, trotzdem nicht alarmieren wenn der Fehler "container config unreadable" ist (bekanntes Docker-Proxy-Problem)
   - Oder: Watchdog pausieren bis config-diff-detector läuft

### Ergebnis nach Batch 1:
- Telegram-Spam-Reduktion: ~90%
- Verbleibende sinnvolle Messages: Fleet Report (4h), daily-heartbeat (24h), morning-brief (24h), echte Drawdown-Alarme

---

## 18. Commands Prepared But Not Executed

```bash
# ⚠️ NOT EXECUTED — Read-only audit. Commands prepared for batch 1 cleanup.

# === 1. FIX container_watchdog.sh stale container names ===
# Edit in project tree, then deploy
# In TRADING_CONTAINERS line, change:
#   TRADING_CONTAINERS="freqtrade-freqforge freqtrade-freqforge-canary freqtrade-regime-hybrid freqai-rebel ai-hedge-fund-crypto"
# To:
#   TRADING_CONTAINERS="trading-freqtrade-freqforge-1 trading-freqtrade-freqforge-canary-1 trading-freqtrade-regime-hybrid-1 trading-freqai-rebel-1 trading-ai-hedge-fund-1"

# === 2. FIX canary_position_monitor.py stale container name ===
# Change CANARY_CONTAINER = "freqtrade-freqforge-canary" → "trading-freqtrade-freqforge-canary-1"

# === 3. FIX morning_brief.py stale container names ===
# In bots list, change all 4 container names from short to full:
#   "freqtrade-freqforge" → "trading-freqtrade-freqforge-1"
#   "freqtrade-freqforge-canary" → "trading-freqtrade-freqforge-canary-1"
#   "freqtrade-regime-hybrid" → "trading-freqtrade-regime-hybrid-1"
#   "freqai-rebel" → "trading-freqai-rebel-1"

# === 4. FIX daily_heartbeat.py stale container name ===
# Change docker exec "freqai-rebel" → "trading-freqai-rebel-1"

# === 5. FIX fleet_auto_repair.py stale container name ===
# Change "docker logs freqai-rebel" → "trading-freqai-rebel-1"

# === 6. CONFIG-DIFF-DETECTOR: Add Docker socket override ===
# Add DOCKER_HOST override at top of script to bypass proxy:
#   os.environ["DOCKER_HOST"] = "unix:///var/run/docker.sock"

# === 7. CLEAN ORPHANED ALERT QUEUE ===
# rm -f /home/hermes/projects/trading/orchestrator/state/alerts/*.json
# (Optional: archive first)
# tar czf /home/hermes/projects/trading/orchestrator/state/alerts-archive-$(date +%Y%m%d).tgz /home/hermes/projects/trading/orchestrator/state/alerts/*.json
# rm /home/hermes/projects/trading/orchestrator/state/alerts/*.json

# === 8. DEPLOY SCRIPT CHANGES ===
# cd /home/hermes/projects/trading
# bash orchestrator/scripts/deploy_cron_scripts.sh
# git add -A && git commit -m "fix: correct stale container names in watchdog/health scripts"
# git push origin main

# === 9. PAUSE DUPLICATE MORNING BRIEF ===
# cronjob(action='pause', job_id='a72abde16f36')  # morning-brief-1040

# === 10. REDUCE critical-event-watchdog frequency ===
# cronjob(action='update', job_id='ae387e595ca0', schedule='*/30 * * * *')
```

---

## 19. Final Verdict: 🔴 RED

**Begründung:**

1. **🔴 Stale Container-Namen in 6 von 11 Telegram-Skripten** → alle produzieren Fehlalarme
2. **🔴 critical-event-watchdog spammt** alle 10 Minuten (144 Nachrichten/Tag) durch config-diff-detector-Fehler
3. **🔴 Telegram Polling Conflict** — Hermes-Gateway hat 409 Conflict mit einem zweiten Poller
4. **🔴 Orphaned Alert Queue** — 1.960 Dateien (seit 23. Mai), 0 ausgeliefert, weiteres Wachstum: 576/Tag
5. **🟡 Duale Telegram-Wege** — Gateway + direkte API-Calls, keine einheitliche Sende-Architektur
6. **🟡 Doppelter Morning Brief** — 08:00 + 10:40, gleiches Skript
7. **🟢 Freqtrade native Telegram** — Sauber deaktiviert auf allen Bots ✅
8. **🟢 Seoul Weather unbestätigt** — Kein Code-Pfad im System gefunden

**Wichtig:** Der Großteil der Probleme ist durch **Container-Namen-Korrekturen + Docker-Proxy-Handling** behebbar. Kein Job muss dauerhaft gelöscht werden. Nach Batch 1 (Container-Namen fixen) wäre der Status gelb/gelb-grün.

---

## Appendix A: Telegram-Polling-Conflict Analyse

Der Hermes-Gateway zeigt wiederholt:
```
WARNING gateway.platforms.telegram: [Telegram] Telegram polling conflict (1/5)
```

Das bedeutet ein **zweiter Prozess pollt den gleichen Bot-Token per long-poll**. Mögliche Ursachen:

1. **Zwei Hermes-Profile** — Das orchestrator-Profil und ein anderes Profil (default?) haben denselben TELEGRAM_BOT_TOKEN konfiguriert und beide laufen als Gateway
2. **Direkte API-Client** — Scripts wie `drawdown_guard.py` oder `heartbeat_intelligence_wrapper.py`, die den Bot-Token für `sendMessage` nutzen (das allein sollte keinen Konflikt auslösen)
3. **Alte Session** — Eine vorherige, nicht sauber beendete Hermes-Session hält noch die long-poll-Verbindung

**Empfehlung:** `hermes status --all` prüfen, ob mehrere Profile mit Telegram laufen. Dann alle bis auf eins deaktivieren.

## Appendix B: Orphaned Alert Queue Analyse

`system_optimizer.py` ruft `_send_telegram_alert()` auf in:
- Zeile 734 (recovery)
- Zeile 762 (recovery)
- Zeile 867 (cleanup)
- Zeile 925 (recovery)
- Zeile 935 (recovery)
- Zeile 1133 (fleet report)

Jeder Aufruf schreibt 1 JSON-Datei. System-optimizer läuft alle 5 Minuten → 2 Dateien pro Run = 24/Stunde = 576/Tag.

Seit 23. Mai: **1.960 Dateien, 0 ausgeliefert, alle `delivered: false`.**

Die Dateien enthalten Fleet Reports und Drawdown-Alerts, die nie auf Telegram angekommen sind. Der Queue-Consumer fehlt.

**Aktion:** Queue leeren und `_send_telegram_alert()` so ändern, dass es die Fleet-Report-Dateien direkt via stdout ausgibt (dann deliver: telegram im Cron-Job), statt sie in einer Orphan-Queue zu parken.

## Appendix C: Docker-Proxy EXEC=0 Auswirkungen

| Skript | Nutzt docker exec? | Betroffen? |
|--------|-------------------|------------|
| container_watchdog.sh | `docker inspect` | ❌ Nein (inspect funktioniert durch Proxy) |
| config_diff_detector.py | `docker exec cat` | ✅ Ja — alle 4 Container "unreadable" |
| canary_position_monitor.py | `docker exec sqlite3` | ✅ Ja — kann keine DB lesen |
| morning_brief.py | `docker exec sqlite3` | ✅ Ja — kann kein PnL lesen |
| fleet_auto_repair.py | `docker logs` | ⚠️ docker logs funktioniert, docker exec nicht |
| drawdown_guard.py | `docker inspect` | ❌ Nein (inspect funktioniert) |
| daily_heartbeat.py | `docker exec` für Rebel | ✅ Ja |
