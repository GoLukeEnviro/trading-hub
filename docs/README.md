# Documentation Index

This directory contains the canonical repository documentation and the archived
context trail for Trading Hub.

## Canonical docs

|- **Glossary** — Terminology definitions for agents and operators (`docs/glossary.md`).
|- **Decommissioning Register** — Decommissioned components and cleanup candidates (`docs/decommissioning-register.md`).
|- `../README.md` — repository overview, safety rules, and workflow guardrails.
|- `../AGENTS.md` — agent safety and architecture guide.
|- `../SOUL.md` — project identity and operating principles.
|- `git-hygiene.md` — tracked vs ignored file policy.
|- `CHANGELOG.md` (root) — Keep-a-Changelog change history.
|- `ARCHITECTURE.md` — System architecture with Mermaid diagrams.
|- `architecture/si-v2-autonomous-dry-run-loop.md` — SI-v2 detailed architecture.
|- `state/current-operational-state.md` — current validated operational snapshot.
|- `decisions/README.md` — ADR index and approval marker registry.
|- `decisions/ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md` — Current SI-v2 policy.
|- `specs/runtime-safety-contract.md` — RiskGuard and ShadowLogger runtime safety contract.
|- `specs/production-risk-limits-spec.md` — Production risk limits (Track B).
|- `specs/incident-response-runbooks.md` — Incident response and go-live runbooks (Track B).
|- `runbooks/kill-switch.md` — Kill-Switch operational runbook.
|- `references/freqtrade-kill-switch-procedure.md` — Kill-switch procedure reference.
|- `self_improvement_v2/README.md` — SI v2 subsystem overview, module map, and entry points.
|- `tools/README.md` — Utility scripts documentation (export_trade_history, freqforge, riskguard).
|- GitHub Issue **#423** — Canonical live roadmap.

### Canon vs. historical documents

Treat the following as canonical sources of truth for the current system:

- Root README.md and AGENTS.md for architecture and safety rules.
- docs/ARCHITECTURE.md for the system architecture.
- docs/state/current-operational-state.md for the current validated runtime snapshot.
- GitHub Issue #423 for the live roadmap.
- docs/glossary.md for terminology definitions.
- docs/decisions/README.md for ADR and approval marker index.

**Historical / superseded documents:**

- `roadmap/roadmap-v2-blocker-first-runtime-ownership.md` — Historical roadmap (superseded by #423).
- `roadmap/implementation-roadmap.md` — Original implementation roadmap (superseded).
- `roadmaps/SI_V2_CONTINUOUS_IMPLEMENTATION_ROADMAP.md` — Controller queue document (historical).
- `state/canonical-trading-status.md` — Fleet snapshot from 2026-06-15 (superseded).
- `state/issues-55-61-evidence-matrix.md` — Phase 1 evidence (all issues closed).
- `state/phase-1-intelligence-epic.md` — Phase 1 epic (all issues closed).
- `state/post-pr-160-architecture.md` — Pre-Phase 2 architecture (superseded).
- `state/autopilot/` — Autopilot system snapshots (replaced by SI-v2 Active Cycle Runner).
- `specs/IMPLEMENTATION_STATUS_AND_NEXT_STEPS.md` — 2026-06-10 status (all items implemented).
- `GAP-REPORT-2026-06-15-TRADING-HUB.md` — Gap register (superseded by #423).

Everything under docs/context/ and docs/archive/ is audit history and must not override
the canonical state documents.

### Additional entry points (outside `docs/`)

- `self_improvement_v2/README.md` — SI v2 subsystem overview, module map, and entry points.
- `tools/README.md` — Utility scripts: export_trade_history, freqforge shadow evaluator, riskguard.

## Subdirectories

### `architecture/`
Detailed architecture documents. Currently contains the SI-v2 autonomous dry-run loop
detail architecture.

### `context/`
Append-only historical reports, incident notes, migration artifacts, cleanup
reports, dashboard surface audits, external-access notes, and other time-
stamped context. Treat this as audit trail material, not as the canonical
current state.

### `specs/`
Canonical specifications and safety contracts for the SI v2 system.

### `state/`
Current or near-current snapshots of the fleet and repo state.
`current-operational-state.md` is the canonical runtime snapshot.
Older state files are marked SUPERSEDED and reference the current file.

### `decisions/`
Decision records (ADRs) and approval markers. Index in `decisions/README.md`.

### `runbooks/`
Operational procedures and response playbooks.

### `reports/`
Proof reports, validation results, and alignment reports.

### `roadmap/`
Roadmap documents. Issue #423 is the current live roadmap.
Both `roadmap-v2` and `implementation-roadmap` are historical.

### `roadmaps/`
Historical directory. Contains `SI_V2_CONTINUOUS_IMPLEMENTATION_ROADMAP.md` — a
separate document about the SI v2 controller's continuous implementation queue.
Distinct from `roadmap/`. Both directories remain; the naming collision is a known
cosmetic issue.

### `references/`
Operational reference documents (kill-switch procedure, etc.).

### `incidents/`
Incident reports for post-mortem documentation.

### `archive/`
Historical documents that have been superseded. Currently contains:
- `gap-reports/` — Pre-2026-06-05 GAP reports and deprecated plans.

### `plans/`
Implementation plans and scoped work proposals.

## How to use this folder

- Read the canonical docs first when onboarding or before changing behavior.
- Use `glossary.md` for terminology definitions.
- Use `decommissioning-register.md` to check component status before modifying code.
- Use `context/` when you need the history behind a change.
- Use `state/current-operational-state.md` when you need the latest validated snapshot.
- Use `decisions/README.md` to find the relevant ADR or approval marker.
- Keep new context entries date-stamped and concise.
