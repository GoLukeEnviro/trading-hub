# Agent0 Deployment Spec — Soll-Liste der Dienste und Bots

**Stand:** 2026-09-16 · **Basis:** `origin/main` @ `0d83a28a7f4d976e7aeb1216c01dd293d301b9e9`
**Zielhost:** `Agent0` (tailnet `agent0-1`, Hetzner instance-id `125365346`)
**Issue:** #730 (Phase 2)
**Quellen:** `docker-compose.hermestrader-dryrun.yml`, `self_improvement_v2/config/freqtrade_bots.readonly.json`,
ADR-2026-07-11 (R7A OPTION_C), ADR-2026-07-09 (Root-Runtime-Authority)

Diese Datei ist die **Soll-Liste**. Sie beschreibt, was verbindlich vorgesehen ist, damit
später eine Ist-Prüfung dagegen laufen kann. Sie behauptet **keinen** laufenden Betrieb.

## 1. Dienste ≠ Trading-Bots

Die kanonische Compose definiert sechs Services. **Fünf Container bedeuten nicht fünf
Trading-Bots** — Webserver und Rainbow handeln nicht:

| Service | Rolle | Handelt? |
|---|---|---|
| `freqtrade-freqforge` | Trading-Bot (Dry-Run), Strategie `FreqForge_Override` | ja (dry-run) |
| `freqtrade-freqforge-canary` | Canary-Trading-Bot, `FreqForge_Override` | ja (dry-run) |
| `freqtrade-regime-hybrid` | Trading-Bot, `RegimeSwitchingHybrid_v7_v04_Integration` | ja (dry-run) |
| `freqtrade-webserver` | Freqtrade-Webserver (UI/API, kein Bot-Loop) | nein |
| `rainbow` | TA-Collector, `internal-only`, keine veröffentlichten Ports | nein |
| `freqai-rebel` | Trading-Bot, **Profile-gated** (siehe §3) | (inaktiv) |

## 2. Soll-Liste (Deployment)

| Dienst | Image (immutable Tag) | User | Host-Port | mem | cpu | Persistente Daten |
|---|---|---|---|---|---|---|
| `freqtrade-freqforge` | `hermestrader/freqtrade-r5a:r7a-5bcb50fc8186-7ca1e4f9b150` | `10000:10000` | `127.0.0.1:8086→8080` | 512m | 1.0 | `freqforge-db`, `freqforge-logs` |
| `freqtrade-freqforge-canary` | dito | `10000:10000` | `127.0.0.1:8081→8080` | 512m | 0.5 | `canary-db`, `canary-logs` |
| `freqtrade-regime-hybrid` | dito | `10000:10000` | `127.0.0.1:8085→8080` | 512m | 1.0 | `regime-hybrid-db`, `regime-hybrid-logs` |
| `freqtrade-webserver` | dito | `10000:10000` | `127.0.0.1:8180→8080` | 256m | 0.5 | `webserver-db` |
| `rainbow` | `hermestrader/rainbow-r5a:6e850c8f8ba1-faa2e3d8c351` | `10000:10000` | keine (intern) | 512m | 1.0 | `rainbow-storage` |
| `freqai-rebel` | (build, opt-in) | `10000:10000` | `127.0.0.1:8087→8080` | 2g | 2.0 | `rebel-db`, `rebel-logs` |

**Netzwerke:** `trading_internal` (bridge, `internal: true`) + `trading_egress` (bridge, outbound).
Marktdaten brauchen Egress; die Trading-APIs bleiben über Loopback-Port-Mapping host-lokal.

**Sicherheitsinvarianten (aus dem Compose-Vertrag, getestet):** kein `docker.sock`,
keine `0.0.0.0`-Portbindung, `user: 10000:10000`, `cap_drop: ALL`,
`no-new-privileges`, Config-/Strategie-/Shared-Mounts read-only, `dry_run=true` in allen
Configs.

