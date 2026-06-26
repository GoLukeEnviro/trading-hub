# Ledger Integrity Watchdog Run — 2026-06-23 2026-06-23T23-43-44

## Ergebnis

| Check | Status | Detail |
|---|---|---|
| Sources Check | WARNING (Missing: freqai-rebel) | 4 active bots, 3 ledger keys |
| Drawdown Check | OK | LEDGER current_drawdown = 1.8039% |
| Live Gap | INFO | Δ = 1019.9984755280998 USDT (LIVE 3498.27 vs LEDGER 2478.2715244719) |

## Aktionen ausgeführt

- Idempotent: kein neuer Audit-Eintrag (gleiche Findings wie letzter Run)
- Canonical Status aktualisiert (JSON + MD + current-op-state)
- Report aktualisiert: docs/context/ledger-watchdog-2026-06-23.md

## Daten-Snapshot

```
LEDGER sources : ['baseline_v1_freqforge', 'freqforge_canary_v1', 'regime_hybrid_dryrun']
Active bots    : ['freqai-rebel', 'freqforge', 'freqforge-canary', 'regime-hybrid']
Missing        : ['freqai-rebel']
Drawdown       : 1.8039% (threshold 3%)
LIVE-LEDGER Δ  : 1019.9984755280998 USDT
```

## Empfohlener nächster Schritt

Tier-2: ledger-collector needs source_key for missing bot(s): freqai-rebel

## Tier-Eskalation

- **Tier 2 erforderlich** für Source-Vervollständigung
- Begründung: fehlende ledger-Key(s) verzerren aggregierte Equity 

## Meta
- Run timestamp: 2026-06-23T23:43:44.767522+00:00
- Fingerprint: {"dd_exceeds": false, "dd_value": 0.018039, "live_ledger_delta": 1020.0, "missing": ["freqai-rebel"]}
- Log: /opt/data/profiles/orchestrator/logs/ledger_integrity_watchdog.log
- State: /opt/data/profiles/orchestrator/state/ledger_integrity_watchdog_state.json
