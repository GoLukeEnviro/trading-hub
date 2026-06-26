# Hermes Memory Curation — User Profile Pass — 2026-06-15 12:06 UTC

## Status

Status: OK  
Operation Level: L2 — safe user-profile memory compaction only.

## Scope

Curated the active orchestrator USER PROFILE (internal Hermes store, not a
filesystem file). No trading runtime, Docker, Freqtrade, or credential mutation.

## Dup Check Result

Cross-referenced all 6 MEMORY entries against all 5 USER PROFILE entries.
**No shared lines >30 characters were found.** After the first curation pass
(which removed the duplicate `Trading Hub runtime mutations` from memory),
the two stores have clean separation:

- USER PROFILE: user preferences, communication style, workflow rules
- MEMORY: operational facts, tool paths, architecture decisions, CI quirks

## User Profile Shortening

| # | Before | After | Saved |
|---|--------|-------|-------|
| UP1 | 127 | 77 | -50 |
| UP2 | 231 | 162 | -69 |
| UP3 | 157 | 127 | -30 |
| UP4 | 281 | 155 | -126 |
| UP5 | 243 | 134 | -109 |

All semantic content preserved; wording compressed without loss.

## Final Footprint

| Store | Chars | Limit | Usage | Entries |
|-------|-------|-------|-------|---------|
| MEMORY | 1,083 | 2,200 | 49% | 6 |
| USER_PROFILE | 700 | 1,375 | 50% | 5 |

Combined headroom: ~1,792 chars free across both stores.

## Safety Notes

- No duplicates remain between MEMORY and USER_PROFILE.
- No secret values added or printed.
- User-profile-only facts (research style, Klare Ansage, ai4trade-bot,
  repo hygiene, git workflow) remain in USER_PROFILE.
- Operational facts (Docker host, gh CLI path, fleet rule, roadmap,
  CI quirks, Honcho status) remain in MEMORY.
