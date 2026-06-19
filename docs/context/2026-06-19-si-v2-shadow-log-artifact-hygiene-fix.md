# SI v2 Shadow-Log Artifact Hygiene Fix — 2026-06-19

## Scope

Resolve the recurring dirty-worktree blocker caused by generated SI v2 per-bot shadow log JSONL files being tracked in Git while the natural scheduled SI v2 cycle appends to them at runtime.

## Root cause

The active SI v2 runtime writes per-bot shadow logs into a repository path:

- `self_improvement_v2/reports/phase2/shadow_logs/`

Writer path confirmed in:

- `self_improvement_v2/src/si_v2/loop/active_cycle_runner.py`
  - `_SHADOW_LOG_DIR = ... / self_improvement_v2 / reports / phase2 / shadow_logs`
  - `shadow_logger = ShadowLogger(log_dir=_SHADOW_LOG_DIR)`
  - `shadow_logger.log(...)` inside the Step 4 safety path
- `self_improvement_v2/src/si_v2/deploy/shadow_logger.py`
  - `ShadowLogger._write_to_file()` appends to `shadow_{bot_id}.jsonl`

So the dirty-worktree condition was not a runtime bug in SI v2 logic; it was an artifact policy mismatch:

- generated runtime JSONL files existed under a tracked repo path
- those JSONL files were still tracked in Git
- the scheduled cycle appended one new line, producing tracked modifications on `main`

## Baseline blocker

Tracked dirty files at baseline:

- `self_improvement_v2/reports/phase2/shadow_logs/shadow_freqai-rebel.jsonl`
- `self_improvement_v2/reports/phase2/shadow_logs/shadow_freqtrade-regime-hybrid.jsonl`

Tracked files under `self_improvement_v2/reports/phase2/shadow_logs/` before the fix:

- `shadow_freqai-rebel.jsonl`
- `shadow_freqtrade-freqforge-canary.jsonl`
- `shadow_freqtrade-freqforge.jsonl`
- `shadow_freqtrade-regime-hybrid.jsonl`

## Backup

External archive created before any Git index change:

- backup directory: `/opt/data/archive/trading-shadow-log-artifact-hygiene-20260619T130850Z`
- patch: `/opt/data/archive/trading-shadow-log-artifact-hygiene-20260619T130850Z/shadow-log-diff.patch`
- snapshot: `/opt/data/archive/trading-shadow-log-artifact-hygiene-20260619T130850Z/shadow_logs_snapshot/`
- checksums: `/opt/data/archive/trading-shadow-log-artifact-hygiene-20260619T130850Z/SHA256SUMS.txt`

## Policy fix applied

1. Made the ignore intent explicit in `.gitignore`:

- `self_improvement_v2/reports/phase2/shadow_logs/*.jsonl`

2. Removed the four generated shadow log JSONL files from the Git index with `git rm --cached`, preserving them on disk.

No runtime files were deleted from the working tree.

## Fixture / reader conflict check

No test or source file was found that depends on these exact tracked JSONL artifacts as committed fixtures.

Observed dependencies are on:

- the `shadow_logs` directory as a runtime output path
- in-memory `ShadowLogger` usage in proof/test flows
- not on committed copies of the four concrete JSONL files

Therefore no fixture migration was required for this fix.

## Validation summary

- after `git rm --cached`, `git status --short` showed staged index removals (`D`) rather than tracked content modifications (`M`) for the four shadow log files
- a synthetic append to `shadow_freqai-rebel.jsonl` did **not** create a tracked `M` diff for that file
- the synthetic append was then restored from the external backup snapshot
- the shadow log files remained present on disk and ignored

## Operational effect

This change removes the recurring Git hygiene conflict that blocked issue `#279`:

- natural SI v2 scheduled runs may continue appending runtime shadow log JSONL entries on disk
- those appends no longer dirty tracked `main` files
- the repository preflight for the profitability evidence gate can proceed once this fix is committed and merged

## Safety invariants preserved

- no live trading change
- no `dry_run=false`
- no Freqtrade config change
- no strategy change
- no Docker / Compose / service / cron mutation
- no secret-file change
- no secrets printed
- no runtime evidence deleted without backup
