# SI v2 — Fixture vs. Real-Data Capability Matrix

> **Grounded at commit `9ceeedd`** — PR #215 (Rainbow read_only runtime
> source + freshness guard) on `main`, 2026-06-14.
>
> This matrix documents which SI v2 components operate on **fixtures**,
> which operate on **read_only** upstream observation, and which can
> consume **production (live) data**. No completion percentages are
> invented; every cell is backed by evidence in the repo.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| 🟢 Fixture | Uses fixture/static input only |
| 🟡 read_only | Uses Rainbow §5 read_only observation (no live producer yet) |
| 🔵 Live | Uses real upstream producer with fresh signal timestamps |
| 🟣 Production | Operates on real Freqtrade trade data |
| 🔴 None | Not yet implemented |
| ⬜ Blocked | Implementation blocked by dependency |

**Source legend (Rainbow §5):**

* `fixture` — sanitized static input (`fixtures/rainbow-signals/`).
* `read_only` — observed via the `RainbowSignalProviderClient` against a
  real HTTP source (in-tree DB-backed stub today, future ai4trade producer).
* `live` — observed via the same client against a production-grade
  producer with timestamps inside the freshness window.

**Scoring eligibility (PR #215, central helper
`_is_rainbow_cycle_scoring_eligible`):**

* `fixture` cycles do **not** count.
* `read_only` cycles count **only** if `rainbow_fresh=True`
  (`freshness_seconds ≤ freshness_max_seconds`, default 900 s = 15 min).
* `live` cycles count under the same freshness rule.
* Scoring gate: 10 / 10 consecutive scoring-eligible cycles.

---

## Capability Matrix

### Rainbow Core

| Component | Current Input | Real-Data Ready? | Evidence |
|-----------|---------------|-------------------|----------|
| Signal envelope validator (`rainbow/validator.py`) | 🟢 Fixture signals | Yes — validator is data-shape-agnostic; tested against fixtures; will validate any §5 envelope from a real producer | `fixtures/rainbow-signals/`; PRs #79, #83, #105 |
| Read-only client (`rainbow/client.py`) | 🟡 read_only | Yes — designed for ai4trade REST, wired in PR #212, runtime source in PR #215 | `client.py`, `client_fixture_harness.py`, PRs #80, #212, #215 |
| Contract snapshot (`rainbow/snapshot.py`) | 🟢 Fixture + 🟡 read_only | Hybrid | `snapshot.py`, PR #82 |
| Drift guard (`rainbow/drift_guard.py`) | 🟢 Fixture + 🟡 read_only | Hybrid | `drift_guard.py`, PR #83 |
| Shadowlock events (`rainbow/shadowlock_events.py`) | 🟢 Fixture + 🟡 read_only | Hybrid | `shadowlock_events.py`, PR #81 |
| Source status reporting (`rainbow/status.py`) | 🟢 Fixture + 🟡 read_only | Hybrid | PR #85 |
| Offline fixture review report | 🟢 Fixture | n/a | PR #84 |

### Evidence Pipeline

| Component | Current Input | Real-Data Ready? | Evidence |
|-----------|---------------|-------------------|----------|
| Source manifest (`evidence/source_manifest.json`) | 🟢 Static + 🟡 read_only | Hybrid | Pre-registered fixture sources + read_only source |
| Evidence bundle builder (`evidence_bundle_builder.py`) | 🟢 Fixture + 🟡 read_only | Hybrid | Processes evidence record schemas from fixtures and read_only |
| Evidence bundle integrity manifest | 🟢 Fixture + 🟡 read_only | Hybrid | Integrity check runs on both fixture and read_only bundles |
| Measurement Ledger (`measurement/ledger.py`) | 🟣 Production | Yes — wired to Active Cycle Runner in PR #211 | 27 fleet cycles, 108 bot measurement points, 24 proposal records |
| Attribution report (`measurement/report.py`) | 🟣 Production | Yes — generated from Measurement Ledger | PR #210, PR #213 Rainbow section |

### Regime Detection

