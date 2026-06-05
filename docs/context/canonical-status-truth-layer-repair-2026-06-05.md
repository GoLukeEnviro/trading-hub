# Canonical Trading Status Truth Layer Repair — 2026-06-05

**Author:** Hermes Orchestrator (glm-5.1 via Z.AI)
**Date:** 2026-06-05T09:45Z
**Scope:** Reporting/truth layer only. No trading behavior changed.

---

## Executive Summary

Repaired the canonical status/reporting truth layer of the Hermes/Freqtrade trading environment. Created a single source-of-truth status model with 7 scopes, health scores, and explicit canonical vs stale source separation. Fixed the fleet_healthcheck.py fake-red verdict (separate session). Marked stale docs as HISTORICAL. Classified Rebel, MCP Paper, and ledger risk properly.

---

## What Was Done

### T1: Fleet Health Report Drift — DONE (previous session)
- Removed decommissioned bots (rsi, momentum) from fleet_healthcheck.py
- Updated strategy names, added active fleet (4 bots)
- Fleet verdict corrected from RED (false) to YELLOW (3/4 GREEN)

### T2: Operational State Doc — DONE
- Marked `docs/state/current-operational-state.md` as HISTORICAL SNAPSHOT
- Created replacement: `docs/state/canonical-trading-status.md`
- Generated from live sources only (containers, DBs, signal files, drawdown state)

### T3: Canonical Status Artifact — DONE
- Created `docs/state/canonical-trading-status.md` (human-readable)
- Created `orchestrator/reports/canonical_trading_status_latest.json` (machine-readable)
- Includes: runtime_health=92, reporting_health=65, data_quality=75, auditability=70, overall=78

### T4: MCP Paper Sandbox Label — DONE
- Labelled as SANDBOX_ONLY in canonical status files
- Warning added: "Synthetic/sandbox prices. Not market truth. Not for live trading decisions."
- Must-not-merge rule documented

### T5: Risk View Separation — DONE
- LIVE_RISK scope: drawdown_state.json (current, 0% drawdown, 4/4 bots reachable)
- LEDGER_RISK scope: fleet_risk_state.json (separate, contains stale backtest source)
- Explicit stale source warning: regime_hybrid_backtest (static 990.0 since 2026-05-30)
- Never merged or averaged

### T6: Rebel Auditability — DONE
- Classified as: RUNNING_INFERENCE_ONLY
- Evidence: FreqAI inference active (0.4-0.9s cycles), 0 trades in DB, state=RUNNING
- VISIBILITY_GAP documented: No trade audit trail until first entry
- No DB migration needed (not approved, not in scope)

### T7: Cron/Scheduler Alignment — REVIEWED
- 31 cron jobs, all status=none (healthy)
- Key pipeline jobs running on schedule (trading-pipeline */5min, unified-signal-heartbeat */15min)
- No stale scripts identified; fleet_healthcheck.py was already patched

---

## Files Changed

| File | Action | Why |
|------|--------|-----|
| `docs/state/canonical-trading-status.md` | CREATED | New canonical human-readable status |
| `orchestrator/reports/canonical_trading_status_latest.json` | CREATED | New canonical machine-readable status |
| `docs/state/current-operational-state.md` | HEADER ADDED | Marked HISTORICAL, superseded by canonical |
| `docs/context/canonical-status-truth-layer-repair-2026-06-05.md` | CREATED | This report |

---

## Validation

- JSON artifacts parse: PASS (canonical_trading_status_latest.json valid)
- No strategy files changed: PASS
- No bot configs changed: PASS
- No dry_run=false: PASS
- No secrets in diff: PASS
- Containers still running: PASS (verified docker ps)
- Decommissioned bots not in fleet score: PASS
- MCP Paper labelled SANDBOX_ONLY: PASS
- Risk scopes separated: PASS
- Rebel classified: PASS (RUNNING_INFERENCE_ONLY)

---

## Remaining Risks

1. **fleet_risk_state stale source**: regime_hybrid_backtest (static equity since 2026-05-30) — documented, not removed (requires user approval as fleet_risk_manager.py consumes it)
2. **Rebel VISIBILITY_GAP**: 0 trades, no audit trail — classified, not fixable without strategy/config change
3. **Permission errors**: 3,786 occurrences on orchestrator config files — separate issue, not in scope
4. **Low signal confidence**: All pairs HOLD, max confidence 0.468 — operational observation, not a reporting issue

---

## Next Safe Step

Clean up `regime_hybrid_backtest` stale source from `fleet_risk_state.json` portfolio sources, or confirm it is intentionally retained for baseline comparison. This requires user approval as it modifies a shared state file consumed by `fleet_risk_manager.py`.
