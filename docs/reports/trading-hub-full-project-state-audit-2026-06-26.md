# Trading Hub — Full Project State Audit

> **Generated:** 2026-06-26T03:15:00Z  
> **Operation Level:** L0 (read-only audit)  
> **Repository:** `GoLukeEnviro/trading-hub` (public, default branch: `main`)  
> **Local path:** `/home/hermes/projects/trading`  
> **Current branch:** `chore/hermes-github-multi-repo-auth`  
> **HEAD:** `47518645e6ae0427b06b48e7dd36a587f4f88649`  
> **origin/main:** `f5b138545d881584a95d6b538972f21a8fb1d37d`  
> **HEAD == origin/main:** ❌ No (2 commits ahead, 0 behind)

---

## 1. Executive Verdict

| Property | Value |
|----------|-------|
| **Status** | 🟡 **YELLOW** |
| **Reason** | Local branch diverged from `origin/main` (2 unmerged commits). SI-v2 loop is GREEN and running. Dashboard containers are up but HTTP unreachable. PR #311 is mergeable but stale (4 days old, no reviews). 4 open issues, none blocking the loop. |
| **Live trading** | `LIVE_FORBIDDEN` — all bots in dry-run |
| **Controller state** | `PAUSED / L3_REPOSITORY_ONLY` |
| **SI-v2 loop** | ✅ GREEN — 4/4 bots authenticated, 4 ShadowProposals, 0 mutations |
| **Profitability gate** | 🔴 Blocked — 2 bots with negative net metrics |
| **Controlled Apply** | 🔴 BLOCKED (fleet-level profitability gate + no human approval token) |

---

## 2. What Is Currently Working

- **SI-v2 Active Cycle loop** — running on 6h cron schedule (`17 */6 * * *`). Latest cycle `20260626T001838Z` GREEN. 64 cycles scanned, 157 proposal records, 256 bot measurement points.
- **All 4 Freqtrade bots** — containers up and healthy: `freqtrade-freqforge` (8086), `freqforge-canary` (8081), `regime-hybrid` (8085), `freqai-rebel` (8087).
- **Hermes Green** — container up (30 min), dashboard UI serving at `:9119`.
- **Guardian** — container up (17h).
- **Dashboard container** — `trading-dashboard` up (2 weeks), Flask app at `:5000`.
- **Freqtrade WebUI** — container up (2 weeks) at `:8180`.
- **WeatherHermes** — container up (2 weeks, healthy) at `:9090`.
- **CI** — 3 active workflows (Main Gate, SI v2 Offline Smoke, SI v2 Phase 2 Proposal Gate). All passing.
- **Secrets** — `.env` and `auth.json` are NOT in the remote repo (404 on API check). `.gitignore` properly excludes them.
- **Scheduler continuity** — proven GREEN over 48h+ (last proof: 2026-06-24). No gaps, no errors.

---

## 3. What Is Not Working or Unproven

- **Dashboard HTTP unreachable** — `trading-dashboard` container is up but `curl localhost:5000` returns 000 (connection refused). The Flask app may have crashed or is binding to a different interface.
- **Freqtrade WebUI HTTP unreachable** — container up at `:8180` but returns 000.
- **Freqforge REST API** — `:8086/api/v1/ping` returns 000 (connection refused or auth required).
- **PR #311 stale** — open 4 days, mergeable, CI green, but 0 reviews, 0 requested reviewers. No one has looked at it.
- **2 unmerged local branches** ahead of `origin/main` — `chore/hermes-github-multi-repo-auth` and `docs/si-v2-safe-parameter-overlay-candidate-package-2026-06-25` exist on remote but are not merged into `main`.
- **Profitability gate** — 2 bots (`regime-hybrid`, `freqai-rebel`) have negative net metrics, blocking fleet-level apply.
- **Rainbow signals stale** — all 50 signals are stale (freshness 23,884s vs 900s threshold). The read-only client works but signals are not fresh.
- **Untracked artifacts** — 50+ untracked files (reports, context docs, coverage artifacts, state files) that need classification.

---

## 4. Local Git / Worktree Table

