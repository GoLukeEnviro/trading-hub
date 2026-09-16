# SI-v2 Reachability Contract — Registry, Compose und Recovery auflösen

**Execution class:** A1 (repository-only)
**Issue:** #733
**Host:** `Agent0` (tailnet `agent0-1`, Hetzner instance-id `125365346`)
**Base:** `origin/main` @ `0e9ce3c5be57ac19b30b3d58297ebce1522729f7`
**Branch:** `fix/si-v2-registry-reachability-contract-20260916`

## Problem

Drei Verträge widersprachen sich, und keiner von ihnen konnte auf einem
frisch aufgesetzten Host gleichzeitig gelten:

| Quelle | Erwartete Adresse |
|---|---|
| SI-v2-Registry | `http://trading-freqtrade-<role>-1:8080` (Docker-DNS, Port 8080) |
| R5A-Compose | `hermestrader-dryrun-<svc>-1`, Host-Ports 8086/8081/8085/8180 |
| `r5a_recovery.PROJECT` | Name **und** Label-Projekt hart `hermestrader-dryrun` |

Der Registry-Weg ist auf dem Zielhost **strukturell unerreichbar**: der
SI-v2-Active-Cycle läuft dort nativ auf dem Host, nicht in einem Container des
Compose-Netzes. Docker-DNS-Namen lösen dort nicht auf (geprüft: keine
Auflösung, keine `/etc/hosts`-Einträge).

Zusätzlich gefunden — und das war der schwerwiegendere Defekt:

### Der Containment-Default macht die veröffentlichten Ports funktionslos

Alle Bot-Configs setzen `api_server.listen_ip_address = 127.0.0.1`. Das ist als
Containment-Default richtig, aber ein **container-interner** Loopback-Listener
ist über einen veröffentlichten Port nicht erreichbar. Empirisch belegt mit
einem Zwei-Container-Experiment auf genau diesem Host:

| Experiment | Listener im Container | Host-`curl` auf veröffentlichten Port |
|---|---|---|
| A | `127.0.0.1` | **`000` (keine Verbindung)** |
| B | `0.0.0.0` | `200` |

Der Container-eigene Healthcheck läuft gegen `127.0.0.1:8080` **innerhalb** des
Containers und bleibt dabei grün. Ein Bot kann also „healthy" melden, während
sein veröffentlichter Port nach außen nichts bedient — genau der Zustand, in
dem SI-v2 `ping_failed` für alle Bots meldet, ohne dass ein Container
fehlerhaft aussieht.

## Änderung

**1. Registry auf host-native Loopback-Endpunkte** (`self_improvement_v2/config/freqtrade_bots.readonly.json`)

- `base_url` je Bot auf `http://127.0.0.1:<veröffentlichter Port>`,
  übereinstimmend mit dem Loopback-Port-Mapping der kanonischen Compose.
- Felder `compose_service` und `container_port` ergänzt, damit die Bindung an
  die Compose explizit und prüfbar ist statt implizit.
- `reachability_contract` dokumentiert, warum Loopback und nicht Docker-DNS.

**2. `freqai-rebel` explizit deaktiviert, nicht still entfernt**

`enabled: false` plus `disabled_reason`. Gemäß ADR-2026-07-11 (OPTION_C) ist
Rebel `NOT_REPRODUCIBLE` und über `profiles: ["rebel"]` gated; R5B hält Rebel
dormant. Der Eintrag **bleibt sichtbar**, damit der Fleet-Umfang auditierbar
ist: die deployte R5A-Fleet sind **3 Trading-Bots + Webserver + Rainbow**, nicht
vier Trading-Bots. Das ist die im Auftrag verlangte ausdrückliche Klärung —
keine stille Reduzierung und keine erfundene 4/4-Abnahme.

**3. Compose: In-Container-Listen-Adresse übersteuert** (`docker-compose.hermestrader-dryrun.yml`)

`FREQTRADE__API_SERVER__LISTEN_IP_ADDRESS=0.0.0.0` für alle fünf port-veröffentlichenden
Dienste. Freqtrades dokumentierter Env-Mechanismus (`FREQTRADE__{section}__{key}`)
wurde gegen das gepinnte Image verifiziert: `show-config` meldet mit Override
`0.0.0.0`, ohne Override `127.0.0.1`.

