# Final Repo Cleanup and Docs Refresh — 20260521

**Date:** 2026-05-21 12:24 UTC
**Scope:** Safe documentation alignment, ignore-rule hardening, and dirty-worktree classification
**Verdict:** READY_FOR_SAFE_COMMIT

## Summary

This pass aligns the main repository docs with the current dry-run-only safety posture,
adds ignore rules for local/runtime artifacts, and separates the remaining dirty files
into safe-to-commit docs versus review-only strategy/research/runtime material.

## Files refreshed in this pass

- `README.md`
- `AGENTS.md`
- `SOUL.md`
- `docs/README.md`
- `docs/context/README.md`
- `docs/state/current-operational-state.md`
- `freqtrade/shared/README.md`
- `.gitignore`

## Dirty-file classification

| Group | Category | Reason | Recommended action |
|-------|----------|--------|--------------------|
| `README.md`, `AGENTS.md`, `SOUL.md`, `docs/README.md`, `docs/context/README.md`, `docs/state/current-operational-state.md`, `freqtrade/shared/README.md`, `docs/context/final-repo-cleanup-and-docs-refresh-20260521.md`, `.gitignore` | `commit_now` | Central repo documentation and ignore-rule updates; no secrets or live-trading activation. | Stage by explicit path and commit together. |
| `.hermes/`, `events/`, `proposals/`, `shared/hermes_signal.json`, `freqtrade/shared/*state*.json`, `freqtrade/shared/*.lock`, `freqtrade/shared/fleet_correlation_matrix.json`, `freqtrade/bots/*/user_data/primo_signal_state.json`, `freqtrade/bots/*/user_data/signals/`, `freqtrade/bots/regime-hybrid/config/research/automation/latest_*.json`, `freqtrade/bots/regime-hybrid/config/research/automation/*_events.jsonl`, `freqtrade/bots/regime-hybrid/config/research/automation/*_state.json`, `orchestrator/config/cron_jobs_backup.json`, `docs/context/git-cleanup-snapshots/`, `docs/context/memory-migration-staging/` | `ignore_only` | Local/runtime/generated noise, local cleanup snapshots, and transient state that should not be versioned. | Keep ignored via `.gitignore`; do not stage. |
| `AGENTS.md.backup.202605162244`, `freqtrade/shared/fleet_risk_manager.py.bak-20260521T095036Z`, `freqtrade/shared/trading_pipeline.py.bak-20260521T095036Z`, `**/*.bak`, `**/*.bak-*`, `*.backup.*`, `orchestrator/backups/` | `archive_local` | Backups and rollback material retained for safety, not source of truth. | Keep locally archived; do not commit. |
| `freqforge-canary/user_data/strategies/FreqForge_Override.py`, `freqforge/user_data/strategies/FreqForge_Override.py`, `freqtrade/bots/regime-hybrid/user_data/strategies/RegimeSwitchingHybrid_v7_v04_Integration.py`, `freqtrade/bots/regime-hybrid/config/`, `freqtrade/bots/regime-hybrid/user_data/strategies/research_regime_hybrid_sideaware_v1.py`, `freqtrade/bots/regime-hybrid/user_data/strategies/research_regime_hybrid_sideaware_v2.py`, `freqtrade/bots/regime-hybrid/user_data/strategies/research_regime_hybrid_sideaware_v3.py`, `orchestrator/scripts/*.py`, `orchestrator/scripts/*.sh`, `freqtrade/shared/calculate_correlation_matrix.py`, `freqtrade/shared/fleet_watcher.py`, `freqtrade/shared/run_fleet_watcher.sh`, `freqtrade/shared/update_fleet_equity.py` | `needs_user_review` | Strategy, research, and operational code can affect trading behavior or automation behavior; not safe to auto-commit without classification. | Leave uncommitted until reviewed and explicitly approved. |
| `docs/GAP-REPORT-2026-05-16.md`, `docs/bridge-plan-v0.1.md`, `docs/gap-report-20260516.md`, `docs/gap-report-20260517.md`, `docs/context/*.md`, `docs/context/*.json`, `docs/context/*.sql` (historical reports and migration artifacts) | `needs_user_review` | Historical context is valuable, but these items are archival records rather than current-state docs. | Review separately for archival commits; keep out of the safe cleanup commit. |

## What changed in the docs

- README now states the repo is dry-run only and documents the core component map.
- AGENTS now emphasizes explicit-path staging, no destructive cleanup, and docs/context updates.
- SOUL now focuses on project identity, safety-first automation, and research/runtime separation.
- `docs/README.md` and `docs/context/README.md` now explain canonical vs historical documentation.
- `docs/state/current-operational-state.md` now reflects the latest documented snapshot and points back to the cleanup report.
- `freqtrade/shared/README.md` now documents the FleetRisk shared-state layer and watcher behavior.
- `.gitignore` now covers local cleanup snapshots, runtime state, shared signal files, and backup noise.

## Remaining intent

- Commit only the safe documentation and ignore-rule updates.
- Leave strategy/research/ops code uncommitted until explicitly reviewed.
- Keep local backups and cleanup snapshots out of Git.

## Next action

Stage the explicit safe paths only, verify `git diff --cached`, and then decide whether the
review-only code/research buckets should stay local or be split into a separate review branch.
