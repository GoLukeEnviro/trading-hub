# Ledger Integrity Watchdog Run — 2026-06-19 2026-06-19T23-45-54

## Ergebnis

| Check | Status | Detail |
|---|---|---|
| Sources Check | WARNING (Missing: freqai-rebel) | 4 active bots, 3 ledger keys |
| Drawdown Check | WARNING (3.45% > 3%) | LEDGER current_drawdown = 3.4490% |
| Live Gap | INFO | Δ = 1061.5173164629 USDT (LIVE 3498.27 vs LEDGER 2436.7526835371) |

## Aktionen ausgeführt

- Idempotent: kein neuer Audit-Eintrag (gleiche Findings wie letzter Run)
- Canonical Status aktualisiert (JSON + MD + current-op-state)
- Report aktualisiert: docs/context/ledger-watchdog-2026-06-19.md

## Daten-Snapshot

```
LEDGER sources : ['baseline_v1_freqforge', 'freqforge_canary_v1', 'regime_hybrid_dryrun']
Active bots    : ['freqai-rebel', 'freqforge', 'freqforge-canary', 'regime-hybrid']
Missing        : ['freqai-rebel']
Drawdown       : 3.4490% (threshold 3%)
LIVE-LEDGER Δ  : 1061.5173164629 USDT
```

## Empfohlener nächster Schritt

Tier-2: ledger-collector needs source_key for missing bot(s): freqai-rebel; Tier-2: drawdown approaching R2 threshold; review fleet_risk_auto_params

## Tier-Eskalation

- **Tier 2 erforderlich** für Source-Vervollständigung
- Begründung: fehlende ledger-Key(s) verzerren aggregierte Equity Drawdown überschreitet R2-Threshold

## Meta
- Run timestamp: 2026-06-19T23:45:54.539293+00:00
- Fingerprint: {"dd_exceeds": true, "dd_value": 0.03449, "live_ledger_delta": 1061.52, "missing": ["freqai-rebel"]}
- Log: /opt/data/profiles/orchestrator/logs/ledger_integrity_watchdog.log
- State: /opt/data/profiles/orchestrator/state/ledger_integrity_watchdog_state.json
