# Branch-Hygiene: Bereinigungsaktion 2026-07-11/12

## Ausgangslage

Das Repository hatte sich über Monate SI-v2-Entwicklung (280+ gemergte PRs) auf **175
Remote-Branches** und **5 lokale Branches** angesammelt, obwohl aktiv nur `main` gepflegt
wird. Grundursache: `delete_branch_on_merge` stand auf `false`, GitHub räumte Branches nach
Merge nicht automatisch auf.

## Durchgeführte Aktion

### Lokal (3 gelöscht)
- `chore/gitignore-local-artifacts` — Inhalt via Squash-Merge (#361) bereits in `main`
- `GAP-report` — Inhalt via anderem Commit-Hash bereits in `main`
- `backup/local-commits-2026-06-15` — beide Commits inhaltlich bereits im Repo vorhanden
  (einer in `main`, Reports bereits als `docs/reports/*.json`)

Verbleibend: `main`, `refactor/active-cycle-runner-auth-simplify` (aktive Arbeit).

### Remote (154 gelöscht, von 175 auf 22 reduziert)
- **139 Branches** mit gemergtem PR (Abgleich über `gh pr list --state merged`, da die
  meisten Merges Squash-Merges waren und `git branch --merged` diese nicht erkennt)
- **15 weitere Branches** ohne (bzw. mit inkonsistent erkanntem) PR-Status, nach Einzelprüfung:
  12 hatten nie einen PR, 3 waren tatsächlich gemergt

**Wichtiger Zwischenbefund während der Ausführung:** Eine erste grobe Klassifizierung
("hat PR vs. hat keinen PR") reichte nicht aus. Eine erneute Einzelprüfung unmittelbar vor
der zweiten Löschrunde (`gh pr list --state all --search "head:<branch>"` pro Branch) ergab,
dass von 33 vermeintlich "PR-losen" Branches tatsächlich **18 einen geschlossenen, nicht
gemergten PR hatten** — diese wurden gemäß Entscheidung unten **nicht gelöscht**, sondern nur
dokumentiert (siehe Abschnitt "Erhaltene Branches — verworfene Arbeit").

### Root-Cause-Fix
`delete_branch_on_merge` wurde auf `true` gesetzt
(`gh api repos/GoLukeEnviro/trading-hub -X PATCH -f delete_branch_on_merge=true`).
GitHub löscht künftig den Head-Branch automatisch bei jedem PR-Merge (Squash, Merge-Commit
oder Rebase). Verifiziert: `gh api repos/GoLukeEnviro/trading-hub --jq '.delete_branch_on_merge'` → `true`.

## Aktueller Stand nach Bereinigung

**Remote (22 Branches):**
- `main`
- 2 offene PRs (unangetastet): `feat/r7a-hermestrader-dryrun-topology` (#519),
  `test/r7a-compose-contract-registry-sot` (#520)
- `codex/rainbow-contract-companion` — automatisch generierter Agent-Branch (Codex/Copilot),
  Commit vom 2026-07-10, kein PR. Status ungeklärt, bewusst nicht gelöscht. Separat mit Luke
  klären, ob/wann er entfernt werden kann.
- 18 Branches mit geschlossenem, nicht gemergtem PR (siehe unten)

**Lokal (2 Branches):** `main`, `refactor/active-cycle-runner-auth-simplify`

## Erhaltene Branches — verworfene Arbeit (bewusst nicht gelöscht)

Diese 18 Remote-Branches haben einen **geschlossenen, aber nicht gemergten** PR. Der Code
ist im PR-Verlauf auf GitHub dauerhaft nachvollziehbar; der Branch selbst wurde auf
ausdrücklichen Wunsch erhalten, falls einzelne PRs versehentlich geschlossen wurden oder der
Code später doch noch gebraucht wird:

| Branch | Hinweis |
|---|---|
| `docs/phase-c-runbook` | |
| `docs/si-v2-branch-hygiene-report` | frühere Branch-Hygiene-Inventur (#46) |
| `docs/si-v2-issue-38-telegram-conflict-rca` | |
| `docs/si-v2-issue-39-watchdog-connectivity` | |
| `docs/si-v2-live-readiness-burndown-280` | |
| `docs/si-v2-scheduled-cycle-proof-before-apply` | |
| `docs/si-v2-watchlist-no-proposal-diagnosis` | |
| `feat/kill-switch-drawdown-cron` | |
| `feat/kill-switch-pipeline-wiring` | |
| `feat/si-v2-143-154-planning-automation-quality` | |
| `feat/si-v2-issue-143-147-149-planning-automation` | |
| `feat/si-v2-phase2-evidence-input-pipeline` | |
| `feat/si-v2-t4-close-watcher` | |
| `feat/signal-generator-config-driven-pair-universe-2026-06-27` | |
| `feat/stale-evidence-gate-2026-07-03` | |
| `feature/riskguard-pair-universe-expansion` | |
| `test-191-failing-check` | Branch-Protection-Testartefakt |
| `test/coverage-80-sprint` | |

Falls diese Liste zu einem späteren Zeitpunkt weiter bereinigt werden soll: pro Branch den
zugehörigen PR-Titel/-Grund prüfen (`gh pr list --state all --search "head:<branch>"`) und
gezielt entscheiden, nicht pauschal löschen.

## Konvention für die Zukunft

- `delete_branch_on_merge = true` ist jetzt aktiv — neue Feature-Branches werden nach PR-Merge
  automatisch entfernt, keine manuelle Nacharbeit mehr nötig.
- Lokale Branches nach `git pull` regelmäßig manuell aufräumen:
  ```bash
  git fetch origin --prune
  git branch --merged main | grep -v '^\*\|main' | xargs -r git branch -d
  ```
- **Keine automatisierte Wiederholung dieser Aktion ist geplant.** Dies war eine einmalige
  Bereinigung, kein wiederkehrender Cron-/CI-Prozess. Sollte sich erneut ein großer Rückstand
  ansammeln, kann dieses Dokument als Vorlage für eine erneute manuelle Aktion dienen.

## Verifikation

- `git branch -r | grep -v HEAD | wc -l` → 22 (vorher 175)
- `git branch | wc -l` → 2 (vorher 5)
- `gh api repos/GoLukeEnviro/trading-hub --jq '.delete_branch_on_merge'` → `true`
- `gh pr view 519 --json headRefName,state` und `gh pr view 520 --json headRefName,state`
  bestätigen, dass beide offenen PR-Branches nicht versehentlich gelöscht wurden
- SHA-Backup aller Ausgangs-Branches liegt vor der Aktion vor (`git ls-remote origin
  'refs/heads/*'`, 176 Einträge, lokal gesichert) — ermöglicht Rollback per
  `git push origin <sha>:refs/heads/<branch-name>` falls nötig
