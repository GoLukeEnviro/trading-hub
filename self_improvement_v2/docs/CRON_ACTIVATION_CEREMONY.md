# Cron Activation Ceremony & jobs.json Guardrails

> **Design document — NO activation in this phase.**
> Defines the preconditions, ceremony, guardrails, validation checklist, and
> rollback plan for activating SI v2 cron jobs.

**Status:** Ratified  
**Date:** 2026-06-10  
**Author:** SI v2 Meta-Orchestrator  
**Issue:** [#26 — Design cron activation ceremony and jobs.json guardrails](https://github.com/GoLukeEnviro/trading-hub/issues/26)

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Activation Preconditions](#2-activation-preconditions)
3. [Candidacy Levels](#3-candidacy-levels)
4. [Activation Ceremony Steps](#4-activation-ceremony-steps)
5. [Validation Checklist](#5-validation-checklist)
6. [Abort Conditions](#6-abort-conditions)
7. [Rollback Plan](#7-rollback-plan)
8. [Security Rules](#8-security-rules)
9. [Related Documents](#9-related-documents)

---

## 1. Purpose

This document defines the **activation ceremony** for SI v2 cron jobs.
The ceremony ensures that no cron job is activated without:

- Explicit human approval
- Validated safety preconditions
- Backup/rollback capability
- Post-activation monitoring

> ⚠️ **No activation in this phase.** All cron definitions remain in
> `cron_defs/` as inactive YAML files until separately approved.

---

## 2. Activation Preconditions

ALL preconditions MUST be satisfied before any cron activation ceremony
can begin:

### 2.1 Platform Preconditions

- [ ] All 450+ SI v2 tests pass on the target branch
- [ ] RiskGuard safety contract is ratified (#22)
- [ ] ShadowLogger is deployed and writable
- [ ] All bots are confirmed `dry_run=True` (verified within last 24h)
- [ ] No open blockers in Phase 0 tracker (#48)
- [ ] Hermes cron scheduler is running and accepting jobs
- [ ] jobs.json file exists and is writable

### 2.2 Human Preconditions

- [ ] Explicit written approval from Luke in a GitHub Issue or PR comment
- [ ] Approval references this design document
- [ ] Activation scope is clearly defined (which jobs, which bots)
- [ ] Rollback plan is reviewed and acknowledged

### 2.3 Job-Specific Preconditions

Each job to be activated must additionally satisfy:

- [ ] Job YAML file is in `cron_defs/` with complete schema
- [ ] Job has been tested in dry-run mode (at least 3 successful cycles)
- [ ] Job's prompt/script contains no live trading commands
- [ ] Job's prompt/script references no secrets
- [ ] Job's expected output size is bounded (< 10KB per run)
- [ ] Job timeout is defined and reasonable (< 5 minutes)
- [ ] Job failure behavior is documented (alert vs. silent retry)

---

## 3. Candidacy Levels

Every SI v2 cron job SHALL be classified into one of four levels:

| Level | Name | Meaning | Activation Authority |
|-------|------|---------|---------------------|
| L0 | Draft | YAML exists in `cron_defs/`, not tested | No activation possible |
| L1 | Tested | Passed 3+ dry-run cycles | May be activated with approval |
| L2 | Active | Currently running in production | Must be monitored |
| L3 | Paused | Previously active, now suspended | May be re-activated without full ceremony |

### Transition Rules

```
L0 (Draft) ──test──▶ L1 (Tested) ──approve──▶ L2 (Active)
L2 (Active) ──suspend──▶ L3 (Paused)
L3 (Paused) ──re-activate──▶ L2 (Active)
```

- L0→L1: Requires only technical validation (test passes)
- L1→L2: Requires full activation ceremony (this document)
- L2→L3: Requires documented reason for suspension
- L3→L2: Requires abbreviated ceremony (validation checklist only, no re-approval)

---

## 4. Activation Ceremony Steps

### Step 1: Preflight (automated)

```bash
# 1. Backup current jobs.json
cp /opt/data/profiles/orchestrator/jobs.json \
   /opt/data/profiles/orchestrator/jobs.json.bak.$(date +%Y%m%dT%H%M%S)

# 2. Validate jobs.json syntax
python3 -c "import json; json.load(open('/opt/data/profiles/orchestrator/jobs.json'))"

# 3. Check no duplicate job IDs
python3 -c "
import json
jobs = json.load(open('/opt/data/profiles/orchestrator/jobs.json'))
ids = [j['id'] for j in jobs]
assert len(ids) == len(set(ids)), f'Duplicate IDs: {ids}'
print(f'OK: {len(jobs)} jobs, no duplicates')
"

# 4. Dry-run: print what would be written
echo "Would add: <job_id> (<schedule>)"
```

### Step 2: Approval (human)

```
Request:  Activate job <job_id> with schedule <cron_expression>
Scope:    <bot_ids affected>
Risk:     <risk assessment from RiskGuard>
Rollback: <rollback plan reference>

Approval: Erlaubt / Nicht erlaubt
Token:    APPROVE_CRON_ACTIVATE_<JOB_ID>_<DATE>
```

### Step 3: Activation (automated, with approval token)

```bash
# 1. Copy backup as safety checkpoint
cp jobs.json.bak jobs.json.pre-activate

# 2. Add job entry to jobs.json
#    (use JSON manipulation, not sed)
python3 -c "
import json
jobs = json.load(open('jobs.json.pre-activate'))
jobs.append({
    'id': '<job_id>',
    'schedule': '<cron_expression>',
    'command': '...',
    'enabled': False,   # ← DISABLED by default!
    ...
})
json.dump(jobs, open('jobs.json', 'w'), indent=2)
"

# 3. Validate final jobs.json
python3 -c "import json; json.load(open('jobs.json'))"

# 4. Enable only if explicitly approved
#    (separate command, not automatic)
```

### Step 4: Enabling (separate approval)

Jobs are activated in **disabled** state. A second explicit approval is
required to enable them:

```bash
# Enable job only after 1h observation of the disabled entry
python3 -c "
import json
jobs = json.load(open('jobs.json'))
for j in jobs:
    if j['id'] == '<job_id>':
        j['enabled'] = True
json.dump(jobs, open('jobs.json', 'w'), indent=2)
"
```

### Step 5: Observation (post-activation)

After enabling, the job runs for **3 cycles** under observation:

- [ ] Cycle 1: Verify job starts, completes, produces expected output
- [ ] Cycle 2: Verify no side effects on trading bots
- [ ] Cycle 3: Verify ShadowLogger entries are generated
- [ ] After 3 cycles: Confirm job is stable, mark as L2 Active

---

## 5. Validation Checklist

Run this checklist before and after every activation:

### Pre-Activation

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 1 | git status clean | `git status --short` | No unintended changes |
| 2 | Current jobs.json valid | `python3 -c "import json; json.load(open('...'))"` | No error |
| 3 | No duplicate IDs | See Step 1 | No duplicates |
| 4 | Backup exists | `ls *.bak.*` | Backup file present |
| 5 | All bots dry-run | `docker ps --format '{{.Names}}'` | No live bot detected |
| 6 | tests pass | `pytest -q` | 456+ passed |

### Post-Activation

| # | Check | Expected |
|---|-------|----------|
| 1 | jobs.json unchanged except for new job | `git diff` shows only intended change |
| 2 | New job appears in `hermes cron list` | Job listed |
| 3 | New job is disabled | `enabled: false` |
| 4 | Hermes scheduler is still running | Process active |
| 5 | No error logs generated | `grep ERROR scheduler.log` empty |

---

## 6. Abort Conditions

The ceremony MUST be aborted immediately if ANY of these conditions occur:

| Condition | Action | Classification |
|-----------|--------|---------------|
| jobs.json is malformed after edit | Restore from backup, abort | `RED` |
| Duplicate job ID detected | Restore from backup, abort | `RED` |
| Scheduler crashes during activation | Restore from backup, restart scheduler | `RED` |
| Job activates with `enabled: true` accidentally | Disable immediately, restore from backup | `RED` |
| Backup file cannot be created | Abort — do not proceed | `RED` |
| Test suite fails during preflight | Abort — fix tests first | `YELLOW` |
| Any bot detected in non-dry-run mode | Abort immediately, escalate | `RED` |
| Activation produces unexpected side effects | Pause all SI v2 cron jobs, restore | `RED` |

---

## 7. Rollback Plan

### 7.1 Rollback Steps

```bash
# 1. Disable the offending job
python3 -c "
import json
jobs = json.load(open('jobs.json'))
for j in jobs:
    if j['id'] == '<job_id>':
        j['enabled'] = False
json.dump(jobs, open('jobs.json', 'w'), indent=2)
"

# 2. Verify it stopped
hermes cron list | grep <job_id>
# Should show: disabled

# 3. If jobs.json is corrupt, restore from backup
cp /opt/data/profiles/orchestrator/jobs.json.bak.<timestamp> \
   /opt/data/profiles/orchestrator/jobs.json

# 4. Restart Hermes scheduler if needed
#    (requires Docker restart approval — separate issue)
```

### 7.2 Rollback Verification

- [ ] Offending job is disabled
- [ ] All other jobs are unaffected
- [ ] No orphaned processes
- [ ] ShadowLogger recorded the rollback event
- [ ] docs/context/ updated with rollback report

---

## 8. Security Rules

1. **No auto-enable** — jobs are always activated in disabled state.
2. **No auto-approval** — enable requires separate human approval.
3. **Backup first** — never edit jobs.json without a timestamped backup.
4. **Validation every step** — validate after every mutation.
5. **No secrets in jobs** — job definitions must never contain tokens,
   API keys, or passwords.
6. **No recursive scheduling** — jobs must never schedule other jobs.
7. **Bounded output** — jobs must limit output (default < 10KB).
8. **Fail-closed** — if any precondition fails, activation is blocked.

---

## 9. Related Documents

| Document | Location | Relationship |
|----------|----------|-------------|
| SI v2 Cron Definitions | `self_improvement_v2/cron_defs/` | Job YAML files |
| SI v2 Cron Planner | `src/si_v2/cron/planner.py` | Cron schedule generation |
| SI v2 Cron CLI | `src/si_v2/cron/cli.py` | Cron management CLI |
| Runtime Safety Contract | `docs/specs/runtime-safety-contract.md` | Fail-closed policy |
| V1-to-V2 Cron Migration | `self_improvement_v2/docs/V1_TO_V2_CRON_MIGRATION.md` | Migration plan |
| ORCHESTRATOR_CHARTER.md | `ORCHESTRATOR_CHARTER.md` | Operating rules |
