# Current Operational State

**Stand: 2026-05-14**
**Zuletzt verifiziert: 2026-05-14 07:20**

---

## Signal Core

| Property | Value |
|----------|-------|
| Active Signal Core | `ai-hedge-fund-crypto` |
| Signal Bridge | `primo_signal.py` |
| Signal Output | `ai-hedge-fund-crypto/output/hermes_signal.json` |
| Signal Status | **STALE** — ~49 Stunden alt (letzte Prüfung: 2026-05-14) |

---

## Execution Fleet

### Active Bots

| Bot | Container | Port | Strategy | Mode | Status |
|-----|-----------|------|----------|------|--------|
| FreqForge | `freqtrade-freqforge` | 8086 | FreqForge_Override | dry-run | Active |
| Regime-Hybrid | `freqtrade-regime-hybrid` | 8085 | RegimeSwitchingHybrid_v7_v04_Integration | futures | Active |
| Momentum | `freqtrade-momentum` | 8084 | MomentumBG15_v1 | futures | Active |
| RSI | `freqtrade-rsi` | 8081 | SimpleRSIOnly_v1 | futures | **QUARANTINE** |
| Webserver | `freqtrade-webserver` | — | — | UI only | Active |

### NOT_DEPLOYED Bots

| Bot | Container | Strategy File | Status |
|-----|-----------|---------------|--------|
| MVS | kein Container | `MinimalViableStrategy_v1.py` | NOT_DEPLOYED — strategy preserved |
| FOMO Phase 3 | kein Container | `freqtrade/bots/fomo-phase3/` | NOT_DEPLOYED — research code preserved |

---

## Persistent Memory

| Property | Value |
|----------|-------|
| System | Honcho (PostgreSQL) |
| Document Count | 3,509 (verifiziert 2026-05-14) |
| Container | `honcho-api-1` (Up 45h) |
| writeFrequency | session (unverifiziert) |
| API Health | **UNRESOLVED** — HTTP-Endpoint nicht erreichbar |

---

## Open Operational Issues

| Issue | Severity | Status |
|-------|----------|--------|
| Signal Staleness | P0 | ~49h alte Signal-Dateien — Pipeline-Investigation offen |
| Honcho API Health | P1 | HTTP-Endpoint reagiert nicht — Ursache unklar |

---

## Active Cron Jobs

*Nicht Teil dieses Dokuments — bitte separat prüfen.*

---

## Key Files

| Datei | Rolle |
|-------|-------|
| `~/.hermes/profiles/orchestrator/SOUL.md` | Live-Orchestrator-Identität |
| `/home/hermes/projects/trading/AGENTS.md` | Primärer Projektkontext |
| `/home/hermes/projects/trading/ORCHESTRATOR_CHARTER.md` | Betriebsverfassung |
| `/home/hermes/projects/trading/docs/runbooks/` | Wiederholbare Audit-Procedures |

---

*Nächste Aktualisierung bei wesentlichen Änderungen — nicht bei jedem Sync.*