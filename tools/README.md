# Tools

## export_trade_history.py

Standardized export helper for Profitability Forensics trade history ingestion.

### Usage

```bash
python3 tools/export_trade_history.py \
  --db /path/to/tradesv3.sqlite \
  --bot freqforge \
  --output /tmp/freqforge-history \
  --since 2026-06-01T00:00:00Z \
  --until 2026-06-07T23:59:59Z
```

Arguments:

- `--db` (required): path to `tradesv3.sqlite`
- `--bot` (required): bot name label in summary output
- `--output` (required): output prefix path
- `--since` (optional): ISO 8601 lower bound for `close_date`
- `--until` (optional): ISO 8601 upper bound for `close_date`

### Outputs

Given `--output /tmp/freqforge-history`:

- `/tmp/freqforge-history_trades.csv` — closed trades with per-trade fields
- `/tmp/freqforge-history_summary.json` — aggregate metrics and export metadata

### Edge-case behavior

- No closed trades: writes CSV header only, summary metrics are `null`, and `NO_TRADE_DATA` is `true`
- No losses in export window: `profit_factor` is the string `UNDEFINED_PF`
- SQLite unavailable/corrupt: exits with code `1`, prints error to stderr, writes no output files
