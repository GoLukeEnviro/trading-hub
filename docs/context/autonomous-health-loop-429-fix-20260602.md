# Autonomous Health Loop 429 — Triage and Classification
**Datum:** 2026-06-02T04:03Z
**Typ:** Provider-Transient Classification + Frequenz-Reduktion
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

*Nicht code-gepatcht — transienter Provider-Overload akzeptiert und Frequenz reduziert.*
