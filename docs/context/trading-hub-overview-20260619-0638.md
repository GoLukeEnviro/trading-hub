# Trading Hub Overview — 2026-06-19 06:38 UTC

Status: WARNING / YELLOW
Operation Level: L0 read-only audit + L2 documentation artifact
Scope: Runtime, Git/docs, Docker/Freqtrade fleet, SI v2, RiskGuard, ShadowLogger, kill switch, cron surface.

No Docker restart, no config mutation, no strategy/risk-parameter change, no live trading, no order action, no credential inspection.

## Executive verdict

The live dry-run runtime is healthy enough for observation: the 4-bot Freqtrade fleet is running, Docker-DNS pings return OK, all inspected active configs have `dry_run=true`, the signal producer is healthy, RiskGuard and ShadowLogger are current, and SI v2 remains `PAUSED / L3_REPOSITORY_ONLY` with zero mutation counters.

Overall status remains YELLOW because documentation snapshots are stale versus runtime, the worktree is dirty with generated/untracked artifacts, one enabled cron job has a last error (`Fleet correlation refresh`), and the latest SI v2 shadow proposals are not promotable due negative real net metrics / pending human approval.

## Evidence snapshot

- Audit timestamp: `2026-06-19T06:33:39+00:00` to `2026-06-19T06:38 UTC`
- Host/kernel: `Linux 6.8.0-124-generic x86_64 GNU/Linux`
- Uptime: `up 1 week, 2 days, 14 hours, 59 minutes`
- Disk: `301G total`, `194G used`, `95G available`, `68%`
- Memory: `30Gi total`, `24Gi available`
- Repo: branch `main`, HEAD `29f5a634c28955e2074775b06f63aa200640aba2`
- Remote main: `29f5a634c28955e2074775b06f63aa200640aba2` — local main matches remote main
- Git state: dirty worktree with generated SI v2 shadow logs modified and multiple untracked docs/reports/state artifacts.

## Runtime containers

- `trading-ai-hedge-fund-1`: running, Docker health `healthy`, port `127.0.0.1:8410->8080`
- `trading-freqtrade-freqforge-1`: running, port `127.0.0.1:8086->8080`
- `trading-freqtrade-regime-hybrid-1`: running, port `127.0.0.1:8085->8080`
- `trading-freqtrade-freqforge-canary-1`: running, port `127.0.0.1:8081->8080`
- `trading-freqai-rebel-1`: running, port `127.0.0.1:8087->8080`
- `trading-freqtrade-webserver-1`: running, port `127.0.0.1:8180->8080`
- `trading-shadowlock-1`: running, Docker health `healthy`
- `trading-guardian`: running
- `trading-hermes-watchdog-1`: running
- `hermes-green`: running

Endpoint checks from Hermes container via Docker DNS:

- `http://trading-ai-hedge-fund-1:8080/health`: HTTP 200, status `ok`, signal file exists, signal age 240s at check time.
- Freqtrade `/api/v1/ping`: `pong` for FreqForge, Regime-Hybrid, FreqForge-Canary, FreqAI-Rebel, and Webserver.
- `host.docker.internal` did not resolve from this container; Docker DNS is the validated path.

## Active Freqtrade configs

All inspected active container configs report `dry_run=true` and Bitget futures isolated mode.

- FreqForge: `dry_run=true`, futures/isolated, max open trades 5, API enabled, credentials present but not inspected.
- Regime-Hybrid: `dry_run=true`, futures/isolated, max open trades 5, API enabled, credentials present but not inspected.
- FreqForge-Canary: `dry_run=true`, futures/isolated, max open trades 3, API enabled, credentials present but not inspected.
- FreqAI-Rebel: `dry_run=true`, futures/isolated, max open trades 2, strategy config `RebelLiquidationV2`, API enabled, credentials present but not inspected.
- Webserver config: `dry_run=true`, futures/isolated, API enabled.

Local JSON config scan found no `dry_run=false` paths.

## Dry-run DB performance snapshot

Read-only SQLite inspection inside active containers:

- FreqForge DB: `tradesv3.freqforge.dryrun.sqlite`
  - total trades: 74
  - closed: 72
  - open: 2 (`ETH/USDT:USDT`, `SOL/USDT:USDT`)
  - closed profit abs sum: `+23.98030075`
  - latest close: `2026-06-18 21:13:52.017000`
