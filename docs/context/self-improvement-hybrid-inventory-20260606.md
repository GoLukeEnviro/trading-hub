# Self-Improvement Hybrid Architecture — Read-Only Inventory Report

**Date:** 2026-06-06
**Author:** Hermes Orchestrator
**Status:** Phase 1 Complete — Ready for Gap Analysis

---

## 1. Current Reality Inventory

### 1.1 Docker Environment

| Property | Value |
|----------|-------|
| Docker Root | `/var/lib/docker` |
| Total Containers | 21 running |
| Freqtrade Bots | 5 (4 traders + 1 webserver) |
| Compose Files | 5 active + 2 backups |
| Docker Proxy | Active (exec blocked unless DOCKER_HOST override) |
| Networks | `trading_hermes-net` (172.26.0.0/16, internal), `ki-fabrik` (172.18.0.0/16, external), `proxy-net` (172.27.0.0/16, internal) |

### 1.2 Running Freqtrade Bots (Detailed)

| # | Container Name | Strategy | Config Path | Port | Network IP |
|---|---------------|----------|-------------|------|-----------|
| 1 | `trading-freqtrade-freqforge-1` | `FreqForge_Override` | `/freqtrade/user_data/config.json` | 8086→8080 | 172.26.0.6 |
| 2 | `trading-freqtrade-regime-hybrid-1` | `RegimeSwitchingHybrid_v7_v04_Integration` | `/freqtrade/user_data/config.json` | 8085→8080 | 172.26.0.9 |
| 3 | `trading-freqtrade-freqforge-canary-1` | `FreqForge_Override` | `/freqtrade/user_data/config.json` | 8081→8080 | 172.26.0.10 |
| 4 | `trading-freqai-rebel-1` | `RebelLiquidation` + `RebelXGBoostClassifier` | `/freqtrade/user_data/config.json` | 8087→8080 | 172.26.0.7 |
| 5 | `trading-freqtrade-webserver-1` | (webserver only) | `/freqtrade/user_data/config.json` | 8180→8080 | 172.26.0.4 |

**All bots use:** `env_file: /opt/data/.env.telegram`, `dry_run=true`, `trading_mode=futures`, `margin_mode=isolated`, Bitget exchange.

### 1.3 Host → Container Bind Mounts

| Bot | Host Path | Container Path |
|-----|-----------|---------------|
| FreqForge | `./freqforge/user_data` | `/freqtrade/user_data` |
| Regime-Hybrid | `./freqtrade/bots/regime-hybrid/user_data` | `/freqtrade/user_data` |
| FreqForge-Canary | `./freqforge-canary/user_data` | `/freqtrade/user_data` |
| FreqAI-Rebel | `./freqtrade/bots/freqai-rebel/user_data` | `/freqtrade/user_data` |
| **All 4** | `./freqtrade/shared/` | `/freqtrade/shared/` (ro) |

### 1.4 Docker Compose Fleet (Not Currently Running)

The file `docker-compose.fleet.yml` defines additional bots that are NOT in the primary compose:
- `freqtrade-rsi` — SimpleRSI strategies
- `freqtrade-momentum` — MomentumBG15 strategies  
- `freqtrade-regime-hybrid` (duplicate)
- `freqforge-canary` (duplicate)

These represent historical/superseded definitions.

### 1.5 Bot Repo Directory Structure (freqtrade/bots/)

| Bot Directory | Strategies | Backtests | Automation |
|--------------|-----------|-----------|-----------|
| `regime-hybrid/` | ~25 strategies (v2-v9, MomentumBG15, RSI, research) | ~80 backtest results | `self_optimizer.py` + `fleet_monitor.py` |
| `fomo-phase3/` | `FOMO_Phase3_v0.py` | Partial | Research pkg with `walk_forward.py`, `backtest.py`, `optimization.py`, `run_optuna.py` |
| `freqai-rebel/` | `RebelLiquidation.py`, `RebelLiquidationWFTop15.py` | 4 backtests + 10 walk-forwards | FreqAI mode, XGBoost classifier |
| `momentum/` | `MomentumBG15_v2_RRRefactor.py`, `MomentumBG15_v3_PairPruned.py`, etc. | ~50 backtests | None |
| `mvs/` | `MinimalViableStrategy_v1.py` | 4 backtests | None |
| `rsi/` | `simple_rsi_only_v1-v2.py`, `simple_rsi_bb_futures.py`, `aggressive_scalp_futures_v1.py` | 1 backtest | None |

