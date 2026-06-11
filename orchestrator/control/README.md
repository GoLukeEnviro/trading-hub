# SI v2 Continuous Controller

This directory contains the repository-side control plane for continuous SI v2 implementation.

## Read Order

1. `POLICY.md`
2. `STATE.json`
3. `QUEUE.json`
4. `HANDOFF.md`
5. `CURRENT_EPIC.md`
6. `MASTER_AGENT_PROMPT.xml`

## Repository Files

The branch contains the durable roadmap, current state, dependency-aware queue, handoff, schemas, validation script, runbook, and controller prompts.

## Operational Files

Runner and scheduler installation remain a separate local VPS step. Their installation and activation require an explicit manual review. Nothing in this branch activates a scheduler or changes a running service.

## Merge Policy

Pull-request merge authority remains human-controlled.
