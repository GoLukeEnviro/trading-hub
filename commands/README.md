# commands/ — Operator Commands (trading-hub-orchestrator)

Versioned, auditable command definitions for the `trading-hub-orchestrator` operator on HermesTrader.
Each command is a Markdown file describing a read-only or explicitly-scoped procedure.

## Conventions
- One file per command; filename = `kebab-case-action.md`.
- Every command specifies: Purpose, Inputs, Output, Validation, Stop conditions, Scope, (optional) PR-title template.
- **No secrets, no runtime mutation** unless the command is an explicitly-approved runtime-action (then gated by the Phase D runner).

## Reference
- Migration bundle `06_proposed_SOUL.md` / `07_proposed_AGENTS.md` provided sanitized input; the live repo `SOUL.md`/`AGENTS.md` are Source of Truth.
- Current command: `next-unblocked-roadmap-task.md` (read-only roadmap picker).
