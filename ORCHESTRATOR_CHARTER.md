# ORCHESTRATOR_CHARTER.md

## Mission

This charter defines the binding rules for the autonomous trading orchestration system based on ai-hedge-fund-crypto as signal layer and Hermes as the meta-orchestrator.

## Role Split

### ai-hedge-fund-crypto — Signal Layer
- Signal generation via TA ensemble + LLM portfolio decisions
- Exchange: Bitget Futures OHLCV
- Model: DeepSeek V4 Pro
- Advisory output only (no order placement)

### Hermes — Meta-Orchestrator
- Profile isolation (`orchestrator` profile)
- Tool execution and automation
- System audits and repairs
- Documentation and escalation
- Human interface via Telegram/Gateway

### Freqtrade — Execution Fleet
- Dry-run trade execution
- Strategy-based entry/exit
- Signal as conservative filter
- No signal-forced trades
- Fail-open on stale/missing signals

## Hermes Profile Isolation

| Profile      | Purpose                                      | Status   |
| ------------ | -------------------------------------------- | -------- |
| `default`    | General-purpose Hermes operations            | active   |
| `mira`       | Mira content pipeline                        | stopped  |
| `trading`    | Future domain/worker profile for trading ops | stopped  |
| `orchestrator` | Meta-control profile for trading orchestration | **NEW**  |

The `orchestrator` profile:
- Cloned config, .env, SOUL.md from `default` (not `--clone-all`)
- Has isolated memory, sessions, cronjobs
- Working directory set to `/home/hermes/projects/trading`
- SOUL at `~/.hermes/profiles/orchestrator/SOUL.md`

## Existing Profile Roles

- **default**: remains unchanged, general-purpose operations
- **trading**: documented as future domain/worker profile, not meta-controller
- **orchestrator**: meta-control profile for trading orchestration

## Dry-Run Only Policy

**Mandatory:**
- All Freqtrade bots must remain `dry_run: true`
- No exchange credentials may be added
- No real orders may be placed
- No leverage/position sizing automation
- No live trading without separate explicit approval

**Validation:**
- `dry_run` must be verified via container config inspection
- Exchange keys must be absent or empty strings
- API server credentials may exist for internal control but must be redacted in reports

## Forbidden Actions

Without separate explicit approval:
- Setting `dry_run: false`
- Adding exchange API keys or secrets
- Placing real orders
- Changing Freqtrade configs
- Changing Freqtrade strategy logic
- Restarting or recreating containers
- Migrating or deleting cronjobs
- Enabling live trading
- Changing signal thresholds or RiskGuard policies
- Modifying Pair allowlists

## Human Approval Requirements

Approval required for:
- Live trading enablement
- Credential changes
- Config modifications
- Strategy logic changes
- Container restarts/recreation
- Cronjob migration/deletion
- Signal threshold changes
- RiskGuard policy changes
- Destructive filesystem operations
- Deletion of historical data

## State Machine

### Global System State

```
INIT → PREFLIGHT → DATA_READY → SIGNAL_READY → RISK_FILTERED → SHADOW_LOGGED → FLEET_SYNCED → MONITORING
```

### Error States

- `DATA_STALE` — Signal output older than max_age
- `SIGNAL_INVALID` — schema validation failed
- `RISK_BLOCKED` — RiskGuard verdict is BLOCK_ENTRY
- `FLEET_UNHEALTHY` — bot API unreachable or state != RUNNING
- `CRON_DRIFT` — cronjob output stale or missing
- `TELEMETRY_STALE` — heartbeat or snapshot older than threshold
- `HUMAN_ESCALATION_REQUIRED` — live-money risk detected

### Per-Pair State (Signal Layer)

```
NO_DATA → DATA_OK → BASELINE_SIGNAL → LLM_SIGNAL → RECONCILED → ACCEPTED / WATCH_ONLY / BLOCKED → SHADOW_RECORDED
```

### Per-Bot State (Freqtrade)

```
UNKNOWN → CONTAINER_RUNNING → API_PONG → STATE_RUNNING → STRATEGY_ACTIVE → SIGNAL_STATE_VISIBLE → DRY_RUN_SAFE
```

## Gate System

### Gate 0 — Reality Lock
- Verify Hermes version, profiles, cronjobs
- Verify Docker containers running
- Verify filesystem paths exist
- Output: `reality-lock-YYYY-MM-DD.md`

### Gate 1 — Dry-Run Safety
- All bots `dry_run: true`
- No exchange credentials present
- REST API credentials redacted in reports
- Output: `fleet-dry-run-safety-audit-YYYY-MM-DD.md`

### Gate 2 — Signal Validity
- `hermes_signal.json` exists
- JSON schema valid
- `generated_at` not stale (max 45 minutes)
- All expected pairs present
- Actions in allowed set
- Confidence in valid range
- Pair mapping complete

### Gate 3 — RiskGuard
- BUY/SELL only with sufficient quality
- HOLD/WATCH/TREND_HOLD = watch-only
- `weak` signal quality = watch-only
- Baseline/LLM disagreement = downgrade
- Unknown pair/action = block

### Gate 4 — Shadow Evidence
- JSONL append successful
- Daily log written
- Summary report written
- Counts match input

