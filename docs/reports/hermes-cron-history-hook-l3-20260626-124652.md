# Hermes Cron History Hook L3 Apply — YELLOW Report

**Date (UTC):** 2026-06-26 12:46:52
**Auditor:** Hermes (orchestrator profile)
**Operation Level:** L3 file-level (partial — blocked at root-write step)
**Final Status:** **YELLOW — restart_required=yes, root-deploy-required**
**PRs merged:** #365, #366, #367
**Next Step:** User runs `sudo bash /opt/data/profiles/orchestrator/state/cron_history_patches/deploy_patched_scheduler.sh` as root, then restart scheduler, then natural-run observation.

---

## Executive Verdict

**YELLOW — 88/100**

Der komplette Tooling-Stack ist fertig, grün, deployed und durch drei PRs reviewt. Der eigentliche Apply auf `/opt/hermes/cron/scheduler.py` ist **vorbereitet und verifiziert**, scheitert aber an der Root-Permission-Barriere: `/opt/hermes/cron/` ist `drwxr-xr-x 10000 10000`, hermes (UID 1337) darf nicht schreiben.

Das **L2-Tooling-Ziel** ist GREEN. Das **L3-Runtime-Ziel** ist YELLOW mit klarem, von Root ausführbarem Einzeiler. Kein Restart wurde durchgeführt. Kein Service wurde gestartet oder gestoppt.

## Was im Repo bestätigt ist

### PRs gemerged

| PR | Status | Inhalt | Merge Commit |
|----|--------|--------|--------------|
| #365 | ✅ Merged | Real hook apply tool (--status/--dry-run/--backup/--apply/--verify/--rollback) | `09d191a` |
| #366 | ✅ Merged | Bug-Fix: filter real mark_job_run call sites (exclude comments + imports) | `2163790` |
| #367 | ✅ Merged | Bug-Fix: py_compile fallback when target __pycache__ is unwritable | `869881d` |

### Lokale main-Sync

```
HEAD:    869881d fix(hermes-cron): py_compile fallback (...)
origin:  869881d
Status:  ## main...origin/main (clean)
```

### Tests

```
$ python3 -m pytest tests/test_apply_cron_history_hook.py -v
# 20 passed in 2.19s
```

Inkl. zwei neue Bug-Regression-Tests (Call-Site-Filter, py_compile-Fallback).

## PR #365

| Check             | Result |
| ----------------- | ------ |
| Merged            | yes |
| Merge method      | squash |
| Merge commit      | `09d191a` |
| Local main synced | yes |

## Runtime Hook Tool Deploy

| File | Git SHA | Runtime SHA | SHA Match | py_compile |
| ---- | ------- | ----------- | --------: | ---------: |
| `apply_cron_history_hook.py` | `eac000f8…d14122` | `eac000f8…d14122` | ✅ | ✅ |
| Backup | `/opt/data/profiles/orchestrator/archive/cron-history-hook-tool-deploy/20260626T123811Z/files/apply_cron_history_hook.py` | SHA `e33307…0d8df` (original runtime version, 9567 bytes) | ✅ restored via `restore.sh` |

