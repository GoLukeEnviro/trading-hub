# Branch Cleanup Audit — 2026-06-15

**Status: YELLOW** — Read-only audit complete. No branches deleted, no PRs merged, no runtime mutation.

**Mode**: `REMOTE_READ_ONLY_GITHUB_API` — no `git fetch`, no `git push`, no `gh pr merge`, no `gh pr close`.

**Generated**: 2026-06-15T12:01:05Z  
**Repository**: `GoLukeEnviro/trading-hub`  
**Base branch**: `main` (HEAD `814af6845ef4eede5b9073009630d2534c441493`)  
**Audit tool**: GitHub API `compare/main...<branch>` + `gh pr view` + `gh pr list`

---

## 1. Executive Verdict

**YELLOW** — cleanup candidates exist, but deletion is not approved. Several unmerged SI-v2 branches still need review. PR #224 is already merged.

### Key findings

| Metric | Value |
|---|---|
| Total remote branches | 87 |
| Open PRs | 6 |
| KEEP_PROTECTED | 1 (`main`) |
| KEEP_OPEN_PR | 6 |
| DELETE_MERGED_NO_PR | 47 |
| REVIEW_RUNTIME_STATE_RISK | 5 |
| REVIEW_DOCS_STALE | 3 |
| REVIEW_UNMERGED_NO_PR | 25 |
| Destructive commands executed | 0 |

### Validation checks

| Check | Result |
|---|---|
| All open PR heads in KEEP_OPEN_PR | ✅ |
| No duplicate branch records | ✅ |
| No DELETE candidate is unmerged (ahead=0) | ✅ |
| No DELETE candidate has open PR | ✅ |
| No main in DELETE candidates | ✅ |
| Compare errors | 0 |

---

## 2. Current Open PR Table

| PR | State | Head Branch | Mergeable | CI | Risk | Decision |
|---:|:------|:------------|:----------|:---|:-----|:---------|
| **#224** | **MERGED** | `feat/si-v2-multibot-auth-telemetry-proof` | n/a | main-gate ✅ offline-smoke ✅ | GREEN | Already merged at 2026-06-15T10:11:44Z. No action. |
| **#220** | OPEN | `feat/kill-switch-wiring` | MERGEABLE | main-gate ✅ only | RED | Amend tests/validate. Do not merge on main-gate alone. |
| **#205** | OPEN | `feat/si-v2-first-rest-shadowproposal-proof` | CONFLICTING | no checks | YELLOW | Likely superseded by #224+. Extract unique evidence only. |
| **#159** | OPEN | `feat/si-v2-controller-active-proof` | CONFLICTING | no checks | RED | Extract evidence only. Do not merge stale STATE/QUEUE. |
| **#71** | OPEN | `docs/si-v2-issue-27-v1-residue-closure` | MERGEABLE | no checks | YELLOW | Docs freshness review before merge. |
| **#70** | OPEN | `docs/si-v2-issue-26-cron-activation-ceremony` | MERGEABLE | no checks | YELLOW | Docs freshness review; cron/runtime semantics may be stale. |
| **#69** | OPEN | `docs/si-v2-issue-25-telegram-approval-design` | MERGEABLE | no checks | YELLOW | Docs freshness review; validate against current Telegram/user-DM approval design. |

---

## 3. Recommended PR Sequence

### 1. #224 — DONE
Already merged at `2026-06-15T10:11:44Z`. Merge commit: `22016a7716067b8404550b46dc34bd3fc3e91575`.  
Checks: `main-gate` SUCCESS, `offline-smoke` SUCCESS.

### 2. #220 — Next engineering target, NOT direct merge
- **Files**: `freqtrade/shared/kill_switch.py`, `freqtrade/shared/primo_signal.py`, `orchestrator/scripts/kill_switch_trigger.sh`, `var/kill_switch.json`
- **Required before merge**:
  - Tests for `kill_switch.py`
  - Tests/proof for `primo_signal.py` integration
  - Validation plan for `trading_pipeline.py`, `custom_exit`, `drawdown_guard`, cron behavior
  - Explain why `var/kill_switch.json` is safe as tracked repo state, or move/mock it
  - Rerun CI including offline-smoke if SI/runtime path is affected

