# Dry-Run Resilience Checks

Date: 2026-06-15
Issues: #257

## Purpose

This runbook documents the expected fail-closed behavior of the signal pipeline
when upstream services or data are degraded, stale, or absent.  All scenarios
below are covered by deterministic unit tests in `tests/test_resilience_contracts.py`.

## Safety boundary

- All tests use local fixtures and mocks.  No exchange, Docker, or live service calls.
- Runtime-dependent scenarios are marked `@pytest.mark.runtime` and skipped by default.
- No `dry_run=false` or live trading path is enabled by any test.

## Scenarios

### 1. Stale signal

| Condition | Expected behavior |
|-----------|------------------|
| Signal timestamp > 25 minutes old | `check_signal_freshness()` returns `(False, "stale_…", age)` |
| RiskGuard receives `is_stale=True` | Verdict: `WATCH_ONLY`, `allow_long_bias=False`, `allow_short_bias=False` |
| Extremely old signal (48h) | Treated as stale, no crash |

**Fail-closed:** No entry is accepted when the signal is stale.

### 2. Missing signal

| Condition | Expected behavior |
|-----------|------------------|
| Signal file does not exist | `read_signal()` returns `(None, "")` |
| Signal is `None` passed to freshness | `check_signal_freshness()` returns `(False, "no_signal", None)` |
| No pairs in signal file | No crash, empty pairs list returned |

**Fail-closed:** Pipeline processes no pairs when the signal is absent.

### 3. Malformed / corrupt signal

| Condition | Expected behavior |
|-----------|------------------|
| Signal file contains invalid JSON | `read_signal()` returns `(None, "")` |
| Signal dict has no timestamp | `check_signal_freshness()` returns `(False, "no_timestamp", None)` |

**Fail-closed:** No crash, pipeline degrades gracefully.

### 4. RiskGuard fail-closed defaults

| Condition | Expected behavior |
|-----------|------------------|
| Zero confidence | Verdict: `WATCH_ONLY` |
| Negative confidence | Verdict: `WATCH_ONLY` |
| Empty bias | Verdict: `WATCH_ONLY` |
| Concurrent cap exceeded | Verdict: `WATCH_ONLY` |

**Fail-closed:** RiskGuard never produces `ACCEPTED` when input data is
invalid or out of bounds.

### 5. Upstream interruption (opt-in runtime tests)

These scenarios require local runtime state and are marked `@pytest.mark.runtime`:

- Missing shared `primo_signal_state.json` on disk
- Docker container not reachable (handled by polling retry in the bridge)

## Test commands

```bash
# All resilience tests (deterministic, no runtime dependency)
python3 -m pytest tests/test_resilience_contracts.py -q -m "not runtime"

# Including opt-in runtime tests
python3 -m pytest tests/test_resilience_contracts.py -q -m runtime
```
