# Documentation Index

This directory contains the canonical repository documentation and the archived
context trail for Trading Hub.

## Canonical docs

- `../README.md` — repository overview, safety rules, and workflow guardrails.
- `../AGENTS.md` — agent safety rules and architecture guide.
- `../SOUL.md` — project identity and operating principles.
- `git-hygiene.md` — tracked vs ignored file policy.
- `state/current-operational-state.md` — current validated operational snapshot.

## Subdirectories

### `context/`
Append-only historical reports, incident notes, migration artifacts, cleanup
reports, and other time-stamped context. Treat this as audit trail material,
not as the canonical current state.

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
