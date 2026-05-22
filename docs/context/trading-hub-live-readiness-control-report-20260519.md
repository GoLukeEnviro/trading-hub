# Trading Hub — Live-Readiness Control Report

**Date:** 2026-05-19 20:10 UTC
**Author:** Hermes Orchestrator (read-only audit)
**Classification:** Consolidation & Live-Readiness Assessment
**Mode:** dry_run=true enforced, no destructive writes

---

## 1. Executive Verdict

**LIVE-READY: NO**

The Trading Hub has achieved significant architectural hardening, but a **recurring cron-stuck bug** has rendered 7 of 10 automation jobs non-functional. The signal pipeline is stale (339+ minutes), and 3 critical scripts are missing from the profile scripts directory. The fleet itself is healthy (5/5 bots reachable, all dry_run=true, portfolio +$26.69), but the automation layer is effectively dead until the cron scheduler is repaired.

**Main Blocker:** Hermes cron-stuck bug — `next_run_at` is `null` for 7/10 jobs, and 3 referenced scripts don't exist in the profile scripts directory.

**Next Best Action:** Delete and recreate all stuck cron jobs, copy 3 missing scripts to `/opt/data/profiles/orchestrator/scripts/`, and manually trigger signal-heartbeat to restore pipeline freshness.

---

## 2. Current Architecture

### 2.1 Container Fleet

| Container | Image | Uptime | Port | Mode |
|-----------|-------|--------|------|------|
| freqtrade-freqforge | freqtradeorg/freqtrade:stable | 6h | 8086 | futures |
| freqtrade-regime-hybrid | freqtradeorg/freqtrade:stable | 6h | 8085 | futures |
| freqtrade-momentum | freqtrade-momentum-custom:running | 6h | 8084 | futures |
| freqtrade-freqforge-canary | freqtradeorg/freqtrade:stable | 6h | 8081 | spot |
| freqai-rebel | freqtradeorg/freqtrade:2026.3_freqai | 6h | 8087 | futures |
| freqtrade-webserver | freqtradeorg/freqtrade:stable | 24h | — | UI only |
| ai-hedge-fund-crypto | (custom) | 24h | 8410 | signal |

### 2.2 Signal Pipeline

```
ai-hedge-fund-crypto (HTTP /trigger)
  → hermes_signal.json (canonical signal)
  → trading_pipeline.py (bridge + RiskGuard)
    → RG-1: stale check (MAX_AGE=25min)
    → RG-2: confidence gate (>= 0.65)
    → RG-3: bias validation
    → RG-4: max concurrent cap (5)
  → primo_signal_state.json (per-bot gate file)
  → shadow_decisions.jsonl (audit trail)
  → Bot strategies read gate file, apply own TA
```

### 2.3 Safety Architecture

- **Signal = GATE, not EXECUTION**: Even ACCEPTED signals require bot's own TA to trigger entry
- **Stale blocking**: Signals older than 25 minutes → `PIPELINE_BLOCKED` → empty state written
- **Confidence gate**: Below 0.65 → `WATCH_ONLY` + `REJECTED` in shadow log
- **Shadow evaluator**: Passive observer, 131 events logged, produces `uncertain` verdicts
- **RiskGuard**: Embedded in `trading_pipeline.py`, not a separate service (spec-only in AGENTS.md)

---

## 3. Automation State

### 3.1 Cron Jobs

| Job | Schedule | Last Status | Next Run | Verdict |
|-----|----------|-------------|----------|---------|
| Fleet Report (alle 4h) | every 240m | ok | 2026-05-19T14:38 | STALE NEXT (past) |
| signal-heartbeat | */20 * * * * | **None** | **None** | STUCK |
| trading-pipeline | */10 * * * * | **None** | **None** | STUCK |
| drawdown-guard | */30 * * * * | **None** | **None** | STUCK |
| container-watchdog | */5 * * * * | **None** | **None** | STUCK |
| mcp-watchdog | */5 * * * * | **None** | **None** | STUCK |
| daily-backup | 0 2 * * * | **None** | **None** | STUCK |
| portfolio-rebalancer | 0 6 * * 1 | **None** | **None** | STUCK |
| cron-guardian | 0 */6 * * * | **None** | 2026-05-19T18:00 | STUCK (past) |
| smart-heartbeat | */10 * * * * | **None** | 2026-05-19T14:40 | STUCK (past) |

