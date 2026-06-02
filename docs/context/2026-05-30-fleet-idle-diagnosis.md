# Fleet Idle Diagnosis — 2026-05-30

## Problem
Fleet steht still: 0 offene Trades, keine Berichtigungen, keine Entries seit ~22. Mai.

## Root Cause (Dreifach-Block)
1. **can_short = False** (Regime-Hybrid) → Short-Signale ignoriert. **FIXED 2026-05-30:** can_short=True gesetzt.
2. **TA-Entry-Bedingungen nicht erfuellt** → Niedriger ADX, keine BB-Breakouts, kein Volume-Spike im aktuellen Markt (F&G=23, bearish). Weder Long- noch Short-Setup.
3. **AI-Signal-Override deaktiviert** (seit 2026-05-21, "recovery safety repair") → Umging RiskGuard, war zu gefaehrlich. BLEIBT DEAKTIVIERT.

## Signal-Layer Status (30.05.2026 06:21 UTC)
- BTC short 0.505 | ETH short 0.51 | SOL short 0.51
- AVAX/NEAR/ARB/OP hold (confidence 0)
- CONFIDENCE_MIN = 0.65 (nicht gesenkt)
- Signal liegt UNTER 0.65 Schwelle → kein Entry selbst bei can_short=True

## Backtest-Ergebnis (7 Tage, 23.-30. Mai)
- can_short=True, CONFIDENCE_MIN=0.65: **0 Trades** (TA-Bedingungen nicht erfuellt)
- Alle 42 historischen Trades (Mai 3-22): 100% LONG, 0 Shorts

## Aenderungen vorgenommen
- Regime-Hybrid: can_short=False → can_short=True (Zeile 62, Dry-run)
- Heartbeat-Writer: Cron alle 15min (war 6h), Momentum entfernt
- Permissions: heartbeat.log + lock file chmod 666

## Nicht vorgenommen (bewusst)
- CONFIDENCE_MIN 0.65 → 0.50: NICHT gesenkt (ohne Walk-Forward-Test zu riskant)
- AI-Signal-Override: NICHT reaktiviert (umgeht RiskGuard)
- Strategie-Anpassung: KEINE TA-Bedingungen gelockert

## Monitoring
- Cron `dedd76b423ce` alle 6h: prueft ob Signal-Confidence >= 0.65 erreicht
- Cron `a7d69925c2de` alle 15min: Heartbeat-Writer
- Beobachtung: Wenn natuerliche Confidence > 0.65 auftritt + can_short=True → Short-Entry moeglich

## Naechste Schritte
- Warten auf Marktregime-Wechsel (steigender ADX, bullish Setup)
- Beobachten ob Confidence >= 0.65 erreicht wird
- Bei erneuter Diskussion: Walk-Forward-Test mit CONFIDENCE_MIN=0.50 (nicht Backtest)