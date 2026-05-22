# Freqtrade WebUI Credentials Setup

## ENV File
Path: `/home/hermes/projects/trading/.env.freqtrade-webui.local`

This file contains WebUI login and per-bot API credentials for local operational use.

## Variable Naming Convention
- `FREQTRADE_WEBUI_*` — Main WebUI login (orphan freqtrade-webserver)
- `FREQTRADE_<BOT>_HOST` — Bot API host (127.0.0.1 for all)
- `FREQTRADE_<BOT>_PORT` — Bot API port
- `FREQTRADE_<BOT>_USER` — Bot API username
- `FREQTRADE_<BOT>_PASS` — Bot API password

## Bots Included
- regime (Regime Hybrid, port 8085)
- momentum (Momentum, Docker host port 8084->internal 8082)
- canary (FreqForge Canary, port 8081)
- rsi (RSI, port 8081 — currently STOPPED)
- fomo (Fomo Phase 3, port 8087 — currently STOPPED, placeholder password)
- mvs (MVS, port 8087 — currently STOPPED, no credentials)
- rebel (FreqAI Rebel, Docker host port 8087->internal 8080)

## Known Issues
- MVS: No username/password set — needs credentials before WebUI use
- Fomo Phase 3: Placeholder password (`CHANGE_ME_BEFORE_LIVE`) — replace before use
- RSI: Currently stopped, port 8081 conflicts with Canary when both running

## Safety
- File is git-ignored (both `.env.*` wildcard and explicit entry)
- File permissions: 600
- Never commit this file
