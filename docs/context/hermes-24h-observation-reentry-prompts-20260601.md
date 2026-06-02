# Real 24h Stability Observation — Re-Entry Prompts

**T0 captured:** 2026-06-01T16:05:41Z
**T0 anchor file:** `orchestrator/state/observation-24h/T0_anchor.txt` = `20260601-1605`
**T0 baseline:** `orchestrator/state/observation-24h/T0-20260601-1605/baseline.txt`
**T0 script:** `orchestrator/state/observation-24h/T0-20260601-1605/report.txt`

This is NOT a smoke test. The observation requires real elapsed time. The user must re-enter the agent prompt at T1 (1h), T2 (4h), and T3 (24h).

---

## T1 Prompt (run AFTER 2026-06-01T17:05:41Z, i.e., >= 60 min after T0)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<agent_prompt>
  <role>Hermes running T1 (1h) stability checkpoint.</role>
  <mission>Verify lockdown integrity has survived 1 real hour.</mission>
  <mode>READ_ONLY</mode>
  <hard_rules>
    <rule>Do not modify anything.</rule>
    <rule>Do not run deploy.</rule>
    <rule>Do not restart anything.</rule>
  </hard_rules>
  <instruction>
    Run the T1 checkpoint:
    python3 /home/hermes/projects/trading/orchestrator/scripts/observation_checkpoint.py T1

    Then load the T0 baseline:
    cat /home/hermes/projects/trading/orchestrator/state/observation-24h/T0-20260601-1605/report.txt

    Compare T1 vs T0. Report:
    1. Permission drift (root-owned files, mode changes)
    2. Script drift (Git vs runtime)
    3. State file mtimes (must have advanced)
    4. jobs.json status field changes
    5. Container health changes
    6. Bot dry_run status

    Final classification: LOCKDOWN_STABLE, OBSERVABILITY_WARNING, or BROKEN.

    Write report to:
    docs/context/hermes-real-24h-stability-observation-20260601-T1.md
  </instruction>
</agent_prompt>
```

## T2 Prompt (run AFTER 2026-06-01T20:05:41Z, i.e., >= 4h after T0)

Same structure as T1, replace `T1` → `T2` and filename accordingly.

## T3 Prompt (run AFTER 2026-06-02T16:05:41Z, i.e., >= 24h after T0)

Same structure as T1, replace `T1` → `T3`.

T3 is the **only** checkpoint allowed to classify `LOCKDOWN_STABLE` or `READY_FOR_PRODUCTION`. Until then, status remains `READY_FOR_REAL_24H_OBSERVATION`.

---

## Pre-Built Comparison Helper

The user can also run this between checkpoints to see drift since T0:

```bash
diff -u /home/hermes/projects/trading/orchestrator/state/observation-24h/T0-20260601-1605/baseline.txt \
        /home/hermes/projects/trading/orchestrator/state/observation-24h/TX-<ts>/report.txt
```

---

## Final Verdict Rules

| Elapsed Time | Verdict Allowed |
|--------------|-----------------|
| < 1h | READY_FOR_REAL_24H_OBSERVATION (only) |
| 1h–4h | PENDING_T2 |
| 4h–24h | PENDING_T3 |
| >= 24h, all checks pass | LOCKDOWN_STABLE |
| >= 24h, but jobs.json status fields still stale | OBSERVABILITY_WARNING (not LOCKDOWN_FAILURE) |
| Any time, root ownership re-appeared | BROKEN_PERMISSION_DRIFT |
| Any time, script drift re-appeared | BROKEN_SCRIPT_DRIFT |

The verdict `READY_FOR_PRODUCTION` requires >= 24h elapsed AND all 11 required containers running AND all 4 bots `dry_run=True` AND zero script drift AND zero permission drift.