- FreqForge-Canary DB: `tradesv3.freqforge_canary.dryrun.sqlite`
  - total trades: 51
  - closed: 51
  - open: 0
  - closed profit abs sum: `+5.58256377`
  - latest close: `2026-06-16 01:30:06.982000`
- Regime-Hybrid DB: `tradesv3.regime_hybrid.dryrun.sqlite`
  - total trades: 54
  - closed: 54
  - open: 0
  - closed profit abs sum: `-7.12849201`
  - latest close: `2026-06-17 09:55:50.036000`
- FreqAI-Rebel DB: `tradesv3.freqai_rebel.dryrun.sqlite`
  - total trades: 10
  - closed: 10
  - open: 0
  - closed profit abs sum: `-0.31948744`
  - latest close: `2026-06-17 09:10:02.541000`

## Signal core and RiskGuard

Signal artifact: `ai-hedge-fund-crypto/output/hermes_signal.json`

- mtime: `2026-06-19T06:30:47Z`
- source: `ai-hedge-fund-crypto`
- exchange: Bitget
- mode: `active`
- global risk mode: `risk_on`
- LLM used: true, model `deepseek-v4-pro`
- current pairs: BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT
- current action set: `short`, confidence `0.85` for all three pairs

RiskGuard artifacts:

- `orchestrator/state/riskguard/riskguard_health.json`: status `OK` at `2026-06-19T06:30:29Z`
- health checks: accepted 3, watch_only 0, signal found true, audit written true, state written true
- `orchestrator/state/riskguard/riskguard_state.json`: summary status `ACTIVE`, stale false, max age 25m, signal age 14.9m at write time
- verdicts: BTC/USDT, ETH/USDT, SOL/USDT all `ACCEPTED` by RiskGuard, but this remains advisory/filtering evidence only; it is not live execution authority.

## Kill switch

Files checked:

- `var/kill_switch.json`: absent
- `freqtrade/shared/kill_switch.json`: absent
- container `/freqtrade/shared/kill_switch.json`: absent

Code contract in `freqtrade/shared/kill_switch.py` returns default mode `NORMAL` when the state file is absent. Current evidence therefore indicates no active `HALT_NEW` or `EMERGENCY` kill-switch state.

## ShadowLogger / Shadowlock

- `orchestrator/logs/shadow_decisions.jsonl`: exists
- line count: 452
- mtime: `2026-06-19T06:30:26Z`
- last records every ~10 minutes through `2026-06-19T06:30:09Z`
- recent records contain schema/event/timestamp/signal/riskguard/decisions/state_writes fields
- `trading-shadowlock-1`: Docker health `healthy`; log heartbeat at `2026-06-19T06:33:42Z`

## SI v2 status

Latest scheduled active cycle:

- job: `si-v2-active-cycle (6h, log-only)` / job id `64866012641a`
- schedule: `17 */6 * * *`
- latest run: `2026-06-19T06:17:10Z`
- artifact: `self_improvement_v2/reports/phase2/evidence/active_cycle_20260619T061710Z.json`
- branch/commit: `main` / `29f5a63`
- fleet verdict: `GREEN`
- reason: all 4 bots authenticated and decisions generated
- total bots: 4
- ping OK: 4
- authenticated status count: 4
- ping failed: 0
- yellow missing env: 0
- mutation counters: runtime/config/live_trading/docker/strategy all 0
- controller state: `PAUSED / L3_REPOSITORY_ONLY`

Safety results:

- FreqForge: `NO_PROPOSAL`, reason `insufficient_signal_depth`; promotion blocked by `no_proposal`.
- FreqForge-Canary: `NO_PROPOSAL`, reason `insufficient_signal_depth`; promotion blocked by `no_proposal`.
- Regime-Hybrid: `SHADOW_PROPOSAL`, approval `PENDING_HUMAN`, RiskGuard `PASS_SHADOW_ONLY`, ShadowLogger `LOGGED`, but walk-forward net metrics are negative: total net PnL `-7.12849201`, profit factor `0.5801`, max drawdown pct `0.7656`, promotion blocked by `walk_forward_net_metrics_negative`.
- FreqAI-Rebel: `SHADOW_PROPOSAL`, approval `PENDING_HUMAN`, RiskGuard `PASS_SHADOW_ONLY`, ShadowLogger `LOGGED`, but walk-forward net metrics are negative: total net PnL `-0.31948744`, profit factor `0.2057`, max drawdown pct `0.0379`, promotion blocked by `walk_forward_net_metrics_negative`.

