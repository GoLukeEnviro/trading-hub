# Zielarchitektur-Roadmap — Simplified (2026-07-14)

> **Status:** Vorschlag / Planungsdokument (L2, docs-only)
> **Autoritative Reihenfolge:** `AGENTS.md` → `SOUL.md` → `docs/state/current-operational-state.md` → dieses Dokument.
> **Verhältnis zu Issue #423:** #423 bleibt die kanonische Task-Roadmap. Dieses
> Dokument definiert das vereinfachte Zielbild; Umsetzung erfolgt erst nach
> Freigabe durch Luke als eigene Issues/Tasks.
>
> Dieses Dokument autorisiert **keine** Runtime-Mutation, kein Live-Trading,
> kein `dry_run=false`, kein Exchange-Key-Deployment und keine
> Bot-/Strategie-Mutation. Live-Kapital braucht immer explizite menschliche
> Freigabe (SOUL.md Regel 1).

---

## Leitprinzip

**Erst Alpha beweisen, dann Orchestrierung.**

Das alte Zielbild hat den Kontrollapparat perfektioniert, bevor die Kernfrage
beantwortet war: *Verdient das System unter realistischen Bedingungen Geld?*
Der gemessene Drawdown von 82,79 % in der einzigen Live-Canary-Episode zeigt:
Die Gates haben den Schaden korrekt abgewickelt (Rollback, D1/D2 blockiert),
aber sie haben ihn nicht verhindert — weil die Grenzen prozessual statt
mathematisch waren und die Basis-Strategie keinen belegten Alpha hatte.

Die neue Regel:

> Der Nachweis-Apparat darf nie größer sein als das, was er beweist.
> Risiko wird mathematisch gekappt, nicht bürokratisch diskutiert.

---

## Delta zum alten Zielbild

| Alt | Neu |
|---|---|
| 7 Systemschichten (Signal-Core, RiskGuard, Kill-Switch, Fleet, Evidence, SI-v2, Hermes) | **3 Schichten:** Sensorik → Risk Engine → Execution |
| 10-Schritte-SI-v2-Loop pro Parameteränderung | **4-Schritte-Loop:** Messen → Validieren → Gewichtet einführen → Entscheiden |
| Allowlist-Mikromanagement pro Parameter | **Parameter-Bounds:** erlaubte Wertebereiche statt Einzel-Freigaben |
| Kill-Switch nur flottenweit | **HALT_BOT** pro Bot + globaler Kill-Switch für systemische Fälle |
| Evidence-Ausfall blockiert alles | Evidence **fail-closed nur für Mutationen**; Telemetrie best-effort mit Alarm |
| Mehrstufige Approval-Marker-Kette für Live | **Genau ein Human-Gate:** einmalige, explizite Live-Freigabe pro Stufe |
| LLM „gegebenenfalls" in der Signalerzeugung | LLM **nur** Regime-/Sentiment-Klassifikation und Research — nie Entry/Exit |
| Canary = separater Bot mit eigenem Zeitfenster | **Gewichtete Einführung:** neue Parameter-Version bekommt Stake-Anteil (5 % → 20 % → 50 % → 100 %), alte Version bleibt Kontrollgruppe im selben Marktfenster |
| Hermes mit autonomem Code-Merge-Loop | Hermes = **CI/CD-Operator mit Runbooks**; Strategie-Änderungen kommen aus dem Research-Pod, nicht aus Hermes |

---

## Die drei Schichten

### Schicht 1 — Sensorik (Signale & Regime, advisory only)

- Deterministische, überprüfbare Signalerzeugung: technische Analyse,
  Marktdaten, Volatilität, Regime-Klassifikation.
- `ai-hedge-fund-crypto` / Rainbow liefern **Regime und Kontext**, keine
  Entry-/Exit-Trigger. LLM-Ausgaben bleiben advisory only (SOUL.md Regel 9)
  und werden für Ideenfindung im Research-Pod genutzt, nie in der Live-Kette.
- Autoritätsgrenze unverändert: **Ein Signal ist eine Empfehlung, keine
  Order.** Signale dürfen Entries filtern oder verhindern, nie erzwingen.

### Schicht 2 — Risk Engine (der mathematische Käfig)

RiskGuard und Kill-Switch verschmelzen zu einer Engine mit harten, nicht
verhandelbaren Zahlen statt Prozess-Checklisten:

