# Profitability Forensics Report — forensics-20260608-001

## 0. Scope, sources, and methodology
- Shadowlock was live during this run; heartbeat entries exist in `var/trading-shadowlock/logs/2026/06/08.jsonl` [src: var/trading-shadowlock/logs/2026/06/08.jsonl, id: lines 1-50].
- The report uses the four trade-history summaries from `docs/context/trade-export-*-2026-06-07_summary.json` plus the matching CSV trade exports [src: docs/context/trade-export-freqforge-2026-06-07_summary.json, id: lines 1-20] [src: docs/context/trade-export-freqforge-canary-2026-06-07_summary.json, id: lines 1-20] [src: docs/context/trade-export-regime-hybrid-2026-06-07_summary.json, id: lines 1-20] [src: docs/context/trade-export-freqai-rebel-2026-06-07_summary.json, id: lines 1-21].
- HYPOTHESIS: because the requested profitability-forensics spec file was absent, I used a conservative window classifier (assumption): `NO_DATA = 0 trades`, `LOW_SAMPLE < 30 trades`, `PROFITABLE PF >= 1.2`, `MARGINAL 1.0 <= PF < 1.2`, `LOSING PF < 1.0`. [src: read_file, id: /home/hermes/projects/trading/docs/specs/profitability-forensics-agent-spec.md not found]

## 1. Current State Anchor Table
| Bot | total_trades | win_rate | profit_factor | net_profit_usdt | max_DD_pct | NO_TRADE_DATA | Sources |
|---|---|---|---|---|---|---|---|
| freqforge | 64 | 84.38% | 1.6426 | +23.2235 | 170.1705% | false | [src: docs/context/trade-export-freqforge-2026-06-07_summary.json, id: lines 1-20] |
| freqforge-canary | 44 | 93.18% | 241.7329 | +7.4034 | 2.4414% | false | [src: docs/context/trade-export-freqforge-canary-2026-06-07_summary.json, id: lines 1-20] |
| regime-hybrid | 48 | 72.92% | 0.5834 | -6.8190 | 3676.7260% | false | [src: docs/context/trade-export-regime-hybrid-2026-06-07_summary.json, id: lines 1-20] |
| freqai-rebel | 0 | N/A | N/A | +0.0000 | N/A | true | [src: docs/context/trade-export-freqai-rebel-2026-06-07_summary.json, id: lines 1-21] |

## 2. Mine Git History — material parameter changes in the last 90 days
### freqforge

| Commit | Date | Material parameter changes | Sources |
|---|---|---|---|
| d451819 | 2026-05-21 | can_short False→True; minimal_roi reset to 0.045/0.030/0.020/0.010; stoploss -0.09→-0.045; use_custom_stoploss False→True; trailing_stop False→True; FleetRisk sync + short entry logic added; AI override changed to no-op; direct short override disabled. | [src: git, id: d451819] |
| 48756c0 | 2026-06-05 | minimal_roi widened to 0.060/0.040/0.025/0.015; stoploss -0.045→-0.050; trailing_stop True→False; AI_OVERRIDE_ALLOWED_PAIRS added (BTC/ETH/SOL); AI_OVERRIDE_CONFIDENCE_MIN=0.75; adx_rel_threshold and rsi_oversold ranges loosened; AI override activated on the latest candle. | [src: git, id: 48756c0] |
### freqforge-canary

| Commit | Date | Material parameter changes | Sources |
|---|---|---|---|
| d451819 | 2026-05-21 | can_short False→True; FleetRisk sync + short entry logic added; AI override changed to no-op; direct short override disabled; trade-entry gating now checks FleetRisk plus PrimoGate; JSONL logging escape bug still noted in commit message. | [src: git, id: d451819] |
### regime-hybrid

