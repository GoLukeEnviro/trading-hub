# Phase 4 Bridge-Primo-Intelligence Coverage Report

## Verdict

**GREEN** ✅ — 47 Tests, 0 failed, Signal-Pipeline Coverage deutlich gestiegen.

## Summary

| Module | Coverage Before | Coverage After | Δ |
|--------|----------------|----------------|---|
| `bridge/hermes_primo_bridge.py` | **18%** | **36%** | **+18%** |
| `primo/llm_signal_filter.py` | **0%** | **43%** | **+43%** |
| `intelligence/regime_detector.py` | **0%** | **69%** | **+69%** |
| `primo/primo_api.py` | 33% | 33% | 0% (nicht priorisiert) |

## Changed Files

| File | Purpose |
|------|---------|
| `self_improvement_v2/tests/test_bridge_primo_intelligence_phase4.py` | **Neu** — 433 Zeilen, 47 Tests |

## Tests Added

| Test Area | Tests | Behavior Covered |
|-----------|-------|-----------------|
| **Bridge validate_signal** | 20 | valid signal, not-a-dict, None, stale timestamp, invalid timestamp, missing timestamp, disallowed pair, missing pair, invalid direction, missing direction, confidence out-of-range (high/low), non-numeric confidence, confidence 0.0, confidence 1.0, veto=true, risk_cap > 1.0, risk_cap non-numeric, direction=none |
| **Bridge _pair_to_filename** | 3 | BTC, ETH, SOL pair mapping |
| **LLM _fmt** | 6 | float, None, N/A, string, int, zero |
| **LLM build_llm_context** | 5 | builds context, bearish EMA, unknown EMA, missing indicators, alt indicator names |
| **LLM call_llm_signal_filter** | 2 | disabled returns WATCH, LLM error returns fallback |
| **Regime regime_to_weight_multiplier** | 9 | all 7 regimes + unknown + unmapped |
| **Regime detect_regime** | 3 | missing columns, insufficient data, sufficient data |

## Commands Run

```bash
# Phase 4 tests
python -m pytest self_improvement_v2/tests/test_bridge_primo_intelligence_phase4.py -v
# → 47 passed, 0 failed

# Coverage
python -m pytest self_improvement_v2/tests/test_bridge_primo_intelligence_phase4.py -q \
  --cov=bridge --cov=primo --cov=intelligence --cov-branch --cov-report=term
# → bridge 36%, primo/llm 43%, intelligence 69%
```

## SI-v2 Loop Impact

| Loop-Schritt | Impact |
|-------------|--------|
| **Fleet-Daten lesen** | ⚠️ Indirekt: Bridge-Signal-Validierung getestet |
| **ShadowProposal bewerten** | ✅ LLM-Signal-Filter getestet (build_llm_context, call_llm_signal_filter mit Mock) |
| **Human Approval** | ⚠️ Keine direkten Tests |
| **Canary-first anwenden** | ⚠️ Keine direkten Tests |
| **Wirkung messen** | ⚠️ Keine direkten Tests |
| **Rollback möglich** | ⚠️ Keine direkten Tests |
| **Nächste Iteration** | ✅ Regime-Detection getestet (regime_to_weight_multiplier, detect_regime) |

## Remaining Risks

1. **bridge/hermes_primo_bridge.py bei 36%** — Die HTTP- und Main-Loop-Logik (Zeilen 108-120, 193-388) ist schwer testbar ohne echten HTTP-Server. Die Pure-Function `validate_signal` ist mit 20 Tests gut abgedeckt.
2. **primo/llm_signal_filter.py bei 43%** — Der LLM-Call-Pfad (Zeilen 169-219) und die JSONL-History (Zeilen 54-62) sind I/O-heavy. Die Prompt-Building-Logik (`build_llm_context`) ist mit 5 Tests gut abgedeckt.
3. **primo/primo_api.py bei 33% (unverändert)** — Nicht priorisiert, da es ein API-Server ist und keine direkte SI-v2-Signal-Pipeline-Logik enthält.
4. **pandas/numpy als Test-Dependency** — Wurde für `regime_detector.py`-Tests installiert. Ist bereits eine existierende Dependency des Moduls.

## Rollback

```bash
git checkout main
git branch -D test/coverage-bridge-primo-intelligence
```

## Recommended Next Step

**Phase 5 — measurement/ledger.py (56% → 80%)** starten. Der Measurement Ledger ist der nächste kritische Pfad für die Wirkungsmessung im SI-v2 Loop. Oder **Phase 6 — dynamic_exits.py (84% → 95%)** für Boundary-Tests.