- **Daily Trailing Drawdown:** Tages-Drawdown-Limit (z. B. 3–5 % Equity).
  Bei Berührung → automatisch `HALT_NEW` bis Tagesende. Kein Diskussionspfad.
- **Trade-Level-Limit:** Verlust pro Trade relativ zur ATR gedeckelt →
  automatischer Exit des Einzeltrades.
- **Bot-Level:** `HALT_BOT` schaltet einen einzelnen Bot ab, ohne die Flotte
  zu stoppen. Der globale Kill-Switch (`NORMAL` / `HALT_NEW` / `EMERGENCY`)
  bleibt für systemische Fälle (Exchange-Ausfall, Datenstromabriss).
- **Globales Risikobudget:** max. Gesamt-Drawdown, Exposure- und
  Positionslimits über die ganze Flotte.
- Die Engine bewertet nicht, ob ein Signal „gut" ist — sie kappt den
  Risiko-Fluss, wenn Kapital schrumpft. Ein 82-%-Drawdown ist damit
  strukturell unmöglich, lange bevor ein Freigabeprozess greifen müsste.

### Schicht 3 — Execution Fleet (dumm, schnell, unabhängig)

- Freqtrade-Bots sind schnelle Ausführungsalgorithmen mit klaren, starren
  Regelwerken pro Regime. Die Strategie bleibt die unmittelbare
  Entscheidungsinstanz des Bots.
- Jeder Bot: eigene Strategie, eigenes Sub-Risikolimit, eigener
  `HALT_BOT`-Schalter, eigene Performance-Messung.
- Start mit **einer** bewiesenen Kernstrategie (oder kleinem Ensemble), nicht
  mit einer breiten Flotte. Skalierung ist eine Belohnung für belegte
  Performance, kein Ausgangszustand.

---

## Der vereinfachte Improvement-Loop (ersetzt den 10-Schritte-SI-v2)

```text
1. MESSEN      — Telemetrie, Trades, Drawdown, Regime laufend erfassen
2. VALIDIEREN  — Kandidat offline prüfen: Walk-Forward, Out-of-Sample,
                 statistische Signifikanz (Sortino/Profit-Factor/Max-DD)
3. EINFÜHREN   — gewichtet: neue Version 5 % Stake-Anteil, Bestand als
                 Kontrollgruppe im selben Marktfenster; Snapshot + Rollback
                 sind Vorbedingung, nicht Checklistenpunkt
4. ENTSCHEIDEN — KEEP (Gewicht steigt), ROLLBACK (Gewicht → 0, Version weg),
                 EXTEND nur bei zu kleiner Stichprobe
```

Verbleibende Gates — genau vier, alle automatisch prüfbar:

1. Parameter innerhalb definierter **Bounds** (statt Einzel-Allowlist).
2. **Snapshot + Rollback** existieren und sind getestet.
3. Kill-Switch ist `NORMAL`, kein anderer Änderungszyklus aktiv.
4. Aktion ist Dry-Run (bzw. innerhalb des freigegebenen Live-Budgets).

Was entfällt: Shadow-Proposal-Formulare, Proposal-Qualitäts-Scoring,
mehrstufige Policy-Gate-Kaskaden, Messfenster-Zeremonien. Der
RuntimeEffectProof bleibt als **ein** automatischer Check erhalten (läuft der
Parameter wirklich in der Runtime?), nicht als eigener Prozessschritt mit
Berichtspflicht.

Damit ist auch das Overfitting-Problem des alten Loops adressiert: Validierung
passiert **offline auf Out-of-Sample-Daten**, bevor irgendetwas die Runtime
berührt — nicht durch Warten auf ein kurzes, zufälliges Canary-Zeitfenster.

---

## Graduation-Pipeline (KPI-basiert statt Marker-Arie)

```text
Backtest + Walk-Forward (Out-of-Sample, Monte-Carlo)
        ↓  harte KPIs bestanden
Shadow / Paper-Trading auf Echtzeitdaten
        ↓  Live-Verhalten ≈ Backtest-Erwartung, sonst Stopp + Diagnose
Dry-Run in der Fleet (≥ 30 Tage)
        ↓  z. B.: Max-DD < 8 %, Profit-Factor > 1.3, stabile Ausführung
LIVE_CANDIDATE — System erzeugt Report mit allen KPIs
        ↓  ★ menschliche Freigabe (das eine Human-Gate) ★
Micro-Live-Canary (isoliertes Konto, < 1 % des Zielkapitals, begrenzte Zeit)
        ↓  30 Tage stabil über dem Rauschen
Gestaffelter Rollout mit Kapital-Gewichtung, Bot für Bot
```

