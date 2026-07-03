# Coverage Quality Gate — Module-Level Strategy

**Date:** 2026-07-03
**Issue:** #314
**Status:** ✅ Complete — PR #451

## Current Baseline

| Metric | Value |
|--------|-------|
| Total line coverage | **82%** |
| Total branch coverage | **70%** |
| Tests passed | **5,207** |
| CI gate (soft-fail) | **80%** |

## Module-Level Coverage Table

### CRITICAL — Decision/Apply Logic (target: 90%+ lines, 85%+ branches)

| Module | Lines | Branches | Status | Risk |
|--------|:-----:|:--------:|:------:|:----:|
| `apply_actuator/policy.py` | **95%** | **93%** | ✅ | Central apply decision logic |
| `apply_actuator/models.py` | **99%** | **100%** | ✅ | All status enums + data models |
| `apply_actuator/overlay_merge.py` | **91%** | **88%** | ✅ | Config merge + safety validation |
| `apply_actuator/restart_with_overlay.py` | **95%** | **92%** | ✅ | Canary restart plan |
| `apply_actuator/rollback_executor.py` | **96%** | **88%** | ✅ | Rollback execution |
| `apply_actuator/rollback_rehearsal.py` | **86%** | **71%** | 🟡 | Rehearsal — I/O-heavy paths |
| `apply_actuator/runtime_executor.py` | **79%** | **75%** | 🟡 | Runtime exec — Docker subprocess |
| `apply_actuator/restart_gate.py` | **84%** | **70%** | 🟡 | Restart gate — 10 gates, I/O |
| `apply_actuator/runtime_binding.py` | **63%** | **50%** | 🟡 | Path resolution — filesystem checks |
| `apply_actuator/controlled_apply.py` | **100%** | **100%** | ✅ | Orchestration entry point |
| `apply_actuator/controlled_apply_actuator.py` | **90%** | **86%** | ✅ | Actuator orchestration |

### CRITICAL — Measurement/Decision (target: 90%+ lines, 85%+ branches)

| Module | Lines | Branches | Status | Risk |
|--------|:-----:|:--------:|:------:|:----:|
| `measurement/ledger.py` | **97%** | **90%** | ✅ | Measurement ledger |
| `measurement/decision_engine.py` | **94%** | **91%** | ✅ | Decision engine |
| `measurement/final_decision_pack.py` | **93%** | **86%** | ✅ | Decision packaging |
| `measurement/models.py` | **99%** | **100%** | ✅ | Measurement models |
| `measurement/report.py` | **99%** | **94%** | ✅ | Measurement report |
| `measurement/statistical_evidence.py` | **86%** | **80%** | 🟡 | Statistical — math-heavy |
| `measurement/autonomous_measurement_watcher.py` | **88%** | **80%** | 🟡 | Watcher — I/O paths |
| `measurement/snapshot_runner.py` | **57%** | **62%** | 🔴 | Snapshot — Docker subprocess |

### CRITICAL — Validation/Gates (target: 90%+ lines, 85%+ branches)

| Module | Lines | Branches | Status | Risk |
|--------|:-----:|:--------:|:------:|:----:|
| `validation/gates.py` | **100%** | **100%** | ✅ | All approval gates |
| `validation/evidence_bundle_validator.py` | **85%** | **80%** | 🟡 | Bundle validation |
| `validation/models.py` | **100%** | **100%** | ✅ | Validation models |
| `validation/matrix.py` | **100%** | **100%** | ✅ | Decision matrix |

### IMPORTANT — Proposal/Scoring (target: 80%+ lines, 70%+ branches)

