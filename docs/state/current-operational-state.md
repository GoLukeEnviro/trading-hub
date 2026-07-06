# Trading Hub — Current Operational State

> **Canonical current-state snapshot** — validated against `main` at
> commit `c897c01` (PR #481 squash-merge — SEC-2 partial fix).
>
> **Last updated:** 2026-07-06
> **Previous update:** 2026-07-01 (Phase 10.4 Post-Fleet Measurement Watcher)
> **Branch:** `main`
> **HEAD:** `c897c01`
> **Companion roadmap:** `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md`

---

## 1. System posture

| Property | Value |
|----------|-------|
| Live trading | `TARGET_ARCHITECTURE_NOT_ENABLED` — live is a future mode, not currently active |
| Execution mode | Dry-run only |
| SI-v2 controller target | **AUTONOMOUS_DRY_RUN** — policy-gated, canary-first, allowlist-based |
| Current official decision | **KEEP_CANARY_OVERLAY** (from T3 Final Decision, 2026-06-30) |
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
| **10.1 Resolver** | `fleet_rollout_input_resolver.py` | #421 | 24 | ✅ |
| **10.2 Evidence Runner** | `fleet_rollout_ready_evidence_runner.py` | #422 | 12 | ✅ |
| **10.3 Dry-Run Executor** | `fleet_dry_run_runtime_executor.py` | #424 | 18 | ✅ |
| **10.4 Post-Fleet Measurement** | `fleet_post_fleet_measurement_watcher.py` | #425 | 20 | ✅ |
| **Total** | **11 modules** | **11 PRs** | **+ tests** | **All GREEN** |

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
| `freqtrade-freqforge-canary` | FreqForge canary | **Running with retained overlay** — see §3 |
| `freqtrade-regime-hybrid` | Regime-hybrid | Active |
| `freqai-rebel` | FreqAI/Rebel | Active |

Momentum is decommissioned and MVS is not deployed. They are historical context only.

---

## 3. Canary State — Verified Runtime Evidence (2026-07-06)

| Property | Value |
|----------|-------|
| **Container** | `trading-freqtrade-freqforge-canary-1` |
| **Status** | ✅ **Running** (since 2026-07-05T00:09Z) |
| **Image** | `freqtradeorg/freqtrade:stable` (⚠️ not custom `canary-c5` image) |
| **Command** | `trade --config /freqtrade/user_data/config.json --config /freqtrade/user_data/overlay_max_open_trades_.json --strategy FreqForge_Override` |
| **Overlay active** | ✅ **YES** — `max_open_trades=2` (from overlay created 2026-06-27T17:46Z by SI-v2) |
| **Baseline config** | `max_open_trades=3`, `dry_run=True` |
| **Docker-Compose definition** | Defines canary **without** overlay config — container diverges from compose |
| **Container created** | 2026-07-03T04:48Z (during rollback ceremony) |
| **Container started** | 2026-07-05T00:09Z — `unless-stopped` policy restarted after rollback stop |
| **Pre-overlay container** | `trading-freqtrade-freqforge-canary-1-pre-overlay` — Exited (130) 8 days ago (the rollback target) |
| **Database** | `tradesv3.freqforge_canary.dryrun.sqlite` (196KB) — 71 closed, 1 open |
| **Open trade** | ATOM/USDT:USDT (opened 2026-07-01, amount=16, rate=1.5179) |
| **Last closed trades** | LINK +0.0056%, AAVE +0.0044%, DOT +0.21% (all since 2026-07-05) |
| **Provenance** | ⚠️ **PROVENANCE_WARNING** — `unless-stopped` restarted after rollback stop without formal re-activation |

### Provenance assessment

The canary was stopped during the 2026-07-03 rollback ceremony (Kill Switch EMERGENCY → container stop → Kill Switch NORMAL). The `unless-stopped` restart policy in `docker-compose.yml` caused the container to restart automatically. The restart **retained the overlay command** (`--config overlay_max_open_trades_.json`) because the same existing container was restarted under the `unless-stopped` policy, not because a Compose recreate was verified. The compose file itself does **not** specify the overlay config. The overlay was injected by the SI-v2 controlled apply chain before the rollback and persisted in the container's command.

**Impact:** T4 measurement data collected since 2026-07-05 is **measurement-contaminated** — the canary is running with `max_open_trades=2` overlay but without formal re-activation or measurement window reset. The 71 closed trades include both pre-rollback and post-restart data.

---

## 4. Measurement Status

| Point | Time | Status |
|-------|------|--------|
| **T0** | 2026-06-27T18:27Z | ✅ **GREEN** |
| **T1** | 2026-06-27T19:27Z | 🟡 **YELLOW / CONTINUE** — Bitget 429 warnings |
| **T2** | 2026-06-28T00:27Z | 🟡 **YELLOW / CONTINUE** — Bitget 429 warnings, 0 new trades |
| **T3** | 2026-06-28T18:27Z | 🟡 **YELLOW / EXTEND_MEASUREMENT** — Bitget 429, Kill Switch HALT_NEW compromised window |
| **T4 Readiness** | 2026-06-30 | ⏳ **NOT_ENOUGH_DATA** — 0 new closed canary trades since T3 |
| **T4 Follow-up** | 2026-06-30 | ⏳ **STILL_NOT_ENOUGH_DATA** — UNI/USDT still open, no change since T4 Readiness |
| **Final Decision** | 2026-06-30 | 🟡 **KEEP_CANARY_OVERLAY** — MEDIUM confidence |

### T4 status after canary restart

The canary restart on 2026-07-05 does **not** automatically unblock T4. The measurement window is contaminated by:
1. The rollback event (Kill Switch EMERGENCY, container stop)
2. The unplanned restart with retained overlay
3. No formal measurement window reset

**Current T4 assessment:** ⏳ **NOT_ENOUGH_DATA** — 1 open trade (ATOM/USDT since 2026-07-01), no new closed canary trades in a clean post-restart window. A formal T4 re-evaluation requires:
- Minimum 1 new closed canary trade in a clean post-restart window
- Minimum 1 new closed control trade in the same period
- Provenance assessment of the restart

### Why KEEP_CANARY_OVERLAY

- Kill Switch was HALT_NEW from T1 through most of the measurement window (2026-06-27T19:27Z to 2026-06-29T04:15Z), blocking ALL new trades fleet-wide
- Only 1 new canary trade (UNI/USDT, still open) and 3 new control trades (BTC open, ETH/SOL closed with losses) since T0
- Insufficient trade data for a meaningful canary-vs-control comparison
- RuntimeProof GREEN, no safety RED triggers — ROLLBACK not justified
- No evidence that `max_open_trades=2` caused harm — KEEP is the correct decision

---

## 5. Operational priority for agents

### Active priority: Extended Measurement (T4 pending, provenance-warning)

**Do NOT start** without explicit approval:
- new apply
- restart
- rollback
- pair expansion
- live readiness
- next candidate research
- canary container manipulation

**Allowed:**
- read-only audits and reports
- documentation updates
- extended measurement collection (T4+)
- monitoring for trade activity under Kill Switch NORMAL

### Next runtime action
**Re-check after canary ATOM/USDT trade closes. Minimum: 1 new closed canary trade in a clean post-restart window + 1 new closed control trade for official T4. Provenance assessment required before T4 can be declared clean.**

---

## 6. Fleet Status (last telemetry cycle: 2026-07-06T12:17Z)

| Bot | Status | Open | Trades | Profit % | Profit abs |
|-----|--------|------|--------|----------|------------|
| **FreqForge** | online | 0 | 1 | +0.34% | +5.13 USDT |
| **Regime-Hybrid** | online | 0 | 4 | -0.76% | -0.32 USDT |
| **FreqAI-Rebel** | online | 0 | 5 | -0.21% | -0.34 USDT |
| **FreqForge-Canary** | running | 1 | 71 | — | — |

All bots: `dry_run=True`, all pings OK.

---

## 7. Safety layer status

| Component | Current status |
|-----------|----------------|
| Dry-run posture | ✅ Required for all active bots |
| Live trading | `TARGET_ARCHITECTURE_NOT_ENABLED` |
| RiskGuard | Required for trading-affecting decisions; currently PASS |
| Kill switch | **NORMAL** (set 2026-07-03T05:26Z, cleared after canary rollback) |
| Apply path | Policy-gated autonomous dry-run (AUTONOMOUS_DRY_RUN mode) |
| Restart path | Canary-only, L3-token-gated via runtime executor |
| Rollback path | Rehearsed but execution hard-blocked |
| Measurement path | Read-only decision engine on `main` |

### Kill Switch State (verified 2026-07-06)

```json
{
  "mode": "NORMAL",
  "reason": "manually cleared",
  "triggered_at": "2026-07-03T05:26:10.981566+00:00",
  "triggered_by": "cli",
  "auto_clear_at": ""
}
```

---

## 8. PR #481 — Security Fix (merged 2026-07-06)

| Property | Value |
|----------|-------|
| **PR** | #481 |
| **Merge commit** | `c897c01` |
| **Scope** | SEC-2 partial fix: reduce container secret exposure |
| **Status** | ✅ **MERGED** |
| **Related issues** | #475 (closed: remove raw docker socket from hermes-green), #476 (open: host-level env fix + API_SERVER_KEY rotation) |
| **Remaining** | #476 remains open — host-level env fix and API_SERVER_KEY rotation not addressed |

---

## 9. Ledger Integrity Warning

| Check | Status | Detail |
|-------|--------|--------|
| Sources | ⚠️ **WARNING** | 4 active bots, 3 ledger keys — `freqai-rebel` missing |
| Drawdown | ✅ OK | 1.81% (threshold 3%) |
| Live-Ledger Gap | ⚠️ INFO | Δ ≈ 1,043 USDT (LIVE 3,498 vs LEDGER 2,455) |
| Recommendation | Tier-2 fix needed | ledger-collector needs source_key for `freqai-rebel` |

---

## 10. Cron Job Status

| Status | Count | Details |
|--------|-------|---------|
| Active (OK) | ~45 | Health checks, heartbeats, drawdown-guard, riskguard, ledger-watchdog, etc. |
| **Failed** | **1** | `fleet-correlation-refresh` (every 3d, last error 2026-07-05) |
| Paused | 1 | `hermes-standby-monitor` (since 2026-06-06) |
| Paused (SI-v1 legacy) | 8 | Bot A/B/C/D backtest/daily/walkforward — runners missing |
| Paused | 1 | `si-v2-t4-watcher` (detector-only, disabled 2026-07-01) |

---

## 11. Security & Permission Issues

| Issue | Status | Detail |
|-------|--------|--------|
| **#476** | 🔴 **OPEN** | Host-level env fix + API_SERVER_KEY rotation — not addressed by PR #481 |
| **Hermes runtime** | ⚠️ **PARTIAL ROOT** | Some Hermes scripts/state files owned by root (UID 0) instead of the configured Hermes runtime ownership (`10000:10000`). Separate SEC/OPS issue needed for systematic fix. |
| **Docker socket** | ✅ **CLOSED** | #475 — raw docker socket removed from hermes-green |

---

## 12. Architecture decisions

| ADR | Status | Summary |
|-----|--------|---------|
| ADR-2026-06-10-watchdog-ownership | Active | Watchdog ownership and lifecycle |
| ADR-2026-06-27-controlled-self-improvement-human-gated-apply | **Superseded for dry-run** | Human-gated apply (historical) |
| ADR-2026-06-27-si-v2-restart-with-overlay-runtime-proof | Active | Restart-with-overlay runtime proof |
| ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target | **Active** | Policy-gated autonomous dry-run, live as target architecture |

---

## 13. Worktree Note

The working tree has 48 dirty files (47 untracked, 1 modified) as of 2026-07-06. These are documentation context reports, incident records, and one modified `self_optimizer.py`. These are **not** system state — they are pending documentation commits and should not be confused with runtime evidence.

---

## 14. Documentation ownership

- `AGENTS.md` — primary operational agent instruction.
- `SOUL.md` — stable project identity and non-negotiable safety principles.
- `CLAUDE.md` — thin Claude Code handoff that defers to `AGENTS.md`.
- `ORCHESTRATOR_CHARTER.md` — durable charter rules.
- `README.md` — repository orientation.
- `docs/state/current-operational-state.md` — this canonical state snapshot.
- `docs/reports/si-v2-phase-*` — phase-specific evidence reports.
- `docs/decisions/ADR-*` — architecture decision records.
