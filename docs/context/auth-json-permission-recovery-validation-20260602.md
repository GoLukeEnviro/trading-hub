# Auth-JSON Permission Recovery — Validation Report
**Datum:** 2026-06-02T03:46Z
**Typ:** Post-Recovery Validation (READ-ONLY)
**Auditor:** Hermes Meta-Orchestrator (glm-5-turbo via Z.AI)
**Trigger:** Root chown auth.json zu 10000:10000 0600

---

## Executive Verdict

**AUTH_RECOVERED**

auth.json ist lesbar durch hermes-green (uid 10000). Keine neuen Permission Denied seit Fix. Scheduler tickt (.tick.lock 03:45Z). Mem0 funktioniert. Alle 4 Trading-Bots dry_run=True. Kein Bot restarted. Kein dry_run geändert.

**EINSCHRÄNKUNG:** Der laufende Gateway-Prozess startete VOR dem Fix (02:37Z) und hat einen leeren Auth-Store gecacht. Der Fix wirkt vollständig erst nach dem nächsten hermes-green Restart. Die auf Disk korrekte Datei wird von neuen Scheduler-Ticks korrekt gelesen. Telegram-Auth-Tokens sind auf Disk lesbar, aber der Gateway-Prozess hat sie beim Start nicht geladen.

---

## Canonical Auth Path

| Pfad | Kontext | Owner | Mode | Status |
|---|---|---|---|---|
| /opt/hermes-green/config/profiles/orchestrator/auth.json | Host | — | — | Host-Mount-Pfad (nicht von Audit erreichbar) |
| /opt/data/profiles/orchestrator/auth.json | Container-Intern | hermes:hermes (10000:10000) | 0600 | READABLE |
| auth.json.corrupt | Container-Intern | — | — | EXISTIERT NICHT (bereinigt) |

Mount-Mapping: `/opt/hermes-green/config` -> `/opt/data` (bestätigt von Root)

---

## auth.json Readability

**Beweis:**
```
File: /opt/data/profiles/orchestrator/auth.json
  Size: 8664  Access: (0600/-rw-------)  Uid: (10000/hermes) Gid: (10000/hermes)
  Change: 2026-06-02 03:41:25Z
```

- Container-UID: 10000 (hermes) — MATCH
- Mode 0600 — owner-only read/write — CORRECT
- `cat auth.json > /dev/null` — READABLE
- Nicht world-readable (mode 0600) — SECURE

**Historische Fehler:** 190 Permission Denied in Logs — ALLE vor 03:41Z (Fix-Zeitpunkt). Keine neuen Errors nach Fix.

---

## Auth / Telegram / MCP Status

| Check | Status | Notes |
|---|---|---|
| auth.json Permission denied (neu) | CLEAN | 0 Vorkommen in letzten 2 Minuten |
| auth-store-empty warnings | HISTORICAL | Tritt auf beim Startup VOR Fix; nicht wiederholt |
| Telegram send_message | NICHT GETESTET | Read-Only Audit; aber Token auf Disk lesbar |
| Telegram delete_webhook errors | HISTORICAL | Von altem Gateway-Startup; nicht wiederholt |
| MCP filesystem server | WARNING | Initial connection retries (startup-phase) |
| MCP bitget-paper server | WARNING | Initial connection retries (startup-phase) |

**BEWERTUNG:** Auth-Layer ist auf Disk repariert. Gateway hat beim Startup (02:37Z) leeren Store gecacht. Neue Scheduler-Ticks lesen auth.json korrekt. Telegram/MCP werden erst nach Gateway-Neustart vollständig authentifiziert sein.

---

## Mem0 Status

| Check | Status | Notes |
|---|---|---|
| mem0_profile | WORKING | 1160 memories geladen |
| mem0_search | WORKING | 20 results, scores 0.60-0.71 |
| mem0_conclude | WORKING | "Fact stored." bestätigt |
| green-mem0 /health | WORKING |curl von Container geblockt (Security Scanner), aber native Tools funktionieren |
| LLM Extraction | WORKING | ollama.com/v1/gpt-oss:120b |
| Embeddings | WORKING | green-ollama/qwen3-embedding:4b/1024d |
| Qdrant | WORKING | hermes_memories_v2, 1024 dims |

---

## Scheduler Status

| Check | Status | Evidence |
|---|---|---|
| Scheduler ticking | YES | .tick.lock Modify: 2026-06-02 03:45:24Z |
| cron/ dir | OK | hermes:hermes 0700, Change: 03:46:19Z |
| jobs.json | OK | hermes:hermes 0600, Modify: 03:43:24Z |
| Job execution | MIXED | autonomous-health-loop failed (429, LLM Rate Limit — nicht auth-bezogen) |

**HINWEIS:** Der Scheduler hat nach dem Fix erfolgreich auf jobs.json zugegriffen (.tick.lock aktualisiert). Der autonomous-health-loop-Fehler ist ein separates LLM 429-Problem (zai/glm-5.1 Rate Limit), kein Auth-Problem.

---

## Unified Heartbeat Status

| Check | Status | Notes |
|---|---|---|
| Heartbeat Writer | ACTIVE | 15min Interval laut Operational State |
| ai-hedge-fund-crypto | HEALTHY | UP, Port 8410 |
| Signal Pipeline | ACTIVE | hermes_signal.json + primo_signal_state.json |

---

## Trading Safety

| Bot | Container | Status | dry_run | Changed? |
|---|---|---|---|---|
| FreqForge | freqtrade-freqforge | Up 2h | true | NO |
| Regime-Hybrid | freqtrade-regime-hybrid | Up 2h | true | NO |
| FreqForge-Canary | freqtrade-freqforge-canary | Up 2h | true | NO |
| FreqAI-Rebel | freqai-rebel | Up 2h | true | NO |
| Webserver | freqtrade-webserver | Up 4d | N/A (UI only) | NO |

Alle 4 Bots: dry_run=True. Kein Restart. Kein Config-Change.

---

## Remaining Issues (P2, nicht blockierend)

1. **Gateway-Cache:** Laufender Gateway-Prozess hat leeren Auth-Store gecacht. Effektiver Fix nach Restart.
2. **autonomous-health-loop 429:** LLM Rate Limit auf zai — separates Problem.
3. **portfolio-rebalancer PermissionError:** rebalance_state.json Permission — separates P1.
4. **watchdog.log stale:** Seit 2026-05-31 23:30Z nicht aktualisiert.
5. **MCP initial retries:** Startphase-Retries für filesystem und bitget-paper — nicht kritisch.
6. **Legacy hermes_memories Collection:** 768 dims, ungenutzt — dokumentieren, nicht löschen.

---

## Next Step

**AUTH_RECOVERED bestätigt.**

Gemäß Planung sind die nächsten Schritte:
1. **P1: portfolio-rebalancer PermissionError** — `chown 10000:10000 rebalance_state.json`
2. **P2: autonomous-health-loop 429** — Model/Backoff-Anpassung
3. **P2: watchdog.log Staleness** — container-watchdog.sh Analyse
4. **P2: legacy hermes_memories** — Nur dokumentieren

Freigabe erforderlich für alle Schritte.

---

*Validation abgeschlossen. Keine Secrets gedruckt. Keine Runtime-Änderungen.*
