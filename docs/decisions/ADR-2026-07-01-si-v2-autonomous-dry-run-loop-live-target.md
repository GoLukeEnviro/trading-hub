# ADR-2026-07-01 — SI-v2 Autonomous Dry-Run Loop with Live-Target Architecture

## Status

Accepted

## Context

SI-v2 has proven that it can read real data from the 4-bot dry-run fleet, create qualified ShadowProposals, execute a controlled canary apply, measure it, and reach KEEP_CANARY_OVERLAY.

The old architecture required human approval for every mutating apply. This blocks the intended self-improvement loop.

The project goal is autonomous dry-run optimization first, then live-trading readiness with real capital later.

## Decision

Replace per-apply human gating in dry-run with policy-gated autonomy.

The default operational target becomes:

**AUTONOMOUS_DRY_RUN**
The system may automatically apply qualified ShadowProposals in dry-run only when all policy gates pass.

Live trading remains a target architecture but is not enabled by this ADR.

## Non-Negotiable Dry-Run Gates

- `dry_run=true` for all active fleet bots
- target must be canary-first
- candidate must be allowlist-compatible
- RiskGuard must PASS
- Kill Switch must be NORMAL
- no active conflicting measurement window
- rollback snapshot must be written before or with apply
- audit event must be written
- measurement plan must be scheduled or emitted
- cooldown/concurrency limits must pass
- no secrets or live exchange keys involved

## Live-Target Position

Live trading is not forbidden as a product goal.

Live is a future operating mode requiring its own readiness gates, capital limits, exchange-key scope, kill-switch behavior, loss limits, and explicit mode transition.

This ADR does not enable live trading.

## Consequences

- Human approval is removed from normal dry-run apply decisions.
- Human involvement moves to architecture/mode transitions, not every dry-run iteration.
- Docs and code must stop treating all mutation as human-gated by default.
- Autonomy must be auditable and reversible.
- The previous human-gated apply phase (ADR-2026-06-27) is recognized as a necessary historical step that proved the controlled apply chain. It is superseded for dry-run by this ADR.