**Result: 9/10 jobs are stuck or never ran. Only Fleet Report has last_status=ok.**

### 3.2 Script Availability

| Script | Profile Dir | Project Dir | Status |
|--------|-------------|-------------|--------|
| ai_hedge_signal_heartbeat.sh | EXISTS | EXISTS | OK |
| trading_pipeline.py | EXISTS | EXISTS | OK |
| drawdown_guard.py | EXISTS | EXISTS | OK |
| container_watchdog.sh | **MISSING** | EXISTS | WILL FAIL |
| mcp_watchdog.sh | **MISSING** | EXISTS | WILL FAIL |
| backup_rotation.py | **MISSING** | EXISTS | WILL FAIL |
| portfolio_rebalancer.py | EXISTS | EXISTS | OK |
| restore_cron_jobs.sh | EXISTS | EXISTS | OK |
| smart_heartbeat.py | EXISTS | EXISTS | OK |

### 3.3 Backup Consistency

- `cron_jobs_backup.json`: 10 jobs — matches active jobs.json count (10/10)
- `restore_cron_jobs.sh`: EXISTS
- **Mismatch: FALSE** (counts match, but backup reflects the same stuck state)

---

## 4. Signal Safety State

### 4.1 Signal Freshness

| File | Age | Stale? | Content |
|------|-----|--------|---------|
| hermes_signal.json | **339 min** (5.6h) | YES | BTC/ETH/SOL short, conf=0.9 |
| primo_signal_state.json | **339 min** | YES | 3 pairs ACCEPTED, short bias |

**The signal has been stale since ~14:30 UTC.** The signal-heartbeat cron job is stuck and has not triggered a new analysis cycle in 6+ hours.

### 4.2 Stale Blocking Verification

- `MAX_AGE_MINUTES = 25.0` hardcoded in `trading_pipeline.py`
- Pipeline logs show `PIPELINE_BLOCKED` events with `stale_57min` reason (logged at 14:28 UTC)
- **Mechanism is correct but cannot execute** because the pipeline cron job itself is stuck

### 4.3 Confidence Gate Verification

- `CONFIDENCE_THRESHOLD = 0.65` hardcoded
- Below 0.65 → `WATCH_ONLY` verdict, `allow_long_bias=False`, `allow_short_bias=False`
- Pipeline logs show test cycle at 14:28: 3 pairs with conf < 0.65 → `rejected: 3`
- **Mechanism is correct and functional when pipeline runs**

### 4.4 Last Known Good Signal

- Timestamp: 2026-05-19T14:30:19 UTC
- BTC/USDT:USDT: confidence=0.9, action=short, verdict=ACCEPTED
- ETH/USDT:USDT: confidence=0.9, action=short, verdict=ACCEPTED
- SOL/USDT:USDT: confidence=0.9, action=short, verdict=ACCEPTED

---

## 5. Bot Performance Snapshot

| Bot | Strategy | Trades | Win Rate | PnL (USDT) | Open | Last Closed |
|-----|----------|--------|----------|-------------|------|-------------|
| FreqForge | FreqForge_Override | 33 | **90.9%** | **+$2.34** | 0 | BTC 14:47 UTC |
| Canary | SimpleRSIOnly_v1 | 18 | **94.4%** | **+$2.67** | 3 (shorts) | SOL 14:20 UTC |
| Regime-Hybrid | RegimeSwitchingHybrid_v7 | 40 | 77.5% | -$7.06 | 0 | ARB May 18 |
| Momentum | MomentumBG15_v1 | 16 | 43.8% | **-$17.42** | 0 | APT 06:37 UTC |
| FreqAI-Rebel | RebelLiquidation | 30 | 30.0% | -$1.41 | 0 | ETH 20:00 UTC |