### 3. #205 — Compare/extract/close
- Now conflicting with main.
- Older first REST ShadowProposal proof is likely superseded by merged authenticated multi-bot telemetry + later telemetry analyzer/snapshot work.
- Keep only unique evidence if missing from main.

### 4. #159 — Evidence-only extraction
- Conflicting.
- Contains `orchestrator/control/QUEUE.json`, `orchestrator/control/STATE.json`, control-plane scripts/schemas.
- Do not merge stale controller state.

### 5. #69–#71 — Docs freshness review
- Mergeable but very behind (211 commits behind main).
- Treat as docs-only review candidates, not automatic merges.

---

## 4. Branch Classification

### KEEP_PROTECTED (1)

| Branch | SHA | Protected |
|--------|-----|-----------|
| `main` | `814af6845ef4` | ✅ |

### KEEP_OPEN_PR (6)

| Branch | PR | SHA | Ahead | Behind | Flags |
|--------|:--:|:----|:-----|:-------|:------|
| `docs/si-v2-issue-25-telegram-approval-design` | #69 | `2151e03f9ca9` | 1 | 211 | DOCS_ONLY, SI_V2 |
| `docs/si-v2-issue-26-cron-activation-ceremony` | #70 | `9f3328c094a7` | 1 | 211 | DOCS_ONLY, RUNTIME_STATE_NAME, SI_V2 |
| `docs/si-v2-issue-27-v1-residue-closure` | #71 | `87316887c1a1` | 1 | 211 | DOCS_ONLY, SI_V2 |
| `feat/kill-switch-wiring` | #220 | `7320b44c6d7a` | 1 | 6 | RUNTIME_STATE_NAME, RUNTIME_STATE_RISK, TRADING_HIGH_RISK |
| `feat/si-v2-controller-active-proof` | #159 | `fc368d6452a9` | 1 | 123 | CONTROL_PLANE, RUNTIME_STATE_RISK |
| `feat/si-v2-first-rest-shadowproposal-proof` | #205 | `b6b8b97a1a2d` | 2 | 21 | SI_V2, TESTS_VALIDATION |

### DELETE_MERGED_NO_PR (47)

All branches below are **fully merged into `origin/main`** (ahead=0), have no open PR, and are not protected.