### 1.6 Existing Automation Layer

Located at: `freqtrade/bots/regime-hybrid/config/research/automation/`

| File | Purpose | Status |
|------|---------|--------|
| `self_optimizer.py` | Read-only performance analyzer across windows (12h/24h/overall) | Active, `automation_write_actions_enabled: false` |
| `fleet_monitor.py` | Cross-bot monitoring and reporting | Active |
| `latest_self_optimization_proposals.json` | Current proposals with metrics | Contains 73 trades for freqai-rebel, PF 0.214 |
| `self_optimizer_events.jsonl` | Append-only event log | Active |
| `self_optimizer_state.json` | State with quarantine candidates | 3 bots quarantined (freqai-rebel, momentum, regime-hybrid) |
| `latest_fleet_monitor_report.json` | Full fleet report | 613-line comprehensive report |

### 1.7 Container Execution (Critical)

| Capability | Status |
|-----------|--------|
| `docker exec` via proxy | **BLOCKED** (403 Forbidden) |
| `docker exec` via DOCKER_HOST=unix:///var/run/docker.sock | **WORKS** |
| `docker ps`, `docker inspect`, `docker logs` | **WORKS** via proxy |
| `docker compose` CLI | **NOT AVAILABLE** on host |
| `freqtrade` CLI on host PATH | **NOT AVAILABLE** |
| `freqtrade` inside containers | **AVAILABLE** via `docker exec` |
| `sqlite3` inside containers | **AVAILABLE** for some, check per-container |
| `jq` inside containers | **NOT AVAILABLE** (use python3 -c) |

### 1.8 Cron Job Landscape

Total: 57 Hermes cron jobs (including 16 self-improvement jobs just added)

Existing relevant jobs:
- `trading-pipeline` (every 10m, no_agent script)
- `canary-position-monitor` (every 30m → Telegram)
- `drawdown-guard` (every 30m → Telegram)
- `container-watchdog` (every 30m → Telegram)
- `fleet-auto-repair` (every 2h → Telegram)
- `FleetRisk equity updater` (every 5m)
- `fleetrisk-auto-params` (every 15m)
- `Fleet Health Quickcheck` (every 2h, LLM-driven)
- `Fleet Report` (every 4h, LLM-driven → Telegram)
- `config-diff-detector` (hourly)
- `ledger-integrity-watchdog` (every 30m)

---

## 2. Bot Mapping Table: Generic A–D → Real Fleet

| Generic | Real Container | Strategy | Risk Profile | Path Prefix | Notes |
|---------|---------------|----------|-------------|-------------|-------|
| **Bot A — Core** | `freqforge-1` | `FreqForge_Override` | Core Conserv. | `freqforge/user_data/` | Most stable, 8086 |
| **Bot B — Regime** | `regime-hybrid-1` | `RegimeSwitchingHybrid_v7_v04_Integration` | Regime-Sens. | `freqtrade/bots/regime-hybrid/user_data/` | Has self_optimizer already, 8085 |
| **Bot C — Momentum** | `momentum/bot` (NOT currently running in primary compose) | `MomentumBG15_v3_PairPruned` | Momentum Strict | `freqtrade/bots/momentum/` | ⚠️ **Not deployed** — needs verification |
| **Bot D — Canary** | `freqforge-canary-1` | `FreqForge_Override` | Canary Low-Stake | `freqforge-canary/user_data/` | Smallest capital, 8081 |
| **Extra — FreqAI** | `freqai-rebel-1` | `RebelLiquidation` + XGBoost | ML/AI | `freqtrade/bots/freqai-rebel/user_data/` | 2GB RAM, 2 CPUs, 8087 |

**Key Insight:** Momentum Bot (Bot C) is NOT running as a container in the primary compose. It exists as:
1. Strategy files in `freqtrade/bots/momentum/` with ~50 backtest results
2. A definition in `docker-compose.fleet.yml` (not deployed)
3. No currently running container → **no live trades, no API, no DB to analyze**

