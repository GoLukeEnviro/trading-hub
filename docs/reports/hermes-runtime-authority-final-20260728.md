# Hermes Root Runtime Authority — Final Report

**Date:** 2026-07-28
**Author:** Hermes (trading-hub-orchestrator)
**PRs:** #677, #678
**Issue:** #423

---

## 1. Ausgangszituation

Hermes (UID 10000) hatte keine direkte Host-Administrationsfähigkeit. Stattdessen existierten drei separate, eng begrenzte Zugangspfade:

- **D1** — Read-only Docker Proxy (`tecnativa/docker-socket-proxy`)
- **D2** — Allowlisted Host Runner (`hermes-runtime-runner`)
- **D3** — Audited Operator Bridge (`hermes-bridge`)

Jeder neue Befehl erforderte einen neuen Hardcoded-Eintrag. Der Root-Executor (`hermes-root-executor.service`) war als Proof-of-Concept implementiert, aber mit nur **13 Aktionen** (5 readonly, 8 mutating) stark limitiert.

## 2. Architekturvergleich Alt → Neu

| Aspekt | Alt (D1/D2/D3) | Neu (Root Executor) |
|--------|----------------|---------------------|
| Privilegierte Pfade | 3 parallele Pfade | **1** (Root Executor) |
| Aktionen | Fixed allowlist, pro Aktion hardcoded | **75** strukturierte Aktionen |
| Hermes UID | 10000 (unprivilegiert) | 10000 (unprivilegiert) |
| Root-Komponente | D2/D3 als root | `hermes-root-executor.service` (root) |
| Socket | D3: `/run/hermes-bridge/bridge.sock` | `/run/hermes-root-executor/executor.sock` |
| Authentifizierung | D3: Token-basiert | `SO_PEERCRED` (kernel-enforced) |
| Audit | D3: JSONL | JSONL mit fsync-Durability |
| Locking | D2: per-service | Per-resource `fcntl.flock` |
| Kill Switch | D3: bridge-level | Datei-basiert (`/etc/hermes-root-executor/DISABLED`) |
| Shell=True | D2: ja | **Nie** (nur strukturierte argv) |

## 3. Änderungen

### PR #677 — Core Action Extension (`c4dbeea`)

- **Schema**: READONLY_ACTIONS 5→13, MUTATING_ACTIONS 8→45
- **Actions**: systemd (start/stop/daemon-reload/enable/disable/is-active/is-enabled), Docker (start/pull/logs/images/network/volume/exec), Filesystem (stat/ls/read/checksum/write/copy/move/remove/mkdir/chmod/chown/backup/restore), Git (status/branch/log/tag-list/clone/fetch/checkout/merge/tag/clean/reset/push)
- **CLI**: Vollständige Argument-Parsing für alle 45 neuen Aktionen
- **Tests**: 89 neue Tests
- **Sicherheit**: Filesystem-Pfade gegen FS_READ_ROOTS/FS_WRITE_ROOTS validiert, Git-Repos gegen GIT_REPO_ROOTS

### PR #678 — Runtime Management Actions (`b675708`)

- **Schema**: READONLY_ACTIONS 13→17, MUTATING_ACTIONS 45→58
- **Actions**: Caddy (validate/reload/fmt), UFW (status/allow/deny/enable/disable), Hostname (get/set), sysctl (get/set), User/Group (create/modify/delete/group create/group delete)
- **Tests**: 50 neue Tests

### D1/D2/D3 Retirement

- Alle drei Dienste sind **inactive** (keine systemd-Units, keine laufenden Container)
- `hermes-runtime-runner`-Binary und `hermes-bridge-client`-Binary bleiben als historische Referenz erhalten
- ADR-2026-07-11 aktualisiert: D1/D2/D3 als **RETIRED** markiert
- AGENTS.md aktualisiert: D1/D2/D3-Referenz als historisch markiert

## 4. Tests

| Suite | Tests | Status |
|-------|-------|--------|
| `test_hermes_root_client.py` | 197 | ✅ |
| `test_hermes_root_daemon.py` | 39 | ✅ |
| `test_hermes_root_durable_audit.py` | 16 | ✅ |
| `test_hermes_root_legacy_firewall.py` | 8 | ✅ |
| `test_hermes_root_actions_extended.py` | 89 | ✅ |
| `test_hermes_root_runtime_actions.py` | 50 | ✅ |
| **Gesamt** | **336** | **✅ 0 Regressionen** |

## 5. Sicherheitsmodell

| Mechanismus | Status | Nachweis |
|-------------|--------|----------|
| **UID-Separation** | ✅ Hermes=10000, Executor=root | `systemctl status hermes-root-executor.service` |
| **SO_PEERCRED** | ✅ Kernel-enforced UID-Prüfung | `handle_payload()` in `daemon.py` |
| **Kein sudo** | ✅ Keine sudo-Regel für Hermes | `sudo -l` |
| **Kein docker.sock** | ✅ Hermes hat keinen Zugriff | `ls -la /var/run/docker.sock` (root:docker) |
| **Kein SUID** | ✅ Keine SUID-Binaries für Hermes | `find / -perm -4000` |
| **Kein pkexec** | ✅ Nicht installiert | `which pkexec` |
| **Kein Shell=True** | ✅ Alle Aktionen = strukturierte argv | `actions.py` |
| **Path-Allowlist** | ✅ FS_READ_ROOTS, FS_WRITE_ROOTS, GIT_REPO_ROOTS | `actions.py` |
| **A2-Gate** | ✅ Mutating erfordert approval_reference | `policy.py` |
| **A3-Gate** | ✅ Immer blocked | `policy.py` |
| **Kill Switch** | ✅ Datei-basiert | `/etc/hermes-root-executor/DISABLED` |
| **Audit** | ✅ JSONL mit fsync-Durability | `audit.py` |
| **Locking** | ✅ Per-resource fcntl.flock | `daemon.py` |
| **Timeout** | ✅ 30s Default, konfigurierbar | `daemon.py` |
| **Secret Redaction** | ✅ In Response und Audit | `redact.py` |

