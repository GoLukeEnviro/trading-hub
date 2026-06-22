# Phase 2.1 – SI v2 Autonomous Dry-Run Operation — Definition of Done

> Status: Draft (to be kept in sync with docs/state/current-operational-state.md
> and docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md).
>
> Scope: Trading Hub — SI v2 Phase 2.1 (autonomous *dry-run* operation only).
> No live trading. No change to LIVE_FORBIDDEN state machine without a separate gate.

---

## 1. Purpose

This document defines the concrete completion criteria for Phase 2.1
"SI v2 Autonomous Dry-Run Operation". It translates the roadmap into a
checkable checklist that can be used by humans and agents before Phase 2.1
is marked as "COMPLETE" in canonical docs.

---

## 2. Preconditions

Before Phase 2.1 can be considered, the following must already hold:

- Phase 2.0 "Runtime Foundation & Docker Ownership" is COMPLETE
  (issue #200 closed, telemetry history enforcement gate merged and active).
- docs/state/current-operational-state.md is reconciled with the current
  main HEAD.
- Live trading is forbidden:
  - All bots dry_run=true.
  - State machine LIVE_FORBIDDEN.
- SI v2 controller is PAUSED / L3_REPOSITORY_ONLY.

If any of these are not true, fix them first and update the current-state doc.

---

## 3. Definition of Done — Phase 2.1

Phase 2.1 is considered COMPLETE only when ALL of the following are true:

### 3.1 Rainbow Producer & Scoring History

- A real Rainbow producer (ai4trade/ai-hedge-fund-crypto compatible)
  is deployed on localhost and:
  - Produces fresh signals at the configured cadence (e.g. every 120s).
- Exposes a health endpoint used by the observation loop.
- The SI v2 observation loop has persisted at least 10/10
  scoring-eligible cycles in the Measurement Ledger:
  - Freshness checks pass (fresh=True, age ≤ configured threshold).
  - Symbols match the expected universe (e.g. BTC, ETH, SOL).
  - No scoring-eligibility "flapping" due to stale SQLite.

### 3.2 Walk-Forward Integration

- The walk-forward cost model and evaluator are integrated into the
  active observation pipeline, not just as an offline tool:
  - At least one scheduled SI v2 cycle exercises the walk-forward
    evaluator against the relevant strategies/universe.
  - Output is persisted in a deterministic location (JSON/Markdown)
    and referenced from a context or state doc.

### 3.3 Telegram / Approval Gates

- There is a documented, implemented approval gate for applying SI v2
  proposals, wired to the existing Telegram / Gateway mechanism:
  - No proposal can mutate runtime, config, strategies, or Docker
    without explicit human approval.
  - The gate is described in a public doc (context or spec), with
    tokens/phrases clearly defined (e.g. APPROVE_RAINBOW_PRODUCER_DEPLOY-style).
- Auto-execution of proposals remains out of scope for this phase:
  - Controller stays PAUSED / L3_REPOSITORY_ONLY.
  - No "auto-merge" or "auto-restart" paths exist.

### 3.4 Dry-Run Only Invariants

- All invariants that enforce dry-run-only are tested and documented:
  - Tests exist that assert:
    - dry_run=true for all fleet bots.
    - No live-trading keys/credentials are present in tracked config.
  - CI gates ensure that any change violating these invariants fails.

### 3.5 Documentation & Traceability

- The following documents reference Phase 2.1 as PARTIAL or COMPLETE
  in a consistent way:
  - docs/state/current-operational-state.md (canonical runtime snapshot).
  - docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md (Phase table).
- At least one context/audit doc explains:
  - How the producer was deployed.
  - How the 10/10 scoring history was achieved.
  - Which safeguards prevent accidental escalation beyond dry-run.

---

## 4. Checklist for Operators / Agents

Use this checklist when deciding whether Phase 2.1 is "DONE":

- [ ] Telemetry history gate and Docker ownership (#200, PR #262) are active.
- [ ] SI v2 controller is PAUSED / L3_REPOSITORY_ONLY.
- [ ] Live trading is forbidden; all bots dry_run=true.
- [ ] Rainbow producer is deployed, healthy, and producing fresh signals.
- [ ] Measurement Ledger shows ≥ 10 scoring-eligible cycles.
- [ ] Walk-forward evaluator is executed by the scheduled SI v2 loop.
- [ ] Approval gate for applying proposals is implemented and documented.
- [ ] No auto-execution of SI v2 proposals exists; human approval is required.
- [ ] Relevant docs (current-state + roadmap v2) are updated to reflect Phase 2.1 status.
- [ ] At least one audit/context doc explains how 2.1 was achieved and which
      safety constraints remain in place.

---

## 5. Non-Goals

The following are explicitly out of scope for Phase 2.1:

- Enabling live trading or changing the global state machine away from LIVE_FORBIDDEN.
- Allowing SI v2 to autonomously apply changes without human approval.
- Rewriting strategies, models, or the core signal engine.
- Changing the overall safety architecture (RiskGuard, Kill Switch, Shadowlock).

These may be considered in later phases (2.2, 3.x) once Phase 2.1 is complete.
