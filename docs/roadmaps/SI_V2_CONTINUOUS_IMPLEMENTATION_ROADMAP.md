# SI v2 Continuous Implementation Roadmap

## 1. Objective

Create a durable, repository-native control plane that allows Hermes to continue implementing SI v2 in bounded, reviewable work packages without requiring repeated copy/paste handoffs.

The controller must:

- resume existing branches and pull requests before starting new work;
- select the next ready work package from a machine-readable queue;
- remain offline-only for the current planning-automation epic;
- preserve human-only merge authority;
- update durable state and handoff records after every run;
- fail closed when repository state, CI, approvals, or dependencies are ambiguous.

## 2. Canonical Sources of Truth

Priority order:

1. `orchestrator/control/POLICY.md`
2. `orchestrator/control/STATE.json`
3. `orchestrator/control/QUEUE.json`
4. GitHub pull requests and issues
5. `orchestrator/control/HANDOFF.md`
6. `orchestrator/control/runs/`

The agent must never rely on chat memory as the only source of project state.

## 3. Operating Model

Each scheduled run performs exactly one bounded work package.

A work package may include:

- one major issue;
- up to three tightly coupled smaller issues;
- one CI repair cycle;
- one PR review and hardening cycle;
- one post-merge main validation cycle.

Default bounds:

- maximum wall-clock budget: 90 minutes;
- maximum internal fix rounds: 3;
- maximum commits per run: 8;
- no merge without a separate explicit approval token;
- no runtime, Docker, Freqtrade, exchange, production, or credential operations.

## 4. Continuous Loop

1. Acquire controller lock.
2. Validate control-plane JSON files.
3. Read policy, state, queue, and latest handoff.
4. Inspect GitHub for:
   - active PRs from the current epic;
   - pending CI;
   - review findings;
   - merged work awaiting main validation;
   - ready issues.
5. Resume existing work before starting new work.
6. Select the highest-priority ready queue item.
7. Create or reuse a dedicated worktree.
8. Implement the bounded package.
9. Run targeted tests.
10. Run full SI v2 validation.
11. Perform an internal review.
12. Apply up to three scoped fix rounds.
13. Commit and push issue-grouped changes.
14. Open or update one PR.
15. Update `STATE.json`.
16. Rewrite `HANDOFF.md`.
17. Write an immutable run report under `runs/`.
18. Release the lock and exit.

## 5. Current Epic: Planning Automation and Quality

Target issues:

- #143 End-to-end planning pipeline validator
- #144 Rehearsal proposal package schema
- #145 Offline planning CI gate
- #146 Artifact redaction policy
- #147 Merge-readiness review checklist
- #148 Offline observation interface contracts
- #149 Planning package index
- #150 Planning package checker command
- #151 Semantic consistency engine
- #152 Negative-test fixture corpus
- #153 Deterministic status report renderer
- #154 Golden regression suite

Recommended dependency order:

1. Administrative closure of #135–#140
2. #144 proposal schema and typed models
3. #151 semantic consistency
4. #146 redaction and path policy
5. #143 end-to-end validator
6. #150 checker command
7. #152 negative fixture corpus
8. #153 deterministic report renderer
9. #147 review checklist
10. #149 package index
11. #148 offline interface contracts
12. #154 golden regression suite
13. #145 CI integration
14. Final internal review and PR readiness audit

## 6. Merge Policy

The continuous controller may:

- create branches and dedicated worktrees;
- edit files inside the dedicated worktree;
- commit and push;
- create or update pull requests;
- repair CI failures within the approved epic scope;
- comment on related issues and PRs;
- update control-plane state.

The continuous controller may not:

- merge pull requests;
- delete branches or worktrees;
- close newly implemented issues before their PR is merged;
- execute runtime or trading operations;
- alter production services;
- access credentials or live environment values.

## 7. Completion Definition

The epic is complete only when:

- all target issues are merged;
- all related issues are closed as completed;
- `origin/main` is validated from a clean worktree;
- full SI v2 tests, Ruff, compileall, JSON validation, and golden tests pass;
- the queue contains no ready or in-progress item for the epic;
- the final handoff points to the next approved epic;
- no unresolved BLOCKER or MAJOR review finding remains.
