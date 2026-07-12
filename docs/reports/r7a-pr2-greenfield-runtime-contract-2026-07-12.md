# R7A PR-2 — Greenfield Runtime Contract Report

**Datum:** 2026-07-12
**Branch:** `feat/r7a-greenfield-compose-rainbow-tests`
**Finaler Head-SHA:** `02ae1a76d845bf43ba7a1517ec557db9782c73c1`
**Base:** `7aec717` (PR #519 merge — R7A PR-1 Docs)
**Issue:** #504 (R7A), #496 (R7 Measurement), #423 (Live-Gate)
**Autor:** Hermes Orchestrator (Repo-Teil) + Claude Code (Runtime-Contract-Fix, Live-Smoke, Audit-Closure)

---

## 0. Hinweis zu dieser Revision

Diese Datei wurde ursprünglich vor der Runtime-Validierung geschrieben und beschrieb
einen rein repo-only Zwischenstand ("kein Container gestartet", "74 Tests",
"unpinned freqtrade:stable"). Diese Angaben waren zum Zeitpunkt des Schreibens korrekt,
sind aber durch die seither erfolgte vollständige Runtime-Contract-Validierung (siehe
Abschnitt 7) überholt. Diese Revision ersetzt den Bericht durch den tatsächlichen
Endstand von PR #524 vor dem Merge.

---

## 1. Commits auf diesem Branch (seit Base `7aec717`)

| SHA | Nachricht |
|---|---|
| `885e264` | feat(runtime): reconcile HermesTrader dry-run topology for Rainbow R7 |
| `d7e4791` | fix(rainbow): PR #524 auf gefixten ai4trade-bot-Runtime-Contract pinnen |
| `149e3a3` | fix(rainbow): Egress-Netz und Freqtrade-Image-Pinning fuer R7A |
| `02ae1a7` | fix(rainbow): Smoke-Test-Fixes - UID-Ownership, Telegram-Env, JWT-Laenge, ai4trade-bot-Pin |

## 2. Upstream-Fix in ai4trade-bot (Root-Cause, nicht Gateway-Wrapper)

Der ursprüngliche Rainbow-Contract-Bruch (falsches Dockerfile, ignorierter
`RAINBOW_CONFIG`, kein read-only-Enforcement, `/health` immer "healthy",
Heartbeat-Pfad-Mismatch) wurde direkt im Rainbow-Quellcode behoben, nicht durch
einen Wrapper in trading-hub:

| PR | Merge-SHA | Inhalt |
|---|---|---|
| ai4trade-bot#78 | `a43a80cf66c7fb77e07b25a650a72c3303d26791` | `read_only`-Default, `RAINBOW_CONFIG` wird respektiert, `extra="forbid"` explizit, kanonischer Heartbeat-Pfad, mutierende Routen → 405 im read-only-Modus, `/health` fail-closed mit Grace-Periode |
| ai4trade-bot#79 | `cd63051545e9b27235f47a3bbb5de858782fcd20` | `CanonicalSignalRegistry`-Default-Pfad korrigiert (gleiche Pfad-Präfix-Bugklasse wie Heartbeat, live beim Runtime-Smoke entdeckt) |

## 3. Geänderte/neue Dateien (finaler Stand)

| Datei | Änderung |
|-------|----------|
| `docker-compose.hermestrader-dryrun.yml` | Rainbow `dockerfile:` ergänzt, Env auf reale Settings reduziert, `trading_egress`-Netz + Zuordnung aller 6 Services, `FREQTRADE__TELEGRAM__ENABLED=false` entfernt (5×) |
| `services/rainbow/rainbow.include.yml` | gleiche Fixes gespiegelt |
| `config/rainbow.internal.yml` | auf reale `RainbowSettings`-Felder reduziert (`read_only`, `evaluation.enabled`) |
| `freqtrade/Dockerfile.hermes10000` | Digest-Pin (sha256:87aa5c6d...), `mkdir -p .../logs` vor `chown -R 10000:10000`, `COPY entrypoint.sh` statt Inline-`printf` |
| `freqtrade/entrypoint.sh` (neu) | Permission-Fix mit sichtbarem WARN-Logging statt stillem Fehler-Verschlucken |
| `freqforge/user_data/config.example.json`, `freqforge-canary/user_data/config.example.json`, `freqtrade/bots/regime-hybrid/user_data/config.example.json`, `freqtrade/bots/webserver/user_data/config.example.json` | `jwt_secret_key`-Platzhalter 28→39 Zeichen (Freqtrade minLength: 32), Freigabe eingeholt |
| `docs/decisions/ADR-2026-07-11-hermes-r7a-dryrun-topology.md` | Pin-Referenz aktualisiert auf finalen Stand (ai4trade-bot#78 + #79), Netzwerk-Notiz (trading_internal + trading_egress) |
| `tests/test_hermestrader_dryrun_compose.py` | 9 neue Testklassen (Dockerfile-Pin, Read-Only-Env, Config-Schema, Heartbeat-Pfad, ADR-Pin-Dokumentation, Egress-Netz x3, Image-Pin, Entrypoint-Sichtbarkeit, UID-Ownership x2, kein Per-Bot-Telegram, JWT-Länge) |
| `docs/reports/r7a-pr2-greenfield-runtime-contract-2026-07-12.md` | diese Datei — auf Endstand korrigiert |

## 4. Fleet-Modell

Unverändert zur ursprünglichen Planung.

**Selected:** OPTION_C
**Default-Services:** freqforge + canary + regime-hybrid + webserver + rainbow
**Profile-gated:** freqai-rebel (`profiles: ["rebel"]`)

## 5. Netzwerk-Topologie (korrigiert gegenüber Ursprungsplan)

Ursprünglich war ausschließlich `trading_internal` (`internal: true`) vorgesehen —
das hätte jeglichen Exchange-Zugriff (Bitget) unmöglich gemacht. Korrigiert auf
Zwei-Netz-Modell:

- `trading_internal` (`internal: true`) — bleibt bestehen, kein externer Zugriff
- `trading_egress` (Standard-Bridge, kein internal) — neu, für Exchange-API-Zugriff

Alle 6 Services (5 Freqtrade-Bots + Rainbow) hängen an beiden Netzen. Kein neues
Host-Port-Mapping.

## 6. Dockerfile.hermes10000 — Live-gefundene Bugs, gefixt

Ursprünglicher Bericht dokumentierte `freqtradeorg/freqtrade:stable` (unpinned) als
offenes Risiko. Beim tatsächlichen Build/Start wurden zwei zusätzliche, vorher
unbekannte Bugs entdeckt und root-cause-gefixt:

1. **Image ungepinnt** → gefixt: Digest-Pin `sha256:87aa5c6d65359b34e9d99a0bb260a38c0efe0315253811e6f48c2afe8f278a6a`.
2. **UID-Ownership-Crash-Loop** (alle 4 Bots): Base-Image enthält `/freqtrade/user_data`
   mit UID 1000 (ftuser vor Remap), Runtime läuft als UID 10000
   (`user: "10000:10000"` ab Container-Start) → Entrypoint konnte als
   Nicht-Root-Prozess strukturell keine fremden Dateien chowns. Gefixt im Dockerfile
   (`chown -R 10000:10000` als root zur Build-Zeit) + `mkdir -p .../logs` **vor**
   dem chown, da das Verzeichnis im Base-Image gar nicht existierte (Docker
   kopiert Volume-Inhalt nur bei Erstinitialisierung aus dem Image, wenn der Pfad
   dort existiert).
3. **Silent-Failure im Entrypoint** (Fehler wurden nach /dev/null umgeleitet und
   ignoriert) hatte den Bug #2 ursprünglich komplett unsichtbar gemacht → durch
   sichtbares WARN-Logging ersetzt, was genau diesen Fehler beim ersten Smoke-Run
   überhaupt erst sichtbar machte.

## 7. Runtime-Smoke-Evidenz (neu — im Ursprungsbericht als "R5a-Scope" verschoben, tatsächlich durchgeführt)

Ausgeführt auf HermesTrader (`/opt/data/projects/trading-hub`), autorisiert für
Docker-Host-Mutationen (Build/Start/Restart/Smoke/Rollback), temporärer Dry-Run
ausschließlich zur Kontraktvalidierung — **keine Live-Aktivierung, keine
persistente Fleet-Übernahme**.

```
docker compose -f docker-compose.hermestrader-dryrun.yml config   # fehlerfrei
docker compose -f docker-compose.hermestrader-dryrun.yml build --pull
docker compose -f docker-compose.hermestrader-dryrun.yml up -d
```

**Ergebnis:** Alle 5 Ziel-Services (rainbow, freqforge, canary, regime-hybrid,
webserver) erreichten Docker-Status `healthy`. `freqai-rebel` korrekt via
`profiles: ["rebel"]` ausgeschlossen.

- **Rainbow-Contract live geprüft:** `docker inspect` bestätigt Build via
  `rainbow.Dockerfile` (uvicorn:8000, nicht python main.py:9090). `GET /health` →
  200 mit vollständigem JSON-Body (`read_only: true`, Heartbeat fresh, Store ready,
  Collectors laufend). `POST /webhooks/subscribe` → 405. `DELETE /webhooks/x` → 405.
- **Egress-Netz live geprüft:** Rainbow-TA-Collector verarbeitet echte Bitget-Signale
  ("Collector 'ta': 3 Signal(e) verarbeitet"). Alle 4 Freqtrade-Bots laden erfolgreich
  697 Bitget-Märkte und verbinden sich per CCXT.
- **UID-10000-Schreibrechte live geprüft:** `docker exec ... id` → uid=10000; SQLite-
  DB-/WAL-Dateien nachweislich mit UID/GID 10000 geschrieben.
- **dry_run=true live geprüft:** DB-Dateinamen enthalten `.dryrun.`.
- **Zusätzliche Sicherheitsschicht bestätigt:** Projekt-eigener Kill-Switch
  (`primo_signal`, Modus `HALT_NEW`) blockiert aktiv alle Order-Entries — unabhängig
  von dry_run, als weitere Absicherung über das ursprünglich Geprüfte hinaus.
- **Rollback-Drill live durchgeführt:** `docker compose down` (ohne `-v`). Alle
  Volumes erhalten. Unabhängige Container (`hermes`, `rainbow-live-*`,
  `docker-socket-proxy`) unberührt. Zum Zeitpunkt dieses Berichts erneut verifiziert:
  Stack ist sauber down, keine verwaisten Container.

### Backup-Snapshots (Restic, real verifiziert)

| Snapshot-ID | Zeitpunkt | Tag | Zweck |
|---|---|---|---|
| `643df416` | 2026-07-12 07:32:27 | `pre-r7a-rainbow-mutation-2026-07-12` | Preflight vor jeglicher Repo-/Runtime-Mutation |
| `8fc7d2b6` | 2026-07-12 08:41:36 | `pre-r7a-build-start-2026-07-12` | Preflight unmittelbar vor Docker-Build/Start |

### Unabhängiger Zusatzfund (nicht Teil von PR #524, während Preflight entdeckt)

Eine separate, vorbestehende `rainbow-live`-Instanz war öffentlich auf Ports
18080/18081 erreichbar und lief mit altem, nicht-fail-closed Rainbow-Code. Sofort
per DOCKER-USER-iptables-Regel (Post-DNAT, Ziel-Container-IP + interner Port)
abgesichert, unabhängig vom PR-524-Merge-Entscheid. Regel weiterhin aktiv
(verifiziert bei Erstellung dieses Berichts).

## 8. Tests (aktualisiert)

Test suite: `tests/test_hermestrader_dryrun_compose.py`

```
106 passed, 1 skipped in 0.20s
```

(Ursprünglicher Bericht: 74 Tests, repo-only. Zuwachs von 32 Tests deckt Dockerfile-
Pin, Read-Only-Env, Config-Schema-Allowlist, Heartbeat-Pfad, ADR-Pin-Dokumentation,
Egress-Netz-Topologie, Freqtrade-Image-Pin, Entrypoint-Sichtbarkeit, UID-Ownership
und Telegram-/JWT-Fixes ab. Der eine Skip ist der erwartete Ausschluss von Rainbow
im Pro-Bot-Telegram-Test.)

Main Gate CI: **pass** bei Head-SHA `02ae1a76d845bf43ba7a1517ec557db9782c73c1`.

Eine vorbestehende, unabhängige Flaky-Test (`tests/rainbow/evaluation/test_cache.py::TestEvaluationCacheTTL::test_expired_entry_returns_none`,
TTL=0-Timing-Edge-Case) tritt identisch auf unmodifiziertem `master` auf (verifiziert
via git stash) — nicht Teil dieses Fixes, bewusst nicht angefasst.

## 9. Secret Scan

Unverändert: alle committeten Config-Dateien enthalten ausschließlich CHANGE_ME-
Platzhalter (inkl. des verlängerten jwt_secret_key-Platzhalters). Keine echten
Credentials.

## 10. Bekannte Rest-Risiken (aktualisiert)

| Risiko | Status | Hinweis |
|--------|--------|---------|
| `Dockerfile.hermes10000` ungepinnt | **BEHOBEN** | Digest-Pin umgesetzt |
| UID-Ownership-Crash-Loop | **BEHOBEN** | Dockerfile-chown + mkdir-Reihenfolge |
| Rainbow-Config-Schema-Mismatch | **BEHOBEN** | via ai4trade-bot#78 |
| Heartbeat-/DB-Pfad-Widerspruch | **BEHOBEN** | via ai4trade-bot#78 + #79 |
| Freqtrade-Telegram-Schema-Crash | **BEHOBEN** | Env-Var entfernt, kein Per-Bot-Telegram (Routing-Architektur separates Thema) |
| jwt_secret_key zu kurz | **BEHOBEN** | Freigabe eingeholt, Platzhalter verlängert |
| Rainbow-Build-Context referenziert externes Repo | OPEN | ai4trade-bot-SHA muss bei künftigen Deploys weiter geprüft werden (Pin-Test in Testsuite vorhanden) |
| Legacy-Compose-Test (`test_docker_compose_contracts.py`) testet RSI/Momentum | KNOWN | Legacy, nicht Teil des Greenfield-Contracts |
| Freqtrade-Telegram-Routing über Hermes-Bot | OFFEN, separates Thema | Architektur-Empfehlung: Freqtrade-webhook-Feature statt natives telegram-RPC (1:1-Token-Limitierung), noch nicht implementiert |

## 11. Rollback

**Rollback = `git revert <merge-commit>`** für den Repo-Teil.
Runtime-Rollback wurde real durchgeführt und verifiziert (Abschnitt 7): `docker
compose down` ohne `-v`, alle Volumes erhalten, keine Fremd-Container betroffen.

## 12. Bestätigung (korrigiert)

> Diese PR wurde vollständig runtime-validiert, nicht nur repo-only geprüft.
> Container wurden gebaut, gestartet, live geprüft und sauber wieder gestoppt
> (kein -v, alle Volumes erhalten).
> Keine dauerhafte Host-Mutation außerhalb der isolierten Dry-Run-Validierung.
> dry_run=false ist nicht enthalten, in keinem Zeitpunkt aktiviert gewesen.
> Live-Trading bleibt #423-gated. Kill-Switch (primo_signal, HALT_NEW) aktiv
> bestätigt.
> Issue #496 (R7-Messung) bleibt blockiert bis zum separaten R5a-Deployment-/
> Parity-Schritt.
