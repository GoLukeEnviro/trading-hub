# Phase 12.6 — Full Orchestrator Gauntlet Validation Report

## Overall Result

PARTIAL

## Executive Summary

The Hermes orchestrator trading stack passed the full read-only gauntlet end-to-end under the `orchestrator` profile.

Verified components:
- Hermes profile isolation and context
- PrimoAgent crypto signal pipeline
- RiskGuard deterministic filter
- ShadowLogger evidence logging
- Risk-aware bridge state emission
- Freqtrade helper bias policy
- Per-bot state files
- Fleet healthcheck
- Multi-cycle validator
- Wrapper v0.2 execution
- Safe fixture-based negative tests
- Cron/profile isolation
- Forbidden-change guarantees

The production safety chain is green and the wrapper exited 0. The only reason this report is PARTIAL rather than PASS is Phase 13 readiness: the current observation window contains 6 wrapper runs total, but only 4 successful wrapper runs were confirmed in the validator output, so the gate policy for GO is not yet satisfied.

## System Architecture Tested

Validated architecture:
- Hermes `orchestrator` profile as control plane
- PrimoAgent at `/home/hermes/primoagent`
- RiskGuard at `/home/hermes/primoagent/risk_guard_v0_1.py`
- ShadowLogger at `/home/hermes/primoagent/shadow_logger_v0_1.py`
- Risk-aware bridge at `/home/hermes/projects/trading/freqtrade/tools/primo_signal_bridge.py`
- Shared helper at `/home/hermes/projects/trading/freqtrade/shared/primo_signal.py`
- Freqtrade bot state files under `/home/hermes/projects/trading/freqtrade/bots/*/user_data/primo_signal_state.json`
- Fleet healthcheck at `/home/hermes/projects/trading/orchestrator/scripts/fleet_healthcheck.py`
- Multi-cycle validator at `/home/hermes/projects/trading/orchestrator/scripts/multicycle_validator.py`
- Wrapper at `/home/hermes/projects/trading/orchestrator/scripts/run_trading_cycle.sh`

## Hermes Orchestrator Profile Status

PASS

Evidence:
- `hermes profile list` shows `orchestrator`
- `hermes -p orchestrator config show` reports working dir `/home/hermes/projects/trading`
- Profile SOUL exists at `/home/hermes/.hermes/profiles/orchestrator/SOUL.md`
- Project SOUL exists at `/home/hermes/projects/trading/SOUL.md`
- `AGENTS.md` exists at `/home/hermes/projects/trading/AGENTS.md`
- `ORCHESTRATOR_CHARTER.md` exists at `/home/hermes/projects/trading/ORCHESTRATOR_CHARTER.md`

## Static Component Inventory and Syntax Results

PASS

Python syntax checks:
- `/home/hermes/primoagent/run_primo_crypto_pipeline.py` → OK
- `/home/hermes/primoagent/risk_guard_v0_1.py` → OK
- `/home/hermes/primoagent/shadow_logger_v0_1.py` → OK
- `/home/hermes/projects/trading/freqtrade/tools/primo_signal_bridge.py` → OK
- `/home/hermes/projects/trading/freqtrade/shared/primo_signal.py` → OK
- `/home/hermes/projects/trading/orchestrator/scripts/fleet_healthcheck.py` → OK
- `/home/hermes/projects/trading/orchestrator/scripts/multicycle_validator.py` → OK

Shell syntax:
- `/home/hermes/projects/trading/orchestrator/scripts/run_trading_cycle.sh` → `bash -n` OK

## Dry-Run Fleet Safety Result

PASS

Live container snapshot:
- `freqtrade-rsi` running
- `freqtrade-momentum` running
- `freqtrade-regime-hybrid` running
- `hermes-agent` running

Config audit:
- All readable Freqtrade configs reported `dry_run=True`
- Exchange credentials absent in all inspected configs (`exchange.key=absent`, `exchange.secret=absent`)