### 5.1 Portfolio Summary

- **Total portfolio value**: $4,476.69 (start: $4,450.00)
- **Total PnL**: +$26.69 (+0.60%)
- **Open risk**: ~$137 (Canary: 3 short positions totaling ~$137 stake)
- **Active drawdown**: 0.0%

### 5.2 Per-Bot Notes

- **FreqForge**: Healthy. 33 trades, 90.9% WR, positive PnL. Recently redeployed (May 18), running well.
- **Canary**: TOP PERFORMER. 94.4% WR, 3 active short positions (BTC/ETH/ATOM via `signal_override_short`).
- **Regime-Hybrid**: Known loss asymmetry (1:6.3 ratio). 77.5% WR negated by outsized losses. Needs exit strategy review.
- **Momentum**: WORST PERFORMER. -$17.42 with 43.8% WR. Entries re-activated (max_open_trades=5) but generating losing trades.
- **FreqAI-Rebel**: 30 trades since DI_threshold/label patch (t0005). 30% WR is low but model is healthy (diverse predictions, real logloss 0.67-0.83). Early in calibration curve.

---

## 6. Risk Controls

### 6.1 Drawdown Guard

- **Script**: `drawdown_guard.py` — ran successfully in read-only mode
- **Portfolio state**: $4,476.69 / $4,450.00 start, DD: 0.0%, action: OK
- **All 5 bots reachable**: confirmed
- **Alert**: Signal stale detected (340min > 60min threshold) — alert queued but Telegram send failed (HTTP 401 Unauthorized)
- **State file**: Written to `orchestrator/state/drawdown_state.json`

### 6.2 Dry Run Verification

| Bot | Config File | dry_run |
|-----|-------------|---------|
| FreqForge | freqforge/config/config_freqforge_dryrun.json | **true** |
| Canary | freqforge-canary/config/config_canary_dryrun.json | **true** |
| Regime-Hybrid | bots/regime-hybrid/config/config_regime_hybrid_dryrun.json | **true** |
| Momentum | bots/momentum/config/config.json | **true** |
| FreqAI-Rebel | bots/freqai-rebel/user_data/config.json | true (from show-config) |

**Result: All bots confirmed dry_run=true. No live trading enabled.**

### 6.3 MCP Paper Trading

- **Portfolio**: $9,921.92 balance, 3 open short positions (BTC, ETH, SOL from May 17)
- **Position margin**: ~$1,878 total across 3 positions
- **ccxt availability**: NOT INSTALLED in Hermes environment
- **MCP server**: Runs as stdio subprocess from config.yaml — health requires Hermes reload if killed
- **Portfolio file**: `orchestrator/logs/mcp/bitget_mcp_portfolio.json` (schema v1.1, last modified May 17)

---

## 7. Shadow Evaluation

### 7.1 Shadow Decisions Log

- **var/freqforge/shadow_decisions.jsonl**: 131 entries (since May 12)
- **orchestrator/logs/shadow_decisions.jsonl**: 13 pipeline-level entries
- **Event types**: entry (E1 rule triggers), open_risk, exit_review
- **Decisions**: Predominantly `uncertain` — the shadow evaluator is conservative
- **Recent entries**: Canary open_risk evaluations for BTC/ETH shorts (conf=0.9, bearish bias) → `uncertain`
- **Format**: Well-structured JSONL with full audit trail (timestamp, event_id, bot, pair, signal data, decision, reason codes)

### 7.2 Pipeline Audit Trail

Pipeline logs show 3 types of events:
1. **pipeline_cycle**: Normal execution with RiskGuard verdicts (accepted/watch_only/rejected counts)
2. **PIPELINE_BLOCKED**: Stale signal detected, empty state written to all targets
3. **Test cycles**: Confidence gate testing (3 pairs below 0.65 → all rejected)

---

## 8. Remaining Live Blockers

### CRITICAL (blocks live-readiness)

