# ORCHESTRATOR_CHARTER.md — Binding Orchestration Rules

## Mission

This charter defines durable orchestration rules for the autonomous trading
research system. `ai-hedge-fund-crypto` is the signal layer, Hermes is the
meta-orchestrator, SI-v2 is the evidence-based self-improvement loop, and
Freqtrade is the dry-run execution fleet.

The system operates under a strict dry-run-only policy until explicitly cleared
for live trading by a documented human approval scope.

**Version:** 2.1
**Updated:** 2026-06-24 — root agent instruction alignment with the proven
SI-v2 4-bot loop
**Profile:** orchestrator
**Project:** `/home/hermes/projects/trading`
**Repo:** `github.com/GoLukeEnviro/trading-hub` (private)

---

## Authority model

1. Human approval is required for any live-money, credential, config, strategy,
   risk, threshold, Docker, Cron, Guardian, or destructive operation.
2. RiskGuard and kill-switch behavior override signals and LLM suggestions.
3. ShadowLogger/report evidence is required for safety-relevant decisions.
4. SI-v2 proposals are evidence until a separate approved apply path exists.
5. LLM output is advisory only and never execution authority.

---

## Operational priority order

For current SI-v2 work, the binding priority order is:

1. SI-v2 Loop
2. Historical Evidence
3. Measurement Attribution
4. ShadowProposal Quality
5. Runtime Safety

Do not drift into Docker, Guardian, Cron, generic healthchecks, generic CI, or
infrastructure cleanup unless that work directly blocks the SI-v2 loop or the
user explicitly approves the scope.

---

## Role split

### ai-hedge-fund-crypto — Signal layer

- Signal generation via technical-analysis ensemble and LLM-assisted portfolio
  decisions.
- Exchange data source: Bitget Futures OHLCV.
- Advisory output only; no order placement and no execution authority.
- The parent repo orchestrates and audits the signal output.

### Hermes — Meta-orchestrator

- Runs in the `orchestrator` profile.
- Performs audits, repairs, documentation, escalation, and safe git
  housekeeping.
- Interfaces with Luke through Telegram/Gateway.
- Does not decide trades directly, place orders, enable live trading, or mutate
  runtime without approval.

### SI-v2 — Self-improvement loop

- Active Cycle Runner reads the dry-run fleet and evidence sources.
- Historical Evidence is part of the current loop contract.
- Measurement Attribution ties observations to cycle, bot, and evidence bundle.
- ShadowProposals remain proposal-only until a separate human-approved apply
  path is invoked.
- Runtime Safety preserves dry-run mode and zero mutation for read-only proof
  and docs work.

### Freqtrade — Dry-run execution fleet

- Dry-run trade execution only.
- Strategy-based entry/exit remains in Freqtrade strategy control.
- Signals are conservative filters and evidence inputs; they never force trades.
- The active SI-v2 fleet is four bot identities:
  - `freqtrade-freqforge`
  - `freqtrade-freqforge-canary`
  - `freqtrade-regime-hybrid`
  - `freqai-rebel`

Momentum and MVS are historical/non-current and must not be counted as active
SI-v2 loop members.

### FreqForge Shadow Evaluator — Passive observer

- Observes dry-run activity and evaluates decisions.
- Does not execute, modify, cancel, or override trades.
- Produces append-only evidence.

---

## Dry-run-only policy

Mandatory:

- All active Freqtrade bots remain in dry-run mode.
- No exchange credentials may be added or committed.
- No real orders may be placed.
- No leverage, capital increase, or position-sizing automation may be enabled
  without explicit approval.
- No live trading may be discussed as actionable until backtest,
  walk-forward, shadow-mode evidence, risk analysis, rollback, and human
  approval are documented.

Validation:

- Dry-run state must be verified from current runtime evidence before any
  runtime-affecting decision.
- Internal API credentials must be redacted in reports and never committed.
- A healthy endpoint is not proof that the full SI-v2 loop is safe; inspect the
  loop evidence bundle and state file.

---

## Forbidden actions without explicit approval

- Setting `dry_run=false` or enabling live trading.
- Adding, copying, printing, persisting, or exposing exchange credentials,
  wallet data, API keys, tokens, or secrets.
- Placing real orders or forcing Freqtrade entries.
- Changing Freqtrade configs, strategies, pairlists, signal thresholds,
  RiskGuard behavior, or capital/exposure settings.
- Restarting, recreating, rebuilding, pruning, or deleting Docker containers,
  networks, images, or volumes.
- Migrating, deleting, or changing Cron/Guardian jobs.
- Deleting historical data or runtime evidence.
- Broad recursive permission changes.

---

## State machine

### Live trading state