| Property | Value |
|----------|-------|
| Current branch | `chore/hermes-github-multi-repo-auth` |
| HEAD | `4751864` |
| origin/main | `f5b1385` |
| Ahead of origin/main | 2 commits |
| Behind origin/main | 0 commits |
| Tracked modifications | 1 file modified: `docker-compose.yml` (Mem0 local deps mount) |
| Staged changes | None |
| Untracked files | 50+ (see §8) |

### Local branches not merged into main (selected)

| Branch | Status |
|--------|--------|
| `chore/hermes-github-multi-repo-auth` | **CURRENT** — 2 commits ahead of main, pushed to origin |
| `docs/si-v2-safe-parameter-overlay-candidate-package-2026-06-25` | Pushed to origin, not merged |
| `apply/si-v2-65502d13-controlled-apply` | Merged via PR #331, local branch stale |
| `fix/guardian-ai-hedge-container-name` | Merged via PR #347, local branch stale |
| `fix/harden-cron-restore-345` | Merged via PR #346, local branch stale |
| `fix/guardian-cron-registry-source-of-truth` | Merged via PR #344, local branch stale |
| `docs/align-root-agent-instructions-si-v2-342` | Merged via PR #343, local branch stale |
| 50+ other stale branches | Various merged/superseded branches still local |

---

## 5. Open PR Table

