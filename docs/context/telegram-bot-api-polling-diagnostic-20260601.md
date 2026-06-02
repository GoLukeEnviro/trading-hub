# Telegram Bot API Polling Diagnostic -- 2026-06-01 12:35 UTC

**Modus:** READ-ONLY. Keine Webhooks geloescht, keine Nachrichten gesendet, keine Container neugestartet.

---

## Executive Verdict

**ROOT CAUSE: Hermes-Agent dispatcht keine jobs.json-Jobs.** Nicht ein Telegram-Problem allein.

Die `deliver=local` Jobs (signal-heartbeat, trading-pipeline, cron-guardian, smart-heartbeat) laufen ueber den **externen systemd Guardian** (`trading-cron-guardian.timer`), nicht ueber den Hermes-Agent. Die `deliver=telegram` Jobs haben keinen externen Trigger und werden vom Hermes-Agent-Cron-System nicht dispatcht.

**Klassifikation: HERMES_CRON_DISPATCHER_NOT_PICKING_UP_JOBS_JSON**

---

## Safe Token Presence / getMe Result

| Check | Ergebnis |
|---|---|
| TELEGRAM_BOT_TOKEN vorhanden | True |
| getMe HTTP_STATUS | 200 |
| getMe ok | True |
| bot_id_present | True |
| username_present | True |

**Token ist gueltig. Bot existiert.**

---

## Webhook State

| Check | Ergebnis |
|---|---|
| getWebhookInfo HTTP_STATUS | 200 |
| webhook_url_set | **False** |
| webhook_url_empty | **True** |
| pending_update_count | 2 |
| last_error_date_present | False |
| last_error_message_present | False |
| has_custom_certificate | False |

**Kein Webhook gesetzt. Kein Webhook-Polling-Konflikt.**

---

## Short Polling vs Long Polling

| Test | HTTP | Dauer | ok | result_count |
|---|---|---|---|---|
| getUpdates timeout=0 | 200 | 0.1s | True | 1 |
| getUpdates timeout=3 | 200 | 0.1s | True | 1 |

**Beide funktionieren.** Telegram API ist voll funktional.

---

## Hermes Telegram Adapter Logs

### Nach Restart (seit 11:15 UTC)

- **0 Telegram-Fehler** im Post-Restart-Log
- **0 TimedOut-Fehler** nach Restart
- **gateway_state.json zeigt:** `telegram: state: connected` (seit 11:15:13 UTC)

### Vor Restart (alte Fehler)

```
ERROR telegram.ext: Network Retry Loop (Bootstrap delete Webhook): Timed out: Timed out. Failed run number 0 of 0. Aborting.
WARNING gateway.platforms.telegram: [Telegram] polling reconnect failed: Timed out
```

Die `bootstrap_del_webhook` hat beim alten Lauf getimed out (httpx.ReadTimeout, read_timeout=20s). Nach dem Restart ist das Problem behoben.

---

## Gateway State

```
platforms:
  telegram: state=connected, error_code=None (seit 11:15 UTC)
  api_server: state=connected, error_code=None
gateway_state: running
active_agents: 0
```

Telegram-Adapter ist **connected** und fehlerfrei.

---

## Cron Session Evidence

### Jobs.json-Jobs vs Session-Aktivitaet

| Job | deliver | has_sessions | erklaerung |
|---|---|---|---|
| signal-heartbeat | local | **False** | laeuft via systemd Guardian |
| trading-pipeline | local | **False** | laeuft via systemd Guardian |
| drawdown-guard | telegram | **False** | WIRD NICHT DISPATCHT |
| container-watchdog | telegram | **False** | WIRD NICHT DISPATCHT |
| mcp-watchdog | telegram | **False** | WIRD NICHT DISPATCHT |
| daily-backup | local | **False** | laeuft via systemd Guardian |
| portfolio-rebalancer | origin | **False** | nicht dispatcht |
| cron-guardian | local | **False** | laeuft via systemd Guardian |
| smart-heartbeat | local | **False** | laeuft via systemd Guardian |
| Fleet Report (alle 4h) | telegram | **True** | laeuft (no_agent=False, LLM-basiert) |

### Hermes-interne Jobs (16 IDs, nicht in jobs.json)

Diese laufen und erstellen Sessions alle paar Minuten. Z.B. `071c043a8fea` (autonomous-health-loop).

### Erkenntnis

- **16 interne Hermes-Jobs** werden dispatcht (Sessions aktiv)
- **1 jobs.json-Job** wird dispatcht (Fleet Report, `no_agent=False`)
- **9 jobs.json-Jobs** werden NICHT dispatcht (alle `no_agent=True`)

Die `deliver=local` Jobs `no_agent=True` laufen nur, weil der **systemd Guardian** sie triggert (signal-heartbeat via ai-hedge-fund-crypto /trigger, trading-pipeline via docker exec hermes-green). Der Hermes-Agent selbst dispatcht sie nicht.

---

## Root Cause Classification

**HERMES_CRON_DISPATCHER_NOT_PICKING_UP_NO_AGENT_JOBS**

Der Hermes-Cron-Scheduler dispatcht `no_agent=True` Script-Jobs aus `jobs.json` nicht. Nur:
1. Interne Hermes-Jobs (nicht in jobs.json definiert) → werden dispatcht
2. `no_agent=False` LLM-Jobs (Fleet Report) → werden dispatcht
3. `no_agent=True` Script-Jobs aus jobs.json → **werden NICHT dispatcht**

Die Telegram-Verbindung ist **sekundaer**. Selbst wenn Telegram perfekt funktionieren wuerde, wuerden die `no_agent=True` Jobs nicht dispatcht, weil der Scheduler sie nicht aufgreift.

Die Script-Fixes (P0/P1) sind korrekt. Aber sie koennen erst wirken wenn der Hermes-Cron-Scheduler die `no_agent=True` Jobs wieder dispatcht.

---

## Recommended Fix Plan

### Option A: Hermes-Agent-Log-Level erhoehen fuer Cron-Dispatch

```bash
# Setze DEBUG-Logging fuer cron.scheduler um zu sehen WARUM jobs.json no_agent=True jobs nicht dispatcht werden
# (Konfigurationsaenderung im Hermes-Agent)
```

### Option B: Pruefen ob jobs.json Format/Kompatibilitaet

Die `no_agent=True` Jobs haben `script: drawdown_guard.py` aber keinen `prompt` oder `command`. Der Hermes-Scheduler erwartet moeglicherweise ein anderes Feld fuer Script-Jobs. Pruefen:
- Hat sich das jobs.json-Schema geaendert?
- Gab es ein Hermes-Agent-Update das die Script-Job-Ausfuehrung geaendert hat?
- Wird ein `command` oder `prompt` Feld statt `script` erwartet?

### Option C: Externen Trigger fuer Telegram-Jobs aufbauen

Da der systemd Guardian die `deliver=local` Jobs bereits triggert, koennte er auch die `deliver=telegram` Jobs triggern. Die Telegram-Delivery wuerde dann ueber den Guardian laufen statt ueber den Hermes-Agent.

---

## Do-Not-Do List

- Kein Webhook setzen/loeschen
- Keine Telegram-Nachricht senden
- Keinen Container restarten
- Keine jobs.json editieren
- Keine State-Dateien loeschen
- Keine Locks entfernen
- Keine Trading-Bots neustarten
- Keinen Blue-Stack anfassen
