# Hermes Cron Stale Runtime Archive Plan

## Purpose

This document defines the plan for archiving 29 STALE_OR_DEAD scripts from the Hermes runtime scripts directory. These files are no longer needed for active operations.

## Scope

**29 files** classified as STALE_OR_DEAD in the CRON_ONLY reconciliation audit (2026-06-26).

## Non-Goal

**No cleanup is executed in this L2A phase.** This document is a plan only. Actual archive operations require L3 approval.

## Archive Target Proposal

```
/opt/data/profiles/orchestrator/scripts/.archive/20260626-cron-only-stale/
```

## Backup Requirement Before Runtime Mutation

Before any file is moved or deleted:

1. The file must already exist in Git (for MISSING_FROM_GIT files that were promoted) OR
2. A SHA256 checksum must be recorded in this plan AND
3. A restore command must be documented AND
4. The archive directory must be created first (copy, not move) AND
5. Only after verification of the copy should the original be removed.

## Restore Commands

To restore any single file from archive:

```bash
cp /opt/data/profiles/orchestrator/scripts/.archive/20260626-cron-only-stale/<filename> \
   /opt/data/profiles/orchestrator/scripts/<filename>
```

To restore all files from archive:

```bash
cp -a /opt/data/profiles/orchestrator/scripts/.archive/20260626-cron-only-stale/* \
   /opt/data/profiles/orchestrator/scripts/
```

## Per-File Stale Table

### Backup Files (10)

| File | Size | SHA (short) | Mtime | Notes | Archive Action |
|---|---|---|---|---|---|
| `autonomous_controller.py.pre-harden` | 29160 | `b84b61b94c57c38d` | 2026-05-28 | Pre-harden backup, different from live | Copy to archive, remove from runtime |
| `fleet_risk_auto_params.py.bak.phase2` | 12283 | `72f18bb60f25338a` | 2026-06-05 | Phase backup, different from live | Copy to archive, remove from runtime |
| `hermes_session_metrics.py.bak-phase-c1-closure` | 4692 | `61d0ace858daed92` | 2026-06-11 | Phase backup, different from live | Copy to archive, remove from runtime |
| `memory_backfill.py.bak-20260521083037` | 20391 | `054b9691673b9369` | 2026-05-21 | Timestamp backup, different from live | Copy to archive, remove from runtime |
| `memory_backfill.py.bak.20260525_121210` | 23305 | `554f9bfcfedce332` | 2026-05-25 | Timestamp backup, different from live | Copy to archive, remove from runtime |
| `memory_hygiene_monitor.py.bak-20260612-072416` | 4389 | `2b9877986369b47c` | 2026-06-12 | Timestamp backup, different from live | Copy to archive, remove from runtime |
| `observation_runner.py.bak-20260603T2342Z` | 36448 | `5cf710a470334bf7` | 2026-06-02 | Timestamp backup, different from live | Copy to archive, remove from runtime |
| `system_optimizer.py.bak.20260605` | 57575 | `82fe9ba44f007d49` | 2026-06-05 | Date backup, different from live | Copy to archive, remove from runtime |
| `trading_pipeline.py.bak-20260521T095210Z` | 30873 | `3e4356140d32b8d4` | 2026-05-19 | Timestamp backup, different from live | Copy to archive, remove from runtime |
| `trading_pipeline.py.bak.20260605` | 34650 | `1525282d4022bb6c` | 2026-06-05 | **SHA-identical to live** — content preserved in Git | Copy to archive, remove from runtime |

### One-Shot Historical Fixers (3)

| File | Size | SHA (short) | Mtime | Notes | Archive Action |
|---|---|---|---|---|---|
| `apply-automation-fix-20260528.sh` | 8396 | `b8bc48d6a3084972` | 2026-06-06 | One-shot fixer from 2026-05-28 | Copy to archive, remove from runtime |
| `apply-soul-alignment-20260528.sh` | 9044 | `88f020298297cd85` | 2026-06-06 | One-shot fixer from 2026-05-28 | Copy to archive, remove from runtime |
| `reset_false_error_jobs.sh` | 1330 | `1f9547307089a41f` | 2026-06-06 | One-shot fixer from 2026-05-28 | Copy to archive, remove from runtime |

### Dead SI Bot Wrappers (16)

These are wrapper scripts that call `self_improvement/bot_*/run_*.sh` targets that no longer exist. All are PAUSED in jobs.json or have no job reference.

