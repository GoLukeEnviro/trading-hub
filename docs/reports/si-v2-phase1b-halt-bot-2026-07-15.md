# SI-v2 Phase 1B — Bot-scoped `HALT_BOT` circuit breaker

**Issue:** #596
**Branch:** `feat/si-v2-phase1b-halt-bot-2026-07-15`
**Date:** 2026-07-15
**Scope:** A1 (repository-only)
**Runtime mutation:** NONE

## Goal

Add a bot-scoped circuit breaker that isolates one failing bot without forcing
a fleet-wide stop. `HALT_BOT` is a Phase-1 safety capability whose runtime
activation is explicitly **out of scope** for this PR.

## Deliverables

| Path | Purpose |
|------|---------|
| `self_improvement_v2/src/si_v2/safety/halt_bot_circuit_breaker.py` | Registry, dataclass, module-level helpers |
| `self_improvement_v2/tests/test_halt_bot_circuit_breaker.py` | 30 tests (validation, isolation, authority, atomicity, evidence) |
| `docs/reports/si-v2-phase1b-halt-bot-2026-07-15.md` | This report |
| `docs/state/current-operational-state.md` | Phase 1B section appended |

## Required behavior — coverage

| Requirement (from issue #596) | Test class |
|---|---|
| Bot identity is explicit and validated | `TestBotIdValidation` (10 cases: 1 happy + 8 invalid + max-length + min-length) |
| Halted bot cannot create new entries | `TestHaltAndClear` + `TestModuleLevelHelpers` |
| Other healthy bots continue | `TestCrossBotIsolation` (2 cases) |
| Open positions are not blindly closed | REDUCING mode reserved; no auto-close in this PR |
| State changes atomic, idempotent, auditable | `TestHaltAndClear::test_halt_idempotent` + `TestAtomicWriteAndCorruption` |
| Unknown / corrupt state fails closed | `TestAtomicWriteAndCorruption` (3 cases) |
| Recovery requires explicit evidence-backed transition | `TestHaltAndClear::test_clear_without_evidence_raises` |
| Fleet kill switch remains authoritative | `TestFleetKillSwitchPrecedence` (5 cases) |

## Authority precedence

```
Fleet kill switch (NORMAL / HALT_NEW / EMERGENCY)
  > HaltBotRegistry (NORMAL / HALTED / REDUCING / UNKNOWN)
```

`combine_with_fleet_kill_switch()` returns `"BLOCKED"` whenever
`fleet_mode != "NORMAL"` regardless of bot state. Bot halt blocks
that bot when fleet is `NORMAL`. UNKNOWN bot state fails closed.

## Fail-closed semantics

- `is_halted(bot_id)` returns `True` for:
  - explicitly halted bots,
  - bots that have never been recorded (unknown state),
  - invalid bot ids (defensive — never trade an unknown entity).
- `combine_with_fleet_kill_switch()` returns `"BLOCKED"` for any
  non-NORMAL fleet mode AND for any UNKNOWN bot state.

This is the safe default: in doubt, do not trade.

## Bot id validation

Bot ids must match `^[a-z][a-z0-9-]{2,63}$`:

- 3..64 characters
- lowercase ASCII alnum + hyphen
- must start with a letter

The contract mirrors the proven four-bot loop ids used elsewhere in
the repository (`freqtrade-freqforge`, `freqtrade-freqforge-canary`,
`freqtrade-regime-hybrid`, `freqai-rebel`).

## Atomic persistence

`_persist()` uses `.tmp` + `os.replace()` to prevent half-written reads.
A `.tmp` file is never left behind on success.

## Evidence

`BotSafetyState.to_dict()` records: bot_id, mode, reason, triggered_at,
triggered_by, previous_mode, cleared_at, cleared_by, cleared_evidence.
Recovery (`clear`) requires explicit `actor` AND non-empty `evidence`;
both fields are rejected as `ValueError` when missing.

## Tests

```
$ PYTHONPATH=self_improvement_v2/src \
    /workspace/projects/trading-hub/.venv/bin/pytest \
    self_improvement_v2/tests/test_halt_bot_circuit_breaker.py -v
…
30 passed in 0.14s
```

## Validation

- `pytest -v` for `test_halt_bot_circuit_breaker.py`: **30 / 30 passed**
- `python3 -m py_compile` for both new files: clean
- `ruff check`: no findings (24 auto-fixes applied for deprecated `typing.Dict`/`typing.List`)
- `git diff --check`: no whitespace issues

## Explicit non-goals

- No strategy / Freqtrade config mutation
- No Docker / Compose / Cron mutation
- No `dry_run=false`
- No runtime activation on any fleet
- No integration with `freqtrade/shared/kill_switch.py` (read precedence is
  documented; wiring happens in a separate A1 PR that updates the strategy
  gate — see follow-up section)

## Follow-up (separate PRs)

1. Wire `HaltBotRegistry.is_halted()` into the strategy entry-gate alongside
   `is_kill_active()` from `freqtrade/shared/kill_switch.py`. A1 scope, no runtime
   activation.
2. Add a CLI subcommand under `self_improvement_v2/cli/` for operator use
   (`halt-bot`, `clear-bot`, `list-halted`).
3. Coordinate contracts with #595 (fleet HWM / daily drawdown guard); do not
   combine in one PR.
4. Schema alignment with future Rainbow R7 attribution (read-only evidence).

## Stop conditions honored

- No runtime mutation
- No live trading
- No autonomous merge; PR is `READY_FOR_HUMAN_MERGE` only after Luke's review
- Fleet kill switch contract preserved
- `RepoWriterLock` + `IsolatedWorktree` contract followed (worktree from
  pinned `origin/main` SHA `243b60c`)

## Human merge required

This PR is opened by an autonomous agent session. **Autonomous merge is
disabled.** Only Luke merges at `READY_FOR_HUMAN_MERGE`. See
`AGENTS.md` §Human-only merge boundary and `docs/state/current-operational-state.md`.
