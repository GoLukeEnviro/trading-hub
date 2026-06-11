# Issues #55–#61 — Evidence Matrix

> **Updated at commit `81884db`** (PR #166 merge — Issue #59 attribution reports merged).
>
> All trading-hub issues #55–#61 were inspected via GitHub API on 2026-06-11.
> Issues #55–#59 are now COMPLETED and merged. Only #60 (maintenance) and #61 (tracker) remain OPEN.

---

## Matrix

| Issue | Title | State | Has PR? | Has Commits? | Closed? | Code Written? | Notes |
|-------|-------|-------|---------|--------------|---------|---------------|-------|
| [#55](https://github.com/GoLukeEnviro/trading-hub/issues/55) | Define canonical Regime Detector schema and integration boundary | **🔴 CLOSED** | ✅ PR [#161](https://github.com/GoLukeEnviro/trading-hub/pull/161) merged | ✅ `e0b5310`, `538464a` | ✅ **Merged at `9017dd4`** | ✅ Spec document + 19 structural tests | Canonical regime schema documented. Next: #56. |
| [#56](https://github.com/GoLukeEnviro/trading-hub/issues/56) | Implement Regime Detector run and Shadowlock enrichment | **🟢 COMPLETED** | ✅ PR [#163](https://github.com/GoLukeEnviro/trading-hub/pull/163) merged | ✅ `9a4f3e1`, `0d8b76c` | ✅ **Merged at `fadfefa`** | ✅ Code written | Regime detector implemented. Regime labels enriched into Shadowlock. |
| [#57](https://github.com/GoLukeEnviro/trading-hub/issues/57) | Build Performance Attribution Engine by source and regime | **🟢 COMPLETED** | ✅ PR [#164](https://github.com/GoLukeEnviro/trading-hub/pull/164) merged | ✅ `c803c7b` | ✅ **Merged at `773e9cb`** | ✅ Code written | Performance attribution engine implemented. |
| [#58](https://github.com/GoLukeEnviro/trading-hub/issues/58) | Implement source_regime_stats summary table and updater | **🟢 COMPLETED** | ✅ PR [#165](https://github.com/GoLukeEnviro/trading-hub/pull/165) merged | ✅ `f1590b5`, `13ce90f` | ✅ **Merged at `e806fc8`** | ✅ Code written | source_regime_stats SQLite cache implemented. |
| [#59](https://github.com/GoLukeEnviro/trading-hub/issues/59) | Generate automated Attribution Reports from Shadowlock and source_regime_stats | **🟢 COMPLETED** | ✅ PR [#166](https://github.com/GoLukeEnviro/trading-hub/pull/166) merged | ✅ `10a2093` | ✅ **Merged at `81884db`** | ✅ Code written | Automated attribution reports generated. |
| [#60](https://github.com/GoLukeEnviro/trading-hub/issues/60) | Add Shadowlock SQLite maintenance command and approval-gated daily job plan | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Depends on #57. No code written. |
| [#61](https://github.com/GoLukeEnviro/trading-hub/issues/61) | Tracker — Intelligence Layer implementation | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Umbrella tracker only. No code expected. |

---

## Traffic Light Summary

| Status | Count | Issues |
|--------|-------|--------|
| 🟢 Has evidence of implementation (merged) | 5 | #55, #56, #57, #58, #59 |
| 🟡 OPEN — no PR, no commits | 2 | #60, #61 |

---

*Updated at commit 81884db, 2026-06-11. Issues #55–#59 completed and merged.*
