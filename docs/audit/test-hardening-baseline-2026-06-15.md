# Test-Hardening Baseline Audit — 2026-06-15

## Scope
Baseline audit for the focused Phase 2 test-hardening branch.

## Branch / HEAD
- Branch: `test/phase2-critical-coverage-hardening`
- HEAD: `b61c90c`

## Existing valid test commands

### Root repository
- `python3 -m pytest tests -q` → **passes** (80 tests, warnings only)
- `python3 -m pytest -q -m "not runtime and not docker and not slow"` → **passes** after adding root `pytest.ini`
- `uv run --with pytest-cov python3 -m pytest -q --cov=. --cov-report=term-missing --cov-report=xml -m "not runtime and not docker and not slow"` → **passes** and produces coverage XML

### self_improvement_v2
- `cd self_improvement_v2 && PYTHONPATH=src:. python3 -m pytest tests -q` → **passes** (144 tests)
- Root-level `python3 -m pytest -q` is **not** a good command for this subproject because repo-wide discovery hits unrelated directories.

### orchestrator/control
- `cd orchestrator/control && PYTHONPATH=/home/hermes/projects/trading python3 -m pytest tests -q` → **passes** (144 tests)

## Current failures / skips observed during baseline

### Unavailable `pytest` entrypoint
- `pytest -q` from repo root failed with:
  - `/usr/bin/bash: line 3: pytest: command not found`

### Repo-wide collection before root config
- `python3 -m pytest -q` from repo root initially failed with collection/import errors across unrelated subprojects.
- After adding root `pytest.ini` with narrow `testpaths = tests`, root-safe discovery is now limited to the root `tests/` tree.

### Coverage tooling
- Direct `python3 -m pytest --cov=...` initially failed because `pytest-cov` was not installed in the shell.
- `uv run --with pytest-cov ...` works as an isolated, report-only coverage path.

## Root test config status
- No root-level `pytest.ini` existed before this hardening pass.
- No root-level `.coveragerc` existed before this hardening pass.
- Added now:
  - `pytest.ini`
  - `.coveragerc`

## Recommended implementation plan
1. Keep the root default safe suite narrow and deterministic.
2. Add temp-path Shadowlock coverage for:
   - append-only writes
   - sequencing / hashing
   - quarantine / dead-letter
   - JSONL rebuild and incremental update
   - query helpers
   - healthcheck freshness
3. Add static Docker contract tests for Freqtrade fleet isolation and localhost-only exposure.
4. Add explicit safety-path tests for control-plane file loading and reconcile rollback.
5. Add deterministic unit tests for the legacy regime detector.
6. Add Rainbow read_only freshness round-trip coverage into SI v2 cycle state.
7. Validate with the safe root suite plus targeted subproject suites.