- KPIs sind vorab fixiert; das System kann eine Stufe **vorschlagen**, nie
  selbst schalten. Verfehlt ein Kandidat die KPIs, fliegt er zurück in den
  Research-Pod — keine Ausnahmen, keine Nachverhandlung.
- Die konkreten Schwellwerte (DD-Limit, Profit-Factor, Fensterlänge) legt
  Luke fest, bevor Phase 3 startet; die Zahlen oben sind Startvorschläge.
- Rollout bleibt Bot für Bot, jederzeit stopp- und rollbackfähig. Niemals die
  ganze Flotte auf einmal.

---

## Rollen

- **Research-Pod (offline):** Hypothesen, Backtests, Walk-Forward,
  Signifikanz-Prüfung. Hier dürfen LLMs mitdenken. Nur validierte Kandidaten
  verlassen den Pod.
- **Hermes:** Infrastruktur-Operator. Deployments, Monitoring,
  Runbook-Ausführung (Incident, Rollback), CI/CD, Dokumentation. Hermes
  erzeugt und merged keine Strategie-Änderungen autonom und hat weiterhin
  keinerlei Live-Autorität.
- **Risk Engine:** einzige Instanz, die Trades blockt oder Bots anhält.
  Automatisch, mathematisch, ohne Ermessensspielraum.
- **Luke:** setzt Risikobudget, KPI-Schwellen und Kapitalobergrenze; erteilt
  die Live-Freigaben. Kein operativer Flaschenhals im Tagesgeschäft — aber
  jederzeit voller Stopp-Zugriff.

Die Trennung der beiden Loops bleibt: Engineering-Loop (Code → Test → PR →
Merge) und Trading-Loop (Daten → Validierung → Gewichtung → Entscheidung)
koppeln nie automatisch ineinander.

---

## Nicht verhandelbar (bleibt aus dem alten Zielbild)

1. Dry-Run ist Default; Live nur nach expliziter menschlicher Freigabe.
2. Signal ≠ Order; LLM nie Execution Authority.
3. Kontrollgruppe für jede Wirkungsmessung.
4. Snapshot + Rollback vor jeder Änderung.
5. Append-only Evidence für **Mutationen und Freigaben** (Trades, Applies,
   Rollbacks, Approvals). Telemetrie-Logging ist asynchron/best-effort:
   Ausfall erzeugt Alarm, stoppt aber nicht den Dry-Run-Handel.
6. Kill-Switch außerhalb der Strategien; niemand kann ihn per Optimierung
   wegoptimieren.
7. Keine Secrets in Git; Credentials außerhalb des Repos.

## Bewusst NICHT übernommen aus den Kritiken

