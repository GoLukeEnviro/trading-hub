# Phase C — Gate-0 Strategy Evidence: Candidate Inventory and Manifest Proposal

**Date:** 2026-07-19
**Phase:** C (Gate-0 Strategy Evidence) — exit gate `edge_decision_recorded`
**Execution class:** A1 (repository-only)
**Issue:** #604
**Branch:** `docs/phase-c-gate0-strategy-inventory-2026-07-19`
**Base:** `origin/main` at `2b6915d` (post-Phase A)

> **Human decision required.** Issue #604 requires Luke's signed strategy
> selection and frozen manifest approval. This report provides the read-only
> candidate inventory and a manifest proposal. No strategy is selected, no
> threshold is frozen, and no holdout is inspected in this PR.

## Blocker status

Issue #604 carried `BLOCKED_BY_PHASE0A_CORRECTIVE_MERGE` (comment 2026-07-14T21:03:49Z).
The corrective PR #620 (`feat(research): complete phase 0a evidence contract`)
merged at `a820c956` on 2026-07-14T22:39:51Z. Issue #594 closed one second
later. The corrective evidence contract (`EvaluationManifestV1`,
`EvaluationBundleV1`, `EvaluationRunnerV1`, canonical cost engine,
partition/leakage policy, mark-to-market, deterministic uncertainty) is present
on `main`. The blocker is factually resolved; this PR updates #604's status to
reflect that.

## Candidate inventory

Three canonical strategies are deployed in the HermesTrader dry-run fleet. A
fourth (Rebel) is non-reproducible per R3.

### 1. FreqForge_Override (baseline)

| Field | Value |
|---|---|
| Strategy identifier | `FreqForge_Override` |
| Version | Baseline v1 (based on `RegimeSwitchingHybrid_v7_v04_Integration`) |
| Repo path | `freqforge/user_data/strategies/FreqForge_Override.py` |
| Timeframe | `15m` (informative `1h`) |
| `can_short` | `False` |
| ROI | `{'0': 0.04, '30': 0.025, '60': 0.015, '120': 0}` |
| Stoploss | `-0.04` (hard) |
| Trailing | Disabled |
| Protections | CooldownPeriod(5), StoplossGuard(60,3,60), MaxDrawdown(480,20,96,6%) |
| Canonical pairs | `BTC/USDT:USDT`, `ETH/USDT:USDT`, `SOL/USDT:USDT` |
| Max open trades | 5 |
| Signal layer | `primo_gate_allows` (read-only filter from `freqtrade/shared/`) |
| Exit signals | None (ROI + stoploss only) |
| LLM layer | None |
| Shadow logging | Passive JSONL to `freqforge_shadow.log` |
| Known defects | None recorded |
| Data coverage | 3 majors on Bitget futures; sufficient for 15m evaluation |
| Historical evidence | C4 ROLLBACK_RECOMMENDED (max_drawdown 82.79% — but this was the canary with a different config path, not FreqForge_Override baseline) |

### 2. RegimeSwitchingHybrid_v7_v04_Integration

| Field | Value |
|---|---|
| Strategy identifier | `RegimeSwitchingHybrid_v7_v04_Integration` |
| Version | v7 v04 Integration |
| Repo path | `freqtrade/bots/regime-hybrid/user_data/strategies/RegimeSwitchingHybrid_v7_v04_Integration.py` |
| Timeframe | Config not in config.example.json (strategy-defined) |
| Canonical pairs | `BTC/USDT:USDT`, `ETH/USDT:USDT`, `SOL/USDT:USDT` |
| Max open trades | 3 |
| Stoploss | `-0.09` (config-level) |
| Known defects | None recorded |
| Data coverage | Same 3 majors; sufficient for evaluation |
| Historical evidence | Active in dry-run fleet; no standalone Gate-0 evidence yet |

### 3. RebelLiquidationV2 (config) / RebelLiquidation (file) — NON-REPRODUCIBLE

| Field | Value |
|---|---|
| Strategy identifier | `RebelLiquidation` (file) / `RebelLiquidationV2` (config) |
| Version | Drift between config and file name (R3: REVIEW_REQUIRED) |
| Repo path | `freqtrade/bots/freqai-rebel/user_data/strategies/` |
| R3 classification | `NOT_REPRODUCIBLE` — 1.2 GB trained FreqAI models not in repo; FreqAI deps + `directory_operations.py` patch missing; base unpinned |
| Gate-0 eligibility | **Ineligible** — cannot reproduce a deterministic evaluation without the trained models |

