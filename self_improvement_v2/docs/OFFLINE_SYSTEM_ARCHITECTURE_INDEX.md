# Offline System Architecture Index

> **[HISTORICAL] SI v2 — Offline Episode Architecture**
> Agent-readable, concise, no stale references.
>
> **⚠️ Historical notice:** Issue-number references for Rainbow core (#51–#56)
> refer to **ai4trade-bot** repo issues, not trading-hub Phase 1 issues (#55–#61).
> For current canonical state and Phase 1 intelligence planning, see
> `docs/state/` documents.

---

## 1. Repository Layout

All SI v2 files live under `self_improvement_v2/`.

| Path | Role |
|------|------|
| `src/si_v2/` | Installable Python package |
| `tests/` | pytest test suite |
| `fixtures/` | Signal, regime, and evidence fixtures |
| `reports/` | Output reports (Markdown + JSON) |
| `evidence/` | Manifest and integrity files |
| `episode/` | Episode manifest JSON |
| `contracts/` | Schema contracts |
| `readiness/` | Readiness matrix generator |
| `attribution/` | Attribution report renderer |
| `docs/` | Documentation and architecture |
| `run_offline_episode.py` | CLI entrypoint |

---

## 2. Rainbow Subsystem

The Rainbow signal validation core.

| File | Purpose |
|------|---------|
| `src/si_v2/rainbow/validator.py` | Signal envelope validation |
| `src/si_v2/rainbow/snapshot.py` | Contract snapshot |
| `src/si_v2/rainbow/drift_guard.py` | Contract drift detection |
| `src/si_v2/rainbow/fixture_review_report.py` | Fixture review |
| `src/si_v2/rainbow/status.py` | Source status |
| `src/si_v2/rainbow/client.py` | Read-only client |
| `src/si_v2/rainbow/client_fixture_harness.py` | Fixture harness |
| `src/si_v2/rainbow/shadowlock_events.py` | Audit event mapping |
| `contracts/rainbow_signal_envelope.schema.json` | Signal contract schema |

---

## 3. Evidence Pipeline

| File | Purpose |
|------|---------|
| `evidence/source_manifest.json` | Registered providers |
| `evidence/external_evidence_record.schema.json` | Evidence record schema |
| `evidence/evidence_bundle.schema.json` | Bundle schema |
| `src/si_v2/evidence/evidence_bundle_builder.py` | Bundle builder |
| `reports/evidence/evidence_bundle.json` | Bundle output |
| `evidence/evidence_bundle_integrity_manifest.json` | File integrity manifest |
| `evidence/evidence_bundle_integrity.py` | Integrity manifest generator |

---

## 4. Regime Fixtures

| File | Purpose |
|------|---------|
| `fixtures/regime-labels/` | Regime label fixtures (5) |
| `fixtures/source-regime-stats/` | Source-regime stat fixtures (2) |
| `src/si_v2/attribution/offline_aggregator.py` | Attribution aggregation |

---

## 5. Attribution

| File | Purpose |
|------|---------|
| `src/si_v2/attribution/offline_aggregator.py` | Aggregate source-regime stats |
| `reports/attribution/offline_attribution_summary.json` | Aggregator output |
| `reports/attribution/offline_attribution_summary.md` | Summary report |
| `attribution/attribution_report_renderer.py` | Attribution Markdown renderer |
| `reports/attribution/attribution_report.md` | Attribution report |

---

## 6. Quality Gate

| File | Purpose |
|------|---------|
| `src/si_v2/cli/offline_quality_gate.py` | Quality gate CLI |
| `reports/readiness/offline_quality_gate_report.md` | Quality gate output |

---

## 7. Offline Episode Layer

| File | Purpose |
|------|---------|
| `episode/offline_episode_manifest.json` | Episode manifest (#104) |
| `src/si_v2/episode/offline_episode.py` | Episode skeleton (#97) |
| `run_offline_episode.py` | CLI entrypoint (#97) |
| `src/si_v2/episode/offline_episode_report.py` | Report renderer (#114) |
| `reports/episode/offline_episode_report.md` | Episode report output (#114) |

---

## 8. Readiness

| File | Purpose |
|------|---------|
| `readiness/phase_1_readiness_matrix.py` | Readiness matrix generator (#117) |
| `reports/readiness/phase_1_readiness_matrix.md` | Readiness matrix output (#117) |
| `reports/source_readiness_summary.md` | Source readiness summary |

---

## 9. Test Coverage Summary

| Test file | Related issues | Test count |
|-----------|----------------|------------|
| `tests/test_rainbow_validator.py` | Rainbow | ~40 |
| `tests/test_rainbow_snapshot.py` | Rainbow | ~15 |
| `tests/test_rainbow_contract_drift_guard.py` | Rainbow | ~15 |
| `tests/test_rainbow_fixture_review_report.py` | Rainbow | ~18 |
| `tests/test_rainbow_source_status.py` | Rainbow | ~16 |
| `tests/test_rainbow_read_only_client.py` | Rainbow | ~19 |
| `tests/test_rainbow_shadowlock_events.py` | Rainbow | ~21 |
| `tests/test_rainbow_offline_golden_path.py` | #107 | ~19 |
| `tests/test_evidence_bundle_builder.py` | #108 | ~9 |
| `tests/test_offline_attribution_aggregator.py` | #111 | ~11 |
| `tests/test_offline_quality_gate.py` | #112 | ~10 |
| `tests/test_regime_label_fixtures.py` | #109 | ~9 |
| `tests/test_offline_episode_skeleton.py` | #97 | ~13 |
| `tests/test_offline_episode_report.py` | #114 | ~12 |
| `tests/test_evidence_bundle_integrity_manifest.py` | #115 | ~12 |
| `tests/test_attribution_report_renderer.py` | #116 | ~11 |
| `tests/test_phase_1_readiness_matrix.py` | #117 | ~13 |
| `tests/test_offline_system_architecture_index.py` | #118 | ~6 |
| Plus earlier: manifest, schema, source, readiness, cron, safety tests | #100–#104 | ~50+ |

---

## 10. Implementation Order

| Phase | Issues | Status |
|-------|--------|--------|
| Rainbow core | #51-#56, #79-#85 | ✅ Complete |
| Post-Rainbow foundation | #100-#104 | ✅ Complete |
| Offline pipeline | #107-#112 | ✅ Complete (PR #126) |
| Episode + readiness | #97, #114-#118 | ✅ Complete (current PR) |
| Governance / CI / Approval | #120-#125 | ⏳ Next |

---

*Index maintained at `self_improvement_v2/docs/OFFLINE_SYSTEM_ARCHITECTURE_INDEX.md`*
*Last updated: 2026-06-10*
