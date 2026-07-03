# SI v2 — Capability Matrix

> **Grounded at commit `32a4804`** — after PR #455 (final roadmap reconciliation)
> on `main`, 2026-07-03.
>
> This matrix documents which SI v2 components are implemented, tested,
> and on what data path. No completion percentages are invented; every cell
> is backed by evidence in the repo.
>
> **Canonical runtime snapshot:** `docs/state/current-operational-state.md`
> **Live roadmap:** GitHub Issue #423
> **ADR pivot:** `docs/decisions/ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md`

---

## Legend

| Symbol | Meaning |
|--------|---------|
| 🟢 Implemented | Module exists on `main` with tests |
| 🟡 Partial | Implemented but with known gaps or restrictions |
| 🔴 Not implemented | Not yet built |
| ⬜ Blocked | Blocked by dependency |
| ❌ Decommissioned | Removed or superseded |

---

## Track Status

| Track | Scope | Status | PRs |
|-------|-------|--------|-----|
| A — SI-v2 Dry-Run Loop Closure | Phase 10.1–10.6 Fleet Rollout Chain | ✅ Complete | #421–#428 |
| B — Operational Readiness | Live Readiness Evidence, Risk Limits, Runbooks, Alerting | ✅ Complete | #429–#432 |
| C — Live Canary Transition | Approval Gate, Config Plan, Activation Ceremony, Measurement/Decision | ✅ Complete | #433–#437 |
| D — Live Fleet Rollout | D1 Approval Gate, D2 Staged Rollout | ⬜ Blocked | — |

### D1 Blockers

1. C4 decision: **ROLLBACK_RECOMMENDED** (max_drawdown_pct = 82.79% breach)
2. `APPROVED_LIVE_FLEET_ROLLOUT` marker: **missing**
3. No C4 KEEP decision artifact exists

---

## Capability Matrix

### Core Loop (`src/si_v2/loop/`)

| Component | Status | Tests | Evidence |
|-----------|--------|-------|----------|
| Active Cycle Runner (`active_cycle_runner.py`) | 🟢 Implemented | ✅ | Scheduled 6h cron, multiple runs on main |
| Cycle State (`cycle_state.py`) | 🟢 Implemented | ✅ | Used by all downstream modules |
| Fleet Analyzer (`fleet_analyzer.py`) | 🟢 Implemented | ✅ | Multi-bot health, drift, anomaly detection |
| Telemetry Normalizer (`telemetry_normalizer.py`) | 🟢 Implemented | ✅ | Uniform schema normalization |

### Measurement (`src/si_v2/measurement/`)

| Component | Status | Tests | Evidence |
|-----------|--------|-------|----------|
| Ledger (`ledger.py`) | 🟢 Implemented | ✅ | Append-only JSONL, production data |
| Build Measurement Ledger (`build_measurement_ledger.py`) | 🟢 Implemented | ✅ | Cycle state → ledger |
| Models (`models.py`) | 🟢 Implemented | ✅ | Pydantic measurement models |
| Report (`report.py`) | 🟢 Implemented | ✅ | Human-readable reports |
| Attribution (`attribution.py`) | 🟢 Implemented | ✅ | Source attribution |
| Decision Engine (`decision_engine.py`) | 🟢 Implemented | 37 | KEEP / EXTEND / ROLLBACK decisions |

### Rainbow Integration (`src/si_v2/rainbow/`)

| Component | Status | Tests | Evidence |
|-----------|--------|-------|----------|
| Client (`client.py`) | 🟢 Implemented | ✅ | Read-only HTTP client |
| Validator (`validator.py`) | 🟢 Implemented | ✅ | Schema validation |
| Drift Guard (`drift_guard.py`) | 🟢 Implemented | ✅ | Freshness/staleness detection |
| ShadowLock Events (`shadowlock_events.py`) | 🟢 Implemented | ✅ | Event integration |
| Status (`status.py`) | 🟢 Implemented | ✅ | Health reporting |
| Client Fixture Harness | 🟢 Implemented | ✅ | Test infrastructure |

