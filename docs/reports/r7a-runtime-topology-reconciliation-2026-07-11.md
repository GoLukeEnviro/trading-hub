# R7A Runtime Topology Reconciliation Report

**Datum:** 2026-07-11  
**Branch:** feat/r7a-hermestrader-dryrun-topology  
**Issue:** #504 (R7A), #496 (R7-Messung)  
**Autor:** CodeLuke

> **Hinweis:** VPS-spezifische Laufzeitdaten (Ports, Container-IDs, Secrets) werden nur referenziert, nicht committed. VPS-Report: `/opt/data/hermes/reports/r7a-host-deploy-2026-07-11.md` (nach Deploy).

---

## 1. Befund: Drei widersprüchliche Compose-Dateien

| Datei | Bots | Image-Strategie | Rainbow | Status |
|---|---|---|---|---|
| `docker-compose.yml` | 4 Bots + webserver | `freqtradeorg/freqtrade:stable` | Nein | Legacy / deprecated |
| `freqtrade/docker-compose.fleet.yml` | rsi/momentum (veraltet) | unbekannt | Nein | Fleet-Alt / deprecated |
| `freqtrade/bots/freqai-rebel/docker-compose.yml` | rebel only | unbekannt | Nein | Rebel-Standalone / deprecated |
| `docker-compose.hermestrader-dryrun.yml` | freqforge + canary + regime-hybrid + rebel (opt-in) | `Dockerfile.hermes10000` | Ja (internal) | **Kanonisch (R7A)** |

**Entscheidung:** Legacy-Dateien bleiben als Rollback-Sicherheit erhalten. Kein Löschen.

---

## 2. Test-Drift (bekanntes Delta)

`tests/test_docker_compose_contracts.py` referenziert `freqtrade-rsi` und `freqtrade-momentum` — diese Services existieren im aktuellen Fleet nicht mehr.

**Status:** Bekanntes Delta, wird in PR-2 adressiert:
- Legacy-Tests in `tests/test_legacy_fleet_compose.py` verschieben (oder mit `@pytest.mark.skip` deprecaten)
- Neue Contract-Tests in `tests/test_hermestrader_dryrun_compose.py`

---

## 3. Rainbow Standalone vs. Integriert

| Aspekt | Standalone (ai4trade-bot) | Integriert (R7A) |
|---|---|---|
| Port | `:18080` (extern erreichbar) | kein `ports:` (internal-only) |
| Healthcheck | HTTP `/health` ✓ | HTTP `/health` (übernommen) |
| Config | `docs/r4/rainbow.internal.yml` | `config/rainbow.internal.yml` (vendored) |
| Delivery Worker | off | off (explizit) |
| evaluation | unbekannt | `evaluation.enabled: false` |

**Kritischer Fix:** Heartbeat-Pfad `/app/storage/heartbeat_rainbow.json` ist unzuverlässig (DB liegt unter `/app/rainbow/storage/`). Healthcheck in `rainbow.include.yml` auf HTTP `/health` umgestellt.

---

## 4. ai4trade-bot Pin-Situation

| Commit | Quelle | Status |
|---|---|---|
| `b65510a` | PR #76 (Dashboard + TA-Fix) | **Aktueller Pin (validiert 2026-07-11)** |
| `a1e3f05` | Original-Anleitung | Veraltet — nicht verwenden |

**Aktion bei Deploy:** Pin auf aktuellen HEAD von ai4trade-bot prüfen und ggf. in `rainbow.include.yml` aktualisieren.

---

## 5. Rebel Status (NOT_REPRODUCIBLE)

R3-Befund: `freqai-rebel` ist NOT_REPRODUCIBLE wegen:
- `directory_operations.py`-Patch nicht versioniert
- FreqAI-Deps nicht in `Dockerfile.hermes10000`
- Model-Artefakte (1.2 GB) nicht committet

**R7A-Entscheidung:** `profiles: ["rebel"]` — opt-in, default aus. Freigabe erst nach PR-3 (Rebel Epic) und Reproducibility-Nachweis.

---

## 6. Canary-Config Delta

`freqforge-canary/config/` enthält `.bak`-Dateien. Vor erstem `docker compose up` muss eine aktive Dry-run-Config vorhanden sein.

**Aktion:** Vor Deploy prüfen welche Config aktiv ist (`config_freqforge_canary_dryrun.json` oder restaurierter `.bak`). Nicht blockierend für PR-Merge.

---

## 7. Netzwerk-Migration

| Alt | Neu |
|---|---|
| `hermes-net` (external) | `trading_internal` (bridge, intern) |

Rainbow ist ausschließlich über `trading_internal` erreichbar. Kein externer Port.

---

## 8. R7-Messplan (#496)

Nach Deploy (nach Freigabe):
- ≥14 Tage shadow/dry-run mit OPTION_C + Rainbow TA-Baseline
- `SI_V2_RAINBOW_MODE=read_only` durchgehend
- Mutation-Counter = 0 als Nachweis
- Live-Trading bleibt #423-gated
