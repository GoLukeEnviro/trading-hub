# Issue #604 — Ratification Proposal for Luke

**Date:** 2026-08-02
**Execution class:** A1 (repository-only, read-only evidence compilation)
**Status:** `READY_FOR_HUMAN_RATIFICATION` — Hermes must NOT self-ratify

## Purpose

This document compiles the complete, verifiable evidence package for Luke's
re-ratification of the Gate-0 strategy and evaluation manifest. The previous
ratification on #604 (2026-07-19) approved `FreqForge_Override` + manifest v1.
Since then, C5.3/C5.4 corrective work has produced a fully stripped
`FreqForge_Gate0_Core_v1` with manifest v3. Luke must explicitly re-ratify
before any holdout evaluation.

## What changed since the 2026-07-19 ratification

| Aspect | Old (v1, 2026-07-19) | New (v3, 2026-08-02) |
|--------|----------------------|---------------------|
| Strategy | `FreqForge_Override` | `FreqForge_Gate0_Core_v1` |
| Manifest | `evaluation-manifest/v1` | `evaluation-manifest/v3` (`gate0-manifest-v3-20260721`) |
| Primo signals | Present | **Removed entirely** |
| FleetRiskManager | Present | **Removed entirely** |
| AI/Shadow/LLM paths | Present | **Removed entirely** |
| sys.path manipulation | Present | **Removed entirely** |
| confirm_trade_entry override | Present | **Removed entirely** |
| bot_loop_start | Present | **Removed entirely** |
| Regime classification | Post-entry lookahead | **Entry-time, per-pair, pre-entry data only** |
| Holdout isolation | Not enforced | **Selection runner never sees holdout** |
| max_missing_candles | Fixed 100 | **5% formula: `floor(total_expected × 0.05)`** |
| tail_quantile | Not present | **0.05** |
| min_duration_days | 180 | **90** (matches WF windows) |
| Partition intervals | `[start, end]` with 23:59:59 | **Proper half-open `[start, end)`** |

## Strategy provenance (verified from repository)

```
strategy_class:        FreqForge_Gate0_Core_v1
strategy_file:         freqforge/user_data/strategies/FreqForge_Gate0_Core_v1.py
strategy_sha256:       112ff28ef7bd1fdc28341b4e53516b48fe7c94278c747691077d4d2e6e7916c0
config_file:           freqforge/user_data/config.example.json
config_sha256:         7647ed03a88e49a63c9916e9e8137ce84d5e12a90f461785a694591e5e70345d
shared_module_sha256:  d977c4ef9cff6c87c8b001a18c9b876fdd0f67eaa1fde5fa7325a9ffa8c14353
```

## Freqtrade image (pinned digest)

```
freqtradeorg/freqtrade@sha256:87aa5c6d65359b34e9d99a0bb260a38c0efe0315253811e6f48c2afe8f278a6a
```

## Repository commit

```
main_sha: 05406a9b32221089fc5090dcc545efbbed095b4e
```

## Evaluation manifest v3 — complete frozen contract

### Market specification

| Field | Value |
|-------|-------|
| Exchange | `bitget` |
| Trading mode | `futures` |
| Market type | `linear` |
| Pairs | `BTC/USDT`, `ETH/USDT`, `SOL/USDT` |
| Timeframe | `15m` |
| Benchmark | `BTC/USDT` futures 15m (buy-and-hold) |

### Partition windows (half-open `[start, end)`)

| Window | Start | End | Duration |
|--------|-------|-----|----------|
| Warm-up | 2024-12-01T00:00:00Z | 2025-01-01T00:00:00Z | 1 month |
| Calibration | 2025-01-01T00:00:00Z | 2025-07-01T00:00:00Z | 6 months |
| Walk-forward 1 | 2025-07-01T00:00:00Z | 2025-10-01T00:00:00Z | 3 months |
| Walk-forward 2 | 2025-10-01T00:00:00Z | 2026-01-01T00:00:00Z | 3 months |
| Holdout (sealed) | 2026-01-01T00:00:00Z | 2026-07-01T00:00:00Z | 6 months |

### Cost model

| Parameter | Value |
|-----------|-------|
| Entry fee | 0.05% taker |
| Exit fee | 0.05% taker |
| Slippage | 0.02% per trade |
| Funding | 0.01% per 8h |
| Leverage | 1.0× |
| Initial equity | 10,000 USDT |

### Evaluation thresholds (v3, frozen)