```text
LIVE_FORBIDDEN → LIVE_CANDIDATE → LIVE_APPROVED → LIVE_ACTIVE
```

Default is `LIVE_FORBIDDEN`. Unknown state means `LIVE_FORBIDDEN`.

### Operational pipeline

```text
INIT → PREFLIGHT → DATA_READY → SIGNAL_READY → RISK_FILTERED → SHADOW_LOGGED → FLEET_SYNCED → MONITORING
```

### Error states

- `DATA_STALE` — required input is stale.
- `SIGNAL_INVALID` — schema or semantic validation failed.
- `RISK_BLOCKED` — RiskGuard blocks entry or downgrades to watch-only.
- `FLEET_UNHEALTHY` — a required active bot is unreachable or not running.
- `CRON_DRIFT` — scheduled loop evidence is stale or missing.
- `TELEMETRY_STALE` — telemetry evidence is stale or incomplete.
- `HUMAN_ESCALATION_REQUIRED` — live-money, credential, destructive, or L3 risk
  is present.

---

## Gate system

### Gate 0 — Reality lock

- Verify repository, branch, runtime snapshot, and evidence paths.
- Do not assume old root docs are runtime truth.

### Gate 1 — Dry-run safety

- Active bots remain dry-run.
- No exchange credentials are introduced.
- Runtime credentials are redacted and never committed.

### Gate 2 — Signal validity

- Signal output exists, is fresh enough for the task, matches schema, and maps
  only to known pairs/actions.
- Invalid or weak signals degrade or block; they do not force trades.

### Gate 3 — RiskGuard

- RiskGuard can downgrade or block decisions.
- HOLD/WATCH/TREND_HOLD style outputs are watch-only and never force entries.

### Gate 4 — Shadow evidence

- ShadowLogger/report evidence records decisions and safety checks.
- If evidence logging is unavailable, pause decision/write actions.

### Gate 5 — SI-v2 loop evidence

- Active Cycle evidence contains all active bot identities.
- Historical Evidence is additive and does not replace telemetry evidence.
- Measurement Attribution remains tied to source artifacts.
- ShadowProposals remain proposal-only unless an approved apply path is invoked.

### Gate 6 — Runtime mutation gate

- Runtime mutation requires explicit approval, proof, rollback, and documented
  scope.
- Read-only proof and docs work must leave mutation counters at zero.

---

## Monitoring colors

### GREEN

- Required SI-v2 evidence is present and internally consistent.
- Active bot identities match the current canonical state.
- RiskGuard and ShadowLogger contracts are satisfied.
- Dry-run posture is preserved.
- No unapproved mutation path is present.

### YELLOW

- Evidence is safe but partial.
- A proof is current enough for diagnosis but not for promotion.
- A follow-up is needed before any runtime decision.

### ORANGE

- Runtime or documentation drift could mislead operators.
- A required source is stale, degraded, or ambiguous.
- Continue read-only inspection only; do not mutate.

### RED

- Live-money risk, credentials exposure, real-order risk, dry-run violation,
  destructive operation, missing safety authority, or unexplained mutation risk
  is present.

---

## Human escalation matrix

Immediate escalation is required for:

- Live-money risk.
- Credentials, API keys, wallet data, tokens, or secrets.
- Any path toward live orders.
- Freqtrade config, strategy, signal threshold, pairlist, RiskGuard, or capital
  changes.
- Docker restart/recreate/rebuild/prune/volume operations.
- Cron or Guardian mutation.
- Data deletion or destructive filesystem changes.
- RiskGuard/ShadowLogger outage during safety-relevant decisions.
- Failed or ambiguous proof for a runtime-affecting change.

No escalation is normally needed for:

- Read-only audits.
- Docs/report generation.
- JSON/schema validation.
- Non-destructive git commits and PRs that contain no secrets or runtime state.

---

## Definition of done

Work is complete only when:

1. The requested scope was addressed and no anti-scope work was added.
2. Safety rules were checked.
3. Evidence was captured with paths and validation output.
4. No hidden live-money path was introduced.
5. No secrets were exposed.
6. No destructive action was performed without approval.
7. Relevant state/report/context docs were updated when required.
8. The next safe step is clear.

---

## Changelog

- **2.1 — 2026-06-24:** Align charter with the proven SI-v2 4-bot loop; make
  SI-v2 loop priority and no-infra-without-loop-blocker scope rule explicit;
  remove current-state volatile metrics from the charter.
- **2.0 — 2026-05-12 (historical/non-current):** Full rewrite for the
  then-current historical 6-bot fleet and earlier orchestration assumptions.
  The historical 6-bot reference is not the current active SI-v2 fleet.
- **1.0 — 2026-05-07:** Initial charter.
