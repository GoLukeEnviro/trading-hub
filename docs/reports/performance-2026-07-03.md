# Performance Report — 2026-07-03

**Quelle:** SQLite via `docker exec` (API extern antwortet leer)

## Bot-Vergleich

| Bot | Trades | Wins | Losses | Win-Rate | Total P&L | Avg Profit% | Open |
|-----|--------|------|--------|----------|-----------|-------------|------|
| **FreqForge** (Control) | 81 | 63 | 18 | **77.8%** | **+3.34 USDT** | +0.27% | 0 |
| **FreqForge Canary** | 64 | 57 | 6 | **89.1%** | **+4.09 USDT** | +0.06% | 1 |
| **Regime-Hybrid** | 58 | 38 | 20 | 65.5% | **-7.51 USDT** | -0.18% | 0 |
| **FreqAI Rebel** | 52 | 20 | 32 | 38.5% | **-2.03 USDT** | -0.18% | 0 |

## Letzte 5 Trades pro Bot

### FreqForge (Control)
| Pair | Profit% | Realized | Closed |
|------|---------|----------|--------|
| BTC/USDT | +1.53% | +5.13 | 2026-06-30 |
| ETH/USDT | -3.84% | -12.70 | 2026-06-29 |
| SOL/USDT | -4.11% | -13.88 | 2026-06-29 |
| ETH/USDT | +2.61% | +0.91 | 2026-06-23 |
| SOL/USDT | +5.09% | +2.24 | 2026-06-23 |

### FreqForge Canary
| Pair | Profit% | Realized | Closed |
|------|---------|----------|--------|
| UNI/USDT | +0.29% | +0.07 | 2026-07-02 |
| LINK/USDT | +0.16% | +0.03 | 2026-07-01 |
| ATOM/USDT | +0.005% | +0.001 | 2026-07-01 |
| DOT/USDT | +0.009% | +0.002 | 2026-07-01 |
| LINK/USDT | -9.33% | -2.24 | 2026-06-24 |

### Regime-Hybrid
| Pair | Profit% | Realized | Closed |
|------|---------|----------|--------|
| ARB/USDT | +0.27% | +0.07 | 2026-07-02 |
| ARB/USDT | -0.91% | -0.23 | 2026-07-02 |
| ARB/USDT | -0.39% | -0.10 | 2026-06-30 |
| ARB/USDT | -0.48% | -0.12 | 2026-06-20 |
| ARB/USDT | -0.70% | -0.17 | 2026-06-17 |

### FreqAI Rebel
| Pair | Profit% | Realized | Closed |
|------|---------|----------|--------|
| ETH/USDT | -1.28% | -0.20 | 2026-07-01 |
| ETH/USDT | -0.01% | -0.002 | 2026-07-01 |
| ETH/USDT | -0.66% | -0.11 | 2026-06-30 |
| BTC/USDT | +0.13% | +0.03 | 2026-06-30 |
| BTC/USDT | -0.25% | -0.06 | 2026-06-30 |

## Erkenntnisse

1. **Canary läuft besser als Control** — 89.1% Win-Rate vs 77.8%, +4.09 USDT vs +3.34 USDT. Der `max_open_trades=2`-Overlay scheint zu wirken.
2. **Regime-Hybrid verliert** — -7.51 USDT bei 65.5% Win-Rate. Die Verluste sind größer als die Gewinne.
3. **Rebel kämpft** — Nur 38.5% Win-Rate, -2.03 USDT. Die kleine Gewinne werden von großen Verlusten übertroffen.
4. **Canary hat 1 offenen Trade** — UNI/USDT (seit 2026-07-02, +0.29%).
5. **Alle anderen Bots haben 0 offene Trades** — wenig Aktivität in den letzten Tagen.