| Branch | SHA | Date | Behind | Notes |
|--------|:----|:-----|:------:|:------|
| `ci/si-v2-issue-182-phase2-proposal-gate` | `0cf2ea0695f2` | 2026-06-12 | 37 | Merged via PR #189 |
| `docs/phase-b2-l3-compose-adoption-plan-200` | `635c5cdf8140` | 2026-06-15 | 7 | Merged via PR #219 |
| `docs/si-v2-issue-20-adapter-contracts` | `e48c94870f69` | 2026-06-10 | 210 | Merged via PR #54 |
| `docs/si-v2-issue-22-riskguard-shadowlogger-contract` | `995158b42d5d` | 2026-06-10 | 210 | Merged via PR #49 |
| `docs/si-v2-issue-23-watchdog-ownership-adr` | `f4a5665aa090` | 2026-06-10 | 210 | Merged via PR #50 |
| `docs/si-v2-issue-26-activation-ceremony-v2` | `8e47b9a4edd4` | 2026-06-12 | 30 | Merged via PR #193 |
| `docs/si-v2-issue-32-consolidate-docs-index` | `abb05452a3b0` | 2026-06-10 | 210 | Merged via PR #51 |
| `docs/si-v2-issue-47-roadmap-baseline` | `c1e166e04b07` | 2026-06-10 | 209 | Merged via PR #76 |
| `docs/si-v2-issue-66-weekly-review-cadence` | `0b9c18d26c5e` | 2026-06-12 | 28 | Merged via PR #194 |
| `docs/si-v2-issue-93-pr36-reconciliation` | `71074bcb88e7` | 2026-06-10 | 176 | Merged via PR #99 |
| `docs/si-v2-phase0-reconciliation-20260611` | `c1b6cf03ce32` | 2026-06-11 | 50 | Merged via PR #171 |
| `docs/si-v2-post-controller-reconciliation` | `b4edf3aeec5f` | 2026-06-11 | 67 | Merged via PR #162 |
| `feat/issue-191-main-gate-workflow` | `4dd20f041a28` | 2026-06-12 | 26 | Merged via PR #195 |
| `feat/issue-60-cache-maintenance` | `58de5cd0c866` | 2026-06-11 | 54 | Merged via PR #169 |
| `feat/si-v2-canonical-ci-pending` | `c20aa0a11737` | 2026-06-11 | 108 | Merged via PR #158 |
| `feat/si-v2-issue-100-104-source-evidence-episode-foundation` | `89125d4d3b8f` | 2026-06-10 | 160 | Merged via PR #119 |
| `feat/si-v2-issue-107-112-goldenpath-evidence-regime-attribution-qagate` | `d8433e0acda2` | 2026-06-10 | 152 | Merged via PR #126 |
| `feat/si-v2-issue-12-shadowlock-indexer` | `bf274c2bb710` | 2026-06-10 | 210 | Merged via PR #52 |
| `feat/si-v2-issue-120-125-governance-ci-approval-runbook` | `a42027e4af52` | 2026-06-10 | 123 | Merged via PR #137 |
| `feat/si-v2-issue-127-132-rehearsal-control` | `b075ebf2209e` | 2026-06-10 | 120 | Merged via PR #138 |
| `feat/si-v2-issue-135-140-rehearsal-planning-gate` | `f0215bc2c502` | 2026-06-10 | 118 | Merged via PR #139 |
| `feat/si-v2-issue-175-controller-baseline-reconciliation` | `49f24a4f4108` | 2026-06-12 | 35 | Merged via PR #190 |
| `feat/si-v2-issue-21-adapter-prototypes-v2` | `318dd08021f9` | 2026-06-10 | 183 | Merged via PR #108 |
| `feat/si-v2-issue-30-status-reporting` | `55ecb8216544` | 2026-06-10 | 210 | Merged via PR #53 |
| `feat/si-v2-issue-31-ci-safety-gates` | `6352845a8256` | 2026-06-10 | 210 | Merged via PR #55 |
| `feat/si-v2-issue-45-shadowlock-writer-indexer-trigger` | `8578110513ba` | 2026-06-10 | 210 | Merged via PR #56 |
| `feat/si-v2-issue-55-regime-schema` | `e0b531037cba` | 2026-06-11 | 72 | Merged via PR #163 |
| `feat/si-v2-issue-56-regime-shadowlock-enrichment` | `0d8b76c178f3` | 2026-06-11 | 72 | Merged via PR #164 |
| `feat/si-v2-issue-57-performance-attribution` | `c803c7b07f67` | 2026-06-11 | 62 | Merged via PR #165 |
| `feat/si-v2-issue-58-source-regime-stats` | `13ce90f1374a` | 2026-06-11 | 59 | Merged via PR #166 |
| `feat/si-v2-issue-59-attribution-reports` | `10a20939a13e` | 2026-06-11 | 57 | Merged via PR #167 |
| `feat/si-v2-issue-65-validation-gate-matrix` | `f8dfb3786c41` | 2026-06-12 | 39 | Merged via PR #188 |
| `feat/si-v2-issue-79-rainbow-envelope-validator` | `1f06fa5ab290` | 2026-06-10 | 180 | Merged via PR #91 |
| `feat/si-v2-issue-81-shadowlock-external-signal-audit-events` | `82459048575a` | 2026-06-10 | 165 | Merged via PR #113 |
| `feat/si-v2-issue-82-rainbow-contract-snapshot` | `e281a22fc75e` | 2026-06-10 | 172 | Merged via PR #105 |
| `feat/si-v2-issue-84-85-80-rainbow-report-status-client` | `9969afb614c4` | 2026-06-10 | 167 | Merged via PR #106 |
| `feat/si-v2-issue-97-114-118-offline-episode-readiness-architecture` | `c042cd20b7dc` | 2026-06-10 | 142 | Merged via PR #133 |
| `final-mistake-check` | `790187fb500a` | 2026-06-10 | 115 | No PR (test branch) |
| `fix/phase2-hermes-watchdog-compose-network` | `4f40bc585d18` | 2026-06-14 | 9 | Merged via PR #218 |
| `fix/si-v2-controller-state-contract` | `adc7632444db` | 2026-06-11 | 75 | Merged via PR #160 |
| `fix/si-v2-issue-185-episode-contract-hardening` | `f424a968c20c` | 2026-06-12 | 43 | Merged via PR #186 |
| `fix/si-v2-issue-43-fleetrisk-state` | `8ba2510b386d` | 2026-06-10 | 210 | Merged via PR #77 |
| `fix/si-v2-sha-validation-regression-tests` | `3482df82304b` | 2026-06-12 | 32 | Merged via PR #192 |
| `no-op` | `790187fb500a` | 2026-06-10 | 115 | No PR (test branch) |
| `temp` | `790187fb500a` | 2026-06-10 | 115 | No PR (test branch) |
| `test-191-green-pr-v2` | `a723fa67226c` | 2026-06-12 | 24 | Merged via PR #198 |
| `test/si-v2-issue-181-phase2-e2e-integration` | `637f3925723b` | 2026-06-12 | 41 | Merged via PR #187 |