| Commit | Date | Material parameter changes | Sources |
|---|---|---|---|
| 9c88d42 | 2026-05-16 | RebelLiquidation target threshold tightened from close.shift(-12) > close*1.005 to > close*1.0005; RegimeSwitchingHybrid_v7_v04_Integration introduced dry_run_override=True with dry_run_confidence_threshold=0.20 and direct dry-run gate bypass. | [src: git, id: 9c88d42] |
| b6530c3 | 2026-05-21 | FleetRiskManager wired into RegimeSwitchingHybrid_v7_v04_Integration; canonical CONFIDENCE_MIN=0.65 added; long/short gates now AND FleetRisk; confirm_trade_entry now blocks on FleetRisk; dry-run bypass was superseded by canonical threshold logic. | [src: git, id: b6530c3] |
| 3d560f5 | 2026-05-23 | RegimeSwitchingHybrid_v6_Stable ROI reduced to 0.015/0.008/0.004, atr_sl_trend tightened to 2.5, atr_sl_range narrowed to 1.5-2.5; RegimeSwitchingHybrid_v7_v04_Integration ROI reduced to 0.012/0.008/0.004, stoploss -0.015, trailing_stop=True, trailing_stop_positive=0.006, trailing_stop_positive_offset=0.012. | [src: git, id: 3d560f5] |
| bd1cfa5 | 2026-05-28 | RR-FIX v1 widened RegimeSwitchingHybrid_v7_v04_Integration ROI to 0.04/0.025/0.015/0.008; stoploss -0.025; use_custom_stoploss=True; trailing_stop_positive=0.012; trailing_stop_positive_offset=0.02; atr_sl_trend=1.2; atr_sl_range=0.8-1.5 default 1.0; atr_tp_trend=1.5-3.0 default 2.2. | [src: git, id: bd1cfa5] |
| 3f52914 | 2026-06-02 | can_short False→True in RegimeSwitchingHybrid_v7_v04_Integration (dry-run short entries now allowed). | [src: git, id: 3f52914] |
| e9ed186 | 2026-06-01 | same can_short False→True flip was also present in the companion self-healing commit set; no additional parameter changes beyond the short enable. | [src: git, id: e9ed186] |
### freqai-rebel

| Commit | Date | Material parameter changes | Sources |
|---|---|---|---|
|| aa53c92 | 2026-05-14 | initial RebelLiquidation add with timeframe=5m, startup_candle_count=40, minimal_roi=0.025, stoploss=-0.015, trailing_stop=True, trailing_stop_positive=0.008, trailing_stop_positive_offset=0.012, use_entry_signal=True, and FreqAI target `close.shift(-12) > close * 1.005`. | [src: git, id: aa53c92] |
|| 9c88d42 | 2026-05-16 | RebelLiquidation target tightened from `close.shift(-12) > close * 1.005` to `close.shift(-12) > close * 1.0005` (more permissive target). | [src: git, id: 9c88d42] |
|| 5679de3 | 2026-06-05 | added RebelLiquidationWFTop15 with timeframe=5m, startup_candle_count=40, minimal_roi=0.025, stoploss=-0.015, trailing_stop=True, trailing_stop_positive=0.008, trailing_stop_positive_offset=0.012, use_entry_signal=True, and 12-candle forward target >0.05%. | [src: git, id: 5679de3] |

## 3. Map Performance to Timeline — 30-day windows, 7-day step
| Bot | Window | Trades | PF | Net_USDT | Class | Commits | Sources |
|---|---|---|---|---|---|---|---|
| freqforge | 2026-05-10T00:00:00Z → 2026-06-09T00:00:00Z | 64 | 1.6426 | +23.2235 | PROFITABLE | 48756c0,d451819,801ff86,9e5ba74 | [src: docs/context/trade-export-freqforge-2026-06-07_trades.csv, id: window 2026-05-10→2026-06-09] |
| freqforge | 2026-05-17T00:00:00Z → 2026-06-16T00:00:00Z | 48 | 1.7601 | +20.2741 | PROFITABLE | 48756c0,d451819 | [src: docs/context/trade-export-freqforge-2026-06-07_trades.csv, id: window 2026-05-17→2026-06-16] |
| freqforge-canary | 2026-05-17T00:00:00Z → 2026-06-16T00:00:00Z | 44 | 241.7329 | +7.4034 | PROFITABLE | d451819 | [src: docs/context/trade-export-freqforge-canary-2026-06-07_trades.csv, id: window 2026-05-17→2026-06-16] |
| regime-hybrid | 2026-05-03T00:00:00Z → 2026-06-02T00:00:00Z | 44 | 0.5498 | -7.0816 | LOSING | e9ed186,bd1cfa5,3d560f5,b6411d4,b6530c3,9c88d42,801ff86,9e5ba74 | [src: docs/context/trade-export-regime-hybrid-2026-06-07_trades.csv, id: window 2026-05-03→2026-06-02] |
| freqai-rebel | NO_DATA | 0 | N/A | +0.0000 | NO_DATA |  | [src: docs/context/trade-export-freqai-rebel-2026-06-07_summary.json, id: lines 8-21] |