| Module | Lines | Branches | Status | Risk |
|--------|:-----:|:--------:|:------:|:----:|
| `propose/proposal_scoring/scoring.py` | **82%** | **70%** | ✅ | Scoring engine |
| `propose/proposal_scoring/policy.py` | **76%** | **67%** | 🟡 | Scoring policy |
| `propose/proposal_scoring/models.py` | **92%** | **69%** | 🟡 | Scoring models |
| `propose/weight_proposal/engine.py` | **84%** | **75%** | 🟡 | Weight proposal engine |
| `propose/weight_proposal/audit.py` | **80%** | **70%** | 🟡 | Weight audit |
| `propose/weight_proposal/models.py` | **79%** | **57%** | 🟡 | Weight models |
| `propose/strategy_adapter/validator.py` | **69%** | **63%** | 🟡 | Strategy validator |
| `propose/strategy_adapter/path_guard.py` | **69%** | **50%** | 🟡 | Path guard |
| `propose/safe_parameters.py` | **100%** | **100%** | ✅ | Safe parameters |
| `propose/similarity_checker.py` | **91%** | **86%** | ✅ | Similarity checker |

### IMPORTANT — Safety Layer (target: 80%+ lines, 70%+ branches)

| Module | Lines | Branches | Status | Risk |
|--------|:-----:|:--------:|:------:|:----:|
| `freqtrade/shared/kill_switch.py` | **89%** | **83%** | ✅ | Kill switch |
| `freqtrade/shared/fleet_risk_manager.py` | **90%** | **86%** | ✅ | Fleet risk manager |
| `freqtrade/shared/primo_signal.py` | **67%** | **67%** | 🟡 | Signal bridge |
| `bridge/hermes_primo_bridge.py` | **40%** | **33%** | 🔴 | HTTP-heavy bridge |
| `intelligence/regime_detector.py` | **96%** | **93%** | ✅ | Regime detection |
| `orchestrator/control/activation_ceremony.py` | **100%** | **100%** | ✅ | Activation ceremony |

## Coverage Targets

| Area | Line Target | Branch Target | Enforcement |
|------|:-----------:|:-------------:|:-----------:|
| **CRITICAL — Decision/Apply** | **90%** | **85%** | Ratchet (no regression) |
| **CRITICAL — Measurement** | **90%** | **85%** | Ratchet (no regression) |
| **CRITICAL — Validation/Gates** | **90%** | **85%** | Ratchet (no regression) |
| **IMPORTANT — Proposal/Scoring** | **80%** | **70%** | Report-only |
| **IMPORTANT — Safety Layer** | **80%** | **70%** | Report-only |
| **LOW — CLI/Glue/Reporting** | Report-only | Report-only | None |
| **Global CI gate** | **80%** | — | Soft-fail (continue-on-error) |

## This PR's Improvement

| Module | Before | After | Δ |
|--------|:------:|:-----:|:-:|
| `apply_actuator/policy.py` (lines) | **73%** | **95%** | **+22%** |
| `apply_actuator/policy.py` (branches) | **65%** | **93%** | **+28%** |
| Tests added | — | **22** | **+22** |

## Remaining Low-Coverage Hotspots

| Module | Lines | Reason | Priority |
|--------|:-----:|--------|:--------:|
| `measurement/snapshot_runner.py` | **57%** | Docker subprocess — hard to test without real containers | 🟡 P1 |
| `bridge/hermes_primo_bridge.py` | **40%** | HTTP/LLM calls — needs mock server | 🟡 P1 |
| `apply_actuator/runtime_binding.py` | **63%** | Filesystem path checks — validation helper, not decision logic | 🟢 P2 |
| `apply_actuator/runtime_executor.py` | **79%** | Docker subprocess — hard to test without real containers | 🟢 P2 |
| `apply_actuator/restart_gate.py` | **84%** | 10 gates, some I/O-heavy | 🟢 P2 |

## Gate Strategy

**Current:** Soft-fail CI gate at 80% (`continue-on-error: true`).

**Recommended next step:** Convert to **critical-module ratchet gate**:
1. Track per-module baseline in this document
2. CI checks that CRITICAL modules don't regress below their current baseline
3. No hard global gate — prevents false CI failures from I/O-heavy modules
4. Ratchet up targets as I/O-heavy modules get test coverage

## Files Changed

| File | Change | Purpose |
|------|--------|---------|
| `self_improvement_v2/tests/test_apply_actuator_policy_edge_cases.py` | **New** (22 tests) | Edge-case coverage for `policy.py` and `runtime_binding.py` |
| `docs/reports/coverage-quality-gate-2026-07-03.md` | **New** | This report |
