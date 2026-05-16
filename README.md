# Trading Hub

Parent/control repository for the autonomous trading system.
Private repo at `github.com/GoLukeEnviro/trading-hub`.

## What This Is

This is the **control plane** for a crypto trading research system.
It does NOT execute trades — all Freqtrade bots run in dry-run mode only.
The repo contains strategies, tooling, documentation, and infrastructure definitions.

## Active Components

| Component | Container | Port | Role |
|-----------|-----------|------|------|
| ai-hedge-fund-crypto | `ai-hedge-fund-crypto` | 8410 | Signal generator (TA + LLM) |
| FreqForge | `freqtrade-freqforge` | 8086 | Baseline strategy bot |
| Regime-Hybrid | `freqtrade-regime-hybrid` | 8085 | Regime-switching strategy bot |
| Momentum | `freqtrade-momentum` | 8084 | Momentum strategy bot |
| RSI | `freqtrade-rsi` | 8081 | RSI mean-reversion bot |
| MVS | `freqtrade-mvs` | — | NOT_DEPLOYED — strategy file preserved, no active container |
| FOMO Phase 3 | — | NOT_DEPLOYED — research code preserved under freqtrade/bots/fomo-phase3, no active container |
| Webserver | `freqtrade-webserver` | — | Freqtrade UI |
| Hermes Agent | `hermes-agent` | 8642 | Meta-orchestrator |
| Honcho | `honcho-api` | 8000 | Persistent memory |
| Caddy | `caddy` | 443 | Reverse proxy (Tailscale Funnel) |

All bots: dry_run=True, exchange=bitget, no real credentials.

## What This Repo Tracks

- **Strategy source files** — 49 `.py` strategy files across all bots (protected by .gitignore negation rules) (Stand 2026-05-14)
- **Freqtrade fleet compose** — `freqtrade/docker-compose.fleet.yml`
- **Signal infrastructure** — `docker-compose.ai-hedge-fund-crypto.yml`
- **FreqForge Shadow Evaluator** — `tools/freqforge/` (passive observer)
- **Orchestrator scripts** — `orchestrator/scripts/` (healthcheck, validators, observation)
- **Bridge & Primo code** — `bridge/`, `primo/`
- **Backtest tooling** — `backtests/` (scripts, benchmarks, lab strategies)
- **FOMO Phase 3 research** — `freqtrade/bots/fomo-phase3/research/` (11 modules, 89/92 tests pass)
- **Documentation** — `docs/context/` (49 phase reports as of 2026-05-14), `docs/git-hygiene.md`
- **Project identity** — `SOUL.md`, `AGENTS.md`, `ORCHESTRATOR_CHARTER.md`

## What This Repo Ignores

See `.gitignore` for the full list. Key exclusions:

- `.env` files and secrets — **never committed**
- Freqtrade bot configs — contain `jwt_secret_key` and UI passwords
- Freqforge configs — same reason
- Virtual environments (`.venv/`, ~1 GB)
- Databases (`.sqlite`, `.db`)
- Docker images (`freqtrade/shared/images/`, ~912 MB)
- Backups and archives (`backups/`, ~186 MB)
- Runtime state (`var/`, `logs/`, `output/`, `cache/`)
- Hyperopt results (binary `.fthypt` files)
- Exchange data downloads (`freqtrade/shared/downloads/`)
- Nested repos (see below)

## Nested Repositories

| Path | Remote | Relationship |
|------|--------|-------------|
| `Agenten_Auto_Trade/` | `git@github.com-trading:GoLukeEnviro/Agenten_Auto_Trade.git` | Independent repo (46 strategies, active) |
| `ai-hedge-fund-crypto/` | `https://github.com/51bitquant/ai-hedge-fund-crypto.git` | Upstream clone, ignored by parent |
| `weatherhermes_persistent/` | `https://github.com/alteregoeth-ai/weatherbot` | Unrelated project, ignored |

## Strategy Inventory

**Tracked in this repo (43 files):**

- `freqtrade/bots/regime-hybrid/user_data/strategies/` — 30 files (v2 through v9 lineage)
- `freqtrade/bots/momentum/user_data/strategies/` — 3 files
- `freqtrade/bots/rsi/user_data/strategies/` — 4 files
- `freqtrade/bots/mvs/user_data/strategies/` — 1 file
- `freqtrade/bots/fomo-phase3/user_data/strategies/` — 1 file
- `freqforge/user_data/strategies/` — 1 file (FreqForge_Override)
- `freqtrade/shared/strategies/` — 1 file (MinimalViableStrategy_v1)
- `freqforge/baseline_v1/` — 1 file (baseline strategy)
- `backtests/daily_lab/` — 4 files (daily strategy experiments)

**Tracked in nested repos:**
- `Agenten_Auto_Trade/user_data/strategies/` — ~46 files (independent repo)

## Safety Rules

1. **No secrets in git** — `.env` files, credentials, jwt_secret_key always ignored
2. **No live trading** — dry-run only unless explicitly approved (backtest → paper 48h → live)
3. **No database commits** — runtime state stays local
4. **Strategy files are sacred** — negation rules in `.gitignore` protect them
5. **Confidence >= 0.60** — hard limit, no trade below 60% confidence
6. **Min 60 paper trades** — before any strategy path unlock

## Project Structure

```
trading-hub/
├── SOUL.md                          project identity + rules
├── AGENTS.md                        system architecture + role definitions
├── ORCHESTRATOR_CHARTER.md          binding orchestration rules
├── README.md                        this file
├── .gitignore                       secret/binary/runtime exclusions
├── docker-compose.ai-hedge-fund-crypto.yml
├── orchestrator/                    scripts, reports, test-fixtures
├── tools/freqforge/                 shadow evaluator
├── freqforge/                       freqforge bot + baseline
├── freqtrade/                       fleet compose + 6 bots + shared modules
├── bridge/                          hermes-primo bridge
├── primo/                           primo agent code
├── backtests/                       benchmarks, daily lab, reports
├── docs/                            context reports, git-hygiene
├── Agenten_Auto_Trade/              [independent repo, ignored]
├── ai-hedge-fund-crypto/            [upstream clone, ignored]
└── weatherhermes_persistent/        [unrelated, ignored]
```
