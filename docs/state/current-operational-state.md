# Trading Hub — Current Operational State

> **Canonical current-state snapshot** — validated against `main` at
> commit `fd48bae` (PR #396 squash-merge).
>
> **Last updated:** 2026-06-30 after T3 + Final Measurement Decision
> **Previous update:** 2026-06-27 after PRs #379–#384 (Complete SI-v2 Chain)

---

## 1. System posture

| Property | Value |
|----------|-------|
| Live trading | `LIVE_FORBIDDEN` — no live trading approval exists |
| Execution mode | Dry-run only |
| SI-v2 controller | `HUMAN_GATED_CANARY_APPLY_PHASE_3C` — canary-only, human-gated, L3-token-gated |
| First L3 Canary Apply | ✅ `APPLIED_WITH_RUNTIME_PROOF` |
| Candidate | `max_open_trades 3→2` on `freqtrade-freqforge-canary` |
| RuntimeEffectProof | **GREEN** |
| Measurement | **COMPLETED** — Final Decision: **EXTEND_MEASUREMENT** |
| Rollback Rehearsal | ✅ Implemented (execution hard-blocked in Phase 5A) |
| Candidate Pipeline | ✅ Implemented (execution hard-blocked in Phase 6A) |
| Final Loop Verdict | **YELLOW / EXTEND_MEASUREMENT** — measurement window was compromised by Kill Switch HALT_NEW |

No root instruction may claim the system is fully GREEN before T2/T3
evidence is evaluated.

---

## 2. SI-v2 Architecture (Complete Chain)

The following modules exist on `main` and form the complete controlled apply
chain:

| Phase | Module | PR | Tests | Status |
|-------|--------|----|-------|--------|
| 3B-A | `restart_with_overlay.py` | #379 | 45 | ✅ |
| 3B-B | `restart_gate.py` | #380 | 23 | ✅ |
| 3C-A | `runtime_executor.py` | #381 | 23 | ✅ |
| 4A | `measurement/decision_engine.py` | #382 | 37 | ✅ |
| 5A | `rollback_rehearsal.py` | #383 | 24 | ✅ |
| 6A | `pipeline/candidate_to_apply.py` | #384 | 36 | ✅ |
| **Total** | **6 modules** | **6 PRs merged** | **188** | **All GREEN** |

### Control flow

```
CandidateApplyInput
  → candidate_to_apply_pipeline()    Phase 6A
  → check_readiness()                 Phase 1
  → execute_apply()                   writes overlay
  → plan_canary_restart_with_overlay()   Phase 3B-A
  → check_restart_gate()              Phase 3B-B
  → build_canary_recreate_plan()
  → run_canary_restart_with_overlay() Phase 3C-A (L3-gated)
  → RuntimeEffectProof                GREEN
  → Measurement Decision Engine       Phase 4A (T0/T1/T2/T3)
  → Rollback Rehearsal                Phase 5A (not executed yet)
```

### Active bot identities

| Bot id | Role | Status in current loop |
|--------|------|------------------------|
| `freqtrade-freqforge` | FreqForge baseline/override | Active (control bot) |
| `freqtrade-freqforge-canary` | FreqForge canary | **Active — apply target** |
| `freqtrade-regime-hybrid` | Regime-hybrid | Active |
| `freqai-rebel` | FreqAI/Rebel | Active |

Momentum is decommissioned and MVS is not deployed. They are historical
context only.

---

## 3. Measurement Status

| Point | Time | Status |
|-------|------|--------|
| **T0** | 2026-06-27T18:27Z | ✅ **GREEN** |
| **T1** | 2026-06-27T19:27Z | 🟡 **YELLOW / CONTINUE** — Bitget 429 warnings |
| **T2** | 2026-06-28T00:27Z | 🟡 **YELLOW / CONTINUE** — Bitget 429 warnings, 0 new trades |
| **T3** | 2026-06-28T18:27Z | 🟡 **YELLOW / EXTEND_MEASUREMENT** — Bitget 429, Kill Switch HALT_NEW compromised window |
| **T4 Readiness** | 2026-06-30 | ⏳ **NOT_ENOUGH_DATA** — 0 new closed canary trades since T3 |
| **T4 Follow-up** | 2026-06-30 | ⏳ **STILL_NOT_ENOUGH_DATA** — UNI/USDT still open, no change since T4 Readiness |
| **Final Decision** | 2026-06-30 | 🟡 **EXTEND_MEASUREMENT** — MEDIUM confidence |

### Why EXTEND_MEASUREMENT

- **Kill Switch was HALT_NEW** from T1 through most of the measurement window (2026-06-27T19:27Z to 2026-06-29T04:15Z), blocking ALL new trades fleet-wide
- Only 1 new canary trade (UNI/USDT, still open) and 3 new control trades (BTC open, ETH/SOL closed with losses) since T0
- Insufficient trade data for a meaningful canary-vs-control comparison
- RuntimeProof GREEN, no safety RED triggers — ROLLBACK not justified
- No evidence that `max_open_trades=2` caused harm — EXTEND is the correct decision

---

## 4. Operational priority for agents

### Active priority: Extended Measurement

**Do NOT start** without explicit approval:
- new apply
- restart
- rollback
- pair expansion
- live readiness
- next candidate research

**Allowed:**
- read-only audits and reports
- documentation updates
- extended measurement collection (T4+)
- monitoring for trade activity under Kill Switch NORMAL

### Next runtime action
**Re-check after canary UNI/USDT trade closes. Minimum: 1 new closed canary trade + 1 new closed control trade for official T4.**

---

## 5. Safety layer status

| Component | Current status |
|-----------|----------------|
| Dry-run posture | ✅ Required for all active bots |
| Live trading | `LIVE_FORBIDDEN` |
| RiskGuard | Required for trading-affecting decisions; currently PASS |
| Kill switch | **NORMAL** (set 2026-06-29T04:15Z, approved by Luke) |
| Apply path | Canary-only, human-gated, L3-token-gated |
| Restart path | Canary-only, L3-token-gated via runtime executor |
| Rollback path | Rehearsed but execution hard-blocked (Phase 5A) |
| Measurement path | Read-only decision engine on `main` |

---

## 6. Documentation ownership

- `AGENTS.md` — primary operational agent instruction.
- `SOUL.md` — stable project identity and non-negotiable safety principles.
- `CLAUDE.md` — thin Claude Code handoff that defers to `AGENTS.md`.
- `ORCHESTRATOR_CHARTER.md` — durable charter rules.
- `README.md` — repository orientation.
- `docs/state/current-operational-state.md` — this canonical state snapshot.
- `docs/reports/si-v2-phase-*` — phase-specific evidence reports.
- `docs/decisions/ADR-*` — architecture decision records.
