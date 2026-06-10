# Context Architecture — trading-hub

> Version: 1.0 | Created: 2026-06-08 | Author: Hermes / Primary Repository Integration Agent

This document defines the canonical role of every documentation path in this repository.
It exists so that humans, Context Agents, and Self-Improvement Agents agree on what goes where.

---

## The Three Layers

| Layer | What it is | Lifecycle | Git-tracked? |
|---|---|---|---|
| **SPEC** | Stable, versioned knowledge | Long-lived, rarely changes | ✅ Always |
| **CONTEXT** | Session outputs, LLM logs, forensics runs, audit snapshots | Medium-lived, per-session | ⚠ Selectively |
| **RUNTIME** | Live logs, trade DBs, backtest raw output, Docker state | Short-lived, auto-generated | ❌ Never |

---

## Path Roles

### `docs/specs/` — Stable Specs (always tracked)

Canonical, versioned knowledge that any agent or human can rely on.
Files here must not contain speculative claims, session-specific data, or timestamps from single runs.

Contains:
- Bot roles and architecture (`bot-roles-and-shadow-architecture.md`)
- Shadowlock writer spec (`shadowlock-writer-spec.md`)
- Profitability Forensics Agent spec (`profitability-forensics-agent-spec.md`)
- Self-Improvement Orchestrator spec (`self-improvement-orchestrator-spec.md`)
- Self-Improvement Orchestrator prompt (`self-improvement-orchestrator-prompt.md`)
- Signal Intelligence spec (`self-improvement-signal-intelligence-spec.md`)
- Trading system audit (`trading-system-audit-2026-06-07.md`)
- This file (`context-architecture.md`)

Rule: **Every claim must be sourced. No speculation without `[HYPOTHESIS]` prefix.**

---

### `docs/prompts/` — Agent Prompts (always tracked)

Stable, reusable agent prompts. These are the "programs" for LLM agents.
A prompt in this folder is considered stable when it has been validated in at least one real run.

Contains:
- `agent-context-engineering.md` — classifies and promotes files in the repo
- `agent-self-improvement-orchestrator.md` — runs backtest episodes and proposes changes

Rule: **Prompts here are versioned. Breaking changes get a new file, not an in-place overwrite.**

---

### `docs/context/` — Session Context (selectively tracked)

Outputs from agent runs: forensics reports, episode reports, recovery candidates, trade summaries.
Most files here are auto-generated and should not be committed unless they contain
non-reproducible conclusions (e.g. forensics attribution hypotheses).

**Track (commit):**
- `forensics-profitability-YYYY-MM-DD.md`
- `recovery-candidates-YYYY-MM-DD.md`
- `self-improvement-run-episode-*.md`
- `*_summary.json` (trade export summaries — statistics only, no live PnL)

**Do not track (gitignore):**
- `trade-export-*_trades.csv` (large, reproducible from SQLite)
- `*_episode_*.py` strategy copies (temporary, reproducible)
- Cron-generated snapshots dated files (`canonical-trading-status-*.md`, etc.)
- mem0 migration files, telegram hygiene audit raw dumps

---

### `docs/state/` — Operational State (selectively tracked)

Point-in-time snapshots of the live system state. Updated by cron scripts.
Only commit manually after a deliberate state change — not on every cron refresh.

---

### `orchestrator/` — Orchestrator Scripts (tracked)

Python scripts for the trading autopilot and hub sync.
Archive subdirectory (`orchestrator/archive/`) is tracked for historical reference.

---

### `shadowlock/` — Shadowlock Service (tracked)

The append-only JSONL ledger service. All source code is tracked.
Runtime data lives in `var/trading-shadowlock/` which is never tracked.

---

### `var/trading-shadowlock/` — Runtime Ledger (never tracked)

The live Shadowlock JSONL logs, inbox, processed, backtests, and state files.
The SQLite index (`state/shadowlock.db`) is also runtime — never commit.

Structure:
```
var/trading-shadowlock/
  inbox/        ← pending entries (picked up by writer)
  processed/    ← successfully written entries
  quarantine/   ← schema-invalid entries
  dead-letter/  ← unrecoverable entries
  logs/         ← YYYY/MM/DD.jsonl ledger files
  backtests/    ← raw backtest JSON and JSONL episode results
  state/        ← sequence files (.seq), indexer state, shadowlock.db
```

Only the `.gitkeep` placeholder files in `inbox/`, `processed/`, and `state/` are tracked.

---

## Git Hygiene Rules

### Always tracked
```
docs/specs/**
docs/prompts/**
docs/decisions/**
docs/runbooks/**
shadowlock/*.py
shadowlock/Dockerfile*
shadowlock/README.md
tools/*.py
tools/README.md
orchestrator/*.py
var/trading-shadowlock/inbox/.gitkeep
var/trading-shadowlock/processed/.gitkeep
var/trading-shadowlock/state/.gitkeep
```

### Never tracked (enforced via .gitignore)
```
var/
**/user_data/backtest_results/
**/user_data/strategies/*_episode_*.py
**/user_data/config_episode_*.json
docs/context/trade-export-*_trades.csv
```

### Selectively tracked (commit manually when non-reproducible)
```
docs/context/forensics-*.md
docs/context/recovery-candidates-*.md
docs/context/self-improvement-run-*.md
docs/context/*_summary.json
docs/context/reconstruction/*.csv
docs/context/ledger-watchdog-*.md
```

### Never tracked (implicit — not in .gitignore but should never be committed)
```
docs/context/canonical-trading-status-*.md   ← cron-generated, auto-refreshed
docs/context/mem0-migration-*/               ← migration artifacts
docs/context/telegram-hygiene-*/             ← audit raw dumps
```

---

## Decision: JSONL vs SQLite

The Shadowlock ledger uses JSONL as the **source of truth** (append-only, auditable, git-diffable).
SQLite is a **read-only cache** built by `shadowlock_indexer.py` — always rebuildable from JSONL.

If SQLite is corrupt or missing: `python shadowlock/shadowlock_indexer.py --rebuild`

See: `docs/specs/shadowlock-writer-spec.md`
