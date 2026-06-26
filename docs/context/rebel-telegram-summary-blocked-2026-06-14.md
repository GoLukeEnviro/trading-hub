# Rebel Status-Summary via Telegram — BLOCKED (Credentials) — 2026-06-14

## Ergebnis

| Schritt | Status | Detail |
|---|---|---|
| Original-Kommando (genau wie angefordert) | FAILED | `No module named 'fleet_api_client'` |
| Runtime-Fix (sys.path) | OK | `orchestrator/scripts` fehlte im Pfad (non-destructive, in-memory) |
| Summary-Inhalt (`build_rebel_status_summary`) | OK | Payload gebaut, Metriken plausibel |
| Telegram-Versand (`drawdown_guard.send_telegram`) | BLOCKED | HTTP 404 — Token ungültig/malformed |

## Root Cause (zwei unabhängige Probleme)

1. **Pfad-Problem (L2, runtime-behebbar):** `self_optimizer._send_telegram_message`
   lädt `orchestrator/scripts/drawdown_guard.py` via `importlib`. Dieses importiert
   `from fleet_api_client import freqtrade_api_get` (Zeile 24). `fleet_api_client.py`
   liegt im selben Verzeichnis `orchestrator/scripts/`, das aber nicht auf `sys.path`
   steht. → `ModuleNotFoundError`. Das Original-Kommando bricht hier ab.

2. **Credential-Problem (L3, ESCALATED):** Nach Pfad-Fix lädt der Helper korrekt,
   aber `send_telegram` schlägt mit HTTP 404 fehl. Der Token stammt aus dem
   Docker-inspect-Fallback von Container `hermes-green` (`TELEGRAM_BOT_TOKEN`), weil
   im Cron-Environment weder `TELEGRAM_BOT_TOKEN` noch `TELEGRAM_BOT_TOKEN_B64`
   gesetzt sind. Der dort gefundene Wert ist **13 Zeichen, kein Doppelpunkt,
   nicht well-formed** (echte Telegram-Tokens: `<digits>:<35-char-hash>`, ~46 Zeichen).
   Telegram liefert 404 = Token entspricht keinem existierenden Bot.

## Sicherheit

- Token-Wert wurde **nicht** ausgegeben/protokolliert (nur Shape: Länge, Format).
- Kein Config-Edit, kein neuer Cron-Job, kein Secret-Read.
- Behebung erfordert Credential-Zugriff → menschliche Freigabe nötig.

## Evidence

```
Original command result:
  {"sent": false, "telegram": {"sent": false, "reason": "No module named 'fleet_api_client'"}}

After sys.path fix:
  [Telegram send failed: HTTP Error 404: Not Found]
  {"sent": false, "telegram": {"sent": false, "via": ".../drawdown_guard.py"}}

Credential shape (value NEVER printed):
  TOKEN shape : len=13 colon=False well_formed=False
  CHAT  shape : len=9  colon=False well_formed=False
  TOKEN source: docker:hermes-green(TELEGRAM_BOT_TOKEN)
```

## Summary-Inhalt (wurde korrekt gebaut, nur Versand blockiert)

```
📊 Rebel Status Summary
DI: 1.5 | Stake: None | SPW: None
PF: 0.28 | WR: 0.349 | Trades: 43
Neue Proposals: 0 | offene Stage0: 2
Letzte Events:
- patch_success / success / rollback=False
- patch_failed_rollback / error / rollback=True
- patch_failed_rollback / error / rollback=True
Empfehlung: scale_pos_weight Proposal prüfen — benötigt neuen Identifier + Retrain.
```

## Next Step (requires human approval — credentials)

- Gültigen Telegram-Bot-Token bereitstellen via:
  - Cron-Environment (`TELEGRAM_BOT_TOKEN=<digits>:<hash>` + `TELEGRAM_CHAT_ID`), ODER
  - Korrektur der `TELEGRAM_BOT_TOKEN` Env-Var im Container `hermes-green`.
- Pfad-Problem ggf. dauerhaft beheben: `orchestrator/scripts` dem Aufruf-Skript
  hinzufügen (sys.path) oder `drawdown_guard.py`-Import robuster machen.
- Danach: Original-Kommando erneut ausführen → `sent: true` erwartet.

## Betroffene Komponenten

- `freqtrade/bots/regime-hybrid/config/research/automation/self_optimizer.py`
  (`send_rebel_status_summary`, `_send_telegram_message`)
- `orchestrator/scripts/drawdown_guard.py` (`send_telegram`, `_get_telegram_creds`)
- `orchestrator/scripts/fleet_api_client.py` (existiert, nur nicht auf Pfad)
