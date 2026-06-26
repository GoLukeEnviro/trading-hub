# Rebel Status Summary Telegram Send — BLOCKED (20260617)

**Operation Level:** L0 inspection / L2 diagnostic artifact
**Decision:** WARNING -> ESCALATED (credential remediation required)
**Status:** Telegram send NOT delivered

## What was attempted

Scheduled cron task: send Rebel FreqAI status summary via the existing
`self_optimizer.send_rebel_status_summary()` Telegram mechanism.

Exact command run (verbatim) from `/home/hermes/projects/trading`:

    import self_optimizer as so
    res = so.send_rebel_status_summary(force=True)

(with `freqtrade/bots/regime-hybrid/config/research/automation` on sys.path)

## Outcome

`sent: false`. Two distinct blockers found, in sequence.

## Blocker 1 — import path gap (exact command, runtime-only)

The command as written inserts only the `automation` directory onto
`sys.path`. `self_optimizer.build_rebel_status_summary()` imports
`fleet_api_client`, which lives at a DIFFERENT path:

- present: `orchestrator/scripts/fleet_api_client.py`
- not on sys.path in this cron shell

Result (verbatim exact command): `reason = "No module named 'fleet_api_client'"`.

This is an invocation/path gap, not a logic defect. It resolves at runtime
by adding `orchestrator/scripts` to `sys.path`. **No config or cron was
modified** to confirm this — runtime-only sys.path insert, non-persistent.

## Blocker 2 — malformed Telegram bot token in `hermes-green` (HARD blocker)

With the import path resolved, `build_rebel_status_summary()` succeeds and
produces a valid 404-char summary. The send then fails with
`HTTP Error 404: Not Found`.

Call chain:
`self_optimizer._send_telegram_message`
-> `orchestrator/scripts/drawdown_guard.send_telegram`
-> `POST https://api.telegram.org/bot{token}/sendMessage`

### Evidence (structural only — no secret values recorded)

- Network to `api.telegram.org`: REACHABLE (probe `getMe` returns 401 for a
  dummy token, proving DNS/TLS/connectivity are fine). The 404 is therefore
  credential-specific, not a network problem.
- In this cron process the `TELEGRAM_*` env vars are **absent**; creds are
  resolved via the Docker fallback (`docker inspect hermes-green .Config.Env`).
- `hermes-green` container env var `TELEGRAM_BOT_TOKEN`: **malformed**.
  - length 13
  - contains NO colon
  - does NOT match the canonical Telegram bot-token shape
    (real tokens are ~45-46 chars, always with a colon separating bot-id from
    hash)
  - Telegram returns HTTP 404 ("Not Found") specifically when the token does
    not correspond to a registered bot.
- `TELEGRAM_ALLOWED_USERS` / `TELEGRAM_HOME_CHANNEL` in `hermes-green`:
  9-digit numeric values (plausible chat IDs) — the chat-id half resolves; only
  the bot-token half is broken.

The 13-char value looks truncated/corrupted/placeholder rather than a real token.

## Why not fixed here

Bot-token correctness is a **credential** matter -> L3. Per SOUL rules 3 & 9
and AGENTS.md safety rules, credentials must not be inspected for values,
rotated, or modified without explicit human approval. This is escalated, not
auto-remediated.

## Remediation (requires human / credential owner)

1. Provision a valid `TELEGRAM_BOT_TOKEN` (full `<digits>:<35+ alnum/hyphen/underscore>`) to
   the `hermes-green` container env (or set `TELEGRAM_BOT_TOKEN` /
   `TELEGRAM_BOT_TOKEN_B64` in the cron runtime environment). Do not truncate.
2. Optional hardening: add a shape-check in
   `drawdown_guard._get_telegram_creds()` so a malformed token fails fast
   with a clear reason instead of a remote 404.
3. Optional: ensure the exact cron command also places
   `orchestrator/scripts` on `sys.path` (or set `PYTHONPATH`) so
   `fleet_api_client` resolves without the manual insert.
4. After (1), re-run `send_rebel_status_summary(force=True)` to deliver the
   summary (the summary payload itself builds correctly).

## No side effects

- No configs modified.
- No new cron jobs created.
- No containers restarted or recreated.
- No secrets printed, persisted, or copied — only length/shape diagnostics.
- The summary message was composed but never transmitted.
