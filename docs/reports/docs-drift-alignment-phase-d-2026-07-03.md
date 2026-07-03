# Docs Drift Alignment Phase D — 2026-07-03

## Scope

L3/Hygiene Follow-up Issues — create separate, well-scoped issues for all
remaining findings from the Docs-Drift Campaign that require runtime, config,
security, or cleanup changes beyond docs-only L2.

Trigger: GitHub Issue #457 Phase D.

## Action

No files changed. No runtime, Docker, Cron, Freqtrade config, strategy,
pair expansion, or live trading changes. **Issues only.**

## Issues Created

| # | Title | Scope | Labels | Key Evidence |
|---|-------|-------|--------|-------------|
| #461 | primo_signal_state.json mount and primo_gate_allows investigation | L3 | L3, security, follow-up | 7 copies, 4 Compose mounts, 12 consumer files |
| #462 | P3 Freqtrade JSON credential migration and config cleanup | L3 | L3, security, follow-up | 5+ config.json with exchange blocks, backup snapshots |
| #463 | Cron and script hygiene — duplicate watchdog, stale references, SI-v1 residue | L2 | hygiene, follow-up | ledger_watchdog.py × 2, run_analyze.sh, SI-v1 backups |
| #464 | Backup and temp file cleanup — 8,719 untracked .bak/.tmp files | L2 | hygiene, follow-up | 8,719 files, 0 tracked; hotspots in orchestrator/backups/, freqtrade/shared/ |
| #465 | Remove stale tests for decommissioned bridge/primo/intelligence code | L2 | hygiene, follow-up | 4 test files + __pycache__ artifacts |
| #466 | SHARED_CONSTANTS.py missing import os | L2 | hygiene, follow-up | Uses os.path.join() without import os |
| #467 | Remote branch hygiene — 387 stale branches | L2 | hygiene, follow-up | 387 remote branches, many merged |

## Source of truth used

1. `docs/state/current-operational-state.md` — canonical runtime snapshot
2. GitHub Issue #423 — canonical live roadmap
3. Phase A/B/C alignment reports and validation outputs
4. File system scan: `find`, `grep`, `git ls-files`, `git branch -r`

## Validation

All issues include:
- Akzeptanzkriterien (acceptance criteria)
- Risiko assessment
- Scope Level (L2/L3)
- Validation commands
- Rollback / Non-goals
- Dependency and Related links

## Campaign Completion Status

| Phase | PR/Issue | Files/Issues | Status |
|-------|----------|-------------|--------|
| A — Critical autonomy drift | #458 | 5 files | ✅ Merged |
| B — Stale state/decisions/roadmap | #459 | 16 files | ✅ Merged |
| C — Structure, glossary, register | #460 | 5 files | ✅ Merged |
| D — L3/Hygiene follow-up issues | #461–#467 | 7 issues | ✅ Created |

**Total campaign output:**
- 3 PRs merged (#458, #459, #460)
- 26 files changed (+753, -152)
- 7 follow-up issues created (#461–#467)
- 4 new documentation files (glossary, decommissioning register, 2 reports)
- 11 SUPERSEDED markers applied to stale docs
- CI cleanup: decommissioned paths removed from .coveragerc and main-gate.yml

## Remaining work (outside #457)

The 7 follow-up issues (#461–#467) are tracked independently. #457 can be
closed once all Phase D issues are confirmed tracked and the campaign report
is accepted.

## Safety statement

No runtime mutation.
No Docker/Cron/Scheduler changes.
No Freqtrade config changes.
No strategy changes.
No live trading.
No pair expansion.
Issues-only — no code changes.
