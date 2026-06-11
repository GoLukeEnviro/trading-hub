# SI v2 — Fixture vs. Real-Data Capability Matrix

> **Grounded at commit `fdac27c`** — PR #160 (controller layer merged).
>
> This matrix documents which SI v2 components operate on **fixtures only**
> versus which can consume **production (real) data**. No completion
> percentages are invented; every cell is backed by evidence in the repo.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| 🟢 Fixture | Uses fixture/static input only |
| 🟡 Hybrid | Designed for real data but currently fixture-fed |
| 🔴 None | Not yet implemented |
| ⬜ Blocked | Implementation blocked by dependency |

---

## Capability Matrix

### Rainbow Core

| Component | Current Input | Real-Data Ready? | Evidence |
|-----------|---------------|-------------------|----------|
| Signal envelope validator (`rainbow/validator.py`) | 🟢 Fixture signals | No — no live signal ingestion pipeline | `fixtures/rainbow-signals/` contains sanitized fixtures |
| Read-only client (`rainbow/client.py`) | 🟢 Fixture harness | No — designed for ai4trade REST but not wired | `client_fixture_harness.py` wraps fixture data |
| Contract snapshot (`rainbow/snapshot.py`) | 🟢 Fixture | No | Validates against fixture-based contract |
| Drift guard (`rainbow/drift_guard.py`) | 🟢 Fixture | No | Compares fixture snapshots only |
| Shadowlock events (`rainbow/shadowlock_events.py`) | 🟢 Fixture | No | Maps fixture events only |

### Evidence Pipeline

| Component | Current Input | Real-Data Ready? | Evidence |
|-----------|---------------|-------------------|----------|
| Source manifest (`evidence/source_manifest.json`) | 🟢 Static file | No — requires live provider registration | Pre-registered fixture sources only |
| Evidence bundle builder (`evidence_bundle_builder.py`) | 🟢 Fixture | No | Processes evidence record schemas from fixtures |
| Evidence bundle integrity manifest | 🟢 Fixture | No | Integrity check runs on fixture bundle |

### Regime Detection

| Component | Current Input | Real-Data Ready? | Evidence |
|-----------|---------------|-------------------|----------|
| Regime label fixtures (`fixtures/regime-labels/`) | 🟢 Fixture | No — 5 pre-canned labels only | Static fixture files |
| Source-regime stats (`fixtures/source-regime-stats/`) | 🟢 Fixture | No — 2 pre-canned stat sets | Static fixture files |
| Regime Detector schema (#55) | ⬜ Not started | N/A | Issue #55 is OPEN, no implementation |
| Regime Detector run (#56) | ⬜ Not started | N/A | Issue #56 is OPEN, no implementation |

### Attribution

| Component | Current Input | Real-Data Ready? | Evidence |
|-----------|---------------|-------------------|----------|
| Offline aggregator (`offline_aggregator.py`) | 🟢 Fixture | No — aggregates fixture regime stats only | `reports/attribution/offline_attribution_summary.json` from fixtures |
| Attribution report renderer | 🟢 Fixture | No | `reports/attribution/attribution_report.md` from fixture data |
| Performance Attribution Engine (#57) | ⬜ Not started | N/A | Issue #57 is OPEN |
| `source_regime_stats` summary (#58) | ⬜ Not started | N/A | Issue #58 is OPEN |
| Automated attribution reports (#59) | ⬜ Not started | N/A | Issue #59 is OPEN |

### Shadowlock / SQLite

| Component | Current Input | Real-Data Ready? | Evidence |
|-----------|---------------|-------------------|----------|
| Shadowlock Writer | 🟡 Hybrid | Yes — runs on VPS, writes to SQLite | Operates in production but only ingested by fixture-level tests |
| Shadowlock Indexer | 🟢 Fixture | Partial — SQLite read cache exists (#12 merged) | No live query pipeline |
| Shadowlock maintenance command (#60) | ⬜ Not started | N/A | Issue #60 is OPEN |

### Quality Gate & Readiness

| Component | Current Input | Real-Data Ready? | Evidence |
|-----------|---------------|-------------------|----------|
| Offline quality gate (`offline_quality_gate.py`) | 🟢 Fixture | No — validates fixture pipeline only | `reports/readiness/offline_quality_gate_report.md` |
| Phase 1 readiness matrix | 🟢 Fixture | No — artifact-existence check only | `reports/readiness/phase_1_readiness_matrix.md` |
| Live-readiness blocker inventory (#124) | 🔶 In prog. | No — documenting blockers | Issue #124 is OPEN |

---

## Summary

| Domain | Total Capabilities | Fixture-Only | Real-Data Ready | Not Started |
|--------|---------------------|--------------|-----------------|-------------|
| Rainbow Core | 5 | 5 | 0 | 0 |
| Evidence Pipeline | 3 | 3 | 0 | 0 |
| Regime Detection | 4 | 2 | 0 | 2 |
| Attribution | 4 | 2 | 0 | 2 |
| Shadowlock | 3 | 2 | 1 | 1 |
| Quality Gate | 2 | 2 | 0 | 0 |
| **Total** | **21** | **16** | **1** | **5** |

> **Key finding:** Only 1 of 21 SI v2 capabilities (Shadowlock Writer) operates
> near real data. All evidence, attribution, and readiness assessments are
> **fixture-based only**. Describing fixture-based attribution as production
> attribution is incorrect.

---

*Generated at commit fdac27c, 2026-06-11*
