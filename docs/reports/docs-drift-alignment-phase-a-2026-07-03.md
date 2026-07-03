# Docs Drift Alignment Phase A — 2026-07-03

## Scope

Critical SI-v2 documentation drift closure — align 4 files with current
AUTONOMOUS_DRY_RUN mode, C4 ROLLBACK_RECOMMENDED state, and D1 BLOCKED posture.

Trigger: GitHub Issue #457, read-only audit 2026-07-03.

## Files changed

| File | Lines (before) | Lines (after) | Nature of change |
|------|---------------|---------------|------------------|
| `self_improvement_v2/README.md` | 333 | 378 | Substantial rewrite — removed HUMAN_GATED claims, added Track A/B/C module map, fleet rollout chain, canary history |
| `CHANGELOG.md` | 174 | 288 | Retro-fill — added dated entries for 2026-06-27 through 2026-07-03 (Track A/B/C, C4 ROLLBACK, backlog hygiene) |
| `docs/ARCHITECTURE.md` | 210 | 248 | Substantial rewrite — updated data flow, controller state machine, component table, kill switch status, added decommissioned section |
| `docs/state/si-v2-capability-matrix.md` | 163 | 226 | Complete rebuild — new track-based structure, all 71 components documented, historical scoring gate section preserved |
| `docs/reports/docs-drift-alignment-phase-a-2026-07-03.md` | — | 87 | New — this report |

## Source of truth used

1. `docs/state/current-operational-state.md` — canonical runtime snapshot (2026-07-01)
2. GitHub Issue #423 — canonical live roadmap (Tracks A/B/C complete, D1 BLOCKED)
3. GitHub Issue #457 — docs drift scope and decision matrix
4. `docs/decisions/ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md`
5. `docs/architecture/si-v2-autonomous-dry-run-loop.md` — SI-v2 detail architecture
6. Git history: PRs #379–#455 (merged commits on main)

## Stale claims removed

| Claim | File | Lines | Replacement |
|-------|------|-------|-------------|
| `Autonomous apply is **not** in scope` | self_improvement_v2/README.md | 32-33 | AUTONOMOUS_DRY_RUN mode description with ADR reference |
| `Controller is HUMAN_GATED_CANARY_APPLY_PHASE_1` | self_improvement_v2/README.md | 214-215 | AUTONOMOUS_DRY_RUN safety constraint |
| `All mutating operations remain: Human-gated` | self_improvement_v2/README.md | 320-324 | Policy-gated autonomous dry-run description |
| `T2: PENDING`, `T3: PENDING`, `Final Decision: PENDING` | self_improvement_v2/README.md | 329-331 | Actual results: T0 GREEN, T1 YELLOW, T2 YELLOW, T3 YELLOW/EXTEND, Final KEEP_CANARY_OVERLAY |
| `SI v2 Controller PAUSED` | docs/ARCHITECTURE.md | 43, 120, 147-151, 182 | AUTONOMOUS_DRY_RUN with state diagram |
| `L3_REPOSITORY_ONLY as current` | docs/ARCHITECTURE.md | 149 | AUTONOMOUS_DRY_RUN policy |
| `Runtime: FORBIDDEN as current` | docs/ARCHITECTURE.md | 151 | Policy-gated canary-first |
| `27 cycles / 108 points / scoring gate 0/10` | docs/ARCHITECTURE.md | 125-129 | Removed volatile counters, reference to canonical state |
| `Kill Switch PENDING (#220)` | docs/ARCHITECTURE.md | 170 | Kill Switch DEPLOYED — NORMAL |
| Controller PAUSED in observation loop | docs/ARCHITECTURE.md | 120 | AUTONOMOUS_DRY_RUN flow with deploy gate |
| `producer freshness is the remaining gate` | si-v2-capability-matrix.md | entire section | Historical section with current state note |
| `grounded at commit 266a930, 2026-06-16` | si-v2-capability-matrix.md | header | Updated to commit 32a4804, 2026-07-03 |
| CHANGELOG stale since 2026-06-15 | CHANGELOG.md | entire file | Retro-filled through 2026-07-03 |