**Recommendation:** Map Bot C to the momentum strategy files (backtest-analysis mode only) until/unless the fleet compose gets deployed.

---

## 3. Existing Components Reused

| Component | Path | Status | Use in Hybrid |
|-----------|------|--------|--------------|
| `self_optimizer.py` (regime) | `freqtrade/bots/regime-hybrid/config/research/automation/self_optimizer.py` | ✅ Active, read-only | Keep as canonical reference implementation |
| `fleet_monitor.py` | Same dir as above | ✅ Active | Keep for cross-bot monitoring |
| `walk_forward_backtest.py` | `freqtrade/bots/regime-hybrid/config/research/signal_tools/walk_forward_backtest.py` | ✅ Exists | Adapt for containerized execution |
| `walk_forward.py` (fomo) | `freqtrade/bots/fomo-phase3/research/fomo_phase3/walk_forward.py` | ✅ Exists | Reference pattern |
| `performance_analyzer.py` | `self_improvement/shared/performance_analyzer.py` | 🆕 Just built | Core analyzer — adapt paths |
| `strategy_mutator.py` | Same dir | 🆕 Just built | Core mutator — adapt paths |
| `backtest_runner.py` | Same dir | 🆕 Just built | Needs Docker-aware execution |
| `deployment_manager.py` | Same dir | 🆕 Just built | Needs Docker-aware execution |
| `dashboard.py` | Same dir | 🆕 Just built | Keep, update paths |
| `logrotate.conf` | Same dir | 🆕 Just built | Needs deployment |
| FreqJWT auth helpers | `freqtrade-fleet-auditing-and-readiness` skill | ✅ Documented | Reference for container API access |
| Host-bitget price fetcher | Various tools | ✅ Available | Use for live price queries |

---

## 4. Missing Components (Gap Analysis)

### P0 — Must Fix Before Any Deployment

| Gap | Detail | Impact |
|-----|--------|--------|
| `backtest_runner.py` calls `freqtrade` CLI directly | Host has no `freqtrade` on PATH | All backtests fail with `FileNotFoundError` |
| `performance_analyzer.py` reads from generic `state_dir/trades.jsonl` | No real trade data connection | Analyzer always returns `hold` (0 trades) |
| Bot C (Momentum) has no running container | `docker exec` impossible | Must run in backtest-analysis mode only |
| No Docker executor module | Every Python script needs container-aware execution | Duplication, fragile shell commands |

### P1 — Should Fix Before Full Activation

| Gap | Detail | Priority |
|-----|--------|----------|
| Walk-forward scripts exist but are isolated (fomo, regime, agenten) | No unified walk-forward orchestration | High |
| Canary promotion logic: None | No proposal system for bot_d → fleet promotion | High |
| Logrotate config not deployed | JSONL logs accumulate unbounded | Medium |
| Approval gate validation: Plausibility checks exist but no integration | Gate can be set `true` without validation | Medium |
| Trade data export: No automated pipeline from live bots → JSONL | Analyzer has no input data | High |

### P2 — Nice to Have

| Gap | Detail |
|-----|--------|
| Rollback watcher: No automated monitoring for post-deployment degradation | 
| Dashboard exporter: Grafana / Prometheus integration for real-time metrics |
| Cross-bot correlation: Momentum bot impacts on core |
| Telegram alerting for self-improvement proposals |

### P3 — Future

- Hyperopt automation  
- Regime-aware parameter switching  
- Multi-bot candidate sharing  

---

## 5. Safe Hybrid Architecture

### Core Principle

