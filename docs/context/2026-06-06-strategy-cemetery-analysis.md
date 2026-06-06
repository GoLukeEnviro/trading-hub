# Strategy Cemetery Analysis — Regime-Hybrid

**Stand:** 2026-06-06
**Total:** 35 Strategiefiles in `freqtrade/bots/regime-hybrid/user_data/strategies/`
**Aktiv:** `RegimeSwitchingHybrid_v7_v04_Integration.py` (via docker-compose)

## Klassifikation

| File | Version | Keep/Archive | Grund |
|------|---------|-------------|-------|
| RegimeSwitchingHybrid_v7_v04_Integration.py | v7.4 | **KEEP** | Aktiv in docker-compose |
| FreqForge_Override.py | — | **KEEP** | Wird von anderen Bots genutzt (shared mount) |
| RegimeSwitchingHybrid_v2.py | v2 | ARCHIVE | Vorgänger, durch v3+ ersetzt |
| RegimeSwitchingHybrid_v2_Opt.py | v2_Opt | ARCHIVE | Hyperopt-Versuch, nicht aktiv |
| RegimeSwitchingHybrid_v3_Final.py | v3 | ARCHIVE | "Final" aber v7 aktiv — irreführend |
| RegimeSwitchingHybrid_v4_ATR.py | v4 | ARCHIVE | Vor v6+ |
| RegimeSwitchingHybrid_v5_ATRv2.py | v5 | ARCHIVE | Vor v6+ |
| RegimeSwitchingHybrid_v6_1_Fett.py | v6.1 | ARCHIVE | Experiment, nie aktiv |
| RegimeSwitchingHybrid_v6_Stable.py | v6 | ARCHIVE | "Stable" aber v7 aktiv |
| RegimeSwitchingHybrid_v7_EntryRefactor.py | v7 | ARCHIVE | Vor v7_v04 |
| RegimeSwitchingHybrid_v7_EntryRefactor_copy_test.py | v7_copy | ARCHIVE | Test-Duplikat |
| RegimeSwitchingHybrid_v8_1_RRR.py | v8.1 | ARCHIVE | Nie deployt |
| RegimeSwitchingHybrid_v8_2_RRR.py | v8.2 | ARCHIVE | Nie deployt |
| RegimeSwitchingHybrid_v8_3_Filter.py | v8.3 | ARCHIVE | Nie deployt |
| RegimeSwitchingHybrid_v8_BaselineTest.py | v8_test | ARCHIVE | Nie deployt |
| RegimeSwitchingHybrid_v9_1_Sentient.py | v9 | **REVIEW** | Höhere Version als aktiv — könnte Upgrade sein |
| momentum_bg15_v1.py | — | ARCHIVE | Nicht referenced |
| momentum_bg15_v2.py | — | ARCHIVE | Nicht referenced |
| momentum_bg15_v3.py | — | ARCHIVE | Nicht referenced |
| momentum_bg15_v3_1.py | — | ARCHIVE | Nicht referenced |
| MomentumDaily.py | — | ARCHIVE | Nicht referenced |
| rsi_bounce_daily_v1.py | — | ARCHIVE | Nicht referenced |
| rsi_mean_reversion_v11.py | — | ARCHIVE | v11? Overfitting-Risiko |
| rsi_momentum_v1.py | — | ARCHIVE | Nicht referenced |
| safe_entry_v1.py | — | ARCHIVE | Nicht referenced |
| SafeEntryDaily.py | — | ARCHIVE | Nicht referenced |
| TrendDaily.py | — | ARCHIVE | Nicht referenced |
| btc_macro_daily_v1.py | — | ARCHIVE | Nicht referenced |
| golden_cross_daily_v1.py | — | ARCHIVE | Nicht referenced |
| simple_trend_ema_v1.py | — | ARCHIVE | Nicht referenced |
| trend_strength_daily_v1.py | — | ARCHIVE | Nicht referenced |
| research_regime_hybrid_sideaware_v1.py | research | ARCHIVE | Research-Strategie |
| research_regime_hybrid_sideaware_v2.py | research | ARCHIVE | Research-Strategie |
| research_regime_hybrid_sideaware_v3.py | research | ARCHIVE | Research-Strategie |
| RegimeSafe.py | — | ARCHIVE | Nicht referenced |

## Risiko
- **Overfitting:** 35 Versionen = klassisches "Curve-Fitting"-Muster
- **v9_Sentient** ist neuer als aktiv (v7) — wurde v9 getestet und verworfen? Das fehlt in der History
- **Archival-Vorschlag:** mv in `freqtrade/bots/regime-hybrid/archive/strategies/`
- **Rollback:** `git mv` → reversibel

**Empfehlung:** Vor Archivierung Git-Commit machen, damit History erhalten bleibt.
