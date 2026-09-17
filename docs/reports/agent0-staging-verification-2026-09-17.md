# Agent0 — unabhängige Verifikation des Transfers und R5A-`docker load`

**Datum:** 2026-09-17 · **Host:** Agent0 (`100.103.203.107`, Hetzner 125365346)
**Issue:** #730 · **Klasse:** A0 (read-only) plus der beauftragte Schritt 1 (`docker load`, ohne Dienststart)
**Bezug:** #730-Kommentar 5710230349 (`TRANSFER_VERIFIED`)

## 1. Ergebnis

Der gemeldete Transfer ist auf Agent0 unabhängig nachgemessen und **bestätigt**.
Der im Auftrag genannte nächste Schritt (`docker load` + Image-ID-Abgleich) wurde
ausgeführt; beide Runtime-IDs sind **exakt** identisch mit `inventory/` und dem
Image-Lock:

| Image | Runtime-ID nach Load | Lock / Inventory |
|---|---|---|
| `hermestrader/freqtrade-r5a:r7a-5bcb50fc8186-7ca1e4f9b150` | `sha256:aa4ab78532d996b0d3ac7b034819918e2085495dd1368399705b208d331bd380` | identisch ✓ |
| `hermestrader/rainbow-r5a:6e850c8f8ba1-faa2e3d8c351` | `sha256:7e2fab4a87790a1aadebed29b2688ec4c45a80ed9763e69f0d3d285093cc5db0` | identisch ✓ |

Kein Container gestartet, kein Volume angelegt, kein Compose-Projekt erzeugt.
Endzustand: 0 Container, 0 Volumes, 0 Compose-Projekte — nur die zwei Images im
lokalen Store.

## 2. Nachgemessene Prüfungen

| Prüfung | Ergebnis |
|---|---|
| `MANIFEST.sha256` gegen `/srv/tradinghub-staging-20260917` | **111/111 PASS** (`sha256sum -c --quiet`, als `hermes`) |
| Manifest-Abdeckung | 124 Dateien auf Platte = 111 Manifest-Einträge + 11 `-shm`/`-wal` + `MANIFEST.sha256`; keine Manifest-Zeile ohne Datei |
| SQLite `integrity_check` (read-only geöffnet) | 6/6 `ok` (freqforge, canary, regime-hybrid, rainbow-canonical, rainbow-signals, verification_evidence) |
| Gate-0 Selection | 9/9 Datei-Hashes == Freeze-Manifest; Manifest-Self-Hash `bdd1bd96…` == Datei |
| Gate-0 Holdout | im Freeze-Manifest referenziert, im Paket **nicht vorhanden** (nur Provenienz) |
| Image-Archiv | 40 Members, 0 absolute/`../`-Pfade, beide Immutable-Tags im Manifest, Tar-SHA256 `a0a1f4c2…` == Sidecar-Wert |
| `docker load` | 20 s; beide IDs exakt wie erwartet (Abschnitt 1) |
| Repo-Artefakte vs `origin/main` | Image-Lock, Rainbow-Lock, `Caddyfile`, `config/rainbow.internal.yml` **byte-identisch**; `docker-compose.hermestrader-dryrun.yml` **abweichend** (3.1) |
| Bot-Configs | 4/4 byte-identisch mit den getrackten Dateien; `dry_run: true`; API-Werte = Platzhalter (3.2) |
| Strategien + `shared` | 58/58 Dateien byte-identisch mit dem Agent0-Checkout |
| Dry-Run-DB-Inhalte | freqforge 74 Trades (letzter 2026-09-17 01:28), canary 141 (02:00), regime-hybrid 81 (2026-09-16 18:42); rainbow-canonical/-signals je 204.585 Zeilen |
| Kill switch (Paket) | `NORMAL` |
| Host | Docker 29.8.0 (containerd-Snapshotter), `hermes` in `sudo`+`docker`, Disk 18/301 GB belegt |

## 3. Befunde vor den nächsten Schritten

### 3.1 Die gestagte Compose ist die Revision **vor** dem #734-Fix

