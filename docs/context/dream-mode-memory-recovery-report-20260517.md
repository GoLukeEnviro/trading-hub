> **OUTDATED — CORRECTION 2026-05-17**
> This report incorrectly treats Holographic memory_store.db as the active database.
> The current active memory backend is **Mem0** (cloud API).
> Holographic DBs are legacy/recovered candidates only.
> See `docs/context/mem0-memory-recovery-correction-20260517.md` for corrected analysis.

# Dream Mode Memory Recovery Report

**Date:** 2026-05-17 14:01 UTC
**Run ID:** dream-mode-memory-recovery-20260517
**Status:** READ-ONLY AUDIT COMPLETE — NO MUTATIONS PERFORMED

## Executive Summary

Recovered 4 candidate databases with a total of 3,490 non-active facts.
The active Holographic DB has 380 facts (restored from backup earlier today).
All 3,870 facts across active + candidate DBs have been classified.

**Key findings:**
- Active DB is healthy (integrity ok, FTS match, HRR dim=1024)
- 5 near-duplicate losers identified in active DB (winners selected)
- 536 import candidates from recovered DBs
- 46 facts marked DO_NOT_IMPORT (secrets, test output, legacy)
- Most recovered facts (1413) are duplicates of active DB content
- The pre-dedup import (2,385 facts from 2026-05-14) is mostly raw/undifferentiated

## Active DB Identification

| Attribute | Value |
|-----------|-------|
| Path | `/home/hermes/.hermes/shared-memory/holographic/memory_store.db` |
| Determined by | Dream Mode SKILL.md + Hermes config (HERMES_HOME) |
| Facts | 380 |
| FTS rows | 380 (MATCH) |
| HRR dim | 1024 |
| Integrity | ok |
| Journal mode | wal |
| Restored from | `.bak.20260517` (earlier this session) |

## Candidate DB Inventory

| # | Status | Facts | Size | Path |
|---|--------|------:|-----:|------|
| 1 | ACTIVE | 380 | 64K | memory_store.db (live) |
| 2 | BACKUP | 380 | 3.4M | memory_store.db.bak.20260517 |
| 3 | BACKUP | 371 | 3.4M | dream-mode backup 2026-05-16 |
| 4 | BACKUP | 354 | 3.2M | dryrun/memory_store.dryrun.db |
| 5 | PRE_DEDUP | 2,385 | 1.4M | raw_import_2385facts (2026-05-14) |
| 6-34 | OTHER | 0 | various | tradesv3.sqlite, kanban.db, etc. |

## Classification Summary

| Label | Active DB | Recovered | Total |
|-------|----------:|----------:|------:|
| KEEP_CURRENT | 0 | 0 | 413 |
| KEEP_CURRENT_4D | 107 | 536 | 230 |
| DUPLICATE_BETTER_EXISTS | 5 | 1413 | 1418 |
| REVIEW_REQUIRED | 256 | 1445 | 1701 |
| STALE_ARCHIVE | 7 | 50 | 57 |
| DO_NOT_IMPORT | 5 | 46 | 51 |

## Duplicate Winners (Task 5)

| Group | Loser IDs | Winner | Reason |
|-------|-----------|--------|--------|
| Docker-Host file access | #313, #299 | **#320** | More complete: mentions "ephemeral container" |
| Luke consistency patterns | #68 | **#73** | More specific: names Tailscale→Caddy→Docker pattern |
| Luke structured decisions | #220 | **#167** | More detail: "decision trees, decision matrices, and decision gates" |
| Skill update expectations | #18 | **#200** | Cleaner wording |

## DO_NOT_IMPORT Examples

