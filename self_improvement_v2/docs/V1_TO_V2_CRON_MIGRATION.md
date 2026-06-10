# v1 → v2 Cron Migration Map

> **Status:** Planning document — NO implementation in this phase.
> All proposed v2 equivalents are DISABLED by default.

## 1. Background

> **2026-06-10 Update:** Generic aliases `bot_a`–`bot_d` were replaced
> with real bot names from [bot-registry.md](../docs/registry/bot-registry.md).
> See `cron_defs/jobs.yaml` for the current configuration.

The original SI v1 system had 16 cron jobs that were **paused**.
Each job corresponded to one of 4 generic bot aliases (Bot A–D) × 4 phases.

## 2. Current v2 Cron Jobs

The current `cron_defs/jobs.yaml` defines 4 real bots with 4 schedules each:

| Bot ID | Bot Name | Container | Strategy |
|--------|----------|-----------|----------|
| `freqforge` | FreqForge | `trading-freqtrade-freqforge-1` | `FreqForge_Override` |
| `freqforge_canary` | FreqForge Canary | `trading-freqtrade-freqforge-canary-1` | `FreqForge_Override` |
| `regime_hybrid` | Regime Hybrid | `trading-freqtrade-regime-hybrid-1` | `RegimeSwitchingHybrid_v7_v04_Integration` |
| `rebel` | Rebel | `trading-freqai-rebel-1` | `RebelLiquidation` |

Each bot has 4 schedules:

| Phase | Schedule |
|-------|----------|
| analyze | `*/30 * * * *` |
| backtest | `0 */6 * * *` |
| daily_report | `0 8 * * *` |
| walkforward | `0 2 * * 0` |

## 3. v1 → v2 Migration (Historical)

The original v1 mapping used generic aliases. These are now replaced:

| v1 Alias | Real Bot |
|----------|----------|
| `bot_a` | `freqforge` |
| `bot_b` | `freqforge_canary` |
| `bot_c` | `regime_hybrid` |
| `bot_d` | `rebel` |

All jobs in `cron_defs/jobs.yaml` are defined with `enabled_default: false`,
`dry_run_only: true`, and `no_agent: false` per SI v2 safety rules.

**Note:** The `*/30 * * * *` schedule (every 30 minutes) passes the
`schedule_must_not_be_too_frequent` validator because 30 > 4.

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