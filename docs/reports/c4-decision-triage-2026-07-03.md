# C4 Decision Triage Report — 2026-07-03

**Issue:** #438 — C4 Decision Triage
**Status:** ✅ Triage Complete
**Decision Validity:** VALID — ROLLBACK_RECOMMENDED stands

---

## 1. Measurement-Window Boundaries

| Property | Value |
|----------|-------|
| C3 ceremony timestamp | 2026-07-02T12:00:00Z |
| Measurement window (14 days) | 2026-06-18T12:00:00Z → 2026-07-02T12:00:00Z |
| LINK/USDT loss date | 2026-06-24T16:51:12Z |
| **Inside window?** | **YES** ✅ |

## 2. LINK/USDT Loss — Contamination Check

**Verdict: NOT contamination.** The LINK/USDT trade (id=59) closed on 2026-06-24 at -9.33%. This falls squarely inside the 14-day measurement window (2026-06-18 to 2026-07-02). It is a legitimate canary performance data point.

## 3. Metric Input Analysis

The C4 module was fed **all 63 lifetime trades** from the canary's dry-run database, not only the 12 trades that fell inside the 14-day window. This is a **data-scope mismatch** — the module's `measurement_window_days` constant (14) is a documentation value, not a data filter. The caller is responsible for providing window-scoped metrics.

However, this does **not** invalidate the ROLLBACK_RECOMMENDED decision:

| Calculation Method | Max Drawdown | Breach? |
|--------------------|:------------:|:-------:|
| Lifetime (C4 reported) | 82.79% | ❌ BREACH |
| Window-relative (start at 0) | 323.38% | ❌ BREACH |
| Continuation (from prior cumulative) | 75.08% | ❌ BREACH |

The max_drawdown metric is a BREACH in **all three** calculation methods. The ROLLBACK_RECOMMENDED decision is robust to the data-scope issue.

## 4. Other Metrics (Window-Filtered, 12 trades)

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Win rate | 91.67% | >= 40% | ✅ OK |
| Profit factor | 0.36 | >= 1.0 | ⚠️ BORDERLINE |
| Sharpe ratio | -0.18 | >= 0.5 | ❌ BREACH |
| Max drawdown | 75.08% | <= 15% | ❌ BREACH |
| Daily loss count | 1 | <= 3 | ✅ OK |

Even with window-filtered data, the decision would be ROLLBACK_RECOMMENDED (two BREACH metrics: max_drawdown and sharpe_ratio).

## 5. Rollback Plan Reference

The C3 ceremony artifacts contain a complete rollback plan at:
`var/si_v2/live_canary_activation_ceremony/live_canary_activation_ceremony.json` → `rollback_plan`

7 steps documented: kill switch EMERGENCY → halt container → restore dry-run config → redeploy → verify → reset kill switch → post-mortem.

## 6. Recommendation

| Item | Status |
|------|--------|
| C4 decision validity | ✅ VALID — ROLLBACK_RECOMMENDED |
| LINK/USDT contamination | ❌ NOT contamination — inside window |
| Data-scope issue | ⚠️ C4 fed 63 lifetime trades, not 12 window-filtered — but outcome unchanged |
| Rollback required? | Human decision needed |
| D1 gate | ❌ BLOCKED — requires C4 KEEP + APPROVED_LIVE_FLEET_ROLLOUT |

## 7. Next Gate Status

| Gate | Status | Required |
|------|--------|----------|
| C4 KEEP decision | ❌ ROLLBACK_RECOMMENDED | KEEP required |
| APPROVED_LIVE_FLEET_ROLLOUT | ❌ Missing | Human approval marker |
| D1 | ❌ BLOCKED | Both above |