**⚠️ Special caution**: `fix/si-v2-controller-state-contract` and `fix/si-v2-issue-43-fleetrisk-state` have state-related names but are confirmed merged (ahead=0). Still recommended to review before deletion.

### REVIEW_RUNTIME_STATE_RISK (5)

| Branch | SHA | Ahead | Behind | Flags |
|--------|:----|:-----:|:------:|:------|
| `chore/si-v2-continuous-controller-control-plane` | `7146cda72e2a` | 1 | 80 | CONTROL_PLANE, RUNTIME_STATE_RISK |
| `docs/phase2-runtime-ownership-map-200` | `d20bb5a5c052` | 1 | 11 | DOCS_ONLY, RUNTIME_STATE_NAME, RUNTIME_STATE_RISK |
| `docs/roadmap-v2-runtime-ownership-reconciliation` | `ae94159c53ff` | 1 | 12 | DOCS_ONLY, RUNTIME_STATE_NAME, RUNTIME_STATE_RISK |
| `feat/si-v2-rainbow-read-only-runtime-source-v1` | `9094b3c83e6c` | 1 | 13 | RUNTIME_STATE_NAME, RUNTIME_STATE_RISK, SI_V2, TESTS_VALIDATION |
| `test-191-failing-check` | `a62eef08e07d` | 1 | 25 | CONTROL_PLANE, TESTS_VALIDATION |

**Decision**: Do not delete or merge automatically. These need exact diff review.

### REVIEW_DOCS_STALE (3)

| Branch | SHA | Ahead | Behind |
|--------|:----|:-----:|:------:|
| `docs/si-v2-branch-hygiene-report` | `9af2e405ccc2` | 1 | 56 |
| `docs/si-v2-issue-38-telegram-conflict-rca` | `b965ec4a6c6e` | 1 | 211 |
| `docs/si-v2-issue-39-watchdog-connectivity` | `d0c33298e419` | 1 | 211 |

**Decision**: Docs freshness review only. Likely archive/close or extract if still useful.

### REVIEW_UNMERGED_NO_PR (25)

