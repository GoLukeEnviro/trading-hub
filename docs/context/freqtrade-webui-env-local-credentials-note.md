# Freqtrade WebUI Local Credentials ENV

Status: Rebuilt and verified. Git-ignored, permission-hardened.

Path: `/home/hermes/projects/trading/.env.freqtrade-webui.local`

Purpose:
- Stores local WebUI and bot API credentials for operational login/use.
- Must never be committed.

Active Bots (all verified: ping + auth):
- WebUI (freqtrade-webserver) — AUTH_PASS
- Regime Hybrid (freqtrade-regime-hybrid) — AUTH_PASS
- Momentum (freqtrade-momentum) — AUTH_PASS
- FreqForge Canary (freqtrade-freqforge-canary) — AUTH_PASS
- FreqAI Rebel (freqai-rebel) — AUTH_PASS

Inactive Bots (TODO only):
- RSI — not running, port conflict with Canary (both 8081)
- Fomo Phase 3 — not running, placeholder password
- MVS — not running, empty credentials, port conflict

Notes:
- Canary password rotation is recommended (appeared in prior chat/log context).
- No JWT secrets, WS tokens, or exchange credentials are stored.
- WebUI accessible via Tailscale: https://agent0.taile6801f.ts.net:9092
- Port 8092 localhost mapping has iptables issue — Tailscale routing works, direct 127.0.0.1:8092 does not.
