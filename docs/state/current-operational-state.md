# Trading Hub — Current Operational State

> **Canonical current-state snapshot** — validated against `main` at
> commit `75384e1` (PR #501 squash-merge).
>
> **Last updated:** 2026-07-10 after Rainbow R1–R6
> **Previous update:** 2026-07-01 after Phase 10.4

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

### Rainbow Integration Status

| Task | Status | PR | Merge SHA |
|------|--------|----|-----------|
| R1 — Contract reconciliation | ✅ MERGED | #497 | `8c167c8` |
| R2 — Read-only provider | ✅ MERGED | #498 | `dc15f6d` |
| R3 — Attribution producer | ✅ MERGED | #499 | `4ec1b18` |
| R4 — Window-scoped C4 fix | ✅ MERGED | #500 | `a70a058` |
| R6 — Candidate quality | ✅ MERGED | #501 | `75384e1` |
| R5 — Runtime preflight audit | ⏳ IN_PROGRESS | — | — |
| R7 — Dry-run measurement | BLOCKED | — | — |

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
| **10.1 Resolver** | `fleet_rollout_input_resolver.py` | #421 | 24 | ✅ |
| **10.2 Evidence Runner** | `fleet_rollout_ready_evidence_runner.py` | #422 | 12 | ✅ |
| **10.3 Dry-Run Executor** | `fleet_dry_run_runtime_executor.py` | #424 | 18 | ✅ |
| **10.4 Post-Fleet Measurement** | `fleet_post_fleet_measurement_watcher.py` | #425 | 20 | ✅ |
| **Rainbow R1** | Contract reconciliation | #497 | + | ✅ |
| **Rainbow R2** | Read-only provider | #498 | + | ✅ |
| **Rainbow R3** | Attribution producer | #499 | + | ✅ |
| **Rainbow R4** | Window-scoped C4 fix | #500 | + | ✅ |
| **Rainbow R6** | Candidate quality | #501 | + | ✅ |
| **Total** | **16 modules** | **16 PRs** | **+ tests** | **All GREEN** |

### Active bot identities

| Bot id | Role | Status in current loop |
|--------|------|------------------------|
| `freqtrade-freqforge` | FreqForge baseline/override | Active (control bot) |
| `freqtrade-freqforge-canary` | FreqForge canary | **Active — apply target** |
| `freqtrade-regime-hybrid` | Regime-hybrid | Active |
| `freqai-rebel` | FreqAI/Rebel | Active |

Momentum is decommissioned and MVS is not deployed. They are historical context only.

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

### Active priority: Rainbow R5 (read-only audit)

**Do NOT start** without explicit approval:
- new apply
- restart
- rollback
- pair expansion
- live readiness
- next candidate research
- runtime remediation from R5 findings

**Allowed:**
- read-only audits and reports
- documentation updates
- Rainbow R5 read-only audit (current task)
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
| Rainbow advisory | Read-only, fail-closed, disabled by default |

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
- `docs/reports/rainbow-r*-*-2026-07-10.md` — Rainbow R1–R6 reports.

---

## C1 planning note (2026-07-09)

- Repository HEAD at C1 planning: `c897c01` (main). Source snapshot referenced elsewhere: `20aee88`.
- Post-snapshot security hardening includes #475 (raw docker socket removed from hermes-green) and #476 (SEC-2 partial fix).
- **Runtime posture remains `AUTONOMOUS_DRY_RUN`** — no fresh runtime measurement performed in C1; runtime re-baseline is a separate, explicitly-gated step (Phase F).
- Workspace bridge (Phase C1A): HermesTrader Hermes container sees this repo read-only at `/workspace/projects/trading-hub`; host path `/opt/data/projects/trading-hub`.

## Rainbow R5 note (2026-07-10)

- Rainbow R1–R6 merged (PRs #497–#501).
- R5 read-only audit in progress.
- R7 blocked until R5 complete and runtime preflight approved.
- No runtime mutation performed during Rainbow integration.
- All Rainbow modules are read-only, fail-closed, disabled by default.
