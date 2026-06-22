# Phase 5A — Shadow/Paper Readiness Proof Plan

## 1. Goal

Define a reproducible, documentation-backed proof contract for SI v2 Phase 5 that demonstrates the end-to-end shadow/paper readiness path without orders, runtime mutation, config writes, strategy writes, Docker changes, Compose changes, Cron changes, or capital execution.

This plan establishes the contract for two deterministic paths:

- `success_path`
- `forced_blocked_path`

The proof must remain artifact-only and must not introduce any live-trading or self-healing behavior.

## 2. Current prerequisites

Validated prerequisites available on `main` after merge commit `475ea07466a89c3017ca1dc2e9a1c04481ff1712`:

- Phase 4 monitoring evaluator proof is merged.
- SI v2 loop evidence exists and is repo-persistent.
- Dynamic Exit Engine is implemented.
- Strategy Codex mapping is implemented.
- Dynamic Exit Evidence Gate is implemented.
- Monitoring evaluator proof is documented.
- Runtime/trading risk remains at zero for this scope.

The current worktree is documentation-focused and must preserve the read-only / artifact-only boundary.

## 3. Success Path contract

The `success_path` must model a clean, reproducible shadow/paper readiness cycle with all required inputs present and valid.

Required properties:

- all 4 bots are represented
- Strategy Codex mappings are available
- Dynamic Exit Evidence is valid
- Exit Evidence Gate does not hard-block
- Profitability Gate does not hard-block
- Monitoring verdict is `green` or explicitly justified `yellow`
- Apply remains artifact-only
- action count is `0`
- mutation count is `0`

Success path behavior must confirm that the loop can proceed through evidence evaluation and reporting without any live-capital side effects.

## 4. Forced-Blocked Path contract

The `forced_blocked_path` must model a deliberately unsafe or incomplete cycle that is blocked correctly by the gates.

Required properties:

- at least one controlled failure is injected
- the failure may be stale telemetry, missing ATR, insufficient candles, or low risk/reward
- Dynamic Exit Gate or Monitoring blocks correctly
- monitoring reflects the unsafe state
- no promotion occurs
- no apply action occurs
- action count is `0`
- mutation count is `0`

The blocked path must prove that the system refuses to promote an unsafe state and that the report remains deterministic and reproducible.

## 5. Required input artifacts

The Phase 5 proof should consume only repository-local artifacts and deterministic fixtures.

Expected inputs:

- SI v2 source modules used by the proof harness
- Strategy Codex mapping artifacts
- Dynamic Exit Evidence artifacts
- monitoring evaluator evidence artifacts
- deterministic fixture data for success and blocked cases
- any read-only state snapshots required to simulate telemetry or risk inputs

The proof must not depend on exchange I/O, mutable runtime state, or external secrets.

## 6. Required output artifacts

The Phase 5 proof must produce the following artifacts:

```text
reports/phase2/shadow_paper_readiness/shadow_paper_readiness_success_20260622.json
reports/phase2/shadow_paper_readiness/shadow_paper_readiness_blocked_20260622.json
reports/phase2/shadow_paper_readiness/shadow_paper_readiness_report_20260622.md
```

Output artifacts must record the evidence path, gate outcomes, and explicit safety assertions.

## 7. Gate expectations

The proof must validate the following gate behavior:

- Exit Evidence Gate validates good evidence and blocks invalid evidence
- Profitability Gate does not hard-block the success path
- forced-blocked inputs trigger a correct block
- no gate ever promotes to a live-capital action
- apply is artifact-only in both paths
- result summaries preserve `action_count = 0` and `mutation_count = 0`

Any unsafe input must stop the path before promotion.

## 8. Monitoring expectations

Monitoring output must be explicit and deterministic.

Expected behavior:

- success path reports `green` or a clearly justified `yellow`
- forced-blocked path reports the unsafe state clearly
- the monitoring report must align with the gate result
- no hidden remediation or auto-healing is allowed
- no runtime side effect may occur from monitoring

Monitoring must explain the decision, not enact it.

## 9. Safety constraints

Explicitly excluded from Phase 5A and Phase 5B:

- no orders
- no exchange I/O
- no restarts
- no Docker changes
- no Compose changes
- no Cron changes
- no runtime mutation
- no config writes
- no strategy writes
- no automated healing actions
- no capital execution

Additional safety requirements:

- preserve repo-persistent evidence only
- keep all outputs deterministic
- keep the proof reversible and inspectable
- do not broaden scope into deployment, live readiness, or infrastructure changes

## 10. Validation commands

Run the following validation commands after writing this plan:

```bash
git diff --check
PYTHONPATH=self_improvement_v2/src python3 -m pytest self_improvement_v2/tests/test_no_forbidden_patterns.py -q
```

These checks validate formatting hygiene and ensure the plan remains within the repository's forbidden-pattern policy.

## 11. Definition of Done

Phase 5A is done when all of the following are true:

- this plan document exists in `docs/context/`
- the success-path and forced-blocked-path contracts are defined
- required inputs and outputs are enumerated
- gate and monitoring expectations are explicit
- safety constraints are explicit
- validation commands are recorded
- the document does not introduce any live-trading, runtime-mutation, or config-write pathway

Phase 5B can begin only after this plan is published and reviewed.
