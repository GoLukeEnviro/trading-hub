# Mem0 Recovery Top 25 Review

**Date:** 2026-05-17
**Status:** PROPOSED — NO IMPORT EXECUTED — WAITING FOR "GO import top25"

## Why 212 CRITICAL Was Too Many

212 items contained heavy redundancy:
- 15+ Fleet listing variants (RSI/Momentum/Regime-Hybrid/FreqForge with port numbers)
- 10+ Infrastructure variants (Tailscale/Caddy/Docker)
- 8+ Dry-run safety variants
- Many were same fact with slightly different wording

## Selection Method

1. All 212 candidates loaded
2. Checked against existing Mem0 memories (100) — 0 duplicates found
3. Grouped by topic (92 unique topics)
4. Picked best (longest/most specific) per topic
5. Merged near-duplicates within same topic
6. Final 25 cover 25 distinct topics

## Top 25 Import Candidates

| # | Topic | Memory Text (preview) |
|---|-------|-----------------------|
| 1 | Signal Bridge | signal_bridge.py deployed: ai-hedge-fund-crypto → 3x primo_signal_state.json |
| 2 | GAP Report | Signal Chain fully broken — ai-hedge-fund-crypto → RiskGuard/ShadowLogger |
| 3 | Infrastructure | Tailscale Funnel (443) → Caddy (3000) → Docker containers on ki-fabrik |
| 4 | Fleet Overview | RSI (8081), Momentum (8084), Regime-Hybrid (8085), FreqForge (8086) |
| 5 | Dry-run Deploy | freqtrade-fomo-phase3, ki-fabrik, 127.0.0.1:8087, dry_run=true |
| 6 | Roadmap | fomo-phase3-master-implementation-roadmap.md |
| 7 | FreqForge Log | freqforge_shadow.log path — file did not exist yet |
| 8 | FreqForge Container | Utility container freqtrade-freqforge |
| 9 | FreqForge Events | Required fields per event: timestamp, bot, pair, side, price... |
| 10 | Security | Docker socket mounts, exposed ports, no internet access |
| 11 | Twister Lab | /home/hermes/twister-lab/, virtual 1000 USDT |
| 12 | Roadmap Path | fomo-phase3 docs/context path |
| 13 | Risk Management | Max DD <15%, confidence >= 0.60 |
| 14 | Deterministic | RiskGuard must be deterministic, fail-open design |
| 15 | Backtest Phases | Lab → walk-forward → Optuna/WFO → integration |
| 16 | Protections | CooldownPeriod, StoplossGuard, MaxDrawdown, LowProfitPairs |
| 17 | Custom Exit | ExitAgent + custom_exit hook for Freqtrade |
| 18 | Data Storage | user_data directory in freqtrade-regime-hybrid container |
| 19 | Exchange | Bitget, :USDT pairs only |
| 20 | Docker Compose | Hermes, Primo, Freqtrade services |
| 21 | Signal Stack | ai-hedge-fund-crypto → output/hermes_signals |
| 22 | Goal | Safer, more robust Freqtrade dry-run fleet architecture |
| 23 | Dry-run Status | All active bots in dry-run, no real funds at risk |
| 24 | RiskGuard Files | Allowed to create/update RiskGuard/ShadowLogger if missing |
| 25 | RiskGuard Role | Primary safety source before Freqtrade bridge decisions |

## Stats

| Metric | Value |
|--------|-------|
| Original CRITICAL | 212 |
| Existing Mem0 duplicates | 0 |
| Internal dedup merges | ~100 |
| Final Top 25 | 25 unique topics |
| Deferred | 187 |

## Import Proposal

When Luke says **"GO import top25"**, each memory will be written via:
```
POST https://api.mem0.ai/v1/memories/
{"messages": [{"role": "user", "content": "<cleaned_memory_text>"}], "user_id": "luke-hermes", "agent_id": "hermes"}
```

## Files

- `docs/context/mem0-recovery-top25-import-candidates-20260517.json` — Full JSON with all 25 items
- `docs/context/mem0-recovery-top25-review-20260517.md` — This review