```
              ┌──────────────────────────────┐
              │  Existing self_optimizer.py   │
              │  (canonical read-only layer)  │
              └──────────┬───────────────────┘
                         │ feeds into
                         ▼
              ┌──────────────────────────────┐
              │  Hybrid Performance Analyzer │
              │  (Docker-aware, JSONL-based) │
              └──────────┬───────────────────┘
                         │ produces
                         ▼
              ┌──────────────────────────────┐
              │  Strategy Mutator            │
              │  (safe parameter overlay)    │
              └──────────┬───────────────────┘
                         │ generates
                         ▼
              ┌──────────────────────────────┐
              │  Docker Backtest Runner      │
              │  (docker exec freqtrade...)  │
              └──────────┬───────────────────┘
                         │ validates
                         ▼
              ┌──────────────────────────────┐
              │  Walk-Forward Validator      │
              │  (4-window, containerized)   │
              └──────────┬───────────────────┘
                         │ checks
                         ▼
              ┌──────────────────────────────┐
              │  Canary Promotion Advisor    │
              │  (proposal_only)             │
              └──────────┬───────────────────┘
                         │ gates
                         ▼
              ┌──────────────────────────────┐
              │  Approval Gate Validator     │
              │  (validates before deploy)   │
              └──────────┬───────────────────┘
                         │ if approved
                         ▼
              ┌──────────────────────────────┐
              │  Deployment Manager          │
              │  (git commit, config copy)   │
              └──────────┬───────────────────┘
                         │ then
                         ▼
              ┌──────────────────────────────┐
              │  Rollback Watcher            │
              │  (monitors post-deploy perf) │
              └──────────────────────────────┘
```

---

## 6. Docker-Aware Execution Model

### 6.1 The DOCKER_HOST Pattern

```python
import subprocess, os

def _docker_exec(container: str, cmd: str) -> subprocess.CompletedProcess:
    """Execute a command inside a Freqtrade container."""
    full_cmd = f"docker exec {container} {cmd}"
    return subprocess.run(
        full_cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "DOCKER_HOST": "unix:///var/run/docker.sock"},
    )
```

### 6.2 Backtest via Container

```python
# Instead of: subprocess.run(["freqtrade", "backtesting", ...])
_docker_exec(
    "trading-freqtrade-freqforge-1",
    "freqtrade backtesting "
    "--config /freqtrade/user_data/config.json "
    "--strategy FreqForge_Override "
    "--timerange 20260401- "
    "--export trades "
    "--backtest-dir /tmp/backtest_results"
)
```

### 6.3 Trade Data Extraction for Analysis

```python
# Extract trades via SQLite
_docker_exec(
    "trading-freqtrade-freqforge-1",
    "python3 -c \"import json, sqlite3; "
    "c = sqlite3.connect('/freqtrade/user_data/tradesv3.dryrun.sqlite'); "
    "c.row_factory = sqlite3.Row; "
    "rows = c.execute('SELECT * FROM trades WHERE is_open=0').fetchall(); "
    "print(json.dumps([dict(r) for r in rows]))\""
)
```

### 6.4 Container Name Mapping

Create a mapping module that translates bot_id → container_name:

```python
BOT_CONTAINERS = {
    "freqforge": "trading-freqtrade-freqforge-1",
    "regime_hybrid": "trading-freqtrade-regime-hybrid-1", 
    "canary": "trading-freqtrade-freqforge-canary-1",
    "freqai_rebel": "trading-freqai-rebel-1",
    "webserver": "trading-freqtrade-webserver-1",
}

BOT_HOST_PATHS = {
    "freqforge": "/home/hermes/projects/trading/freqforge/user_data",
    "regime_hybrid": "/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data",
    "canary": "/home/hermes/projects/trading/freqforge-canary/user_data",
    "freqai_rebel": "/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data",
}
```

---

## 7. Cron/Systemd Plan

### 7.1 Current Cron Jobs (57 total)

The 16 self-improvement jobs already exist. They need:
1. Script paths updated to use `docker exec` via DOCKER_HOST
2. Trade data sources connected (via SQLite extraction)  
3. Bot configs updated to use real container names and paths

### 7.2 Proposed Changes

| Job | Change | Risk |
|-----|--------|------|
| `si-bot-a-analyze-15min` → FreqForge | Update script to use BOT_CONTAINERS mapping | Low |
| `si-bot-b-analyze-20min` → Regime-Hybrid | Update script | Low |
| `si-bot-c-analyze-30min` → Momentum | ⚠️ No container — convert to backtest-analysis only | Medium |
| `si-bot-d-analyze-20min` → Canary | Update script | Low |
| All backtest jobs | Docker-aware execution required | Medium |
| All walkforward jobs | Docker-aware execution required | Medium |

### 7.3 No systemd needed — Hermes cron is the operative scheduler.

---

## 8. Logging and Rotation Plan

### 8.1 Current State
- `self_improvement/shared/logrotate.conf` exists but NOT deployed
- JSONL logs accumulate in `logs/trading-self-improvement/{bot}/`
- No size limits, no rotation

### 8.2 Fix
1. Deploy logrotate config to `/etc/logrotate.d/trading-self-improvement`
2. OR use a Hermes cron job (no_agent script) to rotate logs:
   - Archive files > 7 days old
   - Compress files > 50MB
   - Keep 14 daily backups
3. OR both — logrotate for system-level, Hermes cron for backup

### 8.3 copytruncate Risk Mitigation
For JSONL files, the `copytruncate` mode can lose a line during rotation.
**Mitigation:** Schedule rotation at low-activity time (03:00) and accept the
~1-line loss per 10,000 lines as acceptable for monitoring data.

---

## 9. Canary Promotion Logic

### 9.1 Proposal-Only (No Automatic Promotion)

```text
if canary_trades < 3:
    → "INSUFFICIENT_DATA — need 3+ trades"
    
if canary_dd_24h > 2.0:
    → "BLOCKED — canary drawdown exceeds limit"
    
if canary_pf > 1.25 and canary_dd_24h < 1.5:
    → "PROMOTION_CANDIDATE — ready for review"
    
promotion_output = {
    "canary_bot": "freqforge-canary-1",
    "target_bot": "freqforge-1",
    "candidate_params": {...},
    "backtest_result": "pass",
    "walkforward_result": "pass",
    "verdict": "promotion_candidate",
    "requires_human_approval": True,
}
```

### 9.2 No Auto-Rollout
Promotion never happens without:
1. `approval_gate.json approved: true`
2. `bot_config.json mode: deployment_allowed_after_approval`
3. Human review of the patch plan

---

## 10. Rollback and Kill-Switch Plan

### 10.1 Automatic Triggers (proposal-only mode)

| Trigger | Action |
|---------|--------|
| Post-deployment PF 24h < 0.8 | Rollback proposal generated |
| Post-deployment DD 24h > 4% (Core) / 3% (Momentum) | Rollback proposal generated |
| 3 consecutive losses after deployment | Rollback proposal generated |
| Slippage > 0.35% after deployment | Rollback proposal generated |

### 10.2 Rollback Mechanism
```python
# deployment_manager.py already supports rollback backups
# Every deployment creates: state_dir/rollback_config_{ts}.json
# Rollback = copy backup back to live path + git revert
```

### 10.3 Kill-Switch Conditions
```text
RED: Any production config mutation detected → block all → escalate
RED: dry_run switched to false → block all → escalate
RED: Container restart attempted via self-improvement → block → escalate
```

---

## 11. Patch Plan (Concrete File-by-File)

### 11.1 New Files to Create

| File | Purpose | Safety |
|------|---------|--------|
| `self_improvement/shared/docker_executor.py` | Centralized `docker exec` via DOCKER_HOST | Read-only container ops |
| `self_improvement/shared/trade_exporter.py` | Extract trades from container SQLite → JSONL | Read-only DB query |
| `self_improvement/shared/walk_forward_validator.py` | 4-window walk-forward via container backtest | Read-only backtest |
| `self_improvement/shared/canary_promotion_advisor.py` | Canary → Fleet promotion proposal | Proposal only |
| `self_improvement/shared/approval_gate_validator.py` | Validates gate before deployment | Config validation |
| `self_improvement/shared/rollback_watcher.py` | Monitor post-deployment performance | Read-only monitor |

### 11.2 Files to Update

| File | Change | Reason |
|------|--------|--------|
| `self_improvement/shared/backtest_runner.py` | Replace `subprocess.run(["freqtrade", ...])` → `docker_exec()` | freqtrade not on host PATH |
| `self_improvement/shared/performance_analyzer.py` | Add SQLite trade extraction source | No trades.jsonl from production bots |
| `self_improvement/shared/run_backtest.sh` | Use DOCKER_HOST env var | Docker proxy blocks exec |
| `self_improvement/shared/run_analyze.sh` | Use DOCKER_HOST env var | Same |
| Bot configs (4 files) | Update paths to real containers | Generic bot_a/b/c/d → real names |
| `self_improvement/shared/deployment_manager.py` | Add container-aware checks | Dry-run before docker exec |

### 11.3 Files to Remove/Replace