| Threshold | Value | Rule |
|-----------|-------|------|
| `max_drawdown_pct` | **25.0%** | OOS drawdown must be < 25% |
| `min_profit_factor` | **1.3** | OOS profit factor must be > 1.3 |
| `min_trades` | **100** | Minimum closed trades |
| `min_regimes` | **2** | Minimum distinct market regimes |
| `min_duration_days` | **90** | Minimum OOS duration |
| `min_edge_mean` | **0.01** | Edge mean > 0.01 |
| `min_edge_lower_bound` | **0.0** | Edge lower bound ≥ 0.0 |
| `max_confidence_interval_width` | **0.05** | CI width ≤ 0.05 |
| `max_missing_candles` | **5% formula** | `floor(total_expected × 0.05)` |
| `tail_quantile` | **0.05** | Bootstrap tail quantile |
| `bootstrap_samples` | **1000** | Bootstrap iterations |
| `bootstrap_block_size` | **4** | Block bootstrap size |
| `confidence_level` | **0.95** | Confidence level |
| `bootstrap_seed` | **42** | Deterministic seed |

### Decision rules

| Outcome | Condition |
|---------|-----------|
| `PASS_SELECTION` | All guardrails met |
| `EXTEND` | Insufficient trades/duration/regimes |
| `REJECT` | Drawdown ≥ 25% or profit factor ≤ 1.3 |
| `INVALID` | Data gap > 5% or leakage detected |

### Policies

| Policy | Value |
|--------|-------|
| `boundary_policy` | `STRICT_CONTAINED` — no data from future windows |
| `continuation_policy` | `REPORT_ONLY` — no automatic progression |
| `mark_to_market_price_field` | `close` |

## Pre-existing evidence (A0 preflight GREEN)

- **A0 preflight:** PR #682 (`72421de`) — 146/146 Gate-0 suite passed
- **Backtest contract:** PR #687 (`79ad6dd`) — pinned image digest, selection dataset, funding adapter
- **Snapshot v1:** 156,489 candles (3 × 52,163) at `/opt/data/hermes/gate0-snapshot/`, SHA-256 verified
- **C5.3 corrective:** PR #668 (`da60da3`) — stripped strategy, manifest v3, entry-time regime, selection isolation
- **C5.4 corrective:** PR #675 (`8b4dace`) — SelectionOutcomeV1 fix, pair normalization, unified guardrails
- **#674 import-guard:** PR #690 (`ea04ca2`) — deterministic test isolation, 18/18 tests

## Required human action

Luke must post a signed comment on #604 containing:

```text
APPROVED_GATE0_STRATEGY_AND_MANIFEST_V3
confirmed_by=Luke
strategy=FreqForge_Gate0_Core_v1
manifest_version=evaluation-manifest/v3
manifest_id=gate0-manifest-v3-20260721
main_sha=05406a9b32221089fc5090dcc545efbbed095b4e
image_digest=freqtradeorg/freqtrade@sha256:87aa5c6d65359b34e9d99a0bb260a38c0efe0315253811e6f48c2afe8f278a6a
strategy_sha256=112ff28ef7bd1fdc28341b4e53516b48fe7c94278c747691077d4d2e6e7916c0
config_sha256=7647ed03a88e49a63c9916e9e8137ce84d5e12a90f461785a694591e5e70345d
pairs=BTC/USDT,ETH/USDT,SOL/USDT
timeframe=15m
warmup_start=2024-12-01T00:00:00Z
selection_end=2026-01-01T00:00:00Z
holdout_end=2026-07-01T00:00:00Z
thresholds=gate0-corrective-v3 (max_drawdown=25%, min_profit_factor=1.3, min_trades=100, min_regimes=2, min_duration_days=90, tail_quantile=0.05)
```

## What happens after ratification

1. **A2 Bitget Snapshot v2 issue** created — warm-up + funding + selection windows, new immutable path
2. **Luke issues `APPROVED_A2_BITGET_SNAPSHOT_V2`** — time-limited A2 marker
3. **Fetch/freeze** warm-up + selection + sealed holdout + funding
4. **A2 Selection Backtest issue** created
5. **Luke issues selection-backtest marker**
6. **Execute selection-only backtest** → `PASS_SELECTION` / `EXTEND` / `REJECT` / `INVALID`
7. **C6 holdout ceremony** — only after separate human marker
8. **Gate-0 edge decision** recorded → Phase C exit gate satisfied

## Safety invariants (unchanged)

- No threshold may change after holdout inspection without invalidating the run
- Holdout remains sealed until C6 marker
- No `dry_run=false`, no live orders, no live credentials
- Hermes must NOT self-ratify — this document is a proposal only
