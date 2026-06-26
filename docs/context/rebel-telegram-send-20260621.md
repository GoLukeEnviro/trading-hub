# Rebel Telegram Status Summary — Scheduled Send (2026-06-21)

**Date:** 2026-06-21T01:19Z (UTC)
**Level:** L2 (safe runtime-only send; no config edits, no cron changes, no code changes)
**Components:** `self_optimizer.py` (Rebel status), `orchestrator/scripts/drawdown_guard.py`
**Status:** OK — summary delivered (`sent=True`)

## Task

Scheduled cron: deliver the Rebel FreqAI status summary via the existing
`self_optimizer.send_rebel_status_summary(force=True)` Telegram mechanism.
Constraint: do not modify configs; do not create additional cron jobs.

## Outcome

`sent: true` — message delivered through
`orchestrator/scripts/drawdown_guard.py:send_telegram()` (HTTP 200).

```json
{ "sent": true, "telegram": { "sent": true, "via": "/home/hermes/projects/trading/orchestrator/scripts/drawdown_guard.py" } }
```

## Why the bare documented command failed (again)

The command as-written (automation dir on `sys.path` only) failed first with
`sent=False`, reason `No module named 'fleet_api_client'` — the identical
recurring defect logged on 06-14, 06-17, 06-18, 06-19, and 06-20. Two stacked
runtime issues, unchanged since those runs:

1. **Sibling import path.** `_send_telegram_message()` loads `drawdown_guard.py`
   via `importlib` with a bare file path, so `drawdown_guard`'s
   `from fleet_api_client import ...` fails (`fleet_api_client.py` is a sibling
   in `orchestrator/scripts/`, which is not on `sys.path`).
2. **Stale credential fallback.** In the cron env no Telegram var is set, so
   `_get_telegram_creds()` resolves a 13-char placeholder from `hermes-green`
   instead of the valid ~46-char token in `orchestrator/.env`.

## Resolution applied (runtime-only, no artifacts changed)

Same validated approach as the 06-19/06-20 runs:

- Insert both the automation dir AND `orchestrator/scripts` at the front of
  `sys.path`.
- Source only `TELEGRAM_*` keys from `orchestrator/.env` into `os.environ`
  (never overriding existing values; nothing printed/persisted).
- Then call `send_rebel_status_summary(force=True)`.

No config files, cron jobs, Docker objects, or code were modified.

## Persistent recommendation (still NOT applied — needs L3 approval)

The documented "exact command" remains insufficient in the cron context, so the
task fails on every run until rescued by runtime env loading. A durable fix
needs explicit approval (L3), e.g.:
(a) wrap the snippet to add `orchestrator/scripts` to `sys.path` and load
`orchestrator/.env`; (b) set `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` in the
cron job environment; or (c) make `drawdown_guard._get_telegram_creds()` call
`load_env()` first and have `self_optimizer` import it with the scripts dir on
path. Until then this task will keep failing the bare invocation.

## Safety posture

Unchanged. `LIVE_FORBIDDEN`. Dry-run only. No orders, no `dry_run=false`, no
secrets exposed, no destructive operations, no strategy/risk/config changes.