| File | Size | SHA (short) | Mtime | Referenced in jobs.json | Archive Action |
|---|---|---|---|---|---|
| `si_bot_a_analyze.sh` | 143 | `b59a37bafd7e93be` | 2026-06-06 | No | Copy to archive, remove from runtime |
| `si_bot_a_backtest.sh` | 94 | `c3f606d21bb2bea0` | 2026-06-06 | Yes (paused, id=36c83275566f) | Copy to archive, remove from runtime, remove job |
| `si_bot_a_daily.sh` | 98 | `b3de4c23ef0fb933` | 2026-06-11 | Yes (paused, id=324273d2b714) | Copy to archive, remove from runtime, remove job |
| `si_bot_a_walkforward.sh` | 97 | `1d256e9d5003da17` | 2026-06-06 | No | Copy to archive, remove from runtime |
| `si_bot_b_analyze.sh` | 93 | `7ae6ab0984886987` | 2026-06-06 | No | Copy to archive, remove from runtime |
| `si_bot_b_backtest.sh` | 94 | `565f9869024663fc` | 2026-06-06 | Yes (paused, id=9a0da2c53426) | Copy to archive, remove from runtime, remove job |
| `si_bot_b_daily.sh` | 98 | `c7ca91c7d07664bb` | 2026-06-11 | Yes (paused, id=d990492f1a85) | Copy to archive, remove from runtime, remove job |
| `si_bot_b_walkforward.sh` | 97 | `f4bc65771c11f58a` | 2026-06-06 | Yes (paused, id=2338845f231d) | Copy to archive, remove from runtime, remove job |
| `si_bot_c_analyze.sh` | 93 | `d65b070201af7814` | 2026-06-06 | No | Copy to archive, remove from runtime |
| `si_bot_c_backtest.sh` | 94 | `fc9e46a54ac1cf79` | 2026-06-06 | Yes (paused, id=d45883cfd84f) | Copy to archive, remove from runtime, remove job |
| `si_bot_c_daily.sh` | 98 | `4bf3ae4b10f289d1` | 2026-06-06 | Yes (paused, id=ef2edac12151) | Copy to archive, remove from runtime, remove job |
| `si_bot_c_walkforward.sh` | 97 | `5eb2936ccadd8e7d` | 2026-06-06 | Yes (paused, id=031e3e6a8c18) | Copy to archive, remove from runtime, remove job |
| `si_bot_d_analyze.sh` | 93 | `4b01ddde9524895e` | 2026-06-06 | No | Copy to archive, remove from runtime |
| `si_bot_d_backtest.sh` | 94 | `d9535d7228e81e5c` | 2026-06-06 | Yes (paused, id=505180fcb9b5) | Copy to archive, remove from runtime, remove job |
| `si_bot_d_daily.sh` | 98 | `bbc9f39c7559a953` | 2026-06-06 | Yes (paused, id=3e30a35f6c37) | Copy to archive, remove from runtime, remove job |
| `si_bot_d_walkforward.sh` | 97 | `22e917abd0e2396d` | 2026-06-06 | Yes (paused, id=063ee6241582) | Copy to archive, remove from runtime, remove job |

## L3 Approval Checklist

Before executing the archive operation, the following must be confirmed:

- [ ] All 16 MISSING_FROM_GIT scripts are successfully committed to Git (L2A complete)
- [ ] Runtime-only manifest is committed (L2A complete)
- [ ] This archive plan is reviewed and approved
- [ ] A backup of the runtime scripts directory exists (e.g., `tar -czf /tmp/hermes-runtime-scripts-backup-$(date -u +%Y%m%d).tgz /opt/data/profiles/orchestrator/scripts/`)
- [ ] For the 11 si_bot_* files with jobs.json references: the corresponding paused jobs are removed from jobs.json BEFORE file archive
- [ ] Restore commands are documented and tested
- [ ] After archive, run `deploy_cron_scripts.sh` in dry-run mode to verify no unexpected drift

## Archive Execution Command (for L3)

```bash
# Step 1: Create archive directory
mkdir -p /opt/data/profiles/orchestrator/scripts/.archive/20260626-cron-only-stale

# Step 2: Copy files to archive (preserve metadata)
for f in \
  autonomous_controller.py.pre-harden \
  fleet_risk_auto_params.py.bak.phase2 \
  hermes_session_metrics.py.bak-phase-c1-closure \
  memory_backfill.py.bak-20260521083037 \
  memory_backfill.py.bak.20260525_121210 \
  memory_hygiene_monitor.py.bak-20260612-072416 \
  observation_runner.py.bak-20260603T2342Z \
  system_optimizer.py.bak.20260605 \
  trading_pipeline.py.bak-20260521T095210Z \
  trading_pipeline.py.bak.20260605 \
  apply-automation-fix-20260528.sh \
  apply-soul-alignment-20260528.sh \
  reset_false_error_jobs.sh \
  si_bot_a_analyze.sh si_bot_a_backtest.sh si_bot_a_daily.sh si_bot_a_walkforward.sh \
  si_bot_b_analyze.sh si_bot_b_backtest.sh si_bot_b_daily.sh si_bot_b_walkforward.sh \
  si_bot_c_analyze.sh si_bot_c_backtest.sh si_bot_c_daily.sh si_bot_c_walkforward.sh \
  si_bot_d_analyze.sh si_bot_d_backtest.sh si_bot_d_daily.sh si_bot_d_walkforward.sh; do
  cp -a "/opt/data/profiles/orchestrator/scripts/$f" \
     "/opt/data/profiles/orchestrator/scripts/.archive/20260626-cron-only-stale/$f"
done

# Step 3: Verify archive
for f in ...; do
  orig_sha=$(sha256sum "/opt/data/profiles/orchestrator/scripts/$f" | cut -d' ' -f1)
  arch_sha=$(sha256sum "/opt/data/profiles/orchestrator/scripts/.archive/20260626-cron-only-stale/$f" | cut -d' ' -f1)
  if [ "$orig_sha" = "$arch_sha" ]; then echo "OK|$f"; else echo "FAIL|$f"; fi
done

# Step 4: Remove originals (only after verification)
for f in ...; do
  rm "/opt/data/profiles/orchestrator/scripts/$f"
done
```
