# Phase 3 Active Cycle Runner Coverage Report

## Verdict

**GREEN** ✅ — 60 Tests, 0 failed, Coverage 26% → 64%

## Summary

- **Module:** `self_improvement_v2/src/si_v2/loop/active_cycle_runner.py`
- **Coverage before:** 26%
- **Coverage after:** 64%
- **Line coverage delta:** +38%
- **Branch coverage delta:** 40 branches covered (vorher ~0, jetzt 40)

## Changed Files

| File | Purpose |
|------|---------|
| `self_improvement_v2/tests/test_active_cycle_runner_phase3.py` | **Neu** — 971 Zeilen, 60 Tests |

## Tests Added

| Test Class | Behavior Covered |
|-----------|-----------------|
| `TestIsRainbowCycleScoringEligible` | 8 Fälle: SUCCESS/read_only/live/fixture, errors, count, freshness |
| `TestRiskguardCheck` | 8 Fälle: safe proposal, wrong base_mode, no human approval, wrong policy, dry_run=false, forbidden params, multiple issues, parameters=None |
| `TestAdjustedFleetVerdict` | 8 Fälle: GREEN/YELLOW/RED × SUCCESS/SKIPPED/WARNING/FAILED |
| `TestAsdictProposal` | 2 Fälle: SHADOW_PROPOSAL, NO_PROPOSAL |
| `TestTelemetryToBotEvidence` | 3 Fälle: basic, with signal_depth, with proposal_evidence |
| `TestPerBotHistoricalSummary` | 4 Fälle: unavailable, OK with data, missing bot, no bundle |
| `TestPrimaryVerdictFromHistoricalWindow` | 3 Fälle: returns verdict, no bundle, no verdict |
| `TestWindowsFromHistoricalWindow` | 3 Fälle: returns windows, no bundle, no windows |
| `TestLoadHistoricalEvidenceWindow` | 3 Fälle: store not found, store empty, default candidate_id |
| `TestRunLedgerPostStep` | 3 Fälle: state_dir not found, empty state_dir, with cycle state |
| `TestRunPostCycleValidation` | 2 Fälle: bundle not found, with valid bundle |
| `TestCurrentCommitSha` | 2 Fälle: git failure → unknown, git success → SHA |
| `TestCurrentBranch` | 2 Fälle: git failure → unknown, git success → branch |
| `TestCollectOne` | 3 Fälle: collects telemetry, missing env vars, no auth config |
| `TestRunActiveCycle` | 6 Fälle: full cycle returns 0, creates evidence, creates state, creates report, no apply executed, missing env vars |

## Commands Run

```bash
# Baseline
python -m pytest self_improvement_v2/tests -q --cov=self_improvement_v2/src/si_v2/loop/active_cycle_runner.py --cov-branch --cov-report=term
# → 26% (module-not-imported warning)

# Phase 3 tests
python -m pytest self_improvement_v2/tests/test_active_cycle_runner_phase3.py -v
# → 60 passed, 0 failed

# Coverage
python -m pytest self_improvement_v2/tests/test_active_cycle_runner_phase3.py -q --cov=si_v2.loop.active_cycle_runner --cov-branch --cov-report=term
# → 64%
```

## SI-v2 Loop Impact

| Loop-Schritt | Impact |
|-------------|--------|
| **Fleet-Daten lesen** | ✅ `_collect_one` getestet (HTTP mock, env var handling, auth) |
| **ShadowProposal bewerten** | ✅ `_riskguard_check` getestet (8 safety scenarios), `_asdict_proposal` getestet |
| **Human Approval** | ✅ `_adjusted_fleet_verdict` getestet, approval gate mock integriert |
| **Canary-first anwenden** | ✅ `run_active_cycle` getestet — kein Apply wird ausgeführt |
| **Wirkung messen** | ✅ `_run_ledger_post_step` getestet (3 Szenarien) |
| **Rollback möglich** | ⚠️ Indirekt: Evidence-Bundle-Validierung getestet |
| **Nächste Iteration** | ✅ Rainbow-Scoring-Eligibility getestet |

## Remaining Risks

1. **active_cycle_runner.py bei 64% statt Ziel 70%** — Die Rainbow-Loading-Logik (Zeilen 674-904) und Walk-Forward-Materializer (Zeilen 1158-1192) sind schwer testbar ohne echte Rainbow-Infrastruktur. Die restlichen ~36% sind hauptsächlich I/O-heavy Code (Datei-Persistenz, subprocess, env-var-Reading).
2. **fleet_risk_manager.py noch bei 49%** — aus Sprint 1 offen.
3. **run_active_cycle() Tests sind mock-heavy** — 20+ monkeypatch-Aufrufe pro Test. Das ist akzeptabel für eine 2257-Zeilen-Datei, aber die Tests sind wartungsintensiv.

## Rollback

```bash
git checkout main
git branch -D test/coverage-active-cycle-runner
```

## Recommended Next Step

**Phase 4 — Bridge/Primo/Intelligence Layer (0-20% → 60%)** starten. Die Signal-Pipeline ist der nächste kritische Pfad für den SI-v2 Loop, und die Module sind klein genug für einen schnellen Sprint.