| Component | Current Input | Real-Data Ready? | Evidence |
|-----------|---------------|-------------------|----------|
| Regime label fixtures (`fixtures/regime-labels/`) | 🟢 Fixture | n/a | Static fixture files |
| Source-regime stats (`fixtures/source-regime-stats/`) | 🟢 Fixture | n/a | Static fixture files |
| Regime Detector schema (#55) | 🟣 Production | ✅ **CLOSED** 2026-06-11, merged at `9017dd4` (PR #161) | Spec document + 19 structural tests |
| Regime Detector run (#56) | 🟣 Production | ✅ **CLOSED** 2026-06-11, merged at `fadfefa` (PR #163) | Regime labels enriched into Shadowlock |
| Performance Attribution Engine (#57) | 🟣 Production | ✅ **CLOSED** 2026-06-11, merged at `773e9cb` (PR #164) | Attribution engine implemented |
| `source_regime_stats` summary (#58) | 🟣 Production | ✅ **CLOSED** 2026-06-11, merged at `e806fc8` (PR #165) | SQLite cache implemented |
| Automated Attribution Reports (#59) | 🟣 Production | ✅ **CLOSED** 2026-06-11, merged at `81884db` (PR #166) | Reports generated weekly (issue #66 cadence) |

### Shadowlock / SQLite

| Component | Current Input | Real-Data Ready? | Evidence |
|-----------|---------------|-------------------|----------|
| Shadowlock Writer | 🟡 Hybrid | Yes — runs on VPS, writes to SQLite | Operates in production; ingests Freqtrade trade data |
| Shadowlock Indexer | 🟡 Hybrid | Yes — SQLite read cache exists (#12 merged) | Live query path through Measurement Ledger |
| Shadowlock maintenance command (#60) | 🟡 Hybrid | ✅ **CLOSED** 2026-06-11, merged at `0557b70` (PR #169) | Copy-on-write with 13 M60 fixes |

### Active Cycle / Observation Loop

| Component | Current Input | Real-Data Ready? | Evidence |
|-----------|---------------|-------------------|----------|
| Active Cycle Runner (#208) | 🟣 Production | ✅ Merged at `61fe380` | 27 cycles, all `runner_exit_code=0` |
| Multi-Signal Fusion (#209) | 🟣 Production | ✅ Merged at `c8f9961` | ShadowProposals produced (currently 0 per cycle — see Phase 2.1 producer-freshness plan) |
| Measurement & Attribution Ledger v1 (#210) | 🟣 Production | ✅ Merged at `016c2f6` (PR #210) | 27 cycles, 108 bot points, 24 proposal records |
| Measurement Ledger wiring (#211) | 🟣 Production | ✅ Merged at `3b72438` (PR #211) | Ledger runs every cycle |
| Rainbow read_only client (#212) | 🟡 read_only | ✅ Merged at `29cc474` (PR #212) | Client in place |
| Rainbow cycle + ledger integration (#213) | 🟡 read_only | ✅ Merged at `706e94b` (PR #213) | `external_signals.rainbow` in `CycleState`; Rainbow section in attribution report |
| Rainbow env-var override (#214) | 🟡 read_only | ✅ Merged at `889a747` (PR #214) | `SI_V2_RAINBOW_ENABLED` + `SI_V2_RAINBOW_MODE` |
| Rainbow runtime source + freshness guard (#215) | 🟡 read_only | ✅ Merged at `9ceeedd` (PR #215) | `SI_V2_RAINBOW_BASE_URL` + `…_ENDPOINT_PATH` + `…_TIMEOUT_SECONDS`; DB-backed stub; freshness guard; scoring eligibility helper |

### Quality Gate & Readiness

| Component | Current Input | Real-Data Ready? | Evidence |
|-----------|---------------|-------------------|----------|
| Offline quality gate (`offline_quality_gate.py`) | 🟢 Fixture | Yes for fixture path; no live data path | `reports/readiness/offline_quality_gate_report.md` |
| Phase 1 readiness matrix | 🟢 Fixture + 🟡 read_only | Artifact-existence check | `reports/readiness/phase_1_readiness_matrix.md` |
| Weekly review cadence (#66) | 🟡 Hybrid | Yes — policy merged in PR #194 | Deterministic weekly review per `feat/si-v2-issue-66-weekly-review-cadence` |
| Activation ceremony policy (#26) | n/a | n/a | Fail-closed policy in PR #193 |
| Validation Gate Matrix (#65) | 🟡 Hybrid | Merged in PR #65 | `ff55c86` |

---

## Rainbow Scoring Eligibility — Current State

| Metric | Value |
|--------|-------|
| Total fleet cycles in ledger | 27 |
| `fixture` SUCCESS | 3 |
| `read_only` SUCCESS | 5 |
| `live` SUCCESS | 0 |
| **Scoring-eligible** (read_only/live + `fresh=True`) | **0** |
| History gate required | 10 |
| History gate met | **No** |

**Reason for `0` scoring-eligible cycles:** The DB-backed stub serves a
SQLite `signals.db` whose signal timestamps are 2026-06-14T01:04 UTC —
about 19h before the latest cycle at 2026-06-14T20:48 UTC. The
freshness guard (PR #215, `freshness_max_seconds=900`) correctly
classifies these as `fresh=False`. The ai4trade-bot producer is **not
deployed** (no container, no listener); only the SQLite snapshot exists.

**This is not a loop failure.** The observation loop is GREEN. Scoring
eligibility is unblocked only by **producer freshness** — a real
upstream emitting signals with timestamps inside the 15-min freshness
window. See `roadmap-v2-blocker-first-runtime-ownership.md` Phase 2.1
for the producer-freshness plan.

---

## Summary

| Domain | Total | Fixture-Only | read_only | Production / Live | Not Started |
|--------|-------|--------------|-----------|--------------------|-------------|
| Rainbow Core | 7 | 0 | 7 | 0 | 0 |
| Evidence Pipeline | 5 | 0 | 2 | 3 | 0 |
| Regime Detection | 7 | 2 | 0 | 5 | 0 |
| Shadowlock | 3 | 0 | 3 | 0 | 0 |
| Active Cycle / Observation | 8 | 0 | 4 | 4 | 0 |
| Quality Gate & Readiness | 5 | 1 | 2 | 2 | 0 |
| **Total** | **35** | **3** | **18** | **14** | **0** |

> **Key finding:** All SI v2 components are implemented. 14 of 35
> capabilities are operating on production / live data. 18 are operating
> on the read_only path (fixture + DB-backed stub for the Rainbow
> §5 source). 3 remain fixture-only by design (label fixtures, stat
> fixtures, offline quality gate's fixture path). 0 are not started.
> The remaining gate is **producer freshness**, not component
> implementation.

---

*Reconciled at commit `9ceeedd`, 2026-06-14. Replaces the previous
version grounded at `fdac27c` (2026-06-11) which listed several issues
as OPEN that are now CLOSED and merged.*
