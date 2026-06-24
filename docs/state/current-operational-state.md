# Trading Hub — Current Operational State

> **Canonical current-state snapshot** — validated against merged `main` at
> commit `f14b286a2d1cf501a1aff552d3449c5ceae4a10d`.
>
> **Last updated:** 2026-06-24 as part of Issue #342 docs-only
> root-instruction alignment after the post-PR341 SI-v2 Active Cycle proof
> passed GREEN.
> **Branch for this alignment:** `docs/align-root-agent-instructions-si-v2-342`
> **Companion roadmap:** `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md`

---

## 1. System posture

| Property | Value |
|----------|-------|
| Live trading | `LIVE_FORBIDDEN` — no live trading approval exists |
| Execution mode | Dry-run only |
| Signal source | `ai-hedge-fund-crypto` plus read-only Rainbow observation |
| Meta-orchestrator | `hermes-agent` in the `orchestrator` profile |
| SI-v2 controller | `PAUSED / L3_REPOSITORY_ONLY` |
| Current loop proof | GREEN for evidence/wiring only, not approval-to-apply |
| Profitability gate | Blocked; do not discuss Controlled Apply until the next required proofs are complete |

No root instruction may be treated as proof of runtime safety. For runtime
claims, use this state file plus the referenced proof report/evidence bundle.

---

## 2. Proven SI-v2 4-bot Active Cycle loop

The current proven SI-v2 loop is the read-only Active Cycle path that reads all
four active dry-run bots, writes historical evidence into the bundle, preserves
telemetry evidence, emits ShadowProposals, and performs zero runtime mutation.

### Active SI-v2 bot identities

| Bot id | Runtime role | Status in current loop |
|--------|--------------|------------------------|
| `freqtrade-freqforge` | FreqForge baseline/override bot | Active loop member |
| `freqtrade-freqforge-canary` | FreqForge canary bot | Active loop member |
| `freqtrade-regime-hybrid` | Regime-hybrid bot | Active loop member |
| `freqai-rebel` | FreqAI/Rebel bot | Active loop member |

Momentum is decommissioned and MVS is not deployed. They are historical context
only and must not be counted as active SI-v2 loop members.

### Proof artifacts

| Artifact | Path / Value |
|----------|--------------|
| Proof report | `docs/reports/si-v2-active-cycle-proof-post-pr341-2026-06-24.md` |
| Evidence bundle | `self_improvement_v2/reports/phase2/evidence/active_cycle_20260624T055059Z.json` |
| Evidence SHA-256 | `694641dea7025f49de82a378a6a4d0ce3ad8ecf5ab0214dc70af5eb4252a9aa0` |
| Cycle state | `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260624T055059Z.state.json` |
| Runner log | `/opt/data/logs/si-v2-active-cycle/cycle-20260624T055058Z.log` |

### Proof result summary

| Check | Current proof result |
|-------|----------------------|
| Four active bots represented | OK |
| Four active bots reachable/authenticated | OK |
| `historical_trade_window.status` | OK |
| Per-bot `historical_trade_summary` | Present for every active bot |
| Existing telemetry `evidence_window` | Preserved for every active bot |
| ShadowProposal count | 4 |
| Approval eligible | 2 of 4 |
| Runtime/config/strategy/Docker/live-trading mutation counters | 0 |
| Proposal application | Not invoked |
| Approval/apply tokens | Not provided |

Interpretation: PR #341 wiring is practically validated for evidence and Active
Cycle integration. This is not a trading approval, not a profitability approval,
and not an apply-actuator approval.

---

## 3. Operational priority for follow-up agents

Future agents should use this priority order from `AGENTS.md`:

1. SI-v2 Loop
2. Historical Evidence
3. Measurement Attribution
4. ShadowProposal Quality
5. Runtime Safety

Scope rule: no Docker, Guardian, Cron, generic healthcheck, generic CI, or
infrastructure work unless it directly blocks the SI-v2 loop or Luke explicitly
approves that scope.

---

## 4. Current blocker

The technical runtime blocker for PR #341 is closed by the GREEN proof. The
remaining blocker is agent steering/documentation drift:

- root agent instructions must describe the proven 4-bot SI-v2 loop;
- root docs must not carry stale bot counts or volatile ledger/cycle/Rainbow
  values;
- future agents must not drift into generic infra or healthcheck work while the
  SI-v2 loop sequence is still active.

Issue #342 is completed by this docs-only alignment PR. After merge, this
agent-steering blocker should be considered resolved unless review finds
remaining drift.

---

## 5. Next sequence

1. Merge/review Issue #342 docs-only alignment PR.
2. Review PR #330 and decide whether to update, supersede, or close it against
   the post-PR341 evidence shape.
3. Run the P3 Scheduler Continuity Proof.
4. Only after scheduler continuity and required gates are GREEN should Controlled
   Apply be discussed again.

No apply token is in scope for this state update.

---

## 6. Safety layer status

| Component | Current status |
|-----------|----------------|
| Dry-run posture | Required for all active bots |
| Live trading | Forbidden |
| RiskGuard | Required for trading-affecting decisions |
| ShadowLogger / evidence artifacts | Required for decisions and safety-relevant changes |
| Kill switch | Must be respected; `HALT_NEW` and `EMERGENCY` block new entries |
| Apply actuator | Not in scope unless separately approved with the required proof and token gates |

---

## 7. Documentation ownership

- `AGENTS.md` — primary operational agent instruction.
- `SOUL.md` — stable project identity and non-negotiable safety principles.
- `CLAUDE.md` — thin Claude Code handoff that defers to `AGENTS.md` and
  `SOUL.md`.
- `ORCHESTRATOR_CHARTER.md` — durable charter rules; historical references must
  be clearly marked non-current.
- `README.md` — repository orientation, not a volatile runtime metric store.
- `docs/state/current-operational-state.md` — this canonical state snapshot.
- `docs/reports/` — proof reports with runtime evidence values.
- `docs/context/` — append-only historical reports and decisions.

---

## 8. Historical / non-current notes

- Older documents may mention a six-bot fleet. That is historical/non-current
  and must not be used as the current SI-v2 loop assumption.
- Older Rainbow, ledger, cycle, proposal, or telemetry counts are snapshots, not
  instructions. Use the latest proof report and this state file for current
  runtime claims.
- Honcho persistent memory was decommissioned/archived and is not part of the
  current operational authority path.
