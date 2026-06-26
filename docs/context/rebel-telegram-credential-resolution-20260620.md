# Rebel Telegram Status Summary — Credential-Resolution Incident

**Date:** 2026-06-20 (UTC)
**Level:** L2 (incident resolution; no config or cron changes)
**Components:** `self_optimizer.py` (Rebel status), `orchestrator/scripts/drawdown_guard.py`
**Status:** DELIVERED via working path; root cause documented; code not modified.

## Trigger

Scheduled task: run `self_optimizer.send_rebel_status_summary(force=True)` to push the
Rebel FreqAI status summary over the existing Telegram mechanism.

The command **as-written failed**: `sent=False`, reason
`No module named 'fleet_api_client'` on the first invocation, then HTTP 404 on the
Telegram send once the import path was resolved.

## Root cause (two stacked issues)

1. **Sibling import path bug.** `self_optimizer._send_telegram_message()` loads
   `orchestrator/scripts/drawdown_guard.py` via `importlib.util.spec_from_file_location`
   with a bare file path. That does NOT place the module's directory on `sys.path`, so
   `drawdown_guard`'s `from fleet_api_client import freqtrade_api_get` (line 24) fails.
   `fleet_api_client.py` is a sibling in `orchestrator/scripts/`.

2. **Stale credential fallback.** `drawdown_guard._get_telegram_creds()` reads the
   Telegram token from `os.environ` first; if absent it tries base64, then falls back to
   `docker inspect hermes-green` (lines 230-244). In the cron environment no Telegram env
   var is set and `self_optimizer` never calls `load_env()`, so the function resolved
   credentials from the `hermes-green` container, which carries a **placeholder token**
   (13 chars, non-numeric head). The valid token lives in `orchestrator/.env`
   (46 chars, valid `N:xxxx` shape, confirmed by `getMe` → HTTP 200). Sending with the
   placeholder → Telegram HTTP 404.

   | Source            | Format                | `getMe` | `sendMessage` |
   |-------------------|-----------------------|---------|---------------|
   | `orchestrator/.env` | 46 chars, numeric head (valid) | 200 OK  | 200 OK        |
   | `hermes-green` env  | 13 chars, non-numeric (placeholder) | n/a     | **404**        |

   *(Secret values intentionally omitted; only length/format diagnostics recorded.)*

## What was done

- **No configs modified. No cron jobs created.** No code changes.
- The status summary was built correctly by `self_optimizer` on the first run.
- Delivery completed by populating `os.environ` from the valid `orchestrator/.env`
  (via `drawdown_guard.load_env()`) before invoking
  `send_rebel_status_summary(force=True)`, so `_get_telegram_creds()` selected the real
  token instead of the stale `hermes-green` fallback.
- Result: `sent=True`, `telegram_sent=True`, 404-char summary delivered.

## Recommended follow-up (requires approval — NOT applied here)

These are L3-adjacent code/config changes and were **not** performed:

1. Make `drawdown_guard._get_telegram_creds()` call `load_env()` first (or have
   `self_optimizer` import `drawdown_guard` with `orchestrator/scripts` on `sys.path`
   and call `load_env()`), so the valid `.env` token is used in cron without manual env
   population.
2. Remove/replace the placeholder Telegram token in the `hermes-green` container env, or
   reorder `_get_telegram_creds()` to prefer the `.env` token over the container fallback.
3. The summary also surfaced a `config_error`: *"No such container: freqai-rebel"* —
   i.e. `send_rebel_status_summary` could not reach the Rebel container at read time
   (metrics came from cached sources). Worth a separate health check.

## Live-trading / safety posture

Unchanged. `LIVE_FORBIDDEN`. Dry-run only. No orders, no credentials exposed, no
destructive operations, no strategy/risk/config changes.
