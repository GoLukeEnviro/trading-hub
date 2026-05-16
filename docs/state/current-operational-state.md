# Operational State — Trading Hub

**Last updated:** 2026-05-16 06:26 UTC
**Update trigger:** Stack stabilization run
**Author:** Hermes Agent (deepseek-v4-pro via Ollama Cloud)

---

## 1. Active Containers (Fleet)

| Container | Status | Uptime | Port | Trading Mode | Dry-Run |
|-----------|--------|--------|------|-------------|---------|
| freqtrade-freqforge | Running | 5 days | 8086 | Futures (isolated) | YES |
| freqtrade-regime-hybrid | Running | 4 days | 8085 | Futures | YES |
| freqtrade-momentum | Running | 4 days | 8084 | — | YES |
| freqtrade-freqforge-canary | Running | 6 hours | 8081 | Spot | YES |
| freqai-rebel | Running | 3 hours | 8087 | Futures (isolated) | YES |
| ai-hedge-fund-crypto | Running (healthy) | 4 days | 8410→8080 | Signal only | N/A |

## 2. Stable Bots

### FreqForge (8086) — Gold Standard
- Strategy: FreqForge (signal-independent)
- Pairs: BTC, ETH, SOL, AVAX, NEAR, ARB, OP
- Stake: 100 USDT, max 5 open
- WR: 100% (15/15), PnL: +$12.41
- 3 open longs: SOL (89.5h), AVAX (22.5h), BTC (20.2h)
- All exits via ROI — no stop losses triggered

### FreqForge Canary (8081) — Fresh Clone
- Strategy: FreqForge clone (exact copy)
- Pairs: LINK, DOT, ATOM, UNI, AAVE (non-overlapping with source)
- Stake: 50 USDT, max 3 open
- Spot mode (not futures — matches source bot)
- Deployed: ~6h ago, still warming up, 0 trades
- Normal for new bot — evaluating entries

### Regime-Hybrid (8085)
- Strategy: RegimeSwitchingHybrid_v2 (signal-independent)
- WR: 76.9% (30/39 closed), PnL: -$7.37
- Loss asymmetry: avg_win +$0.28, avg_loss -$1.74 (1:6.3)
- Stop-loss (2x): -$6.13, trailing_stop_loss (8x): -$3.73
- Only ROI exits (24x) are profitable: +$4.98
- Open trades: 0

## 3. Experiments

### FreqAI-rebel (8087) — t0005 Patch
- **What changed:** DI_threshold 0.9→0.4, label threshold 1.002→1.0005, identifier t002→t0005
- **Applied:** 2026-05-16 03:10 UTC
- **Status:** Training runs massively improved — logloss 0.18 (was 0.000 overfitted), DI tossed 2146 (was 3)
- **Pending:** First inference cycles just started. Need to observe for 24h.
- **Backup:** /home/hermes/backups/freqai-rebel/20260516-030836/
- **Rollback plan:** Restore config.json + RebelLiquidation.py from backup, restart
- **Decision due:** 2026-05-17 03:10 UTC — if 0 trades → build Perzentil-Labels v2

## 4. Zombie / Decommissioned

### Momentum (8084) — ZOMBIE
- Container runs, heartbeats, consumes CPU
- **0 new trades** since PrimoAgent decommission
- Root cause: depends on `primo_signal_state.json` via `primo_gate_allows()`
- PrimoAgent pipeline is fully decommissioned → state files are stale
- ALL pairs show `allow_long_bias: false, allow_short_bias: false`
- Decision: read-only audit pending → replace or make signal-independent

### RSI (Exited)
- Container: freqtrade-rsi, Exited (130), 6h ago
- Replaced by FreqForge Canary
- Container NOT removed (only stopped)
- Config preserved at /freqtrade/config/freqtrade_final.json (inside named volume)

### Honcho (FULLY DECOMMISSIONED)
- Containers removed, networks removed, volume archived
- Two zombie cronjobs still active (see Section 6)
- DB: only archive copy exists

## 5. Signal Stack

| Layer | Component | Status |
|-------|-----------|--------|
| Generator | ai-hedge-fund-crypto | Active, deepseek-v4-pro, every 30min |
| Heartbeat | Hermes cron (87594bf612b9) | Every 30min, no_agent=true |
| Output | hermes_signal.json | Fresh — 16 min age |
| Bridge | hermes_primo_bridge.py | EXISTS but NOT wired to any bot |
| ShadowLogger | freqforge_shadow.py | Active, polling |
| Signal state files | primo_signal_state.json per bot | STALE — PrimoAgent decommissioned |
| Active usage | None of the running bots consume signals | Architectural gap |

**Signal details:**
- Source: ai-hedge-fund-crypto
- Model: deepseek-v4-pro @ temp 0.15
- Pairs: BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT
- Risk mode: neutral (consistent)
- Confidence: 0.22-0.25 (all pairs hold)
- Exchange: Bitget Futures

## 6. Cron Jobs

| Name | Schedule | Status | Deliver | Note |
|------|----------|--------|---------|------|
| ai-hedge-signal-heartbeat | every 30m | OK | local | Signal generation trigger |
| freqtrade-4h-fleet-snapshot | every 4h | OK | origin (Telegram) | Fleet status to Luke |
| trading-fleet-signal-audit | every 60m | OK | origin (Telegram) | Signal quality (qwen3.5:397b) |
| freqtrade-daily-report | 07:00 daily | OK | origin (Telegram) | Daily summary |
| honcho-weekly-dedupe | Mo 03:00 | ZOMBIE | origin | Honcho decommissioned — TO REMOVE |
| honcho-memory-quality-guard | 06:00/18:00 | ZOMBIE | origin | Honcho decommissioned — TO REMOVE |

## 7. Known Issues

### Structural
- **Momentum signal dependency** — Bot is zombie, no path to recovery without rebuild
- **Signal-to-bot bridge missing** — ai-hedge-fund-crypto produces signals, no bot consumes them
- **RSI container not cleaned** — Exited but not removed

### Performance
- **Regime-Hybrid loss asymmetry** — Stop-loss losses (2x$6.13) far exceed avg wins ($0.28)
- **FreqAI-rebel untested** — Patch applied but results unknown for 24h

### Process
- **No operational state file prior to this one** — Fleet blind without documentation
- **Git uncommitted changes** — Several modified files without version anchor
- **2 Honcho cronjobs still alive** — Decommissioned component has zombie automation

## 8. No-Touch Rules (Active)

- Do NOT modify FreqForge strategy or config
- Do NOT modify FreqForge Canary strategy or config
- Do NOT restart trading bots without explicit approval
- Do NOT change dry_run mode
- Do NOT add exchange credentials
- Do NOT place real orders
- Read-only audits first, patches only after approval

## 9. Next Decisions Pending

| Decision | Due | Options |
|----------|-----|---------|
| FreqAI-rebel keep or rebuild | 2026-05-17 | Keep if trades > 0; rebuild v2 if 0 |
| Momentum: fix or replace | After audit | A) signal-independent, B) replace, C) decommission |
| RSI cleanup | After audit | Remove container or archive fully |
| Signal bridge wiring | After Momentum decision | Which bot (if any) should consume signals |
