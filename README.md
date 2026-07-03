# Trading Hub

Private control plane for the autonomous crypto trading research system at
`github.com/GoLukeEnviro/trading-hub`.

## What Trading Hub is

Trading Hub is the coordination layer, not the execution authority. It ties
together the signal core, the dry-run Freqtrade fleet, shared fleet state,
orchestrator automation, SI-v2 evidence generation, and audit documentation.

Root documentation is stable orientation. Current runtime facts — cycle ids,
ledger counts, Rainbow/scoring values, bot reachability, evidence hashes, and
PR-specific proof details — belong in `docs/state/`, `docs/reports/`, and
`docs/context/`.

## Current operating mode

- Dry-run only.
- No live trading unless explicitly approved after the required validation
  gates are complete.
- No `dry_run=false` changes without a separate, explicit go-ahead.
- No exchange credentials belong in this repository.

For the canonical current operational snapshot, read:
`docs/state/current-operational-state.md`.

> [📋 Live Roadmap — GitHub Issue #423](https://github.com/GoLukeEnviro/trading-hub/issues/423)
> [📋 Roadmap v2 (historical) →](docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md)
> [📋 Implementation Roadmap (historical) →](docs/roadmap/implementation-roadmap.md)
> Phase overview, completed issues, next priorities. Issue #423 is the canonical
> live roadmap; `roadmap-v2` is historical context.

## Proven SI-v2 loop orientation

The current SI-v2 assumption is a proven four-bot, read-only Active Cycle loop.
For operational instructions, follow `AGENTS.md` first.

Active SI-v2 bot identities:

- `freqtrade-freqforge`
- `freqtrade-freqforge-canary`
- `freqtrade-regime-hybrid`
- `freqai-rebel`

Momentum and MVS are historical/non-current and are not active SI-v2 loop
members. Do not start Docker, Guardian, Cron, healthcheck, generic CI, or
infrastructure work from README context alone; such work needs direct SI-v2-loop
blocker evidence or explicit approval.

## Trading dashboard

`dashboard.py` is the read-only observability surface for the fleet.

- Start it with `python3 dashboard.py` (default `PORT=5000`).
- The page is server-side rendered and re-reads data on every request.
- The live UI is intentionally lean: KPI row, current Hermes signals, bot table,
  system status, and a compact RiskGuard line.
- Keep analysis-heavy or low-value panels out of the main surface; move them
  into docs or audits instead.
- Fresh reads cover the bot SQLite databases, the latest Hermes signal JSON, and
  the current system-status snapshots.

## Core components

| Component | Role | Notes |
|-----------|------|-------|
| `ai-hedge-fund-crypto/` | Signal core | Active signal generator; upstream nested repo, ignored by the parent repo. |
| `orchestrator/` | Hermes control plane | Cron, audits, recovery, reports, gateways, and repo housekeeping. |
| `self_improvement_v2/` | SI-v2 engine | Active Cycle Runner, Historical Evidence, Measurement Attribution, ShadowProposals, runtime safety gates. |
| `freqtrade/` | Dry-run execution fleet | Active SI-v2 fleet state, shared safety code, and bot-specific config directories. |
| `freqforge/` | FreqForge bot | Baseline / override bot and supporting config. |
| `freqforge-canary/` | Canary bot | Independent FreqForge instance for canary testing. |
| `freqtrade/shared/` | FleetRisk + shared state | Shared coordination layer, watcher, fleet-risk artifacts, and kill switch (`kill_switch.py`). |
| `bridge/` | Bridge code (decommissioned) | Hermes/Primo bridge logic — replaced by SI-v2 autonomous loop (ADR-2026-07-01). |
| `primo/` | Primo agent (decommissioned) | Signal-filter and integration helpers — replaced by SI-v2 autonomous loop. |
| `shadowlock/` | ShadowLock service | Read-only evidence trail and decision logging. |
| `intelligence/` | Intelligence layer (vestigial) | Market intelligence and analysis modules — no active code. |
| `tools/freqforge/` | Shadow evaluator | Passive observer and report generator. |
| `orchestrator/scripts/` | Operation scripts | Approved automation entry points and helper scripts. |
| `dashboard.py` | Read-only observability | Single-file Flask dashboard; server-side rendered, no caches or websockets, live request-time reads only. |
| `Caddyfile` | Reverse proxy | Caddy configuration for fleet dashboard and service routing. |
| `docs/context/` | Historical context | Append-only reports, audits, and migration notes. |
| `docs/reports/` | Proof reports | Validations and proof write-ups. |
| `docs/state/` | Current state | Canonical operational snapshot and live-readiness notes. |
| `docs/runbooks/` | Runbooks | Operational procedures: kill-switch, gateway debug, health audits. |
| `scripts/` | Utility scripts | Bootstrap, cleanup, and maintenance helpers. |
| `var/` | Runtime state files | Kill-switch state (`var/kill_switch.json`), not tracked in git. |

## Repository layout

```text
trading-hub/
├── README.md
├── CHANGELOG.md
├── AGENTS.md
├── SOUL.md
├── ORCHESTRATOR_CHARTER.md
├── Caddyfile
├── docker-compose.yml
├── docker-compose.ai-hedge-fund-crypto.yml
├── .github/
├── .gitignore
├── dashboard.py
├── pyproject.toml
├── uv.lock
│
├── docs/
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── GAP-REPORT-2026-06-15-TRADING-HUB.md
│   ├── git-hygiene.md
│   ├── context/               # append-only historical reports
│   ├── reports/               # proof and validation reports
│   ├── decisions/             # ADR decision records
│   ├── runbooks/              # operational runbooks
│   ├── roadmap/               # roadmap docs (canonical + historical)
│   ├── roadmaps/              # SI-v2 continuous implementation control plane
│   ├── specs/                 # safety contracts and specifications
│   ├── state/                 # current operational snapshots
│   └── archive/               # historical/archived documents
│
├── orchestrator/              # Hermes control plane
├── self_improvement_v2/       # SI-v2 engine
├── freqtrade/                 # dry-run execution fleet
├── freqforge/                 # FreqForge bot
├── freqforge-canary/          # canary FreqForge instance
├── bridge/                    # Hermes/Primo bridge logic
├── primo/                     # Primo agent code
├── shadowlock/                # ShadowLock evidence service
├── intelligence/              # market intelligence modules
├── tools/freqforge/           # shadow evaluator (passive)
├── scripts/                   # utility scripts
├── var/                       # runtime state files (not tracked)
├── backtests/                 # backtest results and configs
├── tests/                     # integration tests
├── logs/                      # runtime logs (not tracked)
├── events/                    # event artifacts (not tracked)
├── proposals/                 # shadow proposal artifacts (not tracked)
├── archive/                   # archived artifacts
├── local-memory/              # local memory stack
│
├── ai-hedge-fund-crypto/      # ignored nested clone
├── Agenten_Auto_Trade/        # independent nested repo
├── btc5m-bot/                 # independent nested repo
├── Polymarket-BTC-15-Minute-Trading-Bot/  # independent nested repo
├── polymarket-fadi/           # independent nested repo
├── weatherbot/                # independent nested repo
├── weatherhermes_persistent/  # separate project, ignored
└── weatherhermes_backup/      # separate project, ignored
```

## Runtime files that must not be committed

Treat these as local-only runtime or generated artifacts unless a file is
explicitly reviewed and approved for version control:

- Secrets and credentials: `.env`, `.env.*`, `*.pem`, `*.key`, local SSH
  configs, WebUI credential files.
- Runtime state: `shared/hermes_signal.json`, `freqtrade/shared/*state*.json`,
  `freqtrade/shared/*.lock`, `freqtrade/bots/*/user_data/primo_signal_state.json`,
  `freqtrade/bots/*/user_data/signals/`.
- Local RiskGuard trail: `tools/riskguard/decisions.jsonl`.
- Logs and generated output: `logs/`, `var/`, `output/`, `cache/`, `events/`,
  `proposals/`.
- Backups and archives: `backups/`, `orchestrator/backups/`, `**/*.bak`,
  `**/*.bak-*`, `*.backup.*`.
- Local cleanup / staging folders: `docs/context/git-cleanup-snapshots/`,
  `docs/context/memory-migration-staging/`, `.hermes/`,
  `orchestrator/config/cron_jobs_backup.json`.
- Databases and binary artifacts: `*.sqlite`, `*.db`, `*.fthypt`, `*.feather`,
  `*.parquet`, `*.pkl`.

## Git workflow and branch safety

- Keep `main` synced with `origin/main`.
- Create a feature branch before publishing non-trivial changes.
- Stage files explicitly by path; do not use `git add .`.
- Review `git diff --cached` before committing.
- Do not rewrite history, force-push, or use destructive cleanup commands such
  as `git reset --hard` or `git clean -fdx`.
- Keep docs/context or docs/reports updated after meaningful work, incident
  resolution, architecture changes, or safety-relevant fixes.

## Security notes

- No secrets in Git.
- Local SSH config is ignored.
- WebUI credential files are ignored.
- Strategy and config files are treated as sensitive until reviewed.
- Backups, logs, inspect dumps, and runtime state should stay local.

## Current known risks before live trading

- Live trading is not approved in this repository.
- Strategy or config changes require explicit review and sign-off.
- Runtime state can drift from documentation; revalidate before acting.
- Some research and cleanup artifacts are intentionally left local until they
  are classified and archived.

## Repository validation commands

These commands are safe read-only checks for repo hygiene. Runtime checks should
follow `AGENTS.md` and the current state/proof report, not README assumptions.

```bash
git branch --show-current
git status -sb
git diff --name-status
git rev-parse HEAD
git rev-parse origin/main
git check-ignore -v shared/hermes_signal.json freqtrade/shared/fleet_risk_state.json \
  freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json \
  docs/context/git-cleanup-snapshots/
```

## Documentation map

- `AGENTS.md` — primary agent safety, SI-v2 priority, scope, and architecture guide.
- `SOUL.md` — project identity and operating principles.
- `ORCHESTRATOR_CHARTER.md` — durable orchestration charter.
- `README.md` — repository overview (this file).
- `docs/README.md` — documentation index.
- `docs/context/README.md` — historical context and report conventions.
- `docs/state/current-operational-state.md` — canonical current operational snapshot.
- `docs/state/si-v2-capability-matrix.md` — SI-v2 capability status.
- `docs/GAP-REPORT-2026-06-15-TRADING-HUB.md` — gap register.
- `docs/runbooks/kill-switch.md` — kill-switch operational runbook.
- `docs/git-hygiene.md` — tracked vs ignored file policy.
- `self_improvement_v2/README.md` — SI-v2 subsystem overview and module map.