| # | Title | Branch | Base | Mergeable | CI | Reviews | Age | Recommendation |
|---|-------|--------|------|-----------|----|---------|-----|---------------|
| 311 | feat(si-v2): add report-only alert routing readiness evaluator (#310) | `feat/si-v2-alert-routing-readiness-310` | main | ✅ MERGEABLE | ✅ SUCCESS | 0 reviews | 4 days | **MERGE** — CI green, mergeable, adds alert routing evaluator. Stale but safe. |

**PR #311 details:** 6 files changed (+1547/-1). Adds `alert_routing.py` module, tests, context doc, and readiness report. No runtime mutation. Directly addresses Issue #310. No conflicts. No reviews requested.

---

## 6. Open Issue Table

| # | Title | Labels | Updated | Classification | SI-v2 Relevance |
|---|-------|--------|---------|----------------|-----------------|
| 325 | Rainbow: Harden producer lifecycle and factory-mode observability | none | 2026-06-23 | Post-readiness hardening | Medium — Rainbow is an external signal source for the loop |
| 314 | Raise SI v2 critical-module coverage from baseline to enforced quality gate | enhancement | 2026-06-22 | Post-readiness hardening | Medium — quality gate improvement |
| 310 | [Backlog] SI v2 Post-Readiness Hardening: alert routing, kill-switch proof, runtime drift gates | none | 2026-06-22 | Post-readiness hardening | High — PR #311 addresses alert routing portion |
| 256 | infra: split compose layout into infra, fleet, memory and signal domains | none | 2026-06-15 | Infra-only | Low — infra improvement, not loop-critical |

**Verdict:** No open issue blocks the SI-v2 loop. All are post-readiness hardening or infra-only.

---

## 7. Recent PR / Merge Table (since PR #341)

| # | Title | Merged | Branch |
|---|-------|--------|--------|
| 347 | fix(guardian): use real ai hedge container name | 2026-06-25 | `fix/guardian-ai-hedge-container-name` |
| 346 | fix(restore): merge-safe cron restore with SI-v2 invariant (#345) | 2026-06-25 | `fix/harden-cron-restore-345` |
| 344 | fix: align guardian cron registry source of truth | 2026-06-24 | `fix/guardian-cron-registry-source-of-truth` |
| 343 | docs: align root agent instructions with SI-v2 loop | 2026-06-24 | `docs/align-root-agent-instructions-si-v2-342` |
| 341 | feat(si-v2): add historical evidence to active cycle | 2026-06-24 | `feat/si-v2-active-cycle-historical-evidence` |
| 340 | feat(si-v2): add historical trade window analyzer | 2026-06-23 | `feat/si-v2-historical-window-analyzer` |
| 339 | feat(si-v2): add read-only Freqtrade SQLite backfill importer | 2026-06-23 | `feat/si-v2-historical-freqtrade-db-backfill` |
| 338 | docs(si-v2): record runtime proof green for 65502d13 | 2026-06-23 | `report/si-v2-65502d13-runtime-proof-green` |
| 337 | fix(si-v2): handle non-exposed config keys in runtime proof | 2026-06-23 | `fix/si-v2-proof-api-surface-65502d13` |
| 336 | fix(si-v2): verify runtime effect with multi-config overlay | 2026-06-23 | `fix/si-v2-runtime-proof-multiconfig-65502d13` |
| 335 | feat(si-v2): wire apply actuator into controlled apply flow | 2026-06-23 | `feat/si-v2-actuator-wiring-335` |
| 334 | feat(si-v2): add fleet-aware apply actuator proof gate | 2026-06-23 | `feat/si-v2-apply-actuator-332` |
| 333 | fix(si-v2): reclassify PR #331 apply as NO_RUNTIME_EFFECT | 2026-06-23 | `fix/si-v2-no-runtime-effect-reclassify` |
| 331 | apply(si-v2): controlled apply of 65502d13 to freqforge | 2026-06-23 | `apply/si-v2-65502d13-controlled-apply` |

---

## 8. Untracked / Modified Artifact Classification Table

### Modified tracked file

| File | Change | Classification |
|------|--------|---------------|
| `docker-compose.yml` | Added Mem0 local deps mount + cont-init script | **SHOULD_COMMIT_CODE** — part of `chore/hermes-github-multi-repo-auth` branch work |

### Untracked files — classified

#### SHOULD_COMMIT_DOCS (context docs for SI-v2 loop)

| File | Reason |
|------|--------|
| `docs/context/2026-06-19-si-v2-scheduled-proof-and-profit-lane-backlog.md` | SI-v2 planning context |
| `docs/context/2026-06-22-si-v2-dynamic-exit-engine-phase-1.md` | SI-v2 planning context |
| `docs/context/freqai-rebel-repair-plan.md` | Bot repair context |
| `docs/context/freqai-rebel-repair-report.md` | Bot repair context |
| `docs/context/hermes-memory-curation-20260615-120328.md` | Memory curation context |
| `docs/context/hermes-memory-curation-user-profile-20260615-120600.md` | Memory curation context |
| `docs/context/incident-rebel-telegram-404-2026-06-24.md` | Incident report |
| `docs/context/ledger-watchdog-2026-06-14.md` through `docs/context/ledger-watchdog-2026-06-26.md` (13 files) | Daily watchdog reports |
| `docs/context/rebel-telegram-credential-resolution-20260620.md` | Telegram fix context |
| `docs/context/rebel-telegram-send-20260621.md` | Telegram fix context |
| `docs/context/rebel-telegram-send-blocked-20260617.md` | Telegram fix context |
| `docs/context/rebel-telegram-send-blocked-20260618.md` | Telegram fix context |
| `docs/context/rebel-telegram-send-env-fix-20260619.md` | Telegram fix context |
| `docs/context/rebel-telegram-send-env-gap-20260622.md` | Telegram fix context |
| `docs/context/rebel-telegram-summary-blocked-2026-06-14.md` | Telegram fix context |
| `docs/context/si-v2-runtime-proof-rerun-65502d13-tokened-20260623.md` | Runtime proof context |
| `docs/context/trading-hub-overview-20260619-0638.md` | Project overview |
| `docs/security/rotation-evidence-20260615.md` | Security rotation evidence |

#### SHOULD_COMMIT_DOCS (reports)

| File | Reason |
|------|--------|
| `docs/reports/branch-cleanup-audit-20260615.md` | Branch hygiene report |
| `docs/reports/comprehensive-code-project-audit-2026-06-22.md` | Code audit report |
| `docs/reports/dirty-worktree-owner-check-20260615T090002+0000Z.md` | Worktree audit |
| `docs/reports/git-tree-pr-integration-audit-20260615T084500Z.md` | Git tree audit |
| `docs/reports/hermes-cron-scheduler-audit-20260624-1822.md` | Cron audit report |
| `docs/reports/hermes-cron-scheduler-audit-20260624-1844.md` | Cron audit report |
| `docs/reports/hermes-cron-scheduler-audit-20260624-184616.md` | Cron audit report |
| `docs/reports/hermes-dashboard-memory-provider-endpoint-check-20260626T020600Z.md` | Dashboard endpoint check |
| `docs/reports/hermes-mem0-final-cleanup-20260626T005718Z.md` | Mem0 cleanup report |
| `docs/reports/si-v2-p3-scheduler-continuity-proof-2026-06-24.md` | **Scheduler continuity proof** — should be committed |
| `docs/reports/si-v2-remaining-gates-reassessment-2026-06-24.md` | Gates reassessment — should be committed |
| `docs/reports/si-v2-remaining-gates-reassessment-2026-06-25.md` | **Gates reassessment** — should be committed |

#### LOCAL_RUNTIME_ONLY_DO_NOT_COMMIT

| File | Reason |
|------|--------|
| `$RERUN_DIR/` | Runtime rerun directory |
| `.coverage` | Coverage data |
| `coverage.json` | Coverage data |
| `coverage.xml` | Coverage data |
| `self_improvement_v2/reports/phase2/**` (cycle_state, evidence, measurement, shadow_logs, progress) | **Generated runtime artifacts** — already gitignored via `self_improvement_v2/reports/phase2/**` |
| `self_improvement_v2/state/` | Runtime state directory |
| `self_improvement_v2/fixtures/approved_proposal_smoke.json` | Test fixture (should be committed? Check if it's a test asset) |
| `orchestrator/hermes-green-cont-init/` | Local cont-init script (part of docker-compose.yml change) |
| `docs/context/snapshots/` | Runtime snapshots |

#### SECRET_DO_NOT_COMMIT

| File | Reason |
|------|--------|
| `.env` (in /opt/data, not in repo) | Environment secrets — properly excluded by .gitignore |
| `auth.json` (in /opt/data, not in repo) | Auth secrets — properly excluded |
| `.ssh/` (in /opt/data, not in repo) | SSH keys — properly excluded |

#### STALE_REVIEW_REQUIRED

| File | Reason |
|------|--------|
| `docs/reports/hermes-cron-scheduler-audit-20260624-1822.md` | Multiple versions of same audit exist |
| `docs/reports/hermes-cron-scheduler-audit-20260624-1844.md` | Superseded by 184616 version |
| `docs/reports/hermes-cron-scheduler-audit-20260624-184616.md` | Latest cron audit |
| `docs/reports/si-v2-remaining-gates-reassessment-2026-06-24.md` | Superseded by 2026-06-25 version |

#### DELETE_CANDIDATE_BUT_DO_NOT_DELETE

| File | Reason |
|------|--------|
| `docs/reports/hermes-cron-scheduler-audit-20260624-1822.md` | Superseded by later version |
| `docs/reports/hermes-cron-scheduler-audit-20260624-1844.md` | Superseded by later version |
| `docs/reports/si-v2-remaining-gates-reassessment-2026-06-24.md` | Superseded by 2026-06-25 version |

---

## 9. SI-v2 4-Bot Gate Matrix

**Latest cycle:** `20260626T001838Z` (generated 2026-06-26T00:18:38Z)

| Bot | Present | Ping/Auth | Historical Summary | Telemetry Evidence | ShadowProposal | Walk-Forward Verdict | Profitability | Approval Eligible | Final Classification |
|-----|---------|-----------|-------------------|-------------------|----------------|---------------------|---------------|-------------------|---------------------|
| `freqtrade-freqforge` | ✅ | ✅ OK/AUTH | ✅ Present | ✅ Preserved | ✅ `eea95ce5` | `PASS_REVIEW` (+24.78, PF 1.58) | `candidate` | ✅ `PENDING_HUMAN` | `APPLY_CANDIDATE_REQUIRES_HUMAN_APPROVAL` |
| `freqtrade-freqforge-canary` | ✅ | ✅ OK/AUTH | ✅ Present | ✅ Preserved | ✅ `86a46fa9` | `PASS_REVIEW` (+3.98, PF 1.88) | `candidate` | ✅ `PENDING_HUMAN` | `APPLY_CANDIDATE_REQUIRES_HUMAN_APPROVAL` |
| `freqtrade-regime-hybrid` | ✅ | ✅ OK/AUTH | ✅ Present | ✅ Preserved | ✅ `3dce07c4` | `NEGATIVE_NET_METRICS` (-7.25, PF 0.58) | `blocked` | ❌ `approval_negative_net_metrics` | `APPLY_BLOCKED` |
| `freqai-rebel` | ✅ | ✅ OK/AUTH | ✅ Present | ✅ Preserved | ✅ `44970323` | `NEGATIVE_NET_METRICS` (-0.52, PF 0.54) | `blocked` | ❌ `approval_negative_net_metrics` | `APPLY_BLOCKED` |

**Fleet verdict:** GREEN (all 4 bots authenticated and decisions generated)  
**Controlled Apply:** 🔴 **BLOCKED** — fleet-level profitability gate blocked (2/4 bots negative)  
**Human approval:** 2 bots are only human-approval-blocked; 2 bots are profitability-blocked  
**Mutation counters:** All zero (runtime=0, config=0, strategy=0, docker=0, live_trading=0)

---

## 10. Scheduler Continuity Summary

| Property | Value |
|----------|-------|
| Job ID | `64866012641a` |
| Name | `si-v2-active-cycle (6h, log-only)` |
| Schedule | `17 */6 * * *` (every 6 hours at :17 past) |
| Last run | 2026-06-26T00:18:37Z |
| Last status | `ok` |
| Next run | 2026-06-26T06:17:00Z |
| Consecutive GREEN cycles | 50+ (since 2026-06-15) |
| Gaps in last 48h | None |
| Errors in last 48h | None |
| **Verdict** | ✅ **GREEN** — continuous, no gaps, no errors |

---

## 11. Dashboard / Backend Status Table

| Component | Type | Status | Notes |
|-----------|------|--------|-------|
| `trading-dashboard` (Flask, port 5000) | Dashboard | 🔴 **UNREACHABLE** | Container up 2 weeks, but HTTP returns 000. Flask may have crashed or binds to 127.0.0.1 only. |
| `hermes-green` (port 9119) | Hermes Dashboard | ✅ **RUNNING** | Container up 30 min, serves dashboard UI. Health check passes. |
| `trading-freqtrade-webserver-1` (port 8180) | Freqtrade WebUI | 🔴 **UNREACHABLE** | Container up 2 weeks, but HTTP returns 000. May require auth or bind to different interface. |
| `freqtrade-freqforge` (port 8086) | Bot REST API | 🔴 **UNREACHABLE** | Container up 5h (healthy), but `/api/v1/ping` returns 000. May require JWT auth. |
| `dashboard.py` (source) | Code | ✅ **CODE_PRESENT** | 1746-line Flask app in repo root. References all 4 bots, Guardian, signal freshness. |
| `self_improvement_v2/reports/progress/progress_dashboard.py` | SI-v2 Progress Dashboard | ✅ **CODE_PRESENT** | Python script for SI-v2 progress dashboard. |
| `self_improvement_v2/reports/progress/si_v2_progress_dashboard.md` | SI-v2 Progress Report | ✅ **CODE_PRESENT** | Markdown report. |
| `self_improvement_v2/tests/test_si_v2_progress_dashboard.py` | Tests | ✅ **CODE_PRESENT** | Test file for progress dashboard. |

**Verdict:** Dashboard code is present and the container is running, but the Flask app is not serving HTTP. This needs investigation (possibly a crash loop or binding to 0.0.0.0 vs 127.0.0.1 issue).

---

## 12. Secrets / Auth Status

| Check | Status |
|-------|--------|
| `.env` in remote repo | ❌ Not found (404) — ✅ Properly excluded |
| `auth.json` in remote repo | ❌ Not found (404) — ✅ Properly excluded |
| `.ssh/` in remote repo | ❌ Not found (404) — ✅ Properly excluded |
| `.gitignore` coverage | ✅ Comprehensive — covers `.env`, `.env.*`, `auth.json`, `.ssh/`, config secrets |
| Local `.env` permissions | `-rw-------` (600) — ✅ Properly restricted |
| Local `auth.json` permissions | `-rw-------` (600) — ✅ Properly restricted |
| GitHub token in repo | ✅ Not exposed — uses `git@github.com-trading` SSH remote |
| GitHub API access | ✅ Working — `gh` authenticated, can query repo/PRs/issues |
| **Verdict** | ✅ **SECRETS SAFE** — no secrets exposed in remote, local permissions correct |

---

## 13. Cleanup Plan

### Safe to commit (on appropriate branch)

1. **`docker-compose.yml`** — the Mem0 local deps mount change is part of `chore/hermes-github-multi-repo-auth` branch work. Already committed there.
2. **`docs/reports/si-v2-p3-scheduler-continuity-proof-2026-06-24.md`** — should be committed to `main` or a docs branch.
3. **`docs/reports/si-v2-remaining-gates-reassessment-2026-06-25.md`** — should be committed to `main` or a docs branch.
4. **`docs/reports/hermes-dashboard-memory-provider-endpoint-check-20260626T020600Z.md`** — should be committed.
5. **`docs/reports/hermes-mem0-final-cleanup-20260626T005718Z.md`** — should be committed.
6. **`docs/context/` files** — all the ledger-watchdog, rebel-telegram, and SI-v2 context docs should be committed to preserve history.
7. **`docs/security/rotation-evidence-20260615.md`** — security evidence should be committed.

### Local-only, do not commit

1. **`self_improvement_v2/reports/phase2/`** — all cycle_state, evidence, measurement, shadow_logs, progress artifacts. Already gitignored.
2. **`self_improvement_v2/state/`** — runtime state. Already gitignored.
3. **`.coverage`, `coverage.json`, `coverage.xml`** — coverage artifacts. Already gitignored.
4. **`$RERUN_DIR/`** — runtime rerun directory. Already gitignored.
5. **`docs/context/snapshots/`** — runtime snapshots. Already gitignored.

### Needs human decision

1. **`self_improvement_v2/fixtures/approved_proposal_smoke.json`** — test fixture. Should be committed if it's a test asset, but currently untracked. Needs review.
2. **`orchestrator/hermes-green-cont-init/98-mem0-local-deps.sh`** — local cont-init script. Part of the docker-compose.yml change. Should be committed with the branch.

### Delete candidates (but do not delete without explicit instruction)

1. **`docs/reports/hermes-cron-scheduler-audit-20260624-1822.md`** — superseded by 184616 version.
2. **`docs/reports/hermes-cron-scheduler-audit-20260624-1844.md`** — superseded by 184616 version.
3. **`docs/reports/si-v2-remaining-gates-reassessment-2026-06-24.md`** — superseded by 2026-06-25 version.

### Stale local branches (merged into main, can be deleted)

- `apply/si-v2-65502d13-controlled-apply`
- `fix/guardian-ai-hedge-container-name`
- `fix/harden-cron-restore-345`
- `fix/guardian-cron-registry-source-of-truth`
- `docs/align-root-agent-instructions-si-v2-342`
- `feat/si-v2-active-cycle-historical-evidence`
- `feat/si-v2-historical-window-analyzer`
- `feat/si-v2-historical-freqtrade-db-backfill`
- `report/si-v2-65502d13-runtime-proof-green`
- `fix/si-v2-proof-api-surface-65502d13`
- `fix/si-v2-runtime-proof-multiconfig-65502d13`
- `feat/si-v2-actuator-wiring-335`
- `feat/si-v2-apply-actuator-332`
- `fix/si-v2-no-runtime-effect-reclassify`
- 50+ other archive/merged branches

---

## 14. Next Concrete Step

**Merge PR #311** — `feat/si-v2-alert-routing-readiness-310` into `main`.

- CI is green (Main Gate + SI v2 Offline Smoke both SUCCESS)
- Mergeable status: MERGEABLE
- Merge state: CLEAN
- 0 reviews (no blockers, but also no approvals — needs human review first)
- Adds alert routing evaluator module addressing Issue #310
- No runtime mutation, no live trading risk

**Prerequisite:** Human review and approval of PR #311 before merge.

---

## 15. Backlog Entries

### B1: Merge PR #311 (alert routing readiness evaluator)

| Property | Value |
|----------|-------|
| **Title** | Merge PR #311 — feat(si-v2): add report-only alert routing readiness evaluator |
| **Goal** | Close Issue #310 portion by merging the alert routing evaluator code |
| **Acceptance Criteria** | PR #311 merged to main, CI green, no regressions |
| **Effort** | S (trivial — merge button) |
| **Dependencies** | Human review approval |
| **SI-v2 Relevance** | High — addresses post-readiness hardening backlog |

### B2: Investigate dashboard HTTP unreachability

| Property | Value |
|----------|-------|
| **Title** | Investigate and fix trading-dashboard Flask app HTTP unreachability |
| **Goal** | Restore dashboard accessibility at port 5000 |
| **Acceptance Criteria** | `curl localhost:5000` returns HTTP 200 with dashboard HTML |
| **Effort** | M (diagnose container logs, check Flask binding, restart if needed) |
| **Dependencies** | None |
| **SI-v2 Relevance** | Medium — dashboard is operational visibility, not loop-critical |

### B3: Commit uncommitted SI-v2 proof reports

| Property | Value |
|----------|-------|
| **Title** | Commit uncommitted SI-v2 proof reports to main |
| **Goal** | Preserve scheduler continuity proof and gates reassessment in version history |
| **Acceptance Criteria** | `docs/reports/si-v2-p3-scheduler-continuity-proof-2026-06-24.md` and `docs/reports/si-v2-remaining-gates-reassessment-2026-06-25.md` committed to main |
| **Effort** | S (create branch, add files, PR) |
| **Dependencies** | None |
| **SI-v2 Relevance** | High — these are the canonical gate assessment artifacts |

### B4: Clean up stale local branches

| Property | Value |
|----------|-------|
| **Title** | Delete stale local branches that have been merged into main |
| **Goal** | Reduce local branch clutter from 80+ to <20 active branches |
| **Acceptance Criteria** | All branches merged into main via PR are deleted locally |
| **Effort** | M (identify + delete 50+ branches) |
| **Dependencies** | None |
| **SI-v2 Relevance** | Low — hygiene improvement |

### B5: Resolve `chore/hermes-github-multi-repo-auth` branch

| Property | Value |
|----------|-------|
| **Title** | Resolve chore/hermes-github-multi-repo-auth branch — merge or close |
| **Goal** | Either merge the GitHub multi-repo auth bootstrap into main, or close the branch |
| **Acceptance Criteria** | Branch either merged to main or closed with rationale documented |
| **Effort** | S (review 2 commits, decide) |
| **Dependencies** | Human decision |
| **SI-v2 Relevance** | Low — infrastructure/auth improvement |

### B6: Investigate stale Rainbow signals

| Property | Value |
|----------|-------|
| **Title** | Investigate and fix stale Rainbow signals (all 50 signals stale) |
| **Goal** | Restore fresh Rainbow signal delivery to the SI-v2 loop |
| **Acceptance Criteria** | Rainbow signal freshness <900s, fresh_signal_count > 0 |
| **Effort** | M (diagnose Rainbow producer, check container, check signal pipeline) |
| **Dependencies** | None |
| **SI-v2 Relevance** | Medium — Rainbow is an external signal source; stale signals reduce evidence quality |

---

## Safety Confirmation

- ✅ No proposal was applied
- ✅ No approval token was used, requested, exported, or persisted
- ✅ No live trading was enabled
- ✅ No `dry_run=false` change was made
- ✅ No runtime, config, strategy, Docker, Cron, Guardian, or environment mutation was performed
- ✅ No destructive git command was used
- ✅ No secrets were printed or exposed
- ✅ Apply actuator not invoked (controller remains PAUSED / L3_REPOSITORY_ONLY)
- ✅ All mutation counters zero across all 64 scanned cycles
