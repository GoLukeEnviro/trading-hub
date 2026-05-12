# AGENTS.md — Trading Hub System Architecture

## System Architecture

Autonomous trading orchestration system with clear role separation.
All components run as Docker containers on a single host.
Version-controlled at `github.com/GoLukeEnviro/trading-hub`.

## Role Definitions

### ai-hedge-fund-crypto — Signal Layer (ACTIVE)

**Role:** Crypto-native signal generator using Bitget Futures OHLCV,
technical analysis ensemble, deterministic risk management, and
DeepSeek V4 Pro LLM portfolio decisions.

**Status:** Active. Container `ai-hedge-fund-crypto` (port 8410, healthy).
Exchange: bitget. Model: deepseek-v4-pro @ temp 0.15.
Base URL: Ollama cloud endpoint.

**Output:** `ai-hedge-fund-crypto/output/hermes_signal.json`

**Endpoints (localhost:8410):**
- `GET /health` — container health + signal freshness
- `GET /signal` — latest Hermes signal JSON
- `GET /trigger` — run analysis cycle on demand

**Compose:** `docker-compose.ai-hedge-fund-crypto.yml`
**Source:** upstream clone of `github.com/51bitquant/ai-hedge-fund-crypto` (ignored by parent repo)

---

### Hermes — Meta-Orchestrator

**Container:** `hermes-agent` (CLI, persistent)

**Responsibilities:**
- Profile isolation (`orchestrator` profile)
- Tool execution (terminal, file, docker, cron)
- System audits (Reality Lock, Fleet Safety, Skill Audit)
- Repairs (container recovery, cron repair, config sync)
- Documentation (docs/context updates after every phase)
- Human escalation interface (Telegram/Gateway)
- Subagent delegation for research/dev/review tasks
- Git housekeeping for trading-hub repo

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

---

### RiskGuard / Judge — Safety Layer

**Responsibilities:**
- Schema validation against expected signal format
- Signal freshness check (max 45 minutes)
- Pair allowlist validation
- Action/confidence validation
- Baseline/LLM disagreement detection
- Signal quality assessment

**Verdicts:**
- `ACCEPTED` — signal passes all gates
- `WATCH_ONLY` — informational only, no entry
- `BLOCK_ENTRY` — signal blocked due to risk

**Rules:**
- Entry candidates: BUY/SELL only
- Informational: TREND_HOLD, WATCH, HOLD → never entry
- `signal_quality == weak` → WATCH_ONLY
- Unknown pair/action/quality → BLOCK_ENTRY
- Baseline/LLM disagreement → downgrade

---

### ShadowLogger — Evidence Layer

**Responsibilities:**
- Append-only JSONL logging of every signal cycle
- Daily aggregation and summary report generation
- No side effects, no API calls, no trade execution

**Output:**
- `var/freqforge/shadow_decisions.jsonl` — append-only decision log
- `var/freqforge/state.json` — trade-ID state for change detection
- `var/freqforge/snapshots/` — hourly snapshot directory

---

### FreqForge Shadow Evaluator — v0.1 (PASSIVE)

**Role:** Passive shadow layer that observes Freqtrade dry-run activity and evaluates
whether each entry/exit decision would be approved, vetoed, reduced, or marked uncertain.
Does NOT place, modify, cancel, force-exit, or override any trade.

**Status:** Active. No trade execution capability.

**Components:**
- `tools/freqforge/freqforge_shadow.py` — main poll loop
- `tools/freqforge/freqforge_rules.py` — deterministic rule engine
- `tools/freqforge/freqforge_config.py` — bot map + thresholds
- `tools/freqforge/freqforge_report.py` — markdown report generator

**Data Sources:**
- Freqtrade SQLite DBs via `docker exec sqlite3` (read-only SELECT)
- ai-hedge-fund-crypto signal: `ai-hedge-fund-crypto/output/latest/hermes_signal.json`

**Rule Groups:**
- ENTRY_RULES (E1-E5): evaluated on new trade open
- OPEN_RISK_RULES (O1-O3): evaluated each poll for open positions
- EXIT_RULES (X1-X3): post-hoc review on closed trades

**Hard constraints:** dry_run=True enforced on all bots. No modification of strategies,
configs, or container state. no_action_taken=True + shadow_mode=True in every event.

---

### Freqtrade — Execution Fleet

**Responsibilities:**
- Dry-run trade execution (Bitget futures)
- Strategy-based entry/exit
- Signal as conservative filter
- State reporting via REST API
- Trade history in SQLite

**Active Bots:**

| Bot | Container | Port | Strategy | Exchange | Mode |
|-----|-----------|------|----------|----------|------|
| FreqForge | `freqtrade-freqforge` | 8086 | FreqForge_Override | bitget | dry-run |
| Regime-Hybrid | `freqtrade-regime-hybrid` | 8085 | RegimeSwitchingHybrid_v7_v04_Integration | bitget | futures |
| Momentum | `freqtrade-momentum` | 8084 | MomentumBG15_v1 | bitget | futures |
| RSI | `freqtrade-rsi` | 8081 | SimpleRSIOnly_v1 | bitget | futures |
| MVS | `freqtrade-mvs` | 8087 | MinimalViableStrategy_v1 | bitget | futures |
| Webserver | `freqtrade-webserver` | — | — | — | UI only |

**Stopped / Staged:**

