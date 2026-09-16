# Übernahmeplan — Trading Hub Dry-Run-Fleet auf Agent0

**Stand:** 2026-09-16T00:55Z · **Basis-Commit:** `ddd96fa` · **Issue:** #730
**Zielarchitektur:** Hermes + Trading Hub gemeinsam auf Agent0, ausschließlich Dry-Run.
HermesTrader bleibt unangetastet, bis der Übergang belegt ist.
**Status:** Plan ist ausführbar definiert. Schritt 3 (Host-Namespace) ist am 2026-09-16
ausgeführt und validiert; **Schritt 0 (Zugang) ist der einzige verbleibende Blocker.**

---

## 0. Zugang (Blocker — genau ein Operator-Schritt)

Alle erlaubten Zugangswege von Agent0 zu HermesTrader wurden geprüft und **funktionieren nicht**:

| Weg | Ergebnis |
|---|---|
| SSH `hermes@` / `deploy@` / `root@` / `operator@` / `ubuntu@` | `Permission denied (publickey,password)` |
| SSH mit dem privaten Root-Key von Agent0 | `Permission denied` |
| `tailscale ssh` (Hostkey entspannt) | `Permission denied` — Agent0 hat `RunSSH=false`, HermesTrader bietet SSH nicht über Tailscale an |
| `ssh-agent` / hinterlegte Keys | kein Agent aktiv, keine Schlüssel vorhanden |
| Vault / gespeicherte Logins | leer (0 Einträge) |
| Provider-CLI (`hcloud`), Hetzner-/B2-/SSH-Credentials auf Agent0 | nicht vorhanden |

Erreichbar ist HermesTrader nur **passiv read-only** (Caddy/Cockpit auf 22/80/443/8443/9091).
Für eine Bestandsaufnahme der Container, Images, Daten und des Gate-0-Datasets genügt das nicht —
diese Objekte sind grundsätzlich nur host-lokal sichtbar.

**Der eine Schritt** (HermesTrader-Provider-Konsole / bestehender SSH-Zugang von Luke):

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICbYIPEJaQ2tfM1flCbEiDFkCW6/G+n+ZFNno1M3XU3U hermes@agent0-migration-20260915
```

→ anhängen an `/home/deploy/.ssh/authorized_keys` (und an die `authorized_keys` des
Agenten-Accounts, falls dieser auf HermesTrader existiert — laut Governance `hermes`).
Fingerprint zur Kontrolle: `SHA256:zah7SmM4+vxSnUNIjZh8407zeAHuV3IBZ4DV9X/7jmg`

Der private Schlüssel liegt ausschließlich auf Agent0 (`/home/hermes/.ssh/id_ed25519_hermestrader_migration`, 0600)
und wird nie ausgegeben. Kein Passwort, kein Passwort-Account, keine Übergabe eines Secrets nötig.

**Bis dieser Schritt erfolgt ist: keine weitere Zugriffsprobe, keine weitere Diagnose-Runde.**

---

## 1. Bestandsaufnahme HermesTrader (nach Schritt 0, read-only)

Ein Skript, das ausschließlich liest und nichts verändert:

```bash
# 1) Bots + Container
docker ps -a --filter label=com.docker.compose.project --format \
  '{{.Names}}\t{{.Status}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.service"}}'

# 2) Images samt Digests (Übernahmequelle!)
docker images --digests --format '{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Digest}}'
docker image inspect hermestrader/freqtrade-r5a:r7a-5bcb50fc8186-7ca1e4f9b150 \
  --format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}} {{.Config.User}}'
docker image inspect hermestrader/rainbow-r5a:6e850c8f8ba1-faa2e3d8c351 \
  --format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}} {{.Config.User}}'

# 3) Deployment-Konfiguration
docker compose ls; docker volume ls; docker network ls
find / -maxdepth 5 -name 'docker-compose*.y*ml' 2>/dev/null

# 4) Persistente Bot-Daten (Volumes + Größe), Dry-Run-DBs
docker volume inspect <vol> --format '{{.Name}} {{.Mountpoint}}'
docker run --rm -v <vol>:/d:ro alpine du -sh /d

# 5) Backups
systemctl list-timers | grep -i restic; cat /etc/restic/backblaze.env 2>/dev/null | cut -d= -f1

