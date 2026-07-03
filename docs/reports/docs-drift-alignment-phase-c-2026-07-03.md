# Docs Drift Alignment Phase C — 2026-07-03

## Scope

Documentation structure layer — glossary, decommissioning register, docs index
cross-links, and tools documentation coverage.

Trigger: GitHub Issue #457 Phase C.

## Files changed

| File | Lines (before) | Lines (after) | Nature of change |
|------|---------------|---------------|------------------|
| `docs/glossary.md` | — | 155 | New — canonical glossary (35 terms across 4 categories) |
| `docs/decommissioning-register.md` | — | 88 | New — decommissioned components, CI cleanup, stale test tracking |
| `docs/README.md` | 107 | 139 | Updated — glossary, decommissioning-register, architecture subdir cross-links |
| `tools/README.md` | 156 | 172 | Updated — freqforge/ and riskguard/ sections added |
| `docs/reports/docs-drift-alignment-phase-c-2026-07-03.md` | — | 74 | New — this report |

## Source of truth used

1. `docs/state/current-operational-state.md` — canonical runtime snapshot
2. GitHub Issue #423 — canonical live roadmap
3. `docs/decisions/ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md`
4. Phase A and Phase B alignment reports
5. Git history: commit 6a9d466 (post-Phase-B merge)

## New content

### docs/glossary.md

**35 terms** organized in 4 categories:

| Category | Terms | Key entries |
|----------|-------|-------------|
| SI-v2 System | 7 | AUTONOMOUS_DRY_RUN, ShadowProposal, RuntimeEffectProof, Measurement Decision, KEEP_CANARY_OVERLAY, ROLLBACK_RECOMMENDED |
| Safety Components | 5 | RiskGuard, ShadowLogger, Kill Switch, HALT_NEW, EMERGENCY |
| Fleet & Deployment | 3 | Canary, Control Bot, Freqtrade Fleet |
| Governance | 7 | L2, L3, Approval Marker, Live Target Architecture, LIVE_FORBIDDEN, LIVE_APPROVED, D1 |
| Deprecated | 3 | HUMAN_GATED_CANARY_APPLY_PHASE_1, PAUSED/L3_REPOSITORY_ONLY, Primo/Bridge |

All terms include cross-references to canonical source files.

### docs/decommissioning-register.md

**8 decommissioned components** tracked:
- PrimoAgent, Bridge, Intelligence layer, SI-v1 Controller, Autopilot, Momentum bot, MVS bot, RSI bot

**6 CI/cleanup paths** documented:
- bridge/, primo/, intelligence/ removed from .coveragerc and main-gate.yml (Phase B, PR #459)

**Stale test candidates** and **L3 cleanup items** listed with scope/blocker.

### docs/README.md updates

- Glossary and Decommissioning Register promoted to top of canonical docs section
- `architecture/` subdirectory documented
- `tools/README.md` added to additional entry points
- GitHub Issue #423 link added to canonical list
- `decisions/README.md` cross-referenced for ADR/approval marker lookup
- "How to use" section expanded with glossary/decommissioning/decisions guidance

### tools/README.md updates

- `freqforge/` shadow evaluator section added
- `riskguard/` utilities section added

## Validation commands

```bash
# Verify new files exist
ls -la docs/glossary.md docs/decommissioning-register.md

# Verify cross-links resolve
grep -c "docs/glossary.md" docs/README.md README.md
grep -c "docs/decommissioning-register.md" docs/README.md
grep -c "tools/README.md" docs/README.md
grep -c "freqforge/" tools/README.md
grep -c "riskguard/" tools/README.md
```

## Results

See validation output below (run after commit).

## Remaining follow-ups

### L3 Follow-up Issues (separate from #457)
1. primo_signal_state.json mounts — evaluate primo_gate_allows() before compose change
2. P3 Security — Freqtrade JSON credential migration
3. Cron/script hygiene — ledger_watchdog, si_regime_hybrid_analyze.sh, SI-v1 leftovers
4. Root .bak / backup cleanup
5. freqtrade/shared/*.bak* and .tmp-* cleanup
6. test_bridge_primo_intelligence_phase4.py — stale test for decommissioned code
7. SHARED_CONSTANTS.py missing import os

## Campaign summary

| Phase | PR | Files | Status |
|-------|----|-------|--------|
| A — Critical autonomy drift | #458 | 5 | ✅ Merged |
| B — Stale state/decisions/roadmap | #459 | 16 | ✅ Merged |
| C — Structure, glossary, register | #460 | 5 | 🔵 Open |
| D — L3 follow-up issues | — | — | ⬜ Pending (separate issues) |

## Safety statement

No runtime mutation.
No Docker/Cron/Scheduler changes.
No Freqtrade config changes.
No strategy changes.
No live trading.
No pair expansion.
Docs-only L2.
