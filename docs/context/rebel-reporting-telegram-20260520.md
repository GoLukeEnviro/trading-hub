# Rebel Telegram Reporting — 2026-05-20

## Scope
Extended `freqtrade/bots/regime-hybrid/config/research/automation/self_optimizer.py` with lightweight Telegram reporting for Rebel Self-Optimizer events and scheduled status summaries.

## Implemented

### Event notifications
Important events now send a best-effort Telegram message through the existing `orchestrator/scripts/drawdown_guard.py::send_telegram` helper:
- `patch_success`
- `patch_failed_rollback`
- `requires_new_identifier`

Messages include bot name, status, changed paths/values, rollback flag, timestamp, and the event JSON path.

### Proposal / diagnosis notifications
- Important Stage-0 proposals involving `scale_pos_weight` send one review notification per proposal ID.
- High/critical Rebel diagnoses send one alert per issue-set every 6h max.

### Scheduled summary
Added:
- `build_rebel_status_summary()`
- `send_rebel_status_summary(force=False, min_interval_hours=12.0)`
- CLI flag: `python3 self_optimizer.py --rebel-summary --json`

Summary includes DI threshold, stake, scale_pos_weight, performance snapshot, proposal counts, last events, and one action recommendation.

## Cron
Created Hermes cron job:
- Name: `Rebel Status Summary (12h Telegram)`
- Job ID: `5ed59e6cf398`
- Schedule: every 12h
- Delivery: local (the Python function sends Telegram itself)
- Next run: 2026-05-21T08:20:08Z

## Verification
- Syntax check passed via `py_compile`.
- `build_rebel_status_summary()` executed successfully.
- Forced summary sent via Telegram successfully (`sent=true`).

## Notes
- No strategy code, feature engineering, labels, or live trading settings were changed.
- Event notifications are best-effort and never block patch or rollback logic.
- Anti-spam state is stored at `events/rebel/reporting_state.json`.