### Gate 5 — Freqtrade Sync
- Bridge writes per-bot state files
- State files readable by containers
- Helper module importable
- Stale signal triggers fallback
- Fresh signal gates direction only

### Gate 6 — Performance Gate (Future)
- Backtest v1.1 with fees/slippage
- Pair-scoped non-overlap
- 4h/12h/24h horizons tested
- Baseline comparisons passed
- Minimum 50 non-overlapping signals
- Net 24h edge > baseline + 0.25pp

## RiskGuard Policy

**Verdicts:**
- `ACCEPTED` — signal passes all gates, may be used as filter
- `WATCH_ONLY` — informational only, no entry allowed
- `BLOCK_ENTRY` — signal blocked, fallback to normal strategy

**Rules:**
- Entry candidates: `BUY`, `SELL` only
- Informational actions: `TREND_HOLD`, `WATCH`, `HOLD` → never entry
- Horizon: 24h advisory only (until separately validated)
- Pair allowlist must match backtested universe
- `signal_quality == weak` → `WATCH_ONLY`
- Unknown pair/action/quality → `BLOCK_ENTRY`
- Non-numeric confidence → `BLOCK_ENTRY`
- Baseline/LLM disagreement → downgrade to `WATCH` or `BLOCK`

## Shadow Logging Policy

**Requirements:**
- Append-only JSONL
- One record per signal cycle
- Daily aggregation files
- Summary report per cycle
- No Freqtrade API calls
- No trade execution
- No side effects

**Record Fields:**
- `timestamp`
- `signals_file`
- `risk_file`
- `signals_read`
- `accepted_count`
- `blocked_count`
- `watch_only_count`
- `accepted_signals`
- `blocked_signals`
- `watch_only_pairs`
- `mode`
- `notes`

## Freqtrade Bridge Policy

**Current State:**
- Bridge reads `hermes_signal.json`
- Writes per-bot signal state files
- Shared helper in `/freqtrade/shared/` used by strategies
- Fail-open: stale/missing signal → normal strategy logic
- Fresh signal gates entry direction only, does not force trades

**Future State:**
- Bridge will read risk-filtered signal as primary source
- Raw signal becomes fallback only
- Risk verdict included in state file
- Age, generated_at, reason fields added

## Cron Isolation and Future Migration Plan

**Current State:**
- 4 cronjobs exist in `default` profile:
  - `freqtrade-daily-data-regime-report` (daily 7:00 UTC)
  - `freqtrade-4h-fleet-trade-snapshot` (every 240m)
  - `strategy_heartbeat_intelligence` (every 120m)
  - `ai-hedge-fund-signal-cycle` (every 240m)

**This Phase:**
- Cronjobs inventoried only
- No migration
- No pausing
- No deletion
- No recreation

**Future Migration Plan:**
1. Pause old default-profile job
2. Recreate equivalent job under `orchestrator` profile
3. Run orchestrator job once manually
4. Compare outputs
5. Retire old default-profile job only after approval

**Documentation:**
- `orchestrator-cron-inventory-and-migration-plan-YYYY-MM-DD.md`

## Monitoring Colors

### GREEN
- Signal output fresh
- RiskGuard valid
- ShadowLogger writing
- Bridge writing state
- All Freqtrade APIs pong
- All bots dry-run verified
- No config drift
- No stale telemetry

### YELLOW
- Signal stale but Freqtrade running normally
- RiskGuard accepted_count = 0 (explainable)
- ShadowLogger running with few data points
- One bot has no trades (strategy plausibly quiet)

### ORANGE
- Signal cycle running but output stale
- Bridge writing stale state
- One bot API unreachable but container running
- Strategy mismatch between CLI and config
- Signal schema changed

### RED
- `dry_run: false` detected
- Exchange keys present
- Bot not running
- Container restart loop
- Corrupt JSON
- RiskGuard blocks due to schema invalid
- ShadowLogger not writing
- Cron forwards old reports
- Live-money risk detected

## Human Escalation Matrix

**Immediate Escalation Required:**
- Live-money risk
- Credentials discovered
- `dry_run: false`
- Freqtrade config must change
- Strategy logic must change
- Signal thresholds must change
- Signal and baseline disagree strongly over multiple runs
- Backtest shows FAIL
- Container must be destructively recreated
- Old data must be deleted

**No Escalation Needed:**
- Read-only audits
- Report generation
- JSON validation
- Shadow logging
- Stale classification
- Skill documentation
- Suggestions
- Dry-run healthchecks

## Definition of Done

The orchestrator is considered complete when:

1. ✅ Signal canonical path is unambiguous
2. ✅ Signal cycle runs stably
3. ✅ RiskGuard validates every signal file
4. ✅ ShadowLogger appends every run auditably
5. ✅ Bridge uses max-age and fallback correctly
6. ✅ All three Freqtrade bots API-pong
7. ✅ All bots dry-run verified
8. ✅ Daily report generates automatically
9. ✅ Stale telemetry never reported as GREEN
10. ✅ Every change is auditable
11. ✅ No live execution exists
12. ✅ Runbook + Charter exist

## Version

- Charter Version: 1.0
- Created: 2026-05-07
- Profile: orchestrator
- Project: /home/hermes/projects/trading
