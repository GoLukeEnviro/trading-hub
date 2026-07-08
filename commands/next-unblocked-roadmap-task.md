# Command: next-unblocked-roadmap-task

> Identify **exactly one** next unblocked roadmap task. Read-only — does not modify files.

## Purpose
Keep the trading-hub-orchestrator roadmap moving one concrete, unblocked step at a time. Reads the operator's own state + open GitHub issues and picks the single next task that is unblocked and in-scope.

## Inputs (read-only)
- `SOUL.md`, `AGENTS.md` (operator identity + rules)
- `docs/state/current-operational-state.md` (current repo/phase state)
- Open GitHub issues: `gh issue list --repo GoLukeEnviro/trading-hub --state open`
- Phase-gate status from reports under `/root/reports/`

## Output
- Exactly **one** task, as a structured note (stdout / scratch — **not** committed):
  - Task title + linked issue/PR (if any)
  - Why it is unblocked (which gates are GREEN)
  - Why it is in-scope (trading-hub-orchestrator; no side-projects)
  - Suggested next branch name

## Validation
- Output cites at least one GREEN gate justifying "unblocked".
- Output stays in single-profile scope (no ai-hedge-fund/btc5m-bot/shadowlock runtime action).
- No secret appears in the output.

## Stop conditions
- No GREEN gate for the proposed task -> output "BLOCKED: <missing gate>", pick nothing.
- Two equally-unblocked tasks -> pick the one matching documented phase order (B -> C0 -> C1A -> C1 -> D -> E -> F).
- gh / issue read fails -> output "BLOCKED: issue read failed", do not guess.

## Scope
- Read-only. No file mutation, no Docker, no bot/fleet/strategy action, no Caddy/UFW/Systemd/Cron.

## Suggested PR-title template (follow-up execution)
`<type>(<scope>): <imperative summary>` — e.g. `docs(state): refresh operational state after <phase>`.
