# Ledger Integrity Watchdog Run — 2026-06-18 2026-06-18T23-49-03

## Ergebnis

| Check | Status | Detail |
|---|---|---|
| Sources Check | WARNING (Missing: freqai-rebel) | 4 active bots, 3 ledger keys |
| Drawdown Check | WARNING (3.48% > 3%) | LEDGER current_drawdown = 3.4777% |
| Live Gap | INFO | Δ = 1062.2424857959 USDT (LIVE 3498.27 vs LEDGER 2436.0275142041) |

## Aktionen ausgeführt

- Idempotent: kein neuer Audit-Eintrag (gleiche Findings wie letzter Run)
- Canonical Status aktualisiert (JSON + MD + current-op-state)
- Report aktualisiert: docs/context/ledger-watchdog-2026-06-18.md

## Daten-Snapshot

```
LEDGER sources : ['baseline_v1_freqforge', 'freqforge_canary_v1', 'regime_hybrid_dryrun']
Active bots    : ['freqai-rebel', 'freqforge', 'freqforge-canary', 'regime-hybrid']
Missing        : ['freqai-rebel']
Drawdown       : 3.4777% (threshold 3%)
LIVE-LEDGER Δ  : 1062.2424857959 USDT
```

## Empfohlener nächster Schritt

Tier-2: ledger-collector needs source_key for missing bot(s): freqai-rebel; Tier-2: drawdown approaching R2 threshold; review fleet_risk_auto_params

## Tier-Eskalation

- **Tier 2 erforderlich** für Source-Vervollständigung
- Begründung: fehlende ledger-Key(s) verzerren aggregierte Equity Drawdown überschreitet R2-Threshold

## Meta
- Run timestamp: 2026-06-18T23:49:03.776652+00:00
- Fingerprint: {"dd_exceeds": true, "dd_value": 0.034777, "live_ledger_delta": 1062.24, "missing": ["freqai-rebel"]}
- Log: /opt/data/profiles/orchestrator/logs/ledger_integrity_watchdog.log
- State: /opt/data/profiles/orchestrator/state/ledger_integrity_watchdog_state.json
