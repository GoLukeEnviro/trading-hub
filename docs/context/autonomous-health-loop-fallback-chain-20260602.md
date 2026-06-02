# Autonomous Health Loop — z.ai Fallback Chain
**Datum:** 2026-06-02T04:10Z
**Typ:** Config-Resilience (z.ai-only Fallback Chain)
**Autor:** Hermes Meta-Orchestrator

---

## Executive Verdict

**AUTONOMOUS_HEALTH_LOOP_FALLBACK_READY**

z.ai-only Fallback Chain konfiguriert: glm-5.1 → glm-5-turbo → glm-4.7. Global in config.yaml, profitiert alle zai-Cron-Jobs. Kein Code-Patch, keine neuen Provider, keine Fremdanbieter. Minimaler Eingriff: 4 Zeilen YAML.

---

## Current Job State

| Feld | Wert |
|---|---|
| Job ID | 071c043a8fea |
| Name | autonomous-health-loop |
| Primary Model | glm-5.1 |
| Schedule | every 60m (vorher 30m) |
| Provider | zai |

---

## Model Availability

| Model | In zai Config | Kontextlaenge |
|---|---|---|
| glm-5.1 | Ja (primary) | 256K |
| glm-5-turbo | Ja | 256K |
| glm-4.7 | Ja | 256K |

Alle drei Modelle sind im zai-Provider-Abschnitt von config.yaml registriert. Keine neuen Provider noetig.

---

## Fallback Chain

```yaml
# config.yaml — globale Einstellung fuer alle zai-Cron-Jobs
fallback_providers:
  - provider: zai
    model: glm-5-turbo    # Priority 2: gleicher Provider, schnellere/schaerfe Model-Variante
  - provider: zai
    model: glm-4.7        # Priority 3: stabiler, weniger Token-Verbrauch
```

**Ablauf bei 429:**
1. glm-5.1 → 429/overload
2. Hermes AIAgent fallback chain: glm-5-turbo
3. Wenn auch 429: glm-4.7
4. Wenn alle exhausted: Job failure (self-heal auf naechstem Tick)

**Hermes-interner Mechanismus:**
- AIAgent._fallback_chain (run_agent.py Zeile 1838-1850)
- Scheduler reicht fallback_providers aus config.yaml durch (scheduler.py Zeile 1398)
- Jittered Backoff bereits implementiert (retry_utils.py)
- Kein unendlicher Retry, max 3 attempts pro Modell

---

## Affected Jobs (global)

| Job | Model | Profitiert von Fallback |
|---|---|---|
| autonomous-health-loop | glm-5.1 | Ja |
| daily-signal-confidence-monitor | glm-5.1 | Ja |
| trading-hub-deep-dive-validation | glm-5.1 | Ja |
| Rebel Status Summary | glm-5.1 | Ja |

---

## Fix Applied

**Datei:** /opt/data/profiles/orchestrator/config.yaml
**Aenderung:** `fallback_providers: []` → zai-only Fallback Chain (2 Eintraege)
**Kein Code-Patch.** Kein neuer Provider. Kein DeepSeek/Ollama.

---

## Validation Results

| Check | Status |
|---|---|
| YAML Syntax | PASS |
| Fallback Chain Format | PASS (list of dicts, provider+model) |
| Trading-Bots | Alle 4 Up, dry_run=True |
| Scheduler | tickt (nicht restartet) |

---

## Trading Safety

| Bot | Status | dry_run | Changed? |
|---|---|---|---|
| FreqForge | Up 3h | true | NO |
| Regime-Hybrid | Up 3h | true | NO |
| FreqForge-Canary | Up 3h | true | NO |
| FreqAI-Rebel | Up 3h | true | NO |

---

## Warum keine DeepSeek/Ollama Cloud?

- User-Entscheidung: provider-konsistent bleiben
- Keine neue Baustelle eroeffnen
- zai hat 4 Modelle (glm-4.7, glm-5, glm-5-turbo, glm-5.1) — ausreichende Fallback-Tiefe
- DeepSeek/Ollama Cloud wuerden neue Auth/Config/Endpoint-Ketten erfordern

---

*Nicht DeepSeek/Ollama. Nur z.ai. Global, minimal, durable.*