## Stale claims intentionally preserved as historical

| Claim | File | Context |
|-------|------|---------|
| `HUMAN_GATED_CANARY_APPLY_PHASE_1` mention | self_improvement_v2/README.md | "Historical note" paragraph — superseded for dry-run |
| `HUMAN_GATED_CANARY_APPLY_PHASE_3C` mention | self_improvement_v2/README.md | Historical note paragraph |
| Rainbow scoring gate 0/10 | si-v2-capability-matrix.md | "Historical: Rainbow Scoring Gate" section — explicitly marked historical |
| PR #215 era metrics (27 cycles, 108 points) | CHANGELOG.md | In [2026-06-14] dated entry — correct for that date |
| PR #215 scoring gate description | CHANGELOG.md | In [2026-06-14] dated entry — correct for that date |
| `PAUSED / L3_REPOSITORY_ONLY` | CHANGELOG.md | In [2026-06-15] entry — marked *(superseded by ADR-2026-07-01)* |
| Controller state machine PAUSED→QUEUE→ACTIVE | docs/ARCHITECTURE.md | Removed entirely; replaced with AUTONOMOUS_DRY_RUN state diagram |

## Validation commands

```bash
# Compile check
python -m compileall -q self_improvement_v2 orchestrator tests scripts
# Result: (no output = clean)

# Tests
python -m pytest self_improvement_v2/tests -q
# Result: 0 tests collected (this is expected — SI-v2 tests use src/ layout)
# Corrected:
cd self_improvement_v2 && python3 -m pytest src/ -q 2>&1 | tail -5

# Ruff
ruff check self_improvement_v2/src self_improvement_v2/tests
# Result: (will be checked below)
```

## Results

Validation will be run after commit and before push. Expected: all clean
(docs-only changes should not affect Python compilation or tests).

## Remaining follow-ups

### Phase B (docs consistency, separate PR)

- `AGENTS.md:166-172` — Mark Primo/Bridge endpoints as historical
- `README.md:74-77,127-130` — Mark bridge/, primo/, intelligence/ as decommissioned
- `.coveragerc:8-10` — Remove decommissioned source paths
- `.github/workflows/main-gate.yml:43-47` — Remove decommissioned compileall targets
- `docs/plans/phase-2-1-autonomous-dry-run-dod.md` — Mark superseded
- `docs/backlog/si-v2-self-improvement-next-iteration.md` — Mark closed
- `docs/GAP-REPORT-2026-06-15-TRADING-HUB.md` — Mark superseded
- `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md` — Mark superseded
- `docs/decisions/README.md` — Complete ADR/approval-marker index
- `docs/specs/*.md` — Fix stale `emergency_stop.sh MISSING` claims

### Phase C (documentation structure, separate PR)

- Create `docs/glossary.md`
- Create `docs/decommissioning-register.md`
- Update `docs/README.md` with cross-links
- Link skill roadmap from docs index

### L3 Follow-up Issues (separate from #457)

1. `primo_signal_state.json` mounts — evaluate `primo_gate_allows()` before compose change
2. P3 Security — Freqtrade JSON credential migration
3. Cron/script hygiene — ledger_watchdog, si_regime_hybrid_analyze.sh, SI-v1 leftovers
4. Root `.bak` / backup cleanup
5. `freqtrade/shared/*.bak*` and `.tmp-*` cleanup
6. `SHARED_CONSTANTS.py` missing `import os`
7. `test_bridge_primo_intelligence_phase4.py` — stale test for decommissioned code

## Safety statement

No runtime mutation.
No Docker/Cron/Scheduler changes.
No Freqtrade config changes.
No strategy changes.
No live trading.
No pair expansion.
Docs-only L2.
