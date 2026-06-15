# Yellow Branch Triage — Read-Only Classification Plan

**Status:** Ready for execution
**Created:** 2026-06-15
**Phase:** YELLOW (nach abgeschlossenem GREEN_DELETE)
**Target environment:** Hermes-Container (`/home/hermes/projects/trading`) — Environment-spezifische Validierung im Pre-flight (Task 1)
**Original target path:** `docs/plans/yellow-branch-triage.md` (Prometheus-Hook blockt docs/, Datei liegt hier in .omo/plans/ — User kann sie nach docs/plans/ verschieben)

---

## TL;DR

> **Quick Summary**: Read-only Triage aller 51 verbleibenden Remote-Branches (49 YELLOW_COMPARE + 2 neue Gap-Audit-Branches) nach GREEN_DELETE-Cleanup. Klassifizierung in 5 Kategorien ohne Löschungen. Ein scoped Commit persistiert die bisherigen Cleanup-Reports.
>
> **Deliverables**:
> - Scoped Commit `docs(git): add branch cleanup reconciliation reports`
> - `docs/reports/git-branch-cleanup-yellow-triage-{timestamp}Z.md`
> - `docs/reports/git-branch-cleanup-yellow-triage-{timestamp}Z.json`
> - Post-flight Verifikations-Output
>
> **Estimated Effort**: Short (1–2 Stunden)
> **Parallel Execution**: NO — sequenziell (Safety-First); nur Final Wave parallel
> **Critical Path**: Task 1 (Pre-flight + Commit) → Task 2 (Collect) → Task 3 (Classify + Report) → Task 4 (Verify) → F1–F4

---

## Context

### Original Request
Nach erfolgreichem GREEN_DELETE-Cleanup (47 Branches gelöscht, Post-Cleanup-Preflight reconciled) soll eine **read-only Triage** aller 51 verbleibenden Remote-Branches erstellt werden. Ziel: Klassifizierung, **nicht Löschung**. Lösch-Entscheidungen werden in einem separaten, späteren Schritt getroffen.

### Interview Summary

**Key Discussions**:
- User hat vollständigen Hermes-Agent-Prompt spezifiziert (siehe Anhang A)
- 2 neue Gap-Audit-Branches (`chore/gap-audit-p0-security-ci`, `feat/gap-audit-p246-endpoint-auth`) erschienen während Cleanup-Fenster — müssen konservativ behandelt werden
- Umgebungsdiskrepanz identifiziert: Lokale Windows-Copy bei `HEAD=42263aa`, User-Report beschreibt Hermes-Env bei `HEAD=ced01d1` → Plan muss environment-agnostisch sein, Pre-flight muss Environment validieren und dynamischen HEAD-Pin setzen

**Research Findings**:
- Repo nutzt `docs/`-Konvention (kein `.omo/` vorhanden)
- Report-Naming: `git-branch-cleanup-{phase}-{timestamp}Z.{ext}`
- Report-Sprache: Deutsch (per CLAUDE.md und bestehende Reports)
- AGENTS.md: explizites Staging, keine destructiven Commands, keine `git add .`

### Gap Analysis (Prometheus-Self-Review statt Metis — Billing-Limit)

**Identifizierte Lücken im User-Spec** (alle in Plan adressiert):

| # | Lücke | Lösung im Plan |
|---|-------|---------------|
| 1 | Timestamp-Format `20260615T<UTC>` war Platzhalter | Explizit: `date -u +%Y%m%dT%H%M%SZ` |
| 2 | Stop-Condition-Ordering unklar | Untracked-File-Check VOR Commit, nicht danach |
| 3 | HEAD-Pin fehlte | Dynamisch: Start-HEAD erfassen, am Ende verifizieren |
| 4 | JSON-Schema undefiniert | Explizites Schema in Task 3 definiert |
| 5 | Gap-Audit-Branches nur "nicht löschen" | Hardcode: niemals DELETE_CANDIDATE, immer KEEP_ACTIVE/NEEDS_MANUAL_REVIEW |
| 6 | `git fetch --all --prune` Fail-Handling fehlt | Bei Fetch-Failure: ABORT, keine stale Daten |
| 7 | Report-Dateikollision undefiniert | Bei Existenz: ABORT, nicht überschreiben |
| 8 | Large-Diff-Truncation unklar | Max 50 geänderte Files in `.md`, voll in `.json` |

---

## Work Objectives

### Core Objective
Erzeuge eine vollständige, read-only Klassifizierung aller 51 verbleibenden Remote-Branches als Entscheidungsgrundlage für spätere Lösch-Statements — **ohne irgendetwas am Code, Runtime-State, Docker, Freqtrade, SI v2, Cron, Config oder Branch-State zu verändern**.

### Concrete Deliverables
1. **Scoped Commit** `docs(git): add branch cleanup reconciliation reports` (ausschließlich Dateien unter `docs/reports/git-branch-cleanup-*`)
2. **Markdown-Report** `docs/reports/git-branch-cleanup-yellow-triage-{timestamp}Z.md`
3. **JSON-Report** `docs/reports/git-branch-cleanup-yellow-triage-{timestamp}Z.json`
4. **Post-flight Verifikations-Output** als Evidence

### Definition of Done
- [ ] Alle 51 Branches im Report mit Klassifizierung, ahead-count, changed-file-count, Begründung
- [ ] 0 Branches gelöscht (`git branch -r | grep -v HEAD | wc -l` vor = nach)
- [ ] HEAD unverändert zwischen Start und Ende (dynamischer Pin)
- [ ] Worktree-Status dokumentiert (vor/nach)
- [ ] keine Runtime/Docker/Freqtrade/SI v2/cron/config-Touches
- [ ] JSON-Report validierbar (`jq . file.json > /dev/null` exit 0)

### Must Have
- Pre-flight: Environment-Validierung (Start-HEAD erfassen, Branch-Count-Baseline, Untracked-File-Scan)
- Scoped Commit NUR für `docs/reports/git-branch-cleanup-*`
- Klassifizierung jeder der 51 Branches mit: `ahead_count`, `changed_file_count`, `is_ancestor`, `classification`, `reasoning`
- Die 2 Gap-Audit-Branches: niemals `DELETE_CANDIDATE` (Hardcode-Filter)
- Post-flight: Verifikation dass 0 Branches gelöscht, HEAD unverändert
- JSON-Report mit definiertem Schema (siehe Task 3)
- Exakte nicht-ausgeführte `git push origin --delete`-Kommandos für `DELETE_CANDIDATE`-Branches als Referenz