## 4. Attribute Causation
| Bot | Phase-4 confidence | Why | Sources |
|---|---|---|---|
| freqforge | insufficient_data | All high-sample windows remain PROFITABLE; later windows fall to LOW_SAMPLE, and the profitable slices overlap both d451819 and 48756c0 so there is no clean before/after split. | [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: freqforge-20260510T000000Z-20260609T000000Z] [src: git, id: d451819] [src: git, id: 48756c0] |
| freqforge-canary | insufficient_data | The 44-trade slice is PROFITABLE, but the next windows fall below 30 trades, so phase-4 causation cannot separate pre/post-commit behavior cleanly. | [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: freqforge-canary-20260517T000000Z-20260616T000000Z] [src: git, id: d451819] |
| regime-hybrid | insufficient_data | The only high-sample window is LOSING; later windows are LOW_SAMPLE, so there is no second high-sample window to test for a clean inflection. | [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260503T000000Z-20260602T000000Z] [src: git, id: 9c88d42] [src: git, id: b6530c3] [src: git, id: 3d560f5] [src: git, id: bd1cfa5] [src: git, id: 3f52914] |
| freqai-rebel | insufficient_data | NO_TRADE_DATA=true, so phase 3-5 were skipped. | [src: docs/context/trade-export-freqai-rebel-2026-06-07_summary.json, id: lines 8-21] |

## 5. Identify Recovery Candidates
The table below is intentionally conservative. There is one speculative candidate only, and it is low-confidence because the evidence never produces a clean high-sample inflection point [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260503T000000Z-20260602T000000Z] [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: freqforge-20260510T000000Z-20260609T000000Z] [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: freqforge-canary-20260517T000000Z-20260616T000000Z].
| Rank | Bot | Candidate | Window | Window PF | delta_PF_est | Recovery confidence | Restoration complexity | priority_score | Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | regime-hybrid | Rollback the RR-FIX stack one layer at a time and re-test (start with the latest ROI/stoploss/trailing changes, then gate/short enablements). | 2026-05-03T00:00:00Z → 2026-06-02T00:00:00Z | 0.5498 | 0.4502 | 0.25 | 3.5 | 0.0322 | speculative / low confidence | [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260503T000000Z-20260602T000000Z] [src: git, id: bd1cfa5] [src: git, id: 3d560f5] [src: git, id: 3f52914] |

## 6. Data Gaps
- HYPOTHESIS: The requested spec files were not present in the repo on this run, so I used docs/specs/self-improvement-orchestrator-spec.md and shadowlock/README.md as the nearest authoritative fallbacks. [src: read_file, id: /home/hermes/projects/trading/docs/specs/profitability-forensics-agent-spec.md not found] [src: read_file, id: /home/hermes/projects/trading/docs/specs/bot-roles-and-shadow-architecture.md not found] [src: docs/specs/self-improvement-orchestrator-spec.md, id: lines 12-18; 172-177; 323-328] [src: shadowlock/README.md, id: lines 52-74]
- `freqai-rebel` has `NO_TRADE_DATA=true`; phase 3-5 were intentionally skipped for that bot [src: docs/context/trade-export-freqai-rebel-2026-06-07_summary.json, id: lines 8-21].
- The rolling 30-day windows produce only one high-sample losing slice for `regime-hybrid`; later slices are `LOW_SAMPLE`, so no clean inflection can be proven [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260510T000000Z-20260609T000000Z] [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260517T000000Z-20260616T000000Z] [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260524T000000Z-20260623T000000Z] [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260531T000000Z-20260630T000000Z] [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260607T000000Z-20260707T000000Z].

## 7. Verdict
WARNING/RED — the fleet is not cleanly recoverable from the current evidence: `regime-hybrid` has the only high-sample losing window, and the other bots are either profitable or data-starved, so no high-confidence causal inflection was found [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260503T000000Z-20260602T000000Z] [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: freqforge-20260510T000000Z-20260609T000000Z] [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: freqforge-canary-20260517T000000Z-20260616T000000Z] [src: docs/context/trade-export-freqai-rebel-2026-06-07_summary.json, id: lines 8-21].
