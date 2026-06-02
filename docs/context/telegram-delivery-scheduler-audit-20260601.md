# Telegram-Delivery Scheduler Audit -- 2026-06-01 11:00 UTC

**Modus:** READ-ONLY. Keine Container neugestartet, keine Jobs getriggert, keine Telegram-Nachrichten gesendet, keine State-Dateien modifiziert.

---

## Executive Verdict

**Root Cause: Hermes-Agent Telegram-Polling broken + LLM-Rate-Limit-Kaskade.**

Die `deliver=telegram` Cron-Jobs werden vom Scheduler nicht mehr dispatcht, weil:
1. Das Telegram-Polling im Hermes-Agent mit `TimedOut` fehlschlaegt
2. Der LLM-Provider (z.ai/glm-5.1) mit HTTP 429 rate-limited ist
3. Der Agent in einem Fehler-Retry-Loop steckt und die Cron-Queue nicht abarbeitet

**Klassifikation: HERMES_AGENT_DELIVERY_LOOP_BLOCKED**

---

## Telegram Delivery Jobs Status

| Job | Deliver | Letzter Lauf (State) | Status |
|---|---|---|---|
| drawdown-guard | telegram | 01:59 UTC (drawdown_state.json) | BLOCKED (kein Dispatch seit ~04:00 UTC) |
| container-watchdog | telegram | 04:05 UTC (state file) | BLOCKED (kein Dispatch seit ~04:00 UTC) |
| mcp-watchdog | telegram | 04:43 UTC (state file) | BLOCKED |
| Fleet Report (alle 4h) | telegram | unbekannt | BLOCKED |

---

## Local Delivery Jobs Status

| Job | Deliver | Status |
|---|---|---|
| signal-heartbeat | local | OK (signal_bridge.log: 3 min alt) |
| trading-pipeline | local | OK (signal_bridge.log: 3 min alt) |
| smart-heartbeat | local | OK (standby/hermes_health.json: 0 min alt) |
| daily-backup | local | OK (backup 04:05 UTC vorhanden) |
| cron-guardian | local | OK (guardian.log: 3 min alt) |

---

## jobs.json / Scheduler State Findings

### jobs.json ist ein Konfigurations-Template, kein Live-State

Alle 10 Jobs haben:
- `last_run_at: None`
- `next_run_at: 2026-05-19T20:XX:00` (Erstellungszeitpunkt, nie aktualisiert)
- `last_error: None`, `last_status: None`, `last_delivery_error: None`
- `state: scheduled`

**Interpretation:** Der Hermes-Agent fuehrt `jobs.json` als Job-Definitionen, aber verwaltet den Ausfuehrungsstate intern (nicht in dieser Datei). Die `next_run_at` Werte sind initial und werden vom Agent intern nachgefuehrt, nicht zurueck in die Datei geschrieben.

### 37 interne Cron-Jobs

Der Hermes-Agent hat 37 Cron-Jobs total (mehr als die 10 in jobs.json). Zusaetzliche interne Jobs wie `autonomous-health-loop` werden vom Agent selbst verwaltet.

### portfolio-rebalancer Status: error

`portfolio-rebalancer | enabled=True | status=error | errors=yes` (aus Agent-Log)

---

## Hermes Dispatcher Log Findings

### Telegram-Polling Fehler

```
telegram.error.TimedOut: Timed out
WARNING gateway.platforms.telegram: [Telegram] Telegram polling reconnect failed: Timed out
WARNING gateway.platforms.telegram: [Telegram] Telegram network error (attempt 2/10), reconnecting in 10s. Error: Timed out
```

**Aber:** Telegram API ist vom Container aus erreichbar (`urllib.urlopen('https://api.telegram.org/')` gibt HTTP 200). Das Polling (long-polling `getUpdates`) timed out, aber einfache HTTP-Requests funktionieren.

### LLM-Rate-Limit-Kaskade

```
WARNING run_agent: API call failed (attempt 1/3) error_type=RateLimitError provider=zai model=glm-5.1
HTTP 429: The service may be temporarily overloaded, please try again later
```

Der Agent retryt 3x und gibt dann auf. Dies blockiert den Agent-Loop.

### Tool-Fehler-Loop

```
WARNING run_agent: Tool terminal returned error (0.27s): Security scan — [HIGH] Pipe to interpreter
WARNING run_agent: Tool terminal returned error (0.30s): exit_code=7, Failed to connect to host
WARNING run_agent: Tool terminal returned error: Permission denied
```