### Must NOT Have (Guardrails)
- **KEINE** Branch-Löschung (auch keine automatisierte DELETE_CANDIDATE-Ausführung)
- **KEIN** `git gc`, `git prune --expire=now`, oder reflog-Cleanup
- **KEIN** merge, rebase, reset, force-push, ref-update irgendwelcher Branches
- **KEIN** Docker-, Freqtrade-, SI v2-, cron-, config-Touch
- **KEIN** Source-Code-Edit (`.py`, `.json` configs, `.yml`, etc.)
- **KEIN** `git add .` — nur explizite Dateipfade under `docs/reports/git-branch-cleanup-*`
- **KEIN** Überschreiben existierender Report-Dateien (Kollision → Abort)
- **KEIN** Vorgehen mit stale Daten bei `git fetch`-Failure
- **KEINE** Klassifizierung der 2 Gap-Audit-Branches als `DELETE_CANDIDATE`
- **KEIN** Überschreiten des Scopes auf ZAI-Provider-Config oder andere Konfigurationsbereiche
- **KEIN** Branch-Checkout während der Triage (alles via `origin/<branch>` refs ohne Working-Tree-Wechsel)

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — Alle Verifikation agent-executed.

### Test Decision
- **Infrastructure exists**: N/A (read-only Report-Task, kein Code-Test)
- **Automated tests**: None (klassifizierende Report-Erstellung)
- **Framework**: Bash + `jq` für JSON-Validierung

### QA Policy
Jeder Task MUSS agent-executed QA-Szenarien haben.
Evidence unter `.omo/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Git-State-Checks**: Bash (`git status`, `git rev-parse`, `git branch -r`, `git diff --stat`)
- **Report-Validation**: Bash (`jq` für JSON, `grep`/`Select-String` für Markdown-Inhalt)
- **Safety-Verifikation**: Bash (Count-Diff vor/nach, HEAD-Diff vor/nach)
- **Read-only-Compliance**: Bash (Worktree-Status, `git reflog`-Länge vor/nach)

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Sequenziell — Safety-First):
├── Task 1: Pre-flight + scoped Commit der Reports
├── Task 2: Fetch + Branch-Enumeration + Per-Branch-Data-Collection (51 Branches)
├── Task 3: Klassifizierung + Report-Generierung (.md + .json)
└── Task 4: Post-flight Verifikation (read-only Compliance)

Wave FINAL (4 parallele Reviews nach Task 4):
├── F1: Plan-Compliance-Audit (oracle)
├── F2: Report-Quality-Review (unspecified-high)
├── F3: Manual Spot-Check von 5 Random-Branches (unspecified-high)
└── F4: Scope-Fidelity-Check (deep)

Critical Path: Task 1 → Task 2 → Task 3 → Task 4 → F1–F4
Parallel Speedup: Nur in Final Wave (~30% Ersparnis)
Max Concurrent: 4 (nur Final Wave)
```

### Dependency Matrix

| Task | Blocked By | Blocks |
|------|-----------|--------|
| 1 | — | 2 |
| 2 | 1 | 3 |
| 3 | 2 | 4 |
| 4 | 3 | F1, F2, F3, F4 |
| F1–F4 | 4 | — |

### Agent Dispatch Summary

| Task | Category | Reason |
|------|----------|--------|
| 1 | `quick` | Kleiner Pre-flight + 1 Commit |
| 2 | `unspecified-high` | 51 Branches × mehrere git commands |
| 3 | `deep` | Klassifizierung erfordert Urteilkraft über viele Branches |
| 4 | `quick` | Verifikation mit festen Checks |
| F1 | `oracle` | Plan-compliance read-only review |
| F2 | `unspecified-high` | Report-Structur/Quality-Check |
| F3 | `unspecified-high` | Spot-Check mit handgemachter Verifikation |
| F4 | `deep` | Scope-Fidelity mit diff-Analyse |

---

## TODOs

> Implementation = Report-Erstellung. Jeder Task MUSS QA-Szenarien haben.
> Task-Labels im Format `1.`, `2.`, etc. (bare numbers).
> Final-Wave-Labels im Format `F1.`, `F2.`, etc.

