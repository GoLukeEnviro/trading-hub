# Recovery Candidates — forensics-20260608-001

HYPOTHESIS: no high-confidence candidate exists; the single row below is a low-confidence speculative rollback because `regime-hybrid` is the only bot with a high-sample losing window [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260503T000000Z-20260602T000000Z] [src: docs/context/trade-export-freqforge-2026-06-07_summary.json, id: lines 8-20] [src: docs/context/trade-export-freqforge-canary-2026-06-07_summary.json, id: lines 8-20] [src: docs/context/trade-export-freqai-rebel-2026-06-07_summary.json, id: lines 8-21].

| Rank | Bot | Candidate | Window | Window PF | delta_PF_est | Recovery confidence | Restoration complexity | priority_score | Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | regime-hybrid | Rollback the RR-FIX stack one layer at a time and re-test (start with the latest ROI/stoploss/trailing changes, then gate/short enablements). | 2026-05-03T00:00:00Z → 2026-06-02T00:00:00Z | 0.5498 | 0.4502 | 0.25 | 3.5 | 0.0322 | speculative / low confidence | [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260503T000000Z-20260602T000000Z] [src: git, id: bd1cfa5] [src: git, id: 3d560f5] [src: git, id: 3f52914] |

Notes:
- `delta_PF_est` is measured against breakeven PF=1.0 for the only high-sample losing window [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260503T000000Z-20260602T000000Z].
- `recovery_confidence` and `restoration_complexity` are heuristic estimates because the data never produces a clean before/after high-sample split [src: docs/context/reconstruction/profitability-map-2026-06-08.csv, id: regime-hybrid-20260503T000000Z-20260602T000000Z].
