# Issues #55–#61 — Evidence Matrix

> **Grounded at commit `fdac27c`** (PR #160 merge).
>
> All trading-hub issues #55–#61 were inspected via GitHub API on 2026-06-11.
> No PRs or commits exist for any of these issues in the `trading-hub` repo.
> Historical references in SI v2 docs to "#55" and "#56" as "done" refer to
> **ai4trade-bot** issues (now closed/merged), not these trading-hub issues.

---

## Matrix

| Issue | Title | State | Has PR? | Has Commits? | Closed? | Code Written? | Notes |
|-------|-------|-------|---------|--------------|---------|---------------|-------|
| [#55](https://github.com/GoLukeEnviro/trading-hub/issues/55) | Define canonical Regime Detector schema and integration boundary | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Purely design/spec. No implementation exists. |
| [#56](https://github.com/GoLukeEnviro/trading-hub/issues/56) | Implement Regime Detector run and Shadowlock enrichment | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Depends on #55. No code written. |
| [#57](https://github.com/GoLukeEnviro/trading-hub/issues/57) | Build Performance Attribution Engine by source and regime | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Depends on #56. No code written. |
| [#58](https://github.com/GoLukeEnviro/trading-hub/issues/58) | Implement source_regime_stats summary table and updater | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Depends on #56. No code written. |
| [#59](https://github.com/GoLukeEnviro/trading-hub/issues/59) | Generate automated Attribution Reports from Shadowlock and source_regime_stats | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Depends on #57 + #58. No code written. |
| [#60](https://github.com/GoLukeEnviro/trading-hub/issues/60) | Add Shadowlock SQLite maintenance command and approval-gated daily job plan | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Depends on #57. No code written. |
| [#61](https://github.com/GoLukeEnviro/trading-hub/issues/61) | Tracker — Intelligence Layer implementation | **OPEN** | ❌ None | ❌ None | ❌ No | ❌ No | Umbrella tracker only. No code expected. |

---

## Comparison: ai4trade-bot Issues with Matching Numbers

The SI v2 documentation historically references "#51–#56" as "Rainbow core done."
Those numbers refer to issues in the **ai4trade-bot** repository, not trading-hub.

| ai4trade-bot Issue | Title | State | Notes |
|--------------------|-------|-------|-------|
| [#55](https://github.com/GoLukeEnviro/ai4trade-bot/issues/55) | [SI v2][Phase 0] Tracker — Rainbow Signal Provider foundation | OPEN | Tracker, not the same as trading-hub #55 |
| [#56](https://github.com/GoLukeEnviro/ai4trade-bot/issues/56) | [SI v2][Rainbow] Add sanitized signal fixture pack for contract validation | CLOSED | Merged as ai4trade-bot PR #60 |
| [#59](https://github.com/GoLukeEnviro/ai4trade-bot/issues/59) | [SI v2][Rainbow] Define read-only Signal Provider contract (#51) | MERGED | ai4trade-bot PR |
| [#60](https://github.com/GoLukeEnviro/ai4trade-bot/issues/60) | [SI v2][Rainbow] Add sanitized signal fixture pack (#56) | MERGED | ai4trade-bot PR |

> **Do not conflate these.** The trading-hub issues #55–#61 are Phase 1
> intelligence issues. None have any code or PRs associated with them.
> The fixture pack referenced as "#56" in SI v2 doc comments refers to the
> **ai4trade-bot** issue that generated the fixture files, not the
> trading-hub issue #56.

---

## Traffic Light Summary

| Status | Count | Issues |
|--------|-------|--------|
| 🔴 OPEN — no code, no PR, no commits | 7 | #55, #56, #57, #58, #59, #60, #61 |
| 🟢 Has evidence of implementation | 0 | — |
| 🔄 Has PR in progress | 0 | — |

**Verdict: 0 of 7 Phase 1 Intelligence issues have any implementation
evidence. The entire Phase 1 epic is at zero.**

---

## Historical Report Notice

Older SI v2 reports (progress dashboard, readiness matrix, architecture index)
may reference "#55" and "#56" as "done." Those references are to the
**ai4trade-bot** issue numbers from the Rainbow core phase and are NOT
applicable to the current trading-hub issue set. Those reports are retained
as historical artifacts only.

---

*Generated at commit fdac27c, 2026-06-11*
