# Hermes Trading Reliability Observation Agent — Phase 1 Implementation Plan

> Für Hermes: strikt read-only beobachten, reporten und eskalieren. Keine Runtime-Veränderung vor expliziter Freigabe.

**Ziel:** Einen deterministischen Beobachtungs-Agenten bauen, der den Trading Hub in einem Zyklus prüft, Scores berechnet, Reports schreibt und kritische Probleme zwingend eskaliert.

**Architektur:** Ein einmaliger Python-Runner sammelt Container-, Cron- und Signal-Status, schreibt JSON-Report + State + Heartbeat, und erzeugt bei kritischen Befunden Escalation-Dateien plus Webhook-Alarm. Ein separater Watchdog prüft nur die Heartbeat-Frische. Beide Jobs bleiben read-only außer ihren eigenen Files.

**Tech Stack:** Python 3 (stdlib only), Docker CLI, Hermes Cron Registry (`/opt/data/profiles/orchestrator/cron/jobs.json`), JSON-Dateien, pytest, symlink-basierte Cron-Deployment.

---

## 1. Ausgangslage und Scope

| Bereich | Ist-Zustand | Entscheidung für Phase 1 |
|---|---|---|
| Bestehende Beobachtungsskripte | `orchestrator/scripts/observation_checkpoint.py`, `fleetguard_observation_snapshot.py`, `run_12h_observation_gate.py` | Nicht blind ersetzen; als Referenz verwenden |
| Cron-Quelle der Wahrheit | `/opt/data/profiles/orchestrator/cron/jobs.json` | Primär; `crontab -l` / `/etc/cron.d/*` nur expliziter Fallback und klar gekennzeichnet |
| Runtime-Outputs | `/opt/data/profiles/orchestrator/{state,reports,escalations,logs}` | Exakt diese Pfade verwenden |
| Externes Soll | `/opt/data/profiles/orchestrator/config/expected_state.json` | Muss existieren; fehlt es beim ersten Start oder ist es unlesbar, erfolgt eine degradierte Eskalation plus Minimalvorschlag im Report |
| Dokumentation | `docs/state/current-operational-state.md`, `docs/context/` | Erst nach validiertem Rollout aktualisieren |

### Nicht-Ziele
- Keine Container-Restarts, keine `config.json`-Änderungen, keine Strategie-Anpassungen.
- Kein Live-Trading, keine Dry-Run-Umstellung, keine Exchange-Credentials.
- Keine komplexe Log-Mining-Analyse; nur Container-Health, Cron-Status und Signal-Frische.
- Kein System-crontab-Abhängigkeitsmodell als Primärquelle.
- Keine automatische Reparatur, kein Cron-Selbstmanagement, keine rekursive Aufräumarbeit.
- Explizit ausgeschlossen in Phase 1: jede aktive Reparatur, jeder Container-Restart, jede Cron-Änderung, jeder Config-Edit und jede Strategie-Anpassung — auch bei hoher Confidence. Solche Mechanismen sind ausschließlich Phase 2 vorbehalten und erfordern vorher eine explizite Human-Freigabe plus zusätzliche Sicherheitsmechanismen.

### Leitplanken
- Beobachtungszustand und Prozess-Exitcode sind getrennt: kritische Befunde sind kein Script-Fail.
- Nur interne Ausführungsfehler dürfen den Prozess mit Non-Zero beenden.
- `expected_state.json` ist externes Soll, nicht vom Agenten erzeugt.
- Die neue Logik darf die bestehenden Beobachtungsskripte nicht destabilisieren.

---

## 2. Zielarchitektur

