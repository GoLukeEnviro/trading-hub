# AGENTS.md — Trading Hub System Architecture

## Purpose

This is the repo-level operating guide for agents working in the Trading Hub.
It describes the current architecture, the safety boundary, and the documentation
rules that apply before any modification is made.

Use `docs/state/current-operational-state.md` for the latest validated runtime
snapshot and `docs/context/` for append-only historical reports.

## Agent safety rules

1. Read `AGENTS.md` and `SOUL.md` before making changes.
2. Never use `git add .`; stage files explicitly by path only.
3. Never enable live trading, set `dry_run=false`, or change trading behavior
   without explicit approval.
4. Never use destructive cleanup commands such as `git reset --hard`,
   `git clean -fd`, `git clean -fdx`, or force-push / history rewrite.
5. Always update `docs/context/` after meaningful work, incident resolution,
   bootstrap, cleanup, or architecture changes.
6. Never commit secrets, runtime state, databases, logs, backups, model files,
   or inspect dumps.

## System architecture

### ai-hedge-fund-crypto — Signal Layer (ACTIVE)

- Crypto-native signal generator using Bitget Futures OHLCV.
- Technical-analysis ensemble plus LLM-assisted portfolio decisions.
- Output: `ai-hedge-fund-crypto/output/hermes_signal.json`.
- HTTP endpoints: `/health`, `/signal`, `/trigger` on localhost:8410.
- Treated as the active signal core; the parent repo only orchestrates it.

### Hermes — Meta-Orchestrator

- Container / profile: `hermes-agent` in the `orchestrator` profile.
- Responsibilities: audits, repairs, cron maintenance, documentation,
  escalation, and safe git housekeeping.
- Boundaries: does not decide trades directly, does not place orders, does not
  enable live trading, does not modify Freqtrade configs without approval, and
  does not restart containers without approval.
- Working directory: `/home/hermes/projects/trading`.
- Project identity lives in `~/.hermes/profiles/orchestrator/SOUL.md`.

### RiskGuard / Judge — Safety Layer (SPEC ONLY)

- This layer is a design reference in AGENTS.md only.
- No deployed service, container, cron job, or script currently implements it as
  a standalone component.
- Planned checks: schema validation, freshness, allowlist validation, action /
  confidence validation, and baseline-vs-LLM disagreement handling.
- Verdicts: `ACCEPTED`, `WATCH_ONLY`, `BLOCK_ENTRY`.
- Rules: BUY/SELL only for entries; TREND_HOLD / WATCH / HOLD never force an
  entry; weak or unknown signals degrade or block.

### ShadowLogger — Evidence Layer (SPEC ONLY)

- This layer is the append-only audit concept for signal-cycle decisions.
- No deployed service currently implements it as a standalone component.
- Planned output: JSONL decision log, state snapshot, and snapshot directory.
- Principle: no side effects, no order execution, no hidden branching.

### FreqForge Shadow Evaluator — v0.1 (PASSIVE)

- Passive observer that evaluates whether Freqtrade decisions would be
  approved, vetoed, reduced, or marked uncertain.
- Never places, modifies, cancels, or overrides trades.
- Runs against read-only Freqtrade SQLite data and the latest signal JSON.
- Hard constraint: all bots remain `dry_run=True`.

### Freqtrade — Dry-Run Execution Fleet

- Dry-run trade execution only; no live orders.
- Strategy-based entry/exit with signal as a conservative filter.
- State reporting via REST API and SQLite trade history.

| Bot | Container | Port | Strategy | Mode |
|-----|-----------|------|----------|------|
| FreqForge | `freqtrade-freqforge` | 8086 | `FreqForge_Override` | dry-run |
| Regime-Hybrid | `freqtrade-regime-hybrid` | 8085 | `RegimeSwitchingHybrid_v7_v04_Integration` | dry-run |
| FreqForge-Canary | `freqtrade-freqforge-canary` | 8081 | `FreqForge_Override` | dry-run |
| FreqAI-Rebel | `freqai-rebel` | 8087 | `RebelLiquidation + RebelXGBoostClassifier` | dry-run |
| Momentum | — | — | DECOMMISSIONED | — |
| MVS | — | — | NOT_DEPLOYED | — |
| Webserver | `freqtrade-webserver` | — | UI only | — |

### Decommissioned / historical

- Honcho persistent memory was decommissioned and archived.
- Caddy remains the reverse proxy layer for the host.

## Documentation discipline

- After each meaningful change, update the relevant `docs/context/` report.
- Keep root docs in sync: `README.md`, `docs/README.md`, `docs/context/README.md`,
  `docs/state/current-operational-state.md`.
- Treat `docs/context/` as historical context, not as the canonical current state.
- Treat `docs/state/current-operational-state.md` as the current validated snapshot.