| # | Blocker | Impact | Fix |
|---|---------|--------|-----|
| B1 | **Cron-stuck bug recurring** — 7/10 jobs have null next_run_at | Signal goes stale within 25 min, all automation dead | Delete + recreate all stuck jobs |
| B2 | **3 scripts missing from profile dir** (container_watchdog.sh, mcp_watchdog.sh, backup_rotation.py) | Jobs would fail even if scheduler un-stuck | `cp` from project dir to `/opt/data/profiles/orchestrator/scripts/` |
| B3 | **Signal 339 min stale** — heartbeat not running | Bots cannot receive fresh trading gates | Trigger heartbeat manually, fix cron |
| B4 | **Telegram alerting broken** (HTTP 401) | Drawdown guard alerts not delivered | Fix Telegram bot token in drawdown_guard.py config |

### HIGH (degrades system quality)

| # | Blocker | Impact | Fix |
|---|---------|--------|-----|
| B5 | **Momentum losing consistently** (-$17.42, 43.8% WR) | Drags portfolio down | Consider max_open_trades=0 halt |
| B6 | **Regime-Hybrid loss asymmetry** (1:6.3 win:loss ratio) | 77.5% WR negated by outsized losses | Exit strategy review |
| B7 | **ccxt not available in Hermes env** | MCP paper trading limited to subprocess calls | `pip install ccxt` in Hermes venv |

### MEDIUM (nice-to-have before live)

| # | Blocker | Impact | Fix |
|---|---------|--------|-----|
| B8 | **RiskGuard not a standalone service** (embedded in pipeline script) | Cannot be tested independently | Deploy as separate container |
| B9 | **ShadowLogger not deployed** (spec-only in AGENTS.md) | No independent audit layer | Implement append-only service |
| B10 | **FreqAI-Rebel 30% WR** | Model still calibrating | Monitor 2 more weeks |
| B11 | **MCP portfolio not updating** (last modified May 17) | Stale paper trading state | Investigate MCP server lifecycle |

---

## 9. Next 48h Stability Checklist

### Immediate (0-4h)

- [ ] **Fix cron-stuck bug**: Delete all 9 stuck jobs and recreate with fresh `next_run_at`
- [ ] **Copy missing scripts**: `container_watchdog.sh`, `mcp_watchdog.sh`, `backup_rotation.py` → profile scripts dir
- [ ] **Trigger signal-heartbeat manually**: Restore pipeline freshness
- [ ] **Verify pipeline runs**: Confirm `PIPELINE_BLOCKED` → `pipeline_cycle` with ACCEPTED pairs
- [ ] **Back up jobs.json** after fix

### Short-term (4-24h)

- [ ] **Fix Telegram alerting**: Update bot token in drawdown_guard.py configuration
- [ ] **Momentum halt decision**: Evaluate max_open_trades=0 with Luke
- [ ] **Verify cron-guardian fires**: Should detect and report any new stuck jobs at next 6h mark
- [ ] **Install ccxt**: `pip install ccxt` in Hermes venv for MCP paper trading
- [ ] **Check smart-heartbeat logs**: Verify it produces meaningful health data after restart

### Medium-term (24-48h)

- [ ] **Monitor Regime-Hybrid exits**: Track whether loss asymmetry improves
- [ ] **FreqAI-Rebel WR tracking**: If WR stays below 35% after 48h, consider further calibration
- [ ] **MCP portfolio freshness**: Ensure MCP server keeps portfolio file updated
- [ ] **Full backup rotation**: Verify daily-backup job fires at 02:00 UTC

---

## 10. Go/No-Go Criteria

### Live Trading Go/No-Go Matrix