| Bot | Port | Strategy | Status |
|-----|------|----------|--------|
| FOMO Phase 3 | 8087 | FOMO_Phase3_v0 | stopped, initial_state=stopped |

**Fleet Compose:** `freqtrade/docker-compose.fleet.yml`

**Boundaries:**
- Dry-run only — no exchange credentials
- No signal forces a trade
- Fail-open on stale/missing signal
- Conservative fallback to normal strategy logic

**Strategy Lineage (regime-hybrid — most evolved):**
RegimeSwitchingHybrid v2 → v3_Final → v4_ATR → v5_ATRv2 → v6_Stable → v6.1_Fett → v7_EntryRefactor → v7_v04_Integration (active) → v8_BaselineTest → v8.1/8.2/8.3_RRR → v8.3_Filter → v9.1_Sentient (research)

---

### Honcho — Persistent Memory

**Containers:** honcho-api, honcho-database (PostgreSQL), honcho-redis, honcho-ollama, honcho-deriver
**Status:** Active. writeFrequency=session. DB ~2,000 docs.
**Models:** qwen3-coder:480b, gpt-oss:120b, deepseek-v3.1:671b
**Deriver:** MQG v2.0.0 via ro bind mount
**Watchdog:** Hourly cron alerts Telegram

---

### Caddy — Reverse Proxy

**Container:** `caddy` (host network)
**Tailscale Funnel:** `taile6801f.ts.net:443` → Caddy → Docker containers
**Freqtrade Web UI:** `https://agent0.taile6801f.ts.net:9092`

## Profile Structure

```
~/.hermes/profiles/
├── default/       — general-purpose profile
├── mira/          — Mira content pipeline (stopped)
├── trading/       — future domain/worker profile
└── orchestrator/  — meta-control profile (ACTIVE)
```

## Project Structure

```
/home/hermes/projects/trading/         ← git root (trading-hub)
├── SOUL.md                            — project identity + rules
├── AGENTS.md                          — this file
├── ORCHESTRATOR_CHARTER.md            — binding orchestration rules
├── README.md                          — repo overview
├── .gitignore                         — secret/binary/runtime exclusions
├── docs/
│   ├── context/                       — living documentation (40+ reports)
│   ├── git-hygiene.md                 — what is tracked and why
│   └── hermes-integration-plan.md     — integration reference
├── orchestrator/
│   ├── scripts/                       — fleet_healthcheck, multicycle_validator, etc.
│   ├── reports/                       — generated reports (fleet health, observation)
│   ├── state/                         — runtime state (gitignored)
│   ├── runbooks/                      — operational procedures
│   └── test-fixtures/                 — phase-12-6 signal/risk/state fixtures
├── tools/
│   └── freqforge/                     — FreqForge Shadow Evaluator v0.1
│       ├── freqforge_config.py        — bot map + thresholds
│       ├── freqforge_rules.py         — deterministic rule engine
│       ├── freqforge_shadow.py        — main poll loop
│       └── freqforge_report.py        — markdown report generator
├── freqforge/                         — FreqForge bot instance
│   ├── config/                        — config (gitignored, has jwt keys)
│   ├── baseline_v1/                   — baseline strategy + config
│   └── user_data/strategies/          — FreqForge_Override.py
├── ai-hedge-fund-crypto/              — [ignored] upstream clone
│   ├── output/                        — signal output (gitignored)
│   ├── src/                           — signal generator source
│   └── docker/                        — Dockerfile + entrypoint
├── freqtrade/
│   ├── docker-compose.fleet.yml       — fleet orchestration
│   ├── bots/
│   │   ├── regime-hybrid/             — 30 strategy versions, active config
│   │   ├── momentum/                  — MomentumBG15 variants
│   │   ├── rsi/                       — SimpleRSI strategies
│   │   ├── mvs/                       — MinimalViableStrategy
│   │   ├── fomo-phase3/              — FOMO research (stopped)
│   │   └── sve/                       — SVE bot
│   ├── shared/
│   │   ├── strategies/                — shared strategy files
│   │   ├── exit_agent_v9.py           — ExitAgent prompt + logic
│   │   ├── fleetguard_v1.py           — fleet guard module
│   │   ├── primo_gate.py             — signal gate module
│   │   ├── primo_signal.py           — signal bridge helper
│   │   └── signals/latest_signal.json — latest bridged signal
│   ├── tools/primo_signal_bridge.py   — signal bridge script
│   └── tests/                         — fleetguard tests
├── bridge/
│   ├── hermes_primo_bridge.py         — Hermes-Primo bridge
│   └── Dockerfile                     — bridge container
├── primo/
│   ├── primo_api.py                   — PrimoAgent API
│   ├── llm_signal_filter.py           — LLM signal filter
│   └── Dockerfile                     — Primo container
├── backtests/
│   ├── benchmarks/                    — multi-model LLM benchmarks
│   ├── daily_lab/                     — daily strategy experiments
│   ├── reports/                       — backtest reports
│   ├── walk_forward/                  — walk-forward results
│   └── signal_quality/                — signal quality analysis
├── Agenten_Auto_Trade/                — [ignored] independent git repo
├── backups/                           — [gitignored] cold archives
├── var/                               — [gitignored] runtime state
└── logs/                              — [gitignored] operational logs
```

## Communication Protocol

- All responses start with a status line (OK/WARN/FAIL/INFO)
- Technical content in English
- Casual German for meta-communication
- Zero disclaimers
- Evidence files always listed
- Next actions always specified
