# Incident — Rebel status summary Telegram send fails (HTTP 404)

- Date: 2026-06-24 (cron run, orchestrator profile)
- Operation Level: L0/L2 (read-only diagnosis; no config/cron/credential change)
- Status: ESCALATED (requires credential review)

## Trigger
Scheduled task: run `self_optimizer.send_rebel_status_summary(force=True)` to push the
Rebel FreqAI status summary via the existing self_optimizer Telegram mechanism.

## Observed
- The exact command executed; module import resolved after noting that
  `_send_telegram_message` dynamically loads `orchestrator/scripts/drawdown_guard.py`,
  which top-level-imports `fleet_api_client` (located in `orchestrator/scripts/`).
  That directory is not on sys.path for the automation module, producing
  `No module named 'fleet_api_client'`. Putting `orchestrator/scripts` on PYTHONPATH
  (environment-only, no config/cron change) resolved the import.
- After import resolved, the Telegram send returned `HTTP Error 404: Not Found`.

## Root cause (mask-safe diagnosis; no secret values read or stored)
- No `TELEGRAM_*` env vars are present in the cron environment.
- `drawdown_guard._get_telegram_creds()` falls back to `docker inspect hermes-green`
  `.Config.Env` for `TELEGRAM_BOT_TOKEN`.
- The resolved token from `hermes-green` is NOT a valid Telegram bot token
  (length ~13 chars; real tokens are `numeric:35-char-hash`, ~45 chars with a colon).
- Telegram's API returns 404 specifically for an unknown/invalid bot token
  (a valid token with a bad chat id would return 400, not 404).

## Impact
- The Rebel FreqAI status summary could NOT be delivered via Telegram.
- This will recur on every scheduled run until the token source is fixed.

## Required action (Ask-First / L3 — credentials)
- Provide a valid `TELEGRAM_BOT_TOKEN` (and `TELEGRAM_CHAT_ID`) to the cron runtime
  environment, OR correct the `hermes-green` container env so the fallback resolves a
  real token. Credential changes require explicit human approval and must never be
  printed/persisted by automation.

## Constraints respected
- No configs modified. No new cron jobs created. No secrets exposed.