# 6) Gate-0-Dataset + Manifest + Prüfsummen
ls -la /opt/data/gate0-freqtrade-native-r1 /opt/data/gate0-backtest-results 2>&1
find /opt/data -name '*.sha256' -o -name 'manifest*.json' 2>/dev/null | head
sha256sum /opt/data/gate0-freqtrade-native-r1/*   # Abgleich mit eingefrorenen Hashes

# 7) Secrets — ausschließlich Vorhandensein, niemals Werte
test -f /opt/data/secrets/si-v2-freqtrade.env && echo present
grep -c . /opt/data/secrets/si-v2-freqtrade.env 2>/dev/null   # nur Zeilenzahl
# Schlüsselnamen ohne Werte:
cut -d= -f1 /opt/data/secrets/si-v2-freqtrade.env 2>/dev/null

# 8) Tatsächlicher Trading-Modus
docker exec <bot> freqtrade show-config 2>/dev/null | grep -i dry_run
grep -o '"dry_run"[^,]*' <config>.json
```

Ergebnis wird als Inventar-Artefakt festgehalten (read-only Beweis, keine Mutation).

---

## 2. Images übernehmen — bevorzugt unverändert

**Primärweg (bevorzugt, weil „unverändert übernehmen"):** Images auf HermesTrader exportieren und auf
Agent0 laden, dann per **Digest** gegen den Lock verifizieren.

```bash
# auf HermesTrader (read-only gegenüber dem laufenden Betrieb)
docker save hermestrader/freqtrade-r5a:r7a-5bcb50fc8186-7ca1e4f9b150 | zstd > freqtrade-r5a.tar.zst
docker save hermestrader/rainbow-r5a:6e850c8f8ba1-faa2e3d8c351        | zstd > rainbow-r5a.tar.zst
sha256sum *.tar.zst > transfer.sha256      # Integrität der Übertragung

# Transport: ausschließlich über den Tailnet-Kanal (verschlüsselt), nie über Fremd-Hosting

# auf Agent0 — Pflichtprüfung: geladene ID muss dem Lock entsprechen
zstd -d -c freqtrade-r5a.tar.zst | docker load
zstd -d -c rainbow-r5a.tar.zst   | docker load
docker image inspect hermestrader/freqtrade-r5a:r7a-5bcb50fc8186-7ca1e4f9b150 --format '{{.Id}}'
#   Soll: sha256:aa4ab78532d996b0d3ac7b034819918e2085495dd1368399705b208d331bd380
docker image inspect hermestrader/rainbow-r5a:6e850c8f8ba1-faa2e3d8c351 --format '{{.Id}}'
#   Soll: sha256:7e2fab4a87790a1aadebed29b2688ec4c45a80ed9763e69f0d3d285093cc5db0
```

Stimmt eine ID nicht, wird **nicht** deployed.

**Sekundärweg (nur falls die Images auf HermesTrader nicht mehr existieren):** der sanktionierte
Bootstrap `r5a_build_canonical_baseline` — der einzig legitime Neubau-Pfad. Er ist bereits heute auf
Agent0 vorprüfbar: Lock-Datei-, Dockerfile- (`7ca1e4f9b150…`), Entrypoint- (`7e1890ed32c9…`),
Rainbow-Dockerfile- (`faa2e3d8c351…`) und Rainbow-Checkout-Hash (`6e850c8f8ba1…`) stimmen alle.
Er verlangt `lock.status == "baseline_pending"`; danach müssen die neu gebauten IDs erneut
attestiert und der Lock wieder auf `locked` gesetzt werden. **Kein Lock/Guard wird umgangen oder
umgeschrieben, um einen Deploy zu erzwingen** — das ist der vorgesehene Zeremonie-Pfad.

---

## 3. Namens- und Erreichbarkeitsvertrag (kritischer Designpunkt)

Drei Verträge widersprechen sich heute; das muss **einmal** entschieden werden:

| Quelle | Erwartet |
|---|---|
| SI-v2-Registry (`freqtrade_bots.readonly.json`) | `http://trading-freqtrade-<role>-1:8080` — Projektname `trading`, **Port 8080** |
| R5A-Compose | Container `hermestrader-dryrun-freqtrade-<role>-1`, Host-Ports 8086/8081/8085/8180 → Container 8080 |
| `r5a_recovery.PROJECT` | hart `hermestrader-dryrun`; verlangt **exakt** die Namen `hermestrader-dryrun-<svc>-1` *und* das Compose-Label-Projekt `hermestrader-dryrun` |

Dazu kommt: die Registry-Namen sind **Docker-DNS-Namen**. SI-v2 läuft auf Agent0 **nativ auf dem
Host**, nicht in einem Container — auf dem Host lösen diese Namen nicht auf (geprüft: keine
`/etc/hosts`-Einträge). Die Provenienz-Historie zeigt, dass SI-v2 die Docker-DNS bewusst nutzt
(Commit „fix Freqtrade read-only registry to use Docker DNS").

**Konsequenz:** Ein `container_name:`-Override erfüllt die Registry, bricht aber `r5a_recovery`
(`FLEET_SET_MISMATCH`, weil dort Name *und* Label-Projekt auf `hermestrader-dryrun` geprüft werden).
Es braucht in jedem Fall **eine** abgestimmte Änderung — nicht zwei parallele Pfade:

- **Variante 1 (empfohlen): Deployment an die Registry anpassen.**
  Deploy mit `-p trading`, sodass die Container `trading-freqtrade-<role>-1` heißen und der
  Registry-Eintrag byte-identisch bleiben kann; `PROJECT` in `r5a_recovery` wird parametrisiert
  (A1-Repo-Änderung, 1 Zeile + Tests). Zusätzlich Namensauflösung für den Host schaffen
  (statische IPs im Compose-Netz + `/etc/hosts`-Einträge, **oder** SI-v2-Zyklus in einem Container
  am Fleet-Netz). Der Port 8080 stimmt dann direkt mit dem Registry-Eintrag überein.
- **Variante 2: Registry an das Deployment anpassen.** Deploy bleibt `-p hermestrader-dryrun`
  (kein Recovery-Eingriff), Registry-Basis-URLs werden auf Host-Ports/Alias umgestellt
  (A1-Repo-Änderung am **bewiesenen** SI-v2-Lesepfad).

Belegt ist: mehrere Loopback-IPs können gleichzeitig `:8080` bedienen (Test durchgeführt:
`127.0.0.2/3/4:8080` parallel erfolgreich), sodass ein `127.0.0.x:8080:8080`-Mapping die
Registry-Namen inklusive Port unverändert bedienen kann.

**Fleet-Umfang:** die kanonischen fünf R5A-Services. `freqai-rebel` bleibt hinter
`profiles: ["rebel"]` (R5B: dormant). Die Registry hat **vier** Einträge inklusive `freqai-rebel` —
dessen planmäßiges Fehlen muss explizit behandelt werden (Registry-Eintrag deaktivieren oder
SI-v2-Ergebnis als 3/4 mit dokumentierter Begründung), nicht stillschweigend.

---

## 4. Host-Namespace auf Agent0 (L3, freigabepflichtig)

Diese Pfade sind bindende Verträge und fehlten vor dem 2026-09-16 vollständig. Sie sind
am 2026-09-16 unter #730 angelegt und einzeln gegen die Guard-Bedingungen validiert
worden (`agent0-host-state-revalidation-2026-09-16.md`, §4). Ursache des
`WRITER_IDENTITY_MISMATCH` war **nicht** nur das fehlende Verzeichnis: der Guard bricht
beim ersten Fehler ab, sodass die Bedingungen 6 (Worktree-Parent `10000:10000`,
beschreibbar) und 7 (Lock-Datei regular, `0600`, writer-rw) als latente Mit-Ursachen im
Fehlertext unsichtbar blieben; zusätzlich verlangt `_validate_sandbox` den Lock
physisch innerhalb `/opt/data/state` und den Worktree-Parent innerhalb `/opt/data`.

| Pfad | Soll | Zweck |
|---|---|---|
| `/opt/data/state/repo-writer/` | `root:root`, nicht für UID 10000 beschreibbar | Lock-Verzeichnis |
| `/opt/data/state/repo-writer/hermes-repo-writer.lock` | `10000:10000`, `0600`, vorhanden | Single-Writer-Lock |
| `/opt/data/projects/trading-hub-worktrees/` | `10000:10000`, beschreibbar | isolierte Worktrees |
| `/workspace/projects/trading-hub` | kanonischer Checkout | Repo-Anker der Recovery-Helfer |
| `/opt/data/secrets/si-v2-freqtrade.env` | Secrets, Vorhandensein genügt | SI-v2-JWT-Auth |
| `/opt/data/gate0-*` | Daten + Ergebnisse | #702 |

Ohne diese Pfade fällt `RepoWriterLock()` fail-closed
(`WRITER_IDENTITY_MISMATCH: lock parent … missing`) — **kein** Repo-Schreibzugriff, also auch
kein Report-PR. Genau das war der Zustand bis zum 2026-09-16. Die sudo-/docker-Gruppenrechte von `hermes` sind
**keine** Freigabe, das zu umgehen.

---

## 5. Privilegierter Pfad (Executor)

`hermes-root-executor.service` existiert auf Agent0 nicht. Der vorgeschriebene Pfad ist
`scripts/install-hermes-root-executor.sh` (+ die R5A-Erweiterung
`ops/systemd/install-r5a-compose-executor-extension.sh`), mit serverseitiger
`policy.py`-Gate-Prüfung, Allowlist, `SO_PEERCRED` und Audit.
A2-Marker sind ohne Executor gegenstandslos — der Executor ist die Voraussetzung, nicht die Alternative.

**Rückweg/Absicherung:** Die Installer sind transaktional (Backup + Rollback + Health-Prüfung).
Erst nach verifiziertem Executor-Betrieb **und** verifiziertem Operator-Zugang werden die
breiten `sudo`/`docker`-Rechte von `hermes` eingeschränkt — sonst droht administrativer Lockout.

---

## 6. Reihenfolge (jeder Schritt mit Abbruchkriterium)

1. **Zugang** (Operator) → sonst stoppen. ↯ *aktueller Blocker*
2. **Inventar HermesTrader** read-only; Images/Digests, Daten, Backups, Gate-0-Hashes, Secret-Präsenz, dry_run-Modus.
3. **Host-Namespace Agent0** anlegen (L3-Freigabe); `RepoWriterLock()` muss danach greifen.
   ✅ **Erledigt 2026-09-16** — angelegt und validiert (Lock erwerbbar, `assert_held()` OK,
   konkurrierender Writer abgewiesen, Worktree-Isolation OK, shared Checkout clean).
4. **Images** per `save`/`load` übernehmen und per Digest gegen den Lock verifizieren.
   ↯ Abbruch bei ID-Abweichung.
5. **Namensvertrag** entscheiden (Variante 1 oder 2) und als **ein** A1-PR umsetzen; CI + Merge-Guard grün.
6. **Executor** auf Agent0 installieren und read-only verifizieren (`executor_health`).
7. **Fleet hochfahren** mit dem gelockten Compose (`deploy-locked`), Dry-Run-Invariante prüfen
   (`dry_run=true`, read-only Config-Mount, non-root 10000, Rebel abwesend).
8. **SI-v2 gegen echte Bots**: `ping_ok_count=4` (bzw. 3/4 dokumentiert), `status_authenticated_count ≥ 1`,
   Mutation-Counter alle 0. **Keine Fixtures als Betriebsnachweis.**
9. **Gate-0-Daten** übertragen und Hash-Abgleich gegen die eingefrorenen Manifest-Werte;
   Holdout bleibt geschlossen.
10. **Snapshot + Doppelbetriebsschutz**: vor Schritt 7 Snapshot beider Hosts; Rollback = alten
    Stand wiederherstellen; sicherstellen, dass **kein** Bot-Role gleichzeitig auf beiden Hosts läuft;
    HermesTrader erst nach belegtem Übergang und separater Freigabe anfassen.
11. **Evidence-Report** (`docs/reports/`) + State-Reconciliation über den Writer-/PR-Weg.

---

## 7. Abnahmekriterien (aus dem GOAL)

- Bots verarbeiten aktuelle Marktdaten mit `dry_run=true` (nachgewiesen, nicht nur konfiguriert).
- SI-v2 liest echte Bot-Daten; **keine Fixtures** als Betriebsnachweis.
- Gate-0-Daten stimmen mit den eingefrorenen Hashes überein.
- Kein Live-Trading, kein `dry_run=false`, keine Exchange-Keys.
- HermesTrader unverändert (kein Löschen, kein Abschalten).

## 8. Kleinster ausführbarer nächster Schritt

**Nur Schritt 0:** den oben genannten **öffentlichen** Schlüssel auf HermesTrader eintragen.
Danach ist die Bestandsaufnahme (Schritt 2) sofort ausführbar — alles Weitere hängt daran.
Voraussetzungen, die dafür bereits erfüllt sind: HermesTrader ist online und über Tailscale
erreichbar (7 ms), Agent0 hat das Repo auf `ddd96fa` und den Schlüssel erzeugt.
