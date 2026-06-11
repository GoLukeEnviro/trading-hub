# Phase 0 — Branch & PR Hygiene Inventory Report

**Date:** 2026-06-11 (updated)
**Repo:** GoLukeEnviro/trading-hub
**Report ref:** issue #46

---

## 1. Open Pull Requests

| # | Title | Branch | Status | Mergeable | Classification |
|---|-------|--------|--------|-----------|----------------|
| 69 | [SI v2] Design Telegram approval live adapter with token isolation (#25) | `docs/si-v2-issue-25-telegram-approval-design` | OPEN | MERGEABLE | **Still valid** — design doc, needed before implementation |
| 70 | [SI v2] Design cron activation ceremony and jobs.json guardrails (#26) | `docs/si-v2-issue-26-cron-activation-ceremony` | OPEN | MERGEABLE | **Still valid** — design doc, needed before timer activation |
| 71 | [SI v2] Plan v1 residue archive and migration closure (#27) | `docs/si-v2-issue-27-v1-residue-closure` | OPEN | MERGEABLE | **Still valid** — cleanup plan, separate from implementation |
| 159 | [SI v2][Proof] Controller active cycle proof | `feat/si-v2-controller-active-proof` | OPEN | CONFLICTING | **Superseded / Close** |

### PR #159 — Supersession

- 1 commit ahead of fork point, 67 commits behind current `main`.
- The branch is CONFLICTING with `main`.
- PR body states "No auto-merge" and describes a one-shot proof-of-concept.
- Purpose (demonstrating controller cycle) was succeeded by issues #55–#59 delivery.
- **Recommendation:** Close without merging. Evidence artifacts are local runtime state.

### PRs #69, #70, #71 — Re-evaluation

These three design/plan PRs were created on June 10 during Phase 0. They are:
- All doc-only, each 1 commit
- All MERGEABLE with no conflicts
- 155+ commits behind current `main` (entire Phase 1 burst happened after them)

**Re-evaluation against current main:**

| PR | Issue | Classification | Rationale |
|----|-------|---------------|-----------|
| #69 | #25 — Telegram approval design | **Still valid** | Design doc for Telegram approval adapter with token isolation. Not a Phase 0/1 blocker. Relevant when Telegram integration proceeds. |
| #70 | #26 — Cron activation ceremony | **Still valid** | Design doc for activation guardrails. Relevant when timer/scheduler activation proceeds in a separate root-level phase. |
| #71 | #27 — V1 residue closure plan | **Still valid** | Cleanup plan for archiving v1 residue. Does not block Phase 1. Execution requires a separate approval. |

**Important:** None of these PRs are Phase 1 prerequisites. Phase 1 (Intelligence Layer) is already complete without them. They are Phase 0 design documents that remain valid for their respective follow-up workstreams.

**Recommendation:** Keep open. Merge when their respective implementation phases are ready. Do not merge merely because they are doc-only and MERGEABLE.

---

## 2. Remote Branches (origin-https)

| Branch | Status | Notes |
|--------|--------|-------|
| `main` | Active | **KEEP** |
| `docs/si-v2-post-controller-reconciliation` | **MERGED** (PR #162) | Cleanup: approval-gated when remote cleanup is approved |
| `feat/si-v2-issue-55-regime-schema` | **MERGED** (PR #161) | Cleanup: approval-gated |
| `feat/si-v2-issue-56-regime-shadowlock-enrichment` | **MERGED** (PR #163) | Cleanup: approval-gated |
| `feat/si-v2-issue-57-performance-attribution` | **MERGED** (PR #164) | Cleanup: approval-gated |
| `feat/si-v2-issue-58-source-regime-stats` | **MERGED** (PR #165) | Cleanup: approval-gated |
| `feat/si-v2-issue-59-attribution-reports` | **MERGED** (PR #166) | Cleanup: approval-gated |
| `docs/si-v2-issue-25-telegram-approval-design` | OPEN (PR #69) | **KEEP** — open PR |
| `docs/si-v2-issue-26-cron-activation-ceremony` | OPEN (PR #70) | **KEEP** — open PR |
| `docs/si-v2-issue-27-v1-residue-closure` | OPEN (PR #71) | **KEEP** — open PR |
| `feat/si-v2-controller-active-proof` | OPEN (PR #159) | **KEEP** — PR still open |
| `feat/issue-60-cache-maintenance` | OPEN (PR #169) | **KEEP** — active PR for issue #60 |
| `feat/si-v2-phase2-evidence-input-pipeline` | OPEN (PR #170) | **KEEP** — active PR for issue #62 |

**Evidence:** All six merged branches are verified as fully merged into `main` (commits reachable from `main`).

---

## 3. Local Branches

### 3a. Original Feature/Doc Branches

| Branch | Local SHA | Remote SHA | Delta | Notes |
|--------|-----------|------------|-------|-------|
| `docs/si-v2-post-controller-reconciliation` | `9e4ba29` | `b4edf3a` | 0 ahead, 6 behind | Stale — remote was updated before merge |
| `feat/si-v2-issue-55-regime-schema` | `538464a` | `e0b5310` | 0 ahead, 1 behind | Stale — remote was hardened |
| `feat/si-v2-issue-56-regime-shadowlock-enrichment` | `9a4f3e1` | `0d8b76c` | 0 ahead, 1 behind | Stale — remote was hardened |
| `feat/si-v2-issue-57-performance-attribution` | `c803c7b` | `c803c7b` | SYNCED | Merged, no unique commits |
| `feat/si-v2-issue-58-source-regime-stats` | `f1590b5` | `13ce90f` | 0 ahead, 1 behind | Stale — remote was hardened |
| `feat/si-v2-issue-59-attribution-reports` | `10a2093` | `10a2093` | SYNCED | Merged, no unique commits |

**Note:** All branches are stale or synced. None have unique unmerged work. Cleanup requires:
- Evidence that branch is not checked out in any worktree
- Evidence that no unique commits exist
- Evidence that all commits are reachable from `main` or an archived ref
- A separate approval token before any `git branch -d` or `git push --delete` operations

### 3b. Placeholder Branches

| Branch | SHA | Notes |
|--------|-----|-------|
| `feat/si-v2-issue-60-derived-cache-maintenance` | `81884db` | Points at `origin-https/main` HEAD, no unique commits. Issue #60 was developed on `feat/issue-60-cache-maintenance` branch instead. |

### 3c. Local Review Branches (track remote)

| Branch | Tracking | SHA match? | Notes |
|--------|----------|------------|-------|
| `local/fix-55-regime-schema` | `feat/si-v2-issue-55-regime-schema` | YES (0 ahead) | Review artifact, remote branch merged |
| `local/harden-56` | `feat/si-v2-issue-56-regime-shadowlock-enrichment` | YES (0 ahead) | Review artifact, remote branch merged |
| `local/harden-58` | `feat/si-v2-issue-58-source-regime-stats` | YES (0 ahead) | Review artifact, remote branch merged |
| `local/update-162` | `docs/si-v2-post-controller-reconciliation` | YES (0 ahead) | Review artifact, remote branch merged |

All `local/*` branches are at the same commit as their upstream tracking branch, which has itself been merged into `main`. No unique work remains.

---

## 4. Recommended Cleanup Sequence (Approval-Gated)

### Prerequisites (must all be true before any cleanup):
1. Each targeted branch is NOT checked out in any worktree (`git worktree list`)
2. No unique commits exist (`git log --oneline main..<branch>` is empty)
3. All commits are reachable from `main` or archived
4. A separate human approval token has been granted for cleanup

### Phase A — Open PRs (requires human decision)

| Order | Action | Detail | Risk |
|-------|--------|--------|------|
| 1 | **Close PR #159** | `gh pr close 159 --comment "Superseded by Phase 1 delivery"` | 🟢 Low — no code to lose |
| 2–4 | **Decide on #69/#70/#71** | Do NOT merge automatically. Each requires a review decision when its respective implementation phase is active. | 🟢 Low — doc-only, no urgency |

### Phase B — Remote Branches (after separate approval)

| Order | Action | Detail | Risk |
|-------|--------|--------|------|
| 5 | **Delete merged remote branches** | `git push origin-https --delete` for each of the 6 merged branches | 🟢 Low — commits preserved in main |
| 6 | **Delete superseded remote branches** | `git push origin-https --delete feat/si-v2-controller-active-proof` | 🟢 Low — after PR #159 is closed |

### Phase C — Local Branches (after separate approval)

| Order | Action | Detail | Risk |
|-------|--------|--------|------|
| 7 | **Verify each branch is safe** | For each branch: `git worktree list | grep <branch>` + `git log --oneline main..<branch>` | 🟢 Low |
| 8 | **Delete stale local branches** | `git branch -d <branch>` (use -d, NOT -D) for each verified branch | 🟢 Low — all reachable from main |
| 9 | **Update local main** | `git checkout main && git pull origin-https main` | 🟢 Low |

---

## 5. Integration Order (Condensed)

```
[GATE] Human approval for cleanup
  │
  ├─ 1. Close PR #159 (superseded controller proof)
  │
  ├─ 2. [GATE] Approval for remote branch deletion
  │     └─ Delete all 6 merged remote branches
  │     └─ Delete PR #159 branch
  │
  └─ 3. [GATE] Approval for local branch deletion
        └─ Verify each branch is safe (not in worktree, no unique commits)
        └─ Delete all stale local branches with `git branch -d`
```

**Always prefer `git branch -d` (safe delete — refuses if not merged) over `git branch -D` (force delete).**

---

## 6. Risk Assessment

| Item | Risk | Rationale |
|------|------|-----------|
| Close PR #159 | 🟢 Low | No code to lose; proof artifacts are local runtime state |
| Keep PRs #69–#71 | 🟢 Low | Doc-only, no conflicts, merge when relevant |
| Delete merged remote branches | 🟢 Low | All commits preserved in `main` history |
| Delete local branches | 🟢 Low | All reachable from main or remote tracking refs |

---

## 7. Appendix — State Snapshot

### Git state at inspection
- Worktrees: 10 active (all feature branches for issues #55–#60, review branches)
- Remote: `origin-https` → `https://github.com/GoLukeEnviro/trading-hub.git`
- No uncommitted work in clone

### All refs discovered

```
REMOTE BRANCHES (origin-https)
  main                              → 81884db [ACTIVE]
  docs/si-v2-post-controller-recon  → b4edf3a [MERGED #162]
  feat/si-v2-issue-55-regime-schema → e0b5310 [MERGED #161]
  feat/si-v2-issue-56-...           → 0d8b76c [MERGED #163]
  feat/si-v2-issue-57-...           → c803c7b [MERGED #164]
  feat/si-v2-issue-58-...           → 13ce90f [MERGED #165]
  feat/si-v2-issue-59-...           → 10a2093 [MERGED #166]
  docs/si-v2-issue-25-telegram-...  → 2151e03 [OPEN PR #69]
  docs/si-v2-issue-26-cron-...      → 9f3328c [OPEN PR #70]
  docs/si-v2-issue-27-v1-residue-.. → 8731688 [OPEN PR #71]
  feat/si-v2-controller-active-proof→ fc368d6 [OPEN PR #159]
  feat/issue-60-cache-maintenance   → 8d0e728 [OPEN PR #169]
  feat/si-v2-phase2-evidence-...    → f89f27f [OPEN PR #170]

LOCAL BRANCHES
  docs/si-v2-post-controller-reconciliation  9e4ba29 [STALE -6]
  feat/si-v2-issue-55-regime-schema          538464a [STALE -1]
  feat/si-v2-issue-56-regime-shadowlock-...  9a4f3e1 [STALE -1]
  feat/si-v2-issue-57-performance-attribution c803c7b [SYNCED]
  feat/si-v2-issue-58-source-regime-stats    f1590b5 [STALE -1]
  feat/si-v2-issue-59-attribution-reports    10a2093 [SYNCED]
  feat/si-v2-issue-60-derived-cache-maintain 81884db [POINTS AT main]
  local/fix-55-regime-schema                 e0b5310 [TRACKS remote]
  local/harden-56                            0d8b76c [TRACKS remote]
  local/harden-58                            13ce90f [TRACKS remote]
  local/update-162                           b4edf3a [TRACKS remote]
  main                                       [CURRENT]
```

---

*Report generated by Hermes Agent (orchestrator profile) for issue #46.*
*Updated 2026-06-11 to correct PR #69–#71 status and replace destructive cleanup commands.*
