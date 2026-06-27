# SI-v2 Phase 6A — Candidate-to-Apply Pipeline Orchestrator

**Date:** 2026-06-27
**Branch:** `feat/si-v2-candidate-to-apply-pipeline`
**Candidate:** `max_open_trades 3→2`
**Status:** Implemented — read-only orchestration layer, no runtime mutation

## Context

Der GAP-Bericht nannte `candidate_to_apply_pipeline()` als **P1-Blocker**. Nachdem Apply, Restart, Measurement und Rollback als Einzelmodule existieren, fehlte der **Orchestrator**, der einen ShadowProposal-Candidate durch alle Gates führt.

## Pipeline Orchestrator

Modul: `self_improvement_v2/src/si_v2/pipeline/candidate_to_apply.py`

| Komponente | Aufgabe |
|------------|---------|
| `CandidateApplyInput` | Input-Datenmodell für einen Pipeline-Candidate |
| `CandidatePipelineDecision` | Status-Entscheidung (READY/BLOCKED/DEFERRED/NOT_IMPLEMENTED) |
| `CandidatePipelineResult` | Ergebnis mit Decision + Context Flags |
| `candidate_to_apply_pipeline()` | Haupt-Orchestrator-Funktion |

## Pipeline-Entscheidungen

| Status | Bedeutung |
|--------|-----------|
| `READY_FOR_HUMAN_APPROVAL` | Candidate valid, benötigt Human Gate |
| `READY_FOR_CANARY_APPLY` | Alle Gates pass, Canary-ready |
| `BLOCKED` | Safety-Gate-Verletzung |
| `DEFERRED` | Measurement Window für anderen Candidate aktiv |
| `NOT_IMPLEMENTED_EXECUTION` | execute=True blockiert in Phase 6A |

## Safety Boundaries

- `execute=False` default — keine Runtime-Mutation
- `allow_non_canary=False` default — nur Canary
- `active_measurement_candidate_id` überwacht laufende Messung
- Kein subprocess, kein Docker, kein Apply/Restart/Rollback
- Forbidden Keys (FORBIDDEN_KEYS + strategy/pair_whitelist/pair_blacklist/telegram) blockiert

## Test Evidence

```bash
cd self_improvement_v2 && PYTHONPATH=src python -m pytest \
  tests/test_candidate_to_apply_pipeline.py -q
→ 36 passed
```

Gesamt SI-v2: **188 Tests GREEN** (5 Module)

## Remaining GAPs (from Audit)

- Doku-Drift (ARCHITECTURE.md, Agent-Steering)
- L3 Token Hardening (statische Token-Werte)
- RiskGuard/Cooldown env config
- Legacy Momentum config
- evidence.jsonl tracking
- Pair-Universe overlay limitation
- Final GREEN Review

## Next Step

**PR erstellen und mergen, dann T2 abwarten (00:27Z) oder nächsten GAP angehen.**