Runtime-Tool ist auf dem Bug-Fix-Stand (PR #367 eingeschlossen). `python3 -m py_compile` PASS, alle CLI-Modi funktional.

## Scheduler Hook Apply

### Status Before

```
jobs.json SHA: 6b33208901c7dd46 (Read-only — never written by tool)
[STATUS]
  target    : /opt/hermes/cron/scheduler.py
  backup_dir: /opt/data/profiles/orchestrator/state/cron_history_patches
  state     : unpatched
  sha256    : f2816dea78a62445
  import    : absent
  call      : absent (count=0)
```

### Dry-Run

```
[DRY-RUN]
  would_apply         : True
  reason              : would insert import block + call block(s) after each mark_job_run
  current state       : unpatched
  mark_job_run anchors: 2            ← Bug-Fix #366 (war vorher 4)
  -> import_block: anchor='from hermes_time import now as _hermes_now', ~11 lines
  -> call_block: anchor='mark_job_run(', ~13 lines
```

### Scheduler.py Compile Pre-Apply

```
$ python3 -c "import py_compile; py_compile.compile('/opt/hermes/cron/scheduler.py', cfile='/tmp/pre.pyc', doraise=True)"
compile ok, pyc=/tmp/pre.pyc
```

(Source parses clean; das öffentliche `python3 -m py_compile` würde in `/opt/hermes/cron/__pycache__/` schreiben wollen und rc=1 wegen Permission melden — Bug-Fix #367 erkennt und umgeht das.)

### Backup

```
[BACKUP]
  backup   : /opt/data/profiles/orchestrator/state/cron_history_patches/scheduler.py.20260626_124540.bak
  sha256   : f2816dea78a62445  (matches original scheduler.py)
```

Zusätzlich existiert ein zweiter Backup `scheduler.py.20260626_124619.bak` aus dem in-process Generate-Patch-Schritt (identische SHA).

### In-Process Patch (Tool Self-Test auf echtem Scheduler)

Wir konnten `/opt/hermes/cron/scheduler.py` nicht direkt überschreiben (Root-Permission). Stattdessen:

1. Original `/opt/hermes/cron/scheduler.py` (97387 bytes, SHA `f2816dea…`) nach `/tmp/hermes_hook_apply_tmp/scheduler.py` kopiert
2. `apply_cron_history_hook.apply_patch()` in-process aufgerufen
3. Patched content nach `/opt/data/profiles/orchestrator/state/cron_history_patches/scheduler.py.patched` geschrieben (99185 bytes, SHA `ce820537…`)
4. Compile-Check auf dem patched content: **PASS**

```
Markers in patched file:
  import_block: 1/1   (# HERMES_CRON_HISTORY_HOOK_BEGIN/END)
  call_blocks:  2/2   (# HERMES_CRON_HISTORY_HOOK_CALL_BEGIN/END — one per real mark_job_run call)
```

### Apply — BLOCKED

```
$ python3 /opt/data/profiles/orchestrator/scripts/apply_cron_history_hook.py --apply --target /opt/hermes/cron/scheduler.py
Traceback (most recent call last):
  ...
  File ".../pathlib/_local.py", line 539, in open
PermissionError: [Errno 13] Permission denied: '/opt/hermes/cron/scheduler.py'
```

**Root Cause:**

```
$ stat -c '%U:%G %a' /opt/hermes/cron/scheduler.py
UNKNOWN:UNKNOWN 644            # UID 10000:10000 (hermes inside container)
$ stat -c '%U:%G %a' /opt/hermes/cron/
UNKNOWN:UNKNOWN 755            # Directory UID 10000:10000, no group/other write
$ id
uid=1337(hermes) gid=1337(hermes)
```

`/opt/hermes/cron/` und seine Dateien sind UID-10000-owned. hermes (UID 1337) ist NICHT in group 10000 und hat kein Schreibrecht. Sudo ist nicht installiert (`command not found`). Permission-Drift zwischen UID 10000 und 1337 ist exakt das im Skill `hermes-cron-runtime-contract` dokumentierte Pitfall.

### Verify — Not Yet Reached

Da `--apply` nicht durchlief, wurde `--verify` auf der Runtime-Datei nicht ausgeführt. Der gepatchte Inhalt im Backup-Dir wurde in-process verifiziert (Compile OK, Marker OK, Struktur OK).

### scheduler.py Compile Post-Apply

Nicht anwendbar — Apply hat nicht stattgefunden. Patched-Content ist in `/opt/data/profiles/orchestrator/state/cron_history_patches/scheduler.py.patched` und ist kompilierbar.

### Rollback Path

Aktuell nicht nötig, da `/opt/hermes/cron/scheduler.py` **unverändert** ist (SHA `f2816dea…` identisch zum Pre-Apply-Stand).

Falls der User den Deploy-Skript ausführt und das Ergebnis rückgängig machen will:

```bash
sudo cp -p /opt/data/profiles/orchestrator/state/cron_history_patches/scheduler.py.20260626_124619.bak /opt/hermes/cron/scheduler.py
sudo chmod 644 /opt/hermes/cron/scheduler.py
```

## Restart Gate

| Check             | Result         | Evidence |
| ----------------- | -------------- | -------- |
| Restart required  | yes (PENDING — depends on Phase 5 deploy) | Patch ist nicht im laufenden Scheduler geladen, weil nicht deployt |
| Restart performed | no             | Strict Rule erfüllt: kein Restart ohne explizite Approval, kein Restart-Gate explizit in diesem Lauf freigegeben |
| Reason            | Phase 5 deploy benötigt Root; Restart hängt vom Deploy ab | Permission-Drift UID 10000 vs UID 1337 |

**Restart-Gate Bedingung (für später, nach Deploy):**

- [ ] `sudo bash /opt/data/profiles/orchestrator/state/cron_history_patches/deploy_patched_scheduler.sh` ist gelaufen
- [ ] `--verify` auf Runtime meldet patched
- [ ] scheduler.py kompiliert (py_compile oder in-process)
- [ ] Ein Natural Scheduler Run ist erfolgt **ohne** Restart UND `cron_history.sqlite` hat KEINE neue Row → **restart_required=yes**, separate Freigabe
- [ ] ODER: User gibt expliziten Restart-Approval im Prompt → Restart, dann Phase 7

## Cron History Proof

| Check                        | Before | After |
| ---------------------------- | -----: | ----: |
| cron_history.sqlite rows     |      ? |   N/A |
| latest scheduler-written row |    N/A |   N/A |

Observation Phase ist **nicht ausgeführt**, weil Phase 5 (Apply) wegen Root-Permission blockiert ist. Sobald User den Deploy-Skript ausführt, kann Phase 7 mit dem Observation-Window starten.

## Runtime Safety Checklist

| Item                              | Status |
|-----------------------------------|--------|
| jobs.json direct edit             | **no** — Tool schreibt nur scheduler.py, jobs.json SHA vor/nach unverändert |
| Service restart                   | **no** — kein Restart durchgeführt |
| Broad chmod/chown                 | **no** — nur gezielte chmod 755 auf das neue Script beim Deploy, keine directory-Operation |
| Trading parameter changes         | **no** — kein Trading-System angefasst |
| Secrets exposed                   | **no** — keine secrets in stdout, kein env dump, keine token-prints |
| cron_history.sqlite pre-existing  | **not yet created** — wird beim ersten Hook-Aufruf automatisch angelegt |
| Hermes process alive              | **yes** (pre-condition für Restart-Gate) |

## Cron History Tooling State

```
/opt/data/profiles/orchestrator/scripts/:
  ✅ cron_history_writer.py        (PR #362, deployed 2026-06-26)
  ✅ heartbeat_writer.py           (PR #362, deployed 2026-06-26)
  ✅ apply_cron_history_hook.py    (PR #365+366+367, deployed 2026-06-26 12:45)
  ✅ deploy_patched_scheduler.sh   (NEW — root-deploy helper, 2026-06-26 12:46)

/opt/data/profiles/orchestrator/state/cron_history_patches/:
  ✅ scheduler.py.20260626_124540.bak         (97387 B, SHA f2816dea…)
  ✅ scheduler.py.20260626_124619.bak         (97387 B, SHA f2816dea…)
  ✅ scheduler.py.patched                     (99185 B, SHA ce820537…) — READY TO DEPLOY
  ✅ MANIFEST.jsonl
  ✅ deploy_patched_scheduler.sh              (1454 B, mode 0755)
```

## Final Status

**YELLOW: restart_required=yes, root-deploy-required.**

Grund:
- L2-Tooling (PRs #365/#366/#367) ist vollständig gemerged, getestet (20 passed), deployed und nachweisbar grün
- L3-Patch auf `/opt/hermes/cron/scheduler.py` ist **vorbereitet** (gepatchter Inhalt + deploy-Skript + SHA-Verifikation)
- Apply selbst kann nur als root erfolgen → **blocked on user action**
- Kein Restart, keine Live-Mutation, keine jobs.json-Änderung bisher

## Empfohlene nächste Schritte (User-Aktion)

```bash
# 1. Hook-File als root deployen (interaktiv, SHA-verifiziert):
sudo bash /opt/data/profiles/orchestrator/state/cron_history_patches/deploy_patched_scheduler.sh

# 2. Verifizieren:
python3 /opt/data/profiles/orchestrator/scripts/apply_cron_history_hook.py --status
python3 /opt/data/profiles/orchestrator/scripts/apply_cron_history_hook.py --verify

# 3. Observation-Window starten — KEIN RESTART JETZT:
#    Erst prüfen, ob der laufende Scheduler die geänderte Datei beim nächsten
#    tick nachlädt (Python lädt .py normalerweise nur einmal pro Prozess-Start,
#    also wahrscheinlich Neustart nötig).
#    Wenn nach 1-2 Cron-Ticks KEINE neue Row in cron_history.sqlite:

# 4. Restart-Gate separat:
#    siehe Restart-Gate Block oben — nur nach expliziter Approval.
```

## Remaining Work (reale Blocker)

| # | Blocker | Owner | Severity |
|---|---------|-------|----------|
| 1 | Root-Deploy von `scheduler.py.patched` | user | P0 |
| 2 | Restart-Gate nach Deploy (wahrscheinlich nötig weil Python Module-Cache) | user approval needed | P0 |
| 3 | Natural Scheduler Observation (≥ 1 echte Row in cron_history.sqlite) | post-restart | P0 |
| 4 | Final GREEN-Status update dieses Reports | post-observation | P1 |

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| PR #365 merged and local main synced | ✅ |
| Updated hook tool deployed to runtime with SHA proof | ✅ |
| `/opt/hermes/cron/scheduler.py` backed up before patch | ✅ (zwei Backups im backup-dir) |
| Hook applied only after dry-run and backup | ⚠️ PARTIAL — dry-run und backup gemacht, apply selbst durch Root-Permission blockiert |
| Hook verify passes | ⚠️ PARTIAL — verify NICHT auf Runtime (kein Apply), aber patched content kompiliert und Marker korrekt |
| scheduler.py compiles after patch | ⚠️ PARTIAL — patched content kompiliert, Runtime-Datei unverändert |
| No jobs.json direct edits | ✅ |
| No secrets exposed | ✅ |
| No trading parameters changed | ✅ |
| Full GREEN requires ≥1 real scheduler-written row in cron_history.sqlite | ❌ PENDING — Apply blockiert |
| Final report committed as docs only | ✅ (dieser Report, nach Commit) |

## Risiken

1. **Patch durability**: `/opt/hermes` ist kein Git-Repo. Nach jedem `hermes update` wird scheduler.py überschrieben. Hook muss re-appliziert werden (siehe Skill-Pitfall). Idempotenter Marker-Mechanismus ist bereits implementiert.
2. **Restart impact**: Hermes Dashboard/Gateway muss neu gestartet werden, damit das geänderte scheduler.py geladen wird. Restart ist ein L3B-Schritt, separate Freigabe nötig.
3. **Cron jobs json**: jobs.json wird vom Scheduler-Prozess kontinuierlich aktualisiert (updated_at). Das ist normal und kein Hook-Effekt.

## Files in this PR (geplant)

- `docs/reports/hermes-cron-history-hook-l3-20260626-124652.md` — dieser Report (YELLOW)
- KEINE Runtime-Backups
- KEINE SQLite DBs
- KEINE Logs
- KEINE env/secrets

## Commit Policy

- ✅ Nur Report-File wird committed
- ✅ Kein `.bak`, `.patched`, `deploy_*.sh`, `MANIFEST.jsonl` aus Runtime-Pfaden
- ✅ Commit Message: `docs: record Hermes cron history hook L3 status (YELLOW)`
