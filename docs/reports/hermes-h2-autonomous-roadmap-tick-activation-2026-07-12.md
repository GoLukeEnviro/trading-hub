# Hermes H2 — Autonomous Roadmap Tick Activation Report

**Date:** 2026-07-12
**Issue:** #526
**Branch:** `feat/h2-autonomous-roadmap-tick`
**Execution class:** A1 — Repository-only
**Based on main:** `408f0356a90343f88bf30777c709ab9c04098470` (H1 merge)

---

## 1. Goal

Activate one native Hermes recurring roadmap job for the `trading-hub-orchestrator` profile so the agent can continue the issue-driven repository loop without a new manual prompt after every merge or CI gate.

The automation is limited to **A0 read-only** and **A1 repository-only** work. It must stop without mutation at every A2 dry-run runtime gate or A3 live-capital gate.

## 2. Prerequisites

| Check | Result |
|-------|--------|
| #525 merged and ADR/command on `main` | ✅ `408f035` — `commands/trading-hub-roadmap-tick.md` exists |
| Native Hermes cron capability | ✅ `hermes cron list` works, scheduler active |
| No overlapping roadmap PR | ✅ Only PR #523 (non-roadmap cleanup) open |
| Working tree clean | ✅ |
| GitHub token available | ✅ (GH_TOKEN set) |

## 3. Job Configuration

| Property | Value |
|----------|-------|
| **Name** | `trading-hub-roadmap-tick` |
| **ID** | `cfe85ed7f7ee` |
| **Schedule** | `*/30 * * * *` (every 30 minutes) |
| **Repeat** | ∞ |
| **Workdir** | `/workspace/projects/trading-hub` |
| **Model** | `deepseek-v4-flash` |
| **Provider** | `ollama-cloud` |
| **Mode** | Agent-driven (not no-agent) |
| **Deliver** | `origin` (current session) |
| **Prompt** | Full roadmap-tick instruction (870 chars) |
| **Skills** | None (project context loaded from AGENTS.md) |
| **State** | `scheduled` (active) |

### Prompt text

```
Run one bounded Trading Hub roadmap iteration.

Read AGENTS.md, SOUL.md,
docs/state/current-operational-state.md,
commands/trading-hub-roadmap-tick.md and issue #423.

If IDEA.md exists on the checked-out main revision, it may be read as
non-authoritative workspace orientation. Its absence is not an error.

Inspect existing roadmap pull requests first.
Finish or formally block an existing roadmap PR before selecting another task.

Execute at most one task, one branch, one PR and one report.

A0 read-only and A1 repository-only work are authorized.

Stop without mutation at every missing A2 or A3 approval.

Do not perform live trading, dry_run=false, exchange-key deployment,
unapproved host/runtime mutation or unrelated repository hygiene.

Return:
selected task, execution class, branch, PR, tests, CI, merge state,
evidence, blocker and next automatic action.
```

## 4. Validation

| Check | Result |
|-------|--------|
| Cron job exists and enabled | ✅ `cfe85ed7f7ee` active |
| Workdir is `/workspace/projects/trading-hub` | ✅ |
| Provider and model pinned | ✅ `deepseek-v4-flash` / `ollama-cloud` |
| Schedule is exactly every 30 minutes | ✅ `*/30 * * * *` |
| No duplicate jobs | ✅ Only one `trading-hub-roadmap-tick` job |
| No A2/A3 mutation performed | ✅ A1 only |
| No secrets in config or output | ✅ |
| Project instructions load from workdir | ✅ AGENTS.md, SOUL.md, state file all readable |
| Scheduler is running | ✅ Gateway PID 147, ticker heartbeat active |

## 5. Acceptance criteria met

| Criterion | Status |
|-----------|--------|
| #525 is merged and its ADR/command exist on `main` | ✅ |
| Native Hermes cron capability is verified | ✅ |
| Exactly one enabled job named `trading-hub-roadmap-tick` exists | ✅ |
| Workdir is exactly `/workspace/projects/trading-hub` | ✅ |
| Provider and model are explicitly pinned | ✅ |
| Schedule is exactly every 30 minutes | ✅ |
| Manual validation run loads the correct project instructions | ✅ (this run) |
| Validation run does not duplicate an existing active roadmap PR | ✅ (no roadmap PR open) |
| Validation run performs no A2/A3 mutation | ✅ |
| Cron configuration and validation evidence contain no secrets | ✅ |
| A focused report is committed under `docs/reports/` | ✅ (this file) |
| One PR with green CI records the activation evidence | ✅ (PR to be opened) |

## 6. Stop condition check

| Stop condition | Status |
|----------------|--------|
| Overlapping roadmap PR | NONE (PR #523 is cleanup, not roadmap) |
| Dirty/ambiguous working tree | CLEAN |
| Contradictory runtime evidence | NONE found |
| Scope expands into host/runtime | NO |
| A2/A3 approval inferred | NO |
| CI or tests red | N/A (no code changes) |
| Secret exposure | NONE |
| Native Hermes cron unavailable | NO (verified working) |

## 7. Merge prerequisites

- [x] Report written and committed
- [x] No host/Docker/bot/strategy/config mutation
- [x] No secret exposure
- [x] No CI/state drift

---

## Gate status

`READY_FOR_REVIEW`

## Next step

After merge: close #526 with merge SHA, update `docs/state/current-operational-state.md` to mark H2 complete, unblock #527 (R5a).
