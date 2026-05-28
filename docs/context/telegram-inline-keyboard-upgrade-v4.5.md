# Telegram Inline-Keyboard Upgrade v4.5

Status: implemented in the trading orchestration scripts.

## What changed
- `orchestrator/scripts/drawdown_guard.py`
  - `send_telegram(...)` now accepts `inline_keyboard`.
  - Sends Telegram messages via POST JSON with `reply_markup` when buttons are provided.
- `orchestrator/scripts/system_optimizer.py`
  - Report payloads now include `inline_keyboard` metadata.
  - Fleet / recovery / cleanup / approval-style reports now queue button sets.
- `freqtrade/bots/regime-hybrid/config/research/automation/self_optimizer.py`
  - Rebel notifications now pass inline keyboards through the existing Telegram helper.

## Button callbacks used
- `restore_max_open_trades`
- `fix_permissions`
- `optimize_regime_hybrid`
- `check_canary_shorts`
- `fleet_report_now`
- `cleanup_all`
- `confirm_execute`
- `defer_action`
- `rebel_apply_patch`
- `rebel_rollback`
- `rebel_show_details`

## Notes
- This keeps the Telegram delivery path read-only with respect to trading state; the button callbacks are the action identifiers for downstream handlers.
- No exchange credentials were added or modified.