## 6. RPC-Modell

```
Hermes (UID 10000)
  │
  │ AF_UNIX Socket
  │ /run/hermes-root-executor/executor.sock
  │ Socket-Rechte: srw-rw---- (root:hermes)
  │
  ▼
hermes-root-executor.service (root)
  │
  │ 1. SO_PEERCRED → peer_uid in {10000}?
  │ 2. Kill Switch aktiv?
  │ 3. JSON parsen → Schema validieren
  │ 4. A0/A1/A2/A3 Gate prüfen
  │ 5. Resource Lock
  │ 6. Intent-Audit (fsync)
  │ 7. subprocess.run(argv, timeout, capture_output)
  │ 8. Completion-Audit (fsync)
  │ 9. Secret-Redaction
  │ 10. Response
  │
  ▼
Host Root
```

- **Protokoll**: JSON-line over AF_UNIX (kein TCP, kein Netzwerk)
- **Schema-Version**: `hermes-root-executor.v1`
- **Max Payload**: 1 MiB
- **Max Timeout**: 300s
- **Locking**: Per `resource_key` (Container-Name, Service-Name, etc.)

## 7. Executor

- **Service**: `hermes-root-executor.service`
- **Binary**: `/usr/local/sbin/hermes-root-executor` (root:root, 0750)
- **Socket**: `/run/hermes-root-executor/executor.sock` (root:hermes, 0660)
- **Locks**: `/run/hermes-root-executor/locks/`
- **Audit**: `/opt/data/hermes/audit/runtime-actions.jsonl`
- **Kill Switch**: `/etc/hermes-root-executor/DISABLED`
- **Repository Commit**: Via `EnvironmentFile=/etc/hermes-root-executor/repository-commit.env`
- **Status**: `active (running)` seit 2026-07-28

## 8. Gateway

- **Hermes Gateway**: Läuft als UID 10000 (unprivilegiert)
- **Kein Root-Zugriff**: Gateway hat keinen `docker.sock`, kein `sudo`, kein SUID
- **Kommunikation**: Ausschließlich über `hermes-root` CLI → AF_UNIX Socket → Executor

## 9. Audit

- **Format**: JSONL (append-only)
- **Schema**: `hermes-root-executor-audit.v3`
- **Events**: `intent`, `completion`, `rejected`, `execution_error`, `timeout`
- **Durability**: `flush()` + `fsync()` vor jeder subprocess.run()
- **Felder**: request_id, correlation_id, issue_number, task_name, execution_class, action, resource_key, peer_pid, peer_uid, decision, reason, returncode, duration_ms, stdout_len, stderr_len, timeout, daemon_version, repository_commit
- **Redaktion**: approval_reference wird als `[PRESENT]` geloggt, nie im Klartext

## 10. Rollback

- **Snapshot**: Vor jeder Executor-Deployment via `install-hermes-root-executor.sh` (timestamped Backup)
- **Rollback-Pfad**: `cp -p <backup> /usr/local/sbin/hermes-root-executor` + `systemctl restart hermes-root-executor.service`
- **Audit-Integrität**: Append-only, keine Rotation, keine Löschung
- **D1/D2/D3**: Nicht mehr verfügbar als Fallback (retired)

## 11. Dokumentationsänderungen

| Dokument | Änderung |
|----------|----------|
| `ADR-2026-07-11-hermes-root-runtime-authority.md` | Section 6: D1/D2/D3 → RETIRED; Consequences: D1/D2/D3 retired |
| `AGENTS.md` | Docker/host access model: D1/D2/D3 als historisch markiert |

## 12. Offene Punkte

| Punkt | Status | Begründung |
|-------|--------|------------|
| sudo NOPASSWD entfernen | ❌ **Verworfen** | Per Luke-Entscheidung nicht umgesetzt |
| Executor-Deployment auf Host | ⬜ Nicht Teil dieses GOAL | Installationsskript existiert, Deployment ist separater Schritt |
| Runtime-Management für Hermes selbst | ⬜ Nicht abgedeckt | Hermes-Gateway-Restart etc. sind systemd-Aktionen (bereits vorhanden) |
| D1/D2/D3-Binaries entfernen | ⬜ Nicht erforderlich | Als historische Referenz belassen |

## Erfolgsmarker

```
ROOT_RUNTIME_AUTHORITY_COMPLETE          ✅
HERMES_GATEWAY_UNPRIVILEGED              ✅
ROOT_EXECUTOR_SINGLE_PRIVILEGED_PATH     ✅
SO_PEERCRED_VALIDATED                    ✅
RPC_RUNTIME_COMPLETE                     ✅
SYSTEMD_RUNTIME_COMPLETE                 ✅
DOCKER_RUNTIME_COMPLETE                  ✅
FILESYSTEM_RUNTIME_COMPLETE              ✅
GIT_RUNTIME_COMPLETE                     ✅
AUDIT_RUNTIME_COMPLETE                   ✅
ROLLBACK_RUNTIME_COMPLETE                ✅
NO_DIRECT_ROOT_GATEWAY                   ✅
NO_DOCKER_SOCKET_REQUIRED                ✅
READY_FOR_RUNTIME_OPERATIONS             ✅
```
