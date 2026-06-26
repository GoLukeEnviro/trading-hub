# Git Tree / PR Integration Audit — 2026-06-15T08:45:00Z

Status: **RED**
Operation Level: **L1_READ_ONLY_REPO_AUDIT**
Scope: read-only Git/GitHub integration audit for `/home/hermes/projects/trading`.
Note: reports were generated as requested artifacts; no Git/GitHub/runtime mutation commands were executed.

## 1. Executive Verdict: repository integration readiness

**Verdict: RED.** Repository integration is **not ready for merge**.

Evidence summary:
- Current local HEAD: `ddcfbdbd197b4aa8665cb3829f79f609f75d9601`; known main head matches local main.
- Canonical base used for analysis: `origin/main` / `refs/remotes/origin/main` = `ddcfbdbd197b4aa8665cb3829f79f609f75d9601`.
- Branch refs inventoried: 53 local, 119 remote; 170 non-canonical branch refs classified.
- GitHub PRs: 5 open, 73 merged, 14 closed-unmerged.
- Open PRs blocked: 5/5.
- Conflict probes with conflict evidence: 42 branch refs.
- Dirty worktree entries before report generation: 4; includes required known dirty `HERMES_METRICS.json`.
- Compose CLI recovery is explicitly out-of-scope and was not attempted; Compose-dependent runtime proof remains blocked by the provided host-tooling context.

## 2. Current Repository State: branch, HEAD, worktree, remotes, dirty files

| Item | Evidence |
|---|---|
| Path | `/home/hermes/projects/trading` |
| Branch | `main` |
| HEAD | `ddcfbdbd197b4aa8665cb3829f79f609f75d9601` |
| Canonical base | `refs/remotes/origin/main` (`origin/main`) at `ddcfbdbd197b4aa8665cb3829f79f609f75d9601` |
| Operation timestamp | `2026-06-15T08:45:00Z` |

Preflight command outputs were captured with credential redaction. Dirty entries reported by `git status --short --branch` before these audit report artifacts were written:
- `M docs/state/canonical-trading-status.md`
- `M orchestrator/reports/canonical_trading_status_latest.json`
- `?? HERMES_METRICS.json`
- `?? docs/context/ledger-watchdog-2026-06-15.md`

Remote/config evidence (redacted if needed):
- `pwd` exit=0: `/home/hermes/projects/trading`
- `git rev-parse --show-toplevel` exit=0: `/home/hermes/projects/trading`
- `git status --short --branch` exit=0: `## main...remotes/origin/main;  M docs/state/canonical-trading-status.md;  M orchestrator/reports/canonical_trading_status_latest.json; ?? HERMES_METRICS.json; ?? docs/context/ledger-watchdog-2026-06-15.md`
- `git rev-parse HEAD` exit=0: `ddcfbdbd197b4aa8665cb3829f79f609f75d9601`
- `git remote -v` exit=0: `origin	git@github.com-trading:GoLukeEnviro/trading-hub.git (fetch); origin	git@github.com-trading:GoLukeEnviro/trading-hub.git (push); origin-https	https://github.com/GoLukeEnviro/trading-hub.git (fetch); origin-https	https://github.com/GoL…`
- `git config --get remote.origin.url` exit=0: `git@github.com-trading:GoLukeEnviro/trading-hub.git`

Ref ambiguity finding:
- `git rev-parse origin/main` returned `9ceeedd3dfc390ab63392f3384ea662aebffb351` with stderr `warning: refname 'origin/main' is ambiguous.`.
- Fully qualified `refs/remotes/origin/main` was used for calculations to avoid the local `refs/heads/origin/main` shadowing problem.
  - `refs/heads/main` => `ddcfbdbd197b4aa8665cb3829f79f609f75d9601`
  - `refs/heads/origin/main` => `9ceeedd3dfc390ab63392f3384ea662aebffb351`
  - `refs/remotes/origin/main` => `ddcfbdbd197b4aa8665cb3829f79f609f75d9601`
  - `refs/remotes/origin-https/main` => `29cc474ee6db5640cc4763d90bf282ac434303b5`

## 3. Open PR Inventory: number, title, head, base, draft status, mergeability, age, risk

