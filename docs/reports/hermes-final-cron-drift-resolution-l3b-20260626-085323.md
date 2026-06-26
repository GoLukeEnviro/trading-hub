# Hermes Final Cron Drift Resolution — L3B Git→Runtime Deploy

**Date:** 2026-06-26T08:53:23Z
**Operation Level:** L3 file-level Git-to-runtime deploy
**Merge Base:** `6e4bc91` (PR #357)
**Classification:** GREEN — 100/100

---

## Executive Verdict

**GREEN.** All three approved Git versions were deployed to runtime with zero incidents. The active SHA drift counter is now **0** (down from 3 pre-deploy). The six CRON_ONLY scripts are the documented intentionally-runtime-only set. All syntax checks pass, `drawdown_guard.py` no longer contains hardcoded passwords, and `jobs.json` was not touched. No services were restarted.

---

## Files Deployed

| File | Git SHA | Runtime SHA After | SHA Match | Syntax Check | Secret Scan |
| ---- | ------- | ----------------- | --------: | -----------: | ----------: |
| `container_watchdog.sh` | `7b13e9491f746332` | `7b13e9491f746332` | ✅ | ✅ bash -n PASS | ✅ CLEAN |
| `drawdown_guard.py` | `acf4412ee61be9f6` | `acf4412ee61be9f6` | ✅ | ✅ py_compile PASS | ✅ env-based (no hardcoded creds) |
| `quality_hub_monitor.py` | `0577900fd2edccdf` | `0577900fd2edccdf` | ✅ | ✅ py_compile PASS | ✅ CLEAN |

**Mode after deploy:** All three files `755` — matching the pre-deploy runtime executable mode.

---

## drawdown_guard.py Credential Prerequisites

| Env Name | Presence (current shell) | Fallback Mechanism | Status |
| ---------------------------- | :---------------------: | ------------------ | :----: |
| `FREQTRADE_FREQFORGE_PASS` | no | `config_host` file exists at `/home/hermes/projects/trading/freqforge/config/config_freqforge_dryrun.json` | ✅ |
| `FREQTRADE_CANARY_PASS` | no | `config_host` file exists at `/home/hermes/projects/trading/freqforge-canary/config/config_canary_dryrun.json` | ✅ |
| `FREQTRADE_REGIME_HYBRID_PASS` | no | `config_host` file exists at `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json` | ✅ |
| `FREQTRADE_REBEL_PASS` | no | `config_container` via `docker exec` into `trading-freqai-rebel-1` (confirmed Docker accessible) | ✅ |

**Note:** The Git version uses a 4-layer credential resolution strategy:
1. Environment variable (`password_env` key)
2. Host-mounted config JSON file (`config_host` — exists for 3/4 bots)
3. Container-local config via `docker exec` (`config_container` — rebel)
4. Empty password (safe fallback with WARNING log)

All four Freqtrade containers are running and Docker is fully accessible from this context, so fallback methods 2 and 3 will work even without env vars set.

**Naming discrepancy:** The `.env.freqtrade-webui.local` file uses different env var names (e.g., `FREQTRADE_REGIME_PASS` vs `FREQTRADE_REGIME_HYBRID_PASS`). The `drawdown_guard.py` names match the documented standard in `docs/security/freqtrade-config-credential-management.md`. This is a pre-existing naming divergence and does not block deployment because the layered fallback covers all four bots.

**Values never printed** throughout this operation.

---

## Pre-Deploy State (Phase 2)

| File | Git Mode | Git SHA₁₆ | Runtime Mode | Runtime SHA₁₆ | Drift |
| ---- | :------: | :--------: | :----------: | :-----------: | :---: |
| `container_watchdog.sh` | `775` | `7b13e9491f746332` | `755` | `5695e415e4f009e3` | DRIFT |
| `drawdown_guard.py` | `664` | `acf4412ee61be9f6` | `755` | `a0be1e4c83276d7a` | DRIFT (hardcoded passwords in runtime) |
| `quality_hub_monitor.py` | `664` | `0577900fd2edccdf` | `755` | `51fa06fa8b5bf840` | DRIFT |

All three files also had corresponding [`deploy_cron_scripts.sh`] CRON_ONLY entries.

---

## Backup

| Field | Value |
| ------------------- | ------------------------------------------ |
| Archive dir | `/opt/data/profiles/orchestrator/scripts/.archive/git-to-runtime-drift-fix/20260626T085151Z/` |
| Archive mode | `750` |
| `MANIFEST.jsonl` | present, includes SHA, owner, mode, size, mtime for all 3 files |
| `restore.sh` | present, mode `750` |
| Backup SHA verified | ✅ — all 3 backup SHAs match original runtime SHAs |
| Old `drawdown_guard.py` with hardcoded passwords | In archive only — **never committed to Git** |

---

## Syntax Validation

| File | Git | Runtime (after deploy) |
| ---- | :-: | :--------------------: |
| `container_watchdog.sh` (`bash -n`) | ✅ PASS | ✅ PASS |
| `drawdown_guard.py` (`py_compile`) | ✅ PASS | ✅ PASS |
| `quality_hub_monitor.py` (`py_compile`) | ✅ PASS | ✅ PASS |

---

## Secret Scan Result

| Target | Result |
| ------ | :----: |
| Git `container_watchdog.sh` | ✅ CLEAN (0 hits) |
| Git `drawdown_guard.py` | ✅ False positives only — `password_env` config keys, API password field references (not actual secrets) |
| Git `quality_hub_monitor.py` | ✅ CLEAN (0 hits) |
| **Runtime `drawdown_guard.py` (AFTER deploy)** | ✅ **No hardcoded passwords.** Uses `env_password`, API dynamic resolution, and empty fallback. |
| Runtime `container_watchdog.sh` | ✅ CLEAN |
| Runtime `quality_hub_monitor.py` | ✅ CLEAN |

The three grep hits on `drawdown_guard.py` correspond to:
- `"password": env_password,` — env-based credential resolution
- `"password": str(api.get("password", …))` — dynamic API credential resolution
- `"password": "",` — safe empty fallback

---

## jobs.json Status

- **SHA256:** `89eafda15bbfeeced4bbc634beb025bb4e00f25c56836d24e1022db92c84fc45`
- **Owner/Group:** `hermes:hermes`
- **Mode:** `600`
- **Edited:** ❌ NOT EDITED (content unchanged by this operation)

---

## Final Drift Audit

| Check | Result |
| ------------------------------- | :----: |
| Active SHA drift | **0** ✅ (was 3 pre-deploy) |
| Documented CRON_ONLY scripts | **6** (hermes_heartbeat.py, hermes_memory_dream_mode.py, hermes_session_metrics.py, hermes_weekly_report.py, memory_backfill_wrapper.sh, si_v2_active_cycle_cron.sh) |
| Missing runtime for active jobs | **0** ✅ |
| Total active jobs with named scripts | **36** |
| Total active jobs (all) | **44** (36 named + 8 built-in no-script entries) |

**Note:** The task specification expected 7 documented CRON_ONLY scripts. The actual count is 6. The previous documentation may have counted `(no script)` built-in jobs as CRON_ONLY. This is not a functional issue — the 6 actual CRON_ONLY scripts are all legitimate intentionally-runtime-only scripts.

---

## Runtime Safety Checklist

| Check | Status |
| ----- | :----: |
| `jobs.json` not edited | ✅ |
| No service restarts (Docker, Hermes, scheduler, Guardian, Freqtrade) | ✅ |
| No trading parameter changes | ✅ |
| No broad `chmod`/`chown` | ✅ (narrow per-file `chmod 755`) |
| No secrets exposed or printed | ✅ |
| No files outside the 3 approved targets deployed | ✅ |
| No wildcard copy operations | ✅ (3 explicit `cp` commands) |
| Rollback path exists and documented | ✅ |

---

## Rollback

**Exact command:**
```bash
bash /opt/data/profiles/orchestrator/scripts/.archive/git-to-runtime-drift-fix/20260626T085151Z/restore.sh
```

The `restore.sh` script:
- Copies each archived runtime version back to `/opt/data/profiles/orchestrator/scripts/`
- Verifies SHA match after each restore
- Does NOT edit `jobs.json`
- Does NOT restart services
- Requires write access to runtime scripts directory

---

## Report / Commit

| Field | Value |
| ----- | ----- |
| Report path | `docs/reports/hermes-final-cron-drift-resolution-l3b-20260626-085323.md` |
| Commit | Created below |
| Commit message | `docs: record final Hermes cron drift resolution` |

---

## Remaining Work

The cron runtime contract is now **GREEN** with the following state:

```
OK=30  DRIFT=0  CRON_ONLY=6  MISSING_RUNTIME=0
```

**Residual observations (non-blocking):**
1. **CRON_ONLY count: 6 (not 7).** There are 7 scripts in runtime without Git source, but only 6 are referenced by active cron jobs. The 7th — `hermes_error_alert.py` — exists in runtime but is NOT referenced by any cron job (verified: grep of jobs.json shows zero hits). It is a STALE runtime artifact from a previous deployment that was not archived during the L3B cleanup. The CRON_ONLY=6 metric correctly counts only actively-referenced runtime-only scripts.
2. **drawdown_guard.py env vars not exported:** The 4 `FREQTRADE_*_PASS` vars are not set in the shell. Credential resolution relies on fallback mechanisms (host config files and docker exec). If env var support is desired, the scheduler's environment configuration should be updated — but this is optional since the fallbacks work.
3. **Env var naming divergence:** `.env.freqtrade-webui.local` uses different naming than `drawdown_guard.py` expects (e.g., `FREQTRADE_REGIME_PASS` vs `FREQTRADE_REGIME_HYBRID_PASS`). Harmonizing these names would enable env-var-first resolution for all four bots.

**No further Git-to-runtime deploy actions are required.** The drift resolution campaign (PR #355 → PR #357 → L3B deploy) is complete.
