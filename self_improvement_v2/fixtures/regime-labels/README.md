# Regime Label Fixtures

Synthetic regime label examples for SI v2 offline pipeline testing.

## Fixtures

| File | Regime | Symbol | Confidence | Source |
|------|--------|--------|------------|--------|
| `bullish_regime.json` | bullish | BTC/USDT:USDT | 0.85 | rainbow:ta |
| `bearish_regime.json` | bearish | ETH/USDT:USDT | 0.78 | rainbow:llm |
| `sideways_regime.json` | sideways | SOL/USDT:USDT | 0.65 | rainbow:ta |
| `volatile_regime.json` | volatile | AVAX/USDT:USDT | 0.72 | rainbow:ta |
| `unknown_regime.json` | unknown | UNI/USDT:USDT | 0.0 | rainbow:ta |

## Common Fields

| Field | Description |
|-------|-------------|
| `timestamp_utc` | ISO-8601 UTC timestamp |
| `symbol_or_pair` | Trading pair |
| `timeframe` | Candle timeframe (null if N/A) |
| `regime_label` | Regime classification: bullish, bearish, sideways, volatile, unknown |
| `confidence` | Confidence score 0.0–1.0 |
| `source` | Source identifier |
| `metadata` | Arbitrary metadata (indicators, notes) |

## Normalized Output

All fixtures should parse as valid JSON and be consumed by the attribution aggregator (#111) and stats schema (#110).
