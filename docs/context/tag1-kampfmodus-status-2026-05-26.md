# TAG 1 Kampfmodus Status — 2026-05-26 23:06 UTC

## Sofort-Checks

- DrawdownGuard manuell getriggert: 4/4 Bots erreichbar, Fleet +46.18 USDT vs Startkapital 3450 USDT, DD 0.0%, Signal fresh (15.1 min).
- Canary Position Monitor manuell getriggert: beide Shorts stale (87h), BTC -1.74%, ETH -2.28%, beide noch deutlich vor Stoploss (9.0% entfernt).
- FreqAI-Rebel geprüft: `max_open_trades=2`, Bot RUNNING, BTC+ETH Training 22:59 UTC abgeschlossen, Inferencing aktiv um 23:00/23:05 UTC, aber noch 0 Trades.
- Auto-Repair v2 aktiv: Cron alle 2h (`814fbe371c41`). Canary-Monitor aktiv: alle 30m (`c05c8fc158e4`). Einmaliger Rebel-30m-Check geplant für 23:36 UTC (`af1a9f0c38f3`).

## Regime-Hybrid Deep Dive

- Last-24h closed trades: 0. Neue RR-Parameter konnten daher noch nicht empirisch validiert werden.
- Letzte 5 geschlossene Trades stammen aus 2026-05-15 bis 2026-05-22; 4x ROI-Kleingewinne, 1x Stoploss (-3.123%).
- Kritischer Audit-Fund: Ein älterer Log-Auszug zeigte noch alte Config-Overrides (`stoploss -0.04`, ROI 0.015/0.01/0.005/0.002, trailing 0.01/0.02). Das wurde sofort verifiziert.
- Host-Config und Container-Config prüfen jetzt konsistent die neuen Werte: `stoploss=-0.025`, `minimal_roi={'0': 0.04, '30': 0.025, '60': 0.015, '120': 0.008}`, `trailing_stop_positive=0.012`, `trailing_stop_positive_offset=0.02`.
- Container wurde um 23:05 UTC erneut sauber neugestartet und die geladenen Strategie-Overrides im Startup-Log bestätigt.
- Detailreport gespeichert unter `docs/context/tag1-regime-hybrid-last5-trades-2026-05-26.md`.

## Backtesting / Gates

- `BACKTEST_GATES=false` ist in `fleet_risk_manager.py` und `fleetguard_v1.py` eingebaut und im Container wirksam.
- Trotzdem erzeugt Regime-Hybrid im Backtest weiter 0 Trades. Damit ist der Gate-Layer nicht mehr die Blockade.
- Wahrscheinliche Ursache: die Strategie ist ohne externe Signal-/Override-Dynamik zu restriktiv (ADX + EMA200 HTF + EMA50 + RSI + Volume + Regime-Filter).
- Konsequenz: Live-Validierung bleibt die primäre Bewertungsquelle für den RR-Fix.

## Operative Bewertung TAG 1

- FreqAI-Rebel ist erfolgreich aktiviert und autonom am Arbeiten; jetzt nur noch Beobachtung.
- Canary Shorts sind nicht akut kritisch, aber klar stale; der neue Cron überwacht das jetzt engmaschig.
- Regime-Hybrid ist jetzt nachweislich mit den neuen RR-Parametern live.
- Nächste entscheidende Signale für TAG 1:
  1. Rebel-30m-Check um 23:36 UTC
  2. Canary-Monitor um 23:30 UTC
  3. Fleet-Auto-Repair um 00:00 UTC
