# C3 Rollback Plan Review Gate — 2026-07-03

**Issue:** #440 — C3 Rollback Plan Review Gate
**Status:** ✅ Review Complete
**Rollback Recommendation Validity:** ✅ VALID (confirmed by #438 triage)

---

## 1. Rollback Recommendation Validity

| Check | Result | Evidence |
|-------|--------|----------|
| #438 triage complete? | ✅ Yes | Triage confirmed ROLLBACK_RECOMMENDED valid |
| Measurement-window contamination? | ✅ None | LINK/USDT 2026-06-24 loss inside 14-day window |
| Decision robust to data-scope issue? | ✅ Yes | BREACH in all three calculation methods |
| **Overall validity** | **✅ VALID** | |

## 2. Rollback Target Verification

| Check | Result | Evidence |
|-------|--------|----------|
| C3 ceremony target | ✅ `freqtrade-freqforge-canary` | `live_canary_activation_ceremony.json` → `canary_target` |
| C4 decision target | ✅ `freqtrade-freqforge-canary` | `live_canary_measurement_decision.json` → `canary_target` |
| C2 config plan target | ✅ `freqtrade-freqforge-canary` | C2 report |
| C1 approval gate target | ✅ `freqtrade-freqforge-canary` | C1 gate evidence |
| **Target consistent across all gates** | **✅ Yes** | Single bot, no fleet scope |

## 3. Snapshot and Audit Artifact Verification

| Artifact | Path | Exists? |
|----------|------|:-------:|
| Pre-activation config snapshot | `var/si_v2/live_canary_activation_ceremony/pre_activation_config_snapshot.json` | ✅ |
| Pre-activation kill switch snapshot | `var/si_v2/live_canary_activation_ceremony/pre_activation_kill_switch_snapshot.txt` | ✅ |
| C3 approval marker snapshot | `var/si_v2/live_canary_activation_ceremony/c3_approval_marker_snapshot.md` | ✅ |
| C3 ceremony JSON | `var/si_v2/live_canary_activation_ceremony/live_canary_activation_ceremony.json` | ✅ |
| C3 ceremony report | `var/si_v2/live_canary_activation_ceremony/live_canary_activation_ceremony.md` | ✅ |
| C4 decision JSON | `var/si_v2/live_canary_measurement_decision/live_canary_measurement_decision.json` | ✅ |
| C4 decision report | `var/si_v2/live_canary_measurement_decision/live_canary_measurement_decision.md` | ✅ |
| Dry-run config (restore target) | `freqforge-canary/config/config_canary_dryrun.json` | ✅ |
| Fleet dry-run rollback executor | `self_improvement_v2/src/si_v2/rollout/fleet_dry_run_rollback_executor.py` | ✅ |

## 4. Kill Switch and Alerting Reference Verification

| Reference | Path | Exists? |
|-----------|------|:-------:|
| Kill switch module | `freqtrade/shared/kill_switch.py` | ✅ — current mode: **NORMAL** |
| Kill switch runbook | `docs/runbooks/kill-switch.md` | ✅ |
| Kill switch procedure doc | `docs/references/freqtrade-kill-switch-procedure.md` | ❌ **MISSING** |
| B2 risk limits spec | `docs/specs/production-risk-limits-spec.md` | ✅ |
| B3 incident response runbooks | `docs/specs/incident-response-runbooks.md` | ✅ |
| B4 alerting gate report | `docs/reports/production-alerting-readiness-gate.md` | ✅ |
| Emergency stop script | `orchestrator/scripts/emergency_stop.sh` | ❌ **MISSING** |
| Emergency audit directory | `var/si_v2/emergency/` | ❌ **MISSING** |
| Incident report directory | `docs/incidents/` | ❌ **MISSING** |

## 5. C3 Rollback Plan — Step-by-Step Review

The C3 ceremony defines this 7-step rollback plan:

| Step | Action | Feasibility | Gap |
|------|--------|:-----------:|-----|
| 1 | Activate kill switch: set MODE = 'EMERGENCY' | ✅ `kill_switch.py` supports `set_kill_mode(EMERGENCY)` via CLI or Python | None |
| 2 | Halt canary container: `docker stop freqtrade-freqforge-canary` | ⚠️ Requires Docker access and container name | No emergency stop script exists |
| 3 | Restore dry-run config from preserved snapshot | ✅ Snapshot exists at `pre_activation_config_snapshot.json` | None |
| 4 | Redeploy canary in dry-run mode | ⚠️ Requires Docker compose or manual restart | No documented compose command |
| 5 | Verify dry-run operation (logs, DB, API health) | ✅ Standard Freqtrade healthcheck | None |
| 6 | Reset kill switch to NORMAL | ✅ `kill_switch.py` supports `clear_kill_switch()` | None |
| 7 | File post-mortem report in `docs/incidents/` | ⚠️ Directory `docs/incidents/` does not exist | Must be created |

## 6. Required Human Approval Boundary

| Item | Required Marker | Status |
|------|----------------|:------:|
| Rollback execution | `APPROVED_LIVE_CANARY_ROLLBACK` | ❌ **Not defined** |
| Post-rollback resume | `APPROVED_RESUME_LIVE` | Defined in B2 spec |
| Fleet rollout | `APPROVED_LIVE_FLEET_ROLLOUT` | ❌ Not present |

**Recommendation:** A new approval marker `APPROVED_LIVE_CANARY_ROLLBACK` should be created in `docs/decisions/` before any rollback execution. This keeps the rollback path human-gated and auditable, consistent with the C1/C3 approval pattern.

## 7. Gaps and Risks

| # | Gap | Severity | Mitigation |
|---|-----|:--------:|------------|
| 1 | `orchestrator/scripts/emergency_stop.sh` does not exist | MEDIUM | Use manual `docker stop` or create script before rollback |
| 2 | `docs/references/freqtrade-kill-switch-procedure.md` missing | LOW | Kill switch runbook at `docs/runbooks/kill-switch.md` covers usage |
| 3 | `var/si_v2/emergency/` directory does not exist | LOW | Create on first emergency event |
| 4 | `docs/incidents/` directory does not exist | LOW | Create on first post-mortem |
| 5 | No `APPROVED_LIVE_CANARY_ROLLBACK` marker defined | MEDIUM | Must be created before rollback execution |
| 6 | No live rollback executor module exists | MEDIUM | `fleet_dry_run_rollback_executor.py` exists for dry-run; live rollback needs separate executor or manual steps |

## 8. Next Gate Status

| Gate | Status | Required |
|------|:-----:|----------|
| C4 ROLLBACK_RECOMMENDED | ✅ Valid | Confirmed by #438 |
| C3 rollback plan | ✅ Reviewed | 7 steps documented, gaps identified |
| `APPROVED_LIVE_CANARY_ROLLBACK` | ❌ Missing | Human approval marker needed |
| D1 | ❌ BLOCKED | Requires C4 KEEP + APPROVED_LIVE_FLEET_ROLLOUT |

## 9. Recommendation

The C3 rollback plan is **substantively complete** with 7 documented steps, snapshot-backed artifacts, and kill-switch integration. Three gaps exist (emergency stop script, rollback approval marker, live rollback executor) but none block the review gate itself.

**Next action (human):** Decide whether to:
1. Create `APPROVED_LIVE_CANARY_ROLLBACK` marker and execute rollback per C3 plan, OR
2. Override the ROLLBACK_RECOMMENDED decision and proceed with live canary under extended observation.

**No rollback executed. No D1 started. No runtime touched.**
