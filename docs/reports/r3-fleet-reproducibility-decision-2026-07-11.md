# HermesTrader Root Runtime R3: Fleet Reproducibility Decision

**Datum:** 2026-07-11
**Status:** DECIDED
**Repo:** /opt/data/projects/trading-hub (GoLukeEnviro/trading-hub)
**HEAD:** 8013cfd
**Roadmap-Phase:** R3 (Fleet Reproducibility Decision)

---

## 1. Einschätzung

R3 entscheidet pro Bot, ob er aus versionierten Repo-Quellen auf HermesTrader reproduzierbar ist. Die Entscheidung erfolgt auf zwei Ebenen:

**Ebene 1 (Bot-Level):**
- freqforge: REPRODUCIBLE_NOW
- canary: REPRODUCIBLE_NOW
- regime-hybrid: REPRODUCIBLE_NOW
- rebel: NOT_REPRODUCIBLE
- webserver: Support-Service (separat bewertet in R4)

**Ebene 2 (Fleet-Level):**
```
SELECTED_FLEET_MODEL = OPTION_C
CANONICAL_MEASUREMENT_FLEET = [freqforge, regime-hybrid, canary]
R7_SUFFICIENCY = 3 Bots valid für SI-v2 shadow/dry-run Messung
FreqAI-Coverage deferred bis rebel reproduzierbar (R4+)
```

R3 ist eine reine Entscheidung. Es wurden keine Live-Mutationen durchgeführt.

---

## 2. Beobachtung

### 2.1 Live-Fleet auf agent0 (read-only Verifikation, 2026-07-11)

Vier der fünf Services laufen auf Custom-Images. Kein Image spiegelt das Haupt-Compose wider.

| Container | Live-Image | Image-ID | Repo-Reproduktions-Quelle |
|---|---|---|---|
| trading-freqtrade-freqforge-1 | freqtrade-hermes1337:freqforge-c5 | af2a49a68e60 | UID 1337 (nicht Repo); HermesTrader-Äquivalent: Dockerfile.hermes10000 |
| trading-freqtrade-regime-hybrid-1 | freqtrade-hermes1337:regime-hybrid-c5 | af2a49a68e60 | wie freqforge (gleiches geteiltes Image) |
| trading-freqtrade-freqforge-canary-1 | freqtradeorg/freqtrade:stable | 3c79f4f57817 | Stock; Ziel = Dockerfile.hermes10000 |
| trading-freqai-rebel-1 | freqtrade-hermes1337:freqai-rebel-c25 | cf3108ad4ec6 | NEIN — FreqAI-Deps + directory_operations.py-Patch fehlen |
| trading-freqtrade-webserver-1 | freqtrade-hermes1337:webserver-c5 | af2a49a68e60 | Support-Service (kein Trading-Bot) → R4 |

Hinweis: Die Suffixe `-c5`/`-c25` sind Build-Versions-Tags OHNE Bezug zum Roadmap-Task C5 (New Canary Measurement Window) — reiner Zufall.

### 2.2 Drei widersprüchliche Compose-Definitionen

Keine Definition spiegelt den Live-Zustand:

1. **Haupt-`docker-compose.yml`** (12320 B): 4× `freqtradeorg/freqtrade:stable` + Rebel auf `freqtrade-freqai-rebel:custom` (OLD c24-Image 3470e4282f6b, nicht Live).
2. **`freqtrade/bots/freqai-rebel/docker-compose.yml`** (586 B): Stock `freqtradeorg/freqtrade:2026.3_freqai` + externes Named-Volume, Container `freqai-rebel`.
3. **Live:** Custom `freqtrade-hermes1337:*` + Bind-Mounts auf `/home/hermes/projects/trading/freqtrade/...`. Quelle (Compose/Dockerfile) NICHT im Repo.

### 2.3 Strategie-Drift-Prüfung (sha256, repo vs agent0-live)

Alle aktiven Strategien matchen exakt. Kein Drift.

