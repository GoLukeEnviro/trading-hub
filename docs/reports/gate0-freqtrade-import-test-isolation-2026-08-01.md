# Gate-0 Freqtrade Import Test Isolation

**Date:** 2026-08-01
**Author:** Hermes (trading-hub-orchestrator)
**Issue:** #681
**Branch:** `fix/gate0-freqtrade-import-test-isolation-2026-08-01`
**Base SHA:** `95519773068e55a0b0719d6cb06bdd481d0c1947` (origin/main)

## Observation

### Original test failure

```
Test: TestFreqtradeImport::test_strategy_imports_with_stubs
File: self_improvement_v2/tests/test_c53_corrective.py
Exception: ModuleNotFoundError: No module named 'freqtrade.vendor'
```

### Baseline reproduction (from repo root)

```bash
cd /opt/data/projects/trading-hub-worktrees/a0-preflight-c54
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/trading-hub-gate0-import-pycache \
  TMPDIR=/tmp/trading-hub-gate0-import \
  PYTHONPATH=.../self_improvement_v2/src \
  uv run -p 3.11 python -B -m pytest \
  self_improvement_v2/tests/test_c53_corrective.py::TestFreqtradeImport::test_strategy_imports_with_stubs \
  -vv -p no:cacheprovider
```

**Exit code:** 1
**Result:** FAILED

### find_spec() diagnostics

```python
import importlib.util

for name in (
    "freqtrade",
    "freqtrade.strategy",
    "freqtrade.vendor",
    "freqtrade.vendor.qtpylib",
    "freqtrade.vendor.qtpylib.indicators",
):
    print(name, "=>", importlib.util.find_spec(name))
```

Output:
```
freqtrade => ModuleSpec(name='freqtrade', loader=None,
  submodule_search_locations=_NamespacePath(['.../freqtrade']))
freqtrade.strategy => None
freqtrade.vendor => None
freqtrade.vendor.qtpylib => ERROR ModuleNotFoundError
freqtrade.vendor.qtpylib.indicators => ERROR ModuleNotFoundError
```

## Root Cause

The repository root contains a `freqtrade/` directory **without** `__init__.py`.
Python 3.11 treats this as a **namespace package**. When running from the repo root:

1. `importlib.util.find_spec("freqtrade")` finds the namespace package
2. `import freqtrade` **succeeds** (no `ImportError`)
3. The original test only creates stubs in the `except ImportError` branch
4. The stub-creation block is **skipped entirely**
5. The strategy imports `freqtrade.vendor.qtpylib.indicators` which does not exist
   in the namespace package → `ModuleNotFoundError`

The test passed when run from `self_improvement_v2/` because the repo root was not
on `sys.path`, so the namespace package was not discovered.

## Solution

Replaced the `try/except ImportError` pattern with a **fully controlled import
environment** using `unittest.mock.patch.dict()` on `sys.modules`.

### Key changes

- **Always** create complete Freqtrade stubs (freqtrade, freqtrade.strategy,
  freqtrade.vendor, freqtrade.vendor.qtpylib, freqtrade.vendor.qtpylib.indicators)
- **Always** create TA-Lib stubs (talib, talib.abstract)
- **Always** create a minimal pandas stub
- Use `patch.dict("sys.modules", stubs, clear=False)` to inject stubs
  without removing pre-existing modules
- `patch.dict()` automatically restores original `sys.modules` entries on exit
- No production strategy code changed

### New regression tests

| Test | Purpose |
|------|---------|
| `test_strategy_imports_with_stubs` | Original test — import with controlled stubs |
| `test_strategy_import_with_namespace_package_shadow` | Simulates local `freqtrade/` namespace package |
| `test_strategy_import_restores_sys_modules` | Sentinel modules restored after test |
| `test_strategy_import_no_module_leak` | No stub modules leak into `sys.modules` |

## Validation

### Single test from repo root

```bash
cd <REPO_ROOT>
uv run -p 3.11 python -B -m pytest \
  self_improvement_v2/tests/test_c53_corrective.py::TestFreqtradeImport::test_strategy_imports_with_stubs \
  -vv -p no:cacheprovider
```

**Exit code:** 0
**Result:** PASSED

### Full C5.3 suite from repo root

```bash
cd <REPO_ROOT>
uv run -p 3.11 python -B -m pytest \
  self_improvement_v2/tests/test_c53_corrective.py \
  -q -p no:cacheprovider
```

**Exit code:** 0
**Result:** 45 passed, 0 failed

### Single test from subdirectory

```bash
cd <REPO_ROOT>/self_improvement_v2
uv run python -B -m pytest \
  tests/test_c53_corrective.py::TestFreqtradeImport::test_strategy_imports_with_stubs \
  -vv -p no:cacheprovider
```

**Exit code:** 0
**Result:** PASSED

### Combined Gate-0 suite from repo root

```bash
cd <REPO_ROOT>
uv run -p 3.11 python -B -m pytest \
  self_improvement_v2/tests/test_c51_corrective.py \
  self_improvement_v2/tests/test_c53_corrective.py \
  self_improvement_v2/tests/test_c54_corrective.py \
  self_improvement_v2/tests/test_evaluation_bundle_v1.py \
  self_improvement_v2/tests/test_gate0_evaluation_integration.py \
  -q -p no:cacheprovider
```

**Exit code:** 0
**Result:** 145 passed, 0 failed

### Ruff

```bash
uv run -p 3.11 python -B -m ruff check \
  self_improvement_v2/tests/test_c53_corrective.py
```

**Exit code:** 0
**Result:** All checks passed

## Safety

```
holdout_inspected=NO
backtest_executed=NO
runtime_mutation=NO
strategy_production_code_changed=NO
live_trading=NO
```

## Rest Status

```
A0_PREFLIGHT_STATUS=PENDING_RE_RUN_AFTER_MERGE
PHASE_C_STATUS=IN_PROGRESS
```

## Changed Files

- `self_improvement_v2/tests/test_c53_corrective.py` — refactored
  `TestFreqtradeImport` to use controlled import environment with
  `patch.dict("sys.modules", ...)` and added 3 new regression tests