```text
Hermes Cron (5m)
  └─> trading_reliability_observer_phase1.py
        ├─ lock setzen / stale lock prüfen
        ├─ expected_state.json laden
        ├─ vorige State-Datei laden
        ├─ Container-Health prüfen
        ├─ Cronjob-Status prüfen
        ├─ Signal-Frische prüfen
        ├─ Scores + Issues deterministisch berechnen
        ├─ Report + State + Heartbeat schreiben
        └─ bei Bedarf Escalation-Datei + Webhook

Hermes Cron (10m)
  └─> trading_reliability_observation_watchdog.py
        ├─ Heartbeat-Frische prüfen
        ├─ bei Stale: Escalation + Webhook
        └─ sonst still bleiben
```

### Design-Prinzipien
1. Ein Zyklus = genau ein Report.
2. Keine aktiven Fixes, keine Service- oder Cron-Veränderungen.
3. Alles, was geschrieben wird, ist append-only oder atomisch ersetzt.
4. Die Score-Logik ist rein deterministisch und testbar.
5. Alle Pfade sind explizit und hart codiert, außer der optionalen Webhook-URL.

### Wiederverwendung vorhandener Beobachtungslogik
- Wo technisch sinnvoll und wartbar, werden Funktionen aus `orchestrator/scripts/observation_checkpoint.py`, `fleetguard_observation_snapshot.py` und `run_12h_observation_gate.py` wiederverwendet oder in `observation_common.py` extrahiert.
- Container-Health-Checks und Signal-Freshness-Logik sollen nicht unnötig neu erfunden werden, sondern konsistent in gemeinsame Helfer überführt werden.

---

## 3. Datei- und Komponentenplan

| Datei / Ziel | Aktion | Zweck |
|---|---|---|
| `orchestrator/scripts/observation_common.py` | Create | Gemeinsame Helfer: Pfade, JSON-IO, atomische Writes, Lock-Handling, Zeit-/Status-Parser |
| `orchestrator/scripts/trading_reliability_observer_phase1.py` | Create | Haupt-Runner: ein Zyklus, Scores, Report, State, Heartbeat, Escalation |
| `orchestrator/scripts/trading_reliability_observation_watchdog.py` | Create | Separater Heartbeat-Watchdog, silent-on-ok |
| `orchestrator/tests/test_trading_reliability_observer_phase1.py` | Create | Unit-Tests für Runner, Scores, Lock, Escalation, Report-Schema |
| `orchestrator/tests/test_trading_reliability_observation_watchdog.py` | Create | Unit-Tests für Heartbeat-Frische und Alarmpfad |
| `orchestrator/tests/fixtures/` | Create | Gesampelte `expected_state.json`-, State- und Heartbeat-Fixtures |
| `docs/runbooks/trading-reliability-observation-phase1.md` | Create | Operator-Runbook für manuelle Checks, Alarmpfad und Rollout |
| `docs/context/2026-06-02-trading-reliability-observation-phase1.md` | Create | Rollout-/Incident-Report nach Abschluss der Phase |
| `docs/state/current-operational-state.md` | Modify später | Erst nach validiertem Rollout den aktuellen Stand ergänzen |
| `/opt/data/profiles/orchestrator/cron/jobs.json` | Runtime-Deploy | Zwei neue Jobs: Runner + Watchdog (nicht im Git) |
| `~/.hermes/scripts/` | Runtime-Deploy | Symlinks auf die neuen Skripte, damit Hermes Cron sie findet |

### Runtime-Deployment-Konvention
- Cron-Jobs referenzieren nur den Skript-Namen, nicht den Repository-Pfad.
- `workdir` bleibt `/home/hermes/projects/trading`.
- `deliver` für beide Jobs standardmäßig `local`; die eigentliche Alarmierung läuft über Datei + Webhook.
- Die neuen Jobs werden zuerst getestet und erst danach freigeschaltet.

---

## 4. Implementierungsphasen

### Phase 1 — Contract und Baseline fixieren
**Ziel:** Vor dem ersten Code die exakten Regeln, Pfade und Datenformate einfrieren.

