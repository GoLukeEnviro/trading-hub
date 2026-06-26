# Ledger Integrity Watchdog Run — 2026-06-16 2026-06-16T23-35-16

## Ergebnis

| Check | Status | Detail |
|---|---|---|
| Sources Check | WARNING (Missing: freqai-rebel) | 4 active bots, 3 ledger keys |
| Drawdown Check | WARNING (3.58% > 3%) | LEDGER current_drawdown = 3.5809% |
| Live Gap | INFO | Δ = 1064.8469378842 USDT (LIVE 3498.27 vs LEDGER 2433.4230621158) |

## Aktionen ausgeführt

- Idempotent: kein neuer Audit-Eintrag (gleiche Findings wie letzter Run)
- Canonical Status aktualisiert (JSON + MD + current-op-state)
- Report aktualisiert: docs/context/ledger-watchdog-2026-06-16.md

## Daten-Snapshot

```
LEDGER sources : ['baseline_v1_freqforge', 'freqforge_canary_v1', 'regime_hybrid_dryrun']
Active bots    : ['freqai-rebel', 'freqforge', 'freqforge-canary', 'regime-hybrid']
Missing        : ['freqai-rebel']
Drawdown       : 3.5809% (threshold 3%)
LIVE-LEDGER Δ  : 1064.8469378842 USDT
```

## Empfohlener nächster Schritt

Tier-2: ledger-collector needs source_key for missing bot(s): freqai-rebel; Tier-2: drawdown approaching R2 threshold; review fleet_risk_auto_params

## Tier-Eskalation

- **Tier 2 erforderlich** für Source-Vervollständigung
- Begründung: fehlende ledger-Key(s) verzerren aggregierte Equity Drawdown überschreitet R2-Threshold

## Meta
- Run timestamp: 2026-06-16T23:35:16.255010+00:00
- Fingerprint: {"dd_exceeds": true, "dd_value": 0.035809, "live_ledger_delta": 1064.85, "missing": ["freqai-rebel"]}
- Log: /opt/data/profiles/orchestrator/logs/ledger_integrity_watchdog.log
- State: /opt/data/profiles/orchestrator/state/ledger_integrity_watchdog_state.json
