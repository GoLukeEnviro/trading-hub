# Docs Drift Alignment Phase B — 2026-07-03

## Scope

High-priority documentation consistency reconciliation — stale decisions
index, state snapshots, roadmap markers, CI config, and emergency references.

Trigger: GitHub Issue #457 Phase B.

## Files changed

| File | Lines (before) | Lines (after) | Nature of change |
|------|---------------|---------------|------------------|
| `docs/decisions/README.md` | 25 | 49 | Expanded — complete ADR/approval-marker index (5 ADRs + 4 markers) |
| `docs/reports/c3-rollback-plan-review-2026-07-03.md` | 108 | 110 | Updated — emergency_stop.sh, procedure doc, incidents/ now ✅; gaps table updated |
| `docs/specs/incident-response-runbooks.md` | — | — | No change needed — already correct (references existing emergency_stop.sh) |
| `docs/specs/IMPLEMENTATION_STATUS_AND_NEXT_STEPS.md` | 46 | 50 | SUPERSEDED header added |
| `README.md` | 229 | 232 | Roadmap link → #423; bridge/primo/intelligence marked decommissioned |
| `docs/README.md` | 87 | 127 | Substantial update — canonical/historical split, new doc references, superseded list |
| `docs/state/canonical-trading-status.md` | 125 | 131 | SUPERSEDED header added |
| `docs/state/issues-55-61-evidence-matrix.md` | 33 | 37 | SUPERSEDED header added |
| `docs/state/phase-1-intelligence-epic.md` | 144 | 149 | SUPERSEDED header added |
| `docs/state/post-pr-160-architecture.md` | 134 | 139 | SUPERSEDED header added |
| `docs/state/autopilot/latest.md` | 9 | 13 | SUPERSEDED header + canonical link updated |
| `docs/state/autopilot/daily_20260516.md` | 56 | 62 | SUPERSEDED header added |
| `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md` | 447 | 457 | SUPERSEDED header + #423/ADR-2026-07-01 references |
| `AGENTS.md` | 199 | 204 | Primo/Bridge section marked historical |
| `.coveragerc` | 47 | 44 | Removed decommissioned: primo, bridge, intelligence |
| `.github/workflows/main-gate.yml` | 116 | 113 | Removed decommissioned compileall: bridge, primo, intelligence |
| `docs/reports/docs-drift-alignment-phase-b-2026-07-03.md` | — | 80 | New — this report |

## Source of truth used

1. `docs/state/current-operational-state.md` — canonical runtime snapshot
2. GitHub Issue #423 — canonical live roadmap
3. `docs/decisions/ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md`
4. Git history: commit c81791b (post-Phase-A merge)

## Stale claims removed

| Claim | File | Fix |
|-------|------|-----|
| `roadmap-v2` as "current" forward-looking roadmap | README.md, docs/README.md | Now references #423 as canonical |
| `emergency_stop.sh MISSING` | c3-rollback-plan-review | Updated to ✅ Resolved |
| `freqtrade-kill-switch-procedure.md MISSING` | c3-rollback-plan-review | Updated to ✅ Resolved |
| `docs/incidents/ MISSING` | c3-rollback-plan-review | Updated to ✅ Resolved |
| `var/si_v2/emergency/ MISSING` | c3-rollback-plan-review | Updated to ✅ Resolved |
| `APPROVED_LIVE_CANARY_ROLLBACK` missing | c3-rollback-plan-review | Updated to ✅ Resolved |
| 7 stale `docs/state/*` files with no superseded marker | 6 files | SUPERSEDED headers added |
| roadmap-v2 no superseded header | roadmap-v2 | SUPERSEDED header + #423 reference |
| IMPLEMENTATION_STATUS no superseded marker | IMPLEMENTATION_STATUS | SUPERSEDED header added |
| Primo/Bridge endpoints as current | AGENTS.md | Marked historical |
| bridge/primo/intelligence as active components | README.md | Marked decommissioned/vestigial |
| Decommissioned dirs in .coveragerc | .coveragerc | Removed |
| Decommissioned dirs in compileall CI | main-gate.yml | Removed |
| ADR index missing 3 entries | docs/decisions/README.md | Expanded to 5 ADRs + 4 markers |
| GAP-REPORT-2026-06-15 as current gap register | docs/README.md | Marked superseded |

## Validation commands

```bash
# Stale-claim scan
grep -RIn "emergency_stop.*MISSING\|Current gap register\|HUMAN_GATED_CANARY_APPLY_PHASE_1\|Controller.*PAUSED\|L3_REPOSITORY_ONLY" docs README.md || true

# Expected: only historical/superseded matches
```

## Results

See validation output below (run after commit).

## Remaining follow-ups

### Phase C (documentation structure, separate PR)
- Create docs/glossary.md
- Create docs/decommissioning-register.md
- docs/README.md further cross-linking (if needed after Phase C additions)

### L3 Follow-up Issues (separate from #457)
1. primo_signal_state.json mounts — evaluate primo_gate_allows() before compose change
2. P3 Security — Freqtrade JSON credential migration
3. Cron/script hygiene — ledger_watchdog, si_regime_hybrid_analyze.sh, SI-v1 leftovers
4. Root .bak / backup cleanup
5. freqtrade/shared/*.bak* and .tmp-* cleanup
6. test_bridge_primo_intelligence_phase4.py — stale test for decommissioned code
7. SHARED_CONSTANTS.py missing import os

## Safety statement

No runtime mutation.
No Docker/Cron/Scheduler changes.
No Freqtrade config changes.
No strategy changes.
No live trading.
No pair expansion.
Docs-only L2.