| Bot | Strategie | Hash (repo = live) |
|---|---|---|
| freqforge | FreqForge_Override.py | a01284cd…057e7 |
| canary | FreqForge_Override.py | 910b40f9…0b80c |
| regime-hybrid | RegimeSwitchingHybrid_v7_v04_Integration.py | e9791f15…ee587 |
| rebel | RebelLiquidation.py | de47905b…265a2 |
| rebel | RebelLiquidationWFTop15.py | 9b25b8e4…8337 |
| rebel | RebelXGBoostClassifier.py (freqaimodel) | 13e15c25…81c7 |

Live-regime-hybrid hat ~35 R&D-Strategien; Repo enthält nur aktive (intentionale Kuratierung). Config.json (mit Secrets) nur auf agent0, Content NICHT gelesen (nur Größe via ls).

### 2.4 Rebel directory_operations.py-Patch

Patch in `/freqtrade/freqtrade/configuration/directory_operations.py` (3,78 kB, NICHT im Repo). Diff erstellt mit `docker create + cp` (kein Prozessstart):

**Änderungen stock→rebel:**
- Fügt `import os` hinzu
- Fügt `_SKIP_CHOWN_NAMES = frozenset({"primo_signal_state.json"})` hinzu
- Fügt Funktion `_chown_single()` hinzu
- Rewritet `create_userdata_dir`-chown-Logik: chownt Pfade INDIVIDUELL statt `chown -R`
- Überspringt read-only Bind-Mounts (primo_signal_state.json)

**Zweck:** freqtrades `chown -R ftuser:` scheitert an rebels RO-Bind-Mount.

Diff erstellt gegen bewegliches Tag `:stable` (Version-Drift in Comments sichtbar, nicht rebels exakt gepinnte Basis).

### 2.5 Rebel NOT_REPRODUCIBLE — entscheidender Befund

**user_data/models/ auf agent0:**
- Größe: **1,2 GB** trainierte FreqAI-Artefakte
- Inhalt: `historic_predictions.pkl` etc., 9 Modell-Verzeichnisse (rebel-liquidation-v1/v2/wrapper/...)
- Repo-`.gitignore`: Schließt `user_data/models/`, `*.pkl`, `*.joblib`, `*.sqlite` EXPLIZIT aus
- Keine Modelldatei committet

**Folge:** Diese trainierten Artefakte sind nicht aus Repo-Quellen reproduzierbar (würden Retraining brauchen — datenabhängig, nicht-deterministisch) und kein zulässiger Artefakt-Extrakt (Hauptplan R3 schließt das aus).

**Zusätzliche Hürden:**
- `datasieve`+`xgboost` (FreqAI-Deps, aus Image-History) nicht in `Dockerfile.hermes10000`
- Basis nicht gepinnt
- RebelXGBoostClassifier.py importiert `from freqtrade.freqai.prediction_models.XGBoostClassifier import (...)`

RebelLiquidation.py importiert numpy/talib/pandas/freqtrade.strategy.

### 2.6 Greenfield-Testbuild (HermesTrader, isoliert)

**Build:**
- `Dockerfile.hermes10000` baut sauber → Image `r3-test:hermes10000`
- Base: `freqtradeorg/freqtrade:stable@sha256:87aa5c6d65359b34e9d99a0bb260a38c0efe0315253811e6f48c2afe8f278a6a` (gepinnter Digest)
- UID/GID 10000 verifiziert (`uid=10000(ftuser) gid=10000(ftuser)`)

**Strategie-Import-Test (gehärtet):**
- `--network none --cap-drop ALL --security-opt no-new-privileges`
- tmpfs user_data uid=10000
- Mit `freqtrade/shared/` gemountet + `PYTHONPATH=/ud:/shared`

**Ergebnisse:**
- freqforge FreqForge_Override → OK ✅
- canary FreqForge_Override → OK ✅
- regime-hybrid RegimeSwitchingHybrid_v7_v04_Integration → OK ✅

**Abhängigkeiten:** Alle 3 importieren Custom-Module aus `freqtrade/shared/` (`primo_signal`, `fleetguard_v1`, `fleet_risk_manager`). Repo hat `shared/` vollständig. R4 muss `shared/` nach `/freqtrade/shared` mounten + PYTHONPATH setzen.

