# Agent Prompts — trading-hub

This directory contains stable, versioned prompts for LLM agents operating in the trading-hub system.
Each prompt has been validated in at least one real run before being committed here.

---

## Index

| File | Agent | Role | Status |
|---|---|---|---|
| `agent-context-engineering.md` | Context Engineering Agent | Classifies, promotes and gitignores repo files | v1.0 — validated 2026-06-08 |
| `agent-self-improvement-orchestrator.md` | Self-Improvement Orchestrator | Runs backtest episodes, evaluates outcomes, proposes changes | v1.1 — validated 2026-06-08 |

---

## Usage

These prompts are designed to be copied into an LLM session (Claude, GPT-4, etc.) or run via
an agent framework. They reference paths and specs that exist in this repository.

Before running any prompt:
1. Verify that the referenced spec files exist in `docs/specs/`
2. Ensure the agent has access to the repository working directory
3. Confirm that `var/trading-shadowlock/` is mounted and writable

---

## Versioning Convention

- Minor refinements: update in-place, note version bump in the file header
- Breaking changes (different inputs, different output format): new file with `_v2` suffix
- Deprecated prompts: move to `docs/prompts/archive/`
