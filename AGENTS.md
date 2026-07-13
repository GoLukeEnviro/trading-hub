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
- ShadowProposals may be applied automatically in **AUTONOMOUS_DRY_RUN** mode
  when all policy gates pass. Dry-run mutation is not human-gated by default.
  It is policy-gated, canary-first, allowlist-based, audit-logged,
  snapshot-backed, rollback-capable, and measurement-bound.
- Approval eligibility is not approval. A proposal that passes policy gates
  is eligible for autonomous dry-run apply, not for live trading.
- Mutation counters must remain zero for read-only proof and docs work.
- Profitability or scoring evidence is not live-trading authorization.

Decommissioned or non-deployed bots such as Momentum and MVS are historical
context only. Do not count them as active SI-v2 loop members.

## Source-of-truth order

When resolving conflicts or stale claims, use this hierarchy:

1. Freshly verified Git, GitHub, CI and runtime evidence
2. Existing active roadmap PR and its linked issue
3. Latest explicitly superseding section in `docs/state/current-operational-state.md`
4. Issue #423 for live gates and the long-term live target
5. Active ADRs, `AGENTS.md`, and `SOUL.md`
6. `IDEA.md` exclusively as non-authoritative workspace orientation; its absence is not an error

## Execution classes

- **A0 — Read-only:** inspection, evidence collection, analysis and reports.
  No mutation of any kind.
- **A1 — Repository-only:** branch, code/docs/tests, commit, push, PR, CI
  repair, issue/state reconciliation after merge. Exactly one active roadmap
  PR at a time.
- **A2 — Approved dry-run runtime:** only with explicit issue scope, approval
  marker, snapshot, canary, allowlist, rollback, audit and bounded measurement.
- **A3 — Live capital:** never inferred from root access or A0–A2. Requires
  externally signed, time-limited, scope-specific approval. Always stop if
  any A3 prerequisite is missing.

**Always prohibited without explicit A3 approval:**

- `dry_run=false`
- Live orders
- Live exchange credentials
- Capital or risk limit increases
- RiskGuard weakening
- Kill-switch bypass or deactivation

## Repository writer contract

Every roadmap tick (cron or manual) and every autonomous agent session that
writes to the trading-hub repository MUST follow the enforced single-writer
contract defined in `orchestrator/scripts/repo_writer.py`.

**Global lock.** A single non-blocking `fcntl.flock` on
`/opt/data/state/hermes-repo-writer.lock` serialises all writers. The lock is
process-scoped and kernel-released on exit (incl. SIGKILL). The on-disk JSON
carries holder metadata (PID, host, worktree path, branch, session ID,
started-at) for inspection via `RepoWriterLock().read_holder()`. Failed
acquisition raises `RepoWriterError("BLOCKED_BY_ACTIVE_REPO_WRITER")`;

**Isolated worktrees.** Every writer MUST create a fresh `git worktree add`
from a pinned `origin/main` SHA (never a moving branch) under
`/opt/data/projects/trading-hub-worktrees/`. The shared canonical checkout
(`/workspace/projects/trading-hub`) is read-only — never switch branches,
commit, or reset there. The new worktree's status must be clean
(`git status --porcelain` empty, `HEAD` on the requested branch) before
creating any commits. Remove the worktree after merge or formal abort.

**Clean-worktree verification.** Both the shared checkout and the new
worktree must be clean before branch creation and before commit.

**Stop condition.** `BLOCKED_BY_ACTIVE_REPO_WRITER` is a hard stop — do not
override without explicit operator approval.

**No unrelated debug work.** No session outside the roadmap loop may write
to the trading-hub repository. Cron ticks are the exclusive repository
writer; manual operator sessions may hold the lock but must follow the same
contract.

See `commands/trading-hub-roadmap-tick.md` for the per-tick algorithm and
`tests/test_repo_writer.py` for the enforcement test suite (31 tests).

## Autonomous roadmap session algorithm

Every autonomous agent session acting on the roadmap MUST:

1. Read `AGENTS.md`, `SOUL.md`, `docs/state/current-operational-state.md`,
   and issue #423.
2. Inspect open PRs and linked active issues.
3. Finish or formally block the existing roadmap PR before selecting another
   task.
4. Select the first truly unblocked task.
5. Execute one GOAL, one branch, one PR and one report.
6. Reconcile issue and state after merge.
7. Stop at every missing A2 or A3 approval.

## System architecture boundaries

### Signal layer — `ai-hedge-fund-crypto`

- Crypto-native signal generator using Bitget Futures OHLCV.
- Technical-analysis ensemble plus LLM-assisted portfolio decisions.
- Output is advisory only and must not force trades.
- The parent repo orchestrates and audits; it does not turn signals into direct
  execution authority.

### Hermes — Meta-Orchestrator

- Runs in the `trading-hub-orchestrator` profile for this project.
- Responsibilities: audits, repairs, cron maintenance when approved,
  documentation, escalation, and safe git housekeeping.
- Boundaries: does not decide trades directly, place orders, enable live
  trading, modify Freqtrade configs without approval, or restart containers
  without approval.
- Working directories:
  - Primary repository (read/write): `/workspace/projects/trading-hub`
    (`/opt/data/projects/trading-hub` on HermesTrader host)
  - Secondary repository (read/write, explicit cross-repo scope only):
    `/workspace/projects/ai4trade-bot`
  - `/home/hermes/projects/trading` is historical (agent0) and must NOT be
    used as canonical HermesTrader path.
- **Docker/host access model (historical → current):** Hermes previously
  operated under the SEC-1 "no `docker.sock`" model: a read-only Docker proxy
  (D1), a fixed-command allowlisted host runner (D2), and an audited operator
  bridge (D3) — see `hermestrader-d1-readonly-docker-visibility.md`,
  `hermestrader-d2-impl.md`, and the D3 bridge series in memory for the
  implementation history. That narrow-slice model is superseded as of the
  **Root-Runtime-Authority decision (R0)** — see
  [`docs/decisions/ADR-2026-07-11-hermes-root-runtime-authority.md`](docs/decisions/ADR-2026-07-11-hermes-root-runtime-authority.md).
  The dedicated, UID-separated `hermes-root-executor.service`
  provides host and Docker runtime authority through a local Unix socket
  with peer-credential authentication. Runtime availability and current
  reachability from Hermes must be verified against
  [`docs/state/current-operational-state.md`](docs/state/current-operational-state.md)
  before use — deployment state and reachability can change independently
  of this document. D1/D2/D3 remain documented and may keep running as a
  fallback path. Live-capital trading authority remains separate and
  externally signature-gated regardless of root runtime authority — see the
  ADR's External Live Authority Boundary section.

### VPS Operator Console — human CLI access (non-trading)

- A dedicated `operator` system user exists on HermesTrader for human VPS-wide
  work (Claude Code CLI, OpenAI Codex CLI) via OAuth login and `tmux` sessions.
- `operator` is separate from `deploy` (repo/deployment) and `hermes` (agent
  container). It has no `docker` group access and no `sudo` group membership;
  the only permitted `sudo` action is a logged breakglass wrapper
  (`operator-breakglass-root`) for occasional full-root sessions.
- This is host-level tooling for human maintenance, separate from Hermes's own
  runtime authority. Hermes's own access model is defined by the Root-Runtime-
  Authority decision (see the R0 governance ADR,
  [`docs/decisions/ADR-2026-07-11-hermes-root-runtime-authority.md`](docs/decisions/ADR-2026-07-11-hermes-root-runtime-authority.md)),
  not by this operator user -- this change does not itself alter it.
- Full detail: `docs/context/hermestrader-operator-console-20260710.md`.

### SI-v2 — Self-Improvement Loop

- The SI-v2 controlled apply chain is now fully implemented on `main`.
- The first canary apply (`max_open_trades 3→2`) is **runtime-proven**
  with `RuntimeEffectProof=GREEN`.
- The controller operates in **AUTONOMOUS_DRY_RUN** mode target.
- The full controlled apply chain:
  `execute_apply()` → `plan_canary_restart_with_overlay()` →
  `check_restart_gate()` → `run_canary_restart_with_overlay()` →
  `RuntimeEffectProof` → `Measurement Decision Engine`
- The rollback path is rehearsed but **not executed**.
- The candidate pipeline exists with `execute=False` default.
- **Autonomous dry-run apply** is the target: policy-gated, canary-first,
  allowlist-based, audit-logged, snapshot-backed, rollback-capable,
  measurement-bound. Human approval is not required per dry-run iteration.
- Human approval is required for mode transitions (e.g. live-capital activation)
  and emergency override, not for every qualified dry-run candidate.
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

### Primo and Bridge endpoints (historical)

> **Historical note:** Primo and Bridge are decommissioned (Phase 44-45).
> The SI-v2 autonomous dry-run loop (ADR-2026-07-01) replaces the Primo/Bridge
> signal pipeline. `primo_signal.py` remains in `freqtrade/shared/` as a legacy
> signal filter and kill-switch integration boundary.

- Primo and Bridge endpoints may have required API-key headers depending on
  runtime environment (historical).
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