**Startreihenfolge (Empfehlung, abgeleitet aus Abhängigkeiten):**
1. `rainbow` (TA-Quelle, langsamster `start_period` 120s) — liefert externe Signale.
2. `freqtrade-freqforge` als **erster Bot** (Referenz validieren, s. Runbook).
3. `freqtrade-freqforge-canary`, `freqtrade-regime-hybrid` (übrige Trading-Bots).
4. `freqtrade-webserver` (UI/API, konsumiert die Bots).
5. `freqai-rebel` — nur mit `--profile rebel` und separater Freigabe.

**Abnahmeprüfung je Dienst:** `docker compose ps` zeigt `Up (healthy)`, RestartCount 0,
`OOMKilled=false`, Image-ID == Lock-ID, `dry_run=true` wirksam, authentifizierter
API-Zugriff erfolgreich.

## 3. freqai-rebel — ausdrücklich NICHT im Default-Deployment

`freqai-rebel` steht unter `profiles: ["rebel"]` und wird **nicht** mit dem Default-Start
hochgefahren.

| Frage | Antwort |
|---|---|
| Vorgesehen? | Als Service definiert, aber **opt-in** |
| Warum nicht default? | ADR-2026-07-11 (R5A OPTION_C): in R3 als `NOT_REPRODUCIBLE` eingestuft; bis zum Rebel-Epic (PR-3) aus dem Default-Deploy ausgeschlossen. R5B hält Rebel dormant. |
| Konsequenz für Abnahmen | Die deployte Fleet ist **3 Trading-Bots + Webserver + Rainbow**, nicht vier Trading-Bots. Keine 4/4-Trading-Behauptung. |
| In der SI-v2-Registry | Eintrag vorhanden, `enabled: false` + `disabled_reason` — sichtbar statt still entfernt |

Damit ist die Frage „installieren oder deaktiviert" **beantwortet**: deaktiviert, und
zwar korrekt als solcher dargestellt.

## 4. SI-v2-Sicht (Read-Only-Loop)

Die Registry (nach #733) adressiert host-native Loopback-Endpunkte:

| bot_id | base_url | enabled |
|---|---|---|
| `freqtrade-freqforge` | `http://127.0.0.1:8086` | ja |
| `freqtrade-regime-hybrid` | `http://127.0.0.1:8085` | ja |
| `freqtrade-freqforge-canary` | `http://127.0.0.1:8081` | ja |
| `freqai-rebel` | `http://127.0.0.1:8087` | nein |

Der Active Cycle läuft **nativ auf dem Host**, nicht im Compose-Netz — deshalb Loopback
und keine Docker-DNS. Erwarteter `total_bots` bei grünem Betrieb: **3**.

## 5. Kapazität gegen IST

| Ressource | Soll (Default-Fleet) | IST Agent0 | Reserve |
|---|---|---|---|
| RAM | 2.25 GiB (Limits) | 30 GiB total, 28 GiB verfügbar | ~12× |
| CPU | 4.0 Cores (Limits) | 16 Kerne (AMD EPYC-Rome) | 4× |
| Disk | Images ~1,3 GiB + Volumes | 301 GB, 274 GB frei (5 %) | reichlich |
| Architektur | `x86_64` | `x86_64` | passt |

Mit zusätzlich aktivem Rebel: 4.25 GiB / 6.0 Cores — ebenfalls unkritisch.

**Fazit:** die Hardware ist **kein** Blocker. Der Blocker ist die fehlende
Executor-unit-Definition (§ im #730-Kommentar) und die noch ausstehende
HermesTrader-Inventarisierung.

## 6. Was diese Soll-Liste nicht behauptet

Kein Dienst läuft, kein Image ist auf Agent0 vorhanden, kein Bot verarbeitet
Marktdaten. Die Bilder sind lokal gebaute Tags des Quellhosts und werden **nirgends
verteilt**; der Weg dorthin ist `docker save`/`load` mit Digest-Verifikation gegen
`ops/hermes/hermestrader-dryrun-images.lock.json`, ersatzweise der sanktionierte
`r5a_build_canonical_baseline`-Pfad.
