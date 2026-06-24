# CLAUDE.md

Diese Datei bietet eine schlanke Übergabe für Claude Code
(`claude.ai/code`) bei der Arbeit in diesem Repository.

## Sprache

Kommunikation mit Luke erfolgt auf Deutsch. Code-Kennungen, Pfade, Branches,
Commit-Messages und API-Felder bleiben in ihrer technischen Originalform.

## Autoritative Reihenfolge

1. `AGENTS.md` — primäre operative Agenten-Anweisung.
2. `SOUL.md` — stabile Projektidentität und Sicherheitsprinzipien.
3. `docs/state/current-operational-state.md` — kanonischer aktueller
   Runtime-Snapshot.
4. Aktuelle Proof- und Kontextberichte unter `docs/reports/` und
   `docs/context/`.
5. Der konkrete Nutzer-Prompt.

Diese Datei dupliziert absichtlich keine volatilen Runtime-Metriken. Cycle-IDs,
Ledger-Stände, Rainbow-/Scoring-Zähler, Bot-Reachability, PR-spezifische
Belege und Scheduler-Details gehören in State-/Report-Dateien, nicht hierher.

## Stabile Projektorientierung

- Repository: `github.com/GoLukeEnviro/trading-hub`.
- Arbeitsverzeichnis: `/home/hermes/projects/trading`.
- Betriebsmodus: Dry-run only; Live-Trading ist ohne explizite menschliche
  Freigabe verboten.
- Hermes ist Meta-Orchestrator, nicht Trading Authority.
- `ai-hedge-fund-crypto` ist Signal-Core; Signale sind advisory only.
- Freqtrade bleibt Strategie- und Dry-run-Execution-Fleet.
- SI-v2 ist der evidenzbasierte Self-Improvement-Loop.

## Proven SI-v2 4-bot loop

Für SI-v2-Arbeit gilt die in `AGENTS.md` definierte Priorität:

1. SI-v2 Loop
2. Historical Evidence
3. Measurement Attribution
4. ShadowProposal Quality
5. Runtime Safety

Aktive SI-v2-Bot-Identitäten:

- `freqtrade-freqforge`
- `freqtrade-freqforge-canary`
- `freqtrade-regime-hybrid`
- `freqai-rebel`

Momentum und MVS sind keine aktiven SI-v2-Loop-Mitglieder. Wenn eine andere
Bot-Zahl auftaucht, zuerst `docs/state/current-operational-state.md` und den
neuesten Proof prüfen, nicht aus alten Root-Dokumenten ableiten.

## Unverletzliche Sicherheitsregeln

- Niemals `dry_run=false` setzen, Live-Trading aktivieren,
  Exchange-Zugangsdaten hinterlegen oder echte Orders platzieren.
- Niemals Freqtrade-Konfigs, Strategielogik, Signal-Schwellenwerte,
  Pair-Allowlists, Cronjobs, Guardian, Docker oder Runtime-Umgebung ohne
  explizite Freigabe ändern.
- Niemals Container neustarten, recreieren, Volumes anfassen, Daten löschen,
  prune ausführen oder breite Permission-Änderungen vornehmen ohne Freigabe.
- Niemals `git add .` verwenden; Dateien immer explizit nach Pfad stagen.
- Niemals force-push, `git reset --hard`, `git clean -fdx` oder History
  umschreiben.
- Niemals Secrets, Runtime-State, Datenbanken, Logs, Backups, Dumps oder
  `.env`-Dateien committen.
- Kill-Switch respektieren: `HALT_NEW` und `EMERGENCY` blockieren neue Entries.

## Scope-Regel für Agenten

Keine Docker-, Guardian-, Cron-, Healthcheck-, generische CI- oder
Infra-Arbeit, außer sie blockiert direkt den SI-v2 Loop oder Luke hat genau
diesen Scope freigegeben. Bei Drift: stoppen, Beleg nennen, separates Follow-up
empfehlen.

## Arbeitsablauf

1. Scope klassifizieren: L0/L1/L2/L3.
2. Erst lesen, dann schreiben.
3. Bei SI-v2 zuerst Loop-Relevanz und Safety-Gates prüfen.
4. Root-Dokus stabil halten; volatile Werte in State-/Report-Dateien ablegen.
5. Validierung real ausführen und Ausgaben dokumentieren.
6. Explizit stagen, Diff prüfen, committen und PR erstellen, wenn der Prompt es
   verlangt.

## Eskalation

Sofort eskalieren bei Live-Geld-Risiko, Zugangsdaten, `dry_run=false`, echter
Order-Gefahr, Freqtrade-Config-/Strategie-/RiskGuard-/Signal-Schwellenwert-
Änderungen, Cron-/Guardian-/Docker-Mutationen, Datenlöschung, Volume-Operationen,
unerklärtem Runtime-Drift oder fehlender ShadowLogger/RiskGuard-Evidenz für
eine safety-relevante Entscheidung.