**Rainbow scoring gate:** Historically 0/10 scoring-eligible cycles due to producer freshness.
No longer the primary SI-v2 blocker — autonomous dry-run loop operates independently
of Rainbow scoring (ADR-2026-07-01).

### Proposal (`src/si_v2/propose/`)

| Component | Status | Tests | Evidence |
|-----------|--------|-------|----------|
| Shadow Proposal (`shadow_proposal.py`) | 🟢 Implemented | ✅ | Proposal generation |
| Strategy Adapter | 🟢 Implemented | ✅ | Sandboxed strategy mutation |
| Weight Proposal | 🟢 Implemented | ✅ | Weight optimization |
| Proposal Scoring | 🟢 Implemented | ✅ | Scoring, policy, rejection |
| Similarity Checker | 🟢 Implemented | ✅ | Duplicate detection |

### Apply Chain (`src/si_v2/apply_actuator/`)

| Component | Phase | Status | Tests | PR |
|-----------|-------|--------|-------|----|
| Controlled Apply Actuator | 1 (historical) | 🟢 Implemented | ✅ | — |
| Autonomy Policy | — | 🟢 Implemented | ✅ | NEW |
| Restart with Overlay | 3B-A | 🟢 Implemented | 45 | #379 |
| Restart Gate | 3B-B | 🟢 Implemented | 23 | #380 |
| Runtime Executor | 3C-A | 🟢 Implemented | 23 | #381 |
| RuntimeEffectProof | 3C-B | 🟢 Implemented | ✅ | — |
| Candidate Pipeline | 6A | 🟢 Implemented | 36 | #384 |
| Rollback Rehearsal | 5A | 🟢 Implemented | 24 | #383 |

**First canary apply proven:** `max_open_trades 3→2` on `freqtrade-freqforge-canary`
— RuntimeEffectProof: **GREEN**, Decision: **KEEP_CANARY_OVERLAY** (2026-06-30).

### Fleet Rollout Chain (Track A, Phase 10.1–10.6)

| Component | Phase | Status | Tests | PR |
|-----------|-------|--------|-------|----|
| Fleet Rollout Input Resolver | 10.1 | 🟢 Implemented | 24 | #421 |
| READY-only Fleet Evidence Runner | 10.2 | 🟢 Implemented | 12 | #422 |
| Controlled Dry-Run Fleet Runtime Executor | 10.3 | 🟢 Implemented | 18 | #424 |
| Post-Fleet Measurement Watcher | 10.4 | 🟢 Implemented | 20 | #425 |
| Dry-Run Fleet Rollback Executor | 10.5 | 🟢 Implemented | ✅ | #427 |
| Next Iteration Selector | 10.6 | 🟢 Implemented | 19 | #428 |

### Live Readiness (Track B)

| Component | Status | Tests | PR |
|-----------|--------|-------|----|
| Live Readiness Evidence Audit | 🟢 Implemented | 14 | #429 |
| Production Risk Limits Spec | 🟢 Implemented | — | #430 |
| Incident Response & Go-Live Runbooks | 🟢 Implemented | — | #431 |
| Production Alerting Gate | 🟢 Implemented | 10 | #432 |

### Live Canary (Track C)

| Component | Status | Tests | PR |
|-----------|--------|-------|----|
| Human Approval Gate | 🟢 Implemented | 12 | #433 |
| Live Canary Config Plan | 🟢 Implemented | 17 | #434 |
| Live Canary Activation Ceremony | 🟢 Implemented | 27 | #436 |
| Live Canary Measurement & Decision | 🟢 Implemented | 42 | #437 |

