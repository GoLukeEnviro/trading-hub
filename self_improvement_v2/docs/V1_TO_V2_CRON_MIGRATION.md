# v1 → v2 Cron Migration Map

> **Status:** Planning document — NO implementation in this phase.
> All proposed v2 equivalents are DISABLED by default.

## 1. Background

The current SI v1 system has 16 cron jobs that are currently **paused**.
Each job corresponds to one of 4 bots (Bot A–D) × 4 phases (analyze,
backtest, daily report, walkforward).

## 2. Existing v1 Cron Jobs (Paused)

| # | Bot | Phase | Schedule | Status |
|---|-----|-------|----------|--------|
| 1 | bot_a | analyze | `*/15 * * * *` | Paused |
| 2 | bot_a | backtest | `0 */6 * * *` | Paused |
| 3 | bot_a | daily_report | `0 8 * * *` | Paused |
| 4 | bot_a | walkforward | `0 2 * * 0` | Paused |
| 5 | bot_b | analyze | `*/15 * * * *` | Paused |
| 6 | bot_b | backtest | `0 */6 * * *` | Paused |
| 7 | bot_b | daily_report | `0 8 * * *` | Paused |
| 8 | bot_b | walkforward | `0 2 * * 0` | Paused |
| 9 | bot_c | analyze | `*/15 * * * *` | Paused |
| 10 | bot_c | backtest | `0 */6 * * *` | Paused |
| 11 | bot_c | daily_report | `0 8 * * *` | Paused |
| 12 | bot_c | walkforward | `0 2 * * 0` | Paused |
| 13 | bot_d | analyze | `*/15 * * * *` | Paused |
| 14 | bot_d | backtest | `0 */6 * * *` | Paused |
| 15 | bot_d | daily_report | `0 8 * * *` | Paused |
| 16 | bot_d | walkforward | `0 2 * * 0` | Paused |

## 3. Proposed v2 Equivalents

Each v1 job maps to a v2 `CronJobDef` with `enabled_default: false`,
`dry_run_only: true`, and `no_agent: false`.

| v1 Job | v2 `job_id` | v2 Schedule | Command | Enabled? |
|--------|------------|-------------|---------|----------|
| bot_a/analyze | `bot_a_analyze` | `*/15 * * * *` | `si_v2_analyze` | No ❌ |
| bot_a/backtest | `bot_a_backtest` | `0 */6 * * *` | `si_v2_backtest` | No ❌ |
| bot_a/daily_report | `bot_a_daily_report` | `0 8 * * *` | `si_v2_daily_report` | No ❌ |
| bot_a/walkforward | `bot_a_walkforward` | `0 2 * * 0` | `si_v2_walkforward` | No ❌ |
| bot_b/analyze | `bot_b_analyze` | `*/15 * * * *` | `si_v2_analyze` | No ❌ |
| bot_b/backtest | `bot_b_backtest` | `0 */6 * * *` | `si_v2_backtest` | No ❌ |
| bot_b/daily_report | `bot_b_daily_report` | `0 8 * * *` | `si_v2_daily_report` | No ❌ |
| bot_b/walkforward | `bot_b_walkforward` | `0 2 * * 0` | `si_v2_walkforward` | No ❌ |
| bot_c/analyze | `bot_c_analyze` | `*/15 * * * *` | `si_v2_analyze` | No ❌ |
| bot_c/backtest | `bot_c_backtest` | `0 */6 * * *` | `si_v2_backtest` | No ❌ |
| bot_c/daily_report | `bot_c_daily_report` | `0 8 * * *` | `si_v2_daily_report` | No ❌ |
| bot_c/walkforward | `bot_c_walkforward` | `0 2 * * 0` | `si_v2_walkforward` | No ❌ |
| bot_d/analyze | `bot_d_analyze` | `*/15 * * * *` | `si_v2_analyze` | No ❌ |
| bot_d/backtest | `bot_d_backtest` | `0 */6 * * *` | `si_v2_backtest` | No ❌ |
| bot_d/daily_report | `bot_d_daily_report` | `0 8 * * *` | `si_v2_daily_report` | No ❌ |
| bot_d/walkforward | `bot_d_walkforward` | `0 2 * * 0` | `si_v2_walkforward` | No ❌ |

**Note:** The `*/15 * * * *` schedule (every 15 minutes) passes the
`schedule_must_not_be_too_frequent` validator because 15 > 4.

## 4. Activation Ceremony (Future Phase)

Activation of any cron job will follow a **multi-step ceremony** that is
NOT implemented in this phase:

1. **Dry-run validation:** Run `cron_planner validate` on the jobs.yaml
2. **Plan review:** Run `cron_planner render-plan` and inspect the output
3. **Diff review:** Run `cron_planner diff-readonly` to preview changes
4. **Approval gate:** A human must approve each job activation through
   the existing SI v2 approval system
5. **Staged rollout:** Jobs are activated one phase/bot at a time,
   starting with analyze (read-only) → backtest (compute-only) →
   daily_report → walkforward
6. **Monitoring:** Each activated job is wrapped with ShadowLogger audit
   for the first 7 days

> **No cron job will be activated in Phases H or earlier.** Activation
> requires a dedicated Phase I or later with explicit human sign-off.