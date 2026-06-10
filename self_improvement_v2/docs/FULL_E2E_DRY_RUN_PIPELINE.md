# Full SI v2 E2E Dry-Run Pipeline

## Overview

This document describes the complete 9-stage Self-Improvement v2 pipeline
as implemented for Phase K. The pipeline orchestrates all SI v2 components
through a single `DryRunPipelineHarness` using **only** stub/dry-run/in-memory
implementations. No real adapters, no network calls, no live config writes,
and no Docker operations occur at any point.

The pipeline is designed to be fully testable, deterministic, and safe for CI.

---

## 9 Pipeline Stages

### Stage 0: Signal Check
- **Component:** `InMemorySignalProvider`
- **Input:** Asset identifier from bot config
- **Output:** AdvisorySignal (direction, confidence, risk_score)
- **Boundary:** ai4trade-bot integration protocol
- **Gate:** If signal is `"hold"`, the entire pipeline is BLOCKED
- **Statuses:** `passed` (actionable signal) | `blocked` (hold/no signal)

### Stage 1: Observe (Trade Export)
- **Component:** `TradeExporter` → `FreqtradeAdapter` (dry-run stub)
- **Input:** `bot_id`
- **Output:** List of trade records (dicts with profit_pct, profit_abs, etc.)
- **Boundary:** Freqtrade database (via adapter protocol)
- **Fail-closed:** Exception → stage `failed`

### Stage 2: Analyze (Performance Analytics)
- **Component:** `PerformanceAnalyzer`
- **Input:** Trade records from Stage 1
- **Output:** `AnalysisResult` with per-window `WindowStats` and `decision`
- **Boundary:** Pure computation — no I/O
- **Decision rules:**
  - `< 5 trades` → `"hold"`
  - `consecutive_losses >= 5` → `"block"`
  - Otherwise → `"hold"`
- **Fail-closed:** Exception → stage `failed`

### Stage 3: Propose (Mutation Candidate)
- **Component:** `StrategyMutator` (propose package, not AST)
- **Input:** `AnalysisResult`
- **Output:** `MutationCandidate` or `None`
- **Boundary:** safe_parameters validation
- **Gate:** If `decision == "hold"`, no candidate is built → stage `blocked`
- **Fail-closed:** Exception → stage `failed`

### Stage 4: Mutate Sandbox
- **Components:** `StrategySandbox` + AST `StrategyMutator` + `StrategySandboxValidator`
- **Input:** `MutationCandidate`, strategy fixture file path
- **Output:** `StrategyMutationPlan` (sandbox copy, backup, diff, validation)
- **Boundary:** Filesystem (tmp_path sandbox only)
- **Process:**
  1. Copy source strategy to sandbox directory
  2. Create byte-identical backup
  3. Apply AST-based parameter mutations (rsi_period, cooldown_candles)
  4. Validate: backup exists, diff exists, Python compiles, ranges valid
- **Fail-closed:** Missing parameter → `ValueError` → stage `blocked`
- **Safety:** Original source file is NEVER modified

### Stage 5: Backtest
- **Component:** `BacktestRunner` → `FreqtradeAdapter` (dry-run stub)
- **Input:** `MutationCandidate`, `BotConfig`
- **Output:** `BacktestResult` (total_trades, profit_total_pct, etc.)
- **Boundary:** Freqtrade backtesting engine (via adapter protocol)
- **Pass criteria (stub):** profit > 0, drawdown < 15%, trades >= min_trades
- **Fail-closed:** Adapter returns empty/incomplete → `passed=False` → stage `blocked`

### Stage 6: Walk-Forward Validation
- **Component:** `WalkForwardValidator`
- **Input:** Trade data, `MutationCandidate`, `BotConfig`, `BacktestRunner`
- **Output:** `WalkForwardResult` (stability_score, passed, reason)
- **Boundary:** Pure computation — splits trades into train/test windows
- **Split strategy:** 3 windows, 70/30 train/test ratio
- **Pass criteria:** Out-of-sample profit > 0 AND stability_score > 0.5
- **Fail-closed:** Insufficient data → stage `blocked`

### Stage 7: Approval Gate
- **Component:** `ApprovalGateManager` + `DryRunTelegramAdapter` + `ShadowLogger`
- **Input:** `BacktestResult`, `WalkForwardResult`, `BotConfig`, `MutationCandidate`
- **Output:** `ApprovalDecision` (status: "rejected" | "pending")
- **Boundary:** Telegram (via dry-run adapter — never calls real API)
- **Auto-reject triggers:**
  - `backtest.passed == False`
  - `walk_forward.passed == False`
  - `profit_total_pct <= 0`
  - `max_drawdown_pct >= 0.15`
  - `stability_score < 0.5`
  - `total_trades < 5`
  - Walk-forward reason contains "insufficient"
- **Phase K invariant:** Auto-approval is **impossible** — no "approved" status
- **States:** `"rejected"` → plan blocked | `"pending"` → plan waits for human

### Stage 8: Deployment Plan
- **Component:** `DeploymentPlanOrchestrator`
- **Input:** Candidate, config, backtest + walk-forward results, approval decision
- **Output:** `DeploymentPlan` (status, steps, reason)
- **Status values:**
  - `"rejected"` — approval auto-rejected
  - `"pending_approval"` — waiting for human review (Phase K default)
  - `"ready_for_shadow"` — approved, shadow session started
  - `"blocked"` — (not currently used)
- **Boundary:** No live configs written, no Freqtrade restarted, no Docker

### Stage 9: Shadow Mode
- **Component:** `ShadowModeManager` (injected clock, no timers)
- **Input:** `DeploymentPlan` status
- **Output:** Shadow session check
- **Boundary:** In-memory only — no background processes, no cron, no threading
- **Gate:** Shadow only starts if `plan.status == "ready_for_shadow"`
- **Phase K invariant:** Shadow is NEVER started because human approval is never given

---

## Fail-Closed Gates

The pipeline enforces fail-closed behaviour at every stage boundary:

| Stage | Failure Mode | Guard |
|-------|-------------|-------|
| Signal Check | No signal / "hold" direction | Pipeline blocked, no stages execute |
| Observe | Adapter failure | Trade export fails |
| Analyze | Computation error | Analysis fails |
| Propose | "hold" decision | No candidate built |
| Mutate Sandbox | Missing/ambiguous parameters | ValueError raised |
| Backtest | Negative/insufficient results | passed=False |
| Walk-Forward | Insufficient data / negative OOS | passed=False |
| Approval | Any auto-reject trigger | status="rejected" |
| Deployment Plan | Rejected / pending | Shadow not started |
| Shadow Mode | Plan not "ready_for_shadow" | Shadow not started |

---

## Not Live-Ready

The pipeline and all its components are **not live-ready**. The following
safety invariants are enforced by tests:

1. **No real adapter imports** — `docker`, `freqtrade`, `telegram`, `requests`,
   `httpx`, `ccxt` are never imported in pipeline source
2. **No non-localhost URLs** — all URLs are localhost-only (REST boundary)
3. **No jobs.json writes** — pipeline never writes cron job files
4. **No live strategy path writes** — no `user_data/strategies` or
   `freqtrade/strategies` writes
5. **No env secrets read** — no `os.environ` / `os.getenv` in pipeline code
   (except `config.gate.py` which reads `SI_V2_ENABLE_REAL_ADAPTERS`)
6. **No Any types** — all types are explicit

---

## Preconditions for Future Runtime Probe

Before the SI v2 pipeline can run in a real (non-test) environment,
the following must be satisfied:

### Adapters
- [ ] Real `FreqtradeAdapter` implementation connecting to live DB
- [ ] Real `DockerAdapter` implementation for container management
- [ ] Real `TelegramAdapter` implementation with bot token
- [ ] Real ai4trade REST `SignalProvider` / `OutcomeProvider` / `RiskGateProvider`

### Configuration
- [ ] Valid `BotConfig` entries for each managed bot
- [ ] Accessible strategy files in the workspace
- [ ] Sandbox root directory with write permissions
- [ ] `SI_V2_ENABLE_REAL_ADAPTERS` environment variable set

### Safety Checks
- [ ] Approval gate configured with proper Telegram chat IDs
- [ ] Rollback snapshots configured before first mutation
- [ ] Shadow logger persistence configured (log_dir)
- [ ] Call budget thresholds configured for adapter calls

### Deployment
- [ ] Cron defs integration for scheduled pipeline runs
- [ ] Rest boundary guard asserting non-localhost connections
- [ ] Walk-forward minimum trade thresholds calibrated
- [ ] Backtest pass/fail criteria calibrated for production

---

## Testing

Run the E2E pipeline tests:

```bash
PYTHONPATH=self_improvement_v2/src /tmp/si_v2_venv/bin/python \
    -m pytest self_improvement_v2/tests/test_e2e_dry_run.py -v

PYTHONPATH=self_improvement_v2/src /tmp/si_v2_venv/bin/python \
    -m pytest self_improvement_v2/tests/test_pipeline_safety.py -v
```

Expected test count additions:
- `test_e2e_dry_run.py`: 10 tests (4 happy-path + 6 fail-closed)
- `test_pipeline_safety.py`: 5 tests (5 safety regressions)
