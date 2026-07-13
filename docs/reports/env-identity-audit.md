# Git-Identity & CI-Env Audit Report

> Session: hermes-skill-debug-2026-07-13 | Step 2/6 | Scope L0+L2
> Date: 2026-07-13

## Issue: Git-Identity-Konsistenz, CI-Environment-Variablen und Secret-Hygiene

Prüfung der Git-Identity-Konfiguration (deploy/root/hermes), GH_TOKEN/GITHUB_TOKEN
in Environment-Dateien und CI-Workflows, sowie Secret-Leakage in Git-Config.

## Evidence

### 1. deploy Git-Identity (global ~/.gitconfig)

```
[user]
    name = Luke
    email = GoLukeEnviro@users.noreply.github.com
[credential "https://github.com"]
    helper = !/usr/bin/gh auth git-credential
```

### 2. deploy Git-Identity (repo-level .git/config)

Doppelte, inkonsistente Einträge:
```
user.name=Luke
user.name=GoLukeEnviro        ← DUPLIKAT, anderer Wert
user.email=GoLukeEnviro@users.noreply.github.com
user.email=lukvshop@gmail.com  ← DUPLIKAT, anderer Wert
```

### 3. CRITICAL: PAT in remote.origin.url

```
remote.origin.url=https://GoLukeEnviro:github_pat_[REDACTED]@github.com/GoLukeEnviro/trading-hub.git
```

Der GitHub PAT ist direkt in der Remote-URL eingebettet. Dies ist ein Secret-Leak:
- Der PAT ist in `git config --list` sichtbar
- Der PAT erscheint in Backup/Clone-Operationen
- Der PAT ist im `.git/config` File auf Disk persistiert
- Der credential helper (`gh auth git-credential`) ist bereits korrekt konfiguriert
  aber wird durch die embedded Credentials in der URL umgangen

### 4. GH_TOKEN / GITHUB_TOKEN

- Keine `.env`-Dateien vorhanden → kein Leak-Risiko
- `docs/runbooks/hermes-github-multi-repo-auth.md` dokumentiert GH_TOKEN-Flow korrekt
- `docs/reports/h3b-runtime-control-proof-2026-07-13-part2.md` bestätigt: Secret-Scan clean
  auf `github_pat_`, `ghp_`, `GH_TOKEN=`, `GITHUB_TOKEN=`
- **ABER**: Der Secret-Scan hat offenbar den PAT in `.git/config` nicht erfasst
  (Scan lief gegen Working Tree und Diff/Log, nicht gegen `.git/config`)

### 5. Docker/Entrypoint

Keine `git config`, `user.email` oder `user.name` in Dockerfiles oder Entrypoint-Skripten.
Kein Identity-Leak in Container-Builds.

### 6. CI-Workflows (.github/workflows/)

Drei Workflows: `main-gate.yml`, `si-v2-offline-smoke.yml`, `si-v2-phase2-proposal-gate.yml`

- Keine `GH_TOKEN`- oder `GITHUB_TOKEN`-Referenzen
- `main-gate.yml` nutzt `permissions: contents: read` (minimal)
- Standard `actions/checkout@v4` mit implizitem `GITHUB_TOKEN`
- Keine `git config`-Aufrufe in Workflows

### 7. Weitere User

- `root`: Nur `safe.directory = /opt/data/projects/trading-hub` → clean
- `hermes`: Kein `.gitconfig` → clean

## Investigation

Geprüft:
- [x] deploy `.gitconfig` global (clean, gh credential helper aktiv)
- [x] deploy `.git/config` repo-level (inkonsistente Duplikate)
- [x] `remote.origin.url` auf embedded Credentials (PAT gefunden)
- [x] Alle `.env*`-Dateien (keine vorhanden)
- [x] Dockerfiles/Entrypoints auf git-Identity (clean)
- [x] CI-Workflows auf Token-Handling (minimal, korrekt)
- [x] root/hermes `.gitconfig` (clean)

Ausgeschlossen:
- [x] GH_TOKEN in Umgebungsvariablen (keine `.env`-Dateien)
- [x] Identity-Leak in Container-Builds
- [x] Übermäßige CI-Permissions

## Root Cause

1. **PAT in remote.origin.url**: Der PAT wurde wahrscheinlich bei der initialen
   Repository-Konfiguration direkt in die Clone-URL eingebettet, bevor der
   credential helper eingerichtet wurde. Der credential helper ist jetzt aktiv,
   aber die embedded Credentials in der URL umgehen ihn.

2. **Inkonsistente git-Identity**: Repo-level `git config`-Aufrufe ohne `--global`
   haben die Werte ins lokale `.git/config` geschrieben, wo sie mit anderen
   lokalen Werten konkurrieren. `git config` ohne `--global` oder `--local` 
   schreibt standardmäßig lokal, was zu Duplikaten führt wenn vorher schon
   Werte gesetzt waren.

## Solution

### Fix 1: PAT aus remote.origin.url entfernen (PRIORITÄT HOCH)

```bash
git -C /opt/data/projects/trading-hub remote set-url origin \
  https://github.com/GoLukeEnviro/trading-hub.git
```

Der credential helper (`gh auth git-credential`) authentifiziert danach automatisch.
Kein PAT mehr in der Config sichtbar.

### Fix 2: Git-Identity bereinigen

```bash
# Duplikate aus repo-level config entfernen
git -C /opt/data/projects/trading-hub config --unset user.name
git -C /opt/data/projects/trading-hub config --unset user.email
# Nur global definieren (bereits korrekt: Luke / GoLukeEnviro@users.noreply.github.com)
```

### Fix 3: Secret-Scan auf .git/config ausweiten (optional)

`scripts/secret_scan.py` um Prüfung auf `.git/config` erweitern, um embedded
Credentials in Remote-URLs zu erkennen.

## Verification

- `git config --list` zeigt keinen PAT mehr
- `git remote -v` zeigt `https://github.com/GoLukeEnviro/trading-hub.git` (ohne Credentials)
- `git config user.name` → `Luke` (global, konsistent)
- `git config user.email` → `GoLukeEnviro@users.noreply.github.com` (global, konsistent)
- `git fetch` funktioniert via credential helper