## Recommended Gate-0 candidate

**FreqForge_Override** is the strongest Gate-0 candidate:

1. **Reproducible** — all code is in the repo, no external models or deps.
2. **Simplest edge surface** — ROI + hard stoploss + primo_gate filter. Fewer
   confounding variables for a first edge-evidence run.
3. **Clean separation** — no LLM layer, no custom exit signals, no trailing.
   The edge (if any) comes from entry timing + ROI ladder + stoploss, which is
   exactly what Gate-0 should isolate first.
4. **Canonical deployment** — already running in the HermesTrader dry-run
   fleet with 5/5 health (R5A).

RegimeSwitchingHybrid is a viable alternative but introduces regime-switching
complexity that is harder to attribute in a first holdout.

## Proposed evaluation manifest (for Luke's approval — not frozen)

This is a **proposal** derived from PR #591's suggested values and the
EvaluationManifestV1 contract. Luke must sign the final manifest before any
holdout inspection.

| Field | Proposed value |
|---|---|
| `manifest_version` | `evaluation-manifest/v1` |
| `strategy_identifier` | `FreqForge_Override` |
| `exchange` | `bitget` |
| `trading_mode` | `futures` |
| `market_type` | `linear` |
| `pairs` | `('BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT')` |
| `timeframe` | `15m` |
| Calibration window | 2025-01-01 to 2025-06-30 (6 months) |
| Walk-forward windows | 2025-07-01 to 2025-09-30, 2025-10-01 to 2025-12-31 |
| Holdout window | 2026-01-01 to 2026-06-30 (6 months, untouched) |
| Fee assumption | 0.05% taker (Bitget futures default) |
| Funding assumption | 0.01% per 8h (average, included in cost engine) |
| Slippage assumption | 0.02% per trade (conservative for top-3 majors) |
| Primary metric | OOS profit factor |
| Guardrail: max OOS drawdown | < 25% |
| Guardrail: min OOS profit factor | > 1.3 |
| Guardrail: min trades | > 100 closed trades |
| Guardrail: min regimes | ≥ 2 (trend + range) |
| PASS rule | All guardrails met → `PASS_CANDIDATE` |
| EXTEND rule | Insufficient trades/duration/regimes → `EXTEND` |
| REJECT rule | Drawdown ≥ 25% or profit factor ≤ 1.3 → `REJECT` |
| INVALID rule | Data gap > 5% or leakage detected → `INVALID` |
| Previously tested variants | 0 (this is the first Gate-0 run) |

> **Luke must explicitly confirm or replace every value above** before any
> data snapshot is hashed or holdout results are inspected. No threshold may
> change after holdout inspection without invalidating the run.

## Data snapshot requirements

The manifest requires immutable candle and benchmark snapshots with SHA-256
hashes. These cannot be produced in a repository-only A1 PR — they require
fetching exchange data, which is a runtime action. The data snapshot step is
deferred to Luke's approval of this manifest proposal.

## Scope

- A1 only: repository documentation and evidence report.
- No runtime, Docker, exchange data fetch, strategy execution, or holdout
  inspection.
- No strategy is selected. No threshold is frozen. No Gate-0 execution.
- Luke's signed comment on #604 is the sole authority for the final selection.

## Done criteria (partial — inventory only)

- ✅ Candidate inventory: 3 strategies documented with identifiers, versions,
  configs, pairs, defects, data coverage, and historical evidence.
- ✅ Gate-0 candidate recommendation: FreqForge_Override (with rationale).
- ✅ Manifest proposal: all EvaluationManifestV1 fields populated with
  suggested values from PR #591.
- ⏳ **Luke's signed strategy selection and frozen manifest**: not part of this
  PR — requires Luke's comment on #604.
- ⏳ Data snapshot hashing: deferred (runtime action, not A1).

## Status

`READY_FOR_HUMAN_MERGE` — this PR delivers the read-only inventory and manifest
proposal. Luke's decision on #604 is the next step after merge.