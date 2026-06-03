# Trading Hub

Private control plane for the autonomous crypto trading research system at
`github.com/GoLukeEnviro/trading-hub`.

## What Trading Hub is

Trading Hub is the coordination layer, not the execution authority.
It ties together the signal core, the dry-run Freqtrade fleet, shared fleet
state, orchestrator automation, and audit documentation.

## Current operating mode

- Dry-run only.
- No live trading unless explicitly approved after the required validation
  gates are complete.
- No `dry_run=false` changes without a separate, explicit go-ahead.
- No exchange credentials belong in this repository.

## Trading dashboard

`dashboard.py` is the read-only observability surface for the fleet.

- Start it with `python3 dashboard.py` (default `PORT=5000`).
- The page is server-side rendered and re-reads data on every request.
- The live UI is intentionally lean: KPI row, current Hermes signals, bot table, system status, and a compact RiskGuard line.
- Keep analysis-heavy or low-value panels out of the main surface; move them into docs or audits instead.
- Fresh reads cover the bot SQLite databases, the latest Hermes signal JSON, and the current system-status snapshots.

For the current validated snapshot, see:
`docs/state/current-operational-state.md`.

## Core components

| Component | Role | Notes |
|-----------|------|-------|
| `ai-hedge-fund-crypto/` | Signal core | Active signal generator; upstream nested repo, ignored by the parent repo. |
| `orchestrator/` | Hermes control plane | Cron, audits, recovery, reports, gateways, and repo housekeeping. |
| `freqtrade/` | Dry-run execution fleet | FreqForge, Regime-Hybrid, Momentum, Canary, FreqAI-Rebel, shared state. |
| `freqforge/` | FreqForge bot | Baseline / override bot and supporting config. |
| `freqtrade/shared/` | FleetRisk + shared state | Shared coordination layer, watcher, and fleet-risk artifacts. |
| `bridge/` | Bridge code | Hermes/Primo bridge logic. |
| `primo/` | Primo agent code | Signal-filter and integration helpers. |
| `tools/freqforge/` | Shadow evaluator | Passive observer and report generator. |
| `dashboard.py` | Read-only observability | Single-file Flask dashboard; server-side rendered, no caches or websockets, live request-time reads only. |
| `docs/context/` | Historical context | Append-only reports, audits, and migration notes. |
| `docs/state/` | Current state | Current operational snapshot and live-readiness notes. |

## Repository layout

```text
trading-hub/
├── README.md
├── dashboard.py         # single-file Flask dashboard
├── AGENTS.md
├── SOUL.md
├── ORCHESTRATOR_CHARTER.md
├── .gitignore
├── docs/
│   ├── README.md
│   ├── context/
│   ├── decisions/
│   ├── runbooks/
│   └── state/
├── orchestrator/
├── tools/
├── freqforge/
├── freqtrade/
├── bridge/
├── primo/
├── backtests/
├── ai-hedge-fund-crypto/      # ignored nested clone
├── Agenten_Auto_Trade/                  # independent nested repo
├── btc5m-bot/                           # independent nested repo
├── Polymarket-BTC-15-Minute-Trading-Bot/ # independent nested repo
├── weatherbot/                          # independent nested repo
└── weatherhermes_persistent/            # separate project, ignored
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
  `docs/context/memory-migration-staging/`, `.hermes/`, `orchestrator/config/cron_jobs_backup.json`.
- Databases and binary artifacts: `*.sqlite`, `*.db`, `*.fthypt`, `*.feather`,
  `*.parquet`, `*.pkl`.

## Git workflow and branch safety

- Keep `main` synced with `origin/main`.
- Create a feature branch before publishing non-trivial changes.
- Stage files explicitly by path; do not use `git add .`.
- Review `git diff --cached` before committing.
- Do not rewrite history, force-push, or use destructive cleanup commands such
  as `git reset --hard` or `git clean -fdx`.
- Keep docs/context updated after meaningful work or incident resolution.

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

## Operational validation commands

```bash
git branch --show-current
git status -sb
git diff --name-status
git rev-parse HEAD
git rev-parse origin/main
git check-ignore -v shared/hermes_signal.json freqtrade/shared/fleet_risk_state.json \
  freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json \
  docs/context/git-cleanup-snapshots/
python3 /home/hermes/projects/trading/freqtrade/shared/fleet_watcher.py --once --tail-lines 20
```

## Documentation map

- `AGENTS.md` — agent safety and architecture guide.
- `SOUL.md` — project identity and operating principles.
- `docs/README.md` — documentation index.
- `docs/context/README.md` — historical context and report conventions.
- `docs/context/trading-dashboard-surface-audit-20260603.md` — current dashboard surface, design notes, and failure-handling rules.
- `docs/context/trading-dashboard-external-access-20260602.md` — Docker-socket and external-access notes for the dashboard.
- `docs/state/current-operational-state.md` — current operational snapshot.
- `docs/git-hygiene.md` — tracked vs ignored file policy.
