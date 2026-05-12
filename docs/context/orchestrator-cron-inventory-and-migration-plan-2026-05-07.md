# Cron Inventory and Migration Plan — Orchestrator Bootstrap — 2026-05-07

## Executive Summary

**Status: INVENTORY COMPLETE — MIGRATION DEFERRED**

Four cronjobs exist in `default` profile. No migration in this phase.

## Current Cronjobs (Default Profile)

| Job ID | Name | Schedule | Last Run | Status | Deliver |
|--------|------|----------|----------|--------|---------|
| `aed6ed7fb2e0` | freqtrade-daily-data-regime-report | `0 7 * * *` | 2026-05-07 07:06 ✅ | active | origin |
| `0f2ae23ada95` | freqtrade-4h-fleet-trade-snapshot | every 240m | 2026-05-07 15:15 ✅ | active | origin |
| `a1d8c861f0b1` | strategy_heartbeat_intelligence | every 120m | 2026-05-07 15:14 ✅ | active | local |
| `d3ca1b9e84f8` | primoagent-signal-cycle | every 240m | 2026-05-07 12:36 ✅ | active | local |

## Job Details

### 1. freqtrade-daily-data-regime-report
- **Schedule:** Daily at 07:00 UTC
- **Delivery:** origin (Telegram)
- **Last Run:** OK
- **Purpose:** Daily regime analysis report from Freqtrade data

### 2. freqtrade-4h-fleet-trade-snapshot
- **Schedule:** Every 240 minutes (4 hours)
- **Script:** `freqtrade_monitor.py`
- **Delivery:** origin (Telegram)
- **Last Run:** OK
- **Purpose:** Fleet trade snapshot every 4 hours

### 3. strategy_heartbeat_intelligence
- **Schedule:** Every 120 minutes (2 hours)
- **Script:** `heartbeat_intelligence_wrapper.py`
- **Workdir:** `/home/hermes/projects/trading/Agenten_Auto_Trade`
- **Delivery:** local (no delivery)
- **Last Run:** OK
- **Purpose:** Strategy heartbeat intelligence

### 4. primoagent-signal-cycle
- **Schedule:** Every 240 minutes (4 hours)
- **Delivery:** local (no delivery)
- **Last Run:** OK
- **Purpose:** PrimoAgent signal generation cycle

## Orchestrator Profile Cron Status

**Current:** No cronjobs in `orchestrator` profile yet.

**Reason:** This phase is inventory-only. Migration requires separate plan and approval.

## Future Migration Plan

### Migration Principles

1. **Pause old, don't delete** — preserve ability to rollback
2. **Recreate under orchestrator** — equivalent job with orchestrator profile context
3. **Run once manually** — verify output matches expected behavior
4. **Compare outputs** — ensure no regression
5. **Retire old only after approval** — explicit user confirmation required

### Proposed Migration Order

| Phase | Job | Action | Priority |
|-------|-----|--------|----------|
| 1 | `primoagent-signal-cycle` | Migrate first | HIGH |
| 2 | `freqtrade-4h-fleet-trade-snapshot` | Migrate second | HIGH |
| 3 | `strategy_heartbeat_intelligence` | Migrate third | MEDIUM |
| 4 | `freqtrade-daily-data-regime-report` | Migrate last | LOW |

### Migration Steps (Per Job)

```bash
# Step 1: Pause old job
hermes cron pause <job_id>

# Step 2: Create equivalent under orchestrator
orchestrator cron create \
  --name <job_name> \
  --schedule "<schedule>" \
  --prompt "<prompt>" \
  --skills <required_skills>

# Step 3: Run manually once
orchestrator cron run <new_job_id>

# Step 4: Compare outputs
# - Check output content
# - Check delivery target
# - Check skill availability

# Step 5: Retire old (only after approval)
hermes cron remove <old_job_id>
```

### Skill Requirements (Per Job)

| Job | Required Skills |
|-----|-----------------|
| primoagent-signal-cycle | crypto-data-adapter, trading-hub-operations |
| freqtrade-4h-fleet-trade-snapshot | freqtrade-fleet-auditing-and-readiness, docker-container-recovery |
| strategy_heartbeat_intelligence | freqtrade-fleet-auditing-and-readiness, honcho-operations |
| freqtrade-daily-data-regime-report | freqtrade-fleet-auditing-and-readiness, freqtrade-pair-screening |

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Job fails under orchestrator | LOW | MEDIUM | Run manually first, compare outputs |
| Skills missing | LOW | LOW | Skill audit already passed |
| Delivery target wrong | LOW | LOW | Verify delivery config before migration |
| Output format changed | LOW | MEDIUM | Compare pre/post migration outputs |
| Timing gap during migration | MEDIUM | LOW | Pause old, create new, minimal gap |

## This Phase Decision

**No cronjobs migrated.**

**Rationale:**
- Current jobs are running successfully
- Orchestrator bootstrap must complete first
- RiskGuard + ShadowLogger should be stable before cron migration
- Symlink strategy for PrimoAgent should be decided first

## Next Steps

1. Complete orchestrator bootstrap (this phase)
2. Stabilize RiskGuard + ShadowLogger
3. Execute migration plan phase separately
4. Document each migration in docs/incidents/

---

**Inventory Date:** 2026-05-07  
**Status:** INVENTORY COMPLETE  
**Migration:** DEFERRED  
**Jobs Inventoried:** 4  
**Jobs Migrated:** 0
