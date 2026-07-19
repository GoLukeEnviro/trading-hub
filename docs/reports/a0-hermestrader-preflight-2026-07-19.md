# A0 — HermesTrader Preflight Report

**Date:** 2026-07-19
**Post-C5.1:** `cef26c8`

## Confirmed from container

| Item | Value | Status |
|---|---|---|
| `strategy_file_sha256` | `a01284cdf17fd481c4e0ee6f0069ae3f9f330d...` | OK |
| `config_sha256` | `7647ed03a88e49a63c9916e9e8137ce84d5e12...` | OK |
| `shared_modules_sha256` | `d977c4ef9cff6c87c8b001a18c9b876fdd0f67...` | OK |
| Snapshot manifest | `gate0-snapshot-20260719T212841Z`, 3 files | OK |
| Primo/FleetRisk isolation | Strategy uses `primo_signal` + `fleet_risk_manager` | needs `network=none` |
| Freqtrade CLI | Im Container nicht verfuegbar | NOTICE |

## Luke's Re-Ratification needed

1. **Strategy:** Aktueller `FreqForge_Override` hat `can_short`, `FleetRisk`, `primo_signal`
2. **max_missing_candles=2610** (5%)
3. **min_duration_days=30** (per-window)
4. **Regime:** High/low volatility (ATR-normalisiert)

## A2 Selection Backtest (nach Re-Ratification)

`APPROVED_A2_GATE0_SELECTION_BACKTEST` mit `holdout=FORBIDDEN`, `network=NONE`