| Branch | SHA | Ahead | Behind | Flags |
|--------|:----|:-----:|:------:|:------|
| `docs/si-v2-issue-34-market-data-readiness` | `7e9a83f9f165` | 2 | 48 | SI_V2, TESTS |
| `feat/si-v2-143-154-planning-automation-quality` | `ca5d1142949e` | 5 | 117 | SI_V2, TESTS |
| `feat/si-v2-active-cycle-runner-v1` | `eb34b1dfc374` | 3 | 20 | SI_V2, TESTS |
| `feat/si-v2-issue-143-147-149-planning-automation` | `f7a75038278a` | 1 | 117 | SI_V2, TESTS |
| `feat/si-v2-issue-21-adapter-prototypes` | `172e4ee5f9e7` | 1 | 211 | SI_V2, TESTS |
| `feat/si-v2-issue-35-proposal-scoring-policy` | `da9a6a2ef26f` | 1 | 47 | SI_V2, TESTS |
| `feat/si-v2-issue-63-weight-proposal-engine` | `c0fec2c62d6f` | 1 | 46 | SI_V2, TESTS |
| `feat/si-v2-issue-64-episode-report` | `578544c93aa1` | 1 | 45 | SI_V2, TESTS |
| `feat/si-v2-measurement-ledger-v1` | `7f1c8625aa41` | 1 | 18 | SI_V2, TESTS |
| `feat/si-v2-multibot-auth-telemetry-proof` | `b8e6de75631c` | 8 | 4 | SI_V2, TESTS |
| `feat/si-v2-multibot-rest-shadowproposal-proof` | `c7c31d372ae8` | 1 | 5 | SI_V2, TESTS |
| `feat/si-v2-phase2-evidence-input-pipeline` | `f89f27fb41aa` | 1 | 56 | SI_V2, TESTS |
| `feat/si-v2-phase2-evidence-pipeline-hardened` | `27a6d3ea0d6f` | 2 | 49 | SI_V2, TESTS |
| `feat/si-v2-rainbow-cycle-ledger-integration-v1` | `2653c10bf6f7` | 1 | 16 | SI_V2, TESTS |
| `feat/si-v2-rainbow-enable-observation-v1` | `ccad4cd31d9d` | 1 | 14 | SI_V2 |
| `feat/si-v2-rainbow-read-only-client-v1` | `2812db1b2d39` | 1 | 16 | SI_V2, TESTS |
| `feat/si-v2-readonly-freqtrade-jwt-auth` | `44dceda27a2b` | 4 | 21 | SI_V2, TESTS |
| `feat/si-v2-runner-ledger-integration` | `6eaf1d2e6ea9` | 2 | 17 | SI_V2, TESTS |
| `feat/si-v2-safe-auth-resolver` | `1887454e5c6e` | 6 | 3 | SI_V2, TESTS |
| `feat/si-v2-signal-fusion-v1` | `9c8730a80cf2` | 2 | 19 | SI_V2, TESTS |
| `feat/si-v2-structured-telemetry-snapshots` | `7a806d745479` | 3 | 1 | SI_V2, TESTS |
| `feat/si-v2-telemetry-analyzer-shadowproposal-rule` | `cc3bbc108704` | 5 | 2 | SI_V2, TESTS |
| `fix/si-v2-freqtrade-registry-docker-dns` | `1cf9d9b72e2c` | 5 | 21 | SI_V2 |
| `hygiene/status-artifacts-and-gitignore` | `941b512ea95d` | 1 | 6 | — |
| `test-191-green-pr` | `06f160b7b825` | 1 | 25 | — |

**Note**: `feat/si-v2-multibot-auth-telemetry-proof` is the #224 branch. Because #224 was squash-merged, the branch is still "ahead" by Git ancestry. It is **not** a delete candidate under strict rules.

---

## 5. Dry-Run Deletion Plan

All commands below are **commented out**. No branch has been deleted.

### Batch 1 (10 branches)

```bash
# git push origin --delete ci/si-v2-issue-182-phase2-proposal-gate
# git push origin --delete docs/phase-b2-l3-compose-adoption-plan-200
# git push origin --delete docs/si-v2-issue-20-adapter-contracts
# git push origin --delete docs/si-v2-issue-22-riskguard-shadowlogger-contract
# git push origin --delete docs/si-v2-issue-23-watchdog-ownership-adr
# git push origin --delete docs/si-v2-issue-26-activation-ceremony-v2
# git push origin --delete docs/si-v2-issue-32-consolidate-docs-index
# git push origin --delete docs/si-v2-issue-47-roadmap-baseline
# git push origin --delete docs/si-v2-issue-66-weekly-review-cadence
# git push origin --delete docs/si-v2-issue-93-pr36-reconciliation
```

### Batch 2 (10 branches)

```bash
# git push origin --delete docs/si-v2-phase0-reconciliation-20260611
# git push origin --delete docs/si-v2-post-controller-reconciliation
# git push origin --delete feat/issue-191-main-gate-workflow
# git push origin --delete feat/issue-60-cache-maintenance
# git push origin --delete feat/si-v2-canonical-ci-pending
# git push origin --delete feat/si-v2-issue-100-104-source-evidence-episode-foundation
# git push origin --delete feat/si-v2-issue-107-112-goldenpath-evidence-regime-attribution-qagate
# git push origin --delete feat/si-v2-issue-12-shadowlock-indexer
# git push origin --delete feat/si-v2-issue-120-125-governance-ci-approval-runbook
# git push origin --delete feat/si-v2-issue-127-132-rehearsal-control
```