- **[DO_NOT_IMPORT]** Smoke testing for Hermes projects should import main classes without API keys, p... — Temporary test/debug output: 'smoke test'
- **[DO_NOT_IMPORT]** Luke is a direct communicator who becomes frustrated with fluff, disclaimers, an... — Vague behavioral observation without project-specific utility
- **[DO_NOT_IMPORT]** User prefers seeing proposed code changes for review BEFORE they are applied — e... — Vague behavioral observation without project-specific utility
- **[DO_NOT_IMPORT]** Smoke testing for Hermes projects should import main classes without API keys, p... — Temporary test/debug output: 'smoke test'
- **[DO_NOT_IMPORT]** Luke is a direct communicator who becomes frustrated with fluff, disclaimers, an... — Vague behavioral observation without project-specific utility
- **[DO_NOT_IMPORT]** User prefers seeing proposed code changes for review BEFORE they are applied — e... — Vague behavioral observation without project-specific utility
- **[DO_NOT_IMPORT]** Luke prefers Feather format, 15-minute candle timeframe, hierarchical skill orga... — Vague behavioral observation without project-specific utility
- **[DO_NOT_IMPORT]** Luke prefers Feather format for storing time-series data... — Vague behavioral observation without project-specific utility

## Import Candidates from Recovered DBs

536 facts from non-active DBs are labeled KEEP_CURRENT or KEEP_CURRENT_4D.

These are new facts NOT already in the active DB that reference current architecture.
- **[KEEP_CURRENT]** (conf=0.75) Luke’s message specifies that the original behaviour and configuration of PrimoA...
- **[KEEP_CURRENT]** (conf=0.75) Luke’s success criteria state that the RSI bot must not open new trades while qu...
- **[KEEP_CURRENT]** (conf=0.75) Session-specific task narratives like 'summarize today's market' are not general...
- **[KEEP_CURRENT]** (conf=0.75) Infrastructure access limitations such as sandbox isolation or port binding must...
- **[KEEP_CURRENT]** (conf=0.75) `PATCH /v3/workspaces/{workspace}/peers/{peer_id}` returns `405 Method Not Allow...
- **[KEEP_CURRENT]** (conf=0.75) Luke prefers deep data-driven research and backtest validation before deployment...
- **[KEEP_CURRENT]** (conf=0.75) Luke prefers deep data-driven research and backtest validation before deployment...
- **[KEEP_CURRENT]** (conf=0.75) `writeFrequency: "async"` must never be used on systems with long-running sessio...
- **[KEEP_CURRENT]** (conf=0.75) Luke insists on deep data-driven research and backtesting validation prior to an...
- **[KEEP_CURRENT]** (conf=0.75) Luke requires deep data-driven research and backtest validation before deploymen...

... and 526 more. See manifest JSON for full list.

## Recommended Next Step

1. **Safe: Mark 5 duplicate losers** in active DB (trust_score → 0.1, tag superseded)
2. **Optional: Import 536 KEEP candidates** from recovered DBs using MemoryStore.add_fact()
3. **Skip: 46 DO_NOT_IMPORT**, 50 STALE_ARCHIVE, 1413 duplicates
4. **Review: 1445 REVIEW_REQUIRED** items need manual check before deciding

## GO / NO-GO Decision

| Decision | Condition | Status |
|----------|-----------|--------|
| GO (safe cleanup) | Duplicate losers marked, no data loss | **READY** |
| GO (import) | Import candidates reviewed by Luke | **NEEDS REVIEW** |
| NO-GO (bulk merge) | Raw import (2385 facts) undifferentiated | **BLOCKED** |

## Files Written

| File | Purpose |
|------|---------|
| `docs/context/dream-mode-memory-recovery-manifest-20260517.json` | Full classification manifest (3,870 items) |
| `docs/context/proposed-memory-recovery-labels-20260517.sql` | Proposed SQL (NOT EXECUTED) |
| `docs/context/dream-mode-memory-recovery-report-20260517.md` | This report |

## Safety Confirmation

- [x] No destructive mutation performed
- [x] Every candidate DB inventoried (34 DBs)
- [x] Active DB identified from config/runtime evidence
- [x] Every reviewed fact has exactly one label
- [x] Last-5-days filter applied
- [x] Last-4-days stricter flag applied
- [x] Duplicate groups resolved by best-version selection
- [x] JSON manifest exists
- [x] Markdown report exists
- [x] SQL is only proposed, not executed
