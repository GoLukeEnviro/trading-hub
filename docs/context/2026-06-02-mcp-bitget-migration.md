# MCP Server Migration: bitget-paper -> bitget-mcp-server (official)

Date: 2026-06-02
Status: COMPLETED

## What Changed

Replaced the custom Python `bitget_mcp_server.py` (v1.1, 6 tools, ccxt-based paper-trading)
with the official `bitget-mcp-server` npm package (v1.1.0, 23 tools default, up to 57 with --modules all).

Source: https://github.com/BryanXYF/bryan-trading-skills (Bitget_MCP)
Publisher: Bitget Inc. (digmouse@bitget.com)
npm: bitget-mcp-server@1.1.0

## Current Config (config.yaml)

```yaml
mcp_servers:
  bitget-paper:
    args:
    - -y
    - bitget-mcp-server
    - '--read-only'
    command: npx
    env:
      PYTHONUNBUFFERED: '1'
```

## Safety Controls Active

- `--read-only` flag: ALL write operations (orders, transfers) disabled at server level
- No API keys configured (BITGET_API_KEY / BITGET_SECRET_KEY / BITGET_PASSPHRASE not set)
- Private endpoints return auth errors gracefully -- only public market data works
- Per SOUL.md: Exchange Credentials are NOT added. Escalation required for any key injection.

## Available Tools (23, read-only)

Spot (5 public):
  spot_get_ticker, spot_get_depth, spot_get_candles, spot_get_trades, spot_get_symbols
Spot (3 private -- auth required):
  spot_get_orders, spot_get_fills, spot_get_plan_orders
Futures (7 public):
  futures_get_ticker, futures_get_depth, futures_get_candles, futures_get_trades,
  futures_get_contracts, futures_get_funding_rate, futures_get_open_interest
Futures (3 private -- auth required):
  futures_get_orders, futures_get_fills, futures_get_positions
Account (3 private -- auth required):
  get_account_assets, get_account_bills, get_deposit_address, get_transaction_records
System:
  system_get_capabilities

## Legacy Backup

Old script backed up to:
  /home/hermes/projects/trading/orchestrator/scripts/bitget_mcp_server.py.v1.1-legacy.bak

## Next Steps (require explicit user approval)

1. Add API keys to enable private endpoints (balance, positions, orders) -- ESCALATION REQUIRED
2. Remove `--read-only` to enable trading -- ESCALATION REQUIRED
3. Add `--modules all` to load margin/copytrading/convert/earn/p2p/broker modules
4. Integrate MCP tools with trading-hub-operations skill