Die Sicherheitseigenschaft bleibt erhalten: die **Host**-Bindung ist weiterhin
`127.0.0.1` (Compose-Ports), die API wird nicht über den Host hinaus exponiert.
Der Containment-Test `test_runtime_config_containment.py` fordert
`listen_ip_address == 127.0.0.1` in den Config-Dateien weiterhin ein — die
Config-Dateien wurden **nicht** angetastet, die Übersteuerung liegt in Compose.

**4. Auth-Resolver: Pfade an die reale Deployment-Lage gebunden**

Die Allowlist zeigte auf `/home/hermes/projects/trading/...` — den historischen
agent0-Pfad, der auf dem Zielhost nicht existiert. Auf Agent0 existiert **keine
einzige** der acht hinterlegten Dateien, weshalb die Credential-Auflösung dort
still auf `MISSING` fiel. Die Pfade werden jetzt aus dem kanonischen
Repo-Root abgeleitet (`/workspace/projects/trading-hub`, Fallback: Repo-Root
dieser Datei) und zeigen auf genau die Config, die Compose read-only in den
Container mountet — damit stimmen Host-Leser und Container überein.

## Verifikation

Neuer Contract-Test `tests/test_si_v2_reachability_contract.py` (3 Tests), der
genau den Defekt dauerhaft verhindert:

1. Jeder Dienst mit veröffentlichtem Port **muss** die Listen-Übersteuerung
   setzen — sonst wäre der Port funktionslos.
2. Veröffentlichte Ports binden **nie** `0.0.0.0` (Sicherheit bleibt).
3. Registry-Endpunkte müssen Ports nennen, die die Compose tatsächlich
   veröffentlicht — die Verbindung beider Hälften.

Ergebnisse (isoliertes venv, wie CI installiert):

```text
tests/test_si_v2_reachability_contract.py     3 passed
tests/test_hermestrader_dryrun_compose.py   106 passed, 1 skipped
tests/ (root suite)                        1371 passed, 53 skipped, 1 pre-existing
SI-v2 smoke (self_improvement_v2)          4472 passed, 12 skipped, 2 pre-existing
ruff check self_improvement_v2              All checks passed
ruff check <CI-Pfade>                       All checks passed
docker compose ... config -q                exit 0
```

### TDD-Nachweis

Die 5 Tests, die die stille 4-Bot-Annahme festschrieben, waren nach der
Registry-Änderung **zuerst rot**, bevor die Testmodule angepasst wurden:

```text
FAILED test_multi_bot_proof.py::TestBotRegistry::test_all_bots_enabled
FAILED test_multi_bot_authenticated_telemetry_proof.py::TestBotRegistry::test_all_enabled
FAILED test_freqtrade_auth_resolver.py::TestResolverStructure::test_real_registry_loads_four_bots
FAILED test_freqtrade_auth_resolver.py::TestResolverIntegration::test_resolve_all_returns_per_bot
FAILED test_multi_bot_fleet_analyzer.py::test_registry_has_four_enabled_bots
```

### Vorbestehende, umgebungsabhängige Fehler (nicht aus diesem Diff)

`tests/test_hermes_native_change_c.py::TestStage::test_stage_against_fake_remote_creates_release_without_touching_current`
(reproduziert identisch auf pristine `origin/main`, arbeitet auf einem
`/tmp`-Fake-Remote, nicht Teil dieses Diffs) und
`self_improvement_v2/tests/test_runtime_ceremony_runner.py` (2 Fehler,
`PermissionError: '/opt/data/profiles'` — ebenfalls identisch auf pristine
`origin/main` in einem separaten, gepinnten Worktree nachgewiesen).

## Nicht geändert

Keine Strategie, keine Bot-Config-Datei, kein `dry_run`-Wert, kein Container
gestartet, kein Dienst, kein Cron-Job, kein Secret, kein Kill-Switch-Zustand.
Der Recovery-Vertrag (`r5a_recovery.py`) wurde **nicht** abgeschwächt: ein
`container_name:`-Override hätte `FLEET_SET_MISMATCH` ausgelöst, deshalb wurde
dieser Weg bewusst **nicht** gewählt. Kein Lock wurde zum Bestehen einer
Prüfung umgestellt.
