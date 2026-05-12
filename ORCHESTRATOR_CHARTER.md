# ORCHESTRATOR_CHARTER.md — Binding Orchestration Rules

## Mission

This charter defines the binding rules for the autonomous trading orchestration system.
ai-hedge-fund-crypto is the signal layer, Hermes the meta-orchestrator, Freqtrade the dry-run fleet.
The system operates under a strict dry-run-only policy until explicitly cleared for live trading.

**Version:** 2.0
**Updated:** 2026-05-12
**Profile:** orchestrator
**Project:** /home/hermes/projects/trading
**Repo:** github.com/GoLukeEnviro/trading-hub (private)

---

## Role Split

### ai-hedge-fund-crypto — Signal Layer
- Signal generation via TA ensemble + LLM portfolio decisions
- Exchange: Bitget Futures OHLCV
- Model: DeepSeek V4 Pro (Ollama cloud endpoint)
- Advisory output only — no order placement
- Container: `ai-hedge-fund-crypto` (port 8410, healthy)
- Output: `ai-hedge-fund-crypto/output/hermes_signal.json`

### Hermes — Meta-Orchestrator
- Profile isolation (`orchestrator` profile)
- Tool execution and automation
- System audits, repairs, documentation
- Human interface via Telegram/Gateway
- Git housekeeping for trading-hub repo
- Subagent delegation for research/dev/review

### Freqtrade — Execution Fleet
- Dry-run trade execution (6 bots, all bitget futures)
- Strategy-based entry/exit
- Signal as conservative filter
- No signal-forced trades
- Fail-open on stale/missing signals
- Fleet compose: `freqtrade/docker-compose.fleet.yml`

### FreqForge Shadow Evaluator — Passive Observer
- Observes dry-run activity, evaluates decisions
- Does NOT execute, modify, or override trades
- Append-only JSONL evidence trail
- Components: `tools/freqforge/`

### Honcho — Persistent Memory
- Session-scoped write frequency
- Deriver MQG v2.0.0
- Hourly watchdog cron

---

## Hermes Profile Isolation

| Profile | Purpose | Status |
|---------|---------|--------|
| `default` | General-purpose Hermes operations | active |
| `mira` | Mira content pipeline | stopped |
| `trading` | Future domain/worker profile | stopped |
| `orchestrator` | Meta-control profile for trading orchestration | **ACTIVE** |

The `orchestrator` profile:
- Isolated memory, sessions, cronjobs
- Working directory: `/home/hermes/projects/trading`
- SOUL: `~/.hermes/profiles/orchestrator/SOUL.md`

---

## Dry-Run Only Policy

**Mandatory:**
- All Freqtrade bots must remain `dry_run: true`
- No exchange credentials may be added
- No real orders may be placed
- No leverage/position sizing automation
- No live trading without separate explicit approval per the FreqForge deployment rule: **backtest → paper 48h → live**

**Validation:**
- `dry_run` verified via container config inspection
- Exchange keys must be absent or empty strings
- API server credentials may exist for internal control but must be redacted in reports and never committed to git

---

## Trading Hard Limits

Per user mandate (non-negotiable):
1. **Confidence threshold >= 0.60** — no trade under 60% confidence
2. **Minimum 60 paper trades** before strategy path is unlocked (FreqForge Risk-Manager lock)

---

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
- Modifying pair allowlists
- Deleting historical data

---

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

---

## State Machine

### Global System State

```
INIT → PREFLIGHT → DATA_READY → SIGNAL_READY → RISK_FILTERED → SHADOW_LOGGED → FLEET_SYNCED → MONITORING
```

### Error States

- `DATA_STALE` — Signal output older than max_age (45 min)
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

---

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
- Confidence in valid range [0.60, 1.0]
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
- Bridge writes per-bot signal state files
- State files readable by containers
- Helper module importable
- Stale signal triggers fallback
- Fresh signal gates direction only, does not force trades

### Gate 6 — Performance Gate
- Backtest with fees/slippage
- Pair-scoped non-overlap
- 4h/12h/24h horizons tested
- Minimum 60 non-overlapping trades (hard limit)
- Net edge > baseline + threshold
- Walk-forward validation passed

---

## Monitoring Colors

### GREEN
- Signal output fresh (< 45 min)
- RiskGuard valid
- ShadowLogger writing
- Bridge writing state
- All Freqtrade APIs pong
- All bots dry-run verified
- No config drift

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
- Live-money risk detected

---

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
- Git commits (non-destructive, no secrets)

---

## Definition of Done

The orchestrator system is considered operationally complete when:

1. Signal canonical path is unambiguous
2. Signal cycle runs stably (ai-hedge-fund-crypto healthy)
3. RiskGuard validates every signal file
4. ShadowLogger appends every run auditably
5. Bridge uses max-age and fallback correctly
6. All Freqtrade bots API-pong
7. All bots dry-run verified
8. Daily report generates automatically
9. Stale telemetry never reported as GREEN
10. Every change is auditable via git
11. No live execution exists
12. Runbook + Charter exist and are current

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2026-05-12 | Full rewrite: reflect current fleet (6 bots), ai-hedge-fund-crypto as signal layer, PrimoAgent decommissioned, git repo established, hard limits added, FOMO Phase 3 documented |
| 1.0 | 2026-05-07 | Initial charter |