**rebel:** In R3 nicht testbar (FreqAI-Image fehlt) → bestätigt NOT_REPRODUCIBLE.

**Cleanup:** Verifiziert. Test-Image + Container label-basiert entfernt. Live-Fleet auf beiden Hosts unangetastet.

### 2.7 #504 Scope-Carve-out (Gate)

Autorisierender Kommentar auf Issue #504 (issuecomment-4947132003):

Erlaubt R3 isolierte nicht-trading Docker-Test-Builds + ephemere Diagnose-Container.

**Conditions:**
- no trading mutation
- no network
- no trade loop
- no persistent volumes
- dedicated labels
- full audit
- exact cleanup
- dry_run=false prohibited
- R4/R5a out of scope

R3 eingehalten.

### 2.8 State-File-Drift (Bot-Runtime, außerhalb R3-Scope)

Live-Verifikation (2026-07-11) zeigt alle 4 Bots + Webserver auf agent0 als **laufend** (Dry-Run): freqforge (Up, healthy), canary (Up), regime-hybrid (Up), rebel (Up 40h), webserver (Up 8d). `docs/state/current-operational-state.md` (Stand Rainbow-R5-Reconciliation) behauptet jedoch „no bots currently running" / alle „Not running — requires explicit approval to restart". Diese Diskrepanz wird im R3-PR als NOTE in der State-Datei markiert und für separate Governance-Klärung flagged — NICHT in R3 aufgelöst (Ursache ungeklärt, außerhalb Reproduzierbarkeits-Scope).

---

## 3. Ursache

Warum die Handoff-Prämissen falsch waren:

1. **Nur Rebel Custom-Image:** Falsch. 4/5 Services laufen auf Custom-Images (freqforge, regime-hybrid, rebel, webserver). Nur canary ist Stock.

2. **Haupt-Compose spiegelt Live:** Falsch. Haupt-Compose hat 4× Stock + Rebel auf OLD custom-image. Live hat 3× Custom (freqforge, regime-hybrid, rebel) + 1× Stock (canary) + 1× Custom (webserver).

3. **Shared-Library-Muster:** freqforge, canary, regime-hybrid importieren Custom-Module aus `freqtrade/shared/`. Repo hat `shared/` vollständig. R4 muss mounten + PYTHONPATH setzen.

4. **FreqAI-Zustandsbehaftetheit:** Rebel hat 1,2 GB trainierte Modelle (`user_data/models/`). Diese sind nicht aus Repo-Quellen reproduzierbar (datenabhängig, nicht-deterministisch). Repo schließt Modelle per `.gitignore` aus. Retraining wäre notwendig — substantieller Aufwand.

---

## 4. Umsetzung

Durchgeführt:

1. **read-only Live-Verifikation** auf agent0 (4 Bots, Image-IDs, Strategie-Hashes, directory_operations.py-Patch).
2. **docker create + cp** für Patch-Diff (kein Prozessstart, keine Mutation).
3. **Isolierter Testbuild** auf HermesTrader:
   - `Dockerfile.hermes10000` Build
   - Strategie-Import-Test (gehärtet)
   - UID/GID-Verifikation
4. **Cleanup:**
   - Test-Image + Container label-basiert entfernt
   - Live-Fleet auf beiden Hosts unangetastet verifiziert
   - Persistente Volumes unangetastet

Keine Trading-Mutation. Kein Netzwerk. Kein Trade-Loop.

---

## 5. Validierung

**Testbuild-Ergebnisse:**
- freqforge: FreqForge_Override importiert OK ✅
- canary: FreqForge_Override importiert OK ✅
- regime-hybrid: RegimeSwitchingHybrid_v7_v04_Integration importiert OK ✅
- rebel: NOT_REPRODUCIBLE (FreqAI-Image fehlt, 1,2 GB Modelle nicht im Repo, Patch nicht committet)

**UID-Check:**
- `Dockerfile.hermes10000`: uid=10000(ftuser) gid=10000(ftuser) ✅

