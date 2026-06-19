# SI v2 — Live-Readiness Blocker Burn-Down Plan for Controlled Spot Pilot

> **Issue:** #280
> **Date:** 2026-06-19
> **Author:** Hermes Orchestrator (read-only assessment + planning)
> **Classification:** L2 — Planning artifact, no runtime mutation
> **Live state:** `LIVE_FORBIDDEN` — all bots `dry_run=true`

---

## Verdict

**NOT_READY**

No controlled spot pilot is currently freigabefähig. The profitability evidence
lane (`#279` → `#284`) has not yet produced a pilot candidate, and no live
credentials, live config, or dry-run rehearsal exists.

However, the path from `NOT_READY` to `PILOT_PREP_READY` is now clearer with the
Human Approval Gate (`#276` / PR #289) implemented and the multi-cycle evidence
lane (`#284`) actively accumulating natural scheduled cycles.

---

## 1. Blocker Inventory

| ID | Blocker | Current State | Burn-Down Action | Effort |
|----|---------|---------------|------------------|--------|
| **B-01** | No pilot candidate with positive real net metrics | 2 bots `watch` (no real WF metrics), 2 bots `blocked` (net-negative). Verdict: `WATCH_LIST_ONLY` | Continue accumulating natural scheduled cycles via `#284`; wait for FreqForge or FreqForge-Canary to produce real walk-forward metrics | Time-gated |
| **B-02** | No documented `LIVE_APPROVED` state | State machine remains `LIVE_FORBIDDEN` | Transition requires: B-01 resolved + B-03 through B-07 complete + explicit human approval token `APPROVE_LIVE_SPOT_PILOT_<YYMMDD>` | Gate |
| **B-03** | No live exchange credentials | No exchange API keys configured anywhere; `dry_run=true` for all bots | Create spot-only API key with trade + read permissions only (no withdrawal); store in `/opt/data/secrets/` (never in repo) | Human |
| **B-04** | No live Freqtrade config | All configs are `dry_run=true` with no exchange credentials | Create disabled config skeleton for one bot (spot-only, small `stake_amount`, strict `stoploss`); validate schema before enablement | S |
| **B-05** | No controlled dry-run rehearsal | No rehearsal has been executed against the pilot candidate | Run preflight checklist → controlled dry-run rehearsal with the same strategy/config → measure for ≥48h → compare against baseline | M |
| **B-06** | No signed human approval gate | Human Approval Gate implemented (`#276` / PR #289) but not yet exercised against a real eligible proposal | Wait for B-01 to produce an approval-eligible proposal → human review → `APPROVED` status → proceed to rehearsal | Gate |
| **B-07** | No rollback path documentation | No documented rollback procedure for live enablement | Document: revert to `dry_run=true`, remove live credentials, restore dry-run config, verify kill switch engages | S |

---

## 2. Minimal Path for Spot-Only Pilot

### Scope Constraints

| Constraint | Value |
|------------|-------|
| Bots in pilot | **Exactly one** — pilot candidate from `#284` evidence |
| Trading mode | **Spot only** — no futures, no leverage, no margin |
| Max capital | Small — suggested $50–$100 initial stake |
| Max open trades | 1 (conservative) |
| Duration | 7-day observation window before any adjustment |
| Kill switch | Mandatory — auto-halt on 8% drawdown (`HALT_NEW`) |

### Pilot Candidate Selection (B-01 Burn-Down)

Current watch list (from `#284` rerun):

| Bot | Classification | Net Metrics | Real WF Metrics | Spot Mode |
|-----|---------------|-------------|-----------------|-----------|
| `freqtrade-freqforge` | `watch` | Positive read-path, no real WF | 0/2 cycles | Futures |
| `freqtrade-freqforge-canary` | `watch` | Positive read-path, no real WF | 0/2 cycles | **Spot** |
| `freqtrade-regime-hybrid` | `blocked` | Net-negative (-14.26 PnL) | 2/2 cycles | Futures |
| `freqai-rebel` | `blocked` | Net-negative (-0.64 PnL) | 2/2 cycles | Futures |

**Preferred pilot candidate:** `freqtrade-freqforge-canary` — already runs in
**spot mode**, has positive read-path telemetry, and needs only real walk-forward
metrics to qualify as a candidate.

**Blocking condition:** `freqforge-canary` must produce ≥2 real walk-forward
metric cycles with positive net PnL and acceptable drawdown before it becomes
approval-eligible.

### Burn-Down Sequence

```
B-01 (profitability) ──▶ B-06 (approval gate) ──▶ B-04 (live config skeleton)
                                                      │
                        B-03 (exchange creds) ◀───────┤
                                                      │
                        B-05 (dry-run rehearsal) ◀────┤
                                                      │
                        B-07 (rollback path) ◀────────┤
                                                      │
                        B-02 (LIVE_APPROVED) ◀────────┘
                                │
                                ▼
                        PILOT_APPROVAL_READY
```

---

## 3. Required Minimal Artifacts

| Artifact | Description | Blocking Issue |
|----------|-------------|----------------|
| Profitability evidence report | Multi-cycle report showing positive net metrics for pilot bot | `#284` |
| Approval gate verdict | `ApprovalStatus.PENDING_HUMAN` with `approval_eligible=True` for pilot bot | `#276` |
| Disabled live config skeleton | Spot-only config with `dry_run=true`, no credentials, small stake | B-04 |
| Enablement checklist | Step-by-step checklist for transitioning to live | B-05 |
| Human approval artifact | Signed approval with token, scope, limits, reviewer name | B-06 |
| Rehearsal proof | ≥48h dry-run results matching pilot config parameters | B-05 |
| Rollback path document | Documented revert procedure with exact commands | B-07 |
| RiskGuard validation | Confirmation that RiskGuard would not veto pilot config | B-05 |
| Kill switch verification | Confirmation that `HALT_NEW` activates at 8% drawdown threshold | B-07 |

---

## 4. Classification

| State | Condition | Current |
|-------|-----------|---------|
| `NOT_READY` | Pilot candidate missing, evidence incomplete, or blockers unresolved | **✅ Current** |
| `PILOT_PREP_READY` | All artifacts created, rehearsal passed, rollback documented, but no human approval | — |
| `PILOT_APPROVAL_READY` | All artifacts + human approval signed, ready for controlled enablement | — |

---

## 5. Safety Boundaries

- **No live trading** — this document defines the path, it does not enable it
- **No `dry_run=false`** — all bots remain `dry_run=true`
- **No exchange credentials** in the repo
- **No Freqtrade config changes** — live config skeleton is a disabled artifact, not applied
- **No strategy changes** — pilot uses existing strategy unchanged
- **Human approval mandatory** — no automatic enablement at any stage
- **Controller remains** `PAUSED / L3_REPOSITORY_ONLY`
- **Kill switch** must be verified active before any pilot begins

---

## 6. Reference Artifacts

- Profitability evidence: `docs/context/2026-06-19-si-v2-multi-cycle-profitability-score-rerun.md`
- Evidence lane definition: `docs/context/2026-06-19-si-v2-multi-cycle-profitability-evidence-lane.md`
- Human Approval Gate: PR #289 (`feat/si-v2-approval-gate-276`)
- Governance checklist: `self_improvement_v2/governance/human_approval_gate_checklist.md`
- Runtime preflight: `self_improvement_v2/governance/runtime_preflight_checklist.md`
- Operational state: `docs/state/current-operational-state.md`
- SOUL.md state machine: `~/.hermes/profiles/orchestrator/SOUL.md` §7
