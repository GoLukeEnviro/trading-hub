# AGENTS.md — Trading Orchestrator Roles

## System Architecture

This project implements an autonomous trading orchestration system with clear role separation.

## Role Definitions

### ai-hedge-fund-crypto — Signal Layer (ACTIVE)

**Role:** Crypto-native signal generator using Bitget Futures OHLCV,
technical analysis ensemble, deterministic risk management, and
DeepSeek V4 Pro LLM portfolio decisions.

**Status:** Active. Container `ai-hedge-fund-crypto` (port 8410).
Exchange: bitget. Model: deepseek-v4-pro @ temp 0.15.
Base URL: https://ollama.com/v1.

**Output:** `/home/hermes/projects/trading/ai-hedge-fund-crypto/output/hermes_signal.json`

**Endpoints (localhost:8410):**
- `GET /health` — container health + signal freshness
- `GET /signal` — latest Hermes signal JSON
- `GET /trigger` — run analysis cycle on demand

### Hermes — Meta-Orchestrator

**Responsibilities:**
- Profile isolation (`orchestrator` profile)
- Tool execution (terminal, file, docker, cron)
- System audits (Reality Lock, Fleet Safety, Skill Audit)
- Repairs (container recovery, cron repair, config sync)
- Documentation (docs/context updates)
- Human escalation interface (Telegram/Gateway)
- Subagent delegation for research/dev/review tasks

**Boundaries:**
- Does not decide trades directly
- Does not place orders
- Does not enable live trading without approval
- Does not modify Freqtrade configs without approval
- Does not restart containers without approval

**Profile:**
- Name: `orchestrator`
- Working directory: `/home/hermes/projects/trading`
- SOUL: `~/.hermes/profiles/orchestrator/SOUL.md`

### RiskGuard / Judge — Safety Layer

**Responsibilities:**
- Schema validation
- Signal freshness check
- Pair allowlist validation
- Action/confidence validation
- Baseline/LLM disagreement detection
- Signal quality assessment

**Verdicts:**
- `ACCEPTED` — signal passes all gates
- `WATCH_ONLY` — informational only, no entry
- `BLOCK_ENTRY` — signal blocked due to risk

### ShadowLogger — Evidence Layer

**Responsibilities:**
- Append-only JSONL logging
- Daily aggregation
- Summary report generation
- No side effects
- No API calls
- No trade execution

**Output:**
- `var/freqforge/shadow_decisions.jsonl` — append-only decision log
- `var/freqforge/state.json` — trade-ID state for change detection
- `var/freqforge/snapshots/` — hourly snapshot directory

### FreqForge Shadow Evaluator — v0.1 (PASSIVE)

**Role:** Passive shadow layer that observes Freqtrade dry-run activity and evaluates
whether each entry/exit decision would be approved, vetoed, reduced, or marked uncertain.
Does NOT place, modify, cancel, force-exit, or override any trade.

**Status:** Active (Phase 47). No trade execution capability.

**Components:**
- `tools/freqforge/freqforge_shadow.py` — main poll loop
- `tools/freqforge/freqforge_rules.py` — deterministic rule engine
- `tools/freqforge/freqforge_config.py` — bot map + thresholds
- `tools/freqforge/freqforge_report.py` — markdown report generator

**Output:**
- `var/freqforge/shadow_decisions.jsonl` — append-only decision log
- `var/freqforge/state.json` — trade-ID state for change detection

**Data Sources:**
- Freqtrade SQLite DBs via `docker exec sqlite3` (read-only SELECT)
- ai-hedge-fund-crypto signal: `ai-hedge-fund-crypto/output/latest/hermes_signal.json`

**Rule Groups:**
- ENTRY_RULES (E1-E5): evaluated on new trade open
- OPEN_RISK_RULES (O1-O3): evaluated each poll for open positions
- EXIT_RULES (X1-X3): post-hoc review on closed trades

**Hard constraints:** dry_run=True enforced on all bots. No modification of strategies,
configs, or container state. no_action_taken=True + shadow_mode=True in every event.

### Freqtrade — Execution Fleet

**Responsibilities:**
- Dry-run trade execution
- Strategy-based entry/exit
- Signal als konservativer Filter
- State reporting via REST API
- Trade history in SQLite

**Bots:**
- `freqtrade-freqforge` (port 8086) — FreqForge_Override. **Gold Standard baseline.**
- `freqtrade-regime-hybrid` (port 8085) — RegimeSwitchingHybrid_v7_v04_Integration (futures)
- `freqtrade-rsi` (port 8081) — RSIMeanReversionV11 (spot)
- `freqtrade-momentum` (port 8084) — MomentumBG15_v1 (futures)

**Boundaries:**
- Dry-run only
- No signal forces a trade
- Fail-open on stale/missing signal
- Conservative fallback to normal strategy logic

## Profile Structure

```
~/.hermes/profiles/
├── default/       — general-purpose profile (unchanged)
├── mira/          — Mira content pipeline (stopped)
├── trading/       — future domain/worker profile
└── orchestrator/  — meta-control profile (NEW)
```

## Project Structure

```
/home/hermes/projects/trading/
├── SOUL.md                    — project identity
├── AGENTS.md                  — this file
├── ORCHESTRATOR_CHARTER.md    — binding orchestration rules
├── docs/
│   ├── context/               — living documentation
│   ├── architecture/          — system diagrams
│   ├── decisions/             — ADRs
│   └── incidents/             — incident reports
├── orchestrator/
│   ├── scripts/               — automation scripts
│   ├── reports/               — generated reports
│   ├── state/                 — orchestrator state
│   ├── runbooks/              — operational procedures
│   └── logs/                  — orchestrator logs
├── ai-hedge-fund-crypto/     # Active signal generator (Docker service)
│   ├── output/                # Signal output: latest/, history/, logs/
│   └── src/
├── tools/
│   └── freqforge/             # FreqForge Shadow Evaluator v0.1
│       ├── freqforge_config.py
│       ├── freqforge_rules.py
│       ├── freqforge_shadow.py
│       └── freqforge_report.py
├── var/freqforge/             # FreqForge state + append-only logs
│   ├── shadow_decisions.jsonl
│   ├── state.json
│   └── snapshots/
├── freqtrade/           # Strategies & configs (5 bots, dry-run)
│   ├── docker-compose.fleet.yml
│   ├── bots/
│   ├── shared/
│   └── logs/
├── backtests/           # Results & reports
├── backups/             # Cold archives (phase45-primoagent-archive-*)
└── docs/                # Decisions, ideas, architecture
```

## Communication Protocol

- All responses start with a status line (✅/⚠️/🔴/🟡)
- Technical content in English
- Casual German for meta-communication
- Zero disclaimers
- Evidence files always listed
- Next actions always specified