**Aufgaben:**
- Aktuelle Beobachtungsskripte und `docs/state/current-operational-state.md` als Referenz lesen.
- Die erwarteten Container, Cronjobs und Signal-Pfade in `expected_state.json` eindeutig normieren.
- Entscheiden, welche Signal-Pfade primär und welche Fallbacks sind.
- Bestimmen, wie `jobs.json` gegen `expected_cronjobs` verglichen wird.

**Ergebnis:** Ein sauberer Contract, damit der Runner nur noch Fakten verarbeitet und keine Annahmen raten muss.

**Abnahmekriterium:** Jede Feldbedeutung ist dokumentiert; es gibt keine offenen Pfadfragen mehr.

---

### Phase 2 — Gemeinsame Hilfsfunktionen bauen
**Ziel:** Wiederverwendbare, testbare Basisfunktionen schaffen, damit Runner und Watchdog identisch urteilen.

**Datei:** `orchestrator/scripts/observation_common.py`

**Mindestfunktionen:**
- `read_json(path)` / `write_json_atomic(path, payload)`
- `append_log_line(path, line)`
- `acquire_lock(lock_dir, pid, timestamp)` / `release_lock(lock_dir)`
- `parse_docker_ps_line(name, status, health)`
- `parse_duration_from_status(status_text)`
- `load_expected_state()`
- `load_cron_registry()` / `load_cron_fallback()`
- `evaluate_container_health(expected_containers, docker_ps_rows)`
- `evaluate_signal_freshness(signal_pattern, max_age_seconds)`
- `load_previous_state()` / `trim_history(history, maxlen=10)`
- `infer_job_exitcode(job_record)`
- `resolve_signal_candidates(pattern)`
- `latest_mtime(paths)`

**Designvorgaben:**
- Nur stdlib.
- Atomische Writes mit Temp-Datei + `os.replace`.
- Keine stillen Partial-Writes.
- Zeitstempel immer UTC und ISO-8601 mit `Z`.

**Abnahmekriterium:** Die Helper-Funktionen sind ohne Docker/cron-Realität mit Fixtures testbar.

---

### Phase 3 — Haupt-Runner implementieren
**Ziel:** Den eigentlichen Beobachtungszyklus exakt nach Prompt abbilden.

**Datei:** `orchestrator/scripts/trading_reliability_observer_phase1.py`

**Zyklus-Reihenfolge:**
1. Lock setzen.
2. `expected_state.json` laden; fehlt es beim ersten Start oder ist es unlesbar, wird der Zyklus als degraded eskaliert, ein Minimalvorschlag für die Datei wird in den Report geschrieben, und optional kann ein Bootstrap-Task daraus die Initialversion ableiten.
3. Vorigen State laden oder initialisieren.
4. Container-Health prüfen.
5. Cronjob-Status prüfen.
6. Signal-Frische prüfen.
7. Scores berechnen.
8. Issues + Confidence ableiten.
9. Report schreiben.
10. Escalation prüfen, optional Webhook posten.
11. State und Heartbeat aktualisieren.
12. Lock freigeben.

**Deterministische Score-Formeln:**

```text
unhealthy_count = Anzahl Container mit Status "unhealthy" oder "exited" oder "restarting"
exited_count = Anzahl Container mit Status "exited" (nur wenn nicht bereits in unhealthy_count enthalten)
container_score = max(0, 100 - (unhealthy_count * 30) - (exited_count * 40))

failed_cronjobs = Anzahl der erwarteten Cronjobs, deren letzter Exitcode != 0 ist
stale = 1, wenn Signal-Pipeline älter als expected_max_age_seconds, sonst 0
pipeline_score = max(0, 100 - (failed_cronjobs * 20) - (stale * 30))

if min(container_score, pipeline_score) <= 50:
    overall_status = "critical"
elif min(container_score, pipeline_score) <= 79:
    overall_status = "degraded"
else:
    overall_status = "healthy"
```

**Issue-Typen / Confidence:**

