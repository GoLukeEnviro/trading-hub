# Trading System Audit — 2026-06-07

**Project:** trading-hub  
**Date:** 2026-06-07  
**Status:** Snapshot — current known state

---

## Purpose

This document captures the known system state as of 2026-06-07. It serves as the baseline truth document for the Profitability Forensics Agent (Phase 1: Anchor Current State) and as a reference for the Shadowlock Writer when correlating historical entries.

If trade data contradicts values in this document, trade data is authoritative. This document is a design/observation snapshot, not a ledger.

---

## Active Bot Registry

| Bot | Mode | Strategy Dir | Config Dir | Notes |
|---|---|---|---|---|
| FreqForge | dry/live | `freqforge/user_data/strategies/` | `freqforge/user_data/` | Core production bot |
| FreqForge-Canary | dry/shadow | `freqforge-canary/user_data/strategies/` | `freqforge-canary/user_data/` | Safety canary; mirrors FreqForge with conservative config |
| Regime-Hybrid | dry/shadow | `freqtrade/bots/regime-hybrid/...` | `freqtrade/bots/regime-hybrid/...` | Experimental; regime-aware logic |
| FreqAI-Rebel | shadow | `freqtrade/bots/freqai-rebel/...` | `freqtrade/bots/freqai-rebel/...` | Research-only; FreqAI integration |

---

## Infrastructure Components

| Component | File/Path | Purpose |
|---|---|---|
| Main compose stack | `docker-compose.yml` | All freqtrade bots + bridge + dashboard |
| AI hedge-fund stack | `docker-compose.ai-hedge-fund-crypto.yml` | AI signal container |
| Signal bridge | `bridge/` | Routes AI scores to freqtrade bots |
| Orchestrator | `orchestrator/` | Self-improvement episode runner |
| Dashboard | `dashboard.py` | Monitoring and visualization |
| Fleet risk manager | (shared component) | Cross-fleet drawdown and trade limits |
| Caddy reverse proxy | `Caddyfile` | HTTPS routing for dashboard and APIs |

---

## Known Performance State (as of audit date)

> These values are best-known estimates from docs/GAP-REPORT-2026-06-05-DEEP-DIVE-AUTONOMES-TRADING.md and related gap reports. They are NOT authoritative trade-log readings. The Forensics Agent must verify against actual trade history.

| Bot | Last Known PF | Last Known WR | Mode | Assessment |
|---|---|---|---|---|
| FreqForge | unknown — requires trade log read | unknown | dry/live | Core bot; primary forensics target |
| FreqForge-Canary | unknown — requires trade log read | unknown | dry/shadow | Safety mirror; should track FreqForge closely |
| Regime-Hybrid | unknown — requires trade log read | unknown | dry/shadow | Experimental; regime logic unverified |
| FreqAI-Rebel | unknown — requires trade log read | unknown | shadow | Research; no live capital at risk |

---

## Gap Reports on Record

| Report | Path | Date | Scope |
|---|---|---|---|
| GAP-REPORT-2026-05-16 | `docs/GAP-REPORT-2026-05-16.md` | 2026-05-16 | System gap analysis |
| GAP-REPORT-2026-06-05-DEEP-DIVE | `docs/GAP-REPORT-2026-06-05-DEEP-DIVE-AUTONOMES-TRADING.md` | 2026-06-05 | Deep dive autonomous trading |
| GAP_ANALYSE | `docs/GAP_ANALYSE.md` | unknown | General gap analysis |
| gap-report-20260516 | `docs/gap-report-20260516.md` | 2026-05-16 | Gap report (lowercase version) |
| gap-report-20260517 | `docs/gap-report-20260517.md` | 2026-05-17 | Follow-up gap report |

---

## Agent Stack (as of 2026-06-07)

| Agent | Spec | Role |
|---|---|---|
| Shadowlock Writer | `docs/specs/shadowlock-writer-spec.md` | Append-only chronicle and audit log |
| Profitability Forensics Agent | `docs/specs/profitability-forensics-agent-spec.md` | Historical reconstruction and recovery proposals |
| Self-Improvement Orchestrator | `ORCHESTRATOR_CHARTER.md` (charter); spec TBD | Episode execution and backtest automation |
| Context Engineering Agent | Implicit in CLAUDE.md / AGENTS.md | Spec hygiene and git discipline |

---

## Known Open Gaps (as of 2026-06-07)

1. `docs/specs/` directory did not exist prior to this audit — specs are being created in this commit.
2. `var/trading-shadowlock/` directory structure did not exist — created in this commit.
3. Self-Improvement Orchestrator formal spec (separate from charter) not yet written.
4. Trade history export / SQLite query tooling not yet standardized.
5. Shadowlock Writer not yet deployed as a running service — currently spec-only.
6. Profitability Forensics Agent not yet deployed — currently spec-only.

---

## Related Documents

- `AGENTS.md` — Agent roles and operational guidelines
- `CLAUDE.md` — Claude-specific instructions for this repo
- `ORCHESTRATOR_CHARTER.md` — Self-improvement orchestrator vision
- `SOUL.md` — System principles and values
- `docs/bridge-plan-v0.1.md` — Signal bridge architecture
- `docs/hermes-integration-plan.md` — Hermes agent integration plan