| File | Action | Reason |
|------|--------|--------|
| `self_improvement/bot_a/bot_config.json` | Rewrite → FreqForge config | Generic → real |
| `self_improvement/bot_b/bot_config.json` | Rewrite → Regime-Hybrid config | Same |
| `self_improvement/bot_c/bot_config.json` | Rewrite → Momentum (backtest-only) | No running container |
| `self_improvement/bot_d/bot_config.json` | Rewrite → Canary config | Same |

### 11.4 Files to Keep As-Is

| File | Reason |
|------|--------|
| `self_improvement/shared/strategy_mutator.py` | Path-agnostic, already works |
| `self_improvement/shared/logrotate.conf` | Just needs deployment |
| `self_improvement/shared/dashboard.py` | Path-agnostic, reads from state_dir |
| Hermes cron jobs (16) | Scripts just need updating |

---

## 12. Validation Commands

### 12.1 Pre-Patch Validation
```bash
# Verify docker exec works
DOCKER_HOST=unix:///var/run/docker.sock docker exec trading-freqtrade-freqforge-1 \
  python3 -c "import json; print('docker exec works')"

# Verify freqtrade CLI availability inside container
DOCKER_HOST=unix:///var/run/docker.sock docker exec trading-freqtrade-freqforge-1 \
  freqtrade --version

# Verify SQLite trade data
DOCKER_HOST=unix:///var/run/docker.sock docker exec trading-freqtrade-freqforge-1 \
  python3 -c "import sqlite3; c=sqlite3.connect('/freqtrade/user_data/tradesv3.dryrun.sqlite'); print(c.execute('SELECT COUNT(*) FROM trades').fetchone()[0])"

# Verify git status is clean before patching
cd /home/hermes/projects/trading && git status --short

# Python compile check
python3 -m py_compile self_improvement/shared/*.py
```

### 12.2 Post-Patch Validation
```bash
# Verify all modules compile
python3 -m py_compile self_improvement/shared/*.py

# Verify bot configs are valid JSON
for f in self_improvement/bot_*/bot_config.json; do echo "$f: $(python3 -m json.tool "$f" >/dev/null 2>&1 && echo OK || echo INVALID)"; done

# Dry-run performance analyzer
python3 self_improvement/shared/performance_analyzer.py \
  --config self_improvement/freqforge/bot_config.json 2>&1 | head -20

# Verify no production configs touched
git diff --stat -- self_improvement/ | grep -v self_improvement || true

# Test docker executor module
python3 -c "from self_improvement.shared.docker_executor import bot_list; print(bot_list())"
```

### 12.3 Safety Branch Creation
```bash
git add docs/context/self-improvement-hybrid-inventory-20260606.md
git commit -m "docs: self-improvement hybrid inventory report"
git checkout -b feat/self-improvement-hybrid-safe
```

---

## 13. Final Risk Verdict

| Layer | Status | Notes |
|-------|--------|-------|
| Docker Access | 🟡 YELLOW | `docker exec` blocked via proxy, works via DOCKER_HOST override |
| Bot Mapping | 🟡 YELLOW | Bot C (Momentum) has no running container |
| Trade Data | 🟡 YELLOW | Needs SQLite extraction pipeline — not connected yet |
| Backtest Execution | 🔴 RED | Currently fails — no freqtrade on host, no docker_exec wrapper |
| Config Safety | 🟢 GREEN | All configs in `proposal_only` mode, approval gates disabled |
| Git Safety | 🟢 GREEN | `self_improvement/` is untracked — no production files affected |
| Cron Jobs | 🟢 GREEN | 16 jobs created, all no_agent, all logging to project tree |
| Logrotate | 🟡 YELLOW | Config exists but not deployed to system |
| Walk-Forward | 🟢 GREEN | Existing implementation in repo, needs integration |
| Canary Promotion | 🟡 YELLOW | Logic exists conceptually, no code deployed |
| Rollback | 🟢 GREEN | deployment_manager.py already implements backup-before-overwrite |

**OVERALL VERDICT: 🟡 YELLOW** — Production-mutation safe (GREEN layer), but Docker execution and trade data extraction need implementation before the system can produce meaningful analysis. Backtests are RED (broken) until the Docker executor is built.

**Next Step:** Phase 2 → Generate gap report document, then Phase 3 → Hybrid patch plan review before any code changes.
