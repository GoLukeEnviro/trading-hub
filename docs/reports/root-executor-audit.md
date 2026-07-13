# Root-Executor Audit Report

> Session: hermes-skill-debug-2026-07-13 | Step 1/6 | Scope L0+A1
> Date: 2026-07-13

## Issue: Status-Verification des hermes-root-executor.service

Der ursprüngliche Befund, executor.sock sei ein undokumentiertes Mysterium, war STALE.
Dieser Report verifiziert den aktuellen Ist-Zustand: Startup-Unit, Permissions, Socket-Pfad,
Deployment-Status (Repo-Daemon vs. Host-Script).

## Evidence

### 1. systemd Service-Status (read-only)

`
hermes-root-executor.service - Hermes Root Runtime Executor (Phase R1)
  Active: active (running) since Mon 2026-07-13 13:35:50 UTC
  Main PID: 608481 (python3)
  Tasks: 1 (limit: 16854)
  Memory: 9.3M (peak: 48.7M)
  CPU: 1.067s
  NRestarts: 0
`

Drop-Ins:
- 10-hermes-group-permissions.conf: Group=hermes, RuntimeDirectoryMode=0750, RuntimeDirectoryPreserve=restart
- 20-repository-commit.conf: EnvironmentFile=/etc/hermes-root-executor/repository-commit.env

### 2. Socket Permissions

`
/run/hermes-root-executor/          drwxr-x--- root:hermes 0750
/run/hermes-root-executor/executor.sock  srw-rw---- root:hermes 0660
/run/hermes-root-executor/locks/     drwxr-xr-x root:hermes
`

Kill-Switch: /etc/hermes-root-executor/DISABLED absent → NORMAL.

### 3. Host-Daemon Binary

`
/usr/local/sbin/hermes-root-executor  16424 bytes  -rwxr-x--- root:root  Jul 13 11:20
`

### 4. Repository-Daemon (Source of Truth)

Der Daemon ist vollständig im Repository versioniert:
- hermes_root/daemon.py — AF_UNIX Server, Dual-Protocol (legacy + hermes-root-executor.v1)
- hermes_root/schema.py — Client-seitiges Schema, DEFAULT_SOCKET_PATH
- hermes_root/protocol.py — Protocol-Normalisierung, fail-closed
- hermes_root/client.py — AF_UNIX Client
- hermes_root/actions.py — Action-Registry für hermes-root-executor.v1
- hermes_root/audit.py — Audit-Logging

### 5. Dokumentation

- commands/hermes-root-runtime.md — Client, Protokoll, A0–A3-Klassen
- ADR-2026-07-11-hermes-root-runtime-authority.md — R0 Governance-Entscheidung
- docs/reports/r1-hermes-root-executor-implementation-2026-07-11.md — R1 Implementierung (PR #508)
- docs/reports/h3b-productive-daemon-source-proof-2026-07-12.md — Source-Verification
- docs/reports/h3b-root-executor-source-migration-2026-07-12.md — Migration zum Repo-Daemon
- docs/reports/h3b-runtime-control-proof-2026-07-13-part2.md — Permission-Fix (PR #553/#559)
- docs/state/current-operational-state.md — Kanonischer Snapshot: 🟢 Reachable and fully proven

### 6. Operational State (current-operational-state.md)

`
Root Executor: 🟢 Reachable and fully proven from Hermes
  hermes-root-executor.service active/running (root:hermes permissions
  since the 2026-07-13 systemd fix); complete Issue #531 proof matrix
  passes 5/5; secret exposure contained and credential rotation
  human-attested.
`

## Investigation

Geprüft:
- [x] systemd unit active/running, NRestarts=0
- [x] Socket-Pfad existiert, korrekte Permissions (root:hermes 0660)
- [x] Kill-Switch absent (NORMAL)
- [x] Daemon-Binary auf Host deployed (16424 bytes, Jul 13 11:20)
- [x] Repo-Daemon vollständig versioniert (hermes_root/)
- [x] Dokumentation umfassend (ADR, commands/, docs/reports/, ops/systemd/)
- [x] H3B_RUNTIME_CONTROL_GREEN, Issue #531 proof matrix 5/5

Ausgeschlossen:
- [x] executor.sock ist KEIN undokumentiertes Mysterium — dokumentiert seit R1 (2026-07-11)
- [x] Kein Crash, kein Restart-Loop (NRestarts=0)
- [x] Kein Permission-Problem (root:hermes seit Fix 2026-07-13)

## Root Cause

Der ursprüngliche Befund ( executor.sock undokumentiert) war zum Zeitpunkt der
Log-Analyse bereits STALE. Der hermes-root-executor.service wurde in R1 (PR #508,
2026-07-11) implementiert und ist seither in mehreren Iterationen dokumentiert,
gehärtet und verifiziert worden (R2, H3A, H3B, R5A).

## Solution

Keine Änderung nötig. Der Service ist:
- Dokumentiert (ADR, commands/, hermes_root/, docs/reports/)
- Aktiv und gesund (NRestarts=0, 5h+ uptime)
- Korrekt permissioniert (root:hermes, via systemd drop-in)
- Vollständig versioniert (Repo-Daemon = Source of Truth)

## Verification

- systemctl status: active/running, MainPID=608481, NRestarts=0
- ls -la /run/hermes-root-executor/: root:hermes 0750, executor.sock root:hermes 0660
- git grep executor.sock: 20+ Treffer in commands/, docs/, hermes_root/, ops/, scripts/
- git grep hermes-root-executor: 100+ Treffer in AGENTS.md, ADR, docs/, hermes_root/, scripts/
- current-operational-state.md: 🟢 Reachable and fully proven
- Kill-Switch: NORMAL (DISABLED absent)
