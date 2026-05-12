# Trading Hub

Parent/control repository for the autonomous trading system.

## What This Repo Tracks

- **Orchestrator tooling** — scripts, runbooks, state files
- **Freqtrade fleet configs** — docker-compose, bot configs (sanitized)
- **Strategy source files** — all `.py` strategy files under `freqtrade/bots/`, `freqforge/`
- **FreqForge Shadow Evaluator** — `tools/freqforge/`
- **Bridge & Primo agent** — `bridge/`, `primo/`
- **Docker compose** — root-level compose files for signal infrastructure
- **Documentation** — `docs/`, `AGENTS.md`, `SOUL.md`, `ORCHESTRATOR_CHARTER.md`
- **Backtest scripts** — `backtests/` (scripts and reports, not data)
- **Research code** — `freqtrade/bots/fomo-phase3/research/` source files

## What This Repo Ignores

See `.gitignore` for the full list. Key exclusions:

- `.env` files and secrets — never committed
- Virtual environments (`.venv/`)
- Databases (`.sqlite`, `.db`)
- Docker images (`freqtrade/shared/images/`)
- Backups and archives (`backups/`, `*.tar.gz`)
- Runtime state (`var/`, `logs/`, `output/`, `cache/`)
- Hyperopt results (binary `.fthypt` files)
- Nested repos: `ai-hedge-fund-crypto/` (upstream), `weatherhermes_persistent/` (unrelated)

## Nested Repositories

| Path | Remote | Status |
|------|--------|--------|
| `Agenten_Auto_Trade/` | `git@github.com-trading:GoLukeEnviro/Agenten_Auto_Trade.git` | Independent repo |
| `ai-hedge-fund-crypto/` | `https://github.com/51bitquant/ai-hedge-fund-crypto.git` | Upstream clone, ignored by parent |
| `weatherhermes_persistent/weatherbot_master/` | `https://github.com/alteregoeth-ai/weatherbot` | Unrelated project, ignored |

## Architecture

This repo is the control plane. It does NOT execute trades.
See `AGENTS.md` for the full role/agent architecture.

```
trading-hub/                  <-- this repo
├── AGENTS.md                     agent role definitions
├── SOUL.md                       orchestrator identity
├── ORCHESTRATOR_CHARTER.md       binding rules
├── docker-compose.ai-hedge-fund-crypto.yml
├── orchestrator/                 scripts, runbooks, reports
├── tools/freqforge/              shadow evaluator
├── freqforge/                    freqforge bot configs + strategies
├── freqtrade/                    fleet compose + bot strategies
├── bridge/                       hermes-primo bridge
├── primo/                        primo agent
├── backtests/                    scripts and reports
├── docs/                         living documentation
└── Agenten_Auto_Trade/           [independent git repo]
```

## Safety Rules

1. **No secrets in git** — `.env` files are always ignored
2. **No live trading** — dry-run only unless explicitly approved
3. **No database commits** — runtime state stays local
4. **Strategy files are sacred** — negation rules in `.gitignore` protect them
