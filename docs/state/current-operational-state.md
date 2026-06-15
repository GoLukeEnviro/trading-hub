# Trading Hub — Current Operational State

> **Canonical current-state snapshot** — validated against merged main at
> commit `4dd4d5c` (PR #267 — Rainbow producer hardening, scoring proof fixes).
>
> **Last updated:** 2026-06-16 (post-PR-#267 deep fix pass)
> **Branch:** `main`
> **HEAD:** `4dd4d5c8`
> **Companion roadmap:** `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md`
> **Live fleet snapshot:** `docs/state/canonical-trading-status.md` (⚠️ STALE — regenerated before PR #267, needs re-generation)

---

## 1. System State

| Property | Value |
|----------|-------|
| Live trading | 🔴 `FORBIDDEN` — all bots `dry_run=true` |
| Deployment mode | Containerized (Docker Compose) |
| State machine | `LIVE_FORBIDDEN` — no path to live without RiskGuard validation + human approval |
| Signal source | `ai-hedge-fund-crypto` (Bitget Futures OHLCV) + Rainbow §5 (read_only, observed only) |
| Meta-orchestrator | `hermes-agent` in the `orchestrator` profile |
| SI v2 controller | `PAUSED / L3_REPOSITORY_ONLY` |

### Bot Fleet

| Bot | Mode | Strategy |
|-----|------|----------|
| FreqForge | dry-run | `FreqForge_Override` |
| Regime-Hybrid | dry-run | `RegimeSwitchingHybrid_v7_v04_Integration` |
| FreqForge-Canary | dry-run | `FreqForge_Override` |
| FreqAI-Rebel | dry-run | `RebelLiquidation + RebelXGBoostClassifier` |
| Webserver | — | UI only |
| Momentum | — | DECOMMISSIONED |
| MVS | — | NOT_DEPLOYED |

---

## 2. SI v2 Controller Status

| Property | Value |
|----------|-------|
| **Status** | **PAUSED** |
| **Mode** | `continuous_implementation` |
| **Operation level** | `L3_REPOSITORY_ONLY` |
| **Merge policy** | `HUMAN_ONLY` |
| **Runtime policy** | `FORBIDDEN` |
| **Pause reason** | `AWAITING_NEXT_APPROVED_EPIC` |
| **Active epic** | None |
| **External state dir** | `/opt/data/si-v2-controller/state/` |
| **Active worktree** | None |
| **Active PR** | None |

### Active Cycle / Observation Loop

* **Scheduler job:** `64866012641a` ("si-v2-active-cycle (6h, log-only)"),
  schedule `17 */6 * * *`, profile `orchestrator`.
* **Wrapper:** `/opt/data/scripts/si-v2-active-cycle-runner.sh` (mode 0700,
  owner `hermes:hermes`).
* **Latest cycle:** `20260614T204852Z` (2026-06-14 20:48:52 UTC).
* **Fleet verdict:** `GREEN`. **Mutations:** 0 across
  runtime/config/live_trading/docker/strategy. **Ping:** 4 / 4.
* **Rainbow observation:** `SUCCESS` (source `read_only`, count 3).
  Freshness scoring-eligible cycles **4 / 10 persisted in ledger**.
  Producer is deployed via `rainbow_producer_manager.sh`, health checks passing.
  See §3 Phase 2.1 for status.
* **Ledger:** 27 fleet cycles, 108 bot measurement points, 24 proposal
  records, `mutations_all_zero=True`, `secrets_found=False`.

### Controller Isolation (#176)

* **#176 closed at Stage A** (label `status:stage-a-complete`). Stage A
  isolation proof is the label-level attestation; the on-host
  `si-v2-controller` Unix user **does not exist on this host today**
  (`getent passwd si-v2-controller` returns nothing).
* **Stage B** (dedicated Unix user, dedicated `HERMES_HOME`, scoped
  GitHub/provider creds, hardened service unit) is future hardening,
  deferred until the controller is actually activated. The current
  observation loop is Stage A sufficient because it only reads Freqtrade
  REST + Rainbow read_only HTTP via a loopback stub.
* No `si-v2-controller` user is created in this PR. No systemd units
  are installed. The Hermes scheduler is the only activation path.

---

## 3. Phase Progress Summary

| Phase | Name | Status |
|-------|------|--------|
| 0 | Stabilization & Foundation | ✅ Complete (all 12 issues closed) |
| 1 | Shadowlock & Foundation | ✅ Complete (#12, #45, #47 merged) |
| — | Controller Layer (PR #158–#160) | ✅ Complete (merged) |
| 1i | Real-Data Intelligence | ✅ Complete: #55–#59 (PRs #161–#166). #60 merged (PR #169). #61 closed. |
| 1r | Rainbow Plumbing | ✅ Complete: PRs #212 (client), #213 (cycle/ledger), #214 (env override), #215 (runtime source + freshness guard) |
||| **2.0** | **Runtime Foundation & Docker Ownership** | ✅ **COMPLETE** — #200 closed, telemetry history gate merged (PR #262) |
||| **2.1** | **SI v2 Autonomous Dry-Run Operation** | 🟡 **PARTIAL** — producer deployed, scoring eligible via manual acceptance test. Awaiting first scheduled SI v2 cycle to persist 1/10 scoring. |
| 2.2 | Observability, Hardening & Self-Healing | ⏸ Pending — behind 2.0/2.1 |
| 3 | Signal Weighting & Higher Autonomy | ⏸ Pending — behind 2.1 history gate |

### Phase 0 — Status (Reconciled)

All 12 Phase 0 issues (#22, #23, #32, #30, #31, #20, #21, #25, #26, #27,
#38, #39, #12, #45, #47) have been completed via PRs #49–#54, #68–#75.

Additionally, Phase 0 child issues #43 (FleetRiskManager fix, PR #77)
and #40 (dry-run signal revalidation, PR #142) are **CLOSED**.

### Phase 0 Remediation Issues (reconciled)

| Issue | Title | Status | Notes |
|-------|-------|--------|-------|
| [#44](https://github.com/GoLukeEnviro/trading-hub/issues/44) | Runtime / Docker Compose ownership and healthcheck hardening (parent) | ✅ **CLOSED** 2026-06-12 | Parent. Split into #199 (closed), #200 (closed), #201 (closed). |
| [#199](https://github.com/GoLukeEnviro/trading-hub/issues/199) | infra: Add deterministic Docker healthchecks for Freqtrade fleet | ✅ **CLOSED** 2026-06-13 (PR #204) | Healthchecks present and observable in `canonical-trading-status.md`. |
| [#200](https://github.com/GoLukeEnviro/trading-hub/issues/200) | infra: Canonicalize Compose project ownership, file authority, and unmanaged-container drift | ✅ **CLOSED** 2026-06-16 | Docker Ownership resolved. Telemetry history gate (PR #262) provides enforcement. |
| [#201](https://github.com/GoLukeEnviro/trading-hub/issues/201) | security: Evaluate non-root container execution for hermes-green and green-qdrant | ✅ **CLOSED** 2026-06-16 | P2 hardening — resolved without action. Deferred to Phase 2.2 if needed. |
| [#46](https://github.com/GoLukeEnviro/trading-hub/issues/46) | [SI v2][Phase 0] Branch, PR, and worktree hygiene execution plan | ✅ **CLOSED** 2026-06-11 | Branch/worktree hygiene accepted. |
| [#60](https://github.com/GoLukeEnviro/trading-hub/issues/60) | [SI v2][Phase 1] Add Shadowlock SQLite maintenance command and approval-gated daily job plan | ✅ **CLOSED** 2026-06-11 (PR #169) | Maintenance running under approval-gate. |

---

## 4. SI v2 Implementation Progress

### Scheduled Observation Loop — 🟢 OPERATIONAL

The SI v2 scheduled observation loop is **operational** as of the merge
of PR #213 (Rainbow cycle + ledger integration) and PR #214 (env-var
override) and PR #215 (runtime source + freshness guard). The
**Measurement Ledger** (PR #210) and the **Active Cycle Runner**
(PR #208) write deterministic JSONL artifacts. Mutation counters are
zero across the board. The **Rainbow §5 read_only source** is observed and now scoring-eligible
(producer deployed 2026-06-15, `fresh=True`, see §3 Phase 2.1).

### Capability Status

See `docs/state/si-v2-capability-matrix.md` (rebuilt in this PR) for
the full matrix.

### Live-Readiness Status — 🚫 BLOCKED

* All SI v2 evidence, attribution, and readiness artifacts run on
  **fixtures or read_only** observation.
* No real (live) market data pipeline is connected.
* No real Freqtrade trade data is ingested.
* Timer and dedicated-user activation are **blocked**.
* Scoring gate: **producer deployed, fresh=True, scoring-eligible persisted (4/10 cycles in ledger)**
  (see `docs/plans/producer-freshness-fix-deployment.md` for deployment log)

---

## 5. Safety Layer Status

| Component | Status | Notes |
|-----------|--------|-------|
| `dry_run` | ✅ `True` (all bots) | Enforced |
| RiskGuard contract | ✅ Defined | `docs/specs/runtime-safety-contract.md` |
| ShadowLogger contract | ✅ Defined | `docs/specs/runtime-safety-contract.md` |
| RiskGuard implementation | 🔶 SI v2 spec only | Not a standalone service |
| ShadowLogger implementation | ✅ Deployed | JSONL audit trail (`orchestrator/logs/shadow_decisions.jsonl`) |
| FleetRiskManager | ✅ Deployed | With dry-run entry bug (#43) — fixed |
| CI safety gates | ✅ Implemented | PR #53 (#31) |
| SI v2 mutation counters | ✅ Zero | Across all 27 fleet cycles |

---

## 6. Completed: Runtime Ownership — Unmanaged Container Drift (#200)

Issue #200 is **CLOSED**. The Docker ownership analysis was completed, and
the telemetry history enforcement gate (PR #262) now provides deterministic
coverage. The unmanaged-container drift is documented in the archived
container ownership map.

**Legacy context (superseded):** 20 containers running, 7 with no
`com.docker.compose.project` label at the time of analysis. The SI v2 loop
was never affected — it is Stage A isolated and reads only Freqtrade REST +
the Rainbow read_only stub. The drift was a fleet-automation reliability
concern, not a loop-failure concern.

**Owner (archived):** Hermes.
**Reference:** `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md` Phase 2.0.

---

## 7. Related Documents

| Document | Location | Status |
|----------|----------|--------|
| Roadmap v2 (canonical forward-looking) | `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md` | ✅ Current |
| Implementation Roadmap (historical) | `docs/roadmap/implementation-roadmap.md` | 🔶 Superseded by Roadmap v2 |
| Current Operational State (this file) | `docs/state/current-operational-state.md` | ✅ Current |
| Live Fleet Snapshot (regenerated) | `docs/state/canonical-trading-status.md` | ✅ Current |
| SI v2 Capability Matrix (rebuilt) | `docs/state/si-v2-capability-matrix.md` | ✅ Current |
| Telemetry History Store (PR #262) | `self_improvement_v2/src/si_v2/observe/telemetry_history.py` | ✅ Merged |
| Walk-Forward Cost Model (PR #261) | `backtests/cost_model/` + `docs/backtesting/walk-forward-cost-model.md` | ✅ Merged |
| Producer Freshness Fix Plan | `docs/plans/producer-freshness-fix-deployment.md` | ✅ L3 deployment completed 2026-06-15 |
| Producer Acceptance Test | `orchestrator/scripts/rainbow_producer_acceptance_test.py` | ✅ Production-grade |
| Producer Manager (canonical) | `orchestrator/scripts/rainbow_producer_manager.sh` | ✅ Canonical lifecycle script |
| Scoring Proof Script | `orchestrator/scripts/rainbow_scoring_proof.py` | ✅ Validates scoring eligibility |
| Phase 1 Intelligence Epic (historical) | `docs/state/phase-1-intelligence-epic.md` | 🔶 Historical snapshot at PR #161 |
| Post-PR-160 Architecture (historical) | `docs/state/post-pr-160-architecture.md` | 🔶 Snapshot at PR #160 |
| Issues #55–#61 Evidence Matrix (historical) | `docs/state/issues-55-61-evidence-matrix.md` | 🔶 Snapshot at PR #169 |
| Phase 0 Closure Matrix (historical) | `docs/reports/phase0-closure-matrix-20260611.md` | 🔶 Superseded — see Roadmap v2 |
| PR #215 evidence | `docs/context/2026-06-14-si-v2-rainbow-read-only-runtime-source.md` | ✅ Current |
| PR #215 historical blocker snapshot | `docs/context/2026-06-14-si-v2-rainbow-read-only-prereq-blocked.md` | 🔶 Superseded by PR #215 |
| AGENTS.md | `AGENTS.md` | ✅ Current |

---

## 8. Hermes Memory State

As of 2026-06-15, the orchestrator profile's durable memory was curated in a
two-pass operation. No trading runtime, Docker, Freqtrade, or credential state
was changed.

### Memory Footprint

| Store | Chars | Limit | Usage | Entries |
|-------|-------|-------|-------|---------|
| MEMORY | 1,083 | 2,200 | 49% | 6 |
| USER PROFILE | 700 | 1,375 | 50% | 5 |

### Curation Actions

- Removed stale snapshot entries (fleet container count, PR progress, Honcho
  Deriver).
- Consolidated GitHub/SSH authentication into one compact entry.
- Replaced volatile detail with durable rules (fleet dry-run rule, CI quirks).
- Moved `Trading Hub runtime mutations` preference from MEMORY to its proper
  home in USER PROFILE (already present there).
- Added Honcho decommissioned/archived marker.
- Shortened all 5 USER PROFILE entries for headroom while preserving all
  semantic content.

### Memory Hygiene Rules (active)

1. Keep MEMORY under ~1,500 chars for operating headroom.
2. Store task progress, PR numbers, and incident details in `docs/context/`,
   not canonical memory.
3. Replace snapshot-like runtime facts with durable rules.
4. Treat Honcho references as stale unless explicitly reactivated.

### Related Context Reports

- `docs/context/hermes-memory-curation-20260615-120328.md` — Pass 1 (MEMORY)
- `docs/context/hermes-memory-curation-user-profile-20260615-120600.md` — Pass 2 (USER PROFILE)