Fleet healthcheck:
- Verdict: GREEN
- Bots checked: 3
- JSON and Markdown reports written successfully

## Wrapper Gauntlet Run Result

PASS

Wrapper run:
- Command: `timeout 900 /home/hermes/projects/trading/orchestrator/scripts/run_trading_cycle.sh`
- Exit code: 0
- Run ID: `20260507T210235Z`
- Wrapper log: `/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260507T210235Z.log`

Observed run timeline from log:
- Start: 2026-05-07T21:02:35Z
- Completion: 2026-05-07T21:04:01Z
- Observed wrapper cycle duration: about 86 seconds

## PrimoAgent Pipeline Result and Runtime Duration

PASS

PrimoAgent pipeline completed successfully inside the wrapper:
- 7 symbols analyzed
- Dry-run advisory mode only
- Raw signal JSON written to `/home/hermes/primoagent/output/signals/primo_multi_signal_latest.json`
- CSV output written to `/home/hermes/primoagent/output/csv/crypto_pipeline_latest.csv`

Observed PrimoAgent runtime from wrapper log:
- Step 1 began at 2026-05-07T21:02:35Z
- Step 1 completed at 2026-05-07T21:04:00Z
- Runtime: about 85 seconds

## RiskGuard Result and Verdict Distribution

PASS

Production wrapper run:
- Input valid
- Output valid JSON
- Total signals: 7
- ACCEPTED: 0
- WATCH_ONLY: 7
- BLOCK_ENTRY: 0
- Stale: 0

RiskGuard output file:
- `/home/hermes/primoagent/output/signals/primo_risk_filtered_latest.json`

## ShadowLogger Append Result

PASS

ShadowLogger completed and appended evidence:
- Run ID: `run_20260507T210400Z_9b00815b`
- Total signals logged: 7
- Global log: `/home/hermes/primoagent/output/shadow/primo_shadow_log.jsonl`
- Daily log: `/home/hermes/primoagent/output/shadow/daily/2026-05-07.jsonl`
- Latest summary: `/home/hermes/primoagent/output/shadow/reports/shadow_summary_latest.md`

Validation:
- Shadow log is non-empty
- Shadow summary exists

## Risk-Aware Bridge Result

PASS

Bridge output from wrapper run:
- `bridge_version`: `0.2.0-risk-aware`
- `source_type`: `riskguard`
- `riskguard_available`: `true`
- `fresh`: `false`
- `bots_written`: 3

State files written:
- `/home/hermes/projects/trading/freqtrade/bots/rsi/user_data/primo_signal_state.json`
- `/home/hermes/projects/trading/freqtrade/bots/momentum/user_data/primo_signal_state.json`
- `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json`

Production bridge summary:
- total: 7
- accepted_count: 0
- watch_only_count: 7
- blocked_count: 0
- stale_count: 0
- long_bias_count: 0
- short_bias_count: 0
- fail_open: false

## State Schema and Bias Policy Result

PASS

All three production state files validated as JSON and matched schema 0.2.

Per-file audit:
- top-level required fields present
- `schema_version = 0.2`
- `bridge_version = 0.2.0-risk-aware`
- `source_type = riskguard`
- no missing required pair fields
- no unexpected directional bias

Observed pair behavior in production state files:
- WATCH_ONLY entries remained neutral
- no long bias
- no short bias
- `BLOCK_ENTRY` remains neutral by design for now

## Fleet Health Result

PASS

Fleet health report:
- Verdict: GREEN
- Total bots: 3
- Bots all dry-run safe
- No credentials present
- Shared helper present

Report paths:
- JSON: `/home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.json`
- Markdown: `/home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.md`

## Multi-Cycle Validator Result

PASS

Validator output:
- Status: GREEN
- Wrapper runs found: 6
- RiskGuard: OK
- ShadowLogger: 35 lines
- State Files: OK
- Fleet Health: GREEN

Report paths:
- JSON: `/home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.json`
- Markdown: `/home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.md`