| Criterion | Current Status | Required | Met? |
|-----------|---------------|----------|------|
| All bots dry_run | 5/5 true | 5/5 true | YES |
| Signal pipeline fresh | Stale 339min | <25 min | **NO** |
| Cron automation operational | 1/10 running | 10/10 running | **NO** |
| Drawdown guard functional | OK when run manually | Auto + alerts | **NO** |
| Portfolio positive PnL | +$26.69 (+0.6%) | Positive | YES |
| Confidence gate active | Code verified, tested | Working | YES |
| Stale blocking active | Code verified, tested | Working | YES |
| Telegram alerts working | HTTP 401 | OK | **NO** |
| RiskGuard independent | Embedded in script | Standalone | **NO** |
| ShadowLogger deployed | Spec only | Running | **NO** |
| 48h stable operation | Cron broken | No failures | **NO** |
| All scripts in profile dir | 6/9 present | 9/9 present | **NO** |
| MCP paper trading healthy | Stale since May 17 | Active | **NO** |
| Momentum performance | -$17.42 | Non-negative or halted | **NO** |
| FreqAI-Rebel calibrated | 30% WR | >50% WR | **NO** |

**Score: 4/15 criteria met. LIVE-READY: NO.**

---

## 11. Recommended Next Actions

### Priority 1 — Restore Automation (estimated 15 min)

1. Delete and recreate all 9 stuck cron jobs (signal-heartbeat, trading-pipeline, drawdown-guard, container-watchdog, mcp-watchdog, daily-backup, portfolio-rebalancer, cron-guardian, smart-heartbeat)
2. Copy missing scripts:
   ```bash
   cp /home/hermes/projects/trading/orchestrator/scripts/container_watchdog.sh /opt/data/profiles/orchestrator/scripts/
   cp /home/hermes/projects/trading/orchestrator/scripts/mcp_watchdog.sh /opt/data/profiles/orchestrator/scripts/
   cp /home/hermes/projects/trading/orchestrator/scripts/backup_rotation.py /opt/data/profiles/orchestrator/scripts/
   ```
3. Manually trigger signal heartbeat:
   ```bash
   bash /home/hermes/projects/trading/orchestrator/scripts/ai_hedge_signal_heartbeat.sh
   ```
4. Back up jobs.json after fix

### Priority 2 — Alerting & Safety (estimated 30 min)

5. Fix Telegram bot token for drawdown guard alerts
6. Decide on Momentum: halt (max_open_trades=0) or monitor
7. Install ccxt in Hermes venv for MCP paper trading

### Priority 3 — Validation (48h observation)

8. Monitor all cron jobs for 48h — confirm no re-sticking
9. Track FreqAI-Rebel WR trajectory
10. Review Regime-Hybrid exit strategy after 48h of data

---

## 12. Compact Status Table

| Component | Status | Evidence | Action Needed |
|-----------|--------|----------|---------------|
| Fleet containers (5/5) | OK | All UP 6h+, docker ps | None |
| dry_run enforcement | OK | All config files verified true | None |
| Signal pipeline | BROKEN | 339min stale, cron stuck | Recreate cron jobs |
| Cron automation (9/10) | STUCK | last_status=None, next_run=null | Delete + recreate |
| Missing scripts (3) | MISSING | Not in profile scripts dir | cp from project dir |
| Confidence gate | OK | 0.65 threshold, verified in code | None |
| Stale blocking | OK | MAX_AGE=25min, PIPELINE_BLOCKED logged | None |
| Drawdown guard | OK | 0% DD, all bots reachable, $4476.69 | Fix Telegram token |
| Shadow evaluator | OK | 131 events logged, append-only | None |
| MCP paper trading | DEGRADED | ccxt missing, portfolio stale since May 17 | Install ccxt |
| Telegram alerts | BROKEN | HTTP 401 Unauthorized | Fix bot token |
| Portfolio PnL | OK | +$26.69 (+0.6%) | None |
| Momentum bot | WARN | -$17.42, 43.8% WR | Consider halt |
| FreqAI-Rebel | CALIBRATING | 30% WR, 30 trades, healthy inference | Monitor |

---

**Live-ready: NO**
**Main blocker: Cron-stuck bug — 9/10 automation jobs non-functional, signal pipeline stale**
**Next best action: Delete + recreate all stuck cron jobs, copy 3 missing scripts, trigger heartbeat**
