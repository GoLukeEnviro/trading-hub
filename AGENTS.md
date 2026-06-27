# AGENTS.md — Trading Hub Agent Operating Guide

## Purpose

This is the primary operational instruction file for agents working in the
Trading Hub repository. It defines the current safety boundary, the SI-v2 loop
priority, and the scope rules that prevent drift into unrelated infrastructure
or healthcheck work.

Use `docs/state/current-operational-state.md` for the canonical runtime
snapshot. Use `docs/context/` and `docs/reports/` for historical evidence and
proof reports. Root instructions stay stable and must not carry volatile cycle,
ledger, score, or reachability counters.

## Binding operational priority order

When planning or executing work, use this priority order unless the user gives a
more specific approved scope:

1. **SI-v2 Loop** — keep the read-only Active Cycle loop coherent and verifiable.
2. **Historical Evidence** — preserve the historical trade window and per-bot
   historical summaries in evidence bundles and decisions.
3. **Measurement Attribution** — keep measurement provenance tied to the exact
   cycle, evidence bundle, and bot identity.
4. **ShadowProposal Quality** — improve proposal evidence quality without
   applying proposals or weakening approval gates.
5. **Runtime Safety** — preserve dry-run-only operation, mutation counters,
   kill-switch behavior, RiskGuard boundaries, and ShadowLogger evidence.

## Scope discipline

- Do **not** work on Docker, Guardian, Cron, generic healthchecks, generic CI,
  infrastructure cleanup, container restarts, or environment changes unless the
  issue directly blocks the SI-v2 loop or the user explicitly approves that
  scope.
- Do **not** treat stale root documentation as runtime truth. Revalidate against
  `docs/state/current-operational-state.md`, proof reports, and live evidence
  before acting.
- Do **not** bundle unrelated findings into a loop task. Open or recommend a
  separate follow-up instead.
- Docs-only alignment is L2. Runtime/config/strategy/Docker/Cron mutation is L3
  and requires explicit approval.

## Agent safety rules

1. Read `AGENTS.md` and `SOUL.md` before making changes.
2. Never use `git add .`; stage files explicitly by path only.
3. Never enable live trading, set `dry_run=false`, or change trading behavior
   without explicit approval.
4. Never use destructive cleanup commands such as `git reset --hard`,
   `git clean -fd`, `git clean -fdx`, pruning, volume removal, force-push, or
   history rewrite.
5. Always update the relevant `docs/context/` or `docs/reports/` record after
   meaningful work, incident resolution, bootstrap, cleanup, architecture
   change, or safety-relevant fix.
6. Never commit secrets, runtime state, databases, logs, backups, model files,
   inspect dumps, or generated local state.
7. Respect the kill switch (`freqtrade/shared/kill_switch.py`). If a cycle or
   script detects `HALT_NEW` or `EMERGENCY`, no new entries may be proposed or
   applied. Do not override an active kill switch without explicit human
   approval.

## Proven SI-v2 4-bot loop

The current agent assumption is a proven four-bot, dry-run SI-v2 Active Cycle
loop. Treat these bot ids as the active SI-v2 fleet unless an approved runtime
rollout and the canonical state file say otherwise:

- `freqtrade-freqforge`
- `freqtrade-freqforge-canary`
- `freqtrade-regime-hybrid`
- `freqai-rebel`

Loop semantics:

- The Active Cycle reads all four bots and preserves existing telemetry evidence.
- Historical evidence is additive: it must not replace the telemetry evidence
  window.
- ShadowProposals remain evidence-only until a separate human-approved apply
  path is invoked.
- Approval eligibility is not approval. A proposal that needs human approval is
  not applied by the loop.
- Mutation counters must remain zero for read-only proof and docs work.
- Profitability or scoring evidence is not live-trading authorization.

Decommissioned or non-deployed bots such as Momentum and MVS are historical
context only. Do not count them as active SI-v2 loop members.

## System architecture boundaries

### Signal layer — `ai-hedge-fund-crypto`

- Crypto-native signal generator using Bitget Futures OHLCV.
- Technical-analysis ensemble plus LLM-assisted portfolio decisions.
- Output is advisory only and must not force trades.
- The parent repo orchestrates and audits; it does not turn signals into direct
  execution authority.

### Hermes — Meta-Orchestrator

- Runs in the `orchestrator` profile for this project.
- Responsibilities: audits, repairs, cron maintenance when approved,
  documentation, escalation, and safe git housekeeping.