- [ ] 1. **Pre-flight + scoped Commit der Reports**

  **What to do**:
  - Working Directory verifizieren (`pwd`, `git rev-parse --show-toplevel`)
  - `HEAD_AT_START=$(git rev-parse HEAD)` erfassen und im Evidence speichern
  - `BRANCH_COUNT_AT_START=$(git branch -r | grep -v HEAD | grep -v "origin/main$" | wc -l)` — erwartet 51; falls abweichend: WARNING, weiterfahren
  - Baselines erfassen: `DOCKER_AT_START` (docker ps), `KILL_SWITCH_AT_START` (var/kill_switch.json mode), `WORKTREE_AT_START` (git status --porcelain)
  - **Untracked-File-Scan**: `git status --porcelain | grep '^??'` — alle untracked Files auflisten
  - **STOP-Bedingung PRÜFEN (VOR Commit)**: Falls untracked Files existieren, die NICHT `docs/reports/git-branch-cleanup-*` matchen → ABORT, kein Commit, kein Weiterfahren. Verbotene Files im Error listen.
  - Falls STOP nicht auslöst: Reports explizit stagen per `git add docs/reports/git-branch-cleanup-delete-green-20260615T164801Z.md docs/reports/git-branch-cleanup-delete-green-20260615T164801Z.json docs/reports/git-branch-cleanup-preflight-20260615T183449Z.json docs/reports/git-branch-cleanup-preflight-20260615T183613Z.md docs/reports/git-branch-cleanup-post-green-mini-preflight-20260615T184500Z.md docs/reports/git-branch-cleanup-post-green-mini-preflight-20260615T184500Z.json`
  - Staged-Files verifizieren: `git diff --cached --name-only` darf NUR die 6 Reports zeigen
  - Falls andere Files staged: `git reset` (unstage alles), ABORT mit Error
  - Commit: `git commit -m "docs(git): add branch cleanup reconciliation reports"`
  - `COMMIT_HASH=$(git rev-parse HEAD)` notieren
  - Evidence: `.omo/evidence/task-1-preflight-and-commit.md` mit allen Variablen

  **Must NOT do**:
  - KEIN `git add .`, `git add -A`, `git add -u`, oder Glob-Patterns außerhalb scope
  - KEIN Checkout, Pull, Fetch in diesem Task
  - KEIN Override der STOP-Bedingung
  - KEIN Commit wenn untracked Files außerhalb scope existieren

  **Recommended Agent Profile**:
  - **Category**: `quick` — kleiner Pre-flight + 1 Commit
  - **Skills**: [`git-master`] für korrekte Safety-Patterns

  **Parallelization**:
  - Can Run In Parallel: NO — Wave 1 sequenziell
  - Blocks: Task 2
  - Blocked By: None (startet sofort)

  **References**:
  - `AGENTS.md` Regeln 2 + 5 — explizites Staging, keine destructiven Commands
  - `docs/reports/git-branch-cleanup-post-green-mini-preflight-20260615T184500Z.md` — Format-Referenz für spätere Reports
  - `docs/git-hygiene.md` — tracked-vs-ignored-Policy
  - 6 Report-Dateien unter `docs/reports/git-branch-cleanup-*` — werden committed

  **Acceptance Criteria**:
  - [ ] HEAD_AT_START in Evidence recorded
  - [ ] BRANCH_COUNT_AT_START recorded (Warn falls ≠ 51)
  - [ ] DOCKER_AT_START, KILL_SWITCH_AT_START, WORKTREE_AT_START recorded
  - [ ] Untracked-File-Scan ausgeführt
  - [ ] Falls verbotene untracked Files: ABORT ohne Commit (Erfolg!)
  - [ ] Falls keine verbotenen untracked: Commit erstellt mit korrektem Hash
  - [ ] `git diff HEAD~1..HEAD --name-only` zeigt ausschließlich 6 Report-Dateien

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Happy Path — Pre-flight succeeds, scoped commit created
    Tool: Bash
    Preconditions: Hermes-Env, 6 untracked reports unter docs/reports/git-branch-cleanup-*, kein anderer untracked file
    Steps:
      1. `git rev-parse HEAD` → HEAD_AT_START=ced01d12... (erfassen)
      2. `git status --porcelain | grep '^??'` → listet genau 6 Einträge, alle docs/reports/git-branch-cleanup-*
      3. `git add docs/reports/git-branch-cleanup-delete-green-20260615T164801Z.md` (und 5 weitere, alle einzeln)
      4. `git diff --cached --name-only` → zeigt genau die 6 Dateien
      5. `git commit -m "docs(git): add branch cleanup reconciliation reports"` → exit 0
      6. `git log --oneline -1` → zeigt "docs(git): add branch cleanup reconciliation reports"
      7. `git diff HEAD~1..HEAD --name-only` → zeigt genau die 6 gestagten Dateien, nichts anderes
    Expected Result: Commit erstellt, genau 6 Dateien enthalten, HEAD_AT_START ≠ HEAD_AFTER_COMMIT (neuer Hash)
    Failure Indicators: staged files außerhalb scope; falsche Commit-Message; andere Files im Diff
    Evidence: .omo/evidence/task-1-preflight-and-commit.md

  Scenario: Edge — Verbotene untracked files lösen STOP aus
    Tool: Bash
    Preconditions: Zusätzlich zu den 6 Reports liegt z.B. `scratch.md` oder `config/local.env` untracked im Worktree
    Steps:
      1. `git status --porcelain | grep '^??'` → listet 6 reports PLUS mindestens 1 verbotene File
      2. Filter gegen `docs/reports/git-branch-cleanup-*` Pattern
      3. Erkenne STOP-Bedingung (non-match existiert)
      4. ABORT: KEIN `git add`, KEIN `git commit`
      5. Error-Message listet die verbotenen Files
    Expected Result: Task-Abbruch ohne Modifikation. HEAD unverändert. `git status` identisch zu Start. Evidence zeigt Abort-Reason und verbotene Files.
    Failure Indicators: Commit wird erstellt; verbotene Files gestagt; HEAD geändert
    Evidence: .omo/evidence/task-1-preflight-and-commit-abort.md

  Scenario: Edge — BRANCH_COUNT_AT_START ≠ 51
    Tool: Bash
    Preconditions: Branch-Anzahl weicht von 51 ab (z.B. 50 oder 52)
    Steps:
      1. `git branch -r | grep -v HEAD | grep -v "origin/main$" | wc -l` → z.B. 50 oder 52
      2. WARNING im Evidence: "Branch count ungleich 51: tatsächlich <N>"
      3. Weiterfahren (kein ABORT — Abweichung ist plausible Realität)
    Expected Result: Task läuft durch, Warning dokumentiert. Task 2 adaptiert mit tatsächlichem Count.
    Evidence: .omo/evidence/task-1-branch-count-warning.md
  ```

  **Commit**: YES
  - Message: `docs(git): add branch cleanup reconciliation reports`
  - Files: 6 Report-Dateien unter `docs/reports/git-branch-cleanup-*`

- [ ] 2. **Fetch + Branch-Enumeration + Per-Branch-Data-Collection**

  **What to do**:
  - `git fetch --all --prune` ausführen. Falls Exit ≠ 0 oder "fatal:" im Output → ABORT, keine stale Daten
  - `BRANCH_COUNT_POST_FETCH=$(git branch -r | grep -v HEAD | grep -v "origin/main$" | wc -l)` — mit `BRANCH_COUNT_AT_START` vergleichen, WARNING falls abweichend
  - Branch-Liste erfassen: `git branch -r | grep -v HEAD | grep -v "origin/main$" | sed 's|^[[:space:]]*||'`
  - Für jeden Branch (51 oder tatsächlicher Count) folgende Daten sammeln:
    - `git merge-base --is-ancestor origin/<branch> origin/main; echo $?` → `IS_ANCESTOR` (0=ja, 1=nein, 128=error)
    - `git log --oneline origin/<branch> --not origin/main` → `AHEAD_COMMITS` (Zeilen = `AHEAD_COUNT`)
    - `git diff --stat origin/main..origin/<branch>` → `DIFF_STAT`
    - `git diff --name-status origin/main..origin/<branch>` → `CHANGED_FILES` (A/M/D/R pro File)
    - `git log -1 --format='%H %an %ad %s' origin/<branch>` → `LAST_COMMIT`
  - Intermediate-JSON speichern: `.omo/evidence/task-2-branch-data-raw.json`
  - **Truncation-Regel**: Falls Branch > 50 changed_files → in JSON voll erfassen; für Markdown (Task 3) später auf Top-10 nach Zeilen-Change-Count kürzen. JSON bleibt IMMER vollständig.

  **Intermediate-JSON Schema**:
  ```json
  {
    "fetch_performed_at": "<ISO timestamp>",
    "branch_count_at_start": <N>,
    "branch_count_post_fetch": <N>,
    "branches": [
      {
        "name": "<branch-name>",
        "is_ancestor_of_main": <bool>,
        "ahead_count": <int>,
        "ahead_commits_oneline": "<string>",
        "changed_files_count": <int>,
        "changed_files_status": [{"file": "<path>", "status": "<A|M|D|R>"}],
        "diff_stat_summary": "<string>",
        "last_commit_hash": "<sha>",
        "last_commit_author": "<name>",
        "last_commit_date": "<ISO>",
        "last_commit_subject": "<string>"
      }
    ]
  }
  ```

  **Must NOT do**:
  - KEIN Checkout irgendwelcher Branches (alles via `origin/<branch>` Refs)
  - KEIN `git pull` (nur fetch)
  - KEIN merge, rebase, reset, stash
  - KEIN Working-Tree-Modifikation
  - KEIN Überspringen von Branches — alle 51 (oder tatsächlicher Count) erfassen
  - KEIN Raten bei Fetch-Fehlern — ABORT

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` — 51 Branches × 5 git Commands, hohes Volumen
  - **Skills**: [`git-master`] für effiziente Batch-Operationen

  **Parallelization**:
  - Can Run In Parallel: NO — sequenziell nach Task 1
  - Blocks: Task 3
  - Blocked By: Task 1

  **References**:
  - `AGENTS.md` — Safety rules für git-Operationen
  - `.omo/evidence/task-1-preflight-and-commit.md` — enthält `BRANCH_COUNT_AT_START`, `HEAD_AT_START`

  **Acceptance Criteria**:
  - [ ] `git fetch --all --prune` exit 0, kein "fatal:" im Output
  - [ ] `BRANCH_COUNT_POST_FETCH` recorded, Diff zu `AT_START` falls abweichend
  - [ ] Intermediate-JSON erstellt mit Array aller Branches
  - [ ] Jeder Branch-Eintrag hat alle 11 Pflichtfelder
  - [ ] JSON validierbar (`jq . .omo/evidence/task-2-branch-data-raw.json > /dev/null` exit 0)
  - [ ] `jq '.branches | length' .omo/evidence/task-2-branch-data-raw.json` = `BRANCH_COUNT_POST_FETCH`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Happy Path — Alle 51 Branches erfasst
    Tool: Bash
    Preconditions: Task 1 completed, fetch erfolgreich
    Steps:
      1. `git fetch --all --prune` → exit 0, kein "fatal:"
      2. `git branch -r | grep -v HEAD | grep -v "origin/main$" | wc -l` → 51 (oder tatsächlicher Wert)
      3. Für jeden Branch: führe die 5 git-Commands aus, sammle Daten
      4. Schreibe JSON zu .omo/evidence/task-2-branch-data-raw.json
      5. `jq '.branches | length' .omo/evidence/task-2-branch-data-raw.json` → 51 (oder tatsächlicher Count)
      6. `jq '.branches[0] | keys' .omo/evidence/task-2-branch-data-raw.json` → zeigt alle 11 Feldnamen
      7. `jq '.branches[] | select(.name=="chore/gap-audit-p0-security-ci") | .name' .omo/evidence/task-2-branch-data-raw.json` → returns "chore/gap-audit-p0-security-ci"
    Expected Result: JSON mit vollständigem Datensatz pro Branch, validierbar
    Failure Indicators: fetch failed; JSON invalid; Branch-Count-Mismatch; fehlende Felder; Gap-Audit-Branch fehlt
    Evidence: .omo/evidence/task-2-branch-data-raw.json

  Scenario: Edge — Fetch schlägt fehl
    Tool: Bash
    Preconditions: Netzwerk-Problem, Remote nicht erreichbar, Auth-Fehler
    Steps:
      1. `git fetch --all --prune` → exit ≠ 0 ODER "fatal:" in stderr/stdout
      2. ABORT: KEIN Weiterfahren mit stale Daten
      3. Error-Message mit Fetch-Output
      4. KEINE Intermediate-JSON erstellen
    Expected Result: Task-Abbruch. HEAD unverändert. Task 3+4 nicht ausgeführt.
    Failure Indicators: stale Daten verwendet; Branches mit Air-Gap-Daten; Intermediate-JSON trotzdem erstellt
    Evidence: .omo/evidence/task-2-fetch-failed.md (mit Fetch-stderr)

  Scenario: Edge — Branch mit riesigem Diff (> 50 changed files)
    Tool: Bash
    Preconditions: Ein Branch hat z.B. 200 changed files
    Steps:
      1. Sammle ALLE 200 changed files in Intermediate-JSON (vollständig)
      2. Truncate NICHT im JSON
      3. Merke Branch-Namen für Task 3 (dort MD-Truncation auf Top-10)
      4. `jq '.branches[] | select(.changed_files_count > 50) | .name' .omo/evidence/task-2-branch-data-raw.json` → listet über große Branches
    Expected Result: JSON hat alle 200 Files pro großem Branch. Kein Datenverlust.
    Failure Indicators: truncation im JSON; fehlende Files; JSON invalid durch size
    Evidence: .omo/evidence/task-2-branch-data-raw.json (vollständig) + .omo/evidence/task-2-large-diff-index.md (Liste der großen Branches)
  ```

  **Commit**: NO — Intermediate-Daten sind Evidence, kein Repo-Commit.

- [ ] 3. **Klassifizierung + Report-Generierung (.md + .json)**

  **What to do**:
  - Lese `.omo/evidence/task-2-branch-data-raw.json` (Intermediate-Daten)
  - Für jeden Branch Klassifizierung entscheiden gemäß Logic unten
  - **Gap-Audit-Hardcode VOR Klassifizierung**: Falls `branch.name in {"chore/gap-audit-p0-security-ci", "feat/gap-audit-p246-endpoint-auth"}` → `classification = "KEEP_ACTIVE"` wenn `last_commit_date < 60 Tage`, sonst `"NEEDS_MANUAL_REVIEW"`. Niemals `"DELETE_CANDIDATE"`.
  - Generiere Timestamp: `TS=$(date -u +%Y%m%dT%H%M%SZ)`
  - **Kollisions-Check VOR Schreiben**: Falls `docs/reports/git-branch-cleanup-yellow-triage-${TS}Z.md` ODER `.json` existiert → ABORT (nicht überschreiben)
  - Schreibe Markdown-Report: `docs/reports/git-branch-cleanup-yellow-triage-${TS}Z.md`
  - Schreibe JSON-Report: `docs/reports/git-branch-cleanup-yellow-triage-${TS}Z.json`
  - Evidence: `.omo/evidence/task-3-classification-summary.md` mit Counts und Reasoning-Highlights

  **Classification Logic**:
  - `DELETE_CANDIDATE`:
    - `is_ancestor_of_main=true` UND `ahead_count=0` (bereits komplett in main)
    - ODER `branch.name` matcht `^(scratch|test|tmp|wip|experimental)/` UND `changed_files_count ≤ 2` UND nicht in Conservative-Liste
  - `KEEP_ACTIVE`:
    - Hardcode für 2 Gap-Audit-Branches (siehe oben)
    - `last_commit_date < 30 Tage` UND Branch-name matcht `(feat|fix|chore|perf|refactor|docs|ci)/`
    - Conservative Topics: name enthält `security|ci|endpoint-auth|si-v2|si_v2|telemetry|proposal|rainbow|kill-switch|kill_switch|market-data|controller|auth` → bevorzugt KEEP_ACTIVE
  - `PR_REQUIRED`:
    - `ahead_count > 0` UND `changed_files_count > 0` UND `last_commit_date < 180 Tage` UND nicht eindeutig veraltet UND nicht Gap-Audit
  - `SUPERSEDED_BY_MAIN`:
    - `is_ancestor_of_main=false` ABER `changed_files_count > 0` mit patch-id alle in main vertreten
    - Heuristic: `git log --all --oneline | grep -F "<commit-subject>"` findet Match in main
  - `NEEDS_MANUAL_REVIEW`:
    - Weder clear delete noch clear keep
    - Merge-Konflikte zwischen Branch und main
    - `last_commit_date > 180 Tage` aber Branch hat substantielle Arbeit

  **Markdown-Report-Struktur**:
  - Header: Generated-Date, HEAD (start/end), Branch-Count, Modus (READ-ONLY)
  - Summary-Tabelle: 5 Classification-Counts
  - Pro Branch: Sektion mit `name`, `classification`, `reasoning`, `ahead_count`, `changed_file_count`, `is_ancestor`, `last_commit`, `proposed_action`
  - Große Diffs (> 50 Files): nur Top-10 geänderte Files (sortiert nach Zeilen-Change-Count)
  - `## DELETE_CANDIDATE Commands (NICHT ausgeführt)` — exakte `git push origin --delete <branch>` Befehle
  - `## Must-Not-Delete Branches` — Gap-Audit + conservative
  - `## Confirmation` — 0 deleted, 0 runtime touches, 0 git gc

  **JSON-Schema (finaler Report)** — siehe Separate Schema-Definition in References

  **Must NOT do**:
  - KEIN Checkout, KEIN merge/rebase/reset
  - KEIN `git push origin --delete` ausführen (nur als Text in Report schreiben)
  - KEIN Überschreiben existierender Report-Dateien (Kollision → ABORT)
  - KEIN Klassifizieren der 2 Gap-Audit-Branches als DELETE_CANDIDATE
  - KEIN automatisches Löschen basierend auf Klassifizierung
  - KEIN Modifizieren von `.omo/evidence/task-2-branch-data-raw.json` (read-only Input)

  **Recommended Agent Profile**:
  - **Category**: `deep` — Klassifizierung erfordert Urteilkraft über 51 Branches
  - **Skills**: [`git-master`] für patch-id/heuristic-Checks

  **Parallelization**:
  - Can Run In Parallel: NO — sequenziell nach Task 2
  - Blocks: Task 4
  - Blocked By: Task 2

  **References**:
  - `.omo/evidence/task-2-branch-data-raw.json` — Input-Daten (read-only)
  - `docs/reports/git-branch-cleanup-post-green-mini-preflight-20260615T184500Z.md` — Format-Referenz
  - `docs/GAP-REPORT-2026-06-15-TRADING-HUB.md` — Kontext für Gap-Audit-Branches (deshalb KEEP_ACTIVE)
  - `docs/git-hygiene.md` — tracked-vs-ignored-Policy
  - JSON-Schema:
    ```json
    {
      "generated_at": "<ISO>",
      "head_start": "<sha>",
      "head_end": "<sha>",
      "worktree_status_before": "<string>",
      "worktree_status_after": "<string>",
      "remaining_branch_count": <int>,
      "classifications": {
        "DELETE_CANDIDATE": <int>,
        "KEEP_ACTIVE": <int>,
        "PR_REQUIRED": <int>,
        "SUPERSEDED_BY_MAIN": <int>,
        "NEEDS_MANUAL_REVIEW": <int>
      },
      "branches": [
        {
          "name": "<branch>",
          "classification": "<DELETE_CANDIDATE|KEEP_ACTIVE|PR_REQUIRED|SUPERSEDED_BY_MAIN|NEEDS_MANUAL_REVIEW>",
          "reasoning": "<string>",
          "ahead_count": <int>,
          "changed_file_count": <int>,
          "is_ancestor": <bool>,
          "last_commit_date": "<ISO>",
          "last_commit_subject": "<string>",
          "proposed_action": "<string>",
          "must_not_delete": <bool>
        }
      ],
      "delete_candidate_commands": ["git push origin --delete <branch>"],
      "must_not_delete_branches": ["<branch>"],
      "confirmations": {
        "branches_deleted": 0,
        "runtime_operations_performed": 0,
        "git_gc_executed": false,
        "docker_touched": false,
        "config_files_modified": false
      }
    }
    ```

  **Acceptance Criteria**:
  - [ ] Timestamp mit `date -u +%Y%m%dT%H%M%SZ` generiert
  - [ ] Kollisions-Check ausgeführt (beide Dateien nicht existent)
  - [ ] Alle Branches aus Task 2-JSON klassifiziert (Count = `branch_count_post_fetch`)
  - [ ] 2 Gap-Audit-Branches als `KEEP_ACTIVE` oder `NEEDS_MANUAL_REVIEW`
  - [ ] `classifications` Summe = `remaining_branch_count`
  - [ ] `delete_candidate_commands` enthält nur `DELETE_CANDIDATE`-Branches
  - [ ] `must_not_delete_branches` enthält Gap-Audit + ggf. conservative
  - [ ] `confirmations.branches_deleted = 0`
  - [ ] JSON validierbar: `jq . report.json > /dev/null` exit 0
  - [ ] MD enthält alle 5 Pflicht-Sektionen

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Happy Path — Report generiert mit allen 51 Branches
    Tool: Bash
    Preconditions: Task 2 completed mit validem Intermediate-JSON
    Steps:
      1. `jq '.branches | length' .omo/evidence/task-2-branch-data-raw.json` → z.B. 51
      2. Für jeden Branch: apply Classification Logic + Gap-Audit-Hardcode
      3. `date -u +%Y%m%dT%H%M%SZ` → z.B. 20260615T190000Z
      4. `test -f docs/reports/git-branch-cleanup-yellow-triage-20260615T190000Z.md` → exit 1 (nicht existent, OK)
      5. Schreibe MD + JSON
      6. `jq '.branches | length' docs/reports/git-branch-cleanup-yellow-triage-20260615T190000Z.json` → 51
      7. `jq '.classifications | add' docs/reports/git-branch-cleanup-yellow-triage-20260615T190000Z.json` → 51
      8. `jq '.confirmations.branches_deleted' docs/reports/git-branch-cleanup-yellow-triage-20260615T190000Z.json` → 0
      9. `jq '.branches[] | select(.name=="chore/gap-audit-p0-security-ci") | .classification' docs/reports/git-branch-cleanup-yellow-triage-20260615T190000Z.json` → "KEEP_ACTIVE" oder "NEEDS_MANUAL_REVIEW"
     10. `jq '.branches[] | select(.name=="chore/gap-audit-p0-security-ci") | .must_not_delete' docs/reports/git-branch-cleanup-yellow-triage-20260615T190000Z.json` → true
    Expected Result: Beide Report-Dateien vorhanden, JSON valid, alle Branches klassifiziert, Gap-Audit nicht DELETE_CANDIDATE
    Failure Indicators: Branch-Count-Mismatch; Gap-Audit als DELETE_CANDIDATE; JSON invalid; Kollision nicht erkannt
    Evidence: .omo/evidence/task-3-classification-summary.md + Report-Dateien

  Scenario: Edge — Report-Datei mit gleichem Timestamp existiert bereits
    Tool: Bash
    Preconditions: Datei `docs/reports/git-branch-cleanup-yellow-triage-20260615T190000Z.md` existiert bereits (z.B. von vorherigem Run)
    Steps:
      1. `TS=$(date -u +%Y%m%dT%H%M%SZ)` → z.B. 20260615T190000Z
      2. `test -f docs/reports/git-branch-cleanup-yellow-triage-${TS}Z.md` → exit 0 (exists)
      3. ABORT: KEIN Überschreiben
      4. Error-Message: "Report file collision: <filename>"
    Expected Result: Task-Abbruch. Bestehende Datei unverändert. Keine neue Datei erstellt.
    Failure Indicators: Datei überschrieben; Content gemerged; JSON ohne Kollisions-Check geschrieben
    Evidence: .omo/evidence/task-3-collision-abort.md

  Scenario: Edge — Gap-Audit-Branch versehentlich als DELETE_CANDIDATE markiert
    Tool: Bash
    Preconditions: Classification Logic versucht, `chore/gap-audit-p0-security-ci` als DELETE_CANDIDATE zu markieren (z.B. weil is_ancestor=true)
    Steps:
      1. Hardcode-Filter vor Classification prüfen: branch.name in Gap-Audit-Set
      2. Falls ja: force `classification` zu KEEP_ACTIVE oder NEEDS_MANUAL_REVIEW
      3. `reasoning` enthält: "Gap-audit branch, hardcoded KEEP_ACTIVE per safety rule"
      4. `must_not_delete: true`
      5. In `delete_candidate_commands`: Branch fehlt
      6. In `must_not_delete_branches`: Branch enthalten
    Expected Result: Gap-Audit-Branch niemals DELETE_CANDIDATE. Hardcode-Filter greift VOR anderer Logic.
    Failure Indicators: Gap-Audit als DELETE_CANDIDATE; in delete_candidate_commands; must_not_delete=false
    Evidence: .omo/evidence/task-3-gap-audit-hardcode-check.md
  ```

  **Commit**: NO — Reports bleiben untracked für User-Review.

- [ ] 4. **Post-flight Verifikation (read-only Compliance)**

  **What to do**:
  - `HEAD_AT_END=$(git rev-parse HEAD)` — mit `HEAD_AT_START` (Task 1) vergleichen
  - Falls `HEAD_AT_END != HEAD_AT_START`: CRITICAL FAILURE — irgendwer hat währenddessen committed. Stop, dokumentiere, frage User.
  - `BRANCH_COUNT_AT_END=$(git branch -r | grep -v HEAD | grep -v "origin/main$" | wc -l)` — mit `BRANCH_COUNT_AT_START` vergleichen
  - Falls `BRANCH_COUNT_AT_END != BRANCH_COUNT_AT_START`: CRITICAL FAILURE — Branches verschwunden oder hinzugekommen
  - `WORKTREE_AT_END=$(git status --porcelain)` — darf nur untracked yellow-triage-Reports zeigen
  - Falls modified tracked files oder staged files: CRITICAL FAILURE
  - `DOCKER_AT_END=$(docker ps --format '{{.Names}}' 2>/dev/null | sort | tr '\n' ',')` — mit `DOCKER_AT_START` vergleichen
  - Falls abweichend: WARNING (nicht zwingend von uns verursacht, aber verdächtig)
  - `KILL_SWITCH_AT_END=$(cat var/kill_switch.json 2>/dev/null | jq -r .mode // 'unknown')` — mit Start vergleichen
  - `REFLOG_AT_END=$(git reflog --oneline | wc -l)` — mit Start vergleichen; außer Commit aus Task 1 sollte nichts neu sein
  - Report-Dateien verifizieren: `ls docs/reports/git-branch-cleanup-yellow-triage-*Z.{md,json}` — beide vorhanden
  - JSON-Validierung: `jq . docs/reports/git-branch-cleanup-yellow-triage-*Z.json > /dev/null` exit 0
  - Evidence: `.omo/evidence/task-4-post-flight-verification.md` mit allen Vergleichen + PASS/FAIL-Status

  **Must NOT do**:
  - KEIN `git reset`, `git reflog expire`, `git gc`
  - KEIN Cleanup von untracked Report-Dateien
  - KEIN auto-fix bei Mismatch — nur dokumentieren und User fragen
  - KEIN Überspringen von Checks

  **Recommended Agent Profile**:
  - **Category**: `quick` — feste Check-Liste, klarer Output
  - **Skills**: [`git-master`] für zuverlässige git-State-Inspection

  **Parallelization**:
  - Can Run In Parallel: NO — sequenziell nach Task 3
  - Blocks: F1, F2, F3, F4 (Final Wave)
  - Blocked By: Task 3

  **References**:
  - `.omo/evidence/task-1-preflight-and-commit.md` — hat alle `_AT_START` Werte
  - `.omo/evidence/task-2-branch-data-raw.json` — hat `branch_count_post_fetch`
  - `docs/reports/git-branch-cleanup-yellow-triage-*Z.{md,json}` — zu verifizierende Deliverables

  **Acceptance Criteria**:
  - [ ] `HEAD_AT_END == HEAD_AT_START` (oder dokumentierte User-Aktion zwischenzeitlich)
  - [ ] `BRANCH_COUNT_AT_END == BRANCH_COUNT_AT_START`
  - [ ] `WORKTREE_AT_END` zeigt nur untracked yellow-triage Reports
  - [ ] `DOCKER_AT_END == DOCKER_AT_START` (oder WARNING mit Begründung)
  - [ ] `KILL_SWITCH_AT_END == KILL_SWITCH_AT_START`
  - [ ] Beide Report-Dateien vorhanden
  - [ ] JSON validierbar
  - [ ] Evidence-Datei erstellt mit PASS/FAIL-Übersicht

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Happy Path — Alle Post-flight Checks PASS
    Tool: Bash
    Preconditions: Task 1-3 erfolgreich durchlaufen
    Steps:
      1. `git rev-parse HEAD` → HEAD_AT_END == HEAD_AT_START (aus Task 1 Evidence)
      2. `git branch -r | grep -v HEAD | grep -v "origin/main$" | wc -l` → BRANCH_COUNT_AT_END == BRANCH_COUNT_AT_START
      3. `git status --porcelain` → zeigt nur "?? docs/reports/git-branch-cleanup-yellow-triage-*" Einträge
      4. `docker ps --format '{{.Names}}' | sort | tr '\n' ','` → DOCKER_AT_END == DOCKER_AT_START
      5. `cat var/kill_switch.json | jq -r .mode` → KILL_SWITCH_AT_END == KILL_SWITCH_AT_START
      6. `ls docs/reports/git-branch-cleanup-yellow-triage-*Z.md docs/reports/git-branch-cleanup-yellow-triage-*Z.json` → beide vorhanden
      7. `jq . docs/reports/git-branch-cleanup-yellow-triage-*Z.json > /dev/null` → exit 0
    Expected Result: Alle 7 Checks PASS. Evidence zeigt "POST-FLIGHT: ALL PASS".
    Failure Indicators: HEAD geändert; Branches gelöscht; Worktree modifiziert; JSON invalid; Reports fehlen
    Evidence: .omo/evidence/task-4-post-flight-verification.md

  Scenario: Edge — HEAD hat sich geändert (Critical Failure)
    Tool: Bash
    Preconditions: Während Task 2/3 hat ein anderer Prozess (cron, user, hermes-auto) committed
    Steps:
      1. `git rev-parse HEAD` → HEAD_AT_END ≠ HEAD_AT_START
      2. CRITICAL FAILURE melden
      3. `git log --oneline ${HEAD_AT_START}..HEAD` → zeigt was passiert ist
      4. STOP: KEINE automatische Recovery
      5. User informieren mit Differenz
    Expected Result: Task stoppt mit Critical-Failure-Evidence. User muss entscheiden.
    Failure Indicators: auto-reset versucht; Mismatch stillschweigend ignoriert
    Evidence: .omo/evidence/task-4-critical-head-mismatch.md

  Scenario: Edge — Branch-Count hat sich geändert
    Tool: Bash
    Preconditions: Branches zwischenzeitlich gelöscht (von anderer Session) oder neuer Branch gepusht
    Steps:
      1. `git branch -r | grep -v HEAD | grep -v "origin/main$" | wc -l` → Count ≠ Start-Wert
      2. `git branch -r | grep -v HEAD | grep -v "origin/main$"` → aktuelle Liste
      3. Differenz zu Task 1 erfassen (welche Branches neu/verschwunden)
      4. WARNING ins Evidence (kein ABORT — kann legitime User-Aktion sein)
      5. Report aus Task 3 gilt weiter, aber User muss über Diskrepanz informiert werden
    Expected Result: WARNING dokumentiert. Report unangetastet. User-Review erforderlich.
    Failure Indicators: Branch-Liste stillschweigend verändert; Report überschrieben
    Evidence: .omo/evidence/task-4-branch-count-warning.md
  ```

  **Commit**: NO — Post-flight ist reine Verifikation, keine Repo-Änderung.

---

## Final Verification Wave (nach Task 4 — 4 parallele Reviews, alle müssen APPROVE)

> **Do NOT auto-proceed nach Final Wave.** Präsentiere konsolidierte Ergebnisse an User und fordere explizites "okay" bevor der Plan als abgeschlossen markiert wird.

- [ ] F1. Plan-Compliance-Audit — `oracle`
  Lese diesen Plan Ende-zu-Ende. Für jedes "Must Have": verifiziere dass das Deliverable existiert (Read report file, `git log` für Commit, `git branch -r` für Count). Für jedes "Must NOT Have": durchsuche `git reflog`, `git status`, und Report-Evidence auf verbotene Aktionen — reject mit file:line bei Fund. Vergleiche Deliverables gegen Plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [4/4] | VERDICT: APPROVE/REJECT`

- [ ] F2. Report-Quality-Review — `unspecified-high`
  Lese beide Report-Dateien. Prüfe: alle 51 Branches präsentent, jede Klassifizierung hat `reasoning`, JSON validierbar mit `jq`, Markdown rendert sauber, keine truncation in kritischen Feldern, Schema-Konformanz (siehe Task 3).
  Output: `Branches [51/51] | Classifications [51/51] | JSON valid | MD valid | VERDICT`

- [ ] F3. Manual Spot-Check — `unspecified-high`
  Wähle 5 zufällige Branches aus dem Report. Für jeden: re-führe `git log --oneline origin/<branch> --not origin/main` und `git diff --stat origin/main..origin/<branch>` aus, vergleiche mit Report-Eintrag. Stimmen ahead-count und changed-file-count? Ist die Klassifizierung nachvollziehbar?
  Output: `Spot-Checks [5/5 pass] | Mismatches [list] | VERDICT`

- [ ] F4. Scope-Fidelity-Check — `deep`
  Vergleiche Task 1 "What to do" mit `git log --oneline -3` (welche Commits wurden gemacht?). Vergleiche mit `git diff HEAD~1..HEAD --stat` (welche Files?). Verifiziere 1:1 — nur docs/reports/git-branch-cleanup-* committed, nichts anderes. Prüfe `git status` clean außer untracked Reports. Prüfe `docker ps` unverändert, kill-switch-status unverändert.
  Output: `Commit compliant | Worktree clean | Runtime untouched | VERDICT`

---

## Commit Strategy

- **Task 1 Commit**: `docs(git): add branch cleanup reconciliation reports`
  - Dateien: alle untracked unter `docs/reports/git-branch-cleanup-*` (Preflight, Delete-Green, Post-Green-Mini-Preflight)
  - Pre-commit: `git status --short` (verify nothing else staged)
  - **KEIN** `git add .` — nur explizite Pfade
- **Tasks 2–4**: KEINE weiteren Commits. Neue Report-Dateien bleiben untracked bis zur nächsten Beauftragung.

---

## Success Criteria

### Verification Commands

```bash
# Branch-Count unverändert
git branch -r | grep -v "HEAD" | grep -v "origin/main$" | wc -l
# Expected: 51

# HEAD unverändert (dynamischer Pin — vergleiche mit Task 1 Start-Wert)
git rev-parse HEAD
# Expected: identisch zu Task 1 recorded HEAD

# Report-Dateien vorhanden
ls docs/reports/git-branch-cleanup-yellow-triage-*Z.md
ls docs/reports/git-branch-cleanup-yellow-triage-*Z.json

# JSON valide
jq . docs/reports/git-branch-cleanup-yellow-triage-*Z.json > /dev/null
# Expected exit code: 0

# Worktree clean außer untracked new reports
git status --short
# Expected: nur ?? docs/reports/git-branch-cleanup-yellow-triage-* Einträge

# Keine Runtime-Touches (docker, kill-switch)
docker ps --format "table {{.Names}}\t{{.Status}}" | wc -l
# Expected: unverändert zu Task 1 Start-Count
cat var/kill_switch.json 2>/dev/null | jq -r .mode
# Expected: unverändert zu Task 1 Start-Wert
```

### Final Checklist

- [ ] Alle 51 Branches klassifiziert im Report
- [ ] 2 Gap-Audit-Branches als `KEEP_ACTIVE` oder `NEEDS_MANUAL_REVIEW`
- [ ] 0 Branches gelöscht
- [ ] HEAD unverändert (Start = Ende)
- [ ] Bericht-Dateien vorhanden und valide
- [ ] JSON-Schema konform (siehe Task 3)
- [ ] keine Runtime/Docker/Freqtrade/SI v2/cron/config-Touches
- [ ] keine `git gc`, `git prune`, reflog-Cleanup
- [ ] kein Checkout während Triage
- [ ] F1–F4 alle APPROVE
- [ ] User hat explizites "okay" gegeben

---

## Anhang A: Original Hermes-Agent-Prompt (User-Spec)

> Der folgende Prompt wurde vom User ursprünglich für Hermes verfasst. Dieser Plan formalisiert ihn mit expliziten Lücken-Fills, QA-Szenarien und Guardrails. Hermes kann den Prompt direkt nutzen, solange Task 1–4 dieses Plans eingehalten werden.

````
You are operating in the `GoLukeEnviro/trading-hub` repository.

Goal:
Create a read-only YELLOW branch triage report for the 51 remaining remote branches after GREEN_DELETE cleanup.

Context:
- GREEN_DELETE cleanup completed successfully.
- 47 GREEN_DELETE branches were deleted.
- Post-cleanup mini-preflight reconciled the count delta.
- Remaining branches:
  - 49 original YELLOW_COMPARE branches
  - 2 new UNEXPECTED_REMAINING branches:
    - `chore/gap-audit-p0-security-ci`
    - `feat/gap-audit-p246-endpoint-auth`
- No YELLOW branch has been deleted yet.

Strict scope:
- READ-ONLY only.
- Do NOT delete branches.
- Do NOT run git gc.
- Do NOT merge, rebase, reset, force-push, or update refs.
- Do NOT touch Docker, Freqtrade, SI v2 runtime, cron, config, or trading data.
- Do NOT modify source code.
- Do NOT proceed into branch deletion.

Pre-step: persist report artifacts (siehe Task 1 dieses Plans).

Then continue read-only triage.

Triage every remaining remote branch excluding origin/main, origin/HEAD.

For each branch collect: merge-base ancestry, log not-in-main, diff-stat, name-status.

Classify each as: DELETE_CANDIDATE | KEEP_ACTIVE | PR_REQUIRED | SUPERSEDED_BY_MAIN | NEEDS_MANUAL_REVIEW.

Special rules:
- Die 2 Gap-Audit-Branches: HARDCODE KEEP_ACTIVE oder NEEDS_MANUAL_REVIEW, niemals DELETE_CANDIDATE.
- Security/CI/endpoint-auth/SI v2/telemetry/proposal/rainbow/kill-switch/market-data/controller/auth: konservativ behandeln.

Output: docs/reports/git-branch-cleanup-yellow-triage-{timestamp}Z.{md,json}

Stop condition: Wenn untracked files außerhalb docs/reports/git-branch-cleanup-* → STOP, nicht committen, nicht weiterfahren.
````

---

## Anhang B: Environment-Diskrepanz-Notiz

**Beobachtung**: Lokale Windows-Copy (`E:\VS-code-Projekte-5.2025\trading-hub`) zum Zeitpunkt der Plan-Erstellung:
- `HEAD = 42263aaca59449089e5cce66a69e2ee18183cdcb`
- `origin/main = 3fe9221d016f0ce46a5683ebeaf4014cc93d1749`
- Worktree: clean (Reports bereits tracked)

**User-Report (Hermes-Env)** beschreibt:
- `HEAD = ced01d12e5fefb1a44344d858a3800218a0bf969`
- `main == origin/main`

**Auflösung**: Plan verwendet **dynamischen HEAD-Pin** (Task 1 erfasst `HEAD_AT_START`, Task 4 verifiziert `HEAD_AT_END == HEAD_AT_START`). Keine Hardcodierung auf `ced01d1`. Falls das Hermes-Env zwischenzeitlich weitergelaufen ist, ist das in Ordnung — solange sich HEAD während der Triage-Ausführung nicht ändert.

**Falls der Executor den Diskrepanz-Check explizit machen will**: Vor Task 1 `git log --oneline ced01d1..HEAD` ausführen und im Report dokumentieren, was seit dem User-Report passiert ist.