### Batch 3 (10 branches)

```bash
# git push origin --delete feat/si-v2-issue-135-140-rehearsal-planning-gate
# git push origin --delete feat/si-v2-issue-175-controller-baseline-reconciliation
# git push origin --delete feat/si-v2-issue-21-adapter-prototypes-v2
# git push origin --delete feat/si-v2-issue-30-status-reporting
# git push origin --delete feat/si-v2-issue-31-ci-safety-gates
# git push origin --delete feat/si-v2-issue-45-shadowlock-writer-indexer-trigger
# git push origin --delete feat/si-v2-issue-55-regime-schema
# git push origin --delete feat/si-v2-issue-56-regime-shadowlock-enrichment
# git push origin --delete feat/si-v2-issue-57-performance-attribution
# git push origin --delete feat/si-v2-issue-58-source-regime-stats
```

### Batch 4 (10 branches)

```bash
# git push origin --delete feat/si-v2-issue-59-attribution-reports
# git push origin --delete feat/si-v2-issue-65-validation-gate-matrix
# git push origin --delete feat/si-v2-issue-79-rainbow-envelope-validator
# git push origin --delete feat/si-v2-issue-81-shadowlock-external-signal-audit-events
# git push origin --delete feat/si-v2-issue-82-rainbow-contract-snapshot
# git push origin --delete feat/si-v2-issue-84-85-80-rainbow-report-status-client
# git push origin --delete feat/si-v2-issue-97-114-118-offline-episode-readiness-architecture
# git push origin --delete final-mistake-check
# git push origin --delete fix/phase2-hermes-watchdog-compose-network
# git push origin --delete fix/si-v2-controller-state-contract
```

### Batch 5 (7 branches)

```bash
# git push origin --delete fix/si-v2-issue-185-episode-contract-hardening
# git push origin --delete fix/si-v2-issue-43-fleetrisk-state
# git push origin --delete fix/si-v2-sha-validation-regression-tests
# git push origin --delete no-op
# git push origin --delete temp
# git push origin --delete test-191-green-pr-v2
# git push origin --delete test/si-v2-issue-181-phase2-e2e-integration
```

---

## 6. Risks and Blockers

1. **#220 remains safety-sensitive** — Even though GitHub says `MERGEABLE`, it touches Freqtrade/shared kill-switch logic and `var/kill_switch.json`. Merge-as-is is not justified by one `main-gate` success.

2. **#205 and #159 are conflicting** — Neither should be rebased/merged mechanically. #159 especially risks stale controller state.

3. **Squash-merged branches are not automatically delete candidates** — Example: #224 branch is still ahead by Git ancestry. Under strict rules, it stays review-only unless explicitly decided otherwise.

4. **DELETE_MERGED_NO_PR is not final deletion approval** — Active issue/report references were not exhaustively validated. All deletion commands remain commented.

---

## 7. Required Human Approvals

| Token | Action |
|:------|:-------|
| `APPROVE_220_TEST_AMEND` | Update/amend #220 branch with tests/validation only. No merge. |
| `APPROVE_CLOSE_SUPERSEDED_PRS` | Close or comment on #205/#159 after explicit final evidence review. |
| `APPROVE_DELETE_BRANCHES_BATCH_N` | Delete one named batch only, after reviewing candidates. |

---

## 8. Pre-Existing Dirty Worktree (Unchanged)

```text
?? docs/reports/dirty-worktree-owner-check-20260615T090002+0000Z.json
?? docs/reports/dirty-worktree-owner-check-20260615T090002+0000Z.md
?? docs/reports/git-tree-pr-integration-audit-20260615T084500Z.json
?? docs/reports/git-tree-pr-integration-audit-20260615T084500Z.md
?? self_improvement_v2/reports/phase2/multi-bot-authenticated-telemetry-proof.md
?? self_improvement_v2/reports/phase2/multi-bot-shadowproposal-proof.md
```

These are pre-existing untracked files. Not modified by this audit.

---

## 9. One Next Safe Action

Review this read-only audit. If you want to proceed with deletion, approve a batch by name:

```text
APPROVE_DELETE_BRANCHES_BATCH_1
```

No runtime mutation, no PR merge, no force-push has occurred.
