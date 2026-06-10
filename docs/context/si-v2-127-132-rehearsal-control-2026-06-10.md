# SI v2 #127–#132 Rehearsal-Control Layer

Timestamp (UTC): 2026-06-10T17:09:11Z
Worktree: `/opt/data/trading-worktrees/si-v2-127-132`
Branch: `feat/si-v2-issue-127-132-rehearsal-control`
Base: `origin/main` @ `85aa1add80d0573e5ffbb346a7ba6ce646d9cdb2`

## Scope

Implemented offline-only governance, evidence, rehearsal-control, and static validation artifacts for:

- #127 No-live-trading invariant tests
- #128 Dry-run Evidence Schema
- #129 Runtime Preflight Checklist Report
- #130 Shadow-mode Rehearsal Report Template
- #131 External Adapter Boundary Audit
- #132 Rehearsal Artifact Archive Manifest

## Safety Boundary

No runtime, Docker, Freqtrade bot, exchange, deployment, or live-trading command was executed.
All work was performed in the separate `/opt/data` worktree because the originally requested `/home/hermes/projects/trading-worktrees` path was not writable by the current user.
The dirty main worktree under `/home/hermes/projects/trading` was not modified.

## Validation Summary

Validated from repo root with the SI v2 uv project environment:

- `python -m compileall -x '(support|fixtures)' self_improvement_v2` — PASS
- `uv run --project self_improvement_v2 pytest self_improvement_v2 -q` — PASS
- `uv run --project self_improvement_v2 ruff check self_improvement_v2` — PASS
- `git diff --check` — PASS
- JSON parse validation for all `self_improvement_v2/**/*.json` — PASS

## Notes

`self_improvement_v2` now includes dev dependency metadata for `pytest`, `ruff`, and `httpx` so the full offline test suite can run reproducibly with `uv run --project self_improvement_v2 ...`.

## Live Trading State

`LIVE_FORBIDDEN` remains the assumed/default state. This work does not authorise live trading, `dry_run=false`, real orders, real adapters, Docker restarts, or exchange connectivity.
