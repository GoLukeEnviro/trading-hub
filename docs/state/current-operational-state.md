# Trading Hub — Current Operational State

> **Canonical current-state snapshot** — validated against `main` at
> commit `0dd7231` (PR #409 squash-merge).
>
> **Last updated:** 2026-07-01 after ADR-2026-07-01 (Autonomous Dry-Run Pivot)
> **Previous update:** 2026-06-30 after T3 + Final Measurement Decision

---

## 1. System posture

| Property | Value |
|----------|-------|
| Live trading | `TARGET_ARCHITECTURE_NOT_ENABLED` — live is a future mode, not currently active |
| Execution mode | Dry-run only |
| SI-v2 controller target | **AUTONOMOUS_DRY_RUN** — policy-gated, canary-first, allowlist-based |
| Current official decision | **KEEP_CANARY_OVERLAY** (from T3 Final Decision) |
| Dry-run apply gating | policy-gated, not per-apply human-gated |
| Human approval | required for live-mode transition, not every dry-run candidate |
| First Canary Apply | ✅ `APPLIED_WITH_RUNTIME_PROOF` — `max_open_trades 3→2` on `freqtrade-freqforge-canary` |
| RuntimeEffectProof | **GREEN** |
| Measurement | **COMPLETED** — Final Decision: **KEEP_CANARY_OVERLAY** (YELLOW/MEDIUM) |
| Rollback Rehearsal | ✅ Implemented (execution hard-blocked) |
| Candidate Pipeline | ✅ Implemented (execution hard-blocked in Phase 6A) |
| Runtime mutation by this repo update | **NONE** |

### Historical note

The previous human-gated phase (`HUMAN_GATED_CANARY_APPLY_PHASE_3C`) was a necessary historical step that proved the controlled apply chain. It is superseded for dry-run by ADR-2026-07-01 (Autonomous Dry-Run Loop with Live-Target Architecture).

---

## 2. SI-v2 Architecture (Complete Chain)

The following modules exist on `main` and form the complete controlled apply chain:

| Phase | Module | PR | Tests | Status |
|-------|--------|----|-------|--------|
| 3B-A | `restart_with_overlay.py` | #379 | 45 | ✅ |
| 3B-B | `restart_gate.py` | #380 | 23 | ✅ |
| 3C-A | `runtime_executor.py` | #381 | 23 | ✅ |
| 4A | `measurement/decision_engine.py` | #382 | 37 | ✅ |
| 5A | `rollback_rehearsal.py` | #383 | 24 | ✅ |
| 6A | `pipeline/candidate_to_apply.py` | #384 | 36 | ✅ |
| **Autonomy Policy** | `autonomy/autonomy_policy.py` | **NEW** | **NEW** | ✅ |
| **Total** | **7 modules** | **7 PRs** | **+ tests** | **All GREEN** |

### Control flow (autonomous dry-run)

```
Active Cycle
  → Candidate Selection
  → Autonomy Policy (policy-gated)
  → Canary Dry-run Apply
  → Runtime Proof
  → Measurement
  → Final Decision (KEEP / EXTEND / ROLLBACK)
  → Auto next iteration
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
| **Final Decision** | 2026-06-30 | 🟡 **KEEP_CANARY_OVERLAY** — MEDIUM confidence |

### Why KEEP_CANARY_OVERLAY

- **Kill Switch was HALT_NEW** from T1 through most of the measurement window (2026-06-27T19:27Z to 2026-06-29T04:15Z), blocking ALL new trades fleet-wide
- Only 1 new canary trade (UNI/USDT, still open) and 3 new control trades (BTC open, ETH/SOL closed with losses) since T0
- Insufficient trade data for a meaningful canary-vs-control comparison
- RuntimeProof GREEN, no safety RED triggers — ROLLBACK not justified
- No evidence that `max_open_trades=2` caused harm — KEEP is the correct decision

---

## 4. Operational priority for agents

### Active priority: Extended Measurement (T4 pending)

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
| Live trading | `TARGET_ARCHITECTURE_NOT_ENABLED` |
| RiskGuard | Required for trading-affecting decisions; currently PASS |
| Kill switch | **NORMAL** (set 2026-06-29T04:15Z, approved by Luke) |
| Apply path | Policy-gated autonomous dry-run (AUTONOMOUS_DRY_RUN mode) |
| Restart path | Canary-only, L3-token-gated via runtime executor |
| Rollback path | Rehearsed but execution hard-blocked |
| Measurement path | Read-only decision engine on `main` |

---

## 6. Architecture decisions

| ADR | Status | Summary |
|-----|--------|---------|
| ADR-2026-06-10-watchdog-ownership | Active | Watchdog ownership and lifecycle |
| ADR-2026-06-27-controlled-self-improvement-human-gated-apply | **Superseded for dry-run** | Human-gated apply (historical) |
| ADR-2026-06-27-si-v2-restart-with-overlay-runtime-proof | Active | Restart-with-overlay runtime proof |
| ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target | **Active** | Policy-gated autonomous dry-run, live as target architecture |

---

## 7. Documentation ownership

- `AGENTS.md` — primary operational agent instruction.
- `SOUL.md` — stable project identity and non-negotiable safety principles.
- `CLAUDE.md` — thin Claude Code handoff that defers to `AGENTS.md`.
- `ORCHESTRATOR_CHARTER.md` — durable charter rules.
- `README.md` — repository orientation.
- `docs/state/current-operational-state.md` — this canonical state snapshot.
- `docs/reports/si-v2-phase-*` — phase-specific evidence reports.
- `docs/decisions/ADR-*` — architecture decision records.
