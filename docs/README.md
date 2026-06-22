# Documentation Index

This directory contains the canonical repository documentation and the archived
context trail for Trading Hub.

## Canonical docs

- `../README.md` — repository overview, safety rules, and workflow guardrails.
- `../AGENTS.md` — agent safety and architecture guide.
- `../SOUL.md` — project identity and operating principles.
- `git-hygiene.md` — tracked vs ignored file policy.
- `CHANGELOG.md` (root) — Keep-a-Changelog change history.
- `ARCHITECTURE.md` — System architecture with Mermaid diagrams.
- `state/current-operational-state.md` — current validated operational snapshot.
- `context/trading-dashboard-surface-audit-20260603.md` — dashboard surface audit and operator-view notes.
- `context/trading-dashboard-external-access-20260602.md` — dashboard external access / Docker socket notes.
- `specs/runtime-safety-contract.md` — RiskGuard and ShadowLogger runtime safety contract (issue #22).
- `decisions/ADR-2026-06-10-watchdog-ownership.md` — Watchdog ownership boundary ADR (issue #23).
- `self_improvement_v2/docs/README.md` — SI v2 documentation index (issue #32).
- `runbooks/kill-switch.md` — Kill-Switch operational runbook (PR #220).
- `GAP-REPORT-2026-06-15-TRADING-HUB.md` — Current gap register (TD-01 through TD-10).
- `roadmap/roadmap-v2-blocker-first-runtime-ownership.md` — Canonical forward-looking roadmap.
- `roadmap/implementation-roadmap.md` — Historical implementation roadmap (superseded by roadmap-v2).
- `roadmaps/SI_V2_CONTINUOUS_IMPLEMENTATION_ROADMAP.md` — SI v2 Continuous Implementation control plane (separate document about the controller queue).

### Canon vs. historical documents

Treat the following as canonical sources of truth for the current system:

- Root README.md and AGENTS.md for architecture and safety rules.
- docs/ARCHITECTURE.md for the system architecture.
- docs/state/current-operational-state.md for the current validated runtime snapshot.
- docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md for forward-looking phases and priorities.

Everything under docs/context/ and historical GAP reports under docs/archive/
or older GAP-REPORT-*.md files are audit history and must not override
the canonical state documents.

### Additional entry points (outside `docs/`)

- `self_improvement_v2/README.md` — SI v2 subsystem overview, module map, and entry points.

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

### `roadmap/`
Canonical roadmap documents. `roadmap-v2-blocker-first-runtime-ownership.md` is the
current forward-looking roadmap. `implementation-roadmap.md` is historical.

### `roadmaps/`
⚠️ **Not a duplicate.** Contains `SI_V2_CONTINUOUS_IMPLEMENTATION_ROADMAP.md` — a
separate document about the SI v2 controller's continuous implementation queue.
Distinct from `roadmap/`. Both directories remain; the naming collision is a known
cosmetic issue. See `docs/roadmaps/` for the controller control-plane document.

### `archive/`
Historical documents that have been superseded. Currently contains:
- `gap-reports/` — Pre-2026-06-05 GAP reports and deprecated plans.
  Includes `GAP_ANALYSE.md`, `GAP-REPORT-2026-05-16.md`, `gap-report-20260516.md`,
  `bridge-plan-v0.1.md`, `hermes-integration-plan.md`.

### `plans/`
Implementation plans and scoped work proposals.

## How to use this folder

- Read the canonical docs first when onboarding or before changing behavior.
- Use `context/` when you need the history behind a change.
- Use `state/` when you need the latest validated snapshot.
- Keep new context entries date-stamped and concise.