| Typ | Regel | Confidence | Eskalation |
|---|---|---:|---|
| A | Container unhealthy / exited / restarting | 90–95 | ab 85 |
| B | Erwarteter Cronjob fehlt oder Exitcode != 0 | 85–95 | ab 85 |
| C | Signal-Pipeline stale | 80–90 | ab 85 |
| D | Agent-interner Fehler / Lock-Kollision | 100 | immer |

**Wichtige Nuancen:**
- Ein Container, der nur aus `docker ps` verschwindet, wird für das Scoring als `exited_or_missing` behandelt.
- Wenn eine Score-Komponente nicht berechnet werden kann, wird sie auf 0 gesetzt und der Status wird kritisch.
- Kritische Beobachtungen beenden den Prozess nicht mit Fehlercode, solange der Zyklus erfolgreich abgeschlossen wurde.
- Non-Zero-Exit ist nur für echte Ausführungsfehler reserviert.

**Report-Schema (Mindestfelder):**
- `timestamp`, `agent_id`, `cycle_id`, `mode`
- `system_health.container_score`, `pipeline_score`, `overall_status`
- `detected_issues[]` mit `type`, `description`, `confidence`, `first_seen`, `occurrences_last_30min`
- `escalation_triggered`, `escalation_file`
- `recommendation_for_human`, `next_cycle_in_seconds`
- `state_snapshot` als gekürzte Kopie

**State-Schema (Mindestfelder):**
- `last_successful_cycle`
- `history` mit Ringbuffer-Größe 10
- `open_issues`
- `last_cron_exitcodes`
- `last_report_path`
- `last_escalation_path`
- `overall_status`

**Abnahmekriterium:** Ein manueller Lauf erzeugt exakt einen Report, aktualisiert Heartbeat und State, und schreibt bei kritischen Fällen zusätzlich eine Eskalationsdatei.

---

### Phase 4 — Externen Heartbeat-Watchdog bauen
**Ziel:** Die Liveness des Beobachtungs-Agenten selbst absichern, ohne den Runner zu verändern.

**Datei:** `orchestrator/scripts/trading_reliability_observation_watchdog.py`

**Regeln:**
- Heartbeat-Frische prüfen.
- Schwelle: älter als 12 Minuten = stale.
- Bei frischem Heartbeat: stiller Exit.
- Bei stale Heartbeat: Escalation-Datei schreiben und denselben Webhook anrufen.
- Keine Runtime-Veränderung am Runner.
- Kein weiterer Watchdog-Watchdog; keine Rekursion.

**Webhook-Verhalten:**
- Primär `/usr/bin/curl`.
- URL aus `HERMES_ALERT_WEBHOOK` oder `/opt/data/profiles/orchestrator/config/alert_webhook.url`.
- Wenn keine URL vorhanden oder der Call fehlschlägt: Datei-Eskalation bleibt verbindlich, der Zyklus bleibt aber nachvollziehbar im Log.

**Abnahmekriterium:** Frischer Heartbeat erzeugt keine Ausgabe; stale Heartbeat erzeugt exakt eine Escalation und einen Webhook-Versuch.

### 4.5 Ergänzungen aus finaler Review (2026-06-02)

Folgende vier Punkte aus der finalen Review sind verbindlich und werden in Phase 1 berücksichtigt:

**1. Wiederverwendung bestehender Beobachtungslogik**
- Wo technisch sinnvoll und wartbar, wird Logik aus den bereits existierenden Skripten wiederverwendet oder extrahiert: `observation_checkpoint.py`, `fleetguard_observation_snapshot.py`, `run_12h_observation_gate.py`.
- Insbesondere Container-Health-Checks und Signal-Freshness-Logik sollen nicht komplett neu geschrieben werden, sondern wo möglich als Funktionen/Module in `observation_common.py` konsolidiert werden.
- Ziel: Weniger Code-Duplikation, bessere Wartbarkeit und höhere Konsistenz mit bestehender Beobachtung.

