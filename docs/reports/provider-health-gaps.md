# Provider-Health Gaps Audit Report

> Session: hermes-skill-debug-2026-07-13 | Step 5/6 | Scope L2
> Date: 2026-07-13

## Issue: Keine Health-Checks, Quota-Überwachung oder Circuit-Breaker für LLM-Provider

Der Hermes-Agent ist von mehreren LLM-Providern abhängig (Ollama Cloud,
OpenRouter, z.ai), aber es existiert keine systematische Überwachung
von Verfügbarkeit, Quota oder Kosten.

## Evidence

### 1. Provider-Landschaft

| Provider | Nutzung | Status |
|----------|---------|--------|
| **Ollama Cloud** | Primär: Hermes-Cron-Jobs (roadmap-tick, health-check), Memory-Extraction, Dream-Mode | ⚠️ Single Point of Failure |
| **OpenRouter** | Backtesting-Benchmarks, historisch für Dream-Mode | 🟢 Nur Benchmarks (nicht produktiv) |
| **z.ai** | Fallback-Chain (2 Einträge) | 🟡 Teil der Fallback-Kette |

Quellen: `docs/context/dream-mode-v3.1-validation-20260518.md`,
`docs/context/hermes-memory-system-full-audit-20260518.md`,
`docs/context/autonomous-health-loop-fallback-chain-20260602.md`

### 2. OpenRouter — Credit-Monitoring

- OpenRouter wird nur in `backtests/benchmarks/multi_model_benchmark.py`
  verwendet (4 Modelle: deepseek-v3, gpt-4o-mini, claude-3-haiku, mistral-nemo)
- `docs/context/dream-mode-v3.1-validation-20260518.md` bestätigt:
  "OpenRouter completely unused" im Produktivsystem
- **Kein Credit-Monitoring vorhanden** — wenn OpenRouter-Credits aufgebraucht
  sind, schlagen Benchmark-Runs ohne Vorwarnung fehl

### 3. Ollama Cloud — Quota-Überwachung

- Primärer Provider für Hermes-Cron und Memory-Extraction
- Dokumentierte Single-Point-of-Failure (Gap-Reports 2026-05-16, 2026-06-05)
- `docs/context/2026-06-05-comprehensive-gap-analysis-report.md` (Z. 141):
  "Faellt das LLM-API aus (429, 503, Timeout), gibt es keine alternative
  Signalquelle."
- **Kein Quota-Alert** — keine Überwachung auf API-Limits, 429-Rate-Limits
  oder monatliche Token-Kontingente

### 4. Fallback-Chain — Health-Check

- `docs/context/autonomous-health-loop-fallback-chain-20260602.md`:
  `fallback_providers: []` → zai-only Fallback Chain (2 Eintraege)
- DeepSeek/Ollama Cloud bewusst NICHT in der Fallback-Kette
- **Kein Health-Check** für die Fallback-Kette — wenn der primäre Provider
  ausfällt UND der Fallback nicht erreichbar ist, gibt es keine Warnung
- **Kein Circuit-Breaker** — dokumentiert als gewünscht (P2 in Gap-Report)
  aber nicht implementiert

### 5. Gap-Report-Empfehlungen (nicht umgesetzt)

`docs/GAP-REPORT-2026-06-05-DEEP-DIVE-AUTONOMES-TRADING.md`:
- E3.4: "Circuit zu Cloud-Fallback" — nicht implementiert
- I5.5: "local ollama primary + Circuit zu Cloud-Fallback" — nicht implementiert
- O6.3: "Top-Level Circuit Breaker in Pipeline/Autopilot" — nicht implementiert

`docs/context/2026-06-05-comprehensive-gap-analysis-report.md`:
- P2: "Circuit-Breaker + Backoff-Staffelung" — 6h Aufwand, nicht umgesetzt

## Investigation