Observation window note:
- 6 wrapper runs were found
- validator output includes 4 successful runs and 2 unknown entries
- this is sufficient for a green validator report, but not sufficient for Phase 13 GO under the stricter gate policy

## Negative Fixture Test Result

PASS

Safe fixture directory:
- `/home/hermes/projects/trading/orchestrator/test-fixtures/phase-12-6`

Fixture-based RiskGuard tests:
- stale BUY fixture → ACCEPTED 0, WATCH_ONLY 7, BLOCK_ENTRY 0, Stale 7
- low-confidence BUY fixture → ACCEPTED 0, WATCH_ONLY 7, BLOCK_ENTRY 0, Stale 0
- invalid pair fixture → ACCEPTED 0, WATCH_ONLY 7, BLOCK_ENTRY 0, Stale 0

Helper tests with minimal schema 0.2 fixture files:
- missing state file → neutral/fail-open True
- WATCH_ONLY long → True
- WATCH_ONLY short → True
- ACCEPTED BUY long → True
- ACCEPTED BUY short → False
- ACCEPTED SELL long → False
- ACCEPTED SELL short → True

Conclusion:
- negative tests stayed safe
- no production files were overwritten
- helper fail-open behavior works as intended

## Cron/Profile Isolation Result

PASS

Cron audit:
- global cron list unchanged
- orchestrator profile cron list is empty
- no cron migration into orchestrator profile occurred

Profile files present:
- `/home/hermes/.hermes/profiles/orchestrator/config.yaml`
- `/home/hermes/.hermes/profiles/orchestrator/SOUL.md`

## Forbidden Changes Verification

PASS

Confirmed unchanged / not performed:
- no live trading enabled
- no `dry_run=false`
- no exchange credentials added
- no real orders placed
- no Freqtrade REST forcebuy/forcesell used
- no Freqtrade configs modified
- no Freqtrade strategy files modified
- no containers restarted, recreated, stopped, paused, or deleted
- no cronjobs migrated, edited, deleted, paused, duplicated, or removed
- `/home/hermes/primoagent` was not moved or symlinked
- no signal, shadow, state, log, report, or historical files were deleted

## Known Tech Debt

- `BLOCK_ENTRY` semantics are intentionally neutral for now, matching `WATCH_ONLY` behavior in the helper
- this is documented deferred tech debt, not a regression

## Known Operational Issue

- wrapper timeout should remain at 900 or higher for the gauntlet
- this observed run completed in about 85 seconds, but the phase spec still notes slower PrimoAgent runs can take around 160 seconds

## Phase 13 Readiness

WAIT

Reason:
- the gauntlet is green, but the observation window does not yet satisfy the stricter gate policy of at least 6 successful wrapper runs

## Evidence Files

Final report:
- `/home/hermes/projects/trading/docs/context/phase-12-6-orchestrator-gauntlet-report-2026-05-07.md`

Latest wrapper log:
- `/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260507T210235Z.log`

Fleet health report:
- `/home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.md`
- `/home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.json`

Multi-cycle report:
- `/home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.md`
- `/home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.json`

Additional evidence:
- Raw signal JSON: `/home/hermes/primoagent/output/signals/primo_multi_signal_latest.json`
- RiskGuard JSON: `/home/hermes/primoagent/output/signals/primo_risk_filtered_latest.json`
- Shadow log: `/home/hermes/primoagent/output/shadow/primo_shadow_log.jsonl`
- Shadow summary: `/home/hermes/primoagent/output/shadow/reports/shadow_summary_latest.md`

## Next Actions

1. Run at least 2 more successful wrapper cycles with the same read-only safety contract to satisfy the Phase 13 GO gate.
2. Keep monitoring for state drift in the 3 bot state files and verify every new wrapper run preserves schema 0.2 and zero directional bias unless ACCEPTED verdicts appear.
3. Decide whether `BLOCK_ENTRY` should remain neutral or graduate into explicit block-policy semantics in a later phase; do not change it in this phase.
