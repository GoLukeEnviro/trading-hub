# Tracked Backup Artifact Cleanup — 2026-05-21

## Context

Follows recovery commits b6530c3 and d451819 on branch
`chore/final-docs-and-worktree-cleanup`.

## Files Removed from Git Tracking

| File | Size | Date |
|------|------|------|
| RegimeSwitchingHybrid_v2.py.bak_20260503_022741 | 5.5K | 2026-05-03 |
| RegimeSwitchingHybrid_v6_1_Fett.py.bak_v04_integration | 11K | 2026-05-10 |
| RegimeSwitchingHybrid_v6_Stable.json.bak-shadow-fix-phase25b2 | 689B | 2026-05-03 |

All 3 files are preserved on disk. Only git tracking was removed (`git rm --cached`).

## .gitignore Hardening

Added `**/*.bak_*` pattern to `.gitignore` (line 84). The existing `**/*.bak`
and `**/*.bak-*` patterns already covered the other two naming conventions,
but `bak_` was missing. Future backup files with any of these suffixes will
be automatically ignored.

## What Was NOT Changed

- No strategy logic was modified.
- No runtime state files were touched.
- No local files were deleted.
- Token history remains unresolved — see below.

## Token History Status

The hardcoded Anthropic token removed from `optimize_loop.py` in commit b6530c3
still exists in git history (commits 801ff86 through 3037ea7).

**This cleanup does NOT fix the secret history.**

Required follow-up:
1. Rotate the token at the z.ai/Anthropic provider immediately
2. Schedule `git filter-repo` to purge the token blob from history
3. Force-push to origin after filter-repo (requires coordination)

## Untracked Clutter

~72 untracked files remain classified but not destructively cleaned:
- 38 docs_history (context notes)
- 17 operational_scripts (orchestrator/scripts/*.py)
- 12 research_artifacts (regime-hybrid sideaware research)
- 4 freqtrade_shared_ops (fleet_watcher, etc.)
- 2 runtime_artifacts (freqforge primo_signal_state.json)

These are safe to leave untracked. They will not appear in diffs or commits.

**Date:** 2026-05-21
**Branch:** chore/final-docs-and-worktree-cleanup
**Commits:** b6530c3, d451819
