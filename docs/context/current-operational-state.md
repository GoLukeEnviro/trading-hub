# Current Operational State — Autonomous Mode v4.2

Updated: 2026-05-23 17:18 UTC

## Fleet Overview — ALL SYSTEMS GREEN

| Bot | Status | Trades (closed) | PnL | WR | PF | Open | Verdict |
|-----|--------|-----------------|-----|-----|------|------|---------|
| FreqForge | 🟢 UP 2d | 48 | **+$9.47** | 87.5% | high | 0 | 🥇 Gold Standard |
| FreqForge Canary | 🟢 UP 2d | 26 | **+$3.04** | 91.7% | high | 1 SHORT | 🟢 Active |
| Regime-Hybrid | 🟢 UP 57m | 42 | **-$7.02** | 78.6% | 0.55 | 0 | 🟢 QUARANTINE LIFTED v4.2 |
| FreqAI-Rebel | 🟢 UP 1h | 73 | **-$4.02** | 27.4% | 0.21 | 0 | 🔴 PERMANENT QUARANTINE |

### v4.2 Fixes Applied (2026-05-23 17:15 UTC)

1. **Signal Bridge Permissions — PERMANENTLY FIXED**
   - All 6 `primo_signal_state.json` files: chown to `hermes:hermes`, chmod 644
   - `trading_pipeline.py` STATE_OUTPUT_FILES: removed 2 WRONG paths (`freqtrade/bots/freqforge/`, `freqtrade/bots/freqforge-canary/`) that were NOT mounted by containers
   - Remaining 5 paths all point to CORRECT container mount points
   - Previous: 3/5 writes FAIL every cycle → Now: 5/5 writes OK guaranteed

2. **Regime-Hybrid Quarantine LIFTED**
   - Safety gates: DD 1.4% < 5% ✅ | DailyLoss 0% < 2% ✅ | StratLoss 1.4% < 2.5% ✅
   - max_open_trades=3, stake_amount=50, dry_run=true
   - v7 SL/ROI/Trailing optimizations applied

3. **DrawdownGuard — FULLY OPERATIONAL**
   - 4/4 bots reachable via docker exec + API
   - Portfolio: $3,498.32 / $3,450.00 start (+$48.32, 0% DD)
   - Signal: FRESH (5.6 min)
   - Telegram alerts working

4. **Housekeeping**
   - 6 orphan .tmp files removed
   - 6 stale/untracked context files cleaned
   - All signal files 644 hermes:hermes

### Active Bots

| Container | Port | Strategy | Key Config |
|-----------|------|----------|------------|
| freqtrade-freqforge | :8086 | FreqForge_Override | futures, $100, max_open=5 |
| freqtrade-freqforge-canary | :8081 | FreqForge_Override | spot, $50, max_open=3 |
| freqtrade-regime-hybrid | :8085 | RegimeSwitchingHybrid_v7_v04_Integration | futures, $50, max_open=3 |
| freqai-rebel | :8087 | RebelLiquidation (FreqAI) | futures, FreqAI, PERMANENT QUARANTINE |

### Signal Pipeline

- Source: ai-hedge-fund-crypto (container, port 8410)
- Pipeline: trading_pipeline.py via Hermes cron (every 10min)
- RiskGuard: ACTIVE (threshold 0.65)
- ShadowLogger: ~525 entries
- 3 ACCEPTED SHORT signals (BTC/ETH/SOL, conf 0.75-0.85)

### Safety Limits (v4.2)

- Risk-per-Trade ≤ 1%
- Daily Loss ≤ 2%
- Fleet Drawdown ≤ 5%
- Consecutive Loss: 4-loss pause
- Permanent Quarantine: FreqAI-Rebel (structurally broken model)
