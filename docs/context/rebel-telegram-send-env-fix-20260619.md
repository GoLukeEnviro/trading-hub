# Rebel Telegram Status Summary — Send-Environment Fix

**Date:** 2026-06-19 (UTC)
**Operation Level:** L2 (safe dry-run write / one-shot send; no config edits, no new cron)
**Author:** Hermes orchestrator (cron run)
**Status:** OK — summary delivered

## Task

Send the Rebel FreqAI status summary via the existing `self_optimizer`
Telegram mechanism by invoking:

```python
import self_optimizer as so
so.send_rebel_status_summary(force=True)
```

## Outcome

`sent: true` — message delivered through
`orchestrator/scripts/drawdown_guard.py:send_telegram()` (HTTP 200).

## Why the bare invocation failed and the corrections applied

Running only the documented snippet against the automation path failed for
two reasons in the cron process environment:

1. **Missing sibling import path.** `_send_telegram_message()` dynamically
   loads `orchestrator/scripts/drawdown_guard.py`, which imports its sibling
   `fleet_api_client`. That directory is not on `sys.path`, producing
   `No module named 'fleet_api_client'`.
   - **Fix (runtime only):** insert `/home/hermes/projects/trading/orchestrator/scripts`
     at the front of `sys.path`.

2. **No valid token reachable from the process env.**
   `drawdown_guard._get_telegram_creds()` reads `os.environ` first, then falls
   back to `docker inspect hermes-green`. In this cron process:
   - `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_TOKEN_B64` are **unset**.
   - `hermes-green` `Config.Env` carries only a **13-char placeholder**
     `TELEGRAM_BOT_TOKEN` (real token is ~46 chars) plus a valid
     `TELEGRAM_ALLOWED_USERS`/`TELEGRAM_HOME_CHANNEL`.
   - Result: dummy token + real chat_id → Telegram `HTTP 404`.
   - **Fix (runtime only):** source `orchestrator/.env` into `os.environ`
     (contains the real `TELEGRAM_BOT_TOKEN` len=46 and `TELEGRAM_CHAT_ID`
     len=9). No secret values were logged or printed.

No config files, no cron jobs, no Docker objects were modified.

## Working invocation (self-contained)

```python
import sys, os
sys.path.insert(0, '/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/automation')
sys.path.insert(0, '/home/hermes/projects/trading/orchestrator/scripts')
for line in open('/home/hermes/projects/trading/orchestrator/.env'):
    s = line.strip()
    if s and not s.startswith('#') and '=' in s:
        k, _, v = s.partition('='); k = k[7:] if k.startswith('export ') else k
        v = v.strip().strip("'\"")
        if k.startswith('TELEGRAM_') and v and k not in os.environ:
            os.environ[k] = v
import self_optimizer as so
res = so.send_rebel_status_summary(force=True)
print(res.get('sent'), res.get('telegram'))
```

## Recommendation (L1 — advisory, not applied)

The documented "exact command" is insufficient in the cron context. For a
durable fix, either (a) wrap the documented snippet to also add
`orchestrator/scripts` to `sys.path` and load `orchestrator/.env`, or
(b) set `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` directly in the cron job's
environment. Any change to the cron job or environment should be done with
explicit approval (L3). Not applied here.

## Safety check

- No `dry_run=false`, no live orders, no strategy/risk changes.
- No secrets printed, persisted, or copied.
- No Docker rebuild/restart/prune, no volume or data operations.
- Kill switch / RiskGuard not involved (status-message send only).
