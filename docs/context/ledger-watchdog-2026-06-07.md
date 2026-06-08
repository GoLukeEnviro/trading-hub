# Ledger Integrity Watchdog Run — 2026-06-07 2026-06-07T15-23-07

## Ergebnis

| Check | Status | Detail |
|---|---|---|
| Sources Check | WARNING (Missing: freqai-rebel) | 4 active bots, 3 ledger keys |
| Drawdown Check | OK | LEDGER current_drawdown = 0.1114% |
| Live Gap | INFO | Δ = 975.5793565700001 USDT (LIVE 3498.27 vs LEDGER 2522.69064343) |

## Aktionen ausgeführt

- Idempotent: kein neuer Audit-Eintrag (gleiche Findings wie letzter Run)
- Canonical Status aktualisiert (JSON + MD + current-op-state)
- Report aktualisiert: docs/context/ledger-watchdog-2026-06-07.md

## Daten-Snapshot

```
LEDGER sources : ['baseline_v1_freqforge', 'freqforge_canary_v1', 'regime_hybrid_dryrun']
Active bots    : ['freqai-rebel', 'freqforge', 'freqforge-canary', 'regime-hybrid']
Missing        : ['freqai-rebel']
Drawdown       : 0.1114% (threshold 3%)
LIVE-LEDGER Δ  : 975.5793565700001 USDT
```

## Empfohlener nächster Schritt

Tier-2: ledger-collector needs source_key for missing bot(s): freqai-rebel

## Tier-Eskalation

- **Tier 2 erforderlich** für Source-Vervollständigung
- Begründung: fehlende ledger-Key(s) verzerren aggregierte Equity 

## Meta
- Run timestamp: 2026-06-07T15:23:07.723272+00:00
- Fingerprint: {"dd_exceeds": false, "dd_value": 0.001114, "live_ledger_delta": 975.58, "missing": ["freqai-rebel"]}
- Log: /opt/data/profiles/orchestrator/logs/ledger_integrity_watchdog.log
- State: /opt/data/profiles/orchestrator/state/ledger_integrity_watchdog_state.json
