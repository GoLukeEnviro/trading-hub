# Context Archive

`docs/context/` is the append-only historical record for Trading Hub.
It stores incident write-ups, migration notes, cleanup reports, audit findings,
validation summaries, and other time-stamped context that explains how the repo
arrived at its current state.

## What belongs here

- Incident reports and remediation notes
- Migration and bootstrap summaries
- Audit and validation reports
- Cleanup reports and post-phase summaries
- Dashboard surface audits, external access notes, and UI gap analyses
- Temporary context that later becomes historical reference

## What does not belong here

- Secrets or credentials
- Runtime state, databases, logs, or inspect dumps
- Backup archives
- Live trading configuration changes without review
- Generated noise that is only useful locally

## Relationship to the rest of the docs

- `../README.md` is the repo overview.
- `../AGENTS.md` is the agent safety and architecture guide.
- `../SOUL.md` is the project identity.
- `../state/current-operational-state.md` is the current validated snapshot.

## Naming convention

Use date-stamped filenames so the trail stays sortable and reviewable.
Examples:

- `incident-name-20260521.md`
- `cleanup-report-20260521.md`
- `migration-note-20260521T122400Z.json`

## Local-only staging folders

The following folders are used only for local cleanup or migration work and are
kept out of Git by `.gitignore`:

- `git-cleanup-snapshots/`
- `memory-migration-staging/`
