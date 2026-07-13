# R5B Cutover Gate Planning — HermesTrader Cutover & agent0 Retirement Plan

> **Execution class:** A1 (repository-only: docs/reports + state file reconciliation; no host mutation, no Docker/Compose mutation, no agent0 mutation)
> **Branch:** `docs/r5b-cutover-gate-planning`
> **Issue:** #561 `[Root-Runtime][R5b] HermesTrader cutover gate and agent0 retirement plan`
> **Dependencies:** R5A COMPLETE (PR #560, `80f9733`, `R5A_PARITY_GREEN`, Issue #527 closed) ✅ | Main Gate green on `main` (PR #562 SUCCESS) ✅
> **Scope:** Inventory + gap analysis + sequenced retirement plan ONLY. No agent0 mutation. No host mutation. No Docker/Compose mutation. A2 approval required before any execution phase.

---

## 1. Executive Summary

R5A deployed and proved parity of the **canonical HermesTrader dry-run fleet** (5/5 services healthy: `freqforge`, `freqforge-canary`, `regime-hybrid`, `webserver`, `rainbow` — all `dry_run=true`, Rainbow read-only/fail-closed, kill-switch cycle proven, secret scan clean). ai4trade runtime locked to `6e850c8f8ba1d8a0ad45250f130280e4171c001d`.

R5B is the **canonical dry-run cutover gate**: it covers only the three reproducible agent0 trading roles (`freqforge`, `freqforge-canary`, `regime-hybrid`) and the agent0 webserver. `freqai-rebel` is an explicitly isolated, non-canonical legacy exception and is not migrated, stopped, archived, or deleted by R5B. This plan is **inventory + gap analysis + sequenced, reversible cutover steps only**. No database, volume, model, or credential data is transferred. Execution requires a separate A2 approval for each gate.

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
| Volumes | Named volumes on agent0 | Named volumes on HermesTrader (UID 10000) | **No migration** — source data remains untouched on agent0 |
| Rainbow | Not running | Running (advisory, read-only) | New capability on HermesTrader |
| Root executor | N/A (legacy D1/D2/D3) | `hermes-root-executor.service` (UID 0, proven) | New capability |
| Kill switch | File-based, scoped to legacy roles | Provisioned `NORMAL` on HermesTrader | Gate 1 verifies isolation before a reversible canonical-role freeze |
| ai4trade lock | N/A (uses local images) | `6e850c8f8ba1d8a0ad45250f130280e4171c001d` | Pinned |

---

## 3. Gap Analysis (R5A → R5B Cutover)

### 3.1 Reproducibility Gaps (from R3 Decision)

| Bot | Gap | Resolution Path |
|-----|-----|-----------------|
| freqforge | Image UID 1337 vs 10000; bind-mount vs repo-mount | Re-deploy via canonical compose (R5A proven) |
| canary | Stock image vs `Dockerfile.hermes10000` | Re-deploy via canonical compose (R5A proven) |
| regime-hybrid | Image UID 1337 vs 10000; bind-mount vs repo-mount | Re-deploy via canonical compose (R5A proven) |
| rebel | **NOT_REPRODUCIBLE** — 1.2 GB models, FreqAI deps, uncommitted patch | **Non-canonical legacy exception**; owner Luke; review due within 30 days after this plan merges |
| webserver | Image UID 1337 vs 10000 | Re-deploy via canonical compose (R5A proven) |

**Resolution:** The 3 reproducible trading roles + webserver are **already deployed and parity-proven on HermesTrader** (R5A). The cutover is a **traffic switch without state transfer**, not a rebuild.

### 3.2 Data Boundary (No Migration)

| Asset | agent0 Location | HermesTrader Handling | R5B Rule |
|-------|-----------------|----------------------|----------|
| Freqtrade DB (trades, locks) | `/home/hermes/projects/trading/freqtrade/user_data/` (bind-mounted) | HermesTrader uses its existing canonical volumes | **No export, import, copy, snapshot, or deletion** |
| Kill switch state | Legacy bind-mounted file | Canonical kill switch remains independently managed | No state sync; a later approved freeze is reversible and scoped to canonical agent0 roles only |
| rebel models and state | agent0 bind-mount + `user_data/models/` | No HermesTrader target | Never transferred or handled by R5B |
| Rainbow storage | N/A | `hermestrader-dryrun_rainbow-storage` (UID 10000, fixed) | Canonical-only; no agent0 data input |
| Strategy configs and modules | Bind-mounted | Compose-mounted | Read-only hash/status evidence only |

### 3.3 Legacy Isolation Preflight

`freqai-rebel`, `rainbow-live-rainbow-1`, and `rainbow-live-dashboard-1` are non-canonical. Gate 1 begins with a read-only inventory proving that these legacy workloads share **no credentials, volumes, ports, networks, or delivery/execution control paths** with the canonical HermesTrader fleet. The evidence records identifiers and status only; it never prints secrets.

If any isolation condition cannot be proven, Gate 1 aborts before every mutation and a separate legacy-reconciliation task is required. R6 may exclude rebel only when this evidence is green.

### 3.4 Operational Gaps

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
- ✅ Exposed GitHub OAuth credential revocation request submitted externally; no credential value is recorded
- ✅ Primary Trading-Hub checkout fast-forwarded on `main`; PR #576 retained in its own worktree
- ✅ Read-only evidence: no active or planned Roadmap Cron jobs; no new job will be created before the separate hygiene gates
- ⚠️ agent0 fleet running (R3 verified) — state file drift documented
- ⚠️ rebel NOT_REPRODUCIBLE — excluded from canonical fleet per R3

**Gate 0:** `R5A_PARITY_GREEN` + `R3_DECISION_RECORDED` + `ROOT_EXECUTOR_GREEN` → **ALL GREEN** ✅

---

### Phase 1: Legacy Preflight & Reversible Freeze (A2 — requires A2 approval)

**Objective:** Prove legacy isolation, then freeze only the canonical agent0 roles within one explicitly approved maintenance window. No data moves.

**Hard boundary:** R5B does not snapshot, export, import, copy, archive, or delete databases, volumes, models, credentials, containers, or configuration files.

| Step | Action | Tool | Validation | Rollback |
|------|--------|------|------------|----------|
| 1.1 | Inventory legacy rebel and `rainbow-live-*` boundaries read-only | Read-only host/container inspection | No shared credentials, volumes, ports, networks, or delivery/execution paths | Abort before mutation if evidence is incomplete |
| 1.2 | Verify canonical HermesTrader fleet health | Compose healthchecks + Rainbow | 5/5 green | N/A |
| 1.3 | Record canonical agent0 role status and counters read-only | Freqtrade API / container status | Evidence complete; no data transferred | N/A |
| 1.4 | Freeze only canonical agent0 roles after steps 1.1–1.3 pass | Scoped kill switch → `HALT_NEW` | Previous state recorded; freeze verified | Restore the prior kill-switch state |

**Approval contract (defined, not issued by this report):**
- Marker: `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE`.
- Authority: Luke as repository owner; scope references Issue #561 and this exact gate.
- Validity: one UTC maintenance window, maximum 24 hours.
- Allowed commands: read-only inventory, read-only health/status checks, and the scoped reversible kill-switch freeze.
- Prohibited commands: data movement, snapshots, exports, imports, deletes, Docker/Compose changes, credential changes, container stops, and any Gate 2–4 action.
- Fail closed: failed or incomplete isolation evidence aborts before mutation; after a freeze, only restoring the immediately preceding kill-switch state is allowed.

**Gate 1:** `LEGACY_ISOLATION_VERIFIED` + `CANONICAL_HEALTHY` + `READ_ONLY_EVIDENCE_COMPLETE` + `CANONICAL_FREEZE_RECORDED` → A2 approval required

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

**Objective:** Switch the two remaining reproducible trading roles and the agent0 webserver to HermesTrader.

| Step | Action | Tool | Validation | Rollback |
|------|--------|------|------------|----------|
| 3.1 | Stop `trading-freqtrade-freqforge-1` on agent0 | `hermes-root-executor` (remote) | Container stopped | Restart on agent0 |
| 3.2 | Stop `trading-freqtrade-regime-hybrid-1` on agent0 | `hermes-root-executor` (remote) | Container stopped | Restart on agent0 |
| 3.3 | Stop `trading-freqtrade-webserver-1` on agent0 | `hermes-root-executor` (remote) | Container stopped | Restart on agent0 |
| 3.4 | Verify the 3 canonical roles, webserver, and Rainbow on HermesTrader | Compose + API | 5/5 healthy; canonical traffic only | Restart only the affected agent0 role |

**Gate 3:** `CANONICAL_FLEET_SWITCH_VERIFIED` + `AGENT0_CANONICAL_WORKLOADS_STOPPED` → A2 approval required

---

### Phase 4: Canonical Workload Inactivity Validation (A2 — requires A2 approval)

**Objective:** Make no new mutation; validate 24 hours of inactivity for the three canonical agent0 trading roles plus the agent0 webserver, while HermesTrader remains healthy.

| Step | Action | Tool | Validation | Rollback |
|------|--------|------|------------|----------|
| 4.1 | Observe canonical agent0 roles and webserver for 24h | Read-only API/container status | No activity; no container, volume, or data action | Retain all legacy state unchanged |

**Gate 4:** `CANONICAL_AGENT0_INACTIVITY_24H` + `HERMESTRADER_CANONICAL_HEALTHY` + `REBEL_LEGACY_ISOLATED` → A2 approval required

---

### Phase 5: Post-Cutover Reconciliation (A1 — can proceed after Gate 4)

**Objective:** Reconcile the canonical fleet state and hand off only to R6. R7 remains blocked.

| Step | Action | Tool | Validation |
|------|--------|------|------------|
| 5.1 | Update `current-operational-state.md` — HermesTrader canonical; rebel remains isolated legacy | Git (A1) | PR merged |
| 5.2 | Close Issue #561 with `R5B_CUTOVER_COMPLETE` | GitHub | Issue closed |
| 5.3 | Create the R6 task for the canonical HermesTrader fleet | Roadmap tick | R6 issue created |
| 5.4 | Record R7/#496 as blocked by R6 and the separate immutable runtime-promotion gate | GitHub/state file | No premature R7 start |

**Gate 5:** `STATE_RECONCILED` + `R6_UNBLOCKED` + `R7_STILL_BLOCKED` → automatic (A1)

---

## 5. Approval Gates Summary

| Gate | Phase | Required Approval | Evidence Required |
|------|-------|-------------------|-------------------|
| Gate 0 | Pre-validation | **AUTO** (already satisfied) | R5A_PARITY_GREEN, R3_DECISION, ROOT_EXECUTOR_GREEN |
| Gate 1 | Legacy Preflight & Reversible Freeze | **A2** (explicit human) | Legacy-isolation inventory, read-only evidence, canonical health, scoped freeze record |
| Gate 2 | Canary Switch | **A2** (explicit human) | Canary-only-on-HermesTrader, measurement window initiated |
| Gate 3 | Canonical Baseline Switch | **A2** (explicit human) | Three canonical trading roles plus webserver on HermesTrader; agent0 counterparts stopped |
| Gate 4 | Inactivity Validation | **A2** (explicit human) | 24h inactive canonical agent0 roles/webserver; no deletion or data handling |
| Gate 5 | Reconciliation | **A1** (automatic) | State file updated, #561 closed, R6 unblocked, R7 still blocked |

---

## 6. Safety Invariants (Must Hold at Every Gate)

| Invariant | Enforcement |
|-----------|-------------|
| `dry_run=true` on ALL bots, always | Compose config immutable; secret scan blocks `dry_run=false` |
| No live exchange credentials on either host | Secret scan on both hosts; external live approval required |
| Kill switch respected | `HALT_NEW`/`EMERGENCY` blocks new entries on both fleets |
| Rollback capability maintained | Reversible scoped kill-switch state and targeted service restart; no R5B data destruction |
| Rebel excluded and isolated | Owner Luke; 30-day review; no shared credentials, volumes, ports, networks, or control paths |
| Legacy Rainbow isolated | Gate 1 read-only inventory proves `rainbow-live-*` shares no canonical resource or execution path |
| C4 `ROLLBACK_RECOMMENDED` preserved | No live rollout without C4 `KEEP` + `APPROVED_LIVE_FLEET_ROLLOUT` |
| D1/D2 live gates blocked | Explicitly recorded in state file |
| UID 10000 on HermesTrader | `Dockerfile.hermes10000` bakes UID; compose enforces |
| No `git add .`, no force-push, no reset --hard | AGENTS.md discipline enforced |
| Roadmap Cron remains disabled | No creation or reactivation until `/proposals/` is fixed and the active skills profile is manifested |

---

## 7. Rollback Strategy (Per Phase)

| Phase | Rollback Trigger | Rollback Action | Max Time |
|-------|------------------|-----------------|----------|
| 1 | Isolation evidence incomplete / health check fails | Abort before mutation; if frozen, restore prior scoped kill-switch state | 15 min |
| 2 | Canary measurement fails / health degrades | Restart agent0 canary; kill switch → NORMAL on agent0 | 10 min |
| 3 | Canonical roles unhealthy on HermesTrader | Restart only the affected agent0 role or webserver | 15 min |
| 4 | Activity from a stopped canonical agent0 role or webserver | Make no new mutation; preserve data and investigate | 5 min |

**Rollback rehearsal:** Phase 5A (`rollback_rehearsal.py`, PR #383) completed and rehearsed but not executed. Root executor rollback path proven in Issue #531 proof matrix.

---

## 8. Blocker

`NONE` for A1 planning work. **A2 approval required for Gate 1 (Phase 1 execution).**

---

## 9. Next Action After Merge

Post-merge reconciliation: R5B planning is complete. No runtime action is automatic.
- Close Issue #561 as completed A1 planning.
- Wait for an explicit `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE` approval before any Gate 1 action.
- Keep Roadmap Cron disabled until the separate `/proposals/` hygiene fix and active skills-profile manifest are complete.
- R6 remains blocked pending R5B execution; R7/#496 remains blocked pending R6 and the separate immutable runtime-promotion gate.
**Not in scope:** the `/proposals/` ignore fix, tracked-but-ignored file classification, the skills manifest, `orchestrator.env` templating, `kill_switch.example.json`, ai4trade ignore hygiene, and any runtime activation.


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