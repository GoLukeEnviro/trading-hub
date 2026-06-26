# SI v2 Dynamic Exit Engine Phase 1 — 2026-06-22

## Scope

Implemented the first post-loop SI v2 improvement lever requested in the task: a pure, deterministic dynamic exit engine for ATR / Bollinger-distance / fixed fallback calculations.

## What changed

Added a new risk package:

- `self_improvement_v2/src/si_v2/risk/__init__.py`
- `self_improvement_v2/src/si_v2/risk/dynamic_exits.py`

Added tests:

- `self_improvement_v2/tests/test_dynamic_exits.py`

## Behavior

The module now provides:

- `calculate_dynamic_exit(...)`
- `calculate_dynamic_exit_from_row(...)`
- `DynamicExitResult`

Supported modes and directions:

- modes: `fixed`, `atr`, `bollinger_distance`
- directions: `long`, `short`

Safety / validation behavior:

- no exchange I/O
- no runtime mutation
- no Docker / Compose / cron changes
- blocked results for missing columns, missing ATR, missing Bollinger values, insufficient candles, invalid entry price, invalid ATR, inconsistent Bollinger values, and invalid parameter values
- deterministic rounding with `ROUND_HALF_EVEN` at `0.000001`
- conservative low-volatility floor and high-volatility cap behavior for risk distance

## Validation evidence

Targeted and full validation completed successfully:

- `PYTHONPATH=self_improvement_v2/src python3 -m pytest self_improvement_v2/tests/test_dynamic_exits.py -q`
- `PYTHONPATH=self_improvement_v2/src python3 -m pytest self_improvement_v2/tests -q`
- `uv run --project self_improvement_v2 ruff check self_improvement_v2/src self_improvement_v2/tests`
- `uv run --project self_improvement_v2 --with mypy mypy --follow-imports=skip self_improvement_v2/src/si_v2/risk/dynamic_exits.py`

## Type-check note

A full `mypy self_improvement_v2/src` run still reports many pre-existing errors in unrelated modules across the SI v2 tree. The new risk module itself is clean under isolated type checking.

## Safety state preserved

- no live trading
- no `dry_run=false`
- no config writes
- no strategy writes
- no exchange I/O
- no runtime infrastructure mutation

## Next suggested step

Integrate the new exit calculations into the next evidence / gate layer only after the broader SI v2 typing backlog is addressed or explicitly scoped away.
