# Live Strategy Mutation Approval Ceremony

**Status:** Design Document — No Implementation
**Date:** 2026-06-15
**Issue:** #28
**Parent:** #15 (Master Roadmap)

## Objective

Design the strict approval ceremony required before any future live strategy mutation can even be considered. This builds on the existing sandbox-only strategy mutation system.

## Dependencies

- #17 — Controlled read-only runtime probe
- #22 — Strategy mutation sandbox (establishes test-only mutation)
- #26 — Cron activation ceremony (PR #70, defines activation guardrails)

## 1. Preconditions

All of the following must be true before a live mutation ceremony can begin:

| Precondition | Verification |
|-------------|--------------|
| Controller PAUSED | Check STATE.json `active_item == null` |
| Queue empty | Check QUEUE.json has no pending work |
| Baseline reconciled | Main includes all merged PRs |
| Kill-switch active | EMERGENCY mode verified functional |
| Backups current | Docker volumes, configs, DBs backed up |
| Dry-run observation stable | 7 days of dry-run without regression |

## 2. Ceremony Steps

### Phase A — Preparation (Read-Only)

1. **Backup current state**
   - Back up `docker-compose.yml`, all strategy files, Freqtrade DBs
   - Record current trade state for all 4 bots
   - Tag git state: `git tag pre-live-mutation-<date>`

2. **Create candidate strategy**
   - Branch from main: `feat/live-mutation-candidate`
   - Make strategy changes in sandbox
   - Run full test suite: `pytest tests/ -q` (green required)

3. **Independent review**
   - Another operator reviews the diff
   - Safety checklist: no `dry_run=false`, no exchange creds, no API key changes

### Phase B — Validation (Dry-Run Only)

4. **Shadow mode deployment**
   - Deploy candidate strategy to canary bot only (freqforge-canary)
   - Run 48 hours of dry-run observation
   - Compare performance vs. baseline: no regression in win rate, drawdown, ROI

5. **Walk-forward analysis**
   - Run walk-forward optimization on candidate
   - Result must be within 5% of baseline expected return

### Phase C — Approval

6. **Human approval gate**
   - All Phase A+B evidence reviewed
   - Explicit token: `APPROVE_LIVE_MUTATION_CANDIDATE`
   - Two-person rule: two different operators must approve

7. **Rollback plan documented**
   - Exact commands to revert to previous strategy
   - Expected recovery time: < 5 minutes
   - Tested on canary first

### Phase D — Deployment (If Approved)

8. **Deploy to canary**
   - Switch canary to candidate strategy
   - 24-hour observation period with EMERGENCY kill-switch armed

9. **Deploy to fleet**
   - Roll out in order: canary → regime-hybrid → freqforge → rebel
   - 1-hour observation between each
   - Abort at any sign of regression

## 3. Abort Criteria

The ceremony must be aborted immediately if:

- CI fails on candidate branch
- Canary shows >2% drawdown increase
- Any bot becomes unreachable during deployment
- Kill-switch activates autonomously
- Human operator issues `ABORT_LIVE_MUTATION` command

## 4. Rollback / No-Op Plan

- **Rollback command:** `docker compose restart <bot>` with previous config
- **No-op:** If any precondition fails, the ceremony never starts
- **Recovery time:** < 5 minutes per bot
- **Data loss:** None (trades are preserved in SQLite DB)

## 5. Security Rules

- No cron/scheduler automation of any ceremony step
- No automatic approval — every gate requires human token
- All ceremony steps logged to ShadowLogger
- Approval tokens expire after 24 hours
- Failed ceremony blocks retry for 72 hours

## Safety Guarantees

- No live strategy mutation without explicit human approval
- No automatic deployment path
- All changes gated behind `LIVE_MUTATION_ENABLED=false` default
- Controller remains PAUSED throughout design
