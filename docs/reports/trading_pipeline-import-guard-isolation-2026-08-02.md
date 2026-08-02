# trading_pipeline Import-Guard Isolation — Report

**Date:** 2026-08-02
**Issue:** #674
**Execution class:** A1 (repository-only)
**Branch:** `fix/issue-674-trading-pipeline-import-guard-isolation-2026-08-02`

## Defect

`self_improvement_v2/tests/test_trading_pipeline.py::TestImportGuard::test_kill_switch_disabled_fallback`
asserted fallback behavior on the **live-imported** pipeline module:

```python
import si_v2.loop.trading_pipeline as pipeline
assert pipeline._is_kill_active() is False
```

When `freqtrade.shared.kill_switch` is importable (which it is when tests run
from the repository root — the real `freqtrade/` namespace package shadows any
installed package), the pipeline module binds the **real** kill-switch
functions, which read the **physical** kill-switch file
(`var/kill_switch.json` host fallback or `freqtrade/shared/kill_switch.json`).
The test result then depends on the physical file state:

- Physical `NORMAL` → test passes by accident.
- Physical `HALT_NEW`/`EMERGENCY` → test **fails**.

## Reproduction (2026-08-02, from repo root, baseline commit `a50253a`)

```
$ python -c "import si_v2.loop.trading_pipeline as p; print(p._get_kill_mode(), p._is_kill_active())"
HALT_NEW True

$ python -m pytest self_improvement_v2/tests/test_trading_pipeline.py::TestImportGuard -q
F
FAILED test_trading_pipeline.py::TestImportGuard::test_kill_switch_disabled_fallback
```

The physical `var/kill_switch.json` on the worktree host path resolves to
`HALT_NEW`, proving the test is state-dependent. **This is exactly the defect
deferred from the C5.3 A0 preflight audit (defect J).**

## Fix — deterministic ImportError simulation without physical file access

The import-guard test now:

1. Blocks the kill-switch import deterministically via
   `monkeypatch.setitem(sys.modules, "freqtrade.shared.kill_switch", None)`
   (Python's import system raises `ImportError` when it finds `None` in
   `sys.modules` during an import — no file I/O occurs).
2. Loads the pipeline module in an **isolated namespace** via
   `importlib.util.spec_from_file_location` under a unique module name, so the
   already-imported instance is never reused.
3. Restores every `sys.modules` entry it created in a `finally:` block;
   `monkeypatch` restores the blocked kill-switch entry automatically.
4. Asserts the fallback actually engaged (`_get_kill_mode() == "NORMAL"`,
   `_is_kill_active() is False`, `_is_emergency() is False`) — proving the
   fallback functions, not the real ones, are bound.
5. Never reads, writes, or removes any physical kill-switch file.

### New tests (3)

- `test_kill_switch_disabled_fallback` — fallback defaults (replaces the
  state-dependent test).
- `test_fallback_process_signals_normal` — `process_signals` behaves like
  NORMAL mode with the fallback module bound.
- `test_fallback_never_touches_physical_file` — asserts the isolated module
  does not expose the physical kill-switch path constant (`KILL_SWITCH_PATH`).

## Test commands + counts (from repo root, venv `.venv-674`)

```
$ python -m pytest self_improvement_v2/tests/test_trading_pipeline.py -v
18 passed in 0.07s        # 15 existing + 3 new

$ python -m pytest self_improvement_v2/tests/ -q
# 3 pre-existing failures, unrelated to this change:
#   test_fleet_risk_manager.py::test_medium_winrate_returns_half   (pre-existing;
#     file is excluded from CI offline-smoke per AGENTS.md/CI contract)
#   test_runtime_ceremony_runner.py 2 tests                        (pre-existing;
#     PermissionError writing /opt/data/profiles/orchestrator/... — host-path
#     dependency, unrelated to trading_pipeline)
```

### Baseline comparison (stash of the fix, same venv)

```
$ python -m pytest ... test_trading_pipeline.py::TestImportGuard -q
F  → test_kill_switch_disabled_fallback FAILED (state-dependent)
$ python -m pytest ... (after fix)
18 passed
```

The three other failures reproduce identically with and without the fix —
they are pre-existing and environment-related, not regressions.

## Files changed

- `self_improvement_v2/tests/test_trading_pipeline.py` — import-guard
  isolation (module docstring updated with isolation contract).

## Validation

- `git diff --check`: clean
- Ruff: clean (checked below)
- No production module changed (`trading_pipeline.py` untouched)
- No physical kill-switch file read/written by the tests
- Runtime mutation: NONE (A1)
