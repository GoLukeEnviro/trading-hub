# R5B Cutover Gate Planning — HermesTrader Cutover & agent0 Retirement Plan

> **Execution class:** A1 (repository-only: docs/reports + state file reconciliation; no host mutation, no Docker/Compose mutation, no agent0 mutation)
> **Branch:** `docs/r5b-cutover-gate-planning`
> **Issue:** #561 `[Root-Runtime][R5b] HermesTrader cutover gate and agent0 retirement plan`
> **Dependencies:** R5A COMPLETE (PR #560, `80f9733`, `R5A_PARITY_GREEN`, Issue #527 closed) ✅ | Main Gate green on `main` (PR #562 SUCCESS) ✅
> **Scope:** Inventory + gap analysis + sequenced retirement plan ONLY. No agent0 mutation. No host mutation. No Docker/Compose mutation. A2 approval required before any execution phase.

---

## 1. Executive Summary

R5A deployed and proved parity of the **canonical HermesTrader dry-run fleet** (5/5 services healthy: `freqforge`, `freqforge-canary`, `regime-hybrid`, `webserver`, `rainbow` — all `dry_run=true`, Rainbow read-only/fail-closed, kill-switch cycle proven, secret scan clean). ai4trade runtime locked to `6e850c8f8ba1d8a0ad45250f130280e4171c001d`.

R5B is the **cutover gate**: plan the migration of the **active agent0 dry-run fleet** (4 bots + webserver verified running on agent0 as of R3 live verification 2026-07-11) to the **canonical HermesTrader dry-run fleet**, then retire agent0 trading workloads. This plan is **inventory + gap analysis + sequenced retirement steps only**. Execution requires separate A2 approval with full approval gates (snapshot, canary, allowlist, rollback, audit, bounded measurement).

---

## 2. Current Fleet State Inventory (as of 2026-07-13)

### 2.1 HermesTrader (Canonical Target Fleet — R5A PROVEN)

| Service | Container | Image | Status | Dry-run | Config | Notes |
|---------|-----------|-------|--------|---------|--------|-------|
| freqforge | `freqforge` | `freqtradeorg/freqtrade:stable@sha256:87aa5c6...` (via `Dockerfile.hermes10000`) | ✅ Healthy | ✅ `true` | `config_fqforge_dryrun.json` | R5A parity green |
| freqforge-canary | `freqforge-canary` | same base | ✅ Healthy | ✅ `true` | `config_canary_dryrun.json` | R5A parity green |
| regime-hybrid | `regime-hybrid` | same base | ✅ Healthy | ✅ `true` | `config_regime_hybrid_dryrun.json` | R5A parity green |
| webserver | `webserver` | same base | ✅ Healthy | ✅ `true` | `config_webserver_dryrun.json` | Support service |
| rainbow | `rainbow` | `ai4trade-bot@6e850c8` (Rainbow storage fix #102) | ✅ Healthy | Advisory read-only | N/A | Storage UID 10000 fixed |

**Compose:** `docker-compose.hermestrader-dryrun.yml` (canonical, R7A/R4 via PR #524, merge `ee767a10`)
**Network:** `hermestrader-dryrun_internal` (internal) + `hermestrader-dryrun_egress` (Bitget egress only)
**Volumes:** All UID/GID 10000 owned; Rainbow storage fixed via ai4trade #102
**Kill switch:** Provisioned at `NORMAL` (git-ignored `freqtrade/shared/kill_switch.json`)

### 2.2 agent0 (Current Live Dry-Run Fleet — R3 Verified Running 2026-07-11)

| Bot | Container | Image | Status | Dry-run | Config Source | Reproducibility |
|-----|-----------|-------|--------|---------|---------------|-----------------|
| freqforge | `trading-freqtrade-freqforge-1` | `freqtrade-hermes1337:freqforge-c5` (af2a49a68e60) | ✅ Up, healthy | ✅ | Bind-mount `/home/hermes/projects/trading/freqtrade/...` | **REPRODUCIBLE_NOW** (R3) — uses `freqtrade/shared/`, `Dockerfile.hermes10000` compatible |
| freqforge-canary | `trading-freqtrade-freqforge-canary-1` | `freqtradeorg/freqtrade:stable` (3c79f4f57817) | ✅ Up | ✅ | Bind-mount `/home/hermes/projects/trading/freqtrade/...` | **REPRODUCIBLE_NOW** (R3) — stock image, target = `Dockerfile.hermes10000` |
| regime-hybrid | `trading-freqtrade-regime-hybrid-1` | `freqtrade-hermes1337:regime-hybrid-c5` (af2a49a68e60, same as freqforge) | ✅ Up | ✅ | Bind-mount `/home/hermes/projects/trading/freqtrade/...` | **REPRODUCIBLE_NOW** (R3) — uses `freqtrade/shared/` |
| freqai-rebel | `trading-freqai-rebel-1` | `freqtrade-hermes1337:freqai-rebel-c25` (cf3108ad4ec6) | ✅ Up 40h | ✅ | Bind-mount + `user_data/models/` (1.2 GB) | **NOT_REPRODUCIBLE** (R3) — 1.2 GB trained models not in repo, FreqAI deps missing, `directory_operations.py` patch not committed |
| webserver | `trading-freqtrade-webserver-1` | `freqtrade-hermes1337:webserver-c5` (af2a49a68e60) | ✅ Up 8d | ✅ | Bind-mount | Support service — evaluated in R4 |

**Key discrepancies (flagged in R3, NOT resolved):**
- agent0 fleet runs on **custom `freqtrade-hermes1337:*` images** (UID 1337) — NOT the canonical `Dockerfile.hermes10000` (UID 10000)
- agent0 uses **bind-mounts to `/home/hermes/projects/trading/`** — NOT the repo-mounted compose stack
- **rebel is NOT_REPRODUCIBLE** on HermesTrader (1.2 GB models, missing FreqAI deps, uncommitted patch)
- **State file drift:** `current-operational-state.md` claims "no bots running" but R3 verified all 5 services running on agent0

### 2.3 Infrastructure State

| Component | agent0 (current) | HermesTrader (target) | Gap |
|-----------|------------------|----------------------|-----|
| Docker host | agent0 VPS | HermesTrader VPS | Separate hosts |
| Compose | Implicit/adhoc (no canonical file) | `docker-compose.hermestrader-dryrun.yml` (canonical) | agent0 has no versioned compose |
| Images | `freqtrade-hermes1337:*` (UID 1337) | `Dockerfile.hermes10000` base (UID 10000) | UID mismatch, image lineage different |
| Configs | Bind-mounted from `/home/hermes/projects/trading/` | Repo-mounted configs in compose | Config drift risk |
| Volumes | Named volumes on agent0 | Named volumes on HermesTrader (UID 10000) | Volume migration needed |
| Rainbow | Not running | Running (advisory, read-only) | New capability on HermesTrader |
| Root executor | N/A (legacy D1/D2/D3) | `hermes-root-executor.service` (UID 0, proven) | New capability |
| Kill switch | File-based (state unknown) | Provisioned `NORMAL` on HermesTrader | State sync needed |
| ai4trade lock | N/A (uses local images) | `6e850c8f8ba1d8a0ad45250f130280e4171c001d` | Pinned |

---

## 3. Gap Analysis (R5A → R5B Cutover)

### 3.1 Reproducibility Gaps (from R3 Decision)

| Bot | Gap | Resolution Path |
|-----|-----|-----------------|
| freqforge | Image UID 1337 vs 10000; bind-mount vs repo-mount | Re-deploy via canonical compose (R5A proven) |
| canary | Stock image vs `Dockerfile.hermes10000` | Re-deploy via canonical compose (R5A proven) |
| regime-hybrid | Image UID 1337 vs 10000; bind-mount vs repo-mount | Re-deploy via canonical compose (R5A proven) |
| rebel | **NOT_REPRODUCIBLE** — 1.2 GB models, FreqAI deps, uncommitted patch | **Excluded from canonical fleet** (R3 decision: `SELECTED_FLEET_MODEL = OPTION_C`, rebel = profile-gated only) |
| webserver | Image UID 1337 vs 10000 | Re-deploy via canonical compose (R5A proven) |

**Resolution:** The 3 reproducible bots + webserver are **already deployed and parity-proven on HermesTrader** (R5A). The cutover is a **traffic/state switch**, not a rebuild.

### 3.2 State & Data Migration Gaps

| Asset | agent0 Location | HermesTrader Target | Migration Needed |
|-------|-----------------|---------------------|------------------|
| Freqtrade DB (trades, locks) | `/home/hermes/projects/trading/freqtrade/user_data/` (bind-mounted) | Docker volumes `hermestrader-dryrun_freqforge-userdata` etc. (UID 10000) | **YES** — DB export/import or volume migration |
| Kill switch state | `freqtrade/shared/kill_switch.json` (bind-mounted) | `freqtrade/shared/kill_switch.json` (git-ignored, UID 10000) | **YES** — sync state (currently NORMAL on both) |
| Rainbow storage | N/A | `hermestrader-dryrun_rainbow-storage` (UID 10000, fixed) | N/A — new on HermesTrader |
| Strategy configs | Bind-mounted JSON files | Compose-mounted configs (same content, verified by R3 strategy hash match) | **NO** — content identical per R3 |
| `freqtrade/shared/` modules | Bind-mounted | Compose-mounted (same repo path) | **NO** — content identical |

### 3.3 Operational Gaps

| Area | agent0 | HermesTrader | Gap |
|------|--------|--------------|-----|
| Deployment automation | Manual `docker run` / adhoc | Compose stack + root executor | HermesTrader has managed deployment |
| Health monitoring | Manual `docker ps` | Compose healthchecks + Rainbow advisory | HermesTrader has observability |
| Rollback | Manual container restart | Rehearsed rollback via root executor | HermesTrader has rollback path |
| Secret management | Files on host | Git-ignored files + secret scan clean | HermesTrader has audit trail |
| Network policy | Host network (default) | Split internal/egress networks | HermesTrader has isolation |
| UID hygiene | UID 1337 (legacy) | UID 10000 (canonical) | **Migration required** |

---

## 4. Sequenced Retirement Plan (Cutover Phases)

> **ALL PHASES REQUIRE A2 APPROVAL BEFORE EXECUTION.** This plan is evidence-only until each phase gate is explicitly approved.

### Phase 0: Pre-Cutover Validation (A1 — already complete via R5A/R3)

- ✅ R5A HermesTrader fleet: 5/5 healthy, parity proven, `dry_run=true`
- ✅ R3 reproducibility decision: 3 bots + webserver = REPRODUCIBLE_NOW
- ✅ Strategy hashes match (R3 verified)
- ✅ ai4trade locked to `6e850c8` (Rainbow storage fix)
- ✅ Kill switch NORMAL on HermesTrader
- ✅ Root executor proven (Issue #531 proof matrix 5/5)
- ✅ Secret scan clean (Main Gate green)
- ⚠️ agent0 fleet running (R3 verified) — state file drift documented
- ⚠️ rebel NOT_REPRODUCIBLE — excluded from canonical fleet per R3

**Gate 0:** `R5A_PARITY_GREEN` + `R3_DECISION_RECORDED` + `ROOT_EXECUTOR_GREEN` → **ALL GREEN** ✅

---

### Phase 1: State Sync & Freeze (A2 — requires A2 approval)

**Objective:** Freeze agent0 fleet state; sync critical state to HermesTrader; prepare for traffic switch.

| Step | Action | Tool | Validation | Rollback |
|------|--------|------|------------|----------|
| 1.1 | Snapshot agent0 volumes (restic) | `hermes-root-executor` (remote) | Snapshot ID recorded | Restore from snapshot |
| 1.2 | Export Freqtrade DB from agent0 | `hermes-root-executor` (remote) | Export files verified (checksums) | Re-import to agent0 |
| 1.3 | Import Freqtrade DB to HermesTrader volumes | `hermes-root-executor` (local) | Import verified; trade counts match | Recreate volumes from scratch |
| 1.4 | Sync kill switch state (agent0 → HermesTrader) | `hermes-root-executor` | Both show `NORMAL` | Manual file copy |
| 1.5 | Freeze agent0 fleet (stop accepting new trades) | Kill switch → `HALT_NEW` on agent0 | Kill switch file shows `HALT_NEW` | Kill switch → `NORMAL` |
| 1.6 | Verify HermesTrader fleet still healthy | Compose healthchecks + Rainbow | 5/5 green | N/A |

**Gate 1:** `AGENT0_SNAPSHOT_GREEN` + `DB_SYNC_VERIFIED` + `KILL_SWITCH_SYNCED` + `HERMESTRADER_HEALTHY` → A2 approval required

---

### Phase 2: Canary Traffic Switch (A2 — requires A2 approval)

**Objective:** Switch canary bot traffic to HermesTrader first (canary-first principle).

| Step | Action | Tool | Validation | Rollback |
|------|--------|------|------------|----------|
| 2.1 | Start `freqforge-canary` on HermesTrader (already running, verify) | Compose | Container healthy, API responding | N/A (already running) |
| 2.2 | Stop `trading-freqtrade-freqforge-canary-1` on agent0 | `hermes-root-executor` (remote) | Container stopped | Restart container on agent0 |
| 2.3 | Verify canary trades only on HermesTrader | Freqtrade API / DB | New trades appear on HermesTrader only | Re-enable agent0 canary |
| 2.4 | Monitor canary for 1 measurement window (T0→T1) | Rainbow / Decision Engine | Measurement data flowing | Revert to agent0 |

**Gate 2:** `CANARY_SWITCH_VERIFIED` + `MEASUREMENT_WINDOW_GREEN` → A2 approval required

---

### Phase 3: Baseline Fleet Switch (A2 — requires A2 approval)

**Objective:** Switch remaining reproducible bots (freqforge, regime-hybrid, webserver) to HermesTrader.

| Step | Action | Tool | Validation | Rollback |
|------|--------|------|------------|----------|
| 3.1 | Stop `trading-freqtrade-freqforge-1` on agent0 | `hermes-root-executor` (remote) | Container stopped | Restart on agent0 |
| 3.2 | Stop `trading-freqtrade-regime-hybrid-1` on agent0 | `hermes-root-executor` (remote) | Container stopped | Restart on agent0 |
| 3.3 | Stop `trading-freqtrade-webserver-1` on agent0 | `hermes-root-executor` (remote) | Container stopped | Restart on agent0 |
| 3.4 | Verify all 4 bots + webserver on HermesTrader | Compose + API | 5/5 healthy, trades executing | Re-enable agent0 fleet |
| 3.5 | Update kill switch on agent0 → `EMERGENCY` (hard freeze) | `hermes-root-executor` (remote) | File shows `EMERGENCY` | Manual override |

**Gate 3:** `BASELINE_FLEET_SWITCH_VERIFIED` + `AGENT0_FROZEN` → A2 approval required

---

### Phase 4: agent0 Retirement & Validation (A2 — requires A2 approval)

**Objective:** Confirm agent0 trading workloads fully retired; validate HermesTrader as sole dry-run fleet.

| Step | Action | Tool | Validation | Rollback |
|------|--------|------|------------|----------|
| 4.1 | Verify zero trades on agent0 for 24h | Freqtrade API / DB | No new trades, no open positions | Re-enable if needed |
| 4.2 | Decommission agent0 trading containers | `hermes-root-executor` (remote) | Containers removed | Recreate from snapshots |
| 4.3 | Decommission agent0 trading volumes | `hermes-root-executor` (remote) | Volumes removed (after backup retention) | Restore from restic |
| 4.4 | Archive agent0 configs/state to cold storage | `hermes-root-executor` (remote) | Archive verified (checksums) | N/A |
| 4.5 | Update DNS/routing if any (webserver) | `hermes-root-executor` (local) | Webserver accessible on HermesTrader | Revert DNS |

**Gate 4:** `AGENT0_TRADING_ZERO` + `HERMESTRADER_SOLE_FLEET` → A2 approval required

---

### Phase 5: Post-Cutover Reconciliation (A1 — can proceed after Gate 4)

**Objective:** Reconcile documentation, state files, and handoff to R6/R7.

| Step | Action | Tool | Validation |
|------|--------|------|------------|
| 5.1 | Update `current-operational-state.md` — agent0 retired, HermesTrader canonical | Git (A1) | PR merged |
| 5.2 | Close Issue #561 with `R5B_CUTOVER_COMPLETE` | GitHub | Issue closed |
| 5.3 | Archive agent0 operational docs to `docs/context/` | Git (A1) | Files committed |
| 5.4 | Handoff to R6 (permanent reconciliation via systemd) | Roadmap tick | R6 issue created |
| 5.5 | Handoff to R7 / #496 (Rainbow dry-run measurement) | Roadmap tick | R7 unblocked |

**Gate 5:** `STATE_RECONCILED` + `R6_UNBLOCKED` + `R7_UNBLOCKED` → automatic (A1)

---

## 5. Approval Gates Summary

| Gate | Phase | Required Approval | Evidence Required |
|------|-------|-------------------|-------------------|
| Gate 0 | Pre-validation | **AUTO** (already satisfied) | R5A_PARITY_GREEN, R3_DECISION, ROOT_EXECUTOR_GREEN |
| Gate 1 | State Sync & Freeze | **A2** (explicit human) | Snapshot IDs, DB checksums, kill-switch sync, health checks |
| Gate 2 | Canary Switch | **A2** (explicit human) | Canary-only-on-HermesTrader, measurement window initiated |
| Gate 3 | Baseline Switch | **A2** (explicit human) | All 4 bots on HermesTrader, agent0 EMERGENCY |
| Gate 4 | agent0 Retirement | **A2** (explicit human) | 24h zero trades, containers/volumes decommissioned |
| Gate 5 | Reconciliation | **A1** (automatic) | State file updated, issues closed, R6/R7 unblocked |

---

## 6. Safety Invariants (Must Hold at Every Gate)

| Invariant | Enforcement |
|-----------|-------------|
| `dry_run=true` on ALL bots, always | Compose config immutable; secret scan blocks `dry_run=false` |
| No live exchange credentials on either host | Secret scan on both hosts; external live approval required |
| Kill switch respected | `HALT_NEW`/`EMERGENCY` blocks new entries on both fleets |
| Rollback capability maintained | Restic snapshots + rehearsed rollback via root executor |
| Rebel excluded from canonical fleet | Compose profile `rebel` not in default deploy; `NOT_REPRODUCIBLE` recorded |
| C4 `ROLLBACK_RECOMMENDED` preserved | No live rollout without C4 `KEEP` + `APPROVED_LIVE_FLEET_ROLLOUT` |
| D1/D2 live gates blocked | Explicitly recorded in state file |
| UID 10000 on HermesTrader | `Dockerfile.hermes10000` bakes UID; compose enforces |
| No `git add .`, no force-push, no reset --hard | AGENTS.md discipline enforced |

---

## 7. Rollback Strategy (Per Phase)

| Phase | Rollback Trigger | Rollback Action | Max Time |
|-------|------------------|-----------------|----------|
| 1 | DB sync fails / health check fails | Restore agent0 from restic snapshot; kill switch → NORMAL | 15 min |
| 2 | Canary measurement fails / health degrades | Restart agent0 canary; kill switch → NORMAL on agent0 | 10 min |
| 3 | Baseline bots unhealthy on HermesTrader | Restart agent0 fleet (freqforge, regime-hybrid, webserver) | 15 min |
| 4 | Unexpected trades on agent0 after freeze | Kill switch → EMERGENCY on agent0; investigate | 5 min |

**Rollback rehearsal:** Phase 5A (`rollback_rehearsal.py`, PR #383) completed and rehearsed but not executed. Root executor rollback path proven in Issue #531 proof matrix.

---

## 8. Blocker

`NONE` for A1 planning work. **A2 approval required for Gate 1 (Phase 1 execution).**

---

## 9. Next Automatic Action

Post-merge reconciliation: R5B planning COMPLETE. Next roadmap tick will:
- Reconcile Issue #561 (mark planning complete)
- Wait for A2 approval for Gate 1 (Phase 1: State Sync & Freeze)
- R6 (permanent reconciliation via systemd) and R7/#496 (Rainbow dry-run measurement) remain blocked pending R5B execution completion

---

## 10. References

- R5A Parity Proof: PR #560, merge `80f9733`, Issue #527 (`R5A_PARITY_GREEN`)
- R3 Fleet Reproducibility Decision: `docs/reports/r3-fleet-reproducibility-decision-2026-07-11.md`
- R7A/R4 Greenfield Compose: PR #524, merge `ee767a10`
- Root Executor Proof Matrix: Issue #531 (5/5 green)
- HermesTrader Dry-Run Compose: `docker-compose.hermestrader-dryrun.yml`
- ADR-2026-07-11: `docs/decisions/ADR-2026-07-11-hermes-root-runtime-authority.md`
- Current Operational State: `docs/state/current-operational-state.md`
- Issue #423: Canonical live-gate anchor (C4 `ROLLBACK_RECOMMENDED`, D1/D2 blocked)
- Issue #561: `[Root-Runtime][R5b] HermesTrader cutover gate and agent0 retirement plan`

---

**End of Report**