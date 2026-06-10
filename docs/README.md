# Documentation Index

This directory contains the canonical repository documentation and the archived
context trail for Trading Hub.

## Canonical docs

- `../README.md` — repository overview, safety rules, and workflow guardrails.
- `../AGENTS.md` — agent safety and architecture guide.
- `../SOUL.md` — project identity and operating principles.
- `git-hygiene.md` — tracked vs ignored file policy.
- `state/current-operational-state.md` — current validated operational snapshot.
- `context/trading-dashboard-surface-audit-20260603.md` — dashboard surface audit and operator-view notes.
- `context/trading-dashboard-external-access-20260602.md` — dashboard external access / Docker socket notes.
- `specs/runtime-safety-contract.md` — RiskGuard and ShadowLogger runtime safety contract (issue #22).
- `decisions/ADR-2026-06-10-watchdog-ownership.md` — Watchdog ownership boundary ADR (issue #23).
- `self_improvement_v2/docs/README.md` — SI v2 documentation index (issue #32).

## Subdirectories

### `context/`
Append-only historical reports, incident notes, migration artifacts, cleanup
reports, dashboard surface audits, external-access notes, and other time-
stamped context. Treat this as audit trail material, not as the canonical
current state.

### `specs/`
Canonical specifications and safety contracts for the SI v2 system.

### `state/`
Current or near-current snapshots of the fleet and repo state.

### `decisions/`
Decision records and policy sync notes.

### `runbooks/`
Operational procedures and response playbooks.

### `plans/`
Implementation plans and scoped work proposals.

## How to use this folder

- Read the canonical docs first when onboarding or before changing behavior.
- Use `context/` when you need the history behind a change.
- Use `state/` when you need the latest validated snapshot.
- Keep new context entries date-stamped and concise.