**2. Primäre Quelle für Cronjob-Status**
- Der Observer nutzt primär die Hermes-eigene Cron-Registry: `/opt/data/profiles/orchestrator/cron/jobs.json`.
- Das Parsen von `crontab -l` oder `/etc/cron.d/*` ist nur als expliziter Fallback erlaubt und muss im Report klar als Fallback markiert werden.
- Die kanonische Quelle bleibt die Hermes-Registry; System-Crontab ist nicht die Standardquelle.

**3. Bootstrap / Initialisierung von `expected_state.json`**
- Falls `/opt/data/profiles/orchestrator/config/expected_state.json` beim ersten Start fehlt oder nicht lesbar ist, bricht der Observer nicht sofort mit kritischer Eskalation ab.
- Stattdessen wird eine klare Warnung erzeugt, eine Eskalation der Stufe `degraded` ausgelöst und ein minimaler Default-Vorschlag für `expected_state.json` im Report dokumentiert.
- Optional kann ein separater Bootstrap-Task oder Hilfsskript die Initialversion aus aktuell laufenden Containern und bekannten Cronjobs ableiten.

**4. Webhook-Konfiguration & Eskalationspfad**
- Die Webhook-Alarmierung ist in Phase 1 optional, aber dokumentiert: Ohne konfigurierte `HERMES_ALERT_WEBHOOK` oder `alert_webhook.url` funktioniert nur die Datei-basierte Eskalation unter `/opt/data/profiles/orchestrator/escalations/`.
- In diesem Fall muss ein externer Watcher die `escalations/`-Dateien regelmäßig prüfen und weiterleiten, zum Beispiel per Mail, Telegram oder ntfy.
- Ein produktiver Betrieb ohne Webhook oder externen Watcher ist nicht empfohlen.

---

### Phase 5 — Tests und Fehlerfälle absichern
**Ziel:** Alle kritischen Pfade deterministisch beweisen, bevor irgendetwas per Cron läuft.

**Dateien:**
- `orchestrator/tests/test_trading_reliability_observer_phase1.py`
- `orchestrator/tests/test_trading_reliability_observation_watchdog.py`
- `orchestrator/tests/fixtures/*`

**Testmatrix:**
- Healthy: alle Scores > 79, keine Eskalation.
- Missing `expected_state.json`: degradierte Eskalation mit Minimalvorschlag; bei fehlgeschlagenem Bootstrap wird der Zustand kritisch behandelt.
- Stale Signal: `pipeline_score` fällt korrekt, Report bleibt lesbar.
- Unhealthy Container: `container_score` fällt korrekt.
- Cronjob-Fehler: wiederholte Non-Zero-Inferenz wird in der State-Historie gezählt.
- Lock bereits aktiv und jung: stiller Exit.
- Lock alt oder defekt: Eskalation + Lock-Übernahme.
- Webhook fehlt: Datei-Eskalation bleibt korrekt.
- Watchdog mit frischem Heartbeat: kein Output.
- Watchdog mit altem Heartbeat: Alarmpfad korrekt.

**Verifikationskommandos:**
```bash
python3 -m pytest orchestrator/tests/test_trading_reliability_observer_phase1.py -q
python3 -m pytest orchestrator/tests/test_trading_reliability_observation_watchdog.py -q
python3 -m json.tool /opt/data/profiles/orchestrator/reports/report_<timestamp>.json
python3 -m json.tool /opt/data/profiles/orchestrator/state/observation_state.json
```

**Abnahmekriterium:** Alle Tests laufen grün, und die Failure-Fixtures erzeugen exakt die erwarteten Eskalationen.

---

### Phase 6 — Deployment, Cron und Dokumentation
**Ziel:** Die geprüfte Implementierung kontrolliert in den Betrieb bringen.

