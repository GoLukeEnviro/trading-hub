# SI v2 Continuous Implementation Roadmap

## Objective

Create a durable repository-native control plane so Hermes can continue SI v2 work in bounded, reviewable packages without repeated chat handoffs.

## Sources of Truth

1. `orchestrator/control/POLICY.md`
2. `orchestrator/control/STATE.json`
3. `orchestrator/control/QUEUE.json`
4. GitHub issues and pull requests
5. `orchestrator/control/HANDOFF.md`
6. Immutable run reports under `orchestrator/control/runs/`

Repository state must override conversational memory.

## Continuous Loop

Each scheduled run performs one bounded package:

1. Acquire an exclusive lock.
2. Validate control-plane files.
3. Read policy, state, queue, and handoff.
4. Resume an active branch or pull request before starting new work.
5. Repair in-scope CI or review findings first.
6. Select the highest-priority ready queue item.
7. Work only in the dedicated epic worktree.
8. Run targeted and full SI v2 validation.
9. Apply up to three scoped fix rounds.
10. Commit and push issue-grouped changes.
11. Create or update one pull request.
12. Update state, queue, handoff, and the immutable run report.
13. Release the lock and exit.

## Current Epic

Planning Automation and Quality, issues #143 through #154.

Recommended order:

1. Verify and close completed #135–#140 work.
2. #144 proposal schema and typed models.
3. #151 semantic consistency engine.
4. #146 artifact redaction and path policy.
5. #143 end-to-end planning validator.
6. #150 planning package checker command.
7. #152 negative-test fixture corpus.
8. #153 deterministic status report renderer.
9. #147 review checklist and #149 package index.
10. #148 offline interface contracts after prior gates pass.
11. #154 golden regression suite.
12. #145 offline CI integration.
13. Final internal review and one unmerged pull request.

## Work Bounds

- One major issue or up to three tightly coupled smaller issues per run.
- Maximum duration: 90 minutes.
- Maximum internal fix rounds: 3.
- Maximum commits per run: 8.
- Pull-request merge remains a separate human-approved action.
- Restricted operational actions remain outside this controller.

## Required Validation

Before push:

- compile all SI v2 Python sources;
- run the full SI v2 test suite;
- run Ruff;
- run `git diff --check`;
- parse all project and control-plane JSON files;
- verify deterministic output for repeated fixture runs;
- complete an internal review with no unresolved BLOCKER or MAJOR finding.

## Scheduling

Preferred: a locked systemd oneshot service with a persistent timer every 30 minutes.

Fallback: cron every 30 minutes calling the same locked wrapper.

The scheduler must enforce a single active run, a 90-minute timeout, external logs, and pause/block states. Installation and enablement require a separate privileged-change review.

## Durable Files

- `orchestrator/control/POLICY.md`
- `orchestrator/control/STATE.json`
- `orchestrator/control/QUEUE.json`
- `orchestrator/control/HANDOFF.md`
- `orchestrator/control/CURRENT_EPIC.md`
- `orchestrator/control/MASTER_AGENT_PROMPT.xml`
- `orchestrator/control/runs/<timestamp>-<run-id>.md`

## Completion Definition

The epic is complete when all target issues are merged and closed, main is validated from a clean worktree, all quality checks pass, the queue has no active item, and the final handoff identifies the next separately approved epic.