Measurement summary:

- artifact: `self_improvement_v2/reports/phase2/measurement/measurement_summary.json`
- build timestamp: `2026-06-19T06:17:10Z`
- controller state: `PAUSED / L3_REPOSITORY_ONLY`
- total cycles scanned: 30
- total fleet points: 30
- total bot points: 120
- total proposal records: 46
- total attribution windows: 46
- `mutations_all_zero=true`
- `secrets_found=false`
- fleet verdict counts: GREEN 6, YELLOW 11, RED 13
- latest Rainbow read-only status: `SUCCESS`, batch freshness `PARTIAL`, fresh signal count 24, stale signal count 26, confidence avg 0.552

## Cron surface

Cron tool reports 58 jobs.

Important healthy jobs:

- `trading-pipeline`: ok, every 10m, last `2026-06-19T06:30:26Z`
- `riskguard-service`: ok, every 30m, last `2026-06-19T06:30:29Z`
- `critical-event-watchdog`: ok, every 10m, last `2026-06-19T06:30:29Z`
- `unified-signal-heartbeat`: ok, every 15m, last `2026-06-19T06:30:47Z`
- `si-v2-active-cycle`: ok, 6h schedule, last `2026-06-19T06:17:10Z`, next `2026-06-19T12:17:00Z`
- `ledger-integrity-watchdog`: ok, every 30m, last `2026-06-19T06:35:41Z`

Cron finding:

- `Fleet correlation refresh`: enabled, last status `error`, last run `2026-06-17T22:09:39Z`, next `2026-06-20T22:09:39Z`.
- Several historical `si-bot-*` jobs are disabled/paused with post-closure reasons; this appears intentional, not a live runtime failure.

## Documentation drift

Current runtime is ahead of canonical docs:

- `docs/state/current-operational-state.md` says validated at commit `4dd4d5c8` and latest cycle `20260614T204852Z`.
- Runtime/repo evidence shows current main at `29f5a63` and latest cycle `20260619T061710Z`.
- `docs/state/canonical-trading-status.md` was generated `2026-06-15T09:04:22Z` and contains stale signal/RiskGuard timestamps.

This is documentation drift only; runtime evidence is fresher and should be treated as authoritative for this audit.

## Risks / blockers

1. No live-money path found in this audit; all inspected active configs and local config scan are dry-run.
2. Open dry-run exposure exists in FreqForge: ETH and SOL dry-run positions.
3. Latest AI signal is risk-on/short, and RiskGuard accepts it, but that must not be treated as execution authority.
4. Latest SI v2 shadow proposals are not deployable: pending human approval and blocked by negative walk-forward net metrics.
5. Documentation snapshots are stale and can mislead future agents unless refreshed.
6. One enabled cron job has last status `error`: `Fleet correlation refresh`.
7. Worktree is dirty with generated/untracked artifacts; avoid broad cleanup or `git add .`.
8. `host.docker.internal` does not resolve from Hermes container; Docker DNS names are the verified service path.

## Next safe steps

1. L2 docs-only: refresh `docs/state/current-operational-state.md` and `docs/state/canonical-trading-status.md` from the 2026-06-19 runtime evidence.
2. L0/L1: triage `Fleet correlation refresh` last error by reading its script/output only; do not restart cron or mutate jobs without approval if runtime behavior would change.
3. L0/L1: summarize the dirty worktree by owner/source and separate generated runtime artifacts from documentation reports.
4. Keep SI v2 in `PAUSED / L3_REPOSITORY_ONLY`; no shadow proposal promotion while net metrics are negative and approval is pending.

## Approval boundaries

Freigabe nicht erteilt / not performed:

- no Docker restart/recreate/rebuild/prune
- no Freqtrade config mutation
- no strategy/risk threshold mutation
- no cron mutation
- no data deletion/cleanup
- no live trading or `dry_run=false`
- no real orders
