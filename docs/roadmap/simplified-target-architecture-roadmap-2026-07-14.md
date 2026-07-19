---
authority: historical
status: superseded
superseded_by: config/governance/canonical-roadmap.yaml
---

# Architekturvorschlag — Trading Hub Zielbild (Kandidat, v4 — 2026-07-14)

> **Status:** Vorschlag / Planungsdokument (L2, docs-only). Kein beschlossenes
> Zielbild. Ersetzt v1–v3 dieser Datei (Git-History).
> **Source of Truth:** Konflikte werden ausschließlich nach der in `AGENTS.md`
> („Source-of-truth order") definierten Hierarchie aufgelöst. Dieses Dokument
> besitzt keine eigene Konfliktpriorität.
> **Governance:** SI-v2 bleibt per aktiver ADR
> (`ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md`) verbindlich,
> bis eine supersedierende ADR anderes beschließt. Bis dahin bleiben
> **sämtliche aktiven Dry-Run-Sicherheitsinvarianten der gültigen SI-v2-ADR
> maschinell erzwungen**, einschließlich `dry_run=true`, canary-first,
> Allowlist-Kompatibilität, RiskGuard `PASS`, Kill-Switch `NORMAL`,
> Konfliktfreiheit des Messfensters, Snapshot, Audit-Event, Messplan,
> Rollback-Fähigkeit, Cooldown-/Concurrency-Limits sowie Ausschluss von
> Secrets und Live-Exchange-Keys. Diese Aufzählung ist nachrichtlich; die ADR
> bleibt die vollständige Definition.
>
> Dieses Dokument autorisiert **keine** Runtime-Mutation, kein Live-Trading,
> kein `dry_run=false` und kein Exchange-Key-Deployment. Live-Kapital braucht
> immer explizite menschliche Freigabe (SOUL.md Regel 1).

---

## Der einfache Umstieg

Das Dokument trennt strikt zwei Teile, damit der Einstieg nicht an
Architekturfragen hängt:

**Teil A — wird jetzt gebaut.** Edge-Research, Messbasis-Fix und der
Minimal-Käfig. Alles davon läuft innerhalb der bestehenden Governance —
**es braucht keine Vorentscheidungs-ADR, um anzufangen.**

**Teil B — Richtung, kein Bauauftrag.** Capital Allocator, Live-Mandat,
Live-Trust-Anchor. Detail-Spezifikation und Bau erst nach bestandenem
Gate 0. Die Vorentscheidungs-ADR ist **vor Phase 2** fällig (Allocator ↔
SI-v2), nicht vor Phase 0 — Backtests brauchen keine Meta-Entscheidung.

Damit gilt das oberste Prinzip auch für dieses Dokument selbst: erst
Edge-Evidenz, dann Orchestrierung.

## Leitprinzipien

1. **Erst Edge-Evidenz, dann Orchestrierung.** Ohne belastbare Edge-Evidenz
   ist der Trading Hub ein Research-System mit Sicherheitshülle — kein
   Kandidat für Live-Kapital.
2. **Selektion statt Zentralplanung** (Teil B): Strategie-Versionen
   konkurrieren um Risikobudget, schlechte sterben billig.
3. **Geplantes Risiko wird mathematisch begrenzt.** Realisierte Verluste
   können durch Gaps, Slippage und Ausführungsrisiken höher ausfallen —
   Überschreitungen werden als Limit-Overshoot protokolliert und eskaliert.
4. **Live ist das Endziel, menschlich mandatiert.**
5. **Unsicherheit führt zu Einschränkung, nie zu optimistischer Annahme.**

**Lehre aus C4 (07/2026, Canary im Dry-Run):** Der `ROLLBACK_RECOMMENDED`-
Entscheid bleibt unter allen drei geprüften Berechnungsmethoden gültig;
window-gefiltert verletzen sowohl Continuation-Drawdown (75,08 %) als auch
Sharpe (−0,18) die Guardrails (`docs/reports/c4-decision-triage-2026-07-03.md`).
Der Lifetime-vs.-Window-Fehler ändert das Ergebnis nicht, begrenzt aber die
kausale Attribution und muss vor jedem neuen Vergleichsfenster behoben sein.

## Ebenenmodell

```text
MANAGEMENT PLANE   Luke (Mandate, Stopp) · Hermes (DevOps, Audit)
CONTROL PLANE      Measurement · (später: Capital Allocator)
DATA PLANE         Sensorik → Strategien → Risiko-Funktionen →
                   Freqtrade-Execution ↔ Exchange
```

Keine Ebene erbt stillschweigend Autorität: Ein Merge allokiert kein Kapital,
eine Messung erzeugt keine Order, ein Signal erhöht kein Limit.

## Autoritätsmodell

| Komponente | Darf | Darf nicht |
|---|---|---|
| Sensorik (Rainbow, LLM) | Regime, Kontext, Confidence liefern; Entries filtern | Orders erzeugen; Limits ändern |
| Freqtrade-Strategie | Entry-/Exit-Kandidaten erzeugen | Risiko-Funktionen umgehen |
| Risiko-Funktionen | erlauben, verkleinern, blockieren, Bots anhalten | Live freigeben; Limits aufweichen |
| Capital Allocator (Teil B) | Risikobudget innerhalb fester Grenzen verschieben | Budgets/Caps erhöhen; Mandate erteilen |
| Hermes | Code, Tests, Deployments, Runbooks, Evidence | Trades entscheiden; Mandate erzeugen; Gates umgehen |
| Luke | jederzeit stoppen; Limits und Mandate innerhalb des Governance-Vertrags setzen | Safety-, Evidence- oder Mandats-Checks per Operator-Aktion umgehen |

---

# Teil A — Fundament (wird jetzt gebaut)

## Edge-Research (Phase 0)

- Bestehende Strategien gegen mehrjährige Out-of-Sample-Daten: Walk-Forward,
  unangetastetes Holdout, reale Kosten (Fees, Funding, Slippage),
  Auswahlkorrektur bei mehreren getesteten Varianten.
- Datenbasis explizit gegen Verzerrung prüfen: Survivorship-/Delisting-Bias,
  Datenlücken, exchange-spezifische Marktstruktur.
- Messbasis fixen: C4-Window-Scope (Lifetime vs. Window), Vergleichbarkeits-
  Standards, Umgang mit offenen Trades.
- Ergebnis ist binär — Strategien ohne Edge-Evidenz werden verworfen, nicht
  „verbessert".
- Voraussetzung für jede *Runtime*-Messung (nicht für Offline-Research):
  stabile Flotte; aktuelle Ops-Blocker stehen im State-Dokument und den
  offenen Issues, nicht hier.

**Gate 0 (Weggabelung):** ≥ 1 Strategie mit belastbarer Edge-Evidenz
(Vorschlagswerte: OOS Max-DD < 25 %, Profit-Factor > 1,3, > 100 Trades,
regime-stabil) → weiter. Sonst: Research-only, kein Live-Pfad. Diese
Weggabelung kann das Live-Vorhaben beenden — das ist gewollt.

## Minimal-Käfig (Phase 0/1 — Pflicht, nicht Vorschlag)

- **Ein hartes Flotten-Drawdown-Limit** auf High-Water-Mark-Basis plus
  Tageslimit → automatisch `HALT_NEW`. Weitere Uhren (rollierende 24 h)
  folgen, sobald die ersten zwei bewiesen laufen.
- **Positionsgröße = erlaubtes Kapitalrisiko ÷ ATR-basierte Stop-Distanz.**
  ATR bestimmt die Distanz, nicht das akzeptierte Risiko.
- **`HALT_BOT`** (Bot-Circuit-Breaker): isoliert einen Bot, Flotte läuft
  weiter. Pflichtbestandteil von Phase 1.
- **Kill-Switch-Zielmodell — Zustand plus Aktionen** statt fünf flacher Modi:

  ```text
  Safety-State:  NORMAL · HALT_NEW · REDUCE_ONLY · EMERGENCY
  Aktionen:      CANCEL_PENDING_ENTRIES · CANCEL_ALL_PENDING ·
                 REQUEST_CONTROLLED_UNWIND
  ```

  Heute implementiert: `NORMAL` / `HALT_NEW` / `EMERGENCY`
  (`freqtrade/shared/kill_switch.py`); `REDUCE_ONLY` und die Aktionen sind
  Zielsemantik. `EMERGENCY` erzeugt einen Exit-Intent; **Default-Executor ist
  Freqtrade selbst** (`custom_exit`), die Schließung gilt erst mit
  Exchange-Evidence als bestätigt.
- Risiko-Funktionen begrifflich entflechten (Entry-Gate / Portfolio-Limits /
  Circuit-Breaker), `BLOCK_ENTRY`-Semantik vereinheitlichen.

**Gate 1:** Im deterministischen C4-Replay löst der Safety-Trigger spätestens
beim ersten nachweisbaren Erreichen des Tageslimits aus; ab dann keine neuen
Entries. Tests belegen zusätzlich, dass latenz-/gap-bedingte Überschreitungen
sichtbar als Limit-Overshoot protokolliert und eskaliert werden. `HALT_BOT`
isoliert einen Bot ohne Flotten-Impact (Testbeweis).

---

# Teil B — Zielbild nach Gate 0 (Richtung, kein Bauauftrag)

Nichts in Teil B wird detail-spezifiziert oder gebaut, bevor Gate 0 bestanden
ist und die Vorentscheidungs-ADR (vor Phase 2) angenommen wurde.

## Capital Allocator

- Verteilt **Risikobudget** (nicht Kontostand): Summe der Slices ≤ festes
  Gesamtbudget; Caps pro Strategie; Korrelationsgruppen mit gemeinsamer
  Obergrenze (Vorschlagsmethode: rollierende 30-Tage-Korrelation, Schwelle
  z. B. > 0,7 → gemeinsames Exposure-Cap). Budgets/Caps werden nie
  automatisch erhöht.
- **Neue Version = neue Identität** mit kleiner Start-Slice; automatische
  Stufung (z. B. 2 % → 5 % → 10 % → 20 %) nur für virtuelles Budget im
  Dry-Run/Paper. **Alle Schwellwerte, Primärmetrik und Hysterese werden vor
  Aktivierung schriftlich fixiert** — sonst ist jede Messung post-hoc
  interpretierbar.
- Kopplung an den Käfig: löst eine Risiko-Uhr `HALT_NEW`/`HALT_BOT` aus,
  friert der Allocator die betroffene Slice ein; Wiederanlauf nur über die
  fixierte Entscheidungsregel, nie automatisch beim Uhren-Reset.
- Entscheidungsregel: Mindestdauer **und** Mindest-Trades **und**
  Regime-Abdeckung **und** enges Unsicherheitsintervall, sonst `EXTEND`.
  `KEEP` heißt nur: aktuelle Stufe bestanden. RuntimeEffectProof bleibt
  obligatorisches, persistiertes Artefakt — ohne `GREEN` kein Messfenster.
- SI-v2-Analyzer/Measurement/Evidence bleiben als Werkzeuge; das Verhältnis
  Allocator ↔ SI-v2 entscheidet die ADR.

## Vergleichsmodi

```text
OFFLINE_AB       beide Versionen simuliert auf identischen Daten
PAPER_PARALLEL   beide Versionen virtuell auf Echtzeitdaten
LIVE_CHALLENGER  nur der Challenger live; Baseline Paper oder Subaccount
```

`LIVE_CHALLENGER` hat eine **bekannte Einschränkung**: Die Paper-Baseline
handelt ohne echte Slippage. Umgang: getrennte Subaccounts, wo möglich;
sonst dokumentierter Slippage-Korrekturfaktor. Der Vergleich ist Indiz,
nie allein KEEP-Begründung.

## Execution-Grenze und Live-Trust-Anchor

- Die **Freqtrade-Adapter-Grenze ist die kanonische Dry-Run- und
  Paper-Sicherheitsgrenze** (Risk-Freigabe, Idempotenz, Doppel-Order-Schutz,
  Teilfüllungen). Für Live-Betrieb reicht sie allein nicht aus.
- **Vor dem ersten Live-Euro** muss ein externer, nicht durch Hermes
  administrierbarer **Trust-Anchor** Mandatsprüfung und Zugriff auf
  Live-Credentials erzwingen (Remote Execution Proxy, Credential Broker oder
  vergleichbar). Das zugrunde liegende **Threat Model ist Bestandteil der
  ADR**: Variante A (Host-Root gilt als vertrauenswürdig; Schutz gegen
  Fehlbedienung und Agentenfehler) oder Variante B (kryptografische Trennung
  auch gegenüber Host-Root). „Root kann keinen Live-Pfad erzeugen" ist nur
  mit Variante B wahr.
- **Reconciler:** lokaler Zustand ↔ Exchange-Zustand. Fail-closed heute:
  `HALT_NEW`; Zielsemantik `REDUCE_ONLY` erst nach bewiesener Implementierung.
- **Externer Breakglass-Stopp** unabhängig von HermesTrader: Exchange-
  Subaccount sperren, API-Key exchange-seitig widerrufen. Der lokale
  Kill-Switch hilft nicht, wenn der Host selbst nicht erreichbar ist.

## Live-Mandat

Ein **scope-gebundenes, nicht übertragbares, widerrufbares Mandat**: innerhalb
seines Gültigkeitszeitraums für mehrere zulässige Orders verwendbar, aber
weder nach Ablauf/Widerruf noch für einen anderen Bot, Build, Account oder
Scope. Mindestens eine explizite menschliche Freigabe pro Mandats-Scope; jede
Erweiterung (Kapital, Instrumente, Laufzeit, Strategieversion) = neues Mandat.

```text
schema_version · mandate_id · issued_at · approved_by · nonce
bot_id · strategy_version · commit/image-digest · exchange · account
erlaubte Instrumente · max_capital · max_position_size
max_daily_loss · max_drawdown · valid_from · valid_until
signing_key_id · signature_algorithm · signature · revocation_reference
```

- **Widerruf braucht einen Mechanismus, nicht nur ein Wort:** kurze
  Mandatslaufzeit mit expliziter Erneuerung plus signierte Revocation-List.
  Fällt die Revocation-Prüfung aus: keine neuen oder risikosteigernden
  Orders; risikoreduzierende Exits bleiben zulässig.
- Das Mandat autorisiert ausdrücklich auch den Allocator-Algorithmus, das
  maximale Gewicht je Strategie, das Gesamtbudget und die zulässige
  Rebalancing-Frequenz.

## Graduation

```text
Gate 0 → Käfig (Gate 1) → Allocator Paper/Dry-Run (Gate 2)
→ Execution-Reife + Trust-Anchor (Gate 3: Live-Order ohne Mandat wird
  nachweislich abgelehnt; Reconciler erkennt injizierten Drift)
→ ★ Mandat durch Luke ★ → Micro-Live-Canary (< 1 % Zielkapital, befristet)
→ Skalierung: pro Schritt EINE Dimension, Bot für Bot, automatischer
  Rückbau bei Verletzung, jede Erweiterung = neues Mandat
```

---

## Nicht verhandelbar

1. Dry-Run ist Default; Live nur mit gültigem menschlichem Mandat.
2. Signal ≠ Order; LLM nie Execution Authority.
3. Definierter Vergleichsmodus für jede Wirkungsmessung.
4. **Keine In-Place-Änderung der tradingsemantischen Strategieversion**
   (Entry-/Exit-Logik, Features, Modell, Sizing, Pairs, Stops). Nicht
   tradingsemantische Fixes (Logging, Telemetrie, Security-Patches,
   Packaging) dürfen als neuer Build derselben Strategieversion ausgeliefert
   werden, sofern Contract-Tests unverändertes Tradingverhalten belegen;
   jeder Build erhält neuen `commit_sha`/`image_digest`/`runtime_build_version`.
5. Software-Rollback ≠ Trading-Recovery: realisierte Verluste sind
   irreversibel; für Positionen gibt es Containment und Unwind.
6. Append-only, gehärtete Evidence (Hash-Verkettung oder externe Kopie) für
   Mutationen, Allokationsänderungen und Mandate.
7. Kill-Switch außerhalb der Strategien; per Optimierung nicht erreichbar.
8. Keine Secrets in Git; Live-Credentials außerhalb des Hermes-Trust-Bereichs;
   Keys ohne Withdrawal-Rechte.
9. Fehlende oder widersprüchliche Evidence → `BLOCKED`/`EXTEND`; Teilerfolg
   wird nie als Gesamterfolg protokolliert.
10. **Der Repository-Writer-Vertrag gilt ohne stillschweigende Ausnahme** für
    jede Repo-Schreibaktion (`orchestrator/scripts/repo_writer.py`).
    Incident-, Rotation- und Rollback-Runbooks definieren separate
    *Runtime*-Aktionen, setzen Lock und Worktree aber nie außer Kraft;
    `BLOCKED_BY_ACTIVE_REPO_WRITER` bleibt ein harter Stopp.

## Fail-closed-Klassifizierung

| Ausfall / Befund | Verhalten |
|---|---|
| Kill-Switch-Status nicht lesbar | `HALT_NEW`, fail-closed |
| Mandat ungültig oder nicht prüfbar | keine risikosteigernden Live-Orders; sichere Exits zulässig |
| Exchange-Zustand unbekannt | `HALT_NEW`; Pending Entries nach Möglichkeit stornieren; keine blinde Vollschließung; Reconciliation eskalieren |
| Bestätigte Positions-/Order-Drift | betroffenen Bot isolieren (`HALT_BOT`); bei systemischer Drift flottenweit `HALT_NEW` |
| Marktdaten-Freshness verletzt | betroffene Strategie stoppt |
| Mess-/Attributions-Evidence fehlt | Applies, Allokationsänderungen, Promotions pausieren |
| Reporting/Dashboards | Alarm; sicherer Dry-Run läuft weiter |

## Phasen und Gates

```text
JETZT      Phase 0: Edge-Research + Messbasis + Minimal-Käfig
           (keine ADR nötig; Ops-Stabilisierung als Voraussetzung
            jeder Runtime-Messung, Stand siehe State-Doku)
GATE 0     Edge-Evidenz vorhanden — oder Research-only.
           Phase 1: Käfig vollständig (Gate 1)
ADR-GATE   Vorentscheidungs-ADR, fällig vor Phase 2:
           Allocator ↔ SI-v2 · Execution-Pfad · Threat Model A/B ·
           Mandats-/Revocation-Modell · #423-Reconciliation ·
           Decommissioning-Bedingungen
           Phase 2: Allocator Paper/Dry-Run (Gate 2)
           Phase 3: Execution-Reife + Trust-Anchor + Mandat (Gate 3)
★ MANDAT ★ Phase 4: Micro-Live und Skalierung
```

Die initiale Flotte bleibt auf maximal 4–5 klar abgegrenzte Strategierollen
begrenzt; eine Erweiterung erfordert nachgewiesenen Diversifikationsnutzen,
zusätzliche Risikokapazität und eine eigene Architekturentscheidung.

## Offene Entscheidungen für Luke (mit Vorschlagswerten)

1. **Phase 0 starten und Flotte konzentrieren?** Vorschlag: eine
   Kernstrategie durchläuft Phase 0, der Rest ruht bis zur Edge-Evidenz.
2. **Zahlen bestätigen oder ändern.** Vorschlagswerte: Tages-DD 3 %,
   HWM-Flotten-DD 15 %, Risiko pro Trade 1 % Equity, Slices 2/5/10/20 %,
   Human-Gate ab 20 % bzw. bei jedem Live-Übergang, Promotion ab
   50 geschlossenen Trades **und** 60 Tagen **und** ≥ 2 Regimen.
3. **Vorentscheidungs-ADR-Richtung** (fällig vor Phase 2): ersetzt der
   Allocator SI-v2, ergänzt er ihn, oder wird das nach Gate 0 anhand der
   Ergebnisse entschieden? Vorschlag: nach Gate 0 entscheiden.
4. **Akzeptanz der Weggabelung:** ohne Edge-Evidenz kein Live-Pfad —
   Projekt läuft dann als Research weiter.
