# Architekturvorschlag — Trading Hub Zielbild (Kandidat, v3 — 2026-07-14)

> **Status:** Vorschlag / Planungsdokument (L2, docs-only). Kein beschlossenes
> Zielbild. Ersetzt v1/v2 dieser Datei (Git-History).
> **Source of Truth:** Konflikte werden ausschließlich nach der in `AGENTS.md`
> (Abschnitt „Source-of-truth order") definierten Hierarchie aufgelöst. Dieses
> Dokument besitzt keine eigene Konfliktpriorität und keine Autorität über
> Runtime-Evidence, aktive ADRs, den Operational State oder Issue #423.
> **Governance:** SI-v2 bleibt per aktiver ADR
> (`ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md`) die
> verbindliche Self-Improvement-Architektur. Der hier vorgeschlagene Capital
> Allocator ersetzt nichts, bevor eine supersedierende ADR das beschließt.
> Bis dahin bleiben **alle aktiven Dry-Run-Sicherheitsinvarianten** (canary-first,
> Allowlist, Snapshot, Audit, Messplan, Rollback, Cooldown) maschinell erzwungen.
>
> Dieses Dokument autorisiert **keine** Runtime-Mutation, kein Live-Trading,
> kein `dry_run=false` und kein Exchange-Key-Deployment. Live-Kapital braucht
> immer explizite menschliche Freigabe (SOUL.md Regel 1).

---

## Leitprinzipien

1. **Erst Edge-Evidenz, dann Orchestrierung.** Der Nachweis-Apparat darf nie
   größer sein als das, was er beweist.
2. **Selektion statt Zentralplanung.** Verbesserung läuft über Kapitalallokation:
   Strategie-Versionen konkurrieren um Risikobudget, schlechte sterben billig.
3. **Geplantes Risiko wird mathematisch begrenzt.** Harte Limits mit
   automatischer Wirkung statt Prozess-Checklisten. Realisierte Verluste können
   durch Gaps, Slippage und Ausführungsrisiken dennoch höher ausfallen — auch
   deshalb bleiben Portfolio-Limits und Containment Pflicht.
4. **Live ist das Endziel, menschlich mandatiert.** Dry-Run, Shadow und Canary
   sind Validierungsstufen, keine Endzustände.
5. **Unsicherheit führt zu Einschränkung, nie zu optimistischer Annahme.**

**Lehre aus C4 (07/2026, Canary im Dry-Run):** `ROLLBACK_RECOMMENDED` bleibt
auch window-korrekt fachlich gültig (Max-DD 75,08 %, Sharpe −0,18 — beides
Breaches; siehe `docs/reports/c4-decision-triage-2026-07-03.md`). Der
Lifetime-vs.-Window-Fehler ändert daran nichts, begrenzt aber die saubere
kausale Attribution und muss vor jedem neuen Vergleichsfenster behoben sein.
Konsequenz: mathematischer Käfig (verhindern) und saubere Messbasis (beweisen).

---

## Ebenenmodell

```text
MANAGEMENT PLANE   Hermes (DevOps/Audit) · Luke (Mandate, Limits, Stopp)
                   entwickelt & betreibt — entscheidet keine Trades
─────────────────────────────────────────────────────────────────────
CONTROL PLANE      Capital Allocator · Measurement · Candidate-Lifecycle
                   verteilt Risikobudget, misst, selektiert
─────────────────────────────────────────────────────────────────────
DATA PLANE         Sensorik → Strategien → Risiko-Funktionen →
                   Execution ↔ Exchange · Reconciler
```

Keine Ebene erbt stillschweigend Autorität einer anderen: Ein Merge allokiert
kein Kapital, eine gute Messung erzeugt keine Order, ein profitables Signal
erhöht kein Limit.

## Autoritätsmodell

| Komponente | Darf | Darf nicht |
|---|---|---|
| Sensorik (inkl. Rainbow, LLM) | Regime, Kontext, Confidence liefern; Entries filtern | Orders erzeugen; Limits ändern |
| Freqtrade-Strategie | Entry-/Exit-Kandidaten erzeugen | Risiko-Funktionen oder Execution-Grenze umgehen |
| Risiko-Funktionen | erlauben, verkleinern, blockieren, Bots anhalten | Live freigeben; Limits aufweichen |
| Capital Allocator | Risikobudget innerhalb fester Grenzen verschieben | Budgets/Caps erhöhen; Mandate erteilen |
| Execution-Grenze | autorisierte, mandatierte Orders idempotent ausführen | Orders ohne Freigabe + gültiges Mandat senden |
| Hermes | Code, Tests, Deployments, Runbooks, Evidence | Trades entscheiden; Mandate erzeugen; Gates umgehen |
| Luke | jederzeit stoppen; Limits und Mandate innerhalb des Governance-Vertrags setzen | Evidence-, Mandats- oder Safety-Checks per Operator-Aktion umgehen; Stopp als impliziten Restart behandeln |

Stoppen ist unilateral. Starten und Eskalieren bleiben formal und technisch
begrenzt — auch für den Menschen.

---

## Data Plane

**Sensorik (advisory only).** Deterministische, versionierte Signale mit
Confidence, Gültigkeitsfenster und Reason-Codes; Marktdaten mit
Freshness-Status. LLM nur für Regime/Research, schema-validiert, nie in der
Order-Kette. Ein Signal ist eine Empfehlung, keine Order.

**Strategien.** Maximal 4–5 Bots mit klaren Rollen. Eine Strategie erzeugt
Orderabsichten (Intent ≠ Order). Welche Bots aktuell laufen, steht nur im
State-Dokument; Support-Dienste zählen nie als Bots.

**Risiko — drei getrennte Funktionen** (der heutige Sammelbegriff „RiskGuard"
vermischt sie; Entflechtung inkl. einheitlicher `BLOCK_ENTRY`-Semantik ist
Phase-1-Arbeit):

1. **Entry-Gate** (pro Orderabsicht): `APPROVE` / `RESIZE` / `REJECT` /
   `REDUCE_ONLY` — die restriktivste Entscheidung gewinnt.
2. **Portfolio-Limits** (laufend): Drawdown auf drei Uhren (Kalendertag,
   rollierende 24 h, High-Water-Mark) → automatisch `HALT_NEW`;
   Brutto-/Netto-Exposure; Korrelations-/Konzentrationsgrenzen (vier Bots
   long in korrelierten Assets sind eine Wette). Berechnungsmethode der
   Korrelation wird in Phase 1 festgelegt.
3. **Bot-Circuit-Breaker** (`HALT_BOT`, vorgeschlagen): isoliert einen Bot,
   Flotte läuft weiter. Positionsgröße folgt aus erlaubtem Kapitalrisiko
   geteilt durch ATR-basierte Stop-Distanz — ATR bestimmt die Distanz,
   nicht das akzeptierte Risiko.

**Kill-Switch** (flottenweit, außerhalb der Strategien):

| Modus | Wirkung | Status |
|---|---|---|
| `NORMAL` / `HALT_NEW` / `EMERGENCY` | Betrieb / keine neuen Entries / Entries blockiert + Exit-Intent | implementiert (`freqtrade/shared/kill_switch.py`) |
| `CANCEL_PENDING` / `REDUCE_ONLY` | Entry-Orders stornieren / nur risikoreduzierend | vorgeschlagene Erweiterung |

`EMERGENCY` erzeugt einen **Exit-Intent** — erst Exchange-Evidence beweist die
Schließung. Die konkrete Emergency-Policy (Slippage-Grenzen, Reihenfolge,
Exchange nicht erreichbar) gehört ins Runbook, nicht hierher.

**Execution-Grenze und Reconciler.** Entscheidung für den einfachen Weg:
**Freqtrade bleibt die Ausführungsinstanz.** Die Execution-Grenze ist eine
logische Sicherheitsschicht am Freqtrade-Exchange-Adapter (Risk-Freigabe +
Mandatsprüfung + Idempotenz), kein neues paralleles Order-System. Ein
separates zentrales Gateway wäre eine eigene, spätere ADR — nur falls die
Adapter-Lösung nachweislich nicht reicht. Der **Reconciler** gleicht lokalen
Zustand gegen den tatsächlichen Exchange-Zustand ab (Positionen, offene
Orders, verlorene Antworten); bei Drift wird automatisch eingeschränkt, nie
optimistisch weitergehandelt.

**Root ≠ Live.** Auf demselben Host ist diese Trennung nicht allein durch
Konfiguration erzwingbar — ein Root-Prozess kann lokale Prüfungen prinzipiell
umgehen. Deshalb gilt als Live-Voraussetzung (Phase 3): Das Live-Mandat wird
**extern signiert**, der Signaturschlüssel liegt nie auf HermesTrader,
Live-Credentials liegen außerhalb des von Hermes kontrollierbaren
Trust-Bereichs, Exchange-Keys ohne Withdrawal-Rechte, getrennte Keys für
Dry-Run/Canary/Live. Bis dahin ist die Trennung Konvention, nicht Beweis —
und wird auch so benannt.

---

## Control Plane

### Capital Allocator (vorgeschlagenes Modell)

- Verteilt **Risikobudget** (nicht Kontostand): Summe aller Slices ≤ festes
  Gesamtbudget; Caps pro Strategie; Korrelationsgruppen haben gemeinsame
  Obergrenzen. Budgets und Caps werden **niemals automatisch erhöht**.
- **Neue Version = neue Identität** mit kleiner Start-Slice (z. B. 2 %).
  Keine In-Place-Änderung an einer allokierten Strategie-Version.
- Automatische Stufung (z. B. 2 % → 5 % → 10 % → 20 %) gilt nur für
  virtuelles Budget im Dry-Run/Paper. Oberhalb des Schwellwerts und für jede
  Live-Reallokation gilt: nur innerhalb eines gültigen, signierten Mandats.
- Feste Rebalancing-Frequenz mit Hysterese (Slice ändert sich nur bei
  signifikanter Metrik-Differenz) — kein minütliches Oszillieren.
- SI-v2-Analyzer/Measurement/Evidence bleiben als Werkzeuge erhalten; das
  Verhältnis Allocator ↔ SI-v2 entscheidet die Vorentscheidungs-ADR.

### Vergleichsmodi (Kontrollgruppe sauber definiert)

```text
OFFLINE_AB       beide Versionen simuliert auf identischen Daten
PAPER_PARALLEL   beide Versionen virtuell auf Echtzeitdaten
LIVE_CHALLENGER  nur der Challenger erhält kleines echtes Kapital;
                 Baseline bleibt Paper oder getrennter Subaccount
```

Eine zeitgleiche echte Live-Kontrollgruppe mit demselben Kapital gibt es
nicht — sie würde Orders duplizieren und sich selbst verfälschen.

### Entscheidungsregel (vorab fixiert, sonst gilt EXTEND)

Promotion einer Version nur, wenn **alle** Bedingungen erfüllt sind:
Mindestdauer **und** Mindestzahl geschlossener Trades **und** Abdeckung
mehrerer Marktregime **und** ausreichend enges Unsicherheitsintervall der
vorab fixierten Primärmetrik; Guardrails (Max-DD, Tail-Loss, Fehlerrate)
unverletzt; Fenster-Scope und offene Trades definiert. `KEEP` heißt
ausschließlich: die aktuelle Stufe wurde bestanden. **RuntimeEffectProof**
bleibt ein obligatorisches, persistiertes Evidence-Artefakt — ohne `GREEN`
beginnt kein Messfenster.

### Gate-Modell

**Kleine Dry-Run-Experimente:** keine manuelle Einzelzeremonie — aber alle
aktiven Sicherheitsinvarianten bleiben maschinell erzwungen (siehe
Governance-Hinweis im Kopf). Automatisch heißt nicht abwesend.

**Skalierung über Schwellwert und Live:** vier harte Gates — Portfolio-Limits
(automatisch), Bot-Circuit-Breaker (automatisch), Kill-Switch (Mensch +
definierte Auto-Trigger), **Live-Mandat** (Mensch; ohne gültiges Mandat lehnt
die Execution-Grenze Live-Orders technisch ab).

### Fail-closed-Klassifizierung

| Datenklasse fällt aus | Verhalten |
|---|---|
| Kill-Switch-Status | `HALT_NEW`, fail-closed |
| Reconciliation / Mandatsprüfung | `REDUCE_ONLY` bzw. Live-Ablehnung |
| Marktdaten-Freshness | betroffene Strategie stoppt |
| Mess-/Attributions-Evidence | Applies, Allokationsänderungen, Promotions pausieren |
| Reporting/Dashboards | Alarm; sicherer Dry-Run läuft weiter |

---

## Management Plane

**Hermes:** DevOps, Audit, Executor. Baut, testet, deployt, führt Runbooks
aus, pflegt Evidence und State. Keine Trading-Entscheidungen, keine eigene
Priorisierung trading-relevanter Änderungen. Single-Writer-Vertrag (Lock,
isolierter Worktree, gepinnter SHA, harter Stopp bei
`BLOCKED_BY_ACTIVE_REPO_WRITER`); definierte Runbook-Ausnahmen für Incident,
Secret-Rotation, Rollback. Bei Quellkonflikten: stoppen und
AGENTS.md-Hierarchie anwenden.

**Luke:** setzt Risikobudget, Schwellen, Kapitalobergrenze; erteilt Mandate;
unbegrenzte Stopp-Autorität — Start- und Eskalationsautorität nur innerhalb
des Governance-Vertrags (siehe Autoritätstabelle).

## Live-Mandat

Live-Freigabe ist ein **begrenztes, extern signiertes, befristetes,
widerrufbares, nicht wiederverwendbares Mandat** — genau ein menschlicher Akt
pro Stufe:

```text
approval_id · approved_by · bot_id · strategy_version · commit/image-digest
exchange · account · erlaubte Instrumente
max_capital · max_position_size · max_daily_loss · max_drawdown
valid_from · valid_until
```

Die Execution-Grenze validiert das Mandat vor jeder Live-Order; abgelaufen
oder widerrufen → technische Ablehnung.

## Graduation

```text
Offline: Out-of-Sample + Walk-Forward, unangetastetes Holdout, reale Kosten,
         Auswahlkorrektur bei vielen getesteten Varianten
   ↓ bestanden
Paper/Dry-Run mit Allocator-Slice; Abgleich gegen Backtest-Erwartung
   ↓ z. B. LIVE_CANDIDATE erst ab hoher Slice-Stufe über mehrere Fenster
LIVE_CANDIDATE-Report (alle Entscheidungsdaten auf einer Seite)
   ↓ ★ Live-Mandat durch Luke ★
Micro-Live-Canary (isoliertes Konto, < 1 % Zielkapital, befristet)
   — Pflichtstufe: Dry-Run beweist keine Live-Parität —
   ↓
Skalierung: pro Schritt genau EINE Dimension (Kapital, Instrumente,
Laufzeit), Bot für Bot, automatischer Rückbau bei Verletzung,
jede Erweiterung = neues Mandat
```

## Nicht verhandelbar

1. Dry-Run ist Default; Live nur mit gültigem menschlichem Mandat.
2. Signal ≠ Order; LLM nie Execution Authority.
3. Definierter Vergleichsmodus (OFFLINE_AB / PAPER_PARALLEL /
   LIVE_CHALLENGER) für jede Wirkungsmessung.
4. **Keine In-Place-Änderung an einer allokierten Strategie-Version.**
5. Software-Rollback ≠ Trading-Recovery: realisierte Verluste sind
   irreversibel; für Positionen gibt es Containment und Unwind.
6. Append-only, gehärtete Evidence (Hash-Verkettung oder externe Kopie) für
   Mutationen, Allokationsänderungen und Mandate; Ausfallverhalten nach der
   Fail-closed-Klassifizierung.
7. Kill-Switch außerhalb der Strategien; per Optimierung nicht erreichbar.
8. Keine Secrets in Git; Live-Credentials außerhalb des Hermes-Trust-Bereichs;
   Keys ohne Withdrawal-Rechte.
9. Fehlende oder widersprüchliche Evidence → `BLOCKED`/`EXTEND`; Teilerfolg
   wird nie als Gesamterfolg protokolliert.

## Weg dorthin

Die Phasen sind nicht strikt seriell — Offline-Arbeit läuft parallel; streng
gegated ist nur, was Runtime oder Kapital berührt.

**Vorentscheidung (eine ADR, vor allem anderen):** Verhältnis Allocator ↔
SI-v2 (ersetzt / ergänzt / später), Bestätigung des Execution-Pfads
(Freqtrade-Adapter-Grenze), Reconciliation mit Issue #423. *Exit: kein
Widerspruch mehr zwischen ADR, AGENTS.md, SOUL.md, #423 und diesem Bild.*

**Phase 0 — Edge-Evidenz & Messbasis.** Bestehende Strategien gegen
mehrjährige Out-of-Sample-Daten (inkl. Holdout, reale Kosten,
Auswahlkorrektur). C4-Window-Scope-Fix und Vergleichbarkeits-Standards.
*Exit: ≥ 1 Strategie mit belastbarer Edge-Evidenz (z. B. OOS Max-DD < 25 %,
Profit-Factor > 1,3, Mindest-Trades, regime-stabil) — **oder** die explizite
Feststellung, dass keine besteht.* Diese Phase ist eine Weggabelung: ohne
Edge-Evidenz gibt es keinen Pfad zu Live-Kapital, nur Research.

**Phase 1 — Risiko-Käfig.** Drei-Uhren-Drawdown → `HALT_NEW`;
Positionsgrößen-Formel; `HALT_BOT`; Korrelationsmethode festlegen und
Portfolio-Limits aktivieren; Kill-Switch-Erweiterungen; RiskGuard-Entflechtung.
*Exit: Replay des C4-Verlaufs wird bei ≤ Tageslimit gestoppt; `HALT_BOT`
isoliert ohne Flotten-Impact; Korrelationslimit greift im Test.*

**Phase 2 — Allocator im Dry-Run/Paper.** Virtuelles Budget, Slices,
Hysterese, automatisches Stufen nach der Entscheidungsregel;
Neue-Identität-Mechanik; Evidence-Härtung; Dekommissionierung ersetzter
Prozessschritte gemäß Vorentscheidungs-ADR.
*Exit: kompletter Durchlauf (Offline-Validierung → Slice → Auto-Stufung →
KEEP/ROLLBACK) ohne manuellen Eingriff, im Evidence-Log nachvollziehbar.*

**Phase 3 — Execution-Reife & Mandat.** Adapter-Grenze härten (Idempotenz,
Teilfüllungen, Doppel-Order-Schutz); Reconciler; Mandat-Mechanik mit externer
Signatur; Secret-Trennung; `LIVE_CANDIDATE`-Report-Generator.
*Exit: Live-Order ohne gültiges Mandat wird nachweislich abgelehnt (Test);
Reconciler erkennt injizierten Drift und schränkt ein.*

**Phase 4 — Micro-Live & Skalierung.** Startet nur mit gültigem Mandat.
Micro-Live-Canary, dann Skalierung eine Dimension pro Schritt.
*Exit: definiert Luke bei Mandatserteilung.*

## Offene Entscheidungen für Luke

1. **Die Vorentscheidungs-ADR** (Allocator ↔ SI-v2, Execution-Pfad,
   #423-Reconciliation) — alles Weitere hängt daran.
2. **Zahlen:** Drawdown-Limits, Gesamtrisikobudget, Slice-Stufen und
   Schwellwert fürs Human-Gate, Mindest-Trades/-Dauer/-Regime pro
   Promotion (Kombination statt reiner Zeitdauer).
3. **Flottenrollen:** welche Bots Phase 0 durchlaufen; ob die Flotte bis zur
   Edge-Evidenz auf eine Kernstrategie schrumpft.
4. **Akzeptanz der Phase-0-Weggabelung:** ohne Edge-Evidenz kein Live-Pfad.
