# Phase 0 — Branch & PR Hygiene Inventory Report

**Date:** 2026-06-11  
**Repo:** GoLukeEnviro/trading-hub  
**Report ref:** issue #46  

---

## 1. Open Pull Requests

| # | Title | Branch | Status | Mergeable | Classification |
|---|-------|--------|--------|-----------|----------------|
| 69 | [SI v2] Design Telegram approval live adapter with token isolation (#25) | `docs/si-v2-issue-25-telegram-approval-design` | OPEN | MERGEABLE | **KEEP → MERGE** |
| 70 | [SI v2] Design cron activation ceremony and jobs.json guardrails (#26) | `docs/si-v2-issue-26-cron-activation-ceremony` | OPEN | MERGEABLE | **KEEP → MERGE** |
| 71 | [SI v2] Plan v1 residue archive and migration closure (#27) | `docs/si-v2-issue-27-v1-residue-closure` | OPEN | MERGEABLE | **KEEP → MERGE** |
| 159 | [SI v2][Proof] Controller active cycle proof | `feat/si-v2-controller-active-proof` | OPEN | CONFLICTING | **SUPERSEDED / CLOSE** |

### PR #159 — Detailed Supersession Analysis

- **1 commit ahead** of its fork point, **67 commits behind** current `main`.
- The branch is CONFLICTING with `main`.
- PR body states "No auto-merge" and describes a one-shot proof-of-concept for controller readiness.
- The proof's purpose (demonstrating controller cycle) has been succeeded by the integrated delivery of issues #55–#59 (regime schema, shadowlock, attribution, stats, reports) merged via PRs #160–#166, and the upcoming timer activation ceremony (PR #70).
- **Recommendation:** Close PR #159 without merging. The evidence files (`controller-active-proof-20260611.md`, QUEUE.json, STATE.json) were ephemeral runtime state that served their purpose. No product code change exists to merge.

### PRs #69, #70, #71 — Merge Readiness

- All three are design/document-only PRs.
- Each is 1 commit ahead of its fork point, 155 commits behind `main` (dated June 10 — the entire Phase 0 delivery burst happened after them).
- All three are **MERGEABLE** with no conflicts.
- **Recommendation:** Merge these three PRs into `main` as the final Phase 0 delivery step, after branch cleanup. Their design documents are prerequisites for Phase 1.

---

## 2. Remote Branches (origin-https)

| Branch | Status | Classification |
|--------|--------|----------------|
| `main` | Active | **KEEP** |
| `docs/si-v2-post-controller-reconciliation` | **MERGED** (PR #162) | **SAFE TO DELETE** |
| `feat/si-v2-issue-55-regime-schema` | **MERGED** (PR #161) | **SAFE TO DELETE** |
| `feat/si-v2-issue-56-regime-shadowlock-enrichment` | **MERGED** (PR #163) | **SAFE TO DELETE** |
| `feat/si-v2-issue-57-performance-attribution` | **MERGED** (PR #164) | **SAFE TO DELETE** |
| `feat/si-v2-issue-58-source-regime-stats` | **MERGED** (PR #165) | **SAFE TO DELETE** |
| `feat/si-v2-issue-59-attribution-reports` | **MERGED** (PR #166) | **SAFE TO DELETE** |
| `docs/si-v2-issue-25-telegram-approval-design` | OPEN (PR #69) | **KEEP until PR merged** |
| `docs/si-v2-issue-26-cron-activation-ceremony` | OPEN (PR #70) | **KEEP until PR merged** |
| `docs/si-v2-issue-27-v1-residue-closure` | OPEN (PR #71) | **KEEP until PR merged** |
| `feat/si-v2-controller-active-proof` | OPEN (PR #159) | **DELETE after PR closed** |

All six merged branches (`docs/si-v2-post-controller-reconciliation`, `feat/si-v2-issue-55` through `feat/si-v2-issue-59`) are verified as fully merged into `main` by git's `--merged` check. Their commits are reachable from `main`.

---

## 3. Local Branches

### 3a. Original Feature/Doc Branches (stale — behind remote)

| Branch | Local SHA | Remote SHA | Delta | Classification |
|--------|-----------|------------|-------|----------------|
| `docs/si-v2-post-controller-reconciliation` | `9e4ba29` | `b4edf3a` | 0 ahead, 6 behind | **DELETE** — stale, remote was updated |
| `feat/si-v2-issue-55-regime-schema` | `538464a` | `e0b5310` | 0 ahead, 1 behind | **DELETE** — stale, remote was hardened |
| `feat/si-v2-issue-56-regime-shadowlock-enrichment` | `9a4f3e1` | `0d8b76c` | 0 ahead, 1 behind | **DELETE** — stale, remote was hardened |
| `feat/si-v2-issue-57-performance-attribution` | `c803c7b` | `c803c7b` | SYNCED | **DELETE** — merged, no longer needed |
| `feat/si-v2-issue-58-source-regime-stats` | `f1590b5` | `13ce90f` | 0 ahead, 1 behind | **DELETE** — stale, remote was hardened |
| `feat/si-v2-issue-59-attribution-reports` | `10a2093` | `10a2093` | SYNCED | **DELETE** — merged, no longer needed |

### 3b. Stub Branch (no diff from main)

| Branch | SHA | Notes | Classification |
|--------|-----|-------|----------------|
| `feat/si-v2-issue-60-derived-cache-maintenance` | `81884db` | Points at `origin-https/main` HEAD, no unique commits | **DELETE** — placeholder, never developed |

### 3c. Local Review/Harden Branches (track remote)

| Branch | Tracking | SHA match? | Classification |
|--------|----------|------------|----------------|
| `local/fix-55-regime-schema` | `origin-https/feat/si-v2-issue-55-regime-schema` | YES (0 ahead) | **DELETE** — merge artifact, remote branch already merged |
| `local/harden-56` | `origin-https/feat/si-v2-issue-56-regime-shadowlock-enrichment` | YES (0 ahead) | **DELETE** — merge artifact, remote branch already merged |
| `local/harden-58` | `origin-https/feat/si-v2-issue-58-source-regime-stats` | YES (0 ahead) | **DELETE** — merge artifact, remote branch already merged |
| `local/update-162` | `origin-https/docs/si-v2-post-controller-reconciliation` | YES (0 ahead) | **DELETE** — merge artifact, remote branch already merged |

These `local/*` branches were created during CI/review workflows. Each is exactly at the same commit as its upstream tracking branch, which has itself been merged into `main`. No unique work remains.

---

## 4. Recommended Actions

### Phase A — Open PRs

| Order | Action | Detail | Risk |
|-------|--------|--------|------|
| 1 | **Close PR #159** | `gh pr close 159` — no merge, proof served its purpose | **Low** — no code to lose; comment noting supersession |
| 2 | **Merge PR #71** | `gh pr merge 71 --squash` — v1 residue closure plan | **Low** — doc-only, MERGEABLE |
| 3 | **Merge PR #70** | `gh pr merge 70 --squash` — cron activation ceremony design | **Low** — doc-only, MERGEABLE |
| 4 | **Merge PR #69** | `gh pr merge 69 --squash` — Telegram approval design | **Low** — doc-only, MERGEABLE |

### Phase B — Remote Branches (after PRs closed/merged)

| Order | Action | Detail | Risk |
|-------|--------|--------|------|
| 5 | **Delete merged remote branches** | `git push origin-https --delete docs/si-v2-post-controller-reconciliation feat/si-v2-issue-55-regime-schema feat/si-v2-issue-56-regime-shadowlock-enrichment feat/si-v2-issue-57-performance-attribution feat/si-v2-issue-58-source-regime-stats feat/si-v2-issue-59-attribution-reports` | **Low** — all merged, commits preserved in main |
| 6 | **Delete PR #159 remote branch** | `git push origin-https --delete feat/si-v2-controller-active-proof` | **Low** — after PR is closed |
| 7 | **Delete open PR remote branches** | After PRs #69, #70, #71 are merged, delete their branches | **Low** — automatic if using `--delete-branch` flag on merge |

### Phase C — Local Branches

| Order | Action | Detail | Risk |
|-------|--------|--------|------|
| 8 | **Delete all stale local branches** | `git branch -D docs/si-v2-post-controller-reconciliation feat/si-v2-issue-55-regime-schema feat/si-v2-issue-56-regime-shadowlock-enrichment feat/si-v2-issue-57-performance-attribution feat/si-v2-issue-58-source-regime-stats feat/si-v2-issue-59-attribution-reports feat/si-v2-issue-60-derived-cache-maintenance local/fix-55-regime-schema local/harden-56 local/harden-58 local/update-162` | **Low** — all are stale/merged; no unique unmerged work |
| 9 | **Update local main** | `git checkout main && git pull origin-https main` | **Low** — standard sync |

---

## 5. Integration Order / Cleanup Sequence (Condensed)

```
1. Close PR #159 (superseded)
2. Merge PR #71 (v1 residue plan)
3. Merge PR #70 (cron activation design)
4. Merge PR #69 (telegram design)
5. Delete all merged remote branches
6. Delete PR #159 remote branch
7. Delete all stale local branches
8. Update local main → origin-https/main
```

Total: **4 PR actions** + **1 branch deletion batch (remote)** + **1 branch deletion batch (local)** + **1 sync**.

---

## 6. Risk Assessment

| Item | Risk | Rationale |
|------|------|-----------|
| Close PR #159 | 🟢 Low | No code to lose; proof artifacts are local to the runner's worktrees |
| Merge PRs #69-#71 | 🟢 Low | Doc-only, MERGEABLE, no code conflicts |
| Delete merged remote branches | 🟢 Low | Commits preserved in `main`'s history |
| Delete local branches | 🟢 Low | All reachable from main or remote tracking refs |
| Overall | 🟢 Low | All recommended actions are safe cleanups of fully-merged or superseded work |

---

## 7. Appendix — Full State Snapshot

### Git state at inspection time
- **Current branch:** `main` (behind `origin/main` by 5 commits)
- **Remote:** `origin-https` → `https://github.com/GoLukeEnviro/trading-hub.git`
- **Worktrees:** 10 active worktrees (all feature branches)
- **Uncommitted work:** None (working tree clean)

### All refs discovered

```
HEAD → main (773e9cb)

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

LOCAL BRANCHES
  docs/si-v2-post-controller-reconciliation  9e4ba29 [STALE -6]
  feat/si-v2-issue-55-regime-schema          538464a [STALE -1]
  feat/si-v2-issue-56-regime-shadowlock-...  9a4f3e1 [STALE -1]
  feat/si-v2-issue-57-performance-attribution c803c7b [SYNCED]
  feat/si-v2-issue-58-source-regime-stats    f1590b5 [STALE -1]
  feat/si-v2-issue-59-attribution-reports    10a2093 [SYNCED]
  feat/si-v2-issue-60-derived-cache-maintain 81884db [POINTS AT main]
  local/fix-55-regime-schema                 e0b5310 [TRACKS remote, 0 ahead]
  local/harden-56                            0d8b76c [TRACKS remote, 0 ahead]
  local/harden-58                            13ce90f [TRACKS remote, 0 ahead]
  local/update-162                           b4edf3a [TRACKS remote, 0 ahead]
  main                                       773e9cb [behind 5]
```

---

*Report generated by Hermes Agent (orchestrator profile) for issue #46.*
