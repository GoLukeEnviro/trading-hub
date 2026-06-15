# trading-hub Roadmap v2 – Blocker-First Runtime Ownership

> **Canonical forward-looking roadmap.** Replaces
> `docs/roadmap/implementation-roadmap.md` as the source of truth for
> implementation phases, current state, and next priorities. The older
> roadmap is preserved as historical context and marked superseded.
>
> **Grounded at:** commit `266a930` (PR #261 — walk-forward cost model, after
> PR #262 — telemetry history store + enforcement gate) on `main`, 2026-06-16.
>
> **Companion docs:**
> * `docs/state/current-operational-state.md` — current validated snapshot
> * `docs/state/canonical-trading-status.md` — live fleet snapshot (regenerated)
> * `docs/backtesting/walk-forward-cost-model.md` — cost model foundation (PR #261)
> * `self_improvement_v2/README.md` — includes telemetry history store (PR #262)

---

## Executive Summary

* **#44 is closed.** It is no longer the active blocker.
* **#200 and #201 are closed.** Docker ownership was resolved; the
  telemetry history enforcement gate (PR #262) provides deterministic
  coverage. #201 (P2 non-root hardening) was closed without action.
* **#176 is closed at Stage A.** Stage B (dedicated on-host Unix user) is
  future hardening, not a current blocker.
* **PR #262 is merged** — telemetry history store, wiring, and history
  enforcement gate (`BLOCKED_INSUFFICIENT_HISTORY`).
* **PR #261 is merged** — walk-forward cost model with deterministic fees,
  slippage, funding, aggregate net metrics, and walk-forward evaluator.
* **SI v2 scheduled observation loop is operational** — 27+ cycles, 4/4 bots,
  `fleet_verdict=GREEN`, controller `PAUSED / L3_REPOSITORY_ONLY`, 0 mutations.
* **Rainbow scoring is gated on producer freshness, not on cycle count.**
  0 / 10 scoring-eligible cycles today because the read_only source's
  `signals.db` has stale timestamps (≥ 19h). Need a *producer* (not the
  DB-backed stub) to emit fresh signals inside the 15-min freshness window.
* **Live trading remains forbidden** at every phase.
* **Apply/Scoring auto-execution is explicitly out of scope** for this
  roadmap. Human approval gates stay.
* **Controller stays `PAUSED / L3_REPOSITORY_ONLY`** until an explicit
  future gate.

---

## Aktueller Stand (Reconciled)

| Item | Old assumption | Reconciled truth | Source |
|------|----------------|------------------|--------|
| #44 status | "🔴 BLOCKED — requires Docker/runtime access" | **CLOSED** 2026-06-12 (parent) | `gh issue view 44` |
| #176 status | "Open, controller isolation needed" | **CLOSED** Stage A (`status:stage-a-complete`); Stage B (dedicated Unix user on host) is future work | `gh issue view 176`; `getent passwd si-v2-controller` returns nothing on this host |
| #200 status | "Not yet tracked" | **CLOSED** 2026-06-16. Docker ownership resolved. Telemetry history gate (PR #262) provides enforcement. | `gh issue view 200` |
| #201 status | "Security concern, blocking" | **CLOSED** 2026-06-16. P2 non-root hardening closed without action. | `gh issue view 201` |
| #60 status | "OPEN" (per stale doc) | **CLOSED** 2026-06-11, merged at `0557b70` (PR #169) | `gh issue view 60` |
| #46 status | "OPEN" (per stale doc) | **CLOSED** 2026-06-11 | `gh issue view 46` |
| SI v2 loop | "Not started" / "fixture only" | **Operational**: 27 cycles, `fleet_verdict=GREEN`, 0 mutations | `self_improvement_v2/reports/phase2/measurement/measurement_ledger.jsonl` |
| Rainbow read_only | "PR #212 merged, but plumbing only" | **End-to-end read_only path** with env-override bridge + DB-backed stub + freshness guard | PRs #212, #213, #214, #215 |
| Scoring gate | "0 / 10 — wait for cycles" | "0 / 10 — wait for **producer freshness**" | `_is_rainbow_cycle_scoring_eligible` in `active_cycle_runner.py` |
| Live trading | "Forbidden" | **Forbidden** (no change) | `AGENTS.md`, `SOUL.md`, scheduler config |

---

## Stale Documentation Findings

The reconciliation audit found three primary stale docs and three minor
historical-only items. The fix for each is owned by this PR or by follow-up
ISSUE-B (#200 audit-only plan).

| File | Stale claim | Current truth | Fix in this PR |
|------|-------------|---------------|----------------|
| `docs/state/current-operational-state.md` | Pinned to `0222adb`. #200/#201 listed as open. Phase 2.0 IN PROGRESS — owned by #200. | HEAD is `266a930`. #200/#201 are **CLOSED**. Phase 2.0 is **COMPLETE**. PR #261 (walk-forward) and PR #262 (telemetry history) are merged. | **Updated in this reconciliation.** |
| `docs/roadmap/implementation-roadmap.md` | "Phase 2 — Runtime Blockers — ⬜ Not started — #43/#44". #44 listed as "🔴 BLOCKED — requires Docker/runtime access". Phase 3 Rainbow Signal Integration "Not started". | Rainbow PR #212–#215 all merged. Phase 2 is no longer "not started" — it is owned by #200. | **Header `SUPERSEDED` added in this PR.** This roadmap-v2 replaces it. |
| `docs/state/si-v2-capability-matrix.md` | "#55–#60 OPEN". "Issue #55 is OPEN". "Issue #60 OPEN". "Regime Detector ⬜ Not started". "Performance Attribution Engine ⬜ Not started". Grounded at `fdac27c`. | All of #55–#60 are **CLOSED** (since 2026-06-11). Capability matrix not refreshed since 2026-06-11. Rainbow now has `read_only` source in addition to `fixture`. Measurement Ledger is producing 108 bot points across 27 cycles. | **Updated in this PR.** |
| `docs/reports/phase0-closure-matrix-20260611.md` | "#44 … 🔴 OPEN — BLOCKED". "4 of 6 child issues closed ✅ — 2 remaining". | #44 closed 2026-06-12, #46 closed 2026-06-11. All 6 child issues now closed. | **Header `SUPERSEDED` added in this PR.** Archive (move to `docs/reports/archive/`) deferred to a separate task. |
| `docs/context/2026-06-14-si-v2-rainbow-read-only-prereq-blocked.md` | Headline: "PRE-REQUISITE BLOCKED" | **Superseded by PR #215**, which added the missing env-override bridge AND a DB-backed stub AND a freshness guard. The report is *correct* as a snapshot of the 2026-06-14 blocker; it is *stale* as current state. | **Header `SUPERSEDED` added in this PR.** |
| `docs/state/phase-1-intelligence-epic.md` | Header: "Status: 🟡 Active — #55 completed … #56 in development". | All of #55–#61 are closed. | Out of scope for this PR (history-only; pinned to its own merge). Pointer added to current docs. |
| `AGENTS.md` | — | **Current**. | No change. |
| `docs/state/canonical-trading-status.md` | — | **Current** (regenerated by ledger-watchdog). | No change. |

---

## Current Runtime Truth

* **20 containers UP.** 13 in the `trading` project + 1 in `guardian` + 1 in
  `rizzcoach` + **7 unmanaged** (`btc5m-bot`, `claude-worker`, `green-mem0`,
  `green-ollama`, `green-qdrant`, `trading-hermes-watchdog-1`,
  `weatherhermes`). This is the exact failure mode #200 exists to fix.
* **SI v2 active cycle runner** is the authoritative scheduled loop
  (`64866012641a`, `17 */6 * * *`, log-only). All cycles are
  `runner_exit_code=0`, `fleet_verdict=GREEN`. Mutations:
  `runtime=0 / config=0 / live_trading=0 / docker=0 / strategy=0`.
* **`Rainbow read_only`** returns 3 signals per cycle (BTC, ETH, SOL), all
  `SUCCESS`, but `fresh=False` because the source SQLite carries a
  2026-06-14T01:04 timestamp. The freshness guard correctly excludes them
  from scoring eligibility.
* **`canonical-trading-status.md`** is the current live fleet snapshot
  (regenerated by `ledger-watchdog`). Verdict: `WARNING` — runtime GREEN,
  but `reporting_health_score=73` and `data_quality_score=84` are below
  threshold because of stale `LIVE_RISK` / `drawdown_state`. Phased fix
  in Phase 2.2.

---

## Phase 2.0 – Runtime Foundation & Docker Ownership ✅ COMPLETE

**Status:** ✅ **COMPLETE** — #200 is closed, telemetry history enforcement gate
(PR #262) provides deterministic coverage.

**Previous goal:** Resolve #200 end-to-end without runtime disruption. Establish a
single canonical Compose project + file authority map. Decide whether
Stage B controller isolation is needed now or later.

### Completed Tasks

All T2.0.x tasks are now completed. Key deliverables:

* **T2.0.1–T2.0.5** — Container ownership map, Compose authority, file authority
  matrix, wrapper ownership review, and ownership decisions.
* **T2.0.6** — `current-operational-state.md` reconciliation was done.
* **T2.0.7** — Stage B isolation deferred until Phase 2.1 scoring gate.
* **T2.0.8** — Scheduler wrapper ownership confirmed.
* **PR #262** — Telemetry history store, wiring, and enforcement gate merged,
  providing the history gating that Phase 2.0 required.

### Legacy Tasks (archived — listed for historical reference)

1. **T2.0.1 — Container ownership map** (read-only report).
   * For each of the 20 running containers, capture: compose project label
     (if any), service label, image, source build authority (in-tree
     Dockerfile / external image / scratch), and the wrapper/script that
     starts it.
   * For each **unmanaged** container (`btc5m-bot`, `claude-worker`,
     `green-mem0`, `green-ollama`, `green-qdrant`,
     `trading-hermes-watchdog-1`, `weatherhermes`), record the **actual**
     source of start-up (compose file path / cron wrapper / manual
     `docker run` / external supervisor).
2. **T2.0.2 — Compose authority map** (read-only).
   * Identify the canonical `docker-compose*.yml` for each of the projects
     `trading`, `guardian`, `rizzcoach`.
   * Identify the canonical authority for each unmanaged container:
     * `green-mem0` / `green-ollama` / `green-qdrant` — likely
       `orchestrator/mem0/docker-compose.yml` or similar. **Verify and
       confirm.**
     * `trading-hermes-watchdog-1` — likely a sidecar defined in
       `freqtrade/docker-compose.fleet.yml` or a separate compose. **Verify.**
     * `btc5m-bot`, `claude-worker`, `weatherhermes` — external/handcrafted.
       Document as-is; do not adopt unless explicitly approved.
3. **T2.0.3 — File authority matrix.**
   * For every wrapper script under `/opt/data/scripts/`, identify whether
     it is canonical (a symlink to `/home/hermes/projects/trading/...`),
     legacy backup (`.bak*`), or local-only. Specifically:
     * `si-v2-active-cycle-runner.sh` (canonical, owned by repo)
     * `si-v2-active-cycle-runner.sh.bak*` (legacy, retain or archive)
     * `orchestrator/scripts/*` symlinks vs. standalone
   * For every in-tree Dockerfile that produces a running image
     (`Dockerfile.hermes1337`, `Dockerfile.hermes1337-freqai-rebel`,
     `shadowlock/Dockerfile.hermes1337`, `ai-hedge-fund-crypto` image),
     record the canonical source path and the image tag policy.
4. **T2.0.4 — Wrapper/script ownership review.**
   * Confirm `/opt/data/scripts/si-v2-active-cycle-runner.sh`
     (mode 0700, owner `hermes:hermes`) is the canonical runtime wrapper,
     and that `.bak*` siblings are explicitly marked as such. No change
     in this task; this is a read-only confirmation.
5. **T2.0.5 — No-surprise ownership decision.**
   * Decide for each unmanaged container:
     * (a) **Adopt** — create or repoint a Compose file so the container
       carries a `com.docker.compose.project` label and is owned by a
       tracked file.
     * (b) **Document as external** — keep the container running as-is,
       and add it to a `runtime/external-containers.md` inventory with
       its start-up mechanism, owner, and rollback.
   * The decision must come with explicit human approval for any **adopt**
     action that involves creating or editing a Compose file, recreating a
     container, or restarting a service.
6. **T2.0.6 — `current-operational-state.md` reconciliation.**
   * Update pin to `9ceeedd`; remove #44/#46 from "open" lists; mark
     Phase 2.0 as IN PROGRESS; link to `canonical-trading-status.md` as
     the live fleet snapshot. *(This is done in this PR.)*
7. **T2.0.7 — Stage B controller-isolation decision.**
   * Decide whether to file a follow-up issue for Stage B (dedicated
     `si-v2-controller` Unix user + dedicated `HERMES_HOME` + scoped
     GitHub/provider creds + hardened service unit). Default: **defer**
     until Phase 2.1 reaches "scoring-eligible history ≥ 10/10".
8. **T2.0.8 — Scheduler wrapper ownership.**
   * The Hermes scheduler job `64866012641a` invokes
     `/opt/data/scripts/si-v2-active-cycle-runner.sh`. Confirm:
     * wrapper is owned by repo
     * scheduler job is in the `orchestrator` profile (not `default`)
     * no other scheduler is pointing at an older wrapper
   * No mutation. Read-only confirmation.

### Acceptance Criteria

* Container ownership map is published in
  `docs/reports/phase2-0-runtime-ownership-map-YYYYMMDD.md` (file
  write requires separate approval).
* Each unmanaged container is classified **adopt** or **external**.
* `current-operational-state.md` no longer lists #44 or #46 as open.
  *(Done in this PR.)*
* No container restarted, no Compose file edited, no wrapper mutated by
  this phase.
* `runner_exit_code=0` and `fleet_verdict=GREEN` continue across the
  full duration of Phase 2.0.

### Risks

* **R1 — Adopt path causes container restart.** Mitigation: adopt
  actions are L3 and require explicit per-container approval with
  rollback.
* **R2 — External container disappears.** Mitigation: external
  inventory records start-up command and rollback path.
* **R3 — Wrapper drift.** Mitigation: `.bak*` siblings are explicitly
  recorded; canonical wrapper checksummed and compared at task start.

### Success Metrics

* 0 containers with ambiguous authority.
* 0 stale "BLOCKED — requires Docker/runtime access" references in
  canonical docs.
* Scheduler job `64866012641a` continues to deliver 4/4 ping,
  0 mutations.

---

## Phase 2.1 – SI v2 Autonomous Dry-Run Operation 🟠 CURRENT BLOCKER

**Owner:** Hermes
**Goal:** Reach Rainbow scoring eligibility = 10/10 with a **real
producer**, without breaking dry-run-only.

**Dependencies met:** ✅ PR #262 (telemetry history & enforcement gate),
✅ PR #261 (walk-forward cost model foundation).

### Tasks

1. **T2.1.1 — Producer freshness decision.** Decide whether scoring is
   fed by:
   * (a) **ai4trade-bot producer** — deploy the existing ai4trade-bot as
     a tracked service exposing `GET /signals/latest` (Rainbow §5
     envelope). Today there is a `signals.db` with 3 signals dated
     2026-06-14T01:04, but no producer, no container, no listener.
   * (b) **DB-backed stub with live write** — extend the in-tree stub
     to be **written** to (not just read) by a low-frequency cron that
     updates the SQLite's signal timestamps inside the 15-min window.
     This is a *fixture* with synthetic freshness, explicitly labelled,
     never scoring-eligible for real evidence.
   * (c) **Other in-tree provider** — only if a candidate appears.
   * Default: **(a) ai4trade producer** because scoring must be backed
     by real upstream signal metadata to be defensible.
2. **T2.1.2 — Producer deployment plan.** L3 PR plan covering:
   * See `docs/plans/producer-freshness-fix-deployment.md` for the full
     implementation plan with preflight, credential configuration, compose
     profile, SI v2 reconfiguration, validation commands, rollback steps,
     and approval gates (token: `APPROVE_RAINBOW_PRODUCER_DEPLOY`).
   * container definition under a new Compose project
     (e.g. `ai4trade-producer`)
   * volume ownership for `signals.db`
   * healthcheck (HTTP `/healthz` + signals.db freshness check)
   * restart policy
   * explicit human approval before apply
3. **T2.1.3 — Human approval gate.** Each scoring-eligible cycle is
   flagged in the ledger. Auto-promotion to scoring is **forbidden**
   without an explicit human approval event in `shadow_decisions.jsonl`.
4. **T2.1.4 — ShadowProposal quality.** Continue PR #209 multi-signal
   fusion. Track the no-proposal count per cycle (currently 4/cycle).
   Reduce no-proposals only through additional evidence, not by
   loosening thresholds.
5. **T2.1.5 — Measurement Ledger and attribution.** Already running.
   Continue weekly review (PR #194, issue #66).

### Acceptance Criteria

* 10 consecutive cycles with `rainbow_status=SUCCESS`,
  `rainbow_source ∈ {read_only, live}`, `rainbow_fresh=True`,
  `freshness_seconds ≤ 900`.
* Ledger records include `rainbow_fresh` for every fleet entry.
* `proposal_records` count is non-zero when scoring-eligible evidence
  is present.
* Live trading flag remains `False` on every cycle.

### Risks

* **R1 — Producer emits wrong envelope.** Mitigation: the existing
  validator (`rainbow/validator.py`, fixture-tested) is the gate. If
  the producer emits a non-conforming envelope, the cycle degrades to
  `WARNING`, not crash.
* **R2 — Scoring-eligibility is gamed by timestamp manipulation.**
  Mitigation: `freshness_max_seconds=900`, central helper, plus
  provenance via `source_artifact` → cycle_id. Any change requires L3
  approval.

### Success Metrics

* scoring-eligible cycles / 10
* weekly attribution report (issue #66 cadence) shows non-zero
  proposal-records
* 0 false-positive scoring promotions

---

## Phase 2.2 – Observability, Hardening & Self-Healing

**Owner:** Hermes
**Goal:** Catch up on the long-deferred hardening items, in order, **only
after Phase 2.0 and 2.1 are stable**.

### Tasks

1. **T2.2.1 — Reporting health lift.** `reporting_health_score=73` is
   driven by stale `LIVE_RISK` / `drawdown_state`. Either retire them
   as canonical (mark `historical`) or wire a fresh producer. Default:
   retire as canonical, point operators to `canonical-trading-status.md`.
2. **T2.2.2 — Data quality lift.** `data_quality_score=84` is driven by
   missing `freqai-rebel` state file. Either make Rebel
   `docker-exec-only` explicit (the doc already says this) and remove
   the "VISIBILITY_GAP" verdict, or fix the docker exec probe.
3. **T2.2.3 — Shadowlock maintenance.** Issue #60 is closed; verify
   the daily maintenance is actually running and within the approved
   approval-gate (no destructive vacuum).
4. **T2.2.4 — Branch/worktree hygiene.** #46 is closed. Verify that
   feature branches referenced in the recent PR line
   (`feat/si-v2-rainbow-read-only-runtime-source-v1`,
   `feat/si-v2-rainbow-read-only-client-v1`,
   `feat/si-v2-issue-66-weekly-review-cadence`,
   `feat/si-v2-issue-26-activation-ceremony-v2`,
   `feat/si-v2-issue-175-controller-baseline-reconciliation`,
   `feat/si-v2-issue-182-phase2-proposal-gate`,
   `feat/si-v2-issue-65-validation-gate-matrix`,
   `test/si-v2-issue-181-phase2-e2e-integration`,
   `fix/si-v2-issue-185-episode-contract-hardening`,
   `feat/si-v2-issue-81-shadowlock-external-signal-audit-events`,
   `feat/si-v2-issue-84-85-80-rainbow-report-status-client`,
   `feat/si-v2-issue-82-rainbow-contract-snapshot`,
   `feat/si-v2-issue-79-rainbow-envelope-validator`) are either merged
   or explicitly archived. `git-archive-candidates.md` may be needed.
5. **T2.2.5 — Non-root container execution (#201).** P2 hardening.
   Evaluate feasibility for `hermes-green` and `green-qdrant`. Run a
   dedicated worktree, rebuild with non-root user, validate against
   fixtures, write a `docs/reports/non-root-feasibility-YYYYMMDD.md`.
   **No production change without separate approval.**
6. **T2.2.6 — Stage B controller isolation.** File a follow-up issue
   only after Phase 2.1 scoring gate is met. Out of scope for the
   current loop.

### Acceptance Criteria

* `overall_operational_score ≥ 90` in `canonical-trading-status.md`.
* No YELLOW/RED row in the "Active Fleet" table.
* Worktree inventory clean (no branch older than 30 days un-archived).

### Success Metrics

* `reporting_health_score ≥ 85`
* `data_quality_score ≥ 90`
* 0 zombie worktrees

---

## Phase 3 – Signal Weighting & Higher Autonomy

**Owner:** SI v2 Controller + Hermes + Human
**Goal:** Move from observation to **defensible** weighting, still
dry-run. **Hard constraint:** No apply, no live trading, no
auto-promotion.

### Tasks

1. **T3.1 — Scoring model contract.** Spec + tests. Rainbow evidence
   weighting is allowed only after the history gate (10/10) is met and
   the attribution report (issue #66 cadence) shows non-zero
   proposal-records.
2. **T3.2 — Weight proposal engine.** Issue #63 is already implemented
   (commit `2614787`). Re-verify against current Rainbow data shape.
3. **T3.3 — Validation gate matrix.** Issue #65 is implemented.
   Re-verify gates against scoring-eligible evidence.
4. **T3.4 — Live-readiness package.** Only after a long evidence run
   (≥ 4 weeks of scoring-eligible cycles, ≥ 2 weekly attribution
   reports, controller remains `PAUSED`). L3 approval + L4 risk review
   required.

### Acceptance Criteria

* Weight proposals are produced and reviewed weekly.
* Live-readiness package is filed as a separate PR, not auto-merged.

### Success Metrics

* 4 consecutive weekly attribution reports with non-zero proposal
  records.
* 0 false-positive weight proposals (human-review pass-rate ≥ 0.95).

---

## Gesamter Zeitplan & Meilensteine

| Milestone | Trigger | Exit criterion |
|-----------|---------|----------------|
| M2.0.1 | Roadmap v2 merged | Roadmap v2 is the canonical forward-looking doc |
| M2.0.2 | T2.0.1–T2.0.5 complete | Container ownership map published; all 7 unmanaged containers classified |
| M2.0.3 | T2.0.6 done | `current-operational-state.md` reconciled |
| M2.0.4 | PR #262 merged | Telemetry history store + enforcement gate operational |
| M2.0.5 | PR #261 merged | Walk-forward cost model foundation in tree |
| M2.1.1 | Producer decision (T2.1.1) | ai4trade-bot producer or equivalent committed to L3 PR plan |
| M2.1.2 | First scoring-eligible cycle | Ledger shows `rainbow_fresh=True` ≥ 1 |
| M2.1.3 | History gate met | 10/10 scoring-eligible cycles |
| M2.2.1 | Reporting health lift | `reporting_health_score ≥ 85` |
| M3.0 | 4 weeks of weekly attribution reports | Live-readiness package filed (not merged) |

---

## Risiken & Governance

* **Live trading stays forbidden** at every phase.
* **Apply/Scoring auto-execution stays out of scope** until M2.1.3.
* **Controller stays `PAUSED / L3_REPOSITORY_ONLY`** until explicit future gate.
* **No destructive Docker ops** without per-action approval.
* **No secrets in artifacts** — `secrets_found=False` is a hard gate.
* **No `chown -R` / `chmod -R`** without per-action approval.
* **No force-push / history rewrite** in any of these phases.
* **No `git add .`** in any of these phases.

---

## Issue Plan

| Issue | Title | Type | Effort | Owner |
|-------|-------|------|--------|-------|
| ISSUE-C | SI v2 scheduler status and Rainbow history monitor | observability | S | Hermes |
| ISSUE-D | Rainbow producer freshness / ai4trade producer decision | infra (L3 plan) | L | Hermes + Human |
| ISSUE-E | Future Rainbow evidence weighting (gated 10/10) | si-v2 (L3) | M | SI v2 Controller + Human |
| ISSUE-F | Optional #201 hardening plan | security (L2 plan) | M | Hermes |

**Note:** ISSUE-A (doc reconciliation) is done in this PR. ISSUE-B (#200) is
obsolete — #200 is closed. No issues are opened without separate approval.

---

## Nächste Sofortmaßnahmen

1. **State Reconciliation is done in this PR** — docs reflect merged PRs #261/#262.
2. **Phase 2.0 is complete.** #200 and #201 are closed.
3. **Next active blocker: producer freshness and scoring eligibility.**
   Start the Producer Freshness Audit (Phase 2 of the prioritised plan) to
   identify why the Rainbow read_only producer remains scoring-ineligible.
4. **Defer** ISSUE-F (#201 non-root) to Phase 2.2.
5. **No Docker, no scoring, no apply, no live trading.**