**Schritte:**
1. Skripte in `orchestrator/scripts/` ablegen.
2. Symlinks in `~/.hermes/scripts/` setzen.
3. Zwei Cronjobs in `/opt/data/profiles/orchestrator/cron/jobs.json` ergänzen:
   - Runner: alle 5 Minuten, `no_agent=true`, `deliver=local`
   - Watchdog: alle 10 Minuten, `no_agent=true`, `deliver=local`
4. Erst nach erfolgreichem Smoke-Test die Jobs aktivieren.
5. Erst nach 24h stabiler Beobachtung die Phase als produktiv markieren.
6. `docs/runbooks/`, `docs/context/` und danach `docs/state/current-operational-state.md` aktualisieren.

**Dokumentations-Update nach Abschluss:**
- Was beobachtet wurde.
- Welche Pfade tatsächlich genutzt werden.
- Welche Eskalationsarten aufgetreten sind.
- Welche Teile bewusst unverändert geblieben sind.

**Abnahmekriterium:** Der neue Agent läuft im Cron, bleibt read-only, schreibt nur seine erlaubten Artefakte und meldet kritische Zustände zuverlässig.

---

## 5. Verifikation und Rollout-Gates

| Gate | Muss erfüllt sein | Beweis |
|---|---|---|
| Gate 1 | Hilfsfunktionen sind testbar | Unit-Tests grün |
| Gate 2 | Runner erzeugt Report/State/Heartbeat | Manueller Smoke-Test |
| Gate 3 | Kritische Fälle eskalieren | Escalation-Datei + Webhook-Versuch |
| Gate 4 | Watchdog bleibt still bei frischem Heartbeat | Leerer Output |
| Gate 5 | Cron-Integration verursacht keine Nebenwirkungen | 24h Beobachtung ohne Fehlalarm |
| Gate 6 | Zwei Wochen stabil | Kein unbeobachteter Ausfall, keine falschen Alarme |

### Rollout-Reihenfolge
1. Code + Tests.
2. Manuelle Einzellausführung außerhalb des Cron.
3. Pausierte Cron-Einträge anlegen.
4. Runner aktivieren.
5. Watchdog aktivieren.
6. 24h beobachten.
7. Nach 2 Wochen Phase-1-Abschluss dokumentieren.

---

## 6. Risiken und offene Punkte

| Risiko | Auswirkung | Gegenmaßnahme |
|---|---|---|
| `docker ps` zeigt keine exited Container | Exited und missing müssen zusammen behandelt werden | Missing als `exited_or_missing` klassifizieren |
| `jobs.json` enthält keine expliziten Exitcodes | Cron-Fehler nur indirekt inferierbar | `last_status` / `last_error` normalisieren und in State merken |
| `expected_state.json` fehlt | Kein gültiges Soll | Beim ersten Start degraded + Eskalation + Minimalvorschlag im Report; optionaler Bootstrap-Task kann eine Initialversion ableiten |
| Webhook-URL fehlt oder ist ungültig | Kein Push-Alarm | Datei-Eskalation bleibt bindend |
| Pfad-Divergenz zwischen Repo und Runtime | Falsche Writes / falsches Lesen | Harte Pfadkonstanten + Fixtures + Smoke-Test |
| Zu viel Log-Rauschen | Warnungen werden übersehen | Nur kurze Summary in `observation.log`, alles andere in JSON |

### Offene Entscheidungen
- Welcher Name für die beiden Cronjobs final verwendet wird.
- Ob die Report-Datei zusätzlich eine kurze `.md`-Kurzfassung bekommt oder JSON-only bleibt.
- Ob die bestehende 24h-Beobachtung später auf den neuen Agenten als Datenquelle erweitert wird.

---

## 7. Nächster Schritt

Wenn du freigibst, implementiere ich Phase 1 genau in dieser Reihenfolge:
1. `observation_common.py`
2. Runner
3. Watchdog
4. Tests
5. Cron-Deployment
6. Docs

Bis dahin bleibt alles nur Plan, ohne Runtime-Änderung.