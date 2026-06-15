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
7. Respect the kill switch (`freqtrade/shared/kill_switch.py`). If a cycle
   or script detects `HALT_NEW` or `EMERGENCY` mode, no new entries may be
   proposed or applied. Do not override an active kill switch without
   explicit human approval.

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

### RiskGuard / Judge — Safety Layer (SI V2 SPEC)

- Design reference for signal-cycle safety gates.
- Planned checks: schema validation, freshness, allowlist validation, action /
  confidence validation, and baseline-vs-LLM disagreement handling.
- Verdicts: `ACCEPTED`, `WATCH_ONLY`, `BLOCK_ENTRY`.
- Rules: BUY/SELL only for entries; TREND_HOLD / WATCH / HOLD never force an
  entry; weak or unknown signals degrade or block.
- SI v2 integration: runtime cycle enforces mutation counters, measurement
  ledger gating, and rainbow freshness guard (scoring gate = 0/10).

### ShadowLogger — Evidence Layer (DEPLOYED)

- Append-only JSONL audit trail for signal-cycle decisions.
- Output: `orchestrator/logs/shadow_decisions.jsonl`.
- SI v2 integration: Measurement Ledger (27 fleet cycles, 108 bot measurement
  points, 24 proposal records) writes deterministic JSONL artifacts.
- Principle: no side effects, no order execution, no hidden branching.

### Kill Switch — Central Safety Choke Point (PR #220)

- File-based atomic kill switch in `freqtrade/shared/kill_switch.py`.
- Three modes: `NORMAL` (no blocking), `HALT_NEW` (block entries, keep positions),
  `EMERGENCY` (block entries + signal position close).
- Integrated into `primo_signal.py:primo_gate_allows()` as the highest-priority check.
- CLI via `orchestrator/scripts/kill_switch_trigger.sh`.
- Auto-check mode reads `fleet_risk_state.json` and activates at configurable
  drawdown thresholds (default: HALT at 12%, EMERGENCY at 18%).
- Drawdown guard: auto-activates but does not override an already-active kill switch.
- See `docs/runbooks/kill-switch.md` for full operational procedures.

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
| FreqForge | `trading-freqtrade-freqforge-1` | 8086 | `FreqForge_Override` | dry-run |
| Regime-Hybrid | `trading-freqtrade-regime-hybrid-1` | 8085 | `RegimeSwitchingHybrid_v7_v04_Integration` | dry-run |
| FreqForge-Canary | `trading-freqtrade-freqforge-canary-1` | 8081 | `FreqForge_Override` | dry-run |
| FreqAI-Rebel | `trading-freqai-rebel-1` | 8087 | `RebelLiquidation + RebelXGBoostClassifier` | dry-run |
| Momentum | — | — | DECOMMISSIONED | — |
| MVS | — | — | NOT_DEPLOYED | — |
| Webserver | `trading-freqtrade-webserver-1` | — | UI only | — |

### SI v2 — Self-Improvement Engine (ACTIVE)

- Observation loop: Active Cycle Runner reads Freqtrade REST + Rainbow §5 (read_only)
  every 6 hours via Hermes cron.
- Measurement Ledger: 27 fleet cycles, 108 bot measurement points, 24 proposal records.
- Rainbow read_only source: observed but never scored, never applied, never executed.
- Controller status: `PAUSED / L3_REPOSITORY_ONLY` — all mutation counters zero.
- Scoring gate: 0/10 (awaiting producer freshness, not cycles).
- See `self_improvement_v2/README.md` for full module map and entry points.

### Decommissioned / historical

- Honcho persistent memory was decommissioned and archived.
- Momentum bot decommissioned (strategy archive-only).
- MVS bot never deployed.

## Documentation discipline

- After each meaningful change, update the relevant `docs/context/` report.
- Keep root docs in sync: `README.md`, `docs/README.md`, `docs/context/README.md`,
  `docs/state/current-operational-state.md`.
- Treat `docs/context/` as historical context, not as the canonical current state.
- Treat `docs/state/current-operational-state.md` as the current validated snapshot.
