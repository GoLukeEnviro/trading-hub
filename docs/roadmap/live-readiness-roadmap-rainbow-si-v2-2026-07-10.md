# Live-Readiness-Roadmap — Rainbow/ai4trade-bot als Advisory-Signalquelle (2026-07-10)

> **Status:** Vorschlag / Planungsdokument (L2, docs-only)
> **Source of Truth für Task-Ausführung:** GitHub Issue #423 — dieses Dokument ergänzt #423, es ersetzt es nicht.
> **Autoritative Reihenfolge:** `AGENTS.md` → `SOUL.md` → `docs/state/current-operational-state.md` → dieses Dokument.
> **Upstream-Referenz:** `GoLukeEnviro/ai4trade-bot` @ `f6c42c6`, Contract: `docs/integration/rainbow-signal-provider-contract.md` (Issue #51).
>
> Dieses Dokument autorisiert **keine** Runtime-Mutation, kein Live-Trading, kein
> `dry_run=false`, kein Exchange-Key-Deployment und keine Bot-/Strategie-Mutation.
> Jede solche Aktion braucht den jeweils benannten Approval-Marker und Task-Scope.

## Roadmap Ownership

- **Issue #423 bleibt die kanonische SI-v2-to-Live-Roadmap.** Sie kontrolliert C4, D1, D2 und die Live-Fleet-Autorisierung.
- **Rainbow erhält nach Merge dieses PRs einen separaten, aus #423 verlinkten Tracker** (`[Rainbow][SI-v2] Tracker — Read-only advisory signal integration`). Der Rainbow-Tracker ergänzt #423 als advisory/read-only Integration. Er ersetzt #423 nicht.
- **Nur #423 autorisiert Live-Rollout.** Rainbow-Messungen, -Signale oder Tracker-Abschlüsse können D1/D2 oder Live-Trading nicht eigenständig freigeben.
- **PR-Abhängigkeitsreihenfolge:** PR #487 (dieses Dokument) → Merge → Rainbow-Tracker + Issues anlegen → R1 starten. PR #66 (ai4trade-bot) und PR #488 (Contract-Patch) bleiben Drafts, bis ihre jeweiligen Architektur-Blocker gelöst sind. D1/D2 bleiben blockiert bis gültiger KEEP-Entscheidung und `APPROVED_LIVE_FLEET_ROLLOUT`-Marker.

---

## Einschätzung

ai4trade-bot/Rainbow ist als **read-only advisory Signalquelle und Evidence Provider** für Trading Hub geeignet: Der Signal-Provider-Contract (upstream #51), das kanonische Envelope-Schema, ein fail-closed Validator, ein Fixture-Pack (beidseitig identisch) und ein read-only Client mit Safety-Stempel (`can_execute=False`, `dry_run_only=True`) existieren bereits in beiden Repos. Nicht geeignet — und dauerhaft verboten — ist Rainbow als Order-Executor, Trading-Bot oder direkte Execution Authority; der einzige Pfad zu Freqtrade bleibt SI-v2 → RiskGuard → Strategie-Filter.

## Empfehlung

Die bestehende `si_v2/rainbow/`-Infrastruktur **promoten statt neu bauen**: Contract-Snapshot gegen upstream `f6c42c6` re-validieren (S1), den Client kontrolliert von `fixture` auf `read_only` heben (S2), dann den fehlenden **Attribution-Producer** bauen, der Rainbow-Signale über `AttributionInput`/`SignalContribution` in die vorhandene `source_regime_stats`→`ProposalEvidenceRecord`-Kette einspeist (A1). Live (Tracks E/F) erst nach Runtime-Preflight (Track 0), frischem Dry-Run-Messfenster, gefixtem C4-Window-Scope und neuem C4-KEEP — alle bisherigen Live-Approval-Marker sind am 2026-07-09 abgelaufen; es existiert derzeit **keine gültige Live-Genehmigung**, und das ist der korrekte Zustand.

## Begründung

1. **Der Integrationsvertrag existiert beidseitig.** Upstream definiert `CanonicalSignalEnvelope` (`core/signals/envelope.py`) mit erzwungener Actionability (`_enforce_safety()` → `can_execute=False, dry_run_only=True`), Direction-Mapping (bullish→long, bearish→short, neutral→flat), Null-/Error-/Stale-/Heartbeat-Regeln und Redaction-Policy. Trading Hub hält den Snapshot in `self_improvement_v2/contracts/rainbow_signal_envelope.schema.json` mit Drift-Guard und 3 Contract-Testdateien.
2. **Die Konsum-Seite ist gebaut und fail-closed.** `si_v2/rainbow/validator.py` rejected fehlende Pflichtfelder (confidence, symbol, direction …), normalisiert Directions, behandelt Staleness und `data_quality`; `si_v2/rainbow/client.py` ist default-`disabled`, GET-only, ohne Auth-Header, und bereits im Active Cycle Runner (Step 2c) hinter Env-Gates (`SI_V2_RAINBOW_ENABLED/MODE/BASE_URL`) verdrahtet.
3. **Die Evidence-/Attribution-Kette ist source-agnostisch vorbereitet.** `AttributionInput` → `attribution/engine.py` → `source_regime_stats` (SQLite, `source_id`-keyed) → `evidence/input_pipeline.py` (14 Quality-Gates) → `proposals/candidate_builder.py`. Ein Rainbow-Signal wird in dem Moment zu SI-v2-Evidence, in dem Trades `SignalContribution(source_id="rainbow:*")` zitieren. Was fehlt, ist genau ein Baustein: der Producer dieser Records.
4. **Die Safety-Historie spricht für das Gate-Design.** Die einzige Live-Canary-Episode (02.–03.07.2026) endete mit `ROLLBACK_RECOMMENDED` (max_drawdown 82.79 %) und wurde korrekt abgewickelt (Rollback, Kill-Switch-Zyklus, D1 blockiert). Der dabei entdeckte C4-Data-Scope-Mismatch (Lifetime- statt Window-Trades, `docs/reports/c4-decision-triage-2026-07-03.md` §3) ist ein konkreter, kleiner Fix vor jedem neuen Messfenster.
5. **Rainbow als Executor wäre ein Architekturbruch.** SOUL.md Regel 9 (LLM advisory only), AGENTS.md Signal-Layer-Boundary und der upstream-Contract selbst (§2 Read-Only Boundary) schließen das aus.

## Pro

| Vorteil | Konkret |
|---|---|
| Geringes Delta bis Track-S-Abschluss | Schema, Validator, Fixtures (7), Drift-Guard, read-only Client, Status-Resolver und Cycle-Wiring existieren; offen sind nur Re-Sync, Enablement-Pfad und Status-Promotion |
| Contract-first mit Drift-Schutz | JSON-Schema-Snapshot + `drift_guard.py` + Snapshot-Tests verhindern stilles Auseinanderlaufen der Repos |
| Fail-closed by construction | Default `disabled`; missing confidence/strength/symbol → reject; stale/degraded → keine Entscheidungsverwendung; unknown direction → no execution; Actionability-Stempel auf jedem Envelope |
| Attribution ohne Schema-Änderung | `source_regime_stats` (Schema 1.1) und `ProposalEvidenceRecord` sind bereits `source_id`-keyed — Rainbow fließt nach A1 automatisch in Candidate Selection und Reports |
| Mehr Evidence-Dimensionen für SI-v2 | reason_codes, regime_hint, confidence, freshness als zusätzliche Candidate-Selection- und RiskGuard/Judge-Inputs — advisory only |
| Netzwerk-Boundary bereits gehärtet | `NetworkGuard` (nur http, nur localhost/127.0.0.1, keine Credentials in URL) + Stub-Server-Testpattern vorhanden |
| Live-Ceremony-Code wiederverwendbar | C1–C4-Kette (`si_v2/live/`) ist gebaut und getestet; Track E ist eine Wiederholung mit Lessons, kein Neubau |

## Kontra / Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Rainbow-Producer läuft aktuell nicht (Prozess gestoppt, Boot-Persistence bewusst gated) | Track 0: kontrollierter Start per `rainbow_producer_manager.sh` + Readiness-Check; Auto-Start nur nach separatem Approval (`docs/plans/rainbow-boot-persistence-plan.md`) |
| Stale/degraded Signale könnten Entscheidungen kontaminieren | Validator-Reject + Freshness-Schwelle (900s Readiness / 3600s Envelope `max_age_seconds`); Health-Unreachable ≥3 Checks → Source `UNAVAILABLE`, fail-closed; Pflicht-Tests in S2/S3 |
| Contract-Drift seit Snapshot (2026-06-10) vs. upstream HEAD `f6c42c6` (u. a. `/signals/canonical/latest`) | S1: Re-Sync + Drift-Guard-Lauf als erster Task, bevor irgendetwas enabled wird |
| C4-Messengine bekam Lifetime- statt Window-Trades — Entscheidungsqualität künftiger Messfenster gefährdet | C4-Fix-Issue (Window-Filter) vor jedem neuen Canary-Messfenster; Triage-Report als Testfall-Quelle |
| Signal→Trade-Attribution kann Kausalität überzeichnen (Signal lag vor, Strategie entschied unabhängig) | A1 attribuiert nur bei validiertem, freshem Signal im Entscheidungsfenster; `contribution_weight` konservativ; Attribution ist Evidence, nie Freigabe |
| Runtime-Ist-Zustand blockiert Messungen (Canary tot #478, VPS-Rebuild #483, Pipeline-State leer) | Track 0 als explizite Abhängigkeit der Tracks C–F; keine Messfenster-Behauptungen ohne laufende Fleet |
| Schleichende Autoritäts-Eskalation („Rainbow sagt long, also traden“) | Guard-Tests (advisory-only-Invariante), kein Codepfad Rainbow→`primo_signal_state.json`/Order; Autonomy-/RiskGuard-Gates bleiben einzige Mutations-/Entry-Autorität |
| Unredacted `raw_data`/`features`/`raw_refs` könnten persistiert werden | `redaction_status`-Pflichtfeld, Redaction-Tests, keine Persistenz unredacted Payloads (Contract §11); Secret-Scan bleibt CI-Gate |
| Abgelaufene/fehlende Approval-Marker könnten stillschweigend „weiterverwendet“ werden | Track E verlangt **neue** Marker mit Expiry; Gate-Checks prüfen Marker-Datum, nicht nur Existenz |

## Zielarchitektur

```text
┌────────────────────────────── ai4trade-bot (extern, read-only) ──────────────────────────────┐
│  Rainbow Intelligence Engine                                                                 │
│  Collectors → CryptoSignal → CanonicalSignalEnvelope (can_execute=False, dry_run_only=True)  │
│  FastAPI: GET /signals/latest · /signals/canonical/latest · /health                          │
└───────────────┬──────────────────────────────────────────────────────────────────────────────┘
                │ HTTP GET, localhost-only (NetworkGuard), keine Auth-Header, kein POST
                ▼
   RainbowSignalProviderClient (si_v2/rainbow/client.py, default disabled, fail-closed)
                │
                ▼
   Validator + Drift-Guard (rainbow/validator.py, contracts/*.schema.json)
   → reject: missing confidence/strength/symbol, stale, unknown direction, degraded quality
                │
                ▼
   SignalEvidence  (source_manifest.json · EvidenceBundle · ShadowLogger/Shadowlock-Events)
                │
                ▼
   Attribution  (AttributionInput + SignalContribution(source_id="rainbow:*")
                 → attribution/engine.py → source_regime_stats SQLite)
                │
                ▼
   SI-v2  (evidence/input_pipeline.py → ProposalEvidenceRecord → Candidate Selection
           → Autonomy Policy Gates: dry-run-only, Kill-Switch NORMAL, canary-first, Allowlist)
                │  (nur ShadowProposals / Parameter-Overlays, nie Orders)
                ▼
   RiskGuard  (riskguard_service.py, RG-1..RG-5: confidence ≥ 0.65, max age 25 min,
               downgrade → WATCH_ONLY / block; harte Safety-Autorität)
                │
                ▼
   Freqtrade Dry-Run-Fleet  (freqforge · freqforge-canary · regime-hybrid · freqai-rebel;
                             Strategie entscheidet; primo_gate + Kill-Switch fail-closed)
                │
                ▼
   Measurement  (measurement/ledger.py · decision_engine.py · C4 live_canary_measurement_decision)
                │
                ▼
   Decision  (KEEP / EXTEND / ROLLBACK — human-gated für jede Mode-Transition Richtung Live)
```

**Rollen:**

- **Rainbow / ai4trade-bot** — Signalquelle und Evidence Provider. Liefert Envelopes und Health. Hat keinen Order-Pfad, keine Exchange-Zugriffe für Trading-Hub-Entscheidungen, wird nicht vendored und nicht mutiert. Webhooks/Streaming sind ohne eigenes Issue + Approval nicht Teil der Integration.
- **SignalProvider-Schicht (trading-hub)** — read-only, fail-closed, env-gated, disabled-by-default. Validiert, normalisiert, stempelt Actionability, schreibt Evidence.
- **SI-v2** — konsumiert Signal-Evidence für Candidate Selection und ShadowProposal-Qualität; mutiert ausschließlich policy-gated, canary-first, allowlist-basiert im Dry-Run.
- **RiskGuard** — harte Safety-Layer; darf jedes Signal und jeden Proposal-Effekt downgraden oder blocken; wird nie umgangen.
- **Freqtrade** — Execution-Fleet, dry-run; Strategien bleiben Entscheidungsträger, Signale sind konservative Filter.
- **Measurement/Decision** — C4-Engine liefert Evidence; KEEP ist notwendige Bedingung, nie hinreichende Freigabe für Live. Jede Live-Mode-Transition bleibt human-gated per Approval-Marker.

## Roadmap

### Track 0 — Runtime-Preflight (approval-gated, überwiegend Ops, kein Signal-Code)

**Ziel:** Eine messfähige Runtime herstellen — ohne laufende Fleet und laufenden Producer sind Tracks C–F Theorie.

**⚠️ Track 0 ist nicht automatisch ausführbar.** Jede 0.x-Aktion ist einzeln human-gated (L3). Docker-Operationen, Container-Start/Stopp, Producer-Startup, Secrets-Handling, Scheduler-Änderungen und Canary-Redeployment benötigen jeweils eigenen expliziten Scope und Freigabe. Dieses Dokument autorisiert keine Track-0-Aktion.

| Task | Inhalt | Gate |
|---|---|---|
| 0.1 | VPS-Rebuild-Stabilisierung abschließen (#483 P0: Secrets in `/opt/secrets/trading.env`, freqforge GREEN, Restic-Backup + Restore-Drill) — #483 ist ~3 Tage alt (erstellt 2026-07-07) und enthält Exchange-Key-Deployment und Runtime-Aktionen; darf nicht ungeprüft als ausführbare Rainbow-Dependency importiert werden | L3, explizite Freigabe |
| 0.2 | Canary-Dry-Run-Redeploy: Geplante Wiederinbetriebnahme des Canary nach C4-ROLLBACK. Der Canary-Stopp war intentional (Baseline Return, #423 C4e/C4f). Ein Redeploy ist eine separate L3 Dry-run-Redeployment-Ceremony — kein Routine-Fix für #478. Erfordert aktuelle Evidence, explizites Approval, Snapshot, Rollback-Plan und Verifikation | L3, explizite Freigabe |
| 0.3 | Rainbow-Producer kontrolliert starten (`rainbow_producer_manager.sh start` + `rainbow_producer_readiness_check.py` GREEN); Boot-Persistence bleibt separat gated | L3, explizite Freigabe |
| 0.4 | Doku-Drift schließen: PR #482 mergen, `docs/state/current-operational-state.md` auf Post-C4-Stand bringen, fehlenden Incident-Report `incident-2026-07-03-canary-baseline-return.md` nachreichen | L2 |

**Akzeptanz:** 4 Bots laufen dry-run mit GREEN-Healthchecks; Rainbow `/health` healthy + `/signals/latest` fresh (<900s); State-Doc aktuell.
**Risiken:** Jede 0.x-Aktion ist Runtime-Mutation → nur mit Freigabe, einzeln, mit Evidence-Report.
**Abhängigkeiten:** keine (erster Track); 0.4 ist unabhängig von 0.1–0.3 sofort möglich.

### Track S — Signal Foundation (Restarbeiten, überwiegend vorhanden)

**Ziel:** Rainbow-Signalpfad vom Fixture-Status auf verifizierten read-only-Betrieb heben.

| Task | Inhalt |
|---|---|
| S1 | Contract-Re-Sync: Snapshot + Fixtures gegen upstream `f6c42c6` prüfen (`/signals/canonical/latest` vs. Client-Endpoint, Feld-Drift), Drift-Guard-Lauf dokumentieren |
| S2 | `read_only`-Enablement-Pfad: Env-Gate-Doku, `RainbowStatusResolver` CONFIGURED-Promotion (heute TODO, maxt bei FIXTURE_ONLY), Health/Freshness-Check als read-only Evidence-Artefakt je Cycle |
| S3 | Testlücken schließen: Reject- (missing confidence/strength/symbol), Stale-, Unknown-Direction-, Redaction- und Schema-Version-Tests vervollständigen, falls S1 Drift findet |

**Kanonisches Signalmodell:** bereits abgedeckt durch `contracts/rainbow_signal_envelope.schema.json` — `invalidation/max_age_seconds` und `data_quality` liegen vertragsgemäß unter `metadata`/Invalidation-Regeln; kein Schema-Bruch nötig, nur Mapping-Doku.
**Akzeptanz:** Drift-Guard grün gegen `f6c42c6`; Client erreicht CONFIGURED nur bei erreichbarem, freshem Producer; alle Fail-closed-Regeln testbelegt.
**Tests:** `test_rainbow_contract_snapshot.py`, `test_rainbow_contract_drift_guard.py`, `test_rainbow_signal_validator.py`, `test_rainbow_read_only_client.py` (+ neue Fälle).
**Risiken:** Upstream-Drift seit 2026-06-10 → S1 zuerst. **Abhängigkeiten:** S2-Verifikation gegen echten Producer braucht Track 0.3; S1/S3 sind sofort unblocked (fixture-basiert).

### Track A — Attribution

**Ziel:** Signal → Bot → Trade-Outcome nachvollziehbar machen, ohne Strategie- oder Runtime-Änderung.

| Task | Inhalt |
|---|---|
| A1 | Attribution-Producer: pro geschlossenem Dry-Run-Trade `AttributionInput` mit `SignalContribution(source_id="rainbow:*", contribution_weight, source_confidence)` emittieren — nur wenn ein validiertes, freshes Rainbow-Signal für Pair/Fenster vorlag; sonst keine Rainbow-Contribution (kein Default-Credit) |
| A2 | Einspeisung via `source_regime_stats/update.py` (copy-on-write) + Rebuild-Doku |
| A3 | Measurement-Reports um Signal-Dimension erweitern (win-rate/expectancy je `source_id`, reason_codes, freshness) |

**Akzeptanz:** `attribution_facts` enthalten `rainbow:*`-Einträge; `evidence/input_pipeline.py` emittiert `ProposalEvidenceRecord`s mit Rainbow-`source_id`; Reports zeigen Signal-Attribution; Contribution-Summen = 1.0 (Modell-Invariante).
**Tests:** Muster `test_evidence_input_pipeline.py` (temp SQLite), neue Producer-Unit-Tests mit Fixture-Signalen + synthetischen Trades.
**Risiken:** Kausalitäts-Überzeichnung (s. Kontra). **Abhängigkeiten:** S1/S2.

### Track B — SI-v2 Candidate Quality

**Ziel:** Rainbow-Kontext verbessert ShadowProposal-Qualität; advisory-only bleibt beweisbar.

| Task | Inhalt |
|---|---|
| B1 | Signal-Kontext (direction/confidence/freshness/reason_codes je Pair) in `BotMetrics`/`FleetMetrics` bzw. `proposals/candidate_builder.py` als optionalen Input; Hypothesen bleiben in `SUPPORTED_HYPOTHESES`-Allowlist |
| B2 | `evidence_refs` in `pipeline/candidate_to_apply.py` trägt Signal-Evidence-Referenzen; Herkunft `source` erweitert (z. B. `rainbow_context`) ohne Gate-Lockerung |
| B3 | RiskGuard/Judge-Downgrade-Beweis: Tests, dass RG-1..RG-5 Rainbow-informierte Kandidaten-Effekte downgraden/blocken können; Guard-Test „kein Codepfad Rainbow→Order/primo_signal_state.json“ |

**Akzeptanz:** Candidate-Ranking nutzt Signal-Evidence nachweislich; Autonomy-Gates unverändert; advisory-only-Invariante als dauerhafter Guard-Test (analog `test_no_forbidden_patterns.py`).
**Risiken:** Scope-Drift in Strategie-Nähe → strikt oberhalb der Mutations-Gates bleiben. **Abhängigkeiten:** A1–A3.

### Track C — Dry-run Proof

**Ziel:** Belegen, dass der signalinformierte Loop im Dry-Run funktioniert — bevor über Live geredet wird.

| Task | Inhalt |
|---|---|
| C1 | C4-Window-Scope-Fix: Messengine erhält window-gefilterte Trades statt Lifetime-DB (Defekt aus Triage 2026-07-03 §3); Regressionstest mit den drei Berechnungsmethoden aus dem Triage-Report |
| C2 | Volles Dry-Run-Messfenster (≥14 Tage) mit Signal-Attribution über die laufende Fleet; T0–T4-Punkte mit Rainbow-Evidence |
| C3 | Backtest + Walk-Forward als Pflicht-Gates (bestehende `backtests/`, `tests/test_walk_forward_evaluator.py`) für jeden signalinformierten Kandidaten |
| C4 | Shadow-Mode-Beleg: FreqForge Shadow Evaluator-Auswertung mit Signal-Kontext dokumentieren |

**Akzeptanz:** Ein vollständiger Measurement-Report mit Signal-Attribution, reproduzierbarem Backtest und Walk-Forward; KPIs (Profit, Drawdown, Sharpe) als Evidence gelabelt, ausdrücklich **nicht** als Live-Freigabe.
**Risiken:** Zu wenig geschlossene Trades (T4-Historie!) → Fenster verlängern statt Daten strecken. **Abhängigkeiten:** Track 0 (laufende Fleet + Producer), C1 vor C2.

### Track D — Live Readiness (Refresh, kein Neubau)

**Ziel:** Die vorhandenen B1–B4-Artefakte (PRs #429–#432) auf den Nach-Rollback-Stand heben.

| Task | Inhalt |
|---|---|
| D1 | Live Readiness Evidence Re-Audit (Delta seit 2026-07-03: Rollback-Lessons, abgelaufene Marker, neue Signal-Evidence) |
| D2 | Production Risk Limits Review: Drawdown-Schwellen gegen die 82.79 %-Episode kalibrieren (Limits waren korrekt, Messdaten-Scope war falsch — dokumentieren) |
| D3 | Incident-/Rollback-Runbook um die real durchgeführte C4e/C4f-Prozedur ergänzen |
| D4 | Alerting-Gate von YELLOW auf GREEN (Routing-Proof) |
| D5 | Secret-Handling: SEC-2 (#476) abschließen als Gate; Exchange-Key-Deployment-Plan (nur `/opt/secrets`, nie Git, nie Env-Inspektierbar) |

**Akzeptanz:** Alle vier Readiness-Proofs GREEN; #476 geschlossen; Key-Deployment-Plan reviewed — ohne dass ein Key existiert oder deployt wird.
**Abhängigkeiten:** Track C abgeschlossen (sonst auditiert man einen leeren Zustand).

### Track E — Live Canary (Wiederholung mit Lessons)

**Ziel:** Zweiter, sauber gemessener Live-Canary-Versuch — nur mit frischen Markern.

| Task | Inhalt | Gate |
|---|---|---|
| E1 | Neuer `APPROVED_LIVE_CANARY_TRANSITION`-Marker (die Marker vom 2026-07-02 sind am 2026-07-09 abgelaufen) | Human |
| E2 | Config-Plan-Refresh (C2-Code wiederverwenden), Capital-Limit gemäß B2 | Human-Review |
| E3 | Activation Ceremony nur mit gültigem `APPROVED_EXECUTE_LIVE_CANARY` | Human + Marker |
| E4 | Measurement & Decision mit gefixtem Window-Scope (Track C, C1); Ausgang KEEP / EXTEND / ROLLBACK | Engine + Human |

**Akzeptanz:** Ceremony-Artefakte vollständig, Rollback-Pfad vorab verifiziert, Kill-Switch NORMAL bei Aktivierung, Operator on-call; C4-Entscheidung mit korrekt gescopten Daten.
**Risiken:** Wiederholung des Drawdown-Szenarios → engere Beobachtung, Limits aus D2. **Abhängigkeiten:** Tracks C + D vollständig; alle Marker frisch.

### Track F — Live Fleet (= D1/D2 aus Issue #423)

**Ziel:** Staged Rollout — bleibt blockiert, bis die Beweislage es trägt.

| Task | Inhalt |
|---|---|
| F1 | Live Fleet Rollout Approval Gate — **nur wenn** E4 = KEEP **und** `APPROVED_LIVE_FLEET_ROLLOUT` existiert (beides fehlt heute) |
| F2 | Staged Rollout: ein Bot nach dem anderen, nie alle gleichzeitig; Max-Exposure-Limits je Bot und Fleet |
| F3 | Kill-Switch/Emergency-Stop-Drill vor jedem Rollout-Schritt; Continuous Measurement; automatischer Rollback-Trigger bei Risk Breach |

**Abhängigkeiten:** Track E mit KEEP; Marker; unverändert Issue #423 D1/D2 als ausführende Task-Definition.

## Erste Issues

> Vorschläge — werden erst nach Freigabe als Issues im Rainbow-Tracker angelegt. Aufwand: S ≤ 0,5 Tag, M ≤ 2 Tage, L > 2 Tage. Jedes Issue = ein Branch, ein PR, ein Report.

### R1. `feat(rainbow): re-sync signal provider contract snapshot with upstream f6c42c6`
- **Ziel:** Contract-Snapshot, Fixtures und Validator gegen ai4trade-bot HEAD `f6c42c6` re-validieren (inkl. `/signals/canonical/latest`-Surface); Drift dokumentieren und ggf. Snapshot/Fixtures nachziehen.
- **Akzeptanzkriterien:** Drift-Guard-Lauf dokumentiert; Snapshot-Tests grün; `contracts/README.md`-Prozedur befolgt; Report unter `docs/reports/`.
- **Aufwand:** S. **Abhängigkeiten:** keine. **Stop conditions:** PR-Head-Drift, CI rot, unerwartete Contract-Änderungen. **Expected PR title:** `feat(rainbow): re-sync signal provider contract snapshot with upstream f6c42c6`. **Loop-Bezug:** ShadowProposal Quality / Historical Evidence — verhindert, dass Evidence auf veraltetem Vertrag aufbaut.

### R2. `feat(rainbow): read-only mode enablement path, status CONFIGURED, freshness evidence`
- **Ziel:** `RainbowStatusResolver` um CONFIGURED-Promotion erweitern (erreichbar + fresh), Env-Gate-Doku, Health/Freshness-Check als read-only Evidence-Artefakt je Active Cycle.
- **Akzeptanzkriterien:** Status DISABLED/FIXTURE_ONLY/CONFIGURED/DEGRADED korrekt aufgelöst (Stub-Server-Tests); unavailable ≥3 Checks → Source UNAVAILABLE; kein Auth-Header, GET-only, NetworkGuard unverändert.
- **Aufwand:** M. **Abhängigkeiten:** R1; End-to-End-Verifikation braucht Track 0.3. **Stop conditions:** Producer nicht erreichbar, CI rot, Auth-Header-Leak. **Expected PR title:** `feat(rainbow): read-only mode enablement path, status CONFIGURED, freshness evidence`. **Loop-Bezug:** SI-v2 Loop — Evidence-Input-Qualität.

### R3. `feat(attribution): rainbow signal→trade attribution producer`
- **Ziel:** Producer, der aus geschlossenen Dry-Run-Trades + validierten Rainbow-Envelopes `AttributionInput` mit `SignalContribution(source_id="rainbow:*")` erzeugt und via `source_regime_stats/update.py` einspeist.
- **Akzeptanzkriterien:** Facts mit `rainbow:*` im Cache; `input_pipeline` emittiert entsprechende `ProposalEvidenceRecord`s; keine Attribution ohne freshes, validiertes Signal im Fenster; Unit-Tests nach `test_evidence_input_pipeline.py`-Muster.
- **Aufwand:** M/L. **Abhängigkeiten:** R1–R2. **Stop conditions:** Contribution-Summen ≠ 1.0, CI rot, Kausalitäts-Überzeichnung. **Expected PR title:** `feat(attribution): rainbow signal→trade attribution producer`. **Loop-Bezug:** Measurement Attribution — Provenance Signal→Bot→Trade.

### R4. `fix(live): window-scoped trade filter in canary measurement decision`
- **Ziel:** C4-Messengine erhält nur Trades innerhalb des Messfensters (Fix des Data-Scope-Mismatch aus `docs/reports/c4-decision-triage-2026-07-03.md` §3).
- **Akzeptanzkriterien:** Regressionstest mit den Triage-Zahlen (Lifetime 82.79 % / Window 75.08 % / Continuation); Engine-Output weist Fenster + Trade-Count aus; kein Verhalten außerhalb des Moduls geändert.
- **Aufwand:** S/M. **Abhängigkeiten:** keine. **Stop conditions:** Regression bricht ab, CI rot. **Expected PR title:** `fix(live): window-scoped trade filter in canary measurement decision`. **Loop-Bezug:** Runtime Safety / Measurement Attribution — Entscheidungsqualität künftiger C4-Läufe.

### R5. `ops: runtime preflight for measurement readiness (canary redeploy, producer start, state refresh)`
- **Ziel:** Umbrella für Track 0 — referenziert #478, #483, PR #482; jede Runtime-Aktion einzeln approval-gated.
- **Akzeptanzkriterien:** 4 Bots GREEN dry-run; Rainbow-Producer healthy + fresh; `current-operational-state.md` aktuell; Incident-Report 2026-07-03 nachgereicht.
- **Aufwand:** L (Ops). **Abhängigkeiten:** menschliche Freigabe je Schritt. **Stop conditions:** Fehlende Freigabe, Runtime-Fehler, CI rot. **Expected PR title:** `ops: runtime preflight for measurement readiness`. **Loop-Bezug:** Runtime Safety — ohne laufende Runtime keine Evidence.

### R6. `feat(rainbow): SI-v2 candidate quality with signal context`
- **Ziel:** Rainbow-Kontext (direction/confidence/freshness/reason_codes) in Candidate Selection und ShadowProposal-Qualität integrieren; advisory-only-Invariante als Guard-Test.
- **Akzeptanzkriterien:** Candidate-Ranking nutzt Signal-Evidence; Autonomy-Gates unverändert; Guard-Test „kein Codepfad Rainbow→Order“ grün.
- **Aufwand:** M. **Abhängigkeiten:** R3. **Stop conditions:** Gate-Lockerung, CI rot. **Expected PR title:** `feat(rainbow): SI-v2 candidate quality with signal context`. **Loop-Bezug:** ShadowProposal Quality.

### R7. `feat(rainbow): new dry-run measurement with signal attribution`
- **Ziel:** Volles Dry-Run-Messfenster (≥14 Tage) mit Signal-Attribution, Backtest, Walk-Forward und Shadow-Mode-Beleg.
- **Akzeptanzkriterien:** Measurement-Report mit Signal-Attribution; reproduzierbarer Backtest + Walk-Forward; KPIs als Evidence gelabelt, nicht als Live-Freigabe.
- **Aufwand:** L. **Abhängigkeiten:** R5, R6, Track 0. **Stop conditions:** Zu wenig geschlossene Trades, CI rot. **Expected PR title:** `feat(rainbow): new dry-run measurement with signal attribution`. **Loop-Bezug:** Dry-run Proof / Measurement.

## Status offener operativer Issues

> Diese Issues werden in diesem PR nicht editiert. Die Klassifizierung dient als Orientierung für den Rainbow-Tracker.

| Issue | Status | Klassifizierung |
|---|---|---|
| **#476** (SEC-2) | OPEN | Teilweise adressiert durch PR #481 (merged 2026-07-06). Issue-Body enthält sensitiven Wert (`API_SERVER_KEY=...`) — muss separat redigiert werden. Status-Reconciliation erforderlich. |
| **#477** (MEM-1) | OPEN | Historischer Qdrant/Ollama-Fund vom 2026-07-03. Empfiehlt `ollama pull` und Qdrant-Rebuild (L3-Aktionen). Benötigt frischen Read-only-Recheck vor jeglicher Remediation. |
| **#478** (OPS-1) | OPEN | **Vier getrennte Findings:** (1) Canary `Exited 130` → superseded durch intentionalen Baseline Return (#423 C4e/C4f). (2) Agent Zero `Exited 0` → ungeklärt, braucht Read-only-Recheck. (3) Pipeline-State leer → ungeklärt, braucht Read-only-Recheck. (4) Caddy 502 → ungeklärt, braucht Read-only-Recheck. Issue darf nicht geschlossen werden, bis Findings 2–4 einen aktuellen Read-only-Audit erhalten haben. |
| **#483** (OPS) | OPEN | Erstellt 2026-07-07 (~3 Tage alt). Enthält Exchange-Key-Deployment und Runtime-Aktionen. Darf nicht ungeprüft als ausführbare Rainbow-Dependency importiert werden. Benötigt aktuelle Evidence und separate Freigabe. |

## Post-Merge-Sequenz

```
PR #487 amended + reviewed
    ↓
PR #487 merged
    ↓
Separater Rainbow-Tracker ([Rainbow][SI-v2]) erstellt
    ↓
Tracker aus Issue #423 verlinkt
    ↓
Einzel-Issues R1–R7 im Tracker angelegt
    ↓
Erster unblocked Task R1 (Contract-Re-Sync) ausgewählt
    ↓
Ein Task, ein Branch, ein PR, ein Report
```

## Validierung

| Ebene | Test | Erwartung |
|---|---|---|
| Unit | `test_rainbow_signal_validator.py` (+ neue Fälle aus S3) | missing confidence/strength/symbol → FAIL; unknown direction → FAIL/no execution; stale → reject für Entscheidungen |
| Fixture | 7 Fixtures `fixtures/rainbow-signals/` beidseitig identisch; `client_fixture_harness` | valid_long/valid_short PASS; malformed/stale REJECT; heartbeat nie Entscheidungsinput |
| Contract | `test_rainbow_contract_snapshot.py`, `test_rainbow_contract_drift_guard.py` | Snapshot == upstream `f6c42c6`-Contract; Drift → Test rot, kein stiller Betrieb |
| Stale/Reject | Readiness-Check (900s), Envelope `max_age_seconds` (3600s), `data_quality in {stale, unavailable}` | Signal nicht live-eligible; Source-Status DEGRADED/UNAVAILABLE; fail-closed |
| Redaction | Redaction-Tests auf `metadata`/`features`/`raw_refs`; `scripts/secret_scan.py`, `test_secret_scan_contracts.py` | keine unredacted raw_data-Persistenz; `redaction_status` erzwungen |
| Boundary | `test_ai4trade_rest_boundary.py` (Stub-Server), `test_external_adapter_boundary_audit.py`, `test_no_forbidden_patterns.py` | GET-only, localhost-only, keine Credentials; advisory-only-Invariante |
| Dry-run Smoke | Active Cycle mit `SI_V2_RAINBOW_MODE=fixture`, dann `read_only` gegen laufenden Producer | Cycle GREEN; Rainbow-Evidence im EvidenceBundle; Mutation-Counter = 0 |
| Measurement | Report nach A3/C2 | `source_id="rainbow:*"`-Attribution sichtbar; Contribution-Summen = 1.0; C4 mit Window-Scope (Issue 4) |

## Aktueller Live-Blocker

**Fehlende C4-KEEP-Entscheidung:** Der letzte C4-Lauf (2026-07-03) ergab `ROLLBACK_RECOMMENDED` (max_drawdown 82.79 %, validiert in allen drei Berechnungsmethoden). Ohne ein neues Messfenster, das KEEP ergibt, kann der Marker `APPROVED_LIVE_FLEET_ROLLOUT` nicht entstehen — und damit bleiben D1/D2 (Issue #423) und Track F blockiert. Alles andere (abgelaufene Canary-Marker, gestoppter Producer, tote Container) sind Abhängigkeiten auf dem Weg zu einem neuen C4-Lauf, nicht der Gate-Blocker selbst.

## Nächster konkreter Schritt

**Issue 1 umsetzen — Contract-Re-Sync gegen upstream `f6c42c6`:** Snapshot `self_improvement_v2/contracts/rainbow_signal_envelope.schema.json`, Fixtures und Validator gegen `ai4trade-bot/docs/integration/rainbow-signal-provider-contract.md` @ `f6c42c6` prüfen, Drift-Guard laufen lassen, Befund als Report unter `docs/reports/` dokumentieren, ggf. Snapshot/Fixtures per dokumentierter Prozedur (`contracts/README.md`) nachziehen. Read-only, keine Runtime-Mutation, keine Abhängigkeiten, sofort unblocked — ein Branch, ein PR, ein Report.

---

## Quality-Gate-Selbstprüfung

| # | Prüfung | Ergebnis |
|---|---|---|
| 1 | Rainbow als Execution Authority? | Nein — kein Order-Pfad im Diagramm/Plan; Guard-Test in B3 macht das dauerhaft prüfbar |
| 2 | Live-Trading implizit erlaubt? | Nein — Tracks E/F ausschließlich marker- und human-gated; abgelaufene Marker explizit dokumentiert |
| 3 | `dry_run=false` ohne Marker möglich? | Nein — nur via E3-Ceremony mit gültigem `APPROVED_EXECUTE_LIVE_CANARY` |
| 4 | Stale/degraded ausgeschlossen? | Ja — Validator-Reject, Freshness-Schwellen, Source-UNAVAILABLE-Regel, Pflicht-Tests |
| 5 | Tests oder Behauptungen? | Tests — konkrete bestehende Testdateien + neue Testfälle je Track benannt |
| 6 | Nächster Schritt PR-klein? | Ja — S1 ist read-only, fixture-basiert, ohne Abhängigkeiten |
| 7 | Bleibt #423 Source of Truth? | Ja — Track F verweist auf D1/D2 in #423; dieses Dokument ergänzt, ersetzt nicht |
