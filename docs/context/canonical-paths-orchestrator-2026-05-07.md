# Canonical Paths Report — Orchestrator Bootstrap — 2026-05-07

## Executive Summary

**Status: PARTIAL** — Legacy PrimoAgent path is operative, project path is target.

## Path Verification

| Path | Status | Notes |
|------|--------|-------|
| `/home/hermes/projects/trading` | ✅ EXISTS | Trading root established |
| `/home/hermes/primoagent` | ✅ EXISTS | Legacy runtime path (operative) |
| `/home/hermes/projects/trading/primoagent` | ❌ MISSING | Target canonical path (not yet created) |
| `/home/hermes/projects/trading/freqtrade` | ✅ EXISTS | Freqtrade hub established |

## Current Operative Paths

### PrimoAgent Runtime
- **Current:** `/home/hermes/primoagent`
- **Status:** Active, used by cronjob `d3ca1b9e84f8` (primoagent-signal-cycle)
- **Ownership:** root-owned directory (Docker one-shot pattern)
- **Output:** `/home/hermes/primoagent/output/signals/primo_multi_signal_latest.json`

### Freqtrade Hub
- **Current:** `/home/hermes/projects/trading/freqtrade`
- **Status:** Active, three bots running
- **Bridge Script:** `/home/hermes/projects/trading/freqtrade/tools/primo_signal_bridge.py`
- **Shared Helper:** `/home/hermes/projects/trading/freqtrade/shared/primo_signal.py`

### Cronjob Paths
- **primoagent-signal-cycle:** references `/home/hermes/primoagent` (via script or prompt)
- **freqtrade-4h-fleet-trade-snapshot:** references freqtrade hub
- **strategy_heartbeat_intelligence:** `/home/hermes/projects/trading/Agenten_Auto_Trade`
- **freqtrade-daily-data-regime-report:** references freqtrade hub

## Target Canonical Paths

### Recommended Future State

```
/home/hermes/projects/trading/
├── primoagent/          ← canonical PrimoAgent location (future)
│   ├── run_primo_crypto_pipeline.py
│   ├── crypto_data_adapter.py
│   ├── risk_guard_v0_1.py
│   ├── shadow_logger_v0_1.py
│   ├── decision_engine/
│   └── output/signals/
├── freqtrade/           ← already canonical
├── orchestrator/        ← newly created
└── docs/
```

### Migration Requirements

Before migrating PrimoAgent to canonical path:

1. **Cronjob Compatibility**
   - Update `primoagent-signal-cycle` cronjob to reference new path
   - Or create symlink: `/home/hermes/primoagent → /home/hermes/projects/trading/primoagent`

2. **Bridge Script Compatibility**
   - Verify bridge script reads from correct signal path
   - Current: likely reads from `/home/hermes/primoagent/output/signals/`
   - Target: `/home/hermes/projects/trading/primoagent/output/signals/`

3. **Permission Model**
   - Legacy path is root-owned (Docker one-shot pattern)
   - Target path must preserve this or adapt cronjob

4. **Symlink Strategy (Recommended)**
   - Keep `/home/hermes/primoagent` as symlink to new location
   - Preserves existing cronjob references
   - Preserves existing bridge script paths
   - Preserves user muscle memory

## Recommendation

**Phase 0 Decision:** Do not migrate yet.

**Rationale:**
- Current system is stable
- Cronjobs are running successfully
- Bridge script is functional
- Migration adds risk without immediate benefit

**Future Action:**
1. Complete orchestrator bootstrap
2. Stabilize RiskGuard + ShadowLogger
3. Then migrate PrimoAgent with symlink strategy
4. Update cronjob to point to canonical path
5. Verify one full cycle before retiring legacy path

## Compatibility Notes

- Existing cronjobs will continue working with symlink approach
- Bridge scripts using absolute paths to `/home/hermes/primoagent` will work through symlink
- Docker volumes mounting `/home/hermes/primoagent` will work through symlink
- User workflows and muscle memory preserved

## Next Steps

1. Complete orchestrator bootstrap (this phase)
2. Document migration plan separately
3. Execute migration only after RiskGuard + ShadowLogger are stable
4. Use symlink strategy for zero-downtime migration

---

**Report Date:** 2026-05-07  
**Status:** PARTIAL (legacy path operative, target path documented)  
**Migration:** Deferred to future phase