Der Agent versucht Befehle auszufuehren, die vom Security-Scanner blockiert werden (pipe to interpreter), Permission-Fehler haben (UID 10000 schreibt als hermes-Files), oder Netzwerkfehler haben. Er ist in einem Fehler-Loop gefangen.

### Cron-Scheduler Fehler

```
ERROR cron.scheduler: Job 'autonomous-health-loop' failed: RuntimeError: HTTP 429
```

Der interne Scheduler wirft Fehler wegen 429-Rate-Limits.

---

## Queue / Lock Findings

- **standby.lock:** 5 Bytes, aktualisiert 12:42 UTC (aktiv, nicht stale)
- **.mcp_daemon.pid:** 8 Bytes, aktualisiert 04:43 UTC
- **Keine stale Locks gefunden**, die den Telegram-Delivery blockieren wuerden

Die Blockade ist nicht durch einen Lock verursacht, sondern durch die Fehler-Kaskade im Agent-Loop.

---

## Likely Root Cause

### Kausalkette

```
1. LLM-Provider (z.ai/glm-5.1) gibt HTTP 429 (Rate Limit)
   ↓
2. Hermes-Agent retryt 3x → gibt auf → Agent-Loop fehlerhaft
   ↓
3. Telegram-Polling schlaegt fehl (TimedOut, Bad Gateway)
   Möglicherweise verursacht durch Netzwerk-Ueberlastung durch Retry-Loop
   ↓
4. Cron-Scheduler kann deliver=telegram Jobs nicht abschliessen
   (Script-Ausfuehrung koennte klappen, aber Delivery scheitert)
   ↓
5. Scheduler backt off oder priorisiert deliver=telegram Jobs niedriger
   ↓
6. drawdown-guard, container-watchdog, mcp-watchdog werden nicht mehr dispatcht
```

### Warum deliver=local weiterlaeuft

`deliver=local` Jobs muessen nicht durch den Telegram-Polling-Loop. Der Scheduler kann sie direkt ausfuehren und das Ergebnis lokal ablegen. Der Fehler betrifft nur die Delivery-Pipeline, nicht die Script-Ausfuehrung selbst.

### Zeitliche Eingrenzung

- Letzter erfolgreicher drawdown-guard Lauf: 01:59 UTC
- Letzter erfolgreicher container-watchdog Lauf: 04:05 UTC
- Telegram-Fehler beginnen: im selben Zeitraum
- **Ab ~04:00 UTC sind alle Telegram-Jobs blockiert**

---

## Safe Fix Recommendation

### Option A: Hermes-Agent kontrolliert neustarten (minimaler Eingriff)

```bash
docker restart hermes-green
```

**Risiko:** Gering. Agent startet neu, baut Telegram-Verbindung neu auf, Scheduler beginnt frisch.
**Vorteil:** Behebt TimedOut, 429-Backoff, und Tool-Fehler-Loop in einem Schritt.
**Nachteil:** Kurze Downtime (30-60s). Cron-Jobs die waehrend des Restarts faellig sind, werden beim Neustart nachgeholt.

### Option B: Warten auf Self-Recovery

Die Telegram-Fehler zeigen "attempt X/10, reconnecting in Xs". Der Agent koennte sich selbst erholen wenn die 429-Rate-Limits zurueckgehen.

**Risiko:** Mittel. Wenn der Agent im Fehler-Loop bleibt, erholen sich die Telegram-Jobs nie.
**Vorteil:** Kein Eingriff.

### Option C: LLM-Provider-Swap + Restart

Wenn z.ai/glm-5.1 dauerhaft rate-limited ist, koennte ein Provider-Wechsel helfen (z.B. auf ollama-cloud oder einen anderen Provider). Danach Restart.

**Empfehlung:** **Option A** (kontrollierter Restart). Am einfachsten, geringstes Risiko, behebt die Kaskade sofort.

---

## Do-Not-Do List

- Nicht `jobs.json` bearbeiten (es ist nur ein Template)
- Nicht Telegram-Jobs loeschen oder neu erstellen
- Nicht State-Dateien loeschen
- Nicht Locks entfernen
- Nicht Trading-Bots neustarten
- Nicht Blue-Stack anfassen
- Nicht manuell Telegram-Nachrichten senden
- Nicht dry_run=false setzen