Geprueft:
- [x] OpenRouter-Referenzen in trading-hub → nur Backtesting (nicht produktiv)
- [x] Ollama-Cloud-Nutzung → Cron-Jobs, Memory-Extraction, Dream-Mode
- [x] Fallback-Chain-Konfiguration → zai-only, 2 Eintraege
- [x] Health-Check/Quota-Code → nicht vorhanden
- [x] Circuit-Breaker-Code → nicht vorhanden (nur Gap-Report-Empfehlungen)
- [x] ai4trade-bot auf Provider-Referenzen → keine

Ausgeschlossen:
- [x] Produktiver OpenRouter-Einsatz → nein, nur Benchmarks
- [x] Existierende Quota-Alerts → keine
- [x] Circuit-Breaker-Implementierung → keine

## Root Cause

1. **Fokus auf Funktionalität, nicht auf Betrieb:** Die Provider wurden nach
   funktionalen Kriterien ausgewählt und konfiguriert (Ollama Cloud für
   Hermes, OpenRouter für Benchmarks), aber ohne operative Überwachung.

2. **Keine O11y-Infrastruktur:** Es gibt kein Monitoring-Framework für
   externe API-Abhängigkeiten. Health-Checks sind auf Docker-Container-
   und Exchange-Ping beschränkt, nicht auf LLM-Provider.

3. **Fallback-Chain unvollständig:** Die dokumentierte Fallback-Chain ist
   zai-only und schließt Ollama Cloud explizit aus. Wenn der primäre
   Provider (Ollama Cloud) ausfällt und z.ai nicht erreichbar ist, hat
   Hermes keinen LLM-Zugriff.

## Solution

### 3 GitHub Issues (NUR nach expliziter Freigabe anlegen)

#### Issue 1: "OPS: OpenRouter credit monitoring missing"

**Typ:** Enhancement | **Priority:** Low (nur Benchmarks betroffen)

OpenRouter wird für Backtesting-Benchmarks verwendet. Es gibt kein
Monitoring der OpenRouter-Credits. Wenn das Guthaben aufgebraucht ist,
schlagen Benchmark-Runs ohne Vorwarnung fehl.

Empfehlung:
- OpenRouter-API-Call `/api/v1/credits` in Cron-Job einbauen
- Alert-Schwelle: <$5 oder <100K Tokens
- Alternativ: OpenRouter aus Benchmarks entfernen und auf
  Ollama Cloud / z.ai migrieren

#### Issue 2: "OPS: Ollama-Cloud weekly quota alert missing"

**Typ:** Enhancement | **Priority:** HIGH (primärer Hermes-Provider)

Ollama Cloud ist der primäre LLM-Provider für Hermes. Es gibt kein
Monitoring von:
- Rate-Limits (429-Fehler)
- Monatlichem Token-Kontingent
- API-Verfügbarkeit (Latenz, Error-Rate)

Empfehlung:
- Wöchentlicher Quota-Check via Ollama-Cloud-API
- 429-Counter mit Alert-Schwelle >10/Stunde
- Telegram-Alert bei kritischen Schwellen
- Optional: `hermes provider status` Befehl

#### Issue 3: "OPS: Provider fallback chain needs health check"

**Typ:** Enhancement | **Priority:** HIGH (kein Fallback-Schutz)

Die Fallback-Chain (zai-only, 2 Eintraege) hat keinen Health-Check.
Wenn der primäre Provider ausfällt und der Fallback nicht verfügbar ist,
bleibt Hermes ohne LLM-Zugriff.

Empfehlung:
- Health-Check für jeden Provider in der Chain
- Circuit-Breaker: nach N Fehlern → Provider deaktivieren + Alert
- `hermes provider health` Kommando
- Optional: Ollama Cloud in die Fallback-Chain aufnehmen

## Verification

- [x] Provider-Landschaft vollständig erfasst (Ollama Cloud, OpenRouter, z.ai)
- [x] Quota/Credit-Monitoring als nicht-existent bestätigt
- [x] Fallback-Chain analysiert (zai-only, 2 Einträge)
- [x] Circuit-Breaker als Gap-Report-Empfehlung (nicht implementiert)
- [ ] 3 GitHub Issues — HALTEN AUF EXPLIZITE FREIGABE