**Cleanup-Nachweis:**
- Test-Image r3-test:hermes10000 entfernt (sha256:10ea4619…)
- Test-Container entfernt (label `trading-hub.task=r3-reproducibility`)
- Kein verwaister Container/Prozess

**Live-Fleet-unangetastet-Nachweis:**
- agent0: 5/5 Services laufen (4× Custom: freqforge/regime-hybrid/rebel/webserver, 1× Stock: canary)
- HermesTrader: Keine Live-Container
- docker ps auf beiden Hosts unverändert

---

## 6. Rollback

R3 war nicht-mutierend. Es wurden keine Live-Mutationen durchgeführt.

**Test-Artefakte:**
- Test-Image r3-test:hermes10000 entfernt
- Test-Container (ephemerer Diagnose-Container) entfernt
- Persistente Volumes unangetastet

**Produktion:**
- Keine Änderung
- Rollback N/A

---

## 7. Aktueller Blocker

`KEIN_BLOCKER`

R3 entscheidet nur. rebel NOT_REPRODUCIBLE ist eine dokumentierte Entscheidung, kein Blocker für R3.

---

## 8. Nächster Schritt

**R4 (Repo-only):**

1. **Compose-Stack mit Dockerfile.hermes10000:**
   - freqforge: Dockerfile.hermes10000
   - canary: Dockerfile.hermes10000
   - regime-hybrid: Dockerfile.hermes10000
   - webserver: Support-Service (separat bewertet)

2. **shared/-Mount + PYTHONPATH:**
   - Mount `freqtrade/shared/` nach `/freqtrade/shared`
   - PYTHONPATH=/ud:/shared

3. **Ggf. freqai-Dockerfile** falls rebel→A (Option A für rebel) angestrebt:
   - `Dockerfile.freqai-hermes10000` (datasieve+xgboost)
   - Rekonstruierter directory_operations.py-Patch
   - FreqAI-Trainings-Pipeline (Retraining der 1,2 GB Modelle)
   - Substantiell, datenabhängig, nicht-deterministisch

4. **Rainbow-Runtime-Service neu** (Teil von R4, nicht R5a — R5a ist das Deployment).

**Kein Deployment.** R4 ist Repo-only.

---

## 9. Belege

- **Repo HEAD:** 8013cfd
- **Image Digest Base:** sha256:87aa5c6d65359b34e9d99a0bb260a38c0efe0315253811e6f48c2afe8f278a6a
- **Strategie-Hashes:**
  - freqforge: a01284cd…057e7
  - canary: 910b40f9…0b80c
  - regime-hybrid: e9791f15…ee587
  - rebel (RebelLiquidation.py): de47905b…265a2
  - rebel (RebelLiquidationWFTop15.py): 9b25b8e4…8337
  - rebel (RebelXGBoostClassifier.py): 13e15c25…81c7
- **#504 Carve-out:** issuecomment-4947132003
- **Test-Image entfernt:** sha256:10ea4619… (Label `trading-hub.task=r3-reproducibility`)

---

## 10. Anhang: Korrektur-Hinweise

### 10.1 `-c5`/`-c25` ≠ Roadmap-C5

Die Suffixe `-c5`/`-c25` sind Build-Versions-Tags OHNE Bezug zum Roadmap-Task C5 (New Canary Measurement Window) — reiner Zufall.

### 10.2 D1/D2-Namenskollision

**SEC-1 D1/D2/D3:**
- Superseded als primärer Zugang
- Root-Runtime-Roadmap (nicht SEC-1): R0 (#506), R0.5 (#507), R1 (#508), R2 (#509)

**Live-Roadmap D1/D2:**
- BLOCKED_BY_C4_KEEP_AND_EXTERNAL_LIVE_APPROVAL
- Unterschiedlich von SEC-1 D1/D2

### 10.3 R5a braucht separates APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT

R5a (Rainbow-Runtime-Service) kann nicht starten, bevor APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT vorliegt ( separat von R4-Entscheidung).

---

**End of Report**
