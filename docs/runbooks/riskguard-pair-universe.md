# Runbook: RiskGuard Pair Universe

## Overview

The RiskGuard pair universe is a tracked JSON config file that defines the sanctioned set of trading pairs for RiskGuard evaluation, reporting, and dashboard display.

RiskGuard itself does NOT filter pairs — it evaluates all pairs present in the AI signal file. The pair universe config provides:
- Validation of which pairs are sanctioned
- Reporting of universe count and verdict counts
- Dashboard display of active vs. watchlist pairs
- Fail-closed fallback to safe baseline if config is missing/invalid

## Config File Location

```
orchestrator/config/riskguard-pair-universe.json
```

Example config:
```
orchestrator/config/riskguard-pair-universe.example.json
```

## Config Schema

```json
{
  "schema_version": "1.0",
  "description": "RiskGuard pair universe config",
  "active_universe": ["BTC/USDT:USDT", "ETH/USDT:USDT", ...],
  "watchlist": ["SUI/USDT:USDT", ...],
  "blacklist": ["UST/USDT:USDT", "LUNA/USDT:USDT", ...],
  "max_active_pairs": 10,
  "exchange": "bitget",
  "settle": "USDT",
  "pair_format_regex": "^[A-Z]+/USDT:USDT$"
}
```

## Safety Properties

1. **Fail-closed**: If config is missing, corrupt, or has empty active_universe after validation → falls back to safe BTC/ETH/SOL baseline with explicit warning.
2. **Stablecoin rejection**: Pairs with stablecoin bases (USDC, DAI, UST, LUNA, LUNC, TUSD, FRAX, BUSD) are automatically rejected from active_universe and watchlist.
3. **Blacklist enforcement**: Pairs in `blacklist` are rejected from `active_universe` and `watchlist`.
4. **Format validation**: All pairs must match `pair_format_regex` (default: `^[A-Z]+/USDT:USDT$`).
5. **Max cap**: `max_active_pairs` truncates excess entries with a warning.
6. **Deduplication**: Duplicate pairs within a list are removed.
7. **Watchlist dedup**: Pairs in watchlist that are also in active_universe are removed from watchlist.

## How to Modify the Pair Universe

### Step 1: Edit the config file

```bash
# Always create a snapshot first
cp orchestrator/config/riskguard-pair-universe.json \
   orchestrator/config/riskguard-pair-universe.json.bak-$(date +%Y%m%d_%H%M%S)

# Edit the config
# Add pairs to active_universe or watchlist
# Ensure pairs are available on Bitget futures
# Ensure no stablecoin pairs in active_universe or watchlist
```

### Step 2: Validate

```bash
cd /home/hermes/projects/trading
python3 -c "
import sys; sys.path.insert(0, 'orchestrator/scripts')
from pair_universe import load_pair_universe
u = load_pair_universe()
print(f'Active: {u.active_count} pairs: {u.active_pairs}')
print(f'Watchlist: {u.watchlist_count} pairs: {u.watchlist}')
print(f'Blacklist: {u.blacklist}')
print(f'Source: {u.source}')
if u.warnings:
    print(f'Warnings: {u.warnings}')
"
```

### Step 3: Run tests

```bash
cd /home/hermes/projects/trading
python3 -m pytest tests/test_pair_universe.py -v
```

### Step 4: Open PR

The config file is tracked in git. Changes should go through a PR with validation.

## Important Notes

- RiskGuard evaluates ALL pairs from the AI signal file, not just the sanctioned universe.
- The universe config is for validation, reporting, and dashboard display.
- The signal generator (`ai-hedge-fund-crypto`) now loads active pairs from this config via `sentiment_collector.py` and `portfolio_management_node.py`. If config is missing, it falls back to BTC/ETH/SOL.
- `ai-hedge-fund-crypto/config.yaml` tickers should be kept aligned with the active universe.
- To change which pairs Freqtrade canary scans, you need to modify `freqforge-canary/config/config_canary_dryrun.json` (L3 runtime config).
- The pair universe config does NOT affect live trading — it is read-only metadata.