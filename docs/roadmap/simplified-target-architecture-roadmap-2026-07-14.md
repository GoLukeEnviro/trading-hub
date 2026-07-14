# Zielarchitektur — Trading Hub (Simplified, v2 — 2026-07-14)

> **Status:** Vorschlag / Planungsdokument (L2, docs-only). Ersetzt v1 dieses
> Dokuments (gleiche Datei, Git-History).
> **Autoritative Reihenfolge:** `AGENTS.md` → `SOUL.md` →
> `docs/state/current-operational-state.md` → dieses Dokument.
> **Dokumentmodell:** Dieses Dokument ist das **stabile Zielbild**. Volatile
> Runtime-Fakten (Flottenzustand, Cycle-IDs, C4-Status, aktive Issues) leben
> ausschließlich in `docs/state/` und `docs/reports/` — sie werden hier
> referenziert, nie dupliziert.
> **Verhältnis zu Issue #423:** #423 bleibt die kanonische Task-Roadmap.
> Umsetzung der hier beschriebenen Änderungen erfolgt erst nach Freigabe durch
> Luke als eigene Issues/Tasks.
>
> Dieses Dokument autorisiert **keine** Runtime-Mutation, kein Live-Trading,
> kein `dry_run=false`, kein Exchange-Key-Deployment und keine
> Bot-/Strategie-Mutation. Live-Kapital braucht immer explizite menschliche
> Freigabe (SOUL.md Regel 1).

---

## Leitprinzipien

1. **Erst Alpha beweisen, dann Orchestrierung.** Der Nachweis-Apparat darf
   nie größer sein als das, was er beweist.
2. **Selektion statt Zentralplanung.** Der primäre Verbesserungsmechanismus
   ist Kapitalallokation: Strategien konkurrieren um Risikokapital, schlechte
   Ideen sterben schnell und billig. Kein zentraler Vorschlagsapparat, der
   jede Änderung durch zehn Gates trägt.
3. **Risiko wird mathematisch gekappt, nicht prozessual diskutiert.** Harte
   Limits mit automatischer Wirkung ersetzen Checklisten-Gates.
4. **Live-Betrieb ist das erklärte Endziel**, nicht eine optionale Ausnahme.
   Dry-Run, Shadow und Canary sind Validierungsstufen auf dem Weg dorthin —
   und der Übergang bleibt menschlich mandatiert.
5. **Unsicherheit führt zu Einschränkung, nie zu optimistischer Annahme.**

Einordnung des 82,79-%-Drawdowns (Live-Canary-Episode 07/2026): Die Gates
haben korrekt abgewickelt (ROLLBACK, D1/D2 blockiert), aber nicht verhindert.
Zusätzlich war das Messfenster selbst beeinträchtigt (HALT_NEW-Phasen, geringe
Trade-Zahl, Lifetime- statt Window-Scope). Die korrekte Lesart ist daher
nicht „Änderung als schlechter bewiesen", sondern **„Promotion unzulässig
wegen Guardrail-Verletzung und unzureichender Vergleichsevidenz"**. Beides
wird adressiert: mathematischer Käfig (verhindern) und saubere Messbasis
(beweisen).

---

## Delta v1 → v2 (was die vier Zusatz-Reviews beigesteuert haben)

| Thema | v1 | v2 |
|---|---|---|
| Verbesserungsmechanismus | 4-Schritte-Loop mit gewichteter Einführung | **Capital Allocator** als Herzstück: Allokation 0–100 % pro Strategie-Version, Darwin-Selektion |
| Strukturmodell | 3 Schichten, implizit linear | **3 Ebenen (Planes):** Data / Control / Management — keine Ebene erbt Autorität einer anderen |
| Risk-Begriff | Eine „Risk Engine" | In **drei benannte Funktionen** getrennt: Entry-Gate, Portfolio-Limits, Circuit Breaker (heute vermischt der Begriff „RiskGuard" nachweislich mehrere Dinge, s. u.) |
| Portfolio-Risiko | Global-DD und Exposure erwähnt | Explizite **Korrelations-/Konzentrationslimits** (vier Bots long Krypto = eine Wette) |
| Kill-Switch | 3 Modi + HALT_BOT | + `CANCEL_PENDING`, `REDUCE_ONLY`; **Exit-Intent ≠ bestätigte Schließung** |
| Rollback | „Snapshot + Rollback" | **Software-Rollback ≠ Trading-Recovery**: realisierte Verluste sind nicht rollbackfähig |
| Live-Freigabe | „ein Human-Gate" (Akt) | **Live-Mandat als Artefakt**: begrenzt, signiert, befristet, technisch erzwungen im Execution Gateway |
| Execution | implizit (Freqtrade) | **Execution Gateway + Reconciler**: einziger Exchange-Pfad, Idempotenz, Abgleich lokal ↔ Exchange |
| „Messbar besser" | KPIs genannt | **Entscheidungsregel definiert**: Baseline, Primärmetrik, Mindest-N, Mindestdauer, Vergleichbarkeit, sonst EXTEND |
| Bot-Optimierung | Parameter-Tweaks am Bot | **Neue Version = neue Identität** mit kleiner Start-Allokation; kein In-Place-Tuning allokierter Bots |
| Root vs. Live | Grundsatz genannt | **Technisch erzwungen**: getrennte Secret-Stores, Keys ohne Withdrawal, Live-Credentials nur im Execution Gateway |

---

## Ebenenmodell (ersetzt die lineare Pipeline)

Das alte Bild `Marktdaten → Signal → RiskGuard → Freqtrade → Messung → SI-v2
→ Hermes` suggeriert eine Befehlskette. Tatsächlich sind es drei Ebenen mit
getrennten Autoritäten:

```text
MANAGEMENT PLANE   Hermes (DevOps/Audit) · Luke (Mandate, Limits, Stopp)
                   entwickelt & betreibt — entscheidet keine Trades
─────────────────────────────────────────────────────────────────────
CONTROL PLANE      Capital Allocator · Measurement · Candidate-Lifecycle
                   verteilt Risikokapital, misst, selektiert
─────────────────────────────────────────────────────────────────────
DATA PLANE         Sensorik → Strategien → Risk Engine → Execution
                   Gateway ↔ Exchange · Reconciler
                   handelt — innerhalb der Limits, sonst gar nicht
```

Keine Ebene übernimmt stillschweigend Autorität aus einer anderen. Ein
Merge (Management) allokiert kein Kapital; eine gute Messung (Control)
erzeugt keine Order; ein profitables Signal (Data) erhöht kein Limit.

## Autoritätsmodell

| Komponente | Darf | Darf nicht |
|---|---|---|
| Sensorik / Signal-Core (inkl. Rainbow, LLM) | Regime, Kontext, Confidence liefern; Entries filtern | Orders erzeugen oder erzwingen; Limits ändern |
| Freqtrade-Strategie | Entry-/Exit-Kandidaten erzeugen | Risk Engine, Kill-Switch oder Gateway umgehen |
| Risk Engine | Kandidaten erlauben, verkleinern, blockieren; Bots anhalten | Live-Modus freigeben; Limits aufweichen |
| Capital Allocator | Risikokapital 0–100 % pro Strategie-Version verteilen | Limits überschreiten; Live-Mandat erteilen |
| Execution Gateway | mandatierte, autorisierte Orders idempotent ausführen | Orders ohne Risk-Freigabe + gültiges Mandat senden |
| Hermes | Code, Tests, Deployments, Runbooks, Evidence | Trades entscheiden; Mandate erzeugen; Gates umgehen |
| Luke | Limits, KPI-Schwellen, Live-Mandate; jederzeit Stopp | — (Stopp-Autorität ist unbegrenzt) |

---

## Data Plane

### Sensorik (advisory only)

- Deterministische, versionierte Signalerzeugung: technische Analyse,
  Marktdaten, Regime-Klassifikation. Jedes Signal trägt mindestens Quelle,
  Instrument, Richtung, Confidence, Gültigkeitsfenster, Modellversion und
  Reason-Codes — Freitext ist nie alleinige Entscheidungsgrundlage.
- Marktdaten tragen Freshness-/Qualitätsstatus; veraltete oder inkonsistente
  Daten dürfen nicht stillschweigend verwendet werden (→ Einschränkung).
- LLM-Ausgaben: nur Regime/Sentiment/Research, schema-validiert, versioniert,
  deterministischer Fallback. Nie in der Order-Kette (SOUL.md Regel 9).
- **Ein Signal ist eine Empfehlung, keine Order** — unverändert.

### Strategien (Execution Fleet)

- Maximal **4–5 Bots mit klaren Rollen** (z. B. Trend/Momentum,
  Mean-Reversion, Breakout, Adaptive/FreqAI) statt wachsender Spezialisten-
  Zoo. Skalierung ist Belohnung für belegte Performance.
- Eine Strategie erzeugt **Orderabsichten** (Intent), keine Orders. Jede
  Absicht referenziert Bot-ID, Strategie-Version, Größe und Begründung.
- Begriffsschärfe: logische Bot-Identität ≠ deployte Flotte ≠ Messflotte ≠
  Kontrollgruppe. Welche Bots aktuell laufen, steht nur im State-Dokument.
  Support-Dienste (Rainbow, Dashboard, Webserver) zählen nie als Bots.

### Risk Engine — drei getrennte Funktionen

Der heutige Sammelbegriff „RiskGuard" vermischt nachweislich mehrere Dinge
(z. B. bleibt `BLOCK_ENTRY` in mindestens einem Helper-Pfad bewusst neutral,
`orchestrator/scripts/run_12h_observation_gate.py:371`). Das Zielbild trennt:

1. **Entry-Gate** (pro Orderabsicht): prüft Größe, Stop-Regeln, Datenqualität,
   Kill-Switch-Zustand. Verdikt: `APPROVE` / `RESIZE` / `REJECT` /
   `REDUCE_ONLY`. Die restriktivste Entscheidung gewinnt, immer.
2. **Portfolio-Limits** (laufend): Gesamt-Drawdown, Tages-Trailing-Drawdown
   (Berührung → automatisch `HALT_NEW` bis Tagesende), Brutto-/Netto-Exposure,
   **Korrelations- und Konzentrationslimits** — vier Bots long in
   korrelierten Assets sind eine Wette, nicht vier Strategien.
3. **Bot-Circuit-Breaker** (`HALT_BOT`): ein absaufender Bot verliert seine
   Allokation und wird isoliert, ohne die Flotte zu stoppen. Zusätzlich
   ATR-basierter Verlustdeckel pro Trade → automatischer Einzel-Exit.

Kill-Switch (flottenweit, außerhalb der Strategien; heute
`freqtrade/shared/kill_switch.py`):

| Modus | Wirkung |
|---|---|
| `NORMAL` | regulärer Betrieb |
| `HALT_NEW` | keine neuen Entries, Positionen bleiben |
| `CANCEL_PENDING` | zusätzlich offene Entry-Orders stornieren |
| `REDUCE_ONLY` | nur risikoreduzierende Aktionen erlaubt |
| `EMERGENCY` | Entries blockiert + Exit-Intent für alle Positionen |

Wichtig: `EMERGENCY` erzeugt einen **Exit-Intent**. Erst Exchange-/
Freqtrade-Evidence beweist, dass Positionen tatsächlich geschlossen sind.
Die Emergency-Policy definiert Slippage-Grenzen, Reihenfolge und Verhalten
bei nicht erreichbarer Exchange — pauschales Market-Schließen in illiquiden
Märkten kann Schaden vergrößern.

### Execution Gateway & Reconciler

- **Nur das Execution Gateway sendet Orders an eine Exchange.** Es akzeptiert
  ausschließlich Absichten mit Risk-Freigabe und (für Live) gültigem Mandat.
  Es verantwortet Idempotency-Keys, Retries, Rate-Limits, Teilfüllungen,
  Precision/Min-Notional und Schutz vor Doppel-Ausführung.
- **Reconciler:** vergleicht regelmäßig lokalen erwarteten Zustand gegen den
  tatsächlichen Exchange-Zustand (Positionen, offene Orders, verlorene
  Antworten, manuelle Eingriffe). Bei Drift wird nicht weitergehandelt,
  sondern automatisch eingeschränkt (`REDUCE_ONLY`/`HALT_BOT`) und eskaliert.
- **Root ≠ Live, technisch erzwungen:** Live-Credentials existieren nur im
  Execution Gateway (eigener Secret-Store), Exchange-Keys ohne
  Withdrawal-Rechte, getrennte Keys für Dry-Run/Canary/Live. Hermes' Root-
  oder Repo-Zugriff führt an keiner Stelle zu einem Order-Pfad.

---

## Control Plane

### Capital Allocator (das Herzstück)

Ersetzt den zentralen 10-Schritte-SI-v2-Prozess als primären
Verbesserungsmechanismus:

- Verteilt laufend **Risikokapital (0–100 %)** pro Bot/Strategie-Version nach
  regime-adjustierter Contribution: Sortino/Calmar, Max-DD, Recovery Factor,
  Korrelation zum Restportfolio.
- **Neue Variante = neue Identität + kleine Start-Slice (2–5 %).** Kein
  In-Place-Tuning eines Bots, der Allokation hält. Alte Version läuft als
  zeitgleiche Kontrollgruppe weiter — dasselbe Marktfenster, dieselben
  Kostenannahmen.
- Positive Contribution über das Mindestfenster → Slice steigt stufenweise
  (5 % → 20 % → 50 % → 100 %), automatisch. Negative Contribution oder
  Guardrail-Breach → Slice fällt automatisch, bei 0 stirbt die Version.
- Im Dry-Run ist das ein virtuelles Stake-Budget; im Live-Betrieb echtes
  Kapital strikt innerhalb des Mandats.
- SI-v2-Komponenten (Analyzer, Measurement, Evidence) bleiben als **Analyse-
  und Mess-Werkzeuge** des Allocators erhalten — sie verlieren die Rolle als
  zentrale Änderungs-Pipeline.

### Entscheidungsregel „messbar besser" (vorab fixiert, sonst gilt EXTEND)

- **Baseline:** die weiterlaufende alte Version, zeitgleich, gleiche Pairs,
  gleiches Kapitalbudget, gleiche Kosten-/Slippage-Annahmen.
- **Primärmetrik:** eine (z. B. regime-adjustierter Sortino); Guardrails
  daneben: Max-DD, Tail-Loss, Exposure, operative Fehlerrate.
- **Mindeststichprobe und Mindestdauer** pro Entscheidung (Zahlen setzt
  Luke, s. offene Entscheidungen); offene Trades und Fenster-Scope sind
  definiert (Lehre aus dem C4-Lifetime/Window-Bug).
- Kandidaten durchlaufen **Offline-Validierung vor Runtime-Kontakt**:
  Out-of-Sample, Walk-Forward, Leakage-/Look-ahead-Prüfung,
  Kosten-Simulation. Das adressiert Overfitting strukturell — nicht ein
  kurzes Canary-Zeitfenster.
- `KEEP` heißt ausschließlich: **die aktuelle Stufe wurde bestanden.** Es ist
  nie eine Live-Freigabe und autorisiert nur den nächsten definierten Schritt.

### Gate-Modell (zweistufig statt 10-stufig)

**Kleine Dry-Run-Experimente** (neue Slice ≤ Startgröße, Parameter innerhalb
Bounds): keine Prozess-Gates. Es gelten nur die automatischen Invarianten —
Parameter-Bounds, Snapshot vorhanden, Evidence-Schreibung, Kill-Switch
`NORMAL`, Observability. Geschwindigkeit kommt aus dieser Klasse.

**Skalierung und Live** (Slice über Schwellwert, z. B. > 20 %, oder Übergang
zu echtem Kapital): vier harte Gates —

| Gate | Art | Wirkung |
|---|---|---|
| Portfolio Risk Gate | automatisch, laufend | blockiert/verkleinert bei DD-, Exposure-, Korrelationsverletzung |
| Bot-Circuit-Breaker | automatisch, laufend | Einzelbot auf 0, Flotte läuft weiter |
| Kill-Switch | Mensch + definierte Auto-Trigger | flottenweiter Stopp |
| **Live-Mandat** | Mensch, hart | ohne gültiges Mandat lehnt das Gateway Live-Orders technisch ab |

Der RuntimeEffectProof bleibt als **ein automatischer Check** bei jedem
Apply erhalten (läuft die Version wirklich, `dry_run` unverändert, Bot
gesund?) — nicht als eigener Prozessschritt mit Berichtspflicht.

---

## Management Plane

### Hermes — DevOps, Audit, Executor

- Baut, testet, deployt, überwacht, führt Runbooks aus (Incident, Rollback),
  pflegt Evidence und State. **Keine Trading-Entscheidungen, keine eigene
  Priorisierung trading-relevanter Änderungen** — Prioritäten kommen vom
  Allocator (erkannte Underperformance), von Luke oder aus freigegebenen
  Issues.
- Engineering-Disziplin: ein Task, ein Branch, ein PR, ein Report — ergänzt
  um den **Single-Writer-Vertrag**: globaler Writer-Lock, isolierter
  Worktree, gepinnter `origin/main`-SHA, harter Stopp bei
  `BLOCKED_BY_ACTIVE_REPO_WRITER`. Definierte Runbook-Ausnahmen (Incident,
  Secret-Rotation, dringender Rollback) statt stillschweigender Regelbrüche.
- Bei widersprüchlichen Quellen: stoppen und Source-of-Truth-Hierarchie
  anwenden, nie eine neue Wahrheit erfinden.

### Luke — Mandate und Limits

Setzt Risikobudget, KPI-Schwellen, Kapitalobergrenze; erteilt Live-Mandate;
hat jederzeit unbegrenzte Stopp-Autorität. Kein operativer Flaschenhals im
Experiment-Alltag.

---

## Live-Mandat (ersetzt Marker-Bürokratie)

Live-Freigabe ist kein boolescher Marker, sondern **ein begrenztes,
technisch geprüftes Mandat** — genau ein menschlicher Akt pro Stufe, aber
mit Substanz:

```text
approval_id · approved_by · bot_id · strategy_version · commit/image-digest
exchange · account · erlaubte Instrumente
max_capital · max_position_size · max_daily_loss · max_drawdown
valid_from · valid_until · widerrufbar · nicht wiederverwendbar
```

Das Execution Gateway validiert das Mandat vor jeder Live-Order; abgelaufen
oder widerrufen → technische Ablehnung. Damit ist die Live-Grenze kein
Prozessversprechen mehr, sondern Code.

## Graduation-Pipeline

```text
Offline: Backtest + Walk-Forward (Out-of-Sample, Leakage-geprüft, Kosten real)
        ↓  harte KPIs bestanden
Shadow / Paper auf Echtzeitdaten — Abgleich gegen Backtest-Erwartung,
        signifikante Abweichung = Stopp + Diagnose
        ↓
Dry-Run mit Allocator-Slice (Mindestfenster, z. B. ≥ 30 Tage)
        ↓  z. B.: Max-DD < 8 %, Profit-Factor > 1.3, stabile Ausführung
LIVE_CANDIDATE — automatischer Report mit allen Entscheidungsdaten
        ↓  ★ Live-Mandat durch Luke (das eine Human-Gate) ★
Micro-Live-Canary — isoliertes Konto, < 1 % Zielkapital, befristet
        ↓  Dry-Run beweist keine Live-Parität (Fills, Slippage, Rate-Limits,
            Min-Notional) — deshalb ist diese Stufe Pflicht
Gestaffelter Rollout — pro Schritt nur EINE Dimension erhöhen
(Kapital ODER Instrumente ODER Laufzeit), Bot für Bot, automatischer
Rückbau bei KPI-Verletzung
```

## Nicht verhandelbar

1. Dry-Run ist Default; Live nur mit gültigem menschlichem Mandat.
2. Signal ≠ Order; LLM nie Execution Authority.
3. Zeitgleiche Kontrollgruppe für jede Wirkungsmessung.
4. Snapshot + Rollback vor jeder Änderung — und begrifflich sauber:
   **Software-Rollback ≠ Trading-Recovery.** Realisierte Verluste, Slippage
   und Gebühren sind nicht rollbackfähig; für Positionen gibt es
   Containment (`CANCEL_PENDING`, `REDUCE_ONLY`, kontrollierter Unwind).
5. Append-only Evidence für Mutationen, Allokationsänderungen und Mandate —
   mit Härtung (Hash-Verkettung oder externe Kopie), denn eine lokale
   JSONL-Datei allein ist nicht manipulationssicher. Telemetrie bleibt
   asynchron/best-effort: Ausfall alarmiert, stoppt aber keinen Dry-Run.
6. Kill-Switch außerhalb der Strategien; per Optimierung nicht erreichbar.
7. Keine Secrets in Git; Live-Credentials nur im Execution Gateway; Keys
   ohne Withdrawal-Rechte.
8. Fehlende oder widersprüchliche Evidence → `BLOCKED`/`EXTEND`, nie
   optimistische Annahme. Teilerfolg wird nie als Gesamterfolg protokolliert.

## Bewusst NICHT übernommen aus den Reviews

- **Vollautomatischer Live-Einstieg / „Graduation ohne Mensch":** bleibt
  draußen (SOUL.md Regel 1). Vereinfachung heißt: *ein* Mandat pro Stufe
  statt Marker-Kette — nicht null.
- **„Fast keine Gates für kleine Experimente":** Richtung übernommen, aber
  Bounds, Snapshot und Evidence bleiben auch für kleine Dry-Run-Experimente —
  sie sind automatisch und kosten Millisekunden, keine Prozesszeit.
- **Evidence/Logs entwerten oder löschen:** ohne Audit-Trail ist jedes KEEP
  wertlos. Stattdessen wird Evidence gehärtet und auf das
  Entscheidungsrelevante fokussiert.
- **Sofortige Voll-Spezifikation aller Contracts/Schemas** (Reviews 3+4):
  Die Ontologie (Ebenen, Autoritäten, Mandat, Reconciler) ist übernommen;
  maschinenlesbare Runtime-Contracts und ein ausführbarer Hermes-Prompt sind
  als spätere Artefakte vorgesehen (Phase 3), nicht als Vorbedingung für
  Phase 0 — sonst bauen wir wieder das Labor vor dem Alpha.

## Roadmap-Phasen

### Phase 0 — Alpha-Beweis & saubere Messbasis

**Ziel:** Eine Kernstrategie mit belegtem Edge und eine Messung, der man
trauen kann.

- Bestehende Strategien gegen mehrjährige Out-of-Sample-Daten prüfen
  (Walk-Forward, Monte-Carlo, Regime-Splits, reale Kosten/Slippage).
  Strategien ohne belegten Alpha werden verworfen, nicht „verbessert".
- Messbasis fixen: C4-Window-Scope (Lifetime vs. Window), Vergleichbarkeits-
  Standards (gleiches Kapital, Pairs, Fenster, Kosten), Umgang mit offenen
  Trades definieren.
- Flottenrollen festlegen (max. 4–5) und die Begriffe logische Identität /
  deployte Flotte / Messflotte im State-Dokument sauber trennen.

**Exit:** ≥ 1 Strategie mit Out-of-Sample Max-DD < 25 %, Profit-Factor > 1.3,
regime-stabil; Entscheidungsregel „messbar besser" schriftlich fixiert.

### Phase 1 — Risk Engine & Käfig

**Ziel:** Der mathematische Käfig steht, bevor irgendetwas skaliert.

- Daily-Trailing-Drawdown → automatisches `HALT_NEW`; ATR-Trade-Deckel →
  automatischer Einzel-Exit; `HALT_BOT`-Circuit-Breaker.
- Portfolio-Limits: Brutto-/Netto-Exposure, Korrelations-/Konzentrations-
  grenzen über die Flotte.
- Kill-Switch um `CANCEL_PENDING` und `REDUCE_ONLY` erweitern;
  Emergency-Policy (Slippage-Grenzen, Reihenfolge, Exchange nicht erreichbar)
  definieren; Exit-Intent-vs.-bestätigte-Schließung in Evidence trennen.
- Risk-Funktionen begrifflich und im Code entflechten (Entry-Gate /
  Portfolio-Limits / Circuit Breaker), `BLOCK_ENTRY`-Semantik vereinheitlichen.

**Exit:** Replay des 07/2026-Canary-Verlaufs wird bei ≤ Tageslimit gestoppt;
`HALT_BOT` isoliert einen Bot ohne Flotten-Impact; Korrelationslimit
verhindert im Test die Vier-Bots-eine-Wette-Konstellation.

### Phase 2 — Capital Allocator (MVP) & Loop-Vereinfachung

**Ziel:** Selektion über Allokation ersetzt die 10-Schritte-Pipeline.

- Allocator MVP im Dry-Run: virtuelles Stake-Budget, Slices, automatisches
  Hoch-/Runterstufen nach der fixierten Entscheidungsregel.
- Neue-Version-=-neue-Identität-Mechanik: Kandidaten aus Offline-Validierung
  starten mit 2–5 % Slice gegen die weiterlaufende alte Version.
- Zweistufiges Gate-Modell aktivieren; alte Prozessschritte und Formulare
  dekommissionieren (→ `docs/decommissioning-register.md`); SI-v2-Analyzer/
  Measurement als Allocator-Werkzeuge weiterverwenden.
- Evidence-Härtung: Hash-Verkettung oder externe Kopie für Entscheidungs-
  Records.

**Exit:** Ein kompletter Durchlauf (Offline-Validierung → 5-%-Slice →
automatische Hoch-/Runterstufung → KEEP/ROLLBACK) läuft ohne manuellen
Eingriff im Dry-Run und ist im Evidence-Log nachvollziehbar.

### Phase 3 — Execution-Reife & Live-Mandat-Mechanik

**Ziel:** Alles, was Live technisch voraussetzt — vor dem ersten Live-Euro.

- Execution Gateway härten: Idempotency, Teilfüllungen, Rate-Limits,
  Min-Notional, Doppel-Order-Schutz.
- Reconciler bauen: Positions-/Order-Abgleich lokal ↔ Exchange, Drift →
  automatische Einschränkung + Alarm.
- Live-Mandat-Mechanik implementieren (Artefakt + Gateway-Validierung);
  Secret-Trennung (eigener Store, Keys ohne Withdrawal, getrennte
  Dry/Canary/Live-Keys).
- `LIVE_CANDIDATE`-Report-Generator: alle Entscheidungsdaten auf einer Seite.
- Runtime-Contract und Hermes-Runbooks als eigenständige Artefakte ausgliedern.

**Exit:** Ein Bot erreicht `LIVE_CANDIDATE` ausschließlich über erfüllte
KPIs; Gateway lehnt Live-Orders ohne gültiges Mandat nachweislich ab
(Test); Reconciler erkennt injizierten Drift und schränkt ein.

### Phase 4 — Micro-Live & gestaffelter Rollout

**Ziel:** Kontrollierter Live-Einstieg — startet nur mit gültigem Mandat.

- Micro-Live-Canary: isoliertes Konto, < 1 % Zielkapital, befristetes Mandat,
  engere Kill-Switch-Grenzen, erhöhte Beobachtung.
- Skalierung: pro Schritt genau eine Dimension (Kapital, Instrumente,
  Laufzeit), Bot für Bot, automatischer Rückbau bei KPI-Verletzung;
  jede Erweiterung = neues/erweitertes Mandat.
- Monitoring/Alarme vor dem ersten Trade: Position-Drift, Order-Drift,
  Verlustgrenzen, stale Daten, Mandats-/Versions-Mismatch.

**Exit:** definiert Luke bei Mandatserteilung; ohne belastbaren KEEP aus
Phase 2/3 und gültiges Mandat startet diese Phase nicht.

---

## Offene Entscheidungen für Luke

1. **Risk-Zahlen:** Tages-DD-Limit (3–5 %?), ATR-Multiplikator, globales
   Risikobudget, Korrelations-/Konzentrationsgrenzen.
2. **Allocator-Parameter:** Start-Slice (2–5 %?), Stufen, Schwellwert für das
   Human-Gate bei Skalierung (> 15–20 % Portfolioanteil?).
3. **Entscheidungsregel-Zahlen:** Primärmetrik, Mindest-Trades, Mindestdauer
   (Dry-Run-Fenster 30 Tage vs. konservativere 3–6 Monate vor Live-Kandidatur
   — die Reviews divergieren hier bewusst).
4. **Flottenrollen:** welche der bestehenden Bots die Phase-0-Prüfung
   durchlaufen; ob die Flotte bis zum Alpha-Beweis auf eine Kernstrategie
   schrumpft.
5. **Priorität** der Phasen gegenüber den laufenden Tracks in Issue #423.
