# SI v2 Continuous Controller

This directory is the durable control plane for continuous SI v2 implementation.

## Read Order

1. `POLICY.md`
2. `STATE.json`
3. `QUEUE.json`
4. `HANDOFF.md`
5. `MASTER_AGENT_PROMPT.xml`
6. the latest file under `runs/`, if present

## Important

The controller is not a trading runtime. It is a repository implementation loop. Pull-request merges remain human-approved.
