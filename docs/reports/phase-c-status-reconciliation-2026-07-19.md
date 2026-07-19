# Phase C Status Reconciliation — Premature Complete Corrected

**Date:** 2026-07-19
**Phase:** C (Gate-0 Strategy Evidence) — exit gate `edge_decision_recorded` (NOT YET SATISFIED)
**Execution class:** A1 (repository-only, status correction)
**Issue:** #604 (parent), #651 (A2 snapshot-fetch)
**Branch:** `docs/phase-c-status-reconciliation-2026-07-19`
**Base:** `origin/main` at `e08bb9e`

## Correction

PR #650 set Phase C to `complete` after Luke signed the strategy selection
and frozen manifest on #604. This was premature: the exit gate
`edge_decision_recorded` requires the actual edge decision (PASS/EXTEND/
REJECT/INVALID), which depends on snapshot acquisition → holdout inspection →
evaluation. Only 2 of 5 sub-steps were complete.

This PR corrects Phase C back to `in_progress` and records the precise sub-step
status in the state file.

## Phase C sub-step status

| Sub-step | Status | Evidence |
|---|---|---|
| Strategy selected | ✅ PASS | `FreqForge_Override` — Luke signed on #604 |
| Manifest frozen | ✅ PASS | `APPROVED_GATE0_STRATEGY_AND_MANIFEST` on #604 |
| Snapshot acquisition | ⏳ `PENDING_A2` | A2 issue #651 created with full execution contract; Luke's time-limited marker required |
| Holdout inspected | ❌ NO | Blocked by snapshot |
| Edge decision | ⏳ `PENDING` | Blocked by holdout |

## Changes

| File | Change |
|---|---|
| `config/governance/canonical-roadmap.yaml` | revision 5; Phase C `complete` → `in_progress` |
| `docs/roadmap/canonical-program-roadmap.md` | Regenerated |
| `docs/state/current-operational-state.md` | Phase C sub-status table; frozen manifest summary; A2 next step; revision observed 5 |

## A2 snapshot-fetch issue

Issue #651 created with full execution contract:
- Exact data specification (3 pairs, 15m, 18 months, 4 partition windows)
- Allowed public Bitget endpoints (read-only, no credentials)
- Target host and path (`/opt/data/gate0-snapshot/`)
- Rate/size limits, retry policy
- Hash and provenance format (per-file SHA-256 + manifest JSON)
- Hard prohibitions (no strategy execution, no holdout inspection, no evaluation)
- Cleanup scope (only target directory)
- Audit requirements (every API call logged)
- Required A2 marker format (`APPROVED_A2_GATE0_SNAPSHOT_FETCH`)

Issue #651 is `BLOCKED_BY_MISSING_A2_MARKER` until Luke issues the time-limited marker.

## Scope

- A1 only: repository documentation, roadmap status, state file, evidence report.
- No runtime mutation. No data fetch. No strategy execution. No holdout inspection.
- This is a declared status reconciliation (spec §8.1: phase status correction with no DAG change).

## Status

`READY_FOR_HUMAN_MERGE` — only Luke merges.