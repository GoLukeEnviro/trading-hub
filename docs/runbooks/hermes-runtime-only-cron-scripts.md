# Hermes Runtime-Only Cron Scripts

## Purpose

This document lists scripts that are intentionally **runtime-only** — they live in `/opt/data/profiles/orchestrator/scripts/` and are referenced by the Hermes scheduler (`jobs.json`), but are **not** tracked in the Git repository at `/home/hermes/projects/trading/orchestrator/scripts/`.

These scripts are canonical in runtime only. They are not drift — they are intentionally deployed and managed outside the Git workflow.

## Source of Truth

- **Runtime path:** `/opt/data/profiles/orchestrator/scripts/`
- **Cron registry:** `/opt/data/profiles/orchestrator/cron/jobs.json`
- **Git source path:** `/home/hermes/projects/trading/orchestrator/scripts/`

## Generated From

- **Report:** `/tmp/hermes_cron_only_reconciliation_report.md`
- **Audit timestamp:** 2026-06-26 ~08:00 UTC
- **Audit tool:** Hermes CRON_ONLY Reconciliation Audit (L0)

## CANONICAL_RUNTIME_ONLY Scripts

| Script | Referenced by jobs.json | Reason Runtime-Only | SHA (short) at Audit | Expected Action |
|---|---|---|---|---|
| `si_v2_active_cycle_cron.sh` | `64866012641a` (si-v2-active-cycle) | SI v2 active cycle runner; deployed via cron setup, not via Git | `4d5949da4b566f10` | Keep in runtime; optionally add to Git as canonical source |
| `hermes_memory_dream_mode.py` | `e19a613fb796` (Dream Mode) | Daily memory curation; runtime-deployed | `8b19b816670e2344` | Keep in runtime |
| `hermes_heartbeat.py` | `62a9293cf241` (Hermes Heartbeat) | 15-min heartbeat logger; runtime-deployed | `809c0deb99d81abf` | Keep in runtime |
| `hermes_session_metrics.py` | `886d30a10784` (Hermes Session Metrics) | 5-min session metrics; runtime-deployed | `b5e6b0608ec285a2` | Keep in runtime |
| `hermes_weekly_report.py` | `1e5e818f0845` (Hermes Weekly Report) | Weekly report generator; runtime-deployed | `e00de036feeeeaa5` | Keep in runtime |
| `memory_backfill_wrapper.sh` | `53ae23572f8c` (Memory Backfill) | Wrapper for memory backfill; runtime-deployed | `cda1f82f426e974b` | Keep in runtime |
| `hermes_error_alert.py` | `e0a76eaa101a` (Hermes Error-Alert) | Error alert script (currently PAUSED); runtime-deployed | `cddf93c7618954a3` | Keep in runtime |

## Rules for Adding Future Runtime-Only Scripts

1. Every runtime-only script must be documented in this manifest before deployment.
2. Every runtime-only script must have a corresponding entry in `jobs.json`.
3. The SHA256 short hash must be recorded at deployment time.
4. If a runtime-only script is later promoted to Git, remove it from this manifest and add it to the Git source tree.
5. If a runtime-only script is decommissioned, remove it from this manifest and archive the file.

## Rules for Not Storing Secrets in Scripts

1. No runtime-only script may contain hardcoded API keys, tokens, passwords, or private keys.
2. Secrets must be read from environment variables, `.env` files, or Hermes config at runtime.
3. If a script is found to contain secrets, it must be immediately patched and the secret rotated.

## Validation Command

To verify that all CANONICAL_RUNTIME_ONLY scripts still exist in runtime:

```bash
for f in \
  si_v2_active_cycle_cron.sh \
  hermes_memory_dream_mode.py \
  hermes_heartbeat.py \
  hermes_session_metrics.py \
  hermes_weekly_report.py \
  memory_backfill_wrapper.sh \
  hermes_error_alert.py; do
  if [ -f "/opt/data/profiles/orchestrator/scripts/$f" ]; then
    echo "EXISTS|$f"
  else
    echo "MISSING|$f"
  fi
done
```

To verify that no CANONICAL_RUNTIME_ONLY script has drifted into Git:

```bash
for f in \
  si_v2_active_cycle_cron.sh \
  hermes_memory_dream_mode.py \
  hermes_heartbeat.py \
  hermes_session_metrics.py \
  hermes_weekly_report.py \
  memory_backfill_wrapper.sh \
  hermes_error_alert.py; do
  if [ -f "/home/hermes/projects/trading/orchestrator/scripts/$f" ]; then
    echo "DRIFT|$f — found in Git source"
  else
    echo "CLEAN|$f — not in Git source"
  fi
done
```
