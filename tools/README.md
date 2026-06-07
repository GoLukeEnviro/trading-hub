# Tools — Trading Hub Utility Scripts

This directory contains standalone utility scripts for the trading-hub system.
All scripts use stdlib only and require no additional pip installs.

---

## 1. export_trade_history.py

Standardized CLI tool for exporting closed trades from a Freqtrade
`tradesv3.sqlite` database into CSV (per-trade detail) and JSON (summary metrics)
files.

The Profitability Forensics Agent uses this as its authoritative `trade_history`
data source (P0 evidence tier).

### Usage

```
python tools/export_trade_history.py \
  --db <path-to-tradesv3.sqlite> \
  --bot <bot-name> \
  --output <output-path-prefix> \
  [--since <ISO-8601-date>] \
  [--until <ISO-8601-date>] \
  [--format csv|json|both]
```

| Flag | Required | Description |
|---|---|---|
| `--db` | Yes | Path to the Freqtrade tradesv3.sqlite database. |
| `--bot` | Yes | Bot name string for labeling output (e.g., `freqforge`). |
| `--output` | Yes | Output path prefix (no extension). Produces `{prefix}_trades.csv` and `{prefix}_summary.json`. |
| `--since` | No | ISO 8601 date filter, inclusive. Filters on `close_date`. Example: `2026-01-01` or `2026-01-01T00:00:00Z`. |
| `--until` | No | ISO 8601 date filter, inclusive. Filters on `close_date`. Example: `2026-06-01` or `2026-06-01T23:59:59Z`. |
| `--format` | No | Output format. One of: `csv` (default), `json`, `both`. |

### Worked Examples

#### a. Basic Export for FreqForge

```bash
python tools/export_trade_history.py \
  --db freqtrade/bots/freqforge/tradesv3.sqlite \
  --bot freqforge \
  --output /tmp/freqforge-export
```

Produces:
- `/tmp/freqforge-export_trades.csv` — per-trade detail
- `/tmp/freqforge-export_summary.json` — aggregate metrics

#### b. Filtered Export with Date Range

```bash
python tools/export_trade_history.py \
  --db freqtrade/bots/freqforge/tradesv3.sqlite \
  --bot freqforge \
  --output /tmp/freqforge-filtered \
  --since 2026-01-01 \
  --until 2026-05-31
```

#### c. Export from Inside the Docker Container

```bash
docker exec trading-freqtrade-freqforge-1 \
  python /tools/export_trade_history.py \
    --db /freqtrade/user_data/tradesv3.sqlite \
    --bot freqforge \
    --output /tmp/freqforge-export
```

> **Note:** Mount the `tools/` directory into the container, or copy the script
> in first. For ad-hoc exports, run from the host with the SQLite path that the
> volume mount exposes.

### Output File Format

#### `{prefix}_trades.csv`

| Column | Type | Description |
|---|---|---|
| `trade_id` | int | Freqtrade trade ID |
| `open_date_utc` | str | ISO 8601 open timestamp |
| `close_date_utc` | str | ISO 8601 close timestamp |
| `pair` | str | Trading pair (e.g., BTC/USDT) |
| `profit_abs` | float | Absolute profit/loss in quote currency |
| `profit_ratio` | float | Profit ratio (e.g., 0.05 = 5%) |
| `stake_amount` | float | Stake amount |
| `open_rate` | float | Entry price |
| `close_rate` | float | Exit price |
| `trade_duration_seconds` | int | Duration in seconds |
| `is_open` | int | Always 0 (closed trades only) |
| `exchange` | str | Exchange name |
| `strategy` | str | Strategy name (if column exists, else NULL) |

#### `{prefix}_summary.json`

| Key | Type | Description |
|---|---|---|
| `schema_version` | str | `"1.0"` |
| `bot_name` | str | Bot name from `--bot` |
| `export_timestamp_utc` | str | Export run timestamp ISO 8601 |
| `db_path` | str | Absolute path to input DB |
| `since` | str or null | `--since` value |
| `until` | str or null | `--until` value |
| `total_trades` | int | Number of closed trades |
| `winning_trades` | int | Trades with profit_abs >= 0 |
| `losing_trades` | int | Trades with profit_abs < 0 |
| `win_rate` | float or null | winning_trades / total_trades |
| `gross_profit` | float | Sum of all winning trade profits |
| `gross_loss` | float | Absolute sum of all losing trade losses |
| `profit_factor` | float or str or null | gross_profit / gross_loss; `"UNDEFINED_PF"` if no losses; null if no trades |
| `net_profit_usdt` | float | gross_profit - gross_loss |
| `avg_win` | float or null | Average profit per winning trade |
| `avg_loss` | float or null | Average loss per losing trade |
| `avg_risk_reward` | float or null | avg_win / avg_loss |
| `max_drawdown_pct` | float or null | Maximum peak-to-trough drawdown on cumulative profit_abs |
| `avg_trade_duration_seconds` | int or null | Average trade duration |
| `NO_TRADE_DATA` | bool | `true` if zero closed trades matched filters |

### Edge Cases

| Case | Behaviour |
|---|---|
| **NO_TRADE_DATA** | CSV written with headers only (no data rows). Summary has all metrics null and `"NO_TRADE_DATA": true`. Exit code 0. |
| **UNDEFINED_PF** | If `gross_loss == 0` and `total_trades > 0`, `profit_factor` is written as the string `"UNDEFINED_PF"` (not a float). |
| **DB not found** | Prints `ERROR: db not found: <path>` to stderr. Exit code 1. No output files written. |
| **Corrupt DB** | Prints `ERROR: cannot open db: <error>` to stderr. Exit code 1. No output files written. |
| **Write error** | Prints `ERROR: cannot write to: <path> — <reason>` to stderr. Exit code 1. |
| **Partial output** | Never writes partial output. Both files succeed or neither is written. |

---

## Integration with Forensics Agent

The Forensics Agent (spec at `docs/specs/profitability-forensics-agent-spec.md`)
expects `{output}_summary.json` as the P0 evidence tier `trade_history` source.

- Run `export_trade_history.py` for each bot before starting a Forensics run.
- The Forensics Agent reads the summary JSON to populate:
  - `total_trades`, `winning_trades`, `losing_trades`
  - `win_rate`, `profit_factor`, `net_profit_usdt`
  - `max_drawdown_pct`, `avg_risk_reward`
  - `avg_trade_duration_seconds`
- The per-trade CSV is used for 30-day rolling window analysis and inflection point detection.

---

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success (including NO_TRADE_DATA) |
| 1 | Error (DB not found, corrupt DB, write error) |
