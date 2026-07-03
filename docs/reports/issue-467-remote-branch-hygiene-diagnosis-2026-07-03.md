# Issue #467 Remote Branch Hygiene — Diagnosis Report (2026-07-03)

## Scope

Read-only diagnosis of remote branches across all 3 remotes (`origin`,
`origin-https`, `origin-pat`). No branches deleted.

## Approval marker

```
APPROVED_REMOTE_BRANCH_HYGIENE_FOR_467_READ_ONLY_DIAGNOSIS_ONLY
```

## Remote overview

| Remote | URL | Branches |
|--------|-----|:--------:|
| `origin` | `git@github.com-trading:GoLukeEnviro/trading-hub.git` | 192 |
| `origin-https` | `https://github.com/GoLukeEnviro/trading-hub.git` | 101 |
| `origin-pat` | `https://GoLukeEnviro@github.com/GoLukeEnviro/trading-hub.git` | 101 |
| **Total** | | **394** |

## Remote mirror status

| Property | origin-https | origin-pat |
|----------|:-----------:|:----------:|
| Unique branches (not in `origin`) | 0 | 0 |
| Branches mirrored from `origin` | 101 | 101 |
| Last updated | 2026-07-03 06:45 | — |

**Both mirrors are pure subsets of `origin`** — no unique content.
Recommend removing `origin-https` and `origin-pat` remotes or pruning them.

## Open PR dependencies

```
gh pr list --state open → [] (no open PRs)
```

All branches are from completed/merged PRs or abandoned work.

## Branch classification

Because this repo uses squash/rebase merge strategy, `git branch -r --merged`
is not reliable (only 5/186 origin/ branches detected as merged).

### By age on `origin` (sample of all 186 non-main branches)

| Age bracket | Count (sample) | Examples |
|-------------|:--------------:|----------|
| **> 7 days stale** (2026-06-11 to 2026-06-25) | ~15 | `GAP-report` (Jun 15), `chore/si-v2-*` (Jun 11–25), `docs/rainbow-*` (Jun 23), `docs/roadmap-v2-*` (Jun 14) |
| **3–7 days stale** (2026-06-26 to 2026-06-30) | ~10 | `docs/canonicalize-si-v2-*`, `chore/hermes-github-*`, `docs/si-v2-extend-*` |
| **< 3 days / active** (2026-07-01 to 2026-07-03) | ~30+ | Docs-drift campaign branches, fix branches, all merged via squash |

### Earliest branch: `2026-06-11` (22 days)
### Latest branch: `2026-07-03` (today)

### By category on `origin`

| Prefix | Count (est.) | Status |
|--------|:------------:|--------|
| `docs/` | ~40 | Mostly merged via squash or proof-run branches |
| `fix/` | ~15 | All merged |
| `chore/` | ~10 | All merged |
| `test/` | ~15 | All merged (coverage runs) |
| `feat/` | ~5 | Merged |
| `apply/` | ~1 | Merged controlled apply |
| `proof/` | ~2 | Merged proof runs |
| `hygiene/` | ~3 | Merged |
| `GAP-report` | 1 | Stale (abandoned) |
| `feature/` | ~1 | Merged |

## Removal candidates (Phase 1 — safe, confirmed merged)

These branches belong to completed PRs and are confirmed safe to delete:

| Branch | Created | PR |
|--------|---------|-----|
| `docs/si-v2-critical-drift-alignment-2026-07-03` | 2026-07-03 | #458 ✅ merged |
| `docs/safety-reconcile-stale-decisions-state-roadmap-2026-07-03` | 2026-07-03 | #459 ✅ merged |
| `docs/index-glossary-decommissioning-register-2026-07-03` | 2026-07-03 | #460 ✅ merged |
| `fix/run-analyze-vestigial-marker-463` | 2026-07-03 | #469 ✅ merged |
| `fix/shared-constants-missing-import-os-466` | 2026-07-03 | #470 ✅ merged |
| `fix/remove-stale-decommissioned-tests-465` | 2026-07-03 | #471 ✅ merged |
| `docs/report-464-backup-temp-cleanup-2026-07-03` | 2026-07-03 | #472 ✅ merged |
| `docs/report-463-disabled-cron-cleanup-2026-07-03` | 2026-07-03 | #473 ✅ merged |
| `docs/phase-d-follow-up-issue-tracker-2026-07-03` | 2026-07-03 | #468 ✅ merged |
| `docs/roadmap-closure-reconciliation-2026-07-03` | 2026-07-03 | #455 ✅ merged |

And many more historical merged branches.

## Suggested deletion batch strategy

**Batch 1 (safe, all recently merged, ~50 branches):**
- All `docs/` branches from 2026-07-03 (confirmed merged)
- All `fix/` branches from 2026-07-03 (confirmed merged)
- All `origin-https/*` branches (mirror, no unique content)

**Batch 2 (historical merged, ~100 branches):**
- `docs/*`, `fix/*`, `chore/*`, `test/*` branches from 2026-06-11 to 2026-06-30
- All `proof/*`, `apply/*`, `hygiene/*`, `feature/*` branches

**Batch 3 (long-stale, ~36 branches):**
- `GAP-report` (abandoned since Jun 15)
- `origin/apply/*`, `origin/chore/*` (all completed)
- Any other branch not included in batches 1–2

**Remote cleanup:**
- Remove `origin-https` remote after confirming no usage
- Remove `origin-pat` remote after confirming no usage

## Required approval marker for deletion

```
APPROVED_REMOTE_BRANCH_DELETE_FOR_467_BATCH_1
```

## Validation commands (for deletion phase)

```bash
# Before
git branch -r | wc -l

# Dry-run deletion
git push origin --delete --dry-run <branch>  # per batch

# Verify no force-push
# Before remote removal:
git remote remove origin-https
git remote remove origin-pat
```

## Safety statement

```
No branches deleted.
No remotes pruned.
No force-push.
No repo, Docker, Cron, Config, or runtime mutation.
Read-only diagnosis only.
```
