# Test Baseline Drift Note — SI v2 Issue #18

> **Issue:** #18
> **Status:** Documentation-only investigation note.
> **Runtime systems touched:** none.

---

## 1. Objective

Clarify the test-count drift discovered during Phase L:

| Source | Count |
|--------|-------|
| Earlier prompt expectation | 459 test items |
| Verified Phase L / pre-push collection | 457 test items |
| Verified full run | 456 passed, 1 skipped |

The verified baseline is now:

```text
457 collected items across 34 test files
456 passed, 1 skipped
```

---

## 2. Evidence Collected

Command used for collection:

```bash
PYTHONPATH=self_improvement_v2/src /tmp/si_v2_venv/bin/python \
  -m pytest self_improvement_v2/tests --collect-only -q
```

Collected counts by file:

| Test file | Items |
|-----------|------:|
| `tests/test_adapter_audit.py` | 13 |
| `tests/test_adapters.py` | 9 |
| `tests/test_ai4trade_boundary.py` | 15 |
| `tests/test_ai4trade_rest_boundary.py` | 28 |
| `tests/test_approval_gate.py` | 12 |
| `tests/test_backtest_runner.py` | 8 |
| `tests/test_call_budget.py` | 12 |
| `tests/test_config_gate.py` | 10 |
| `tests/test_cron_cli.py` | 20 |
| `tests/test_cron_generator.py` | 7 |
| `tests/test_cron_planner.py` | 19 |
| `tests/test_cron_schema.py` | 34 |
| `tests/test_deployment_plan.py` | 5 |
| `tests/test_dry_run_behavior.py` | 9 |
| `tests/test_e2e_dry_run.py` | 11 |
| `tests/test_guardrails.py` | 29 |
| `tests/test_market_data.py` | 12 |
| `tests/test_no_any_types.py` | 1 |
| `tests/test_no_forbidden_patterns.py` | 24 |
| `tests/test_performance_analyzer.py` | 9 |
| `tests/test_phase_d_e2e.py` | 11 |
| `tests/test_pipeline_e2e.py` | 7 |
| `tests/test_pipeline_safety.py` | 5 |
| `tests/test_real_adapter_bases.py` | 25 |
| `tests/test_rollback_plan.py` | 9 |
| `tests/test_schemas.py` | 18 |
| `tests/test_shadow_logger.py` | 12 |
| `tests/test_shadow_mode.py` | 12 |
| `tests/test_similarity_checker.py` | 9 |
| `tests/test_state_roundtrip.py` | 5 |
| `tests/test_strategy_mutator.py` | 7 |
| `tests/test_strategy_sandbox.py` | 32 |
| `tests/test_telegram_adapter.py` | 9 |
| `tests/test_walk_forward.py` | 9 |
| **Total** | **457** |

Command used for full run with skip reason:

```bash
PYTHONPATH=self_improvement_v2/src /tmp/si_v2_venv/bin/python \
  -m pytest self_improvement_v2/tests --override-ini addopts='' -q -rs
```

Result:

```text
456 passed, 1 skipped in 9.59s
```

Skip reason:

```text
SKIPPED [1] self_improvement_v2/tests/test_market_data.py:127:
pyarrow is installed — cannot test missing-dependency path
```

---

## 3. Drift Assessment

The `459` value appears to be stale planning/current-state metadata rather than
a current repository fact:

- Searching `self_improvement_v2/` found no committed reference to `459`.
- Phase L was documentation-only and did not modify tests.
- The pre-push validation suite consistently collected `457` items.
- The skipped item is environment-dependent and expected when `pyarrow` is
  installed; it does not change the collection count.

No test collection bug was identified in this investigation.

---

## 4. Current Baseline

Use this as the current SI v2 baseline until a later code change intentionally
adds/removes tests:

```text
pytest collect: 457 items across 34 files
pytest full:    456 passed, 1 skipped
skip reason:    pyarrow installed, missing-dependency path cannot be tested
```

---

## 5. Safety Confirmation

This investigation did not access Docker, Freqtrade, Telegram, ai4trade-bot,
exchanges, live databases, live configs, live strategy files, cron, Hermes
scheduler, `jobs.json`, or live trading state.

No code mutation was required. No follow-up fix issue is needed unless a future
phase observes a new inconsistent collection count from the same commit.