- **Vollautomatischer Live-Rollout ohne Mensch** („Graduation ohne Marker"):
  verstößt gegen SOUL.md Regel 1 und bleibt draußen. Die Vereinfachung
  besteht darin, die Freigabe auf *einen* expliziten Akt pro Stufe zu
  reduzieren — nicht darin, sie abzuschaffen.
- **„Der Mensch kann nicht eingreifen":** Selbstdisziplin des Systems ist
  richtig (Limits kann der Betrieb nicht aufweichen), aber der Mensch behält
  immer die Stopp-Autorität. Entzogen wird nur die impulsive
  *Freischaltung*, nie die Notbremse.
- **Logs/Evidence löschen und „neu anfangen":** Append-only-Evidence für
  Entscheidungen bleibt. Ohne Audit-Trail ist jedes KEEP wertlos.
- **Canary ersatzlos streichen:** ersetzt durch gewichtete Einführung mit
  echter zeitgleicher Kontrollgruppe — das behebt den berechtigten Einwand
  (unterschiedliche Marktfenster verfälschen den Vergleich), ohne ungetestete
  Änderungen auf die Flotte zu lassen.

---

## Roadmap-Phasen

### Phase 0 — Alpha-Beweis & Baseline-Bereinigung

**Ziel:** Eine Kernstrategie, die den Namen verdient.

- Bestehende Strategien gegen mehrjährige Out-of-Sample-Daten prüfen
  (Walk-Forward, Monte-Carlo-Permutation, Regime-Splits).
- Strategien ohne belegten Alpha werden verworfen, nicht weiter „verbessert".
- C4-Window-Scope-Fix (Lifetime- vs. Window-Trades) abschließen, damit
  künftige Messungen überhaupt aussagekräftig sind.

**Exit-Kriterium:** ≥ 1 Strategie mit Out-of-Sample Max-DD < 25 %,
Profit-Factor > 1.3 und über Regimes stabiler Performance.

### Phase 1 — Risk Engine 2.0

**Ziel:** Der mathematische Käfig steht, bevor irgendetwas skaliert.

- Daily Trailing Drawdown → automatisches `HALT_NEW`.
- ATR-basiertes Trade-Level-Limit → automatischer Einzel-Exit.
- `HALT_BOT` (bot-individuelle Abschaltung) implementieren.
- Evidence-Kopplung umbauen: Mutationen fail-closed, Telemetrie best-effort
  mit Alarm.

**Exit-Kriterium:** Simulierter 2026-07-Canary-Verlauf wird von der Engine
bei ≤ Tageslimit gestoppt (Replay-Test); `HALT_BOT` stoppt einen Bot ohne
Flotten-Impact.

### Phase 2 — Loop-Vereinfachung

**Ziel:** 10-Schritte-SI-v2 → 4-Schritte-Loop.

- Offline-Validierung (Walk-Forward/Signifikanz) als Pflicht-Vorstufe jedes
  Kandidaten.
- Policy-Gates auf die vier automatischen Checks reduzieren;
  Parameter-Bounds statt Allowlist.
- Gewichtete Einführung (Stake-Anteil) im Dry-Run implementieren, inkl.
  automatischem KEEP/ROLLBACK nach Sortino/Max-DD.
- Alte Prozessschritte und Formulare dekommissionieren
  (→ `docs/decommissioning-register.md`).

**Exit-Kriterium:** Ein kompletter Kandidaten-Durchlauf (Validierung →
5-%-Gewichtung → Entscheidung) läuft ohne manuellen Eingriff im Dry-Run und
ist im Evidence-Log nachvollziehbar.

### Phase 3 — Graduation-Pipeline

**Ziel:** KPI-basierter, halbautomatischer Weg Richtung Live-Kandidatur.

- Shadow-/Paper-Stage mit automatischem Backtest-Realität-Abgleich.
- KPI-Schwellen mit Luke fixieren; `LIVE_CANDIDATE`-Report-Generator bauen.
- Das eine Human-Gate implementieren: Report → explizite Freigabe →
  Stufenwechsel; alles andere an Marker-Bürokratie entfällt.

**Exit-Kriterium:** Ein Bot erreicht `LIVE_CANDIDATE` ausschließlich über
erfüllte KPIs; der Freigabe-Report enthält alle Entscheidungsdaten auf einer
Seite.

### Phase 4 — Micro-Live & gestaffelter Rollout

**Ziel:** Kontrollierter Live-Einstieg — erst nach Phase-3-Gate und Freigabe.

- Micro-Live-Canary: isoliertes Konto, < 1 % Zielkapital, festes Zeitfenster,
  Credentials außerhalb Git, getesteter Kill-Switch.
- Kapital-Gewichtung für den Rollout (5 % → 20 % → 50 % → 100 %), Bot für
  Bot, mit automatischem Rückbau bei KPI-Verletzung.
- Monitoring, Alarmierung, Incident-Runbooks vor dem ersten Live-Trade.

**Exit-Kriterium:** definiert Luke bei Freigabe von Phase 4; ohne neuen
belastbaren KEEP-Nachweis und explizite Freigabe startet diese Phase nicht.

---

## Offene Entscheidungen für Luke

1. Konkrete Zahlen für Risk Engine (Tages-DD-Limit, ATR-Multiplikator,
   globales Risikobudget).
2. KPI-Schwellen der Graduation-Pipeline (DD, Profit-Factor, Fensterlängen).
3. Welche der aktuellen vier SI-v2-Bots die Phase-0-Prüfung durchlaufen —
   und ob die Flotte bis zum Alpha-Beweis auf eine Kernstrategie schrumpft.
4. Reihenfolge/Priorität der Phasen gegenüber den laufenden Tracks in #423.