| PR | Title | Head | Base | Draft | Mergeable | Updated | Ahead/Behind | Conflict | Risk | Decision | Reason |
|---:|---|---|---|---|---|---|---|---|---|---|---|
| 205 | si-v2: add first read-only Freqtrade REST shadow proposal proof | `feat/si-v2-first-rest-shadowproposal-proof` | `main` | False | conflicting | 2026-06-13T11:57:38Z | 2/15 | True | DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| 159 | [SI v2][Proof] Controller active cycle proof — CONTROLLER-ACTIVE-PROOF completed | `feat/si-v2-controller-active-proof` | `main` | False | conflicting | 2026-06-11T15:03:08Z | 1/117 | True | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| 71 | [SI v2] Plan v1 residue archive and migration closure (#27) | `docs/si-v2-issue-27-v1-residue-closure` | `main` | False | mergeable | 2026-06-10T11:06:37Z | 1/205 | False | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge. |
| 70 | [SI v2] Design cron activation ceremony and jobs.json guardrails (#26) | `docs/si-v2-issue-26-cron-activation-ceremony` | `main` | False | mergeable | 2026-06-10T11:06:32Z | 1/205 | False | DOCS_LOW_RISK,RUNTIME_HIGH_RISK,SI_V2_CORE | **BLOCKED** | open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge. |
| 69 | [SI v2] Design Telegram approval live adapter with token <redacted> (#25) | `docs/si-v2-issue-25-telegram-approval-design` | `main` | False | mergeable | 2026-06-10T11:04:46Z | 1/205 | False | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge. |

## 4. Closed/Merged PR Inventory: recently merged or superseded work

Merged PRs are treated as `SUPERSEDED`; closed-unmerged PRs are `ARCHIVE_CLOSE_CANDIDATE` unless a human reopens scope on a fresh branch.

| PR | State | Title | Head | Merged/Closed | Decision |
|---:|---|---|---|---|---|
| 219 | merged | docs: add #200 phase B2 L3 adoption execution plan | `docs/phase-b2-l3-compose-adoption-plan-200` | 2026-06-15T07:51:34Z | **SUPERSEDED** |
| 218 | merged | fix: align hermes-watchdog compose network before adoption | `fix/phase2-hermes-watchdog-compose-network` | 2026-06-15T07:37:13Z | **SUPERSEDED** |
| 217 | merged | docs: publish #200 runtime ownership map audit | `docs/phase2-runtime-ownership-map-200` | 2026-06-14T22:30:02Z | **SUPERSEDED** |
| 216 | merged | docs: reconcile Trading Hub state and add blocker-first Roadmap v2 | `docs/roadmap-v2-runtime-ownership-reconciliation` | 2026-06-14T22:08:21Z | **SUPERSEDED** |
| 215 | merged | si-v2: add Rainbow read_only runtime source env overrides | `feat/si-v2-rainbow-read-only-runtime-source-v1` | 2026-06-14T20:43:00Z | **SUPERSEDED** |
| 214 | merged | si-v2: enable Rainbow observation in scheduled Active Cycle via env-var override | `feat/si-v2-rainbow-enable-observation-v1` | 2026-06-14T17:16:23Z | **SUPERSEDED** |
| 213 | merged | si-v2: integrate Rainbow read_only signals into active cycle ledger | `feat/si-v2-rainbow-cycle-ledger-integration-v1` | 2026-06-14T13:07:33Z | **SUPERSEDED** |
| 212 | merged | feat(si-v2): add rainbow read-only signal client | `feat/si-v2-rainbow-read-only-client-v1` | 2026-06-14T01:42:57Z | **SUPERSEDED** |
| 211 | merged | si-v2: wire passive Measurement Ledger into Active Cycle Runner | `feat/si-v2-runner-ledger-integration` | 2026-06-13T19:02:09Z | **SUPERSEDED** |
| 210 | merged | si-v2: add Measurement and Attribution Ledger v1 | `feat/si-v2-measurement-ledger-v1` | 2026-06-13T18:46:03Z | **SUPERSEDED** |
| 209 | merged | si-v2: add multi-signal fusion for actionable ShadowProposals | `feat/si-v2-signal-fusion-v1` | 2026-06-13T16:54:15Z | **SUPERSEDED** |
| 208 | merged | si-v2: add Active Multi-Bot Cycle Runner v1 | `feat/si-v2-active-cycle-runner-v1` | 2026-06-13T14:43:03Z | **SUPERSEDED** |
| 207 | merged | si-v2: add minimal read-only Freqtrade JWT auth | `feat/si-v2-readonly-freqtrade-jwt-auth` | 2026-06-13T11:57:37Z | **SUPERSEDED** |
| 206 | merged | si-v2: fix Freqtrade read-only registry to use Docker DNS | `fix/si-v2-freqtrade-registry-docker-dns` | 2026-06-13T09:39:49Z | **SUPERSEDED** |
| 204 | merged | infra: add deterministic Docker healthchecks for Freqtrade fleet | `feat/issue-199-freqtrade-healthchecks` | 2026-06-13T08:57:31Z | **SUPERSEDED** |
| 203 | merged | si-v2: Stage B one-shot proof artifact (issue #202) | `si-v2/issue-202-one-shot-proof` | 2026-06-13T08:20:49Z | **SUPERSEDED** |
| 198 | merged | test: GREEN PR for branch protection validation (v2) | `test-191-green-pr-v2` | 2026-06-12T18:50:45Z | **SUPERSEDED** |
| 197 | closed | test: GREEN PR for branch protection validation | `test-191-green-pr` | 2026-06-12T18:47:32Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 196 | closed | test: failing check for branch protection validation | `test-191-failing-check` | 2026-06-12T18:47:31Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 195 | merged | ci: add always-reporting main-gate workflow for branch protection | `feat/issue-191-main-gate-workflow` | 2026-06-12T18:32:11Z | **SUPERSEDED** |
| 194 | merged | feat(si-v2): deterministic weekly proposal review cadence policy | `docs/si-v2-issue-66-weekly-review-cadence` | 2026-06-12T18:14:05Z | **SUPERSEDED** |
| 193 | merged | feat(si-v2): fail-closed scheduler activation ceremony and jobs.json guardrails | `docs/si-v2-issue-26-activation-ceremony-v2` | 2026-06-12T18:06:53Z | **SUPERSEDED** |
| 192 | merged | fix: harden SHA validation with regression tests for 593d55e | `fix/si-v2-sha-validation-regression-tests` | 2026-06-12T17:57:44Z | **SUPERSEDED** |
| 190 | merged | [SI v2] feat: add reusable controller baseline reconciliation command (#175) | `feat/si-v2-issue-175-controller-baseline-reconciliation` | 2026-06-12T17:35:16Z | **SUPERSEDED** |
| 189 | merged | [SI v2] ci: add dedicated Phase 2 proposal-stack CI gate (#182) | `ci/si-v2-issue-182-phase2-proposal-gate` | 2026-06-12T17:31:48Z | **SUPERSEDED** |
| 188 | merged | [SI v2] feat: implement Validation Gate Matrix for Phase 2 proposal review (#65) | `feat/si-v2-issue-65-validation-gate-matrix` | 2026-06-12T17:30:09Z | **SUPERSEDED** |
| 187 | merged | [SI v2] test: real no-mock Phase 2 end-to-end integration proof (#181) | `test/si-v2-issue-181-phase2-e2e-integration` | 2026-06-12T17:24:45Z | **SUPERSEDED** |
| 186 | merged | [SI v2] fix: harden episode report contracts — SHA-256, timestamps, verdict truth table, duplicate ID rejection, fingerprint provenance (#185) | `fix/si-v2-issue-185-episode-contract-hardening` | 2026-06-12T16:50:23Z | **SUPERSEDED** |
| 184 | merged | [SI v2][Phase 2] Implement episode report builder for proposal review workflow (#64) | `feat/si-v2-issue-64-episode-report` | 2026-06-12T09:44:56Z | **SUPERSEDED** |
| 183 | merged | [SI v2][Phase 2] Implement Weight Proposal Engine with human-approval output only (#63) | `feat/si-v2-issue-63-weight-proposal-engine` | 2026-06-12T09:37:49Z | **SUPERSEDED** |
| 174 | merged | feat(si-v2): add proposal scoring and promotion policy (issue #35) | `feat/si-v2-issue-35-proposal-scoring-policy` | 2026-06-12T08:41:58Z | **SUPERSEDED** |
| 173 | merged | docs(si-v2): add market-data readiness specification — issue #34 | `docs/si-v2-issue-34-market-data-readiness` | 2026-06-12T00:05:10Z | **SUPERSEDED** |
| 172 | merged | feat(si-v2): harden issue #62 — evidence input pipeline with full typed contract | `feat/si-v2-phase2-evidence-pipeline-hardened` | 2026-06-11T23:57:48Z | **SUPERSEDED** |
| 171 | merged | docs(si-v2): Phase 0/Phase 1 reconciliation — close #46, #60, #61 | `docs/si-v2-phase0-reconciliation-20260611` | 2026-06-11T23:25:48Z | **SUPERSEDED** |
| 170 | closed | feat(si-v2): Phase 2 — Evidence Input Pipeline | `feat/si-v2-phase2-evidence-input-pipeline` | 2026-06-11T23:28:52Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 169 | merged | feat(si-v2): harden issue #60 — derived SQLite cache maintenance with copy-on-write safety | `feat/issue-60-cache-maintenance` | 2026-06-11T23:19:48Z | **SUPERSEDED** |
| 168 | closed | docs(si-v2): Phase 0 reconciliation - update stale docs after #55-#59 merge | `docs/si-v2-phase0-reconciliation-20260611` | 2026-06-11T23:22:11Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 167 | closed | docs(si-v2): branch/PR hygiene inventory report for #46 | `docs/si-v2-branch-hygiene-report` | 2026-06-11T22:33:33Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 166 | merged | feat(si-v2): implement issue #59 — automated attribution reports | `feat/si-v2-issue-59-attribution-reports` | 2026-06-11T21:30:01Z | **SUPERSEDED** |
| 165 | merged | feat(si-v2): implement issue #58 — source_regime_stats SQLite cache | `feat/si-v2-issue-58-source-regime-stats` | 2026-06-11T21:14:03Z | **SUPERSEDED** |
| 164 | merged | feat(si-v2): implement issue #57 — Performance Attribution Engine | `feat/si-v2-issue-57-performance-attribution` | 2026-06-11T20:24:22Z | **SUPERSEDED** |
| 163 | merged | feat(si-v2): implement issue #56 — regime detector run and Shadowlock enrichment | `feat/si-v2-issue-56-regime-shadowlock-enrichment` | 2026-06-11T20:08:55Z | **SUPERSEDED** |
| 162 | merged | docs(si-v2): post-controller documentation reconciliation (PR #160) | `docs/si-v2-post-controller-reconciliation` | 2026-06-11T19:29:17Z | **SUPERSEDED** |
| 161 | merged | [SI v2][Phase 1] Canonical Regime Detector Schema (#55) | `feat/si-v2-issue-55-regime-schema` | 2026-06-11T19:19:51Z | **SUPERSEDED** |
| 160 | merged | fix(controller): repair state contract, separate mutable state, real active cycle proof | `fix/si-v2-controller-state-contract` | 2026-06-11T18:30:08Z | **SUPERSEDED** |
| 158 | merged | [SI v2] Canonical planning automation branch (reconciles #155 + #156 + #145) | `feat/si-v2-canonical-ci-pending` | 2026-06-11T13:15:37Z | **SUPERSEDED** |
| 157 | merged | [SI v2] Continuous controller control plane | `chore/si-v2-continuous-controller-control-plane` | 2026-06-11T14:27:33Z | **SUPERSEDED** |
| 156 | closed | [SI v2] Add planning automation and quality layer (#143–#154) | `feat/si-v2-143-154-planning-automation-quality` | 2026-06-11T13:23:01Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 155 | closed | [SI v2] Add planning pipeline automation layer (#143 #144 #145 #146 #147 #149) | `feat/si-v2-issue-143-147-149-planning-automation` | 2026-06-11T13:22:58Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 142 | merged | [SI v2] Add rehearsal planning gate layer (#135 #136 #137 #138 #139 #140) | `feat/si-v2-issue-135-140-rehearsal-planning-gate` | 2026-06-10T18:56:43Z | **SUPERSEDED** |
| 141 | merged | [SI v2] Add rehearsal-control layer (#127 #128 #129 #130 #131 #132) | `feat/si-v2-issue-127-132-rehearsal-control` | 2026-06-10T18:14:57Z | **SUPERSEDED** |
| 134 | merged | [SI v2] Add offline smoke CI, governance, approval, progress, blockers, and runbook (#120 #121 #122 #123 #124 #125) | `feat/si-v2-issue-120-125-governance-ci-approval-runbook` | 2026-06-10T16:40:09Z | **SUPERSEDED** |
| 133 | merged | [SI v2] Add offline episode, reports, readiness, and architecture index (#97 #114 #115 #116 #117 #118) | `feat/si-v2-issue-97-114-118-offline-episode-readiness-architecture` | 2026-06-10T15:14:51Z | **SUPERSEDED** |
| 126 | merged | [SI v2] Add offline golden path, evidence, regime, attribution, and quality gate (#107 #108 #109 #110 #111 #112) | `feat/si-v2-issue-107-112-goldenpath-evidence-regime-attribution-qagate` | 2026-06-10T15:04:30Z | **SUPERSEDED** |
| 119 | merged | [SI v2] Add source, evidence, and episode foundation (#100 #101 #102 #103 #104) | `feat/si-v2-issue-100-104-source-evidence-episode-foundation` | 2026-06-10T13:56:22Z | **SUPERSEDED** |
| 113 | merged | [SI v2][Rainbow] Add Shadowlock audit event mapper (#81) | `feat/si-v2-issue-81-shadowlock-external-signal-audit-events` | 2026-06-10T13:34:59Z | **SUPERSEDED** |
| 106 | merged | [SI v2][Rainbow] Add fixture report, status, and read-only client (#84 #85 #80) | `feat/si-v2-issue-84-85-80-rainbow-report-status-client` | 2026-06-10T13:28:01Z | **SUPERSEDED** |
| 105 | merged | [SI v2][Rainbow] Add contract snapshot and drift guard (#82 #83) | `feat/si-v2-issue-82-rainbow-contract-snapshot` | 2026-06-10T13:18:42Z | **SUPERSEDED** |
| 99 | merged | [SI v2][PR36] Add post-merge reconciliation report (#93) | `docs/si-v2-issue-93-pr36-reconciliation` | 2026-06-10T13:05:32Z | **SUPERSEDED** |
| 91 | merged | [SI v2][Rainbow] Add signal envelope validator with fixture tests (#79) | `feat/si-v2-issue-79-rainbow-envelope-validator` | 2026-06-10T12:54:55Z | **SUPERSEDED** |
| 78 | merged | [SI v2] Implement read-only runtime adapter prototypes behind env gate (#21) | `feat/si-v2-issue-21-adapter-prototypes-v2` | 2026-06-10T12:06:40Z | **SUPERSEDED** |
| 77 | merged | [SI v2][Phase 0] Fix FleetRiskManager missing state fallback (#43) | `fix/si-v2-issue-43-fleetri<redacted-token>` | 2026-06-10T11:39:08Z | **SUPERSEDED** |
| 76 | merged | [SI v2] Canonical roadmap, README, and .gitignore baseline (#47) | `docs/si-v2-issue-47-roadmap-baseline` | 2026-06-10T11:37:26Z | **SUPERSEDED** |
| 75 | merged | [SI v2] Connect Shadowlock Writer to incremental Indexer trigger (#45) | `feat/si-v2-issue-45-shadowlock-writer-indexer-trigger` | 2026-06-10T11:38:48Z | **SUPERSEDED** |
| 74 | merged | [SI v2] Implement shadowlock SQLite read-cache indexer (#12) | `feat/si-v2-issue-12-shadowlock-indexer` | 2026-06-10T11:38:34Z | **SUPERSEDED** |
| 73 | closed | [SI v2] Document watchdog connectivity target root cause (#39) | `docs/si-v2-issue-39-watchdog-connectivity` | 2026-06-11T13:23:05Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 72 | closed | [SI v2] Document rebel Telegram polling conflict root cause (#38) | `docs/si-v2-issue-38-telegram-conflict-rca` | 2026-06-11T13:23:03Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 68 | closed | [SI v2] Implement read-only runtime adapter prototypes behind env gate (#21) | `feat/si-v2-issue-21-adapter-prototypes` | 2026-06-10T12:07:35Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 54 | merged | [SI v2] Design read-only Docker/Freqtrade adapter contracts after runtime probe (#20) | `docs/si-v2-issue-20-adapter-contracts` | 2026-06-10T11:38:15Z | **SUPERSEDED** |
| 53 | merged | [SI v2] Strengthen CI safety gates and forbidden-pattern regression suite (#31) | `feat/si-v2-issue-31-ci-safety-gates` | 2026-06-10T11:37:46Z | **SUPERSEDED** |
| 52 | merged | [SI v2] Add safety status reporting layer with CLI (#30) | `feat/si-v2-issue-30-status-reporting` | 2026-06-10T11:38:00Z | **SUPERSEDED** |
| 51 | merged | [SI v2] Consolidate project documentation and decision log (#32) | `docs/si-v2-issue-32-consolidate-docs-index` | 2026-06-10T11:37:05Z | **SUPERSEDED** |
| 50 | merged | [SI v2] ADR: Decide watchdog ownership between SI v2 and ai4trade-bot (#23) | `docs/si-v2-issue-23-watchdog-ownership-adr` | 2026-06-10T11:36:46Z | **SUPERSEDED** |
| 49 | merged | [SI v2] Define RiskGuard and ShadowLogger runtime safety contract (#22) | `docs/si-v2-issue-22-riskguard-shadowlogger-contract` | 2026-06-10T11:36:26Z | **SUPERSEDED** |
| 42 | merged | fix(tools): support multiple Freqtrade trade DB schemas | `extract/export-trade-history-multi-schema` | 2026-06-10T09:12:01Z | **SUPERSEDED** |
| 36 | merged | [SI v2] Self-Improvement foundation, safety gates, dry-run pipeline, and runtime probe planning. | `feat/si-v2-foundation` | 2026-06-10T09:42:05Z | **SUPERSEDED** |
| 13 | closed | [WIP] feat: shadowlock_indexer.py — SQLite read-cache for JSONL ledger (Issue #12) | `copilot/fix-212666996-1237110730-965175f3-a5a3-495f-8aa4-ecd03192f16a` | 2026-06-10T08:55:37Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 11 | merged | feat: implement orchestrator spec, trade-history tooling, and shadowlock service (Issue #9) | `feat/hermes-issue-9-complete` | 2026-06-07T20:04:56Z | **SUPERSEDED** |
| 10 | closed | Complete agent stack foundation: orchestrator episode spec, trade-history export CLI, and Shadowlock writer service | `copilot/feat-complete-agent-stack` | 2026-06-10T08:55:32Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 8 | merged | feat: add agent specs and shadowlock directory structure | `feat/agent-specs-shadowlock-2026-06-07` | 2026-06-07T20:04:49Z | **SUPERSEDED** |
| 7 | merged | fix: telegram polling conflict — persistent resolution batch 2a | `fix/telegram-polling-conflict-batch2a-20260606` | 2026-06-07T13:48:49Z | **SUPERSEDED** |
| 6 | merged | fix: stabilize telegram and cron hygiene batch 1 | `fix/telegram-hygiene-batch1-clean-20260606` | 2026-06-06T07:30:14Z | **SUPERSEDED** |
| 5 | closed | fix: stabilize cron and telegram hygiene batch 1 | `fix/telegram-hygiene-batch1-20260606` | 2026-06-06T07:19:06Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 4 | closed | fix: complete PR #3 clean/main rebuild | `copilot/c-vmach-mir-das-biuttte-fertig-komplett` | 2026-06-02T12:57:31Z | **ARCHIVE_CLOSE_CANDIDATE** |
| 3 | merged | Clean/main rebuild | `clean/main-rebuild` | 2026-06-02T12:41:01Z | **SUPERSEDED** |
| 2 | merged | chore: harden trading permission guard and signal runtime writes | `chore/permission-hardening-guardian` | 2026-05-21T11:44:07Z | **SUPERSEDED** |
| 1 | merged | chore: secure Trading Hub git workflow and version critical files | `feat/trading-workflow-cleanup` | 2026-05-16T18:14:48Z | **SUPERSEDED** |

## 5. Branch Inventory: local and remote branches with ahead/behind counts

Base for ahead/behind: `refs/remotes/origin/main`. Counts are `ahead/behind` from branch relative to canonical base. Every non-canonical local/remote ref is listed.

| Type | Branch | Head | Date | Ahead | Behind | Open PR | Closed PRs | Conflict | Risk | Decision | Reason |
|---|---|---|---|---:|---:|---:|---|---|---|---|---|
| local | `docs/phase-b2-l3-compose-adoption-plan-200` | `635c5cdf8140` | 2026-06-15 07:47:09 +0000 | 0 | 1 |  | 219 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `docs/phase2-runtime-ownership-map-200` | `d20bb5a5c052` | 2026-06-14 22:25:27 +0000 | 1 | 5 |  | 217 | no | DOCS_LOW_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| local | `docs/readme-refresh-current-state` | `29f6d2cebcf7` | 2026-06-10 10:40:03 +0000 | 1 | 205 |  |  | yes | DOCS_LOW_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| local | `docs/roadmap-v2-runtime-ownership-reconciliation` | `ae94159c53ff` | 2026-06-14 22:03:40 +0000 | 1 | 6 |  | 216 | no | DOCS_LOW_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| local | `docs/si-v2-issue-25-telegram-approval-design` | `2151e03f9ca9` | 2026-06-10 10:59:59 +0000 | 1 | 205 | #69 |  | no | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge. |
| local | `docs/si-v2-issue-26-cron-activation-ceremony` | `9f3328c094a7` | 2026-06-10 11:00:59 +0000 | 1 | 205 | #70 |  | no | DOCS_LOW_RISK,RUNTIME_HIGH_RISK,SI_V2_CORE | **BLOCKED** | open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge. |
| local | `docs/si-v2-issue-27-v1-residue-closure` | `87316887c1a1` | 2026-06-10 11:01:46 +0000 | 1 | 205 | #71 |  | no | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge. |
| local | `docs/si-v2-issue-38-telegram-conflict-rca` | `b965ec4a6c6e` | 2026-06-10 11:03:32 +0000 | 1 | 205 |  | 72 | yes | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| local | `docs/si-v2-issue-39-watchdog-connectivity` | `d0c33298e419` | 2026-06-10 11:05:00 +0000 | 1 | 205 |  | 73 | yes | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| local | `docs/si-v2-issue-93-pr36-reconciliation` | `71074bcb88e7` | 2026-06-10 12:55:08 +0000 | 0 | 170 |  | 99 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-143-154-planning-automation-quality` | `ca5d1142949e` | 2026-06-10 19:38:08 +0000 | 5 | 111 |  | 156 | no | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | **CHERRY_PICK_CANDIDATE** | mixed docs plus high/unknown-risk content; cherry-pick only valuable low-risk pieces after review. |
| local | `feat/si-v2-active-cycle-runner-v1` | `eb34b1dfc374` | 2026-06-13 13:06:25 +0000 | 3 | 14 |  | 208 | yes | SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| local | `feat/si-v2-canonical-ci-pending` | `58b3acc17409` | 2026-06-11 10:52:58 +0000 | 0 | 104 |  | 158 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-canonical-planning-reconciliation` | `5b0a96a1452a` | 2026-06-11 12:19:51 +0000 | 2 | 104 |  |  | no | DOCS_LOW_RISK,SI_V2_CORE,TESTS_VALIDATION | **CHERRY_PICK_CANDIDATE** | mixed docs plus high/unknown-risk content; cherry-pick only valuable low-risk pieces after review. |
| local | `feat/si-v2-controller-active-proof` | `fc368d6452a9` | 2026-06-11 15:02:53 +0000 | 1 | 117 | #159 |  | yes | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| local | `feat/si-v2-issue-100-104-source-evidence-episode-foundation` | `89125d4d3b8f` | 2026-06-10 13:38:35 +0000 | 0 | 154 |  | 119 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-issue-107-112-goldenpath-evidence-regime-attribution-qagate` | `f7fe1f9680b9` | 2026-06-10 14:01:59 +0000 | 0 | 147 |  | 126 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-issue-120-125-governance-ci-approval-runbook` | `a42027e4af52` | 2026-06-10 16:35:46 +0000 | 0 | 117 |  | 134 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-issue-127-132-rehearsal-control` | `b075ebf2209e` | 2026-06-10 18:10:07 +0000 | 0 | 114 |  | 141 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-issue-135-140-rehearsal-planning-gate` | `f0215bc2c502` | 2026-06-10 18:27:14 +0000 | 0 | 112 |  | 142 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-issue-143-147-149-planning-automation` | `f7a75038278a` | 2026-06-10 19:10:06 +0000 | 1 | 111 |  | 155 | yes | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| local | `feat/si-v2-issue-21-adapter-prototypes` | `172e4ee5f9e7` | 2026-06-10 10:58:56 +0000 | 1 | 205 |  | 68 | yes | SI_V2_CORE | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| local | `feat/si-v2-issue-21-adapter-prototypes-v2` | `318dd08021f9` | 2026-06-10 12:03:16 +0000 | 0 | 177 |  | 78 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-issue-79-rainbow-envelope-validator` | `1f06fa5ab290` | 2026-06-10 12:24:10 +0000 | 0 | 174 |  | 91 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-issue-81-shadowlock-external-signal-audit-events` | `82459048575a` | 2026-06-10 13:30:48 +0000 | 0 | 159 |  | 113 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-issue-82-rainbow-contract-snapshot` | `e281a22fc75e` | 2026-06-10 13:09:37 +0000 | 0 | 166 |  | 105 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-issue-84-85-80-rainbow-report-status-client` | `9969afb614c4` | 2026-06-10 13:22:28 +0000 | 0 | 161 |  | 106 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-issue-97-114-118-offline-episode-readiness-architecture` | `99a68bec8752` | 2026-06-10 15:09:06 +0000 | 0 | 137 |  | 133 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `feat/si-v2-measurement-ledger-v1` | `7f1c8625aa41` | 2026-06-13 18:17:42 +0000 | 1 | 12 |  | 210 | yes | SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| local | `feat/si-v2-rainbow-cycle-ledger-integration-v1` | `2653c10bf6f7` | 2026-06-14 12:08:22 +0000 | 1 | 10 |  | 213 | yes | SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| local | `feat/si-v2-rainbow-enable-observation-v1` | `ccad4cd31d9d` | 2026-06-14 17:12:55 +0000 | 1 | 8 |  | 214 | yes | SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| local | `feat/si-v2-rainbow-read-only-client-v1` | `2812db1b2d39` | 2026-06-14 01:27:01 +0000 | 1 | 10 |  | 212 | no | DOCS_LOW_RISK,SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| local | `feat/si-v2-rainbow-read-only-runtime-source-v1` | `9094b3c83e6c` | 2026-06-14 19:52:25 +0000 | 1 | 7 |  | 215 | no | DOCS_LOW_RISK,SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| local | `feat/si-v2-readonly-freqtrade-jwt-auth` | `44dceda27a2b` | 2026-06-13 11:44:20 +0000 | 4 | 15 |  | 207 | yes | DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| local | `feat/si-v2-runner-ledger-integration` | `6eaf1d2e6ea9` | 2026-06-13 19:00:33 +0000 | 2 | 11 |  | 211 | yes | SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| local | `feat/si-v2-signal-fusion-v1` | `9c8730a80cf2` | 2026-06-13 16:52:30 +0000 | 2 | 13 |  | 209 | yes | SI_V2_CORE,TRADING_HIGH_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| local | `fix/phase2-hermes-watchdog-compose-network` | `4f40bc585d18` | 2026-06-14 22:40:42 +0000 | 0 | 3 |  | 218 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `fix/si-v2-controller-state-contract` | `adc7632444db` | 2026-06-11 18:15:19 +0000 | 0 | 69 |  | 160 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `heads/origin/main` | `9ceeedd3dfc3` | 2026-06-14 22:43:00 +0200 | 0 | 6 |  |  | no | DOCS_LOW_RISK | **SUPERSEDED** | remote/local main alias, not a feature branch; keep read-only, clean only via explicit ref cleanup approval. |
| local | `local/si-v2-controller-pr157-completion` | `7146cda72e2a` | 2026-06-11 14:32:07 +0000 | 1 | 74 |  |  | yes | SI_V2_CORE,UNKNOWN_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| local | `pr-134-audit` | `0f7f8f746bac` | 2026-06-10 15:20:44 +0000 | 0 | 126 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `rescue/phase2-critical-coverage-hardening-pre-main-unblock-20260615T081140Z` | `b61c90ce066a` | 2026-06-15 00:30:02 +0200 | 0 | 4 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `review/pr-105-rainbow-contract-drift` | `e281a22fc75e` | 2026-06-10 13:09:37 +0000 | 0 | 166 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `review/pr-106-rainbow-report-status-client` | `9969afb614c4` | 2026-06-10 13:22:28 +0000 | 0 | 161 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `review/pr-113-rainbow-shadowlock-events` | `82459048575a` | 2026-06-10 13:30:48 +0000 | 0 | 159 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `review/pr-119-source-evidence-episode` | `89125d4d3b8f` | 2026-06-10 13:38:35 +0000 | 0 | 154 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `review/pr-126-offline-pipeline` | `d8433e0acda2` | 2026-06-10 15:04:17 +0000 | 0 | 146 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `review/pr-133-offline-episode-readiness` | `c042cd20b7dc` | 2026-06-10 15:14:28 +0000 | 0 | 136 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `review/pr-78-issue-21-adapters` | `318dd08021f9` | 2026-06-10 12:03:16 +0000 | 0 | 177 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `review/pr-99-pr36-reconciliation` | `71074bcb88e7` | 2026-06-10 12:55:08 +0000 | 0 | 170 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `temp-ci-pending` | `c20aa0a11737` | 2026-06-11 12:32:19 +0000 | 0 | 102 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| local | `test/phase2-critical-coverage-hardening` | `b61c90ce066a` | 2026-06-15 00:30:02 +0200 | 0 | 4 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/chore/si-v2-continuous-controller-control-plane` | `98b0e9451a85` | 2026-06-11 10:43:17 +0000 | 0 | 91 |  | 157 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/docs/si-v2-issue-20-adapter-contracts` | `e48c94870f69` | 2026-06-10 10:50:48 +0000 | 0 | 204 |  | 54 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/docs/si-v2-issue-22-riskguard-shadowlogger-contract` | `995158b42d5d` | 2026-06-10 10:37:24 +0000 | 0 | 204 |  | 49 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/docs/si-v2-issue-23-watchdog-ownership-adr` | `f4a5665aa090` | 2026-06-10 10:39:07 +0000 | 0 | 204 |  | 50 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/docs/si-v2-issue-25-telegram-approval-design` | `2151e03f9ca9` | 2026-06-10 10:59:59 +0000 | 1 | 205 | #69 |  | no | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge. |
| remote | `origin-https/docs/si-v2-issue-26-cron-activation-ceremony` | `9f3328c094a7` | 2026-06-10 11:00:59 +0000 | 1 | 205 | #70 |  | no | DOCS_LOW_RISK,RUNTIME_HIGH_RISK,SI_V2_CORE | **BLOCKED** | open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge. |
| remote | `origin-https/docs/si-v2-issue-27-v1-residue-closure` | `87316887c1a1` | 2026-06-10 11:01:46 +0000 | 1 | 205 | #71 |  | no | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge. |
| remote | `origin-https/docs/si-v2-issue-32-consolidate-docs-index` | `abb05452a3b0` | 2026-06-10 10:40:18 +0000 | 0 | 204 |  | 51 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/docs/si-v2-issue-38-telegram-conflict-rca` | `b965ec4a6c6e` | 2026-06-10 11:03:32 +0000 | 1 | 205 |  | 72 | yes | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin-https/docs/si-v2-issue-39-watchdog-connectivity` | `d0c33298e419` | 2026-06-10 11:05:00 +0000 | 1 | 205 |  | 73 | yes | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin-https/docs/si-v2-issue-47-roadmap-baseline` | `c1e166e04b07` | 2026-06-10 11:28:21 +0000 | 0 | 203 |  | 76 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/docs/si-v2-issue-93-pr36-reconciliation` | `71074bcb88e7` | 2026-06-10 12:55:08 +0000 | 0 | 170 |  | 99 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-143-154-planning-automation-quality` | `ca5d1142949e` | 2026-06-10 19:38:08 +0000 | 5 | 111 |  | 156 | no | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | **CHERRY_PICK_CANDIDATE** | mixed docs plus high/unknown-risk content; cherry-pick only valuable low-risk pieces after review. |
| remote | `origin-https/feat/si-v2-canonical-ci-pending` | `c20aa0a11737` | 2026-06-11 12:32:19 +0000 | 0 | 102 |  | 158 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-100-104-source-evidence-episode-foundation` | `89125d4d3b8f` | 2026-06-10 13:38:35 +0000 | 0 | 154 |  | 119 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-107-112-goldenpath-evidence-regime-attribution-qagate` | `d8433e0acda2` | 2026-06-10 15:04:17 +0000 | 0 | 146 |  | 126 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-12-shadowlock-indexer` | `bf274c2bb710` | 2026-06-10 11:07:48 +0000 | 0 | 204 |  | 74 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-120-125-governance-ci-approval-runbook` | `a42027e4af52` | 2026-06-10 16:35:46 +0000 | 0 | 117 |  | 134 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-127-132-rehearsal-control` | `b075ebf2209e` | 2026-06-10 18:10:07 +0000 | 0 | 114 |  | 141 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-135-140-rehearsal-planning-gate` | `f0215bc2c502` | 2026-06-10 18:27:14 +0000 | 0 | 112 |  | 142 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-143-147-149-planning-automation` | `f7a75038278a` | 2026-06-10 19:10:06 +0000 | 1 | 111 |  | 155 | yes | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin-https/feat/si-v2-issue-21-adapter-prototypes` | `172e4ee5f9e7` | 2026-06-10 10:58:56 +0000 | 1 | 205 |  | 68 | yes | SI_V2_CORE | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin-https/feat/si-v2-issue-21-adapter-prototypes-v2` | `318dd08021f9` | 2026-06-10 12:03:16 +0000 | 0 | 177 |  | 78 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-30-status-reporting` | `55ecb8216544` | 2026-06-10 10:42:31 +0000 | 0 | 204 |  | 52 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-31-ci-safety-gates` | `6352845a8256` | 2026-06-10 10:44:46 +0000 | 0 | 204 |  | 53 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-45-shadowlock-writer-indexer-trigger` | `8578110513ba` | 2026-06-10 11:09:18 +0000 | 0 | 204 |  | 75 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-79-rainbow-envelope-validator` | `1f06fa5ab290` | 2026-06-10 12:24:10 +0000 | 0 | 174 |  | 91 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-81-shadowlock-external-signal-audit-events` | `82459048575a` | 2026-06-10 13:30:48 +0000 | 0 | 159 |  | 113 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-82-rainbow-contract-snapshot` | `e281a22fc75e` | 2026-06-10 13:09:37 +0000 | 0 | 166 |  | 105 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-84-85-80-rainbow-report-status-client` | `9969afb614c4` | 2026-06-10 13:22:28 +0000 | 0 | 161 |  | 106 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/feat/si-v2-issue-97-114-118-offline-episode-readiness-architecture` | `c042cd20b7dc` | 2026-06-10 15:14:28 +0000 | 0 | 136 |  | 133 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/final-mistake-check` | `790187fb500a` | 2026-06-11 00:17:13 +0200 | 0 | 109 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/fix/si-v2-controller-state-contract` | `adc7632444db` | 2026-06-11 18:15:19 +0000 | 0 | 69 |  | 160 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/fix/si-v2-issue-43-fleetri<redacted-token>` | `8ba2510b386d` | 2026-06-10 11:18:25 +0000 | unknown | unknown |  | 77 | unknown | UNKNOWN_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin-https/main` | `29cc474ee6db` | 2026-06-14 03:42:57 +0200 | 0 | 9 |  |  | no | DOCS_LOW_RISK | **SUPERSEDED** | remote/local main alias, not a feature branch; keep read-only, clean only via explicit ref cleanup approval. |
| remote | `origin-https/no-op` | `790187fb500a` | 2026-06-11 00:17:13 +0200 | 0 | 109 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/pr-155` | `f7a75038278a` | 2026-06-10 19:10:06 +0000 | 1 | 111 |  |  | yes | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin-https/pr-156` | `ca5d1142949e` | 2026-06-10 19:38:08 +0000 | 5 | 111 |  |  | no | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | **CHERRY_PICK_CANDIDATE** | mixed docs plus high/unknown-risk content; cherry-pick only valuable low-risk pieces after review. |
| remote | `origin-https/pr-157-full` | `98b0e9451a85` | 2026-06-11 10:43:17 +0000 | 0 | 91 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin-https/pr-72` | `b965ec4a6c6e` | 2026-06-10 11:03:32 +0000 | 1 | 205 |  |  | yes | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin-https/pr-73` | `d0c33298e419` | 2026-06-10 11:05:00 +0000 | 1 | 205 |  |  | yes | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin-https/temp` | `790187fb500a` | 2026-06-11 00:17:13 +0200 | 0 | 109 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/chore/si-v2-continuous-controller-control-plane` | `7146cda72e2a` | 2026-06-11 14:32:07 +0000 | 1 | 74 |  | 157 | yes | SI_V2_CORE,UNKNOWN_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/ci/si-v2-issue-182-phase2-proposal-gate` | `0cf2ea0695f2` | 2026-06-12 17:30:50 +0000 | 0 | 31 |  | 189 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/docs/roadmap-v2-runtime-ownership-reconciliation` | `ae94159c53ff` | 2026-06-14 22:03:40 +0000 | 1 | 6 |  | 216 | no | DOCS_LOW_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/docs/si-v2-branch-hygiene-report` | `9af2e405ccc2` | 2026-06-11 21:51:24 +0000 | 1 | 50 |  | 167 | yes | DOCS_LOW_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin/docs/si-v2-issue-20-adapter-contracts` | `e48c94870f69` | 2026-06-10 10:50:48 +0000 | 0 | 204 |  | 54 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/docs/si-v2-issue-22-riskguard-shadowlogger-contract` | `995158b42d5d` | 2026-06-10 10:37:24 +0000 | 0 | 204 |  | 49 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/docs/si-v2-issue-23-watchdog-ownership-adr` | `f4a5665aa090` | 2026-06-10 10:39:07 +0000 | 0 | 204 |  | 50 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/docs/si-v2-issue-25-telegram-approval-design` | `2151e03f9ca9` | 2026-06-10 10:59:59 +0000 | 1 | 205 | #69 |  | no | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge. |
| remote | `origin/docs/si-v2-issue-26-activation-ceremony-v2` | `8e47b9a4edd4` | 2026-06-12 18:03:08 +0000 | 0 | 24 |  | 193 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/docs/si-v2-issue-26-cron-activation-ceremony` | `9f3328c094a7` | 2026-06-10 11:00:59 +0000 | 1 | 205 | #70 |  | no | DOCS_LOW_RISK,RUNTIME_HIGH_RISK,SI_V2_CORE | **BLOCKED** | open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge. |
| remote | `origin/docs/si-v2-issue-27-v1-residue-closure` | `87316887c1a1` | 2026-06-10 11:01:46 +0000 | 1 | 205 | #71 |  | no | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge. |
| remote | `origin/docs/si-v2-issue-32-consolidate-docs-index` | `abb05452a3b0` | 2026-06-10 10:40:18 +0000 | 0 | 204 |  | 51 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/docs/si-v2-issue-34-market-data-readiness` | `7e9a83f9f165` | 2026-06-12 00:02:37 +0000 | 2 | 42 |  | 173 | no | DOCS_LOW_RISK,SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/docs/si-v2-issue-38-telegram-conflict-rca` | `b965ec4a6c6e` | 2026-06-10 11:03:32 +0000 | 1 | 205 |  | 72 | yes | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin/docs/si-v2-issue-39-watchdog-connectivity` | `d0c33298e419` | 2026-06-10 11:05:00 +0000 | 1 | 205 |  | 73 | yes | DOCS_LOW_RISK,SI_V2_CORE | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin/docs/si-v2-issue-47-roadmap-baseline` | `c1e166e04b07` | 2026-06-10 11:28:21 +0000 | 0 | 203 |  | 76 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/docs/si-v2-issue-66-weekly-review-cadence` | `0b9c18d26c5e` | 2026-06-12 18:13:16 +0000 | 0 | 22 |  | 194 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/docs/si-v2-issue-93-pr36-reconciliation` | `71074bcb88e7` | 2026-06-10 12:55:08 +0000 | 0 | 170 |  | 99 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/docs/si-v2-phase0-reconciliation-20260611` | `c1b6cf03ce32` | 2026-06-11 23:21:42 +0000 | 0 | 44 |  | 171,168 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/docs/si-v2-post-controller-reconciliation` | `b4edf3aeec5f` | 2026-06-11 19:21:23 +0000 | 0 | 61 |  | 162 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/issue-191-main-gate-workflow` | `4dd20f041a28` | 2026-06-12 18:30:55 +0000 | 0 | 20 |  | 195 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/issue-60-cache-maintenance` | `58de5cd0c866` | 2026-06-11 23:18:15 +0000 | 0 | 48 |  | 169 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-143-154-planning-automation-quality` | `ca5d1142949e` | 2026-06-10 19:38:08 +0000 | 5 | 111 |  | 156 | no | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | **CHERRY_PICK_CANDIDATE** | mixed docs plus high/unknown-risk content; cherry-pick only valuable low-risk pieces after review. |
| remote | `origin/feat/si-v2-active-cycle-runner-v1` | `eb34b1dfc374` | 2026-06-13 13:06:25 +0000 | 3 | 14 |  | 208 | yes | SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/feat/si-v2-canonical-ci-pending` | `c20aa0a11737` | 2026-06-11 12:32:19 +0000 | 0 | 102 |  | 158 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-controller-active-proof` | `fc368d6452a9` | 2026-06-11 15:02:53 +0000 | 1 | 117 | #159 |  | yes | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin/feat/si-v2-first-rest-shadowproposal-proof` | `b6b8b97a1a2d` | 2026-06-13 13:57:36 +0200 | 2 | 15 | #205 |  | yes | DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin/feat/si-v2-issue-100-104-source-evidence-episode-foundation` | `89125d4d3b8f` | 2026-06-10 13:38:35 +0000 | 0 | 154 |  | 119 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-107-112-goldenpath-evidence-regime-attribution-qagate` | `d8433e0acda2` | 2026-06-10 15:04:17 +0000 | 0 | 146 |  | 126 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-12-shadowlock-indexer` | `bf274c2bb710` | 2026-06-10 11:07:48 +0000 | 0 | 204 |  | 74 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-120-125-governance-ci-approval-runbook` | `a42027e4af52` | 2026-06-10 16:35:46 +0000 | 0 | 117 |  | 134 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-127-132-rehearsal-control` | `b075ebf2209e` | 2026-06-10 18:10:07 +0000 | 0 | 114 |  | 141 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-135-140-rehearsal-planning-gate` | `f0215bc2c502` | 2026-06-10 18:27:14 +0000 | 0 | 112 |  | 142 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-143-147-149-planning-automation` | `f7a75038278a` | 2026-06-10 19:10:06 +0000 | 1 | 111 |  | 155 | yes | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin/feat/si-v2-issue-175-controller-baseline-reconciliation` | `49f24a4f4108` | 2026-06-12 17:34:02 +0000 | 0 | 29 |  | 190 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-21-adapter-prototypes` | `172e4ee5f9e7` | 2026-06-10 10:58:56 +0000 | 1 | 205 |  | 68 | yes | SI_V2_CORE | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin/feat/si-v2-issue-21-adapter-prototypes-v2` | `318dd08021f9` | 2026-06-10 12:03:16 +0000 | 0 | 177 |  | 78 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-30-status-reporting` | `55ecb8216544` | 2026-06-10 10:42:31 +0000 | 0 | 204 |  | 52 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-31-ci-safety-gates` | `6352845a8256` | 2026-06-10 10:44:46 +0000 | 0 | 204 |  | 53 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-35-proposal-scoring-policy` | `da9a6a2ef26f` | 2026-06-12 08:40:33 +0000 | 1 | 41 |  | 174 | no | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/feat/si-v2-issue-45-shadowlock-writer-indexer-trigger` | `8578110513ba` | 2026-06-10 11:09:18 +0000 | 0 | 204 |  | 75 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-55-regime-schema` | `e0b531037cba` | 2026-06-11 19:11:52 +0000 | 0 | 66 |  | 161 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-56-regime-shadowlock-enrichment` | `0d8b76c178f3` | 2026-06-11 20:01:06 +0000 | 0 | 66 |  | 163 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-57-performance-attribution` | `c803c7b07f67` | 2026-06-11 20:16:21 +0000 | 0 | 56 |  | 164 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-58-source-regime-stats` | `13ce90f1374a` | 2026-06-11 21:08:45 +0000 | 0 | 53 |  | 165 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-59-attribution-reports` | `10a20939a13e` | 2026-06-11 21:24:34 +0000 | 0 | 51 |  | 166 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-63-weight-proposal-engine` | `c0fec2c62d6f` | 2026-06-12 09:36:13 +0000 | 1 | 40 |  | 183 | yes | SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/feat/si-v2-issue-64-episode-report` | `578544c93aa1` | 2026-06-12 09:43:05 +0000 | 1 | 39 |  | 184 | yes | SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/feat/si-v2-issue-65-validation-gate-matrix` | `f8dfb3786c41` | 2026-06-12 17:28:25 +0000 | 0 | 33 |  | 188 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-79-rainbow-envelope-validator` | `1f06fa5ab290` | 2026-06-10 12:24:10 +0000 | 0 | 174 |  | 91 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-81-shadowlock-external-signal-audit-events` | `82459048575a` | 2026-06-10 13:30:48 +0000 | 0 | 159 |  | 113 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-82-rainbow-contract-snapshot` | `e281a22fc75e` | 2026-06-10 13:09:37 +0000 | 0 | 166 |  | 105 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-84-85-80-rainbow-report-status-client` | `9969afb614c4` | 2026-06-10 13:22:28 +0000 | 0 | 161 |  | 106 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-issue-97-114-118-offline-episode-readiness-architecture` | `c042cd20b7dc` | 2026-06-10 15:14:28 +0000 | 0 | 136 |  | 133 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/feat/si-v2-measurement-ledger-v1` | `7f1c8625aa41` | 2026-06-13 18:17:42 +0000 | 1 | 12 |  | 210 | yes | SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/feat/si-v2-phase2-evidence-input-pipeline` | `f89f27fb41aa` | 2026-06-11 22:12:08 +0000 | 1 | 50 |  | 170 | yes | SI_V2_CORE | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin/feat/si-v2-phase2-evidence-pipeline-hardened` | `27a6d3ea0d6f` | 2026-06-11 23:56:28 +0000 | 2 | 43 |  | 172 | yes | SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/feat/si-v2-rainbow-cycle-ledger-integration-v1` | `2653c10bf6f7` | 2026-06-14 12:08:22 +0000 | 1 | 10 |  | 213 | yes | SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/feat/si-v2-rainbow-enable-observation-v1` | `ccad4cd31d9d` | 2026-06-14 17:12:55 +0000 | 1 | 8 |  | 214 | yes | SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/feat/si-v2-rainbow-read-only-client-v1` | `2812db1b2d39` | 2026-06-14 01:27:01 +0000 | 1 | 10 |  | 212 | no | DOCS_LOW_RISK,SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/feat/si-v2-rainbow-read-only-runtime-source-v1` | `9094b3c83e6c` | 2026-06-14 19:52:25 +0000 | 1 | 7 |  | 215 | no | DOCS_LOW_RISK,SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/feat/si-v2-readonly-freqtrade-jwt-auth` | `44dceda27a2b` | 2026-06-13 11:44:20 +0000 | 4 | 15 |  | 207 | yes | DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/feat/si-v2-runner-ledger-integration` | `6eaf1d2e6ea9` | 2026-06-13 19:00:33 +0000 | 2 | 11 |  | 211 | yes | SI_V2_CORE | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/feat/si-v2-signal-fusion-v1` | `9c8730a80cf2` | 2026-06-13 16:52:30 +0000 | 2 | 13 |  | 209 | yes | SI_V2_CORE,TRADING_HIGH_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/final-mistake-check` | `790187fb500a` | 2026-06-11 00:17:13 +0200 | 0 | 109 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/fix/si-v2-controller-state-contract` | `adc7632444db` | 2026-06-11 18:15:19 +0000 | 0 | 69 |  | 160 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/fix/si-v2-freqtrade-registry-docker-dns` | `1cf9d9b72e2c` | 2026-06-13 09:38:27 +0000 | 5 | 15 |  | 206 | yes | DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/fix/si-v2-issue-185-episode-contract-hardening` | `f424a968c20c` | 2026-06-12 16:48:18 +0000 | 0 | 37 |  | 186 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/fix/si-v2-issue-43-fleetri<redacted-token>` | `8ba2510b386d` | 2026-06-10 11:18:25 +0000 | unknown | unknown |  | 77 | unknown | UNKNOWN_RISK | **SUPERSEDED** | matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven. |
| remote | `origin/fix/si-v2-sha-validation-regression-tests` | `3482df82304b` | 2026-06-12 17:55:02 +0000 | 0 | 26 |  | 192 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/no-op` | `790187fb500a` | 2026-06-11 00:17:13 +0200 | 0 | 109 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/temp` | `790187fb500a` | 2026-06-11 00:17:13 +0200 | 0 | 109 |  |  | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/test-191-failing-check` | `a62eef08e07d` | 2026-06-12 18:34:58 +0000 | 1 | 19 |  | 196 | no | SI_V2_CORE | **BLOCKED** | non-open branch touches high/unknown-risk areas without current validation/PR ownership. |
| remote | `origin/test-191-green-pr` | `06f160b7b825` | 2026-06-12 18:35:59 +0000 | 1 | 19 |  | 197 | yes | UNKNOWN_RISK | **BLOCKED** | merge-tree conflict probe reported conflict markers/changed-in-both evidence. |
| remote | `origin/test-191-green-pr-v2` | `a723fa67226c` | 2026-06-12 18:47:34 +0000 | 0 | 18 |  | 198 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |
| remote | `origin/test/si-v2-issue-181-phase2-e2e-integration` | `637f3925723b` | 2026-06-12 17:23:10 +0000 | 0 | 35 |  | 187 | no | UNKNOWN_RISK | **SUPERSEDED** | no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref. |

## 6. Git Tree Findings: divergence, merge bases, duplicate/superseded branches

- Decision counts across non-canonical branch refs: `{'SUPERSEDED': 132, 'BLOCKED': 33, 'CHERRY_PICK_CANDIDATE': 5}`.
- PR decision counts after PR-state normalization: `{'BLOCKED': 5, 'SUPERSEDED': 73, 'ARCHIVE_CLOSE_CANDIDATE': 14}`.
- Duplicate object IDs found for 48 object IDs; many are expected local/remote/pr aliases. Treat as cleanup inventory only.
- `refs/heads/origin/main` shadows `origin/main` and causes ambiguous-ref warnings. This is a repo-clarity risk and should be cleaned only in an explicitly approved ref-cleanup task.
- Many merged PR branches still exist locally/remotely; most are `SUPERSEDED` by main and should not be merged again.
- No `git fetch` was run; remote branch refs are the currently available local remote-tracking refs plus GitHub PR API metadata.

## 7. Risk Classification by File Area

| Risk category | Branch-ref count | Meaning |
|---|---:|---|
| SI_V2_CORE | 60 | self_improvement_v2/**, orchestrator/control/**, intelligence/** |
| RUNTIME_HIGH_RISK | 3 | docker/compose/systemd/scheduler/Caddy/Mem0/Qdrant/Ollama/Hermes-runtime related files |
| TRADING_HIGH_RISK | 8 | Freqtrade/strategy/dry-run/live/exchange/order/RiskGuard/ShadowLogger-impacting files |
| DOCS_LOW_RISK | 45 | docs/**, markdown, report-style docs |
| TESTS_VALIDATION | 1 | tests, pytest config, fixtures, validation/smoke scripts |
| UNKNOWN_RISK | 122 | generated/binary/deleted/large or unclear files |

Multi-bot rule: any SI v2/Freqtrade candidate remains blocked unless it preserves all four Freqtrade bots as first-class targets. PR #205 is explicitly multi-bot-related but conflict-blocked and requires proof before merge.

## 8. Conflict Probe Results

Read-only `git merge-tree` probes found conflict evidence on 42 branch refs. No `git merge` was run.

| Branch | Type | Ahead/Behind | Risk | Open PR | Conflict sample |
|---|---|---|---|---:|---|
| `docs/readme-refresh-current-state` | local | 1/205 | DOCS_LOW_RISK |  | changed in both; +<<<<<<< .our |
| `docs/si-v2-issue-38-telegram-conflict-rca` | local | 1/205 | DOCS_LOW_RISK,SI_V2_CORE |  |   our    100644 b929fc7fda3e6f8c86b57d0b65ab62030daac6ec self_improvement_v2/docs/RCA-REBEL-TELEGRAM-CONFLICT.md;   their  100644 89d07b81c4670297c728625338b5928e0a055e27 self_improvement_v2/docs/RCA-REBEL-TELEGRAM-CONFLICT.md |
| `docs/si-v2-issue-39-watchdog-connectivity` | local | 1/205 | DOCS_LOW_RISK,SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `feat/si-v2-active-cycle-runner-v1` | local | 3/14 | SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK |  | changed in both; +<<<<<<< .our |
| `feat/si-v2-controller-active-proof` | local | 1/117 | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | #159 | +<<<<<<< .our; +>>>>>>> .their |
| `feat/si-v2-issue-143-147-149-planning-automation` | local | 1/111 | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK |  | +<<<<<<< .our; +>>>>>>> .their |
| `feat/si-v2-issue-21-adapter-prototypes` | local | 1/205 | SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `feat/si-v2-measurement-ledger-v1` | local | 1/12 | SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `feat/si-v2-rainbow-cycle-ledger-integration-v1` | local | 1/10 | SI_V2_CORE |  | changed in both; +<<<<<<< .our |
| `feat/si-v2-rainbow-enable-observation-v1` | local | 1/8 | SI_V2_CORE |  | changed in both; +<<<<<<< .our |
| `feat/si-v2-readonly-freqtrade-jwt-auth` | local | 4/15 | DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK |  | +<<<<<<< .our; +>>>>>>> .their |
| `feat/si-v2-runner-ledger-integration` | local | 2/11 | SI_V2_CORE |  | changed in both; +<<<<<<< .our |
| `feat/si-v2-signal-fusion-v1` | local | 2/13 | SI_V2_CORE,TRADING_HIGH_RISK |  | changed in both; +<<<<<<< .our |
| `local/si-v2-controller-pr157-completion` | local | 1/74 | SI_V2_CORE,UNKNOWN_RISK |  | changed in both; +<<<<<<< .our |
| `origin-https/docs/si-v2-issue-38-telegram-conflict-rca` | remote | 1/205 | DOCS_LOW_RISK,SI_V2_CORE |  |   our    100644 b929fc7fda3e6f8c86b57d0b65ab62030daac6ec self_improvement_v2/docs/RCA-REBEL-TELEGRAM-CONFLICT.md;   their  100644 89d07b81c4670297c728625338b5928e0a055e27 self_improvement_v2/docs/RCA-REBEL-TELEGRAM-CONFLICT.md |
| `origin-https/docs/si-v2-issue-39-watchdog-connectivity` | remote | 1/205 | DOCS_LOW_RISK,SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin-https/feat/si-v2-issue-143-147-149-planning-automation` | remote | 1/111 | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin-https/feat/si-v2-issue-21-adapter-prototypes` | remote | 1/205 | SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin-https/pr-155` | remote | 1/111 | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin-https/pr-72` | remote | 1/205 | DOCS_LOW_RISK,SI_V2_CORE |  |   our    100644 b929fc7fda3e6f8c86b57d0b65ab62030daac6ec self_improvement_v2/docs/RCA-REBEL-TELEGRAM-CONFLICT.md;   their  100644 89d07b81c4670297c728625338b5928e0a055e27 self_improvement_v2/docs/RCA-REBEL-TELEGRAM-CONFLICT.md |
| `origin-https/pr-73` | remote | 1/205 | DOCS_LOW_RISK,SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin/chore/si-v2-continuous-controller-control-plane` | remote | 1/74 | SI_V2_CORE,UNKNOWN_RISK |  | changed in both; +<<<<<<< .our |
| `origin/docs/si-v2-branch-hygiene-report` | remote | 1/50 | DOCS_LOW_RISK |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin/docs/si-v2-issue-38-telegram-conflict-rca` | remote | 1/205 | DOCS_LOW_RISK,SI_V2_CORE |  |   our    100644 b929fc7fda3e6f8c86b57d0b65ab62030daac6ec self_improvement_v2/docs/RCA-REBEL-TELEGRAM-CONFLICT.md;   their  100644 89d07b81c4670297c728625338b5928e0a055e27 self_improvement_v2/docs/RCA-REBEL-TELEGRAM-CONFLICT.md |
| `origin/docs/si-v2-issue-39-watchdog-connectivity` | remote | 1/205 | DOCS_LOW_RISK,SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin/feat/si-v2-active-cycle-runner-v1` | remote | 3/14 | SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK |  | changed in both; +<<<<<<< .our |
| `origin/feat/si-v2-controller-active-proof` | remote | 1/117 | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK | #159 | +<<<<<<< .our; +>>>>>>> .their |
| `origin/feat/si-v2-first-rest-shadowproposal-proof` | remote | 2/15 | DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK | #205 | +<<<<<<< .our; +>>>>>>> .their |
| `origin/feat/si-v2-issue-143-147-149-planning-automation` | remote | 1/111 | DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin/feat/si-v2-issue-21-adapter-prototypes` | remote | 1/205 | SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin/feat/si-v2-issue-63-weight-proposal-engine` | remote | 1/40 | SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin/feat/si-v2-issue-64-episode-report` | remote | 1/39 | SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin/feat/si-v2-measurement-ledger-v1` | remote | 1/12 | SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin/feat/si-v2-phase2-evidence-input-pipeline` | remote | 1/50 | SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin/feat/si-v2-phase2-evidence-pipeline-hardened` | remote | 2/43 | SI_V2_CORE |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin/feat/si-v2-rainbow-cycle-ledger-integration-v1` | remote | 1/10 | SI_V2_CORE |  | changed in both; +<<<<<<< .our |
| `origin/feat/si-v2-rainbow-enable-observation-v1` | remote | 1/8 | SI_V2_CORE |  | changed in both; +<<<<<<< .our |
| `origin/feat/si-v2-readonly-freqtrade-jwt-auth` | remote | 4/15 | DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin/feat/si-v2-runner-ledger-integration` | remote | 2/11 | SI_V2_CORE |  | changed in both; +<<<<<<< .our |
| `origin/feat/si-v2-signal-fusion-v1` | remote | 2/13 | SI_V2_CORE,TRADING_HIGH_RISK |  | changed in both; +<<<<<<< .our |
| `origin/fix/si-v2-freqtrade-registry-docker-dns` | remote | 5/15 | DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK |  | +<<<<<<< .our; +>>>>>>> .their |
| `origin/test-191-green-pr` | remote | 1/19 | UNKNOWN_RISK |  | +<<<<<<< .our; +>>>>>>> .their |

## 9. Validation Evidence Found

- Existing report/proof/validation-like files found (tail): 121.
- Validation/proof keyword hits found (tail): 300.
- This is evidence of prior validation artifacts, **not** proof that any current branch is merge-ready.

Recent/tail report-like files:
- `self_improvement_v2/reports/readiness/phase_1_readiness_matrix.md`
- `self_improvement_v2/reports/reconciliation/pr36_post_merge_reconciliation.md`
- `self_improvement_v2/reports/runtime_probe/phase-m2-dryrun-signal-validation-20260610-001/APPROVAL.md`
- `self_improvement_v2/reports/runtime_probe/phase-m2-dryrun-signal-validation-20260610-001/COMMAND_ALLOWLIST.md`
- `self_improvement_v2/reports/runtime_probe/phase-m2-dryrun-signal-validation-20260610-001/evidence.jsonl`
- `self_improvement_v2/reports/runtime_probe/phase-m2-dryrun-signal-validation-20260610-001/fleet_inventory_audit_20260610.md`
- `self_improvement_v2/reports/runtime_probe/phase-m2-dryrun-signal-validation-20260610-001/redaction_report.md`
- `self_improvement_v2/reports/runtime_probe/phase-m2-dryrun-signal-validation-20260610-001/runtime_signal_validation_report.md`
- `self_improvement_v2/reports/runtime_probe/phase_m3_issue_40_dry_run_signal_revalidation.md`
- `self_improvement_v2/reports/shadow_mode_rehearsal_report_template.md`
- `self_improvement_v2/reports/source_readiness_summary.md`
- `self_improvement_v2/tests/fixtures/golden/blocked/report.md`
- `self_improvement_v2/tests/fixtures/golden/pass/report.md`
- `self_improvement_v2/tests/fixtures/golden/warning/report.md`
- `var/trading-self-improvement/artifacts/freqai_repair_and_ai_override_regression_20260607_031152/final_report/report.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/2026-06-05-comprehensive-gap-analysis-report.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/20260528-rebuild-report.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/auth-json-permission-recovery-validation-20260602.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/cron-telegram-post-batch1-validation-20260606.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/dream-mode-memory-recovery-report-20260517.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/dream-mode-v3.1-validation-20260518.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/fleet-health-report-template.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/freqai-rebel-feature-importance-report-2026-05-26.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/freqforge-shadow-evaluator-v0-1-report.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/hermes-primo-freqtrade-mvs-integration-report.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/honcho-dedup-report-2026-05-13.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/memory-cleanup-post-validation-20260602.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/phase-11-local-safety-flow-validation-2026-05-07.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/phase-12-6-orchestrator-gauntlet-report-2026-05-07.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/phase1-completion-report-20260602.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/phase44-stage16-ai-hedge-fund-crypto-ssl-llm-validation.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/rebel-reporting-telegram-20260520.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/report-audit-enhancement-v46-20260525.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/runtime-automation-validation-20260521.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/telegram-hygiene-batch1-post-merge-validation-20260606.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/telegram-hygiene-batch1-runtime-deploy-validation-20260606.md`
- `var/trading-self-improvement/artifacts/regression_and_freqai_repair_20260607_030613/config_snapshots/trading-hub-live-readiness-control-report-20260519.md`
- `weatherhermes_persistent/docs/COMPOSE_MOUNT_PATCH_REPORT_NO_RESTART_20260509.md`
- `weatherhermes_persistent/docs/HOST_PERSISTENCE_REPORT_20260509.md`
- `weatherhermes_persistent/weatherbot_master/docs/context/weatherhermes-v3-3-smoke-test-report-20260509.md`

Sample validation/proof hits:
- `self_improvement_v2/docs/AI4TRADE_COMPATIBILITY_MATRIX.md:48` — \| **Strategy Mutation** \| SI v2 (`strategy_mutator`) \| Unique to SI v2 mutation pipeline \|
- `self_improvement_v2/docs/AI4TRADE_COMPATIBILITY_MATRIX.md:49` — \| **Backtest Runner** \| SI v2 (`backtest_runner`) \| Unique to SI v2 \|
- `self_improvement_v2/docs/AI4TRADE_COMPATIBILITY_MATRIX.md:50` — \| **Walk-Forward** \| SI v2 (`walk_forward`) \| Unique to SI v2 \|
- `self_improvement_v2/docs/AI4TRADE_COMPATIBILITY_MATRIX.md:51` — \| **Deployment Orchestration** \| SI v2 (`deployment_plan`) \| Unique to SI v2 \|
- `self_improvement_v2/docs/AI4TRADE_COMPATIBILITY_MATRIX.md:52` — \| **Shadow Mode** \| SI v2 (`shadow_mode`) \| Unique to SI v2 \|
- `self_improvement_v2/docs/AI4TRADE_COMPATIBILITY_MATRIX.md:53` — \| **Rollback** \| SI v2 (`rollback_plan`) \| Unique to SI v2 \|
- `self_improvement_v2/docs/AI4TRADE_COMPATIBILITY_MATRIX.md:54` — \| **Safe Parameters** \| SI v2 (`safe_parameters`) \| Unique to SI v2 \|
- `self_improvement_v2/docs/AI4TRADE_COMPATIBILITY_MATRIX.md:62` — \| Integration \| Type \| SI v2 Interface \| ai4trade-bot Consumer \|
- `self_improvement_v2/docs/AI4TRADE_COMPATIBILITY_MATRIX.md:70` — \| Integration \| Type \| SI v2 Interface \| ai4trade-bot Consumer \|
- `self_improvement_v2/docs/AI4TRADE_COMPATIBILITY_MATRIX.md:77` — \| Integration \| Type \| SI v2 Interface \| ai4trade-bot Consumer \|
- `tests/test_freqtrade_healthchecks.py:1` — """Static validation tests for Freqtrade Docker healthcheck definitions (issue #199).
- `tests/test_freqtrade_healthchecks.py:14` — import pytest
- `tests/test_freqtrade_healthchecks.py:42` — @pytest.fixture(scope="module")
- `tests/test_freqtrade_healthchecks.py:50` — @pytest.fixture(scope="module")
- `tests/test_freqtrade_healthchecks.py:73` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:78` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:83` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:90` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:97` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:104` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:115` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:123` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:131` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:139` — "hermes-green",
- `tests/test_freqtrade_healthchecks.py:140` — "green-",
- `tests/test_freqtrade_healthchecks.py:148` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:183` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:188` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:193` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)
- `tests/test_freqtrade_healthchecks.py:198` — @pytest.mark.parametrize("service_name", TARGET_SERVICES)

## 10. Decision Matrix

### Branch decisions

#### MERGE_CANDIDATE (0)
- None.
#### CHERRY_PICK_CANDIDATE (5)
- `feat/si-v2-143-154-planning-automation-quality` (local, ahead/behind 5/111, risk DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK): mixed docs plus high/unknown-risk content; cherry-pick only valuable low-risk pieces after review.
- `feat/si-v2-canonical-planning-reconciliation` (local, ahead/behind 2/104, risk DOCS_LOW_RISK,SI_V2_CORE,TESTS_VALIDATION): mixed docs plus high/unknown-risk content; cherry-pick only valuable low-risk pieces after review.
- `origin-https/feat/si-v2-143-154-planning-automation-quality` (remote, ahead/behind 5/111, risk DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK): mixed docs plus high/unknown-risk content; cherry-pick only valuable low-risk pieces after review.
- `origin-https/pr-156` (remote, ahead/behind 5/111, risk DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK): mixed docs plus high/unknown-risk content; cherry-pick only valuable low-risk pieces after review.
- `origin/feat/si-v2-143-154-planning-automation-quality` (remote, ahead/behind 5/111, risk DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK): mixed docs plus high/unknown-risk content; cherry-pick only valuable low-risk pieces after review.
#### SUPERSEDED (132)
- `docs/phase-b2-l3-compose-adoption-plan-200` (local, ahead/behind 0/1, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `docs/phase2-runtime-ownership-map-200` (local, ahead/behind 1/5, risk DOCS_LOW_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `docs/roadmap-v2-runtime-ownership-reconciliation` (local, ahead/behind 1/6, risk DOCS_LOW_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `docs/si-v2-issue-93-pr36-reconciliation` (local, ahead/behind 0/170, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-active-cycle-runner-v1` (local, ahead/behind 3/14, risk SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `feat/si-v2-canonical-ci-pending` (local, ahead/behind 0/104, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-issue-100-104-source-evidence-episode-foundation` (local, ahead/behind 0/154, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-issue-107-112-goldenpath-evidence-regime-attribution-qagate` (local, ahead/behind 0/147, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-issue-120-125-governance-ci-approval-runbook` (local, ahead/behind 0/117, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-issue-127-132-rehearsal-control` (local, ahead/behind 0/114, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-issue-135-140-rehearsal-planning-gate` (local, ahead/behind 0/112, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-issue-21-adapter-prototypes-v2` (local, ahead/behind 0/177, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-issue-79-rainbow-envelope-validator` (local, ahead/behind 0/174, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-issue-81-shadowlock-external-signal-audit-events` (local, ahead/behind 0/159, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-issue-82-rainbow-contract-snapshot` (local, ahead/behind 0/166, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-issue-84-85-80-rainbow-report-status-client` (local, ahead/behind 0/161, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-issue-97-114-118-offline-episode-readiness-architecture` (local, ahead/behind 0/137, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `feat/si-v2-measurement-ledger-v1` (local, ahead/behind 1/12, risk SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `feat/si-v2-rainbow-cycle-ledger-integration-v1` (local, ahead/behind 1/10, risk SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `feat/si-v2-rainbow-enable-observation-v1` (local, ahead/behind 1/8, risk SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `feat/si-v2-rainbow-read-only-client-v1` (local, ahead/behind 1/10, risk DOCS_LOW_RISK,SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `feat/si-v2-rainbow-read-only-runtime-source-v1` (local, ahead/behind 1/7, risk DOCS_LOW_RISK,SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `feat/si-v2-readonly-freqtrade-jwt-auth` (local, ahead/behind 4/15, risk DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `feat/si-v2-runner-ledger-integration` (local, ahead/behind 2/11, risk SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `feat/si-v2-signal-fusion-v1` (local, ahead/behind 2/13, risk SI_V2_CORE,TRADING_HIGH_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `fix/phase2-hermes-watchdog-compose-network` (local, ahead/behind 0/3, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `fix/si-v2-controller-state-contract` (local, ahead/behind 0/69, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `heads/origin/main` (local, ahead/behind 0/6, risk DOCS_LOW_RISK): remote/local main alias, not a feature branch; keep read-only, clean only via explicit ref cleanup approval.
- `origin-https/chore/si-v2-continuous-controller-control-plane` (remote, ahead/behind 0/91, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/docs/si-v2-issue-20-adapter-contracts` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/docs/si-v2-issue-22-riskguard-shadowlogger-contract` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/docs/si-v2-issue-23-watchdog-ownership-adr` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/docs/si-v2-issue-32-consolidate-docs-index` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/docs/si-v2-issue-47-roadmap-baseline` (remote, ahead/behind 0/203, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/docs/si-v2-issue-93-pr36-reconciliation` (remote, ahead/behind 0/170, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-canonical-ci-pending` (remote, ahead/behind 0/102, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-100-104-source-evidence-episode-foundation` (remote, ahead/behind 0/154, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-107-112-goldenpath-evidence-regime-attribution-qagate` (remote, ahead/behind 0/146, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-12-shadowlock-indexer` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-120-125-governance-ci-approval-runbook` (remote, ahead/behind 0/117, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-127-132-rehearsal-control` (remote, ahead/behind 0/114, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-135-140-rehearsal-planning-gate` (remote, ahead/behind 0/112, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-21-adapter-prototypes-v2` (remote, ahead/behind 0/177, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-30-status-reporting` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-31-ci-safety-gates` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-45-shadowlock-writer-indexer-trigger` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-79-rainbow-envelope-validator` (remote, ahead/behind 0/174, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-81-shadowlock-external-signal-audit-events` (remote, ahead/behind 0/159, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-82-rainbow-contract-snapshot` (remote, ahead/behind 0/166, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-84-85-80-rainbow-report-status-client` (remote, ahead/behind 0/161, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/feat/si-v2-issue-97-114-118-offline-episode-readiness-architecture` (remote, ahead/behind 0/136, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/final-mistake-check` (remote, ahead/behind 0/109, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/fix/si-v2-controller-state-contract` (remote, ahead/behind 0/69, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/fix/si-v2-issue-43-fleetri<redacted-token>` (remote, ahead/behind unknown/unknown, risk UNKNOWN_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin-https/main` (remote, ahead/behind 0/9, risk DOCS_LOW_RISK): remote/local main alias, not a feature branch; keep read-only, clean only via explicit ref cleanup approval.
- `origin-https/no-op` (remote, ahead/behind 0/109, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/pr-157-full` (remote, ahead/behind 0/91, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin-https/temp` (remote, ahead/behind 0/109, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/chore/si-v2-continuous-controller-control-plane` (remote, ahead/behind 1/74, risk SI_V2_CORE,UNKNOWN_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/ci/si-v2-issue-182-phase2-proposal-gate` (remote, ahead/behind 0/31, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/docs/roadmap-v2-runtime-ownership-reconciliation` (remote, ahead/behind 1/6, risk DOCS_LOW_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/docs/si-v2-issue-20-adapter-contracts` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/docs/si-v2-issue-22-riskguard-shadowlogger-contract` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/docs/si-v2-issue-23-watchdog-ownership-adr` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/docs/si-v2-issue-26-activation-ceremony-v2` (remote, ahead/behind 0/24, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/docs/si-v2-issue-32-consolidate-docs-index` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/docs/si-v2-issue-34-market-data-readiness` (remote, ahead/behind 2/42, risk DOCS_LOW_RISK,SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/docs/si-v2-issue-47-roadmap-baseline` (remote, ahead/behind 0/203, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/docs/si-v2-issue-66-weekly-review-cadence` (remote, ahead/behind 0/22, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/docs/si-v2-issue-93-pr36-reconciliation` (remote, ahead/behind 0/170, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/docs/si-v2-phase0-reconciliation-20260611` (remote, ahead/behind 0/44, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/docs/si-v2-post-controller-reconciliation` (remote, ahead/behind 0/61, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/issue-191-main-gate-workflow` (remote, ahead/behind 0/20, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/issue-60-cache-maintenance` (remote, ahead/behind 0/48, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-active-cycle-runner-v1` (remote, ahead/behind 3/14, risk SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/feat/si-v2-canonical-ci-pending` (remote, ahead/behind 0/102, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-100-104-source-evidence-episode-foundation` (remote, ahead/behind 0/154, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-107-112-goldenpath-evidence-regime-attribution-qagate` (remote, ahead/behind 0/146, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-12-shadowlock-indexer` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-120-125-governance-ci-approval-runbook` (remote, ahead/behind 0/117, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-127-132-rehearsal-control` (remote, ahead/behind 0/114, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-135-140-rehearsal-planning-gate` (remote, ahead/behind 0/112, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-175-controller-baseline-reconciliation` (remote, ahead/behind 0/29, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-21-adapter-prototypes-v2` (remote, ahead/behind 0/177, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-30-status-reporting` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-31-ci-safety-gates` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-35-proposal-scoring-policy` (remote, ahead/behind 1/41, risk DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/feat/si-v2-issue-45-shadowlock-writer-indexer-trigger` (remote, ahead/behind 0/204, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-55-regime-schema` (remote, ahead/behind 0/66, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-56-regime-shadowlock-enrichment` (remote, ahead/behind 0/66, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-57-performance-attribution` (remote, ahead/behind 0/56, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-58-source-regime-stats` (remote, ahead/behind 0/53, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-59-attribution-reports` (remote, ahead/behind 0/51, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-63-weight-proposal-engine` (remote, ahead/behind 1/40, risk SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/feat/si-v2-issue-64-episode-report` (remote, ahead/behind 1/39, risk SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/feat/si-v2-issue-65-validation-gate-matrix` (remote, ahead/behind 0/33, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-79-rainbow-envelope-validator` (remote, ahead/behind 0/174, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-81-shadowlock-external-signal-audit-events` (remote, ahead/behind 0/159, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-82-rainbow-contract-snapshot` (remote, ahead/behind 0/166, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-84-85-80-rainbow-report-status-client` (remote, ahead/behind 0/161, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-issue-97-114-118-offline-episode-readiness-architecture` (remote, ahead/behind 0/136, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/feat/si-v2-measurement-ledger-v1` (remote, ahead/behind 1/12, risk SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/feat/si-v2-phase2-evidence-pipeline-hardened` (remote, ahead/behind 2/43, risk SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/feat/si-v2-rainbow-cycle-ledger-integration-v1` (remote, ahead/behind 1/10, risk SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/feat/si-v2-rainbow-enable-observation-v1` (remote, ahead/behind 1/8, risk SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/feat/si-v2-rainbow-read-only-client-v1` (remote, ahead/behind 1/10, risk DOCS_LOW_RISK,SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/feat/si-v2-rainbow-read-only-runtime-source-v1` (remote, ahead/behind 1/7, risk DOCS_LOW_RISK,SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/feat/si-v2-readonly-freqtrade-jwt-auth` (remote, ahead/behind 4/15, risk DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/feat/si-v2-runner-ledger-integration` (remote, ahead/behind 2/11, risk SI_V2_CORE): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/feat/si-v2-signal-fusion-v1` (remote, ahead/behind 2/13, risk SI_V2_CORE,TRADING_HIGH_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/final-mistake-check` (remote, ahead/behind 0/109, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/fix/si-v2-controller-state-contract` (remote, ahead/behind 0/69, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/fix/si-v2-freqtrade-registry-docker-dns` (remote, ahead/behind 5/15, risk DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/fix/si-v2-issue-185-episode-contract-hardening` (remote, ahead/behind 0/37, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/fix/si-v2-issue-43-fleetri<redacted-token>` (remote, ahead/behind unknown/unknown, risk UNKNOWN_RISK): matching PR is already merged; branch is stale cleanup candidate unless unique diff is manually proven.
- `origin/fix/si-v2-sha-validation-regression-tests` (remote, ahead/behind 0/26, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/no-op` (remote, ahead/behind 0/109, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/temp` (remote, ahead/behind 0/109, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/test-191-green-pr-v2` (remote, ahead/behind 0/18, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `origin/test/si-v2-issue-181-phase2-e2e-integration` (remote, ahead/behind 0/35, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `pr-134-audit` (local, ahead/behind 0/126, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `rescue/phase2-critical-coverage-hardening-pre-main-unblock-20260615T081140Z` (local, ahead/behind 0/4, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `review/pr-105-rainbow-contract-drift` (local, ahead/behind 0/166, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `review/pr-106-rainbow-report-status-client` (local, ahead/behind 0/161, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `review/pr-113-rainbow-shadowlock-events` (local, ahead/behind 0/159, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `review/pr-119-source-evidence-episode` (local, ahead/behind 0/154, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `review/pr-126-offline-pipeline` (local, ahead/behind 0/146, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `review/pr-133-offline-episode-readiness` (local, ahead/behind 0/136, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `review/pr-78-issue-21-adapters` (local, ahead/behind 0/177, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `review/pr-99-pr36-reconciliation` (local, ahead/behind 0/170, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `temp-ci-pending` (local, ahead/behind 0/102, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
- `test/phase2-critical-coverage-hardening` (local, ahead/behind 0/4, risk UNKNOWN_RISK): no branch-only commits relative to origin/main; already represented by canonical base or duplicate tracking ref.
#### ARCHIVE_CLOSE_CANDIDATE (0)
- None.
#### BLOCKED (33)
- `docs/readme-refresh-current-state` (local, ahead/behind 1/205, risk DOCS_LOW_RISK): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `docs/si-v2-issue-25-telegram-approval-design` (local, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge.
- `docs/si-v2-issue-26-cron-activation-ceremony` (local, ahead/behind 1/205, risk DOCS_LOW_RISK,RUNTIME_HIGH_RISK,SI_V2_CORE): open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge.
- `docs/si-v2-issue-27-v1-residue-closure` (local, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge.
- `docs/si-v2-issue-38-telegram-conflict-rca` (local, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `docs/si-v2-issue-39-watchdog-connectivity` (local, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `feat/si-v2-controller-active-proof` (local, ahead/behind 1/117, risk DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `feat/si-v2-issue-143-147-149-planning-automation` (local, ahead/behind 1/111, risk DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `feat/si-v2-issue-21-adapter-prototypes` (local, ahead/behind 1/205, risk SI_V2_CORE): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `local/si-v2-controller-pr157-completion` (local, ahead/behind 1/74, risk SI_V2_CORE,UNKNOWN_RISK): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin-https/docs/si-v2-issue-25-telegram-approval-design` (remote, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge.
- `origin-https/docs/si-v2-issue-26-cron-activation-ceremony` (remote, ahead/behind 1/205, risk DOCS_LOW_RISK,RUNTIME_HIGH_RISK,SI_V2_CORE): open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge.
- `origin-https/docs/si-v2-issue-27-v1-residue-closure` (remote, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge.
- `origin-https/docs/si-v2-issue-38-telegram-conflict-rca` (remote, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin-https/docs/si-v2-issue-39-watchdog-connectivity` (remote, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin-https/feat/si-v2-issue-143-147-149-planning-automation` (remote, ahead/behind 1/111, risk DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin-https/feat/si-v2-issue-21-adapter-prototypes` (remote, ahead/behind 1/205, risk SI_V2_CORE): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin-https/pr-155` (remote, ahead/behind 1/111, risk DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin-https/pr-72` (remote, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin-https/pr-73` (remote, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin/docs/si-v2-branch-hygiene-report` (remote, ahead/behind 1/50, risk DOCS_LOW_RISK): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin/docs/si-v2-issue-25-telegram-approval-design` (remote, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge.
- `origin/docs/si-v2-issue-26-cron-activation-ceremony` (remote, ahead/behind 1/205, risk DOCS_LOW_RISK,RUNTIME_HIGH_RISK,SI_V2_CORE): open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge.
- `origin/docs/si-v2-issue-27-v1-residue-closure` (remote, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge.
- `origin/docs/si-v2-issue-38-telegram-conflict-rca` (remote, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin/docs/si-v2-issue-39-watchdog-connectivity` (remote, ahead/behind 1/205, risk DOCS_LOW_RISK,SI_V2_CORE): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin/feat/si-v2-controller-active-proof` (remote, ahead/behind 1/117, risk DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin/feat/si-v2-first-rest-shadowproposal-proof` (remote, ahead/behind 2/15, risk DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin/feat/si-v2-issue-143-147-149-planning-automation` (remote, ahead/behind 1/111, risk DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin/feat/si-v2-issue-21-adapter-prototypes` (remote, ahead/behind 1/205, risk SI_V2_CORE): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin/feat/si-v2-phase2-evidence-input-pipeline` (remote, ahead/behind 1/50, risk SI_V2_CORE): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- `origin/test-191-failing-check` (remote, ahead/behind 1/19, risk SI_V2_CORE): non-open branch touches high/unknown-risk areas without current validation/PR ownership.
- `origin/test-191-green-pr` (remote, ahead/behind 1/19, risk UNKNOWN_RISK): merge-tree conflict probe reported conflict markers/changed-in-both evidence.
#### UNKNOWN (0)
- None.

### PR decisions

#### MERGE_CANDIDATE (0)
- None.
#### CHERRY_PICK_CANDIDATE (0)
- None.
#### SUPERSEDED (73)
- PR #219 `docs/phase-b2-l3-compose-adoption-plan-200` [merged]: docs: add #200 phase B2 L3 adoption execution plan — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #218 `fix/phase2-hermes-watchdog-compose-network` [merged]: fix: align hermes-watchdog compose network before adoption — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #217 `docs/phase2-runtime-ownership-map-200` [merged]: docs: publish #200 runtime ownership map audit — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #216 `docs/roadmap-v2-runtime-ownership-reconciliation` [merged]: docs: reconcile Trading Hub state and add blocker-first Roadmap v2 — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #215 `feat/si-v2-rainbow-read-only-runtime-source-v1` [merged]: si-v2: add Rainbow read_only runtime source env overrides — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #214 `feat/si-v2-rainbow-enable-observation-v1` [merged]: si-v2: enable Rainbow observation in scheduled Active Cycle via env-var override — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #213 `feat/si-v2-rainbow-cycle-ledger-integration-v1` [merged]: si-v2: integrate Rainbow read_only signals into active cycle ledger — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #212 `feat/si-v2-rainbow-read-only-client-v1` [merged]: feat(si-v2): add rainbow read-only signal client — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #211 `feat/si-v2-runner-ledger-integration` [merged]: si-v2: wire passive Measurement Ledger into Active Cycle Runner — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #210 `feat/si-v2-measurement-ledger-v1` [merged]: si-v2: add Measurement and Attribution Ledger v1 — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #209 `feat/si-v2-signal-fusion-v1` [merged]: si-v2: add multi-signal fusion for actionable ShadowProposals — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #208 `feat/si-v2-active-cycle-runner-v1` [merged]: si-v2: add Active Multi-Bot Cycle Runner v1 — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #207 `feat/si-v2-readonly-freqtrade-jwt-auth` [merged]: si-v2: add minimal read-only Freqtrade JWT auth — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #206 `fix/si-v2-freqtrade-registry-docker-dns` [merged]: si-v2: fix Freqtrade read-only registry to use Docker DNS — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #204 `feat/issue-199-freqtrade-healthchecks` [merged]: infra: add deterministic Docker healthchecks for Freqtrade fleet — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #203 `si-v2/issue-202-one-shot-proof` [merged]: si-v2: Stage B one-shot proof artifact (issue #202) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #198 `test-191-green-pr-v2` [merged]: test: GREEN PR for branch protection validation (v2) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #195 `feat/issue-191-main-gate-workflow` [merged]: ci: add always-reporting main-gate workflow for branch protection — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #194 `docs/si-v2-issue-66-weekly-review-cadence` [merged]: feat(si-v2): deterministic weekly proposal review cadence policy — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #193 `docs/si-v2-issue-26-activation-ceremony-v2` [merged]: feat(si-v2): fail-closed scheduler activation ceremony and jobs.json guardrails — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #192 `fix/si-v2-sha-validation-regression-tests` [merged]: fix: harden SHA validation with regression tests for 593d55e — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #190 `feat/si-v2-issue-175-controller-baseline-reconciliation` [merged]: [SI v2] feat: add reusable controller baseline reconciliation command (#175) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #189 `ci/si-v2-issue-182-phase2-proposal-gate` [merged]: [SI v2] ci: add dedicated Phase 2 proposal-stack CI gate (#182) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #188 `feat/si-v2-issue-65-validation-gate-matrix` [merged]: [SI v2] feat: implement Validation Gate Matrix for Phase 2 proposal review (#65) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #187 `test/si-v2-issue-181-phase2-e2e-integration` [merged]: [SI v2] test: real no-mock Phase 2 end-to-end integration proof (#181) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #186 `fix/si-v2-issue-185-episode-contract-hardening` [merged]: [SI v2] fix: harden episode report contracts — SHA-256, timestamps, verdict truth table, duplicate ID rejection, fingerprint provenance (#185) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #184 `feat/si-v2-issue-64-episode-report` [merged]: [SI v2][Phase 2] Implement episode report builder for proposal review workflow (#64) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #183 `feat/si-v2-issue-63-weight-proposal-engine` [merged]: [SI v2][Phase 2] Implement Weight Proposal Engine with human-approval output only (#63) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #174 `feat/si-v2-issue-35-proposal-scoring-policy` [merged]: feat(si-v2): add proposal scoring and promotion policy (issue #35) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #173 `docs/si-v2-issue-34-market-data-readiness` [merged]: docs(si-v2): add market-data readiness specification — issue #34 — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #172 `feat/si-v2-phase2-evidence-pipeline-hardened` [merged]: feat(si-v2): harden issue #62 — evidence input pipeline with full typed contract — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #171 `docs/si-v2-phase0-reconciliation-20260611` [merged]: docs(si-v2): Phase 0/Phase 1 reconciliation — close #46, #60, #61 — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #169 `feat/issue-60-cache-maintenance` [merged]: feat(si-v2): harden issue #60 — derived SQLite cache maintenance with copy-on-write safety — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #166 `feat/si-v2-issue-59-attribution-reports` [merged]: feat(si-v2): implement issue #59 — automated attribution reports — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #165 `feat/si-v2-issue-58-source-regime-stats` [merged]: feat(si-v2): implement issue #58 — source_regime_stats SQLite cache — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #164 `feat/si-v2-issue-57-performance-attribution` [merged]: feat(si-v2): implement issue #57 — Performance Attribution Engine — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #163 `feat/si-v2-issue-56-regime-shadowlock-enrichment` [merged]: feat(si-v2): implement issue #56 — regime detector run and Shadowlock enrichment — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #162 `docs/si-v2-post-controller-reconciliation` [merged]: docs(si-v2): post-controller documentation reconciliation (PR #160) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #161 `feat/si-v2-issue-55-regime-schema` [merged]: [SI v2][Phase 1] Canonical Regime Detector Schema (#55) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #160 `fix/si-v2-controller-state-contract` [merged]: fix(controller): repair state contract, separate mutable state, real active cycle proof — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #158 `feat/si-v2-canonical-ci-pending` [merged]: [SI v2] Canonical planning automation branch (reconciles #155 + #156 + #145) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #157 `chore/si-v2-continuous-controller-control-plane` [merged]: [SI v2] Continuous controller control plane — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #142 `feat/si-v2-issue-135-140-rehearsal-planning-gate` [merged]: [SI v2] Add rehearsal planning gate layer (#135 #136 #137 #138 #139 #140) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #141 `feat/si-v2-issue-127-132-rehearsal-control` [merged]: [SI v2] Add rehearsal-control layer (#127 #128 #129 #130 #131 #132) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #134 `feat/si-v2-issue-120-125-governance-ci-approval-runbook` [merged]: [SI v2] Add offline smoke CI, governance, approval, progress, blockers, and runbook (#120 #121 #122 #123 #124 #125) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #133 `feat/si-v2-issue-97-114-118-offline-episode-readiness-architecture` [merged]: [SI v2] Add offline episode, reports, readiness, and architecture index (#97 #114 #115 #116 #117 #118) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #126 `feat/si-v2-issue-107-112-goldenpath-evidence-regime-attribution-qagate` [merged]: [SI v2] Add offline golden path, evidence, regime, attribution, and quality gate (#107 #108 #109 #110 #111 #112) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #119 `feat/si-v2-issue-100-104-source-evidence-episode-foundation` [merged]: [SI v2] Add source, evidence, and episode foundation (#100 #101 #102 #103 #104) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #113 `feat/si-v2-issue-81-shadowlock-external-signal-audit-events` [merged]: [SI v2][Rainbow] Add Shadowlock audit event mapper (#81) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #106 `feat/si-v2-issue-84-85-80-rainbow-report-status-client` [merged]: [SI v2][Rainbow] Add fixture report, status, and read-only client (#84 #85 #80) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #105 `feat/si-v2-issue-82-rainbow-contract-snapshot` [merged]: [SI v2][Rainbow] Add contract snapshot and drift guard (#82 #83) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #99 `docs/si-v2-issue-93-pr36-reconciliation` [merged]: [SI v2][PR36] Add post-merge reconciliation report (#93) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #91 `feat/si-v2-issue-79-rainbow-envelope-validator` [merged]: [SI v2][Rainbow] Add signal envelope validator with fixture tests (#79) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #78 `feat/si-v2-issue-21-adapter-prototypes-v2` [merged]: [SI v2] Implement read-only runtime adapter prototypes behind env gate (#21) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #77 `fix/si-v2-issue-43-fleetri<redacted-token>` [merged]: [SI v2][Phase 0] Fix FleetRiskManager missing state fallback (#43) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #76 `docs/si-v2-issue-47-roadmap-baseline` [merged]: [SI v2] Canonical roadmap, README, and .gitignore baseline (#47) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #75 `feat/si-v2-issue-45-shadowlock-writer-indexer-trigger` [merged]: [SI v2] Connect Shadowlock Writer to incremental Indexer trigger (#45) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #74 `feat/si-v2-issue-12-shadowlock-indexer` [merged]: [SI v2] Implement shadowlock SQLite read-cache indexer (#12) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #54 `docs/si-v2-issue-20-adapter-contracts` [merged]: [SI v2] Design read-only Docker/Freqtrade adapter contracts after runtime probe (#20) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #53 `feat/si-v2-issue-31-ci-safety-gates` [merged]: [SI v2] Strengthen CI safety gates and forbidden-pattern regression suite (#31) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #52 `feat/si-v2-issue-30-status-reporting` [merged]: [SI v2] Add safety status reporting layer with CLI (#30) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #51 `docs/si-v2-issue-32-consolidate-docs-index` [merged]: [SI v2] Consolidate project documentation and decision log (#32) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #50 `docs/si-v2-issue-23-watchdog-ownership-adr` [merged]: [SI v2] ADR: Decide watchdog ownership between SI v2 and ai4trade-bot (#23) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #49 `docs/si-v2-issue-22-riskguard-shadowlogger-contract` [merged]: [SI v2] Define RiskGuard and ShadowLogger runtime safety contract (#22) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #42 `extract/export-trade-history-multi-schema` [merged]: fix(tools): support multiple Freqtrade trade DB schemas — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #36 `feat/si-v2-foundation` [merged]: [SI v2] Self-Improvement foundation, safety gates, dry-run pipeline, and runtime probe planning. — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #11 `feat/hermes-issue-9-complete` [merged]: feat: implement orchestrator spec, trade-history tooling, and shadowlock service (Issue #9) — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #8 `feat/agent-specs-shadowlock-2026-06-07` [merged]: feat: add agent specs and shadowlock directory structure — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #7 `fix/telegram-polling-conflict-batch2a-20260606` [merged]: fix: telegram polling conflict — persistent resolution batch 2a — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #6 `fix/telegram-hygiene-batch1-clean-20260606` [merged]: fix: stabilize telegram and cron hygiene batch 1 — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #3 `clean/main-rebuild` [merged]: Clean/main rebuild — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #2 `chore/permission-hardening-guardian` [merged]: chore: harden trading permission guard and signal runtime writes — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
- PR #1 `feat/trading-workflow-cleanup` [merged]: chore: secure Trading Hub git workflow and version critical files — PR is already merged; any remaining branch ref is cleanup/supersession inventory, not a merge candidate.
#### ARCHIVE_CLOSE_CANDIDATE (14)
- PR #197 `test-191-green-pr` [closed]: test: GREEN PR for branch protection validation — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #196 `test-191-failing-check` [closed]: test: failing check for branch protection validation — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #170 `feat/si-v2-phase2-evidence-input-pipeline` [closed]: feat(si-v2): Phase 2 — Evidence Input Pipeline — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #168 `docs/si-v2-phase0-reconciliation-20260611` [closed]: docs(si-v2): Phase 0 reconciliation - update stale docs after #55-#59 merge — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #167 `docs/si-v2-branch-hygiene-report` [closed]: docs(si-v2): branch/PR hygiene inventory report for #46 — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #156 `feat/si-v2-143-154-planning-automation-quality` [closed]: [SI v2] Add planning automation and quality layer (#143–#154) — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #155 `feat/si-v2-issue-143-147-149-planning-automation` [closed]: [SI v2] Add planning pipeline automation layer (#143 #144 #145 #146 #147 #149) — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #73 `docs/si-v2-issue-39-watchdog-connectivity` [closed]: [SI v2] Document watchdog connectivity target root cause (#39) — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #72 `docs/si-v2-issue-38-telegram-conflict-rca` [closed]: [SI v2] Document rebel Telegram polling conflict root cause (#38) — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #68 `feat/si-v2-issue-21-adapter-prototypes` [closed]: [SI v2] Implement read-only runtime adapter prototypes behind env gate (#21) — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #13 `copilot/fix-212666996-1237110730-965175f3-a5a3-495f-8aa4-ecd03192f16a` [closed]: [WIP] feat: shadowlock_indexer.py — SQLite read-cache for JSONL ledger (Issue #12) — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #10 `copilot/feat-complete-agent-stack` [closed]: Complete agent stack foundation: orchestrator episode spec, trade-history export CLI, and Shadowlock writer service — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #5 `fix/telegram-hygiene-batch1-20260606` [closed]: fix: stabilize cron and telegram hygiene batch 1 — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
- PR #4 `copilot/c-vmach-mir-das-biuttte-fertig-komplett` [closed]: fix: complete PR #3 clean/main rebuild — PR is closed without merge; keep archived unless a human reopens scope on a fresh branch.
#### BLOCKED (5)
- PR #205 `feat/si-v2-first-rest-shadowproposal-proof` [open]: si-v2: add first read-only Freqtrade REST shadow proposal proof — merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- PR #159 `feat/si-v2-controller-active-proof` [open]: [SI v2][Proof] Controller active cycle proof — CONTROLLER-ACTIVE-PROOF completed — merge-tree conflict probe reported conflict markers/changed-in-both evidence.
- PR #71 `docs/si-v2-issue-27-v1-residue-closure` [open]: [SI v2] Plan v1 residue archive and migration closure (#27) — open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge.
- PR #70 `docs/si-v2-issue-26-cron-activation-ceremony` [open]: [SI v2] Design cron activation ceremony and jobs.json guardrails (#26) — open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge.
- PR #69 `docs/si-v2-issue-25-telegram-approval-design` [open]: [SI v2] Design Telegram approval live adapter with token <redacted> (#25) — open PR with mergeability=MERGEABLE; high/unknown risk categories require validation before merge.
#### UNKNOWN (0)
- None.

## 11. Recommended Safe Integration Order

1. STOP: do not merge anything while the worktree is dirty and all open PRs are blocked.
2. Read-only owner check for pre-existing dirty files: docs/state/canonical-trading-status.md, orchestrator/reports/canonical_trading_status_latest.json, HERMES_METRICS.json, docs/context/ledger-watchdog-2026-06-15.md.
3. Resolve ref ambiguity in planning only: refs/heads/origin/main shadows origin/main and must not be used as an unqualified base; no deletion/rename without explicit approval.
4. Triage open PR conflicts first: #205 and #159 are GitHub-conflicting and merge-tree-conflicting; preserve multi-bot SI v2 scope for #205.
5. For open docs PRs #69-#71, do not merge directly despite GitHub mergeable=true; recreate/cherry-pick onto current main only if still wanted and after SI v2 docs validation.
6. Review CHERRY_PICK_CANDIDATE branches file-by-file; only extract still-valuable SI v2 planning docs/tests after targeted validation.
7. Treat merged PR branches and duplicate remote refs as cleanup inventory; archive/close/delete only in a separate explicit cleanup pass.

## 12. Required Validation Per Candidate

No immediate `MERGE_CANDIDATE` branch exists. The following blocked/cherry-pick candidates require validation before any future merge/cherry-pick:

### `docs/si-v2-issue-25-telegram-approval-design` — BLOCKED
- Risk: DOCS_LOW_RISK,SI_V2_CORE
- Files changed: 1
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only

### `docs/si-v2-issue-26-cron-activation-ceremony` — BLOCKED
- Risk: DOCS_LOW_RISK,RUNTIME_HIGH_RISK,SI_V2_CORE
- Files changed: 1
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only
  - host preflight only; no Docker/Compose/runtime mutation without explicit L3 approval
  - document rollback path before runtime adoption

### `docs/si-v2-issue-27-v1-residue-closure` — BLOCKED
- Risk: DOCS_LOW_RISK,SI_V2_CORE
- Files changed: 1
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only

### `feat/si-v2-143-154-planning-automation-quality` — CHERRY_PICK_CANDIDATE
- Risk: DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK
- Files changed: 33
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only
  - manual file-by-file review for generated/binary/deleted/large changes

### `feat/si-v2-canonical-planning-reconciliation` — CHERRY_PICK_CANDIDATE
- Risk: DOCS_LOW_RISK,SI_V2_CORE,TESTS_VALIDATION
- Files changed: 4
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - run targeted pytest for touched tests
  - verify CI-equivalent smoke result
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only

### `feat/si-v2-controller-active-proof` — BLOCKED
- Risk: DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK
- Files changed: 10
- Conflict: yes
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only
  - manual file-by-file review for generated/binary/deleted/large changes

### `origin-https/docs/si-v2-issue-25-telegram-approval-design` — BLOCKED
- Risk: DOCS_LOW_RISK,SI_V2_CORE
- Files changed: 1
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only

### `origin-https/docs/si-v2-issue-26-cron-activation-ceremony` — BLOCKED
- Risk: DOCS_LOW_RISK,RUNTIME_HIGH_RISK,SI_V2_CORE
- Files changed: 1
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only
  - host preflight only; no Docker/Compose/runtime mutation without explicit L3 approval
  - document rollback path before runtime adoption

### `origin-https/docs/si-v2-issue-27-v1-residue-closure` — BLOCKED
- Risk: DOCS_LOW_RISK,SI_V2_CORE
- Files changed: 1
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only

### `origin-https/feat/si-v2-143-154-planning-automation-quality` — CHERRY_PICK_CANDIDATE
- Risk: DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK
- Files changed: 33
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only
  - manual file-by-file review for generated/binary/deleted/large changes

### `origin-https/pr-156` — CHERRY_PICK_CANDIDATE
- Risk: DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK
- Files changed: 33
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only
  - manual file-by-file review for generated/binary/deleted/large changes

### `origin/docs/si-v2-issue-25-telegram-approval-design` — BLOCKED
- Risk: DOCS_LOW_RISK,SI_V2_CORE
- Files changed: 1
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only

### `origin/docs/si-v2-issue-26-cron-activation-ceremony` — BLOCKED
- Risk: DOCS_LOW_RISK,RUNTIME_HIGH_RISK,SI_V2_CORE
- Files changed: 1
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only
  - host preflight only; no Docker/Compose/runtime mutation without explicit L3 approval
  - document rollback path before runtime adoption

### `origin/docs/si-v2-issue-27-v1-residue-closure` — BLOCKED
- Risk: DOCS_LOW_RISK,SI_V2_CORE
- Files changed: 1
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only

### `origin/feat/si-v2-143-154-planning-automation-quality` — CHERRY_PICK_CANDIDATE
- Risk: DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK
- Files changed: 33
- Conflict: no
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only
  - manual file-by-file review for generated/binary/deleted/large changes

### `origin/feat/si-v2-controller-active-proof` — BLOCKED
- Risk: DOCS_LOW_RISK,SI_V2_CORE,UNKNOWN_RISK
- Files changed: 10
- Conflict: yes
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only
  - manual file-by-file review for generated/binary/deleted/large changes

### `origin/feat/si-v2-first-rest-shadowproposal-proof` — BLOCKED
- Risk: DOCS_LOW_RISK,SI_V2_CORE,TRADING_HIGH_RISK,UNKNOWN_RISK
- Files changed: 17
- Conflict: yes
- Required validation:
  - markdown/link review for changed docs
  - confirm docs match current runtime evidence
  - PYTHONPATH=src python -m pytest tests/test_phase2_e2e_integration.py::TestNoRuntimeAccess -v --tb=short
  - SI v2 dry-run/active-cycle smoke proof with read-only sources only
  - prove all four Freqtrade bots remain first-class dry-run targets
  - RiskGuard/ShadowLogger design impact review before merge
  - manual file-by-file review for generated/binary/deleted/large changes

## 13. Explicit Non-Actions

- No git merge, rebase, reset, pull, push, branch deletion, PR merge, or PR close was executed.
- No package installation or Compose recovery was attempted.
- No Docker, Freqtrade, scheduler, Telegram, Mem0, Qdrant, Ollama, Caddy, or Hermes runtime action was executed.
- HERMES_METRICS.json was not modified, moved, staged, committed, or read for contents; it was only reported from git status.
- No live-trading, dry_run, credentials, exchange config, strategy, signal threshold, or risk-parameter change was made.
- No validation tests were run because this audit was limited to read-only inventory and pytest may create cache artifacts.

## 14. Exact Next Step

**Do not merge; first perform a read-only owner check of the current dirty worktree entries and confirm whether each is intentional before any branch/PR integration.**
