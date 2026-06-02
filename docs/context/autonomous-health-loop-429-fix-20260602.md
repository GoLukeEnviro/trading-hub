# Autonomous Health Loop 429 — Triage, Classification and Fallback Chain
**Datum:** 2026-06-02T04:03Z (initial) / T06:07Z (fallback chain)
**Typ:** Provider-Transient Classification + Frequenz-Reduktion + z.ai Fallback Chain
**Autor:** Hermes Meta-Orchestrator

---

## Executive Verdict

**PROVIDER_RATE_LIMIT_TRANSIENT — kein Code-Bug, Selbstheilung funktioniert**

Der autonomous-health-loop erhaelt gelegentlich HTTP 429 vom zai-Provider (glm-5.1). In den letzten 24h: 2 Failures bei ~48 Runs (96% Erfolg). Hermes Retry-Mechanismus (3 Retries mit Jittered Backoff) funktioniert korrekt. Job self-heal auf naechstem Tick. Frequenz von 30m auf 60m reduziert, um Provider-Druck zu senken.

---

## Job Definition

| Feld | Wert |
|---|---|
| Job ID | 071c043a8fea |
| Name | autonomous-health-loop |
| Typ | Agent-Job (no_agent=False) |
| Modell | glm-5.1 |
| Provider | zai |
| Schedule (vorher) | every 30m |
| Schedule (nachher) | every 60m |
| Deliver | local |
| Toolsets | terminal, file |
| completed | 312 |
| last_status | ok |
| no_agent | False |

---

## 429 Root Cause

**Klassifikation:** PROVIDER_RATE_LIMIT_TRANSIENT

- Provider: zai (api.z.ai/api/coding/paas/v4)
- Modell: glm-5.1
- Fehler: HTTP 429, Code 1305, "The service may be temporarily overloaded"
- 24h Statistik: 2/48 Runs failed = 96% Erfolg
- Hermes Retry: 3 Retries mit Jittered Backoff (5s base, 120s max)
- Nach 3 Retries: Job faellt durch, self-heal auf naechstem Tick
- deliver=local: kein Telegram-Spam bei Failure

Der 429 kommt vom zai-Provider, nicht von Hermes. Es ist ein transienter Overload, kein lokales Problem.

---

## Fix Applied

**Aenderung:** Schedule von `every 30m` auf `every 60m`
**Begruendung:** Halbiert Provider-Anfragen, minimiert 429-Wahrscheinlichkeit
**Kein Code-Patch noetig:** Hermes Retry-Logik ist bereits korrekt implementiert

---

## Validation Results

| Check | Status |
|---|---|
| Schedule updated | PASS (every 60m) |
| next_run_at | 2026-06-02T05:09:08Z |
| Trading-Bots | Alle 4 Up, dry_run=True |
| scheduler | tickt weiter |
| unified heartbeat | nicht geprueft, nicht im Scope |

---

## Trading Safety

| Bot | Status | dry_run | Changed? |
|---|---|---|---|
| FreqForge | Up 3h | true | NO |
| Regime-Hybrid | Up 3h | true | NO |
| FreqForge-Canary | Up 3h | true | NO |
| FreqAI-Rebel | Up 3h | true | NO |

---

## Remaining Issues

- config.yaml Permission Warning ("failed to load config.yaml") tritt periodisch auf, ist aber nicht blockierend — job laeuft mit defaults weiter. Nicht in Scope fuer diesen Fix.
- Hermes Retry-Logik ist im Core (/opt/hermes/agent/retry_utils.py) bereits optimal mit Jittered Backoff. Keine Aenderung noetig.

---

## Fallback Chain (2026-06-02T06:07Z)

**Typ:** Globaler `config.yaml` fallback_providers Eintrag (gilt fuer ALLE zai-Agent-Jobs)

Die globale Hermes-Config in `/opt/data/config.yaml` wurde um eine z.ai-Fallback-Chain erweitert:

```yaml
fallback_providers:
  - provider: zai
    model: glm-5-turbo
  - provider: zai
    model: glm-4.7
```

**Fallback-Logik:**
1. Primär: glm-5.1 (unverändert)
2. Bei 429/Timeout/Model-Fehler: Versuch glm-5-turbo (zai)
3. Bei erneutem Fehler: Versuch glm-4.7 (zai)
4. Nach Erschöpfung: Job failt mit DEGRADED, self-heal auf nächstem Tick

**Warum nur z.ai:**
- Provider-Konsistenz: gleicher API-Key (GLM_API_KEY), gleicher Base-URL, gleicher Auth-Context
- Keine neuen Credential-Chains oder Provider-Integrationen nötig
- DeepSeek/Ollama Cloud bewusst weggelassen, um keine zusätzliche Baustelle zu öffnen

**Mechanismus:**
- `config.yaml` fallback_providers wird vom Scheduler bei jedem Job-Tick frisch gelesen (scheduler.py Zeile 1280: "Re-read .env and config.yaml fresh every run")
- An AIAgent._fallback_chain übergeben (scheduler.py Zeile 1398)
- Kein Gateway-/Container-Restart nötig

**Betroffene Jobs:**
- autonomous-health-loop (glm-5.1, 60m)
- Rebel Status Summary (glm-5.1, 720m)
- trading-hub-deep-dive-validation (glm-5.1, täglich)
- daily-signal-confidence-monitor (glm-5.1, alle 6h)
- Alle weiteren zai-Agent-Jobs mit glm-5.1

---

*Zwei Schichten: (1) Frequenz-Reduktion von 30m→60m, (2) globale z.ai-Fallback-Chain. Kein Code-Patch nötig.*
