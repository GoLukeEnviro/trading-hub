# Rebel Status Summary Telegram Send — STILL BLOCKED (20260618, recurrence)

**Operation Level:** L0 inspection / L2 diagnostic artifact
**Decision:** WARNING -> ESCALATED (credential remediation still pending)
**Status:** Telegram send NOT delivered (identical to 20260617)

## Recurrence

Same scheduled cron task as 20260617: send Rebel FreqAI status summary via
`self_optimizer.send_rebel_status_summary(force=True)`. Result today:
`sent: false`. Both blockers from 20260617 persist unchanged.

See `docs/context/rebel-telegram-send-blocked-20260617.md` for the full
root-cause analysis. This file records only what was re-confirmed today.

## Re-confirmed evidence (20260618 12:45 UTC, structural only — no secret values)

Blocker 1 (import path gap) — unchanged:
- Exact command run from `/home/hermes/projects/trading` returns
  `reason = "No module named 'fleet_api_client'"`.
- `fleet_api_client.py` lives at `orchestrator/scripts/`, not on sys.path.
- Resolves at runtime by adding `orchestrator/scripts` to sys.path/PYTHONPATH.

Blocker 2 (malformed bot token in `hermes-green`) — unchanged, HARD blocker:
- No `TELEGRAM_*` env vars in the cron/orchestrator runtime shell.
- Fallback resolves token from `docker inspect hermes-green .Config.Env`.
- `hermes-green` `TELEGRAM_BOT_TOKEN`: **len=13, no colon** -> not a valid
  Telegram bot-token shape (real tokens: `<digits>:<35+ alnum>`, ~45-46 chars).
- Send chain `self_optimizer._send_telegram_message`
  -> `drawdown_guard.send_telegram`
  -> `POST https://api.telegram.org/bot{token}/sendMessage` returns
  **HTTP 404 {"ok":false,"error_code":404,"description":"Not Found"}**.
- Egress to `api.telegram.org` confirmed healthy (bogus token path returns
  Telegram's own 404; not a proxy/network artifact).
- `TELEGRAM_ALLOWED_USERS` / `TELEGRAM_HOME_CHANNEL`: 9-digit numeric
  (plausible chat IDs). Only the bot-token half is broken.

## Summary payload (built correctly, never transmitted)

```
📊 Rebel Status Summary
DI: 1.5 | Stake: None | SPW: None
PF: 0.28 | WR: 0.349 | Trades: 43
Neue Proposals: 0 | offene Stage0: 2
Letzte Events:
- patch_success / success / rollback=False
- patch_failed_rollback / error / rollback=True
- patch_failed_rollback / error / rollback=True
Empfehlung: scale_pos_weight Proposal prüfen — benötigt neuen Identifier + Retrain.
Zeit: 2026-06-18T12:45:25.239068+00:00
```

## Why not fixed here

Bot-token correctness is a credential matter -> L3. Per SOUL rules 3 & 9 and
AGENTS.md safety rules, credentials must not be inspected for values, rotated,
or modified without explicit human approval. Escalated, not auto-remediated.

## Remediation still required (unchanged from 20260617)

1. Provision a VALID `TELEGRAM_BOT_TOKEN` (`<digits>:<35+ alnum>`) to the
   `hermes-green` container env, or set `TELEGRAM_BOT_TOKEN` /
   `TELEGRAM_BOT_TOKEN_B64` in the cron runtime environment. (Not yet done.)
2. Optional hardening: shape-check in
   `drawdown_guard._get_telegram_creds()` so malformed tokens fail fast.
3. Optional: put `orchestrator/scripts` on sys.path/PYTHONPATH for the cron
   command so `fleet_api_client` resolves.
4. After (1), re-run `send_rebel_status_summary(force=True)` to deliver.

## No side effects

- No configs modified. No new cron jobs created.
- No containers restarted or recreated. No secrets printed/copied/persisted.
- Only length/shape diagnostics recorded.
