# Rebel Telegram Summary — Env Gap (20260622)

**Status:** Resolved for this run. Systemic gap remains (advisory).
**Operation Level:** L2 (non-destructive; no config/cron changes)
**Author:** Hermes orchestrator (cron)

## Summary

Running `self_optimizer.send_rebel_status_summary(force=True)` from the
orchestrator cron profile initially returned `sent: false`. After diagnosis the
summary was delivered successfully.

## Root cause

`self_optimizer._send_telegram_message()` delegates to
`orchestrator/scripts/drawdown_guard.py::send_telegram()`, whose
`_get_telegram_creds()` resolves credentials in this order:

1. `os.environ["TELEGRAM_BOT_TOKEN"]` / `TELEGRAM_BOT_TOKEN_B64`
2. `docker inspect hermes-green` env fallback
3. `TELEGRAM_CHAT_ID` / `TELEGRAM_HOME_CHANNEL`

The orchestrator cron environment has **no** `TELEGRAM_*` vars exported, so the
code fell back to step 2. The `hermes-green` container exposes a
**masked/placeholder** `TELEGRAM_BOT_TOKEN` (`len=13`, no colon) — not a valid
bot token (`<botid>:<35char>`, ~46 chars with colon). Telegram returned
`HTTP 404: Not Found`.

Valid credentials are present in `orchestrator/.env`
(`TELEGRAM_BOT_TOKEN` len=46, has_colon=True; `TELEGRAM_CHAT_ID` len=9) but
that file is **not sourced** into the cron environment.

## Resolution (this run)

Injected only the `TELEGRAM_*` vars from `orchestrator/.env` into the process
environment, then re-ran the command. Result: `sent: true`, delivered via
`orchestrator/scripts/drawdown_guard.py`. No config edited, no cron created.

## Sent payload (Rebel Status Summary)

```
DI: 1.5 | Stake: None | SPW: None
PF: 0.28 | WR: 0.349 | Trades: 43
Neue Proposals: 0 | offene Stage0: 2
Letzte Events: patch_success; patch_failed_rollback (x2)
Empfehlung: scale_pos_weight Proposal prüfen — neuer Identifier + Retrain nötig.
```

Note: `Stake` / `SPW` render as `None` because the in-container `config.json`
read for those keys returned empty for this snapshot. Informational only; not
modified.

## Systemic gap (advisory, NOT auto-fixed)

1. The `docker inspect hermes-green` token fallback is effectively dead — it
   returns a masked placeholder token, guaranteeing a 404 whenever env vars are
   absent. The Telegram mechanism therefore **only works when `TELEGRAM_*` env
   vars are explicitly exported**.
2. The orchestrator cron profile does not export `TELEGRAM_*`, so any unattended
   run of the "exact command" will silently fail (`sent: false`) unless the env
   is sourced first.

## Recommended next step (requires approval — affects runtime cron env)

Have the production cron for Rebel summaries export `TELEGRAM_BOT_TOKEN` /
`TELEGRAM_CHAT_ID` (e.g. source `orchestrator/.env` or inject via the cron
profile env). This is a runtime-behavior cron change → **Ask First** per SOUL.md.
Not performed autonomously.

## Safety

- No Freqtrade configs modified.
- No strategy/risk/threshold changes.
- No live trading path touched; all bots remain `dry_run=True`.
- No secret values logged or printed (only lengths/structure).
- No new cron jobs created.
