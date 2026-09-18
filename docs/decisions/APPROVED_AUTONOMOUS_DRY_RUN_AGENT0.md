# Autonomous Dry-Run Activation Approval — Agent0

**Marker:** `APPROVED_AUTONOMOUS_DRY_RUN_AGENT0`
**Date:** 2026-09-18
**Author:** Luke (GoLukeEnviro)
**Status:** Active

---

## Approval

Luke authorizes the activation of `AUTONOMOUS_DRY_RUN` on Agent0, exclusively
for the existing dry-run fleet and only after all gates of the master GOAL
(2026-09-18) are completed:

- RiskGuard baseline contract v1 developed and merged;
- conservative RiskGuard state initialized on Agent0;
- SI-v2 apply chain activated against the existing dry-run fleet;
- a qualified proposal applied canary-first if one actually exists;
- snapshot, measurement and necessary rollback executed automatically;
- scheduler and Telegram notifications activated for autonomous dry-run
  operation;
- issue, state and evidence documentation updated.

## Scope

- **Host:** Agent0 (`agent0-1`)
- **Bots:** the three allowed dry-run bots (`freqtrade-freqforge`,
  `freqtrade-freqforge-canary`, `freqtrade-regime-hybrid`); canary-first
- **Parameters:** the existing parameter allowlist
  (`safe_parameters.SAFE_PARAMETERS` with the accepted ranges)
- **Mode:** `AUTONOMOUS_DRY_RUN` — dry-run only, no live trading
- **Gates:** RiskGuard- and kill-switch-required; snapshot- and
  rollback-required; measurement-required

## Explicitly not authorized

- `dry_run=false`; real capital or real orders; live exchange keys
- live canary or live fleet; risk-capital limit increases
- new pairs or strategies outside the existing allowlists
- weakening of kill switch, RiskGuard or rollback obligations
- activation of `freqai-rebel`; holdout access or Gate-0 decisions

## Constraints

- No cryptographic signature is invented; this marker is the human-readable
  authorization record and references the operator GOAL.
- Approval eligibility is not live approval. Any apply stays policy-gated,
  canary-first, snapshot-backed, rollback-capable, measurement-bound and
  audit-logged.
- The kill switch must be `NORMAL` and RiskGuard must derive `PASS` at
  evaluation time; otherwise the stage stays fail-closed.
- Runtime execution of a prepared canary change is wired only after the R7A
  topology has been verified end to end; until then the stage prepares and
  records, and applies nothing.

## Reference

Operator GOAL of 2026-09-18 (`MASTER-GOAL: RiskGuard v1 fertigstellen und
SI-v2 auf Agent0 vollständig in den sicheren Modus AUTONOMOUS_DRY_RUN
überführen`), Owner authorization section. Gates 1-3 evidence:
PR #750 / merge `586f13c` (contract), RiskGuard state `167a7e14…` (runtime),
chain proof `NO_QUALIFIED_PROPOSAL` (no canary candidate existed).
