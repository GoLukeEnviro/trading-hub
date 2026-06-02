# Memory Cleanup Baseline — 2026-06-02

**Established:** 2026-06-02T14:30Z
**Purpose:** Stable reference point for future memory quality comparisons.

## Final State

| Metric | Value |
|--------|-------|
| Memory count | 978 |
| Active quality estimate | ~96% |
| Backfill noise rate (48h dry-run) | 0% |
| Hygiene monitor | Active, read-only, daily 06:00 UTC |
| UUID-only guardrail | Active in both scripts |

## Quality Trajectory

```
1166 (initial)  →  1058 (reject cleanup)  →  1039 (incident recovery)  →  978 (quarantine cleanup)
  84% quality        93% quality              94% quality                  96% quality
```

## Guardrail Status

```
MEMORY_MUTATION_UUID_ONLY_GUARD_ACTIVE
```

Enforced in:
- `/opt/data/profiles/orchestrator/scripts/memory_hygiene_monitor.py` — READ-ONLY, reports only
- `/opt/data/profiles/orchestrator/scripts/memory_backfill.py` — stores via explicit classification, never search

**Permanent rule:** Memory mutations (delete, rewrite, quarantine) MUST use explicit UUID
allowlists only. Semantic search results MUST NEVER be accepted as deletion targets.

## Active Monitors

| Monitor | Cron ID | Schedule | Type |
|---------|---------|----------|------|
| Memory Backfill | 03ab84100557 | `0 */2 * * *` | Write (filter-hardened) |
| Memory Hygiene | e889146fa17a | `0 6 * * *` | Read-only |

## Incident Lessons (2026-06-02)

1. **Never delete by semantic search.** A restore dry-run test searched for
   "RESTORE_DRY_RUN_TEST" and got 20 semantically similar memories. All 20
   were deleted without ID verification. Recovery possible because equivalent
   versions existed, but procedural failure.

2. **Restore test markers must be unique.** "RESTORE_DRY_RUN_TEST" semantically
   overlaps with genuine memories about testing, restoring, backups. Future
   tests must use UUID-verified markers: write → get ID → delete by ID.

3. **UUID allowlists are the only safe deletion method.** This rule is now
   codified as `MEMORY_MUTATION_UUID_ONLY_GUARD_ACTIVE` in all memory scripts.

## Remaining Review Queue

All P3/P4 — no urgency, no action without explicit user request.

| Priority | Category | Count | Action When |
|----------|----------|-------|-------------|
| P3 | 14 remaining quarantine (KEEP + UNCERTAIN) | 14 | Next deep-dive review |
| P3 | 56 UNCERTAIN "User states/reports/notes" | 56 | When contamination recurs |
| P3 | 19 REWRITE_AS_CANONICAL | 19 | Cosmetic rewrite opportunity |
| P4 | DeprecationWarning: datetime.utcfromtimestamp | 1 | Next script update |

### Hygiene Monitor 19 Hits
These are NOT new contamination. They are known "User states/reports/notes" memories
containing operational terms ("cron job", "bind mount"). They remain in the
UNCERTAIN queue. Next hygiene run should expect ~19 baseline hits from these.

## Future Review Rules

1. Any memory cleanup MUST follow this sequence:
   - Phase 1: Preflight (backup verify, UUID list verify, count verify)
   - Phase 2: Dry run (classify by UUID, verify no wrong-class items)
   - Phase 3: Execute (UUID-only deletion, one-by-one, logged)
   - Phase 4: Post-validation (count check, untouched verification)
   - Phase 5: Documentation

2. Abort conditions (hard stop):
   - UUID count does not match expected
   - Backup is missing or unreadable
   - Any UNCERTAIN or KEEP item is in deletion list
   - Mem0 API health check fails

3. No memory mutation during documentation or monitoring tasks.

4. Hygiene monitor baseline: expect ~19 operational hits from User-states
   pattern. Alert only if hits exceed 25 or new categories appear.

## Backup Artifacts

| File | Purpose |
|------|---------|
| `backups/20260602T140123Z-memory-cleanup-manifest.json` | Full manifest with all 184 items |
| `backups/20260602T140226Z-reject-ids-full.txt` | 107 REJECT UUIDs |
| `backups/20260602T140226Z-quarantine-ids-full.txt` | 77 original QUARANTINE UUIDs |
| `backups/20260602T-phase7-delete-candidate-uuids.txt` | 61 final DELETE_CANDIDATE UUIDs |

Path prefix: `/opt/data/profiles/orchestrator/skills/maintenance/dream-mode/backups/`

## Recommended Git Commit

```
docs: memory cleanup baseline and reports

- memory-system-recovery-20260602.md: root cause, filter hardening, 107 deletions
- memory-cleanup-post-validation-20260602.md: backup audit, quarantine review
- memory-final-uuid-cleanup-20260602.md: 61 UUID-based deletions, guardrail
- memory-cleanup-baseline-20260602.md: stable reference for future comparison
```

Files to stage (relative to repo root):
```
docs/context/memory-system-recovery-20260602.md
docs/context/memory-cleanup-post-validation-20260602.md
docs/context/memory-final-uuid-cleanup-20260602.md
docs/context/memory-cleanup-baseline-20260602.md
```

Do NOT stage backup UUID files or modified scripts (memory_backfill.py,
memory_hygiene_monitor.py) without separate explicit approval.
