# Trade History Forensics Run — 2026-06-07

## Kontext
- Shadowlock lief als Voraussetzung bereits.
- Die Exporte wurden lokal unter `docs/context/` erzeugt und nicht committed.
- Der generische Pfad `freqtrade/bots/{BOT}/tradesv3.sqlite` war für alle vier Bots nicht vorhanden; verwendet wurden die realen DB-Pfade aus den Summary-JSONs.

## Quellen
- `docs/context/trade-export-freqforge-2026-06-07_summary.json`
  - CSV: `docs/context/trade-export-freqforge-2026-06-07_trades.csv`
- `docs/context/trade-export-freqforge-canary-2026-06-07_summary.json`
  - CSV: `docs/context/trade-export-freqforge-canary-2026-06-07_trades.csv`
- `docs/context/trade-export-regime-hybrid-2026-06-07_summary.json`
  - CSV: `docs/context/trade-export-regime-hybrid-2026-06-07_trades.csv`
- `docs/context/trade-export-freqai-rebel-2026-06-07_summary.json`
  - CSV: `docs/context/trade-export-freqai-rebel-2026-06-07_trades.csv`

## Kennzahlen
| Bot | DB Path | total_trades | win_rate | profit_factor | net_profit_usdt | max_DD_pct | NO_TRADE_DATA | Notes |
|---|---|---:|---:|---:|---:|---:|---|---|
| freqforge | `/home/hermes/projects/trading/freqforge/user_data/tradesv3.freqforge.dryrun.sqlite` | 64 | 84.38% | 1.6426 | +23.2235 | 170.1705% | false | profitabel, aber DD > 100% |
| freqforge-canary | `/home/hermes/projects/trading/freqforge-canary/user_data/tradesv3.freqforge_canary.dryrun.sqlite` | 44 | 93.18% | 241.7329 | +7.4034 | 2.4414% | false | PF extrem hoch wegen sehr kleinem Gross-Loss |
| regime-hybrid | `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/tradesv3.regime_hybrid.dryrun.sqlite` | 48 | 72.92% | 0.5834 | -6.8190 | 3676.7260% | false | negatives Net Profit und massiver Drawdown |
| freqai-rebel | `/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data/tradesv3.freqai_rebel.dryrun.sqlite` | 0 | N/A | N/A | +0.0000 | N/A | true | NO_TRADE_DATA=true; profit_factor im JSON = null (nicht UNDEFINED_PF) |

## Auffälligkeiten
- `freqforge` ist netto profitabel, hat aber einen Drawdown von >100% auf Basis des Exporter-PnL-Verlaufs.
- `freqforge-canary` zeigt einen sehr hohen Profit Factor, getrieben durch extrem kleine Verlustsumme.
- `regime-hybrid` ist der klare Ausreißer nach unten: negatives Net Profit und sehr hoher Drawdown.
- `freqai-rebel` hat keine Trades; deshalb sind `win_rate`, `profit_factor` und `max_DD_pct` nicht berechenbar.

## Gesamturteil
WARNING/RED — die Fleetsumme ist nicht unkritisch, weil `regime-hybrid` deutlich unter Wasser ist, auch wenn die anderen Bots lokal positiv aussehen.
