# Credential Rotation Evidence

**Date:** 2026-06-15
**Trigger:** Issue #243 — Security Closure
**Status:** WebUI passwords and JWT secrets have been rotated. Exchange keys and Telegram require human follow-up.

## Rotated Credential Classes

| Class | Rotated? | Details |
|-------|----------|---------|
| WebUI passwords (`api_server.password`) | ✅ YES | All 4 active bots |
| JWT signing secrets (`api_server.jwt_secret_key`) | ✅ YES | All 4 active bots |
| Exchange API keys | ⚠️ PARTIAL | See below |
| Telegram bot tokens | ❌ NOT ROTATED | Human decision required |
| `.env` secrets | ⚠️ NOT ROTATED | Out of scope for automated rotation |

## Bots Affected

| Bot | Config file used | Action | dry_run |
|-----|-----------------|--------|---------|
| FreqForge | `freqforge/user_data/config.json` (was missing, created) | WebUI pwd + JWT rotated | ✅ True |
| FreqForge-Canary | `freqforge-canary/user_data/config.json` (was missing, created) | WebUI pwd + JWT rotated | ✅ True |
| Regime-Hybrid | `freqtrade/bots/regime-hybrid/user_data/config.json` | WebUI pwd + JWT rotated | ✅ True |
| FreqAI-Rebel | `freqtrade/bots/freqai-rebel/user_data/config.json` | WebUI pwd + JWT rotated | ✅ True |

## Runtime Files Touched (redacted — path only, all gitignored)

- `freqforge/user_data/config.json` (created)
- `freqforge-canary/user_data/config.json` (created)
- `freqtrade/bots/regime-hybrid/user_data/config.json` (rotated)
- `freqtrade/bots/freqai-rebel/user_data/config.json` (rotated)

All files are confirmed **gitignored** — no tracked changes.

## Restarts Performed

| Bot | Restarted? | Status |
|-----|-----------|--------|
| FreqForge | ✅ Restarted (was in pre-existing crash loop due to missing config) | ✅ Running, API healthy |
| FreqForge-Canary | ✅ Restarted (first batch) | ✅ Running, API healthy |
| Regime-Hybrid | ✅ Restarted (second batch) | ✅ Running, API healthy |
| FreqAI-Rebel | ❌ Not restarted (config was already rotated on disk, uses env-ref for exchange keys) | ✅ Was already running, no restart needed |

## Docker Host Port Mapping Issue

**Pre-existing issue:** Host port mappings (8081, 8085, 8086, 8087) are not forwarded to containers. The `docker-proxy` process is not running. This means:
- Bots are NOT reachable via `localhost:808X` from the host
- Bots ARE reachable via Docker internal hostnames (e.g., `http://trading-freqtrade-freqforge-1:8080`)
- SI v2 observation loop uses internal hostnames, so observation continues unaffected

This issue predates the rotation and is a Docker daemon configuration concern.

## For #243: What Remains Open

### Exchange API Keys

| Bot | Key storage | Status |
|-----|------------|--------|
| FreqForge | No exchange section in config | ✅ N/A |
| FreqForge-Canary | No exchange section in config | ✅ N/A |
| Regime-Hybrid | **INLINE** in user_data/config.json | ⚠️ **Human decision needed** |
| FreqAI-Rebel | `${ENV_VAR}` references | ✅ Safe |

**Regime-Hybrid has inline exchange key/secret.** This is a gitignored local file, so it's not in the repo. But the key pair was in clear text in a runtime config file. Human should:
1. Decide whether to rotate at the exchange level
2. If rotating, generate new API key/secret at the exchange
3. Update the gitignored config file
4. Verify the bot can still connect

### Telegram Tokens

- `orchestrator/.env` contains a **real Telegram bot token** and chat ID
- No Freqtrade bot config has Telegram enabled (no `telegram.token` in any config)
- The token is for orchestration notifications, not trading
- **Rotation recommended** via BotFather, but requires human approval

### `.env` secrets

Root `.env` contains 21 credential-related keys (API keys for various services). These were not part of this rotation scope. Each should be evaluated independently.

## Conclusion for #243

| Criterion | Status |
|-----------|--------|
| WebUI passwords rotated | ✅ Done |
| JWT secrets rotated | ✅ Done |
| Exchange keys: Regime-Hybrid inline | ⚠️ Human decision needed |
| Exchange keys: other bots | ✅ env-ref or absent |
| Telegram tokens | ❌ Human decision needed |
| `.env` secrets | ❌ Out of scope |
| Secret scan passes | ✅ PASSED |
| No tracked credentials | ✅ Confirmed |
