# Issues #55–#61 — Evidence Matrix

> **Updated at commit `9017dd4`** (PR #161 merge — Issue #55 now implemented).
>
> All trading-hub issues #55–#61 were inspected via GitHub API on 2026-06-11.
> Issue #55 now has a completed spec PR that was reviewed and merged.

---

## Matrix

| Issue | Title | State | Has PR? | Has Commits? | Closed? | Code Written? | Notes |
|-------|-------|-------|---------|--------------|---------|---------------|-------|
| [#55](https://github.com/GoLukeEnviro/trading-hub/issues/55) | Define canonical Regime Detector schema and integration boundary | **🔴 CLOSED** | ✅ PR [#161](https://github.com/GoLukeEnviro/trading-hub/pull/161) merged | ✅ `e0b5310`, `538464a` | ✅ **Merged at `9017dd4`** | ✅ Spec document + 19 structural tests | Canonical regime schema documented. Next: #56. |
| [#56](https://github.com/GoLukeEnviro/trading-hub/issues/56) | Implement Regime Detector run and Shadowlock enrichment | **OPEN** | 🔄 In progress | In progress | ❌ No | ❌ Not yet | Depends on #55 (complete). Active work item. |
| [#57](https://github.com/GoLukeEnviro/trading-hub/issues/57) | Build Performance Attribution Engine by source and regime | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Depends on #56. No code written. |
| [#58](https://github.com/GoLukeEnviro/trading-hub/issues/58) | Implement source_regime_stats summary table and updater | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Depends on #56. No code written. |
| [#59](https://github.com/GoLukeEnviro/trading-hub/issues/59) | Generate automated Attribution Reports from Shadowlock and source_regime_stats | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Depends on #57 + #58. No code written. |
| [#60](https://github.com/GoLukeEnviro/trading-hub/issues/60) | Add Shadowlock SQLite maintenance command and approval-gated daily job plan | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Depends on #57. No code written. |
| [#61](https://github.com/GoLukeEnviro/trading-hub/issues/61) | Tracker — Intelligence Layer implementation | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Umbrella tracker only. No code expected. |

---

## Traffic Light Summary

| Status | Count | Issues |
|--------|-------|--------|
| 🟢 Has evidence of implementation (merged) | 1 | #55 |
| 🔄 Has PR in progress | 1 | #56 (active work item) |
| 🔴 OPEN — no code, no PR, no commits | 5 | #57, #58, #59, #60, #61 |

---

*Updated at commit 9017dd4, 2026-06-11. Issue #55 completed and merged.*