**C4 Outcome (2026-07-03):** ROLLBACK_RECOMMENDED (max_drawdown 82.79% breach).
Validated by #438 triage. Human selected rollback path (#442).
Canary baseline return completed (#447). Post-return verification passed (#449).

### Adapters (`src/si_v2/adapters/`)

| Component | Status | Tests |
|-----------|--------|-------|
| Freqtrade Adapter (base) | 🟢 Implemented | ✅ |
| Freqtrade REST Read-Only | 🟢 Implemented | ✅ |
| Real Freqtrade Adapter | 🟢 Implemented | ✅ |
| Docker Adapter | 🟢 Implemented | ✅ |
| Telegram Adapter | 🟢 Implemented | ✅ |
| Call Budget | 🟢 Implemented | ✅ |
| Auth Resolver | 🟢 Implemented | ✅ |

### Deploy (`src/si_v2/deploy/`)

| Component | Status | Tests |
|-----------|--------|-------|
| Deployment Plan | 🟢 Implemented | ✅ |
| Rollback Plan | 🟢 Implemented | ✅ |
| ShadowLogger | 🟢 Implemented | ✅ |
| Shadow Mode | 🟢 Implemented | ✅ |

### Validation (`src/si_v2/validation/`)

| Component | Status | Tests |
|-----------|--------|-------|
| Validation Gates | 🟢 Implemented | ✅ |
| Decision Matrix | 🟢 Implemented | ✅ |
| Renderers | 🟢 Implemented | ✅ |

### Supporting Modules

| Package | Status |
|---------|--------|
| `attribution/` | 🟢 Implemented |
| `backtest/` | 🟢 Implemented |
| `config/` | 🟢 Implemented |
| `cron/` | 🟢 Implemented |
| `episode/` | 🟢 Implemented |
| `evidence/` | 🟢 Implemented |
| `integrations/ai4trade/` | 🟢 Implemented |
| `proofs/` | 🟢 Implemented |
| `regime/` | 🟢 Implemented |
| `reports/` | 🟢 Implemented |
| `runtime_probe/` | 🟢 Implemented |
| `signals/` | 🟢 Implemented |
| `state/` | 🟢 Implemented |
| `source_regime_stats/` | 🟢 Implemented |

---

## Historical: Rainbow Scoring Gate

The Rainbow scoring gate (10/10 consecutive scoring-eligible cycles) was the
primary SI-v2 blocker before the autonomous dry-run pivot.

**Historical state (2026-06-16):**
- 0 scoring-eligible cycles (DB-backed stub timestamps were stale)
- Producer freshness was the remaining gate

**Current state (2026-07-03):**
- Scoring gate is **no longer the primary blocker** for SI-v2 loop operation
- AUTONOMOUS_DRY_RUN mode operates independently of Rainbow scoring (ADR-2026-07-01)
- Rainbow remains as an optional signal enrichment source
- Producer freshness is a signal-quality concern, not a loop-gating concern

---

## Summary

| Domain | Total | Implemented | Partial | Blocked | Not Implemented |
|--------|-------|-------------|---------|---------|----------------|
| Core Loop | 4 | 4 | 0 | 0 | 0 |
| Measurement | 6 | 6 | 0 | 0 | 0 |
| Rainbow Integration | 6 | 6 | 0 | 0 | 0 |
| Proposal | 5 | 5 | 0 | 0 | 0 |
| Apply Chain | 8 | 8 | 0 | 0 | 0 |
| Fleet Rollout (10.1–10.6) | 6 | 6 | 0 | 0 | 0 |
| Live Readiness (Track B) | 4 | 4 | 0 | 0 | 0 |
| Live Canary (Track C) | 4 | 4 | 0 | 0 | 0 |
| Adapters | 7 | 7 | 0 | 0 | 0 |
| Deploy | 4 | 4 | 0 | 0 | 0 |
| Validation | 3 | 3 | 0 | 0 | 0 |
| Supporting | 14 | 14 | 0 | 0 | 0 |
| **Total** | **71** | **71** | **0** | **0** | **0** |

> **Key finding:** All planned SI-v2 components are implemented on `main`.
> Track A (Fleet Rollout), Track B (Readiness), and Track C (Live Canary) are
> complete. Track D (Live Fleet Rollout) is blocked by C4 ROLLBACK_RECOMMENDED
> and missing APPROVED_LIVE_FLEET_ROLLOUT marker.
> Live trading remains not enabled. Dry-run-only posture preserved.

---

*Previous version grounded at commit `266a930` (2026-06-16).
Rebuilt at commit `32a4804` (2026-07-03).*