- Boundaries: does not decide trades directly, place orders, enable live
  trading, modify Freqtrade configs without approval, or restart containers
  without approval.
- Working directory: `/home/hermes/projects/trading`.

### SI-v2 — Self-Improvement Loop

- The SI-v2 controlled apply chain is now fully implemented on `main`.
- The first L3-gated canary apply (`max_open_trades 3→2`) is **runtime-proven**
  with `RuntimeEffectProof=GREEN`.
- The controller operates in **Phase 4 (Measurement Window)** — T0 GREEN, T1 YELLOW,
  T2/T3 pending. See `docs/state/current-operational-state.md`.
- The full controlled apply chain:
  `execute_apply()` → `plan_canary_restart_with_overlay()` →
  `check_restart_gate()` → `run_canary_restart_with_overlay()` →
  `RuntimeEffectProof` → `Measurement Decision Engine`
- The rollback path is rehearsed (Phase 5A) but **not executed**.
- The candidate pipeline exists (Phase 6A) with `execute=False` default.
- **No autonomous apply** is in scope. All mutating operations remain:
  canary-only, dry-run-only, human-gated, L3-token-gated.
- **No new apply, restart, or rollback** before T2/T3 evidence is evaluated.

### Freqtrade — Dry-run execution fleet

- Dry-run trade execution only; no live orders.
- Strategy-based entry/exit remains in Freqtrade strategy control.
- Signals are conservative filters and evidence inputs; they never force an
  entry.
- State is observed through REST/API evidence and read-only local artifacts.

### RiskGuard / Judge — Safety layer

- RiskGuard is the preferred risk authority for trading-affecting decisions.
- Signals, LLM suggestions, and ShadowProposals may be downgraded or blocked.
- BUY/SELL entries require valid safety context; HOLD/WATCH/TREND_HOLD style
  signals never force entries.

### ShadowLogger — Evidence layer

- ShadowLogger and related JSONL/report artifacts provide append-only evidence
  for decisions, approvals, incidents, and safety-relevant changes.
- If evidence logging is unavailable, read-only audits may continue with a
  warning, but decision/write actions must pause, block, or escalate.

### Kill switch — Central safety choke point

- The file-based kill switch lives in `freqtrade/shared/kill_switch.py`.
- Modes: `NORMAL`, `HALT_NEW`, and `EMERGENCY`.
- `HALT_NEW` and `EMERGENCY` block new entries. Do not override either mode
  without explicit human approval.

### FreqForge Shadow Evaluator — Passive observer

- Evaluates whether Freqtrade decisions would be approved, vetoed, reduced, or
  uncertain.
- Never places, modifies, cancels, or overrides trades.
- Runs against read-only Freqtrade data and the latest signal evidence.

### Primo and Bridge endpoints

- Primo and Bridge endpoints may require API-key headers depending on runtime
  environment.
- Never print, copy, persist, or expose endpoint credentials.
- Health endpoints are not proof that the SI-v2 loop is safe; validate the loop
  evidence artifacts instead.

## Runtime / autonomy change checklist

Before changing anything related to runtime behavior, autonomy, SI-v2, Docker,
Cron, Guardian, Freqtrade, strategy, risk, or signal thresholds:

1. Read `docs/state/current-operational-state.md` for the current validated
   runtime snapshot.
2. Read the latest relevant proof report under `docs/reports/` and historical
   context under `docs/context/`.
3. Confirm the planned change directly supports the SI-v2 loop or has explicit
   user approval.
4. Confirm the dry-run-only policy, kill-switch contract, RiskGuard boundary,
   and ShadowLogger evidence contract remain intact.
5. For L3 actions, stop and request explicit approval with rollback evidence.

## Documentation discipline

- Keep `SOUL.md` short and stable: identity, safety, and operating principles.
- Keep `AGENTS.md` as the primary operational instruction file.
- Keep `CLAUDE.md` as a thin handoff that defers to `AGENTS.md` and `SOUL.md`.
- Keep `ORCHESTRATOR_CHARTER.md` focused on durable charter rules and mark any
  historical/non-current references explicitly.
- Keep `README.md` as repository orientation, not a runtime metric store.
- Keep volatile runtime values — cycle ids, ledger counts, Rainbow/scoring
  counts, reachability snapshots, PR-specific proof details — in
  `docs/state/`, `docs/reports/`, or append-only `docs/context/` files.