Die Compose im Paket entspricht dem Host-Stand `ddd96fa`. `origin/main` (`236620c`)
enthält seit #734 fünf zusätzliche Zeilen
`FREQTRADE__API_SERVER__LISTEN_IP_ADDRESS=0.0.0.0` (je Service). Ohne sie ist der
Loopback-Port eines Bots von außen nicht erreichbar — genau der Zustand, den #734
strukturell erklärt hat (`ping_failed` bei „gesunden" Containern).
→ Für das Compose-Projekt die Datei aus dem aktualisierten Checkout verwenden,
nicht die Paketkopie. (Read-only geparst: 5 Services, 8 Volumes, keine Fehler.)

### 3.2 Secrets: das Paket enthält **keine** Live-Secrets, aber eine Mount-Entscheidung

Die vier `config.example.json` (auch im Paket) enthalten `CHANGE_ME*`-Platzhalter —
keine echten Zugangsdaten. Der Schritt „interne API-Secrets für Agent0 neu
erzeugen" bleibt trotzdem sinnvoll. Entscheidungspunkt:

Der `freqtrade_auth_resolver.py` (Stand `origin/main`) liest zuerst
`user_data/config.json` (untracked, per `.gitignore` ausgeschlossen), dann
`config.example.json`. Das Compose mountet derzeit `config.example.json`.
Damit neue Secrets wirksam werden, ist **eine** der beiden Varianten nötig:

1. untracked `user_data/config.json` je Bot + Compose-Mount-Umstellung (eine
   kleine A1-Änderung), oder
2. Änderung der getrackten `config.example.json` (erzeugt einen dirty Worktree
   im gemeinsamen Checkout bzw. würde Secrets committen).

Variante 1 ist die saubere: sie hält den Checkout clean und trifft die bereits
implementierte Resolver-Reihenfolge.

### 3.3 Checkout und Registry 3 Commits hinter `origin/main`

Der Agent0-Checkout steht clean auf `ddd96fa`. Die SI-v2-Registry im Checkout
adressiert noch Docker-DNS (`http://trading-freqtrade-…-1:8080`); `origin/main`
adressiert Loopback-Ports (`127.0.0.1:8086` etc.). Vor dem SI-v2-Lauf muss der
Checkout auf `origin/main` (A2-Schritt), sonst läuft der Loop gegen den alten
Erreichbarkeitsvertrag. `hermes_root/r5a_recovery.py` (`PROJECT = "hermestrader-dryrun"`)
ist unverändert vorhanden.

### 3.4 Host-Voraussetzungen für den SI-v2-Lauf fehlen noch

`/opt/data/scripts/` (Wrapper), `/opt/data/logs/si-v2-active-cycle/`,
`/opt/data/secrets/si-v2-freqtrade.env` und `self_improvement_v2/.venv` fehlen;
`hermes-root-executor.service` ist nicht installiert (kein Unit, keine
Socket-Spuren); `hermes cron` hat 0 Jobs (Gateway läuft, Cron würde feuern).

### 3.5 Doppelbetrieb

Die HermesTrader-Fleet läuft unverändert weiter (Quellhost unangetastet). Vor dem
Agent0-Start sind die Rollen zu trennen (Runbook §9), sonst divergieren die
Dry-Run-DBs und die Messzuordnung ist nicht mehr eindeutig.

### 3.6 Zugangswege

`ssh neu` existiert nur auf der Windows-Seite; auf Agent0 ist der Alias nicht
aufgelöst. Von Agent0 direkt: `deploy@100.96.132.39` ⇒
`Permission denied (publickey,password)` — der direkte Server-zu-Server-Weg fehlt
weiterhin (konsistent mit dem Transferbericht). sshd-Journal: ein preauth-Abbruch
von `100.96.132.39` (HermesTrader) um 08:30; ab 07:50 erfolgreiche Logins mit dem
Key `SHA256:0b/40vl…`.

### 3.7 Hermes-Zustand im Paket

`siv2/state-snapshots.tar.gz` enthält eine Gateway-Zustands-Sicherung vom
2026-07-12 (`state.db` ≈ 46 MB, `auth.json`, `.env`, `config.yaml`, `kanban.db`,
`projects.db`, Pairing-Daten). Der Transferbericht listet „Hermes-Agent-State
(`state.db`, `profiles`)" unter „bewusst nicht enthalten" — diese Sicherung ist
jedoch Teil des Pakets. Entweder bewusst als Bestandteil deklarieren oder aus dem
Paket entfernen; bis dahin gilt sie als sensibel (Rechte wurden eingeschränkt,
Abschnitt 4).

## 4. Durchgeführte Änderungen an Agent0

- `docker load` des beauftragten Archivs (Abschnitt 1) — ohne Dienststart.
- Read-only One-Shot-Inspektionen der Images (Dateiinhalte/Pfade; keine Ports,
  keine Volumes, kein Netz).
- `chmod`: `siv2/state-snapshots.tar.gz` und `siv2/sessions.tar.gz` waren
  world-readable (`0644 root:root`) und wurden auf `0640 root:hermes` gesetzt.
  Danach ist auch die Manifest-Verifikation als `hermes` vollständig grün.

## 5. Nächste Schritte (jeweils eigenes Gate)

| # | Schritt | Gate |
|---|---|---|
| 1 | `docker load` + ID-Abgleich | **erledigt** |
| 2 | Checkout auf `origin/main`; Compose aus dem Checkout mit `-p hermestrader-dryrun` übernehmen | A2 |
| 3 | DB-Snapshots in die neuen Volumes (`freqforge-db` usw.) | A2 |
| 4 | Secrets erzeugen + Mount-Variante entscheiden (3.2) | A1/A2 |
| 5 | Host-Namespace (`scripts`/`logs`/`secrets`), SI-v2-venv, Executor | L3 |
| 6 | Rollen-Trennung Quelle/Ziel (3.5) | A2 |
| 7 | Bot-Start in der Reihenfolge der Soll-Liste; Abnahme: `Up (healthy)`, IDs == Lock, `dry_run=true`, SI-v2 `total_bots=3` | separate Freigabe |
| 8 | Genau ein Scheduler-Job + Nachweis eines echten automatischen Laufs | A2 |

## 6. Rollback / Zustand

Rückweg für den Load: `docker rmi` der beiden Tags (lokal, jederzeit möglich); die
Archive sind unangetastet. Keine Repo-Mutation aus dieser Sitzung. Der
Writer-Lock auf Agent0 ist frei (flock kernel-released nach PID-Ende).
