# Decommissioning Register

> Tracks all decommissioned components, when they were removed, what replaced
> them, and what artifacts remain.

---

## Decommissioned Components

| Component | Decommissioned | Replaced By | Remaining Artifacts | Notes |
|-----------|---------------|-------------|---------------------|-------|
| **PrimoAgent** | Phase 44-45 | SI-v2 autonomous loop | `primo/` directory, `primo_signal.py` in `freqtrade/shared/` | Primo directory contains vestigial code. `primo_signal.py` retained as legacy signal filter + kill-switch integration. |
| **Bridge** (`hermes_primo_bridge.py`) | Phase 44-45 | SI-v2 apply chain | `bridge/` directory | Bridge directory contains vestigial code. No active connections. |
| **Intelligence** layer | Vestigial | N/A (never active) | `intelligence/` directory | Contains market intelligence stubs. No active code or runtime usage. |
| **SI-v1 Controller** (`si-bot-*`) | Phase 27 (PR #159) | SI-v2 Active Cycle Runner | Possible stale script references | v1 residue closure. SI-v2 loop fully replaced v1. |
| **Autopilot** system | 2026-06 | SI-v2 Active Cycle Runner | `docs/state/autopilot/` | Autopilot v0 was the initial read-only monitor. Replaced by the 6h cron cycle runner. |
| **Momentum bot** | Pre-2026-06 | — | `freqtrade/bots/momentum/` | Decommissioned. Historical state artifact may still exist. |
| **MVS bot** | Never deployed | — | — | Never deployed. Listed as non-current in fleet documentation. |
| **RSI bot** | Pre-2026-06 | — | `freqtrade/bots/rsi/` | Decommissioned. No current state artifact. |

---

## Removed CI / Coverage Paths

| Path | Removed In | Reason | PR |
|------|-----------|--------|----|
| `bridge/` from `.coveragerc` | 2026-07-03 (Phase B) | Decommissioned component | #459 |
| `primo/` from `.coveragerc` | 2026-07-03 (Phase B) | Decommissioned component | #459 |
| `intelligence/` from `.coveragerc` | 2026-07-03 (Phase B) | Decommissioned component | #459 |
| `bridge/` from `main-gate.yml` compileall | 2026-07-03 (Phase B) | Decommissioned component | #459 |
| `primo/` from `main-gate.yml` compileall | 2026-07-03 (Phase B) | Decommissioned component | #459 |
| `intelligence/` from `main-gate.yml` compileall | 2026-07-03 (Phase B) | Decommissioned component | #459 |

---

## Stale Tests (Not Yet Cleaned)

| Test | Status | Issue | Action |
|------|--------|-------|--------|
| `test_bridge_primo_intelligence_phase4.py` | Stale — tests decommissioned code | L3 follow-up | Separate cleanup issue |

---

## Cleanup Candidates (Separate L3 Issues)

| Artifact | Type | Scope | Blocker |
|----------|------|-------|---------|
| `root/*.bak`, `root/*.backup.*` | Backup files | L3 | Requires approval |
| `freqtrade/shared/*.bak*`, `freqtrade/shared/*.tmp-*` | Backup/temp files | L3 | Requires approval |
| `orchestrator/backups/` | Backup directory | L3 | Requires approval |
| `test_export_trade_history.py` (duplicate) | Duplicate test | L2 | Verify uniqueness |
| `SHARED_CONSTANTS.py` missing `import os` | Code defect | L2 | Fix + test |

---

## Related Documents

| Document | Location |
|----------|----------|
| ADR: Autonomous Dry-Run | `docs/decisions/ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md` |
| Live Roadmap | GitHub Issue #423 |
| Architecture | `docs/ARCHITECTURE.md` |
| Glossary | `docs/glossary.md` |
