# Credential Rotation Checklist

**Date:** 2026-06-15
**Issue:** #243
**Status:** Template — execute manually outside the repository.

> **Hard rule:** Do not print old or new credentials in logs, PR comments, issues, or chat.
> Do not commit rotated values to the repository. Runtime configs are gitignored.

## Prerequisites

- [ ] Confirm all bots are in `dry_run=true` mode before any rotation step.
- [ ] Confirm local runtime configs exist and are gitignored (`.gitignore` covers them).
- [ ] Have your local secret manager / vault accessible.
- [ ] Plan a downtime window if bot restart is required for credential reload.

## 1. Freqtrade WebUI / API Passwords

Affected bots (check config files under `freqtrade/bots/*/config/config*.json`):

| Bot | Config path | Has password? | Rotated? |
|-----|-------------|---------------|----------|
| Regime-Hybrid | `.../config_regime_hybrid_dryrun.json` | Yes — `api_server.password` | ☐ |
| FreqForge | `freqforge/config/config_freqforge_dryrun.json` | Yes | ☐ |
| FreqForge-Canary | `freqforge-canary/config/config_canary_dryrun.json` | Yes | ☐ |
| RSI | `.../rsi/config/config.json` | Yes | ☐ |
| Momentum | `.../momentum/config/config.json` | Yes | ☐ |
| MVS | `.../mvs/config/config.json` | Yes (empty `""`) | ☐ |

Procedure:
1. Generate new random password (e.g. `openssl rand -base64 32`).
2. Update the runtime config file `api_server.password` field.
3. Do NOT commit this change (config file is gitignored).

## 2. JWT Signing Secrets

Affected bots:

| Bot | Has `jwt_secret_key`? | Rotated? |
|-----|----------------------|----------|
| Regime-Hybrid | Yes | ☐ |
| FreqForge | Yes | ☐ |
| FreqForge-Canary | Yes | ☐ |
| RSI | Yes | ☐ |
| Momentum | Yes | ☐ |
| MVS | Yes | ☐ |

Procedure:
1. Generate a new JWT signing value with: `openssl rand -hex 32`.
2. Replace `jwt_secret_key` value in the local runtime config.
3. Restart the bot (Docker container restart) for the new key to take effect.
4. Verify the bot's REST API responds with 200 on health endpoint after restart.

## 3. Exchange API Keys / Secrets

**Critical:** If any exchange key was ever inlined (not `${ENV_VAR}`) in a tracked config:

Affected configs:
- Data on exchange being used (Bitget for dry-run): verify that `exchange.key` and `exchange.secret` use `${ENV_VAR}` indirection.

Procedure:
1. If keys use env-var indirection, rotate the env-var values in the host environment (`.env` files).
2. If keys were ever inlined in a tracked file, **treat the key pair as compromised and rotate at the exchange level**.
3. Do not commit any new keys.
4. Verify: bot can still start and report dry-run status without authentication errors.

## 4. Telegram Bot Tokens

Affected bots:

| Bot | Has Telegram token? | Rotated? |
|-----|-------------------|----------|
| Regime-Hybrid | Yes (in config) | ☐ |
| Others | Check per config | ☐ |

Procedure:
1. Revoke existing Telegram bot token via [@BotFather](https://t.me/BotFather).
2. Generate new token.
3. Update the runtime config's `telegram.token` field.
4. Restart the bot for the new token to take effect.
5. Verify: bot sends a test notification.

## 5. Environment Variables (`.env` files)

All `.env*` files are gitignored, but their values may have been leaked elsewhere. These are typically loaded into Docker containers or the host environment.

Check these paths:
- `./.env`
- `./.env.freqtrade`
- `orchestrator/.env`
- `freqforge/.env`

If any `.env` contains credentials that were historically in tracked config files, rotate them.

Procedure:
1. Identify all keys in `.env*` files that contain credential values.
2. For each key, generate a new value.
3. Update the `.env*` file (stay gitignored).
4. Notify the runtime environment (container restart or source).
5. Verify operation.

## 6. Post-Rotation Verification

Run these checks after all rotations:

```bash
# Secret scan must pass on the tracked tree
python3 scripts/secret_scan.py --tracked

# Verify no credentials leaked to tracked files
git diff --stat

# Verify all bot APIs respond (HTTP 200)
# Example for Regime-Hybrid:
curl -s -o /dev/null -w "%{http_code}" http://localhost:8085/api/v1/ping

# Verify dry-run flag is still set
# Example: check api_version in each config has dry_run=true
```

## Confirmation

- [ ] All WebUI passwords rotated
- [ ] All JWT secrets rotated
- [ ] Exchange API keys rotated if inlined in history
- [ ] Telegram tokens rotated if in history
- [ ] `.env` secrets rotated
- [ ] Post-rotation verification passed
- [ ] Secret scan passes (`python3 scripts/secret_scan.py --tracked`)
- [ ] No new credentials committed
