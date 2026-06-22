# SI v2 Real-Capital Go/No-Go Checklist — Documentation Only

**Generated:** 2026-06-22T07:42:09Z
**Branch:** `docs/si-v2-real-capital-go-no-go-checklist`
**Scope:** documentation-only checklist; no trading authorization implied.

## 1. Goal

Define the mandatory Go/No-Go checklist for SI v2 so that shadow/paper readiness cannot be mistaken for live-capital readiness.

This checklist is a control document, not an execution gate. It exists to make the boundary explicit between:

- proof that the system can reason safely in shadow/paper mode, and
- any separate future review that might consider real-capital operations under explicit human approval.

## 2. Current proof stack

The current proof stack referenced by this checklist is:

- Dynamic Exit Engine
- Strategy Codex
- Dynamic Exit Evidence Gate
- Fleet Monitoring Evaluator
- Monitoring Evaluator Proof
- Shadow/Paper Readiness Proof
- Success path `GREEN`
- Forced-blocked path `BLOCKED_AS_EXPECTED`
- `action_count = 0`
- `mutation_count = 0`
- `capital_execution = disabled`

Supporting evidence artifacts currently documented in the repo include:

- `docs/context/2026-06-22-si-v2-shadow-paper-readiness-proof.md`
- `docs/context/2026-06-22-si-v2-monitoring-evaluator-proof.md`
- `docs/context/2026-06-22-si-v2-dynamic-exit-evidence-merge-proof.md`
- `docs/context/2026-06-22-si-v2-dynamic-exit-engine-phase-1.md`

## 3. Explicit non-authorization statement

This document does **not** authorize:

- real capital deployment
- exchange-order execution
- `dry_run=false`
- live trading of any kind
- automated capital increase
- automated strategy promotion
- config mutation for live execution

The system remains in a documentation / readiness-evidence phase only.

## 4. Mandatory Go criteria

A future real-capital review must require all of the following to be true:

- SI-v2 loop proof present and current
- Dynamic Exit Proof present and current
- Strategy Codex present and current
- Monitoring Proof present and current
- Shadow/Paper Success Path `GREEN`
- Forced-blocked path `BLOCKED_AS_EXPECTED`
- `action_count = 0`
- `mutation_count = 0`
- `capital_execution = disabled`
- Kill-switch / pause concept documented and operationally understood
- Alert-routing concept documented and tested
- Manual approval gate documented and required

## 5. Mandatory No-Go blockers

Any one of the following is a hard blocker:

- stale telemetry
- missing heartbeat
- missing stop-loss
- missing take-profit
- missing risk/reward ratio
- dynamic exit gate blocked
- profitability gate blocked
- monitoring red
- unresolved CI failure
- unresolved test failure
- unresolved runtime drift
- unclear credential path
- any strategy/config write outside explicit approval
- any order-capable path without explicit approval
- any request to set `dry_run=false` without a separate approval PR

## 6. Required manual approval gate

Before any live-capital discussion can proceed, a separate human approval must explicitly specify:

- scope
- exchange
- strategy
- bot(s)
- capital limits
- timeframe
- monitoring owner
- rollback plan
- kill-switch expectations
- approval expiry or review window

Without that explicit approval, this checklist remains non-authorizing.

## 7. Required safety artifacts

The following safety artifacts must exist and be current before any separate approval can even be considered:

- shadow/paper proof report
- dynamic exit proof report
- monitoring proof report
- strategy codex reference
- kill-switch documentation
- pause / halt procedure
- alert-routing procedure
- rollback procedure
- validation evidence attached to the relevant change set

## 8. Required monitoring state

Monitoring must be in a clearly healthy state before any live-capital review:

- telemetry fresh
- heartbeat present
- monitoring verdict `green`
- no unresolved alert backlog
- no unexplained runtime drift
- no unreviewed evidence gaps
- no hidden mutation counters
- no ambiguous capital-execution path

If monitoring is degraded, the correct response is to block and investigate, not to loosen gates.

## 9. Required rollback / pause / kill-switch conditions

A live-capital review must define the exact response for these conditions:

- telemetry freshness loss
- heartbeat loss
- monitoring red
- dynamic exit regression
- profitability regression
- unresolved CI/test regression
- runtime drift
- credential uncertainty
- strategy/config drift
- any unexpected order-capable path

At minimum, the review must document how to:

- pause new entries
- preserve current evidence
- preserve logs
- preserve rollback state
- activate or respect the kill switch

## 10. Required validation commands

Before publishing the checklist PR, run:

```bash
git diff --check
PYTHONPATH=self_improvement_v2/src python3 -m pytest self_improvement_v2/tests/test_no_forbidden_patterns.py -q
```

These commands validate formatting hygiene and ensure the repository still rejects forbidden live-trading patterns.

## 11. Definition of Done

This document is complete when all of the following are true:

- the checklist is written and reviewed as documentation only
- the non-authorization statement is explicit and unambiguous
- Go criteria and No-Go blockers are spelled out
- the manual approval gate is explicit
- safety artifacts are referenced
- monitoring requirements are explicit
- rollback / pause / kill-switch conditions are explicit
- validation commands are recorded
- the resulting change remains free of order execution, exchange I/O, runtime mutation, config writes, strategy writes, Docker changes, Compose changes, or Cron changes
- no real capital is authorized
- no `dry_run=false` is authorized
- no exchange-order path is authorized
- a separate approval PR is still required
