# Trading Hub — Current Operational State

> **Canonical current-state snapshot** — validated against `main` at
> PR #586 (post-merge header refresh, merge `2f8cfbc`). R5A is **complete
> and parity-proven**: the canonical HermesTrader dry-run fleet (freqforge,
> freqforge-canary, regime-hybrid, webserver, rainbow) is persistently
> deployed with 5/5 health, full `dry_run=true` parity, and a clean secret
> scan. ai4trade runtime dependency is locked to
> `6e850c8f8ba1d8a0ad45250f130280e4171c001d`.
> H3B_RUNTIME_CONTROL_GREEN (PR #559) and the full Issue #531 proof
> matrix remain valid. The R5A executor extension was deployed at
> commit `782d2c04f59ee96151581de436b069095d28b019` (ratified by
> repository owner after installer bug-fix arc).
>
> **Last updated:** 2026-07-14 — SAFETY CORRECTION: Fresh agent0 evidence proves the planned canonical-role-only freeze is IMPOSSIBLE with the current fleet-wide kill switch. Agent0 `trading-freqai-rebel-1` is RUNNING and shares the fleet-wide writable kill-switch mount (`/home/hermes/projects/trading/freqtrade/shared` → `/freqtrade/shared` rw=true; `kill_switch.json` mode=NORMAL; `freqtrade/shared/kill_switch.py` is fleet-wide). Gate 1 remains BLOCKED/NOT APPROVABLE until Luke explicitly selects one of three decision paths. No role-scoped freeze exists. R6/R7 remain blocked; runtime_mutation=NONE.
> **Previous update:** 2026-07-14 post-roadmap-tick (PR #585 merged — Legacy Rainbow credential isolation RESOLVED PASS; Issue #583 closed; R5B Gate 1 now has 0 remaining UNVERIFIED items — both freqai-rebel config and Rainbow credential isolation resolved; Gate 1 remains BLOCKED pending explicit `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE` marker; no runtime mutation; R6 blocked by R5B; R7 split into #105 shadow validation + #496 attributed measurement; C4 ROLLBACK_RECOMMENDED preserved).
> **Earlier update:** 2026-07-14 post-roadmap-tick (PR #585 merged — Legacy Rainbow credential isolation resolved)
> **Earlier update:** 2026-07-14 post-roadmap-correction (PR #581 merged — R5B-A1 roadmap alignment, substantive body update)
> **Earlier update:** 2026-07-13 post-single-writer-containment (`HERMES_SINGLE_WRITER_GREEN`, PRs #564–#570 closed, enforced RepoWriterLock + IsolatedWorktree contract, no runtime mutation)

---

## 1. System posture

| Property | Value |
|----------|-------|
| Live trading | `TARGET_ARCHITECTURE_NOT_ENABLED` — live is a future mode, not currently active |
| Execution mode | Dry-run only |
| SI-v2 controller target | **AUTONOMOUS_DRY_RUN** — policy-gated, canary-first, allowlist-based |
| Current official C4 decision | **ROLLBACK_RECOMMENDED** (max_drawdown 82.79%, validated in all three calculation methods) |
| Canary state | **Stopped** — intentional baseline return after C4 ROLLBACK (#423 C4e) |
| Kill switch | **NORMAL** |
| Dry-run config | **Preserved** at `freqforge-canary/config/config_canary_dryrun.json` |
| Human approval | required for live-mode transition, not every dry-run candidate |
| Runtime mutation by this repo update | **NONE** |
| Active Hermes profile | `trading-hub-orchestrator` |
| Primary repo (read/write) | `/workspace/projects/trading-hub` (`/opt/data/projects/trading-hub` on host) |
| Secondary repo (read/write, cross-repo scope only) | `/workspace/projects/ai4trade-bot` |

### Rainbow Integration Status

| Task | Status | PR | Merge SHA |
|------|--------|----|-----------|
| R1 — Contract reconciliation | ✅ COMPLETED | #497 | `8c167c8` |
| R2 — Read-only provider | ✅ COMPLETED | #498 | `dc15f6d` |
| R3 — Attribution producer | ✅ COMPLETED | #499 | `4ec1b18` |
| R4 — Window-scoped C4 fix | ✅ COMPLETED | #500 | `a70a058` |
| R5 — Runtime preflight audit | ✅ COMPLETED | #502 | `78979a7` |
| R6 — Candidate quality | ✅ COMPLETED | #501 | `75384e1` |
| R7A — Greenfield Compose + Rainbow Runtime | ✅ COMPLETED | #524 | `ee767a10` |
| R7 — Dry-run measurement | ⏳ BLOCKED | — | — |
| R7 Track 1 — ai4trade-bot #105 Shadow Validation | ⏳ BLOCKED | — | — |
| R7 Track 2 — trading-hub #496 Attributed Measurement | ⏳ BLOCKED | — | — |

### Historical note

The previous human-gated phase (`HUMAN_GATED_CANARY_APPLY_PHASE_3C`) was a necessary historical step that proved the controlled apply chain. It is superseded for dry-run by ADR-2026-07-01 (Autonomous Dry-Run Loop with Live-Target Architecture).

---

## 2. SI-v2 Architecture (Complete Chain)

The following modules exist on `main` and form the complete controlled apply chain:

| Phase | Module | PR | Tests | Status |
|-------|--------|----|-------|--------|
| 3B-A | `restart_with_overlay.py` | #379 | 45 | ✅ |
| 3B-B | `restart_gate.py` | #380 | 23 | ✅ |
| 3C-A | `runtime_executor.py` | #381 | 23 | ✅ |
| 4A | `measurement/decision_engine.py` | #382 | 37 | ✅ |
| 5A | `rollback_rehearsal.py` | #383 | 24 | ✅ |
| 6A | `pipeline/candidate_to_apply.py` | #384 | 36 | ✅ |
| **Autonomy Policy** | `autonomy/autonomy_policy.py` | **NEW** | **NEW** | ✅ |
| **10.1 Resolver** | `fleet_rollout_input_resolver.py` | #421 | 24 | ✅ |
| **10.2 Evidence Runner** | `fleet_rollout_ready_evidence_runner.py` | #422 | 12 | ✅ |
| **10.3 Dry-Run Executor** | `fleet_dry_run_runtime_executor.py` | #424 | 18 | ✅ |
| **10.4 Post-Fleet Measurement** | `fleet_post_fleet_measurement_watcher.py` | #425 | 20 | ✅ |
| **Rainbow R1** | Contract reconciliation | #497 | + | ✅ |
| **Rainbow R2** | Read-only provider | #498 | + | ✅ |
| **Rainbow R3** | Attribution producer | #499 | + | ✅ |
| **Rainbow R4** | Window-scoped C4 fix | #500 | + | ✅ |
| **Rainbow R5** | Runtime preflight audit | #502 | + | ✅ |
| **Rainbow R6** | Candidate quality | #501 | + | ✅ |
| **Rainbow R7A** | Greenfield Compose + Rainbow Runtime | #524 | + | ✅ |
| **Total** | **17 modules** | **17 PRs** | **+ tests** | **All GREEN** |

### Active bot identities

| Bot id | Role | Current state |
|--------|------|---------------|
| `freqtrade-freqforge` | FreqForge baseline/override | **Not running** — requires explicit approval to restart |
| `freqtrade-freqforge-canary` | FreqForge canary | **Stopped** — intentional baseline return after C4 ROLLBACK |
| `freqtrade-regime-hybrid` | Regime-hybrid | **Not running** — requires explicit approval to restart |
| `freqai-rebel` | FreqAI/Rebel | **Not running** — requires explicit approval to restart |

Momentum is decommissioned and MVS is not deployed. They are historical context only.

---

## 3. Measurement Status

| Point | Time | Status |
|-------|------|--------|
| **T0** | 2026-06-27T18:27Z | ✅ **GREEN** |
| **T1** | 2026-06-27T19:27Z | 🟡 **YELLOW / CONTINUE** — Bitget 429 warnings |
| **T2** | 2026-06-28T00:27Z | 🟡 **YELLOW / CONTINUE** — Bitget 429 warnings, 0 new trades |
| **T3** | 2026-06-28T18:27Z | 🟡 **YELLOW / EXTEND_MEASUREMENT** — Bitget 429, Kill Switch HALT_NEW compromised window |
| **T4 Readiness** | 2026-06-30 | ⏳ **NOT_ENOUGH_DATA** — 0 new closed canary trades since T3 |
| **T4 Follow-up** | 2026-06-30 | ⏳ **STILL_NOT_ENOUGH_DATA** — UNI/USDT still open, no change since T4 Readiness |
| **C4 Final Decision** | 2026-06-30 | 🟡 **ROLLBACK_RECOMMENDED** — max_drawdown 82.79% breach |

### Why ROLLBACK_RECOMMENDED

- **Kill Switch was HALT_NEW** from T1 through most of the measurement window (2026-06-27T19:27Z to 2026-06-29T04:15Z), blocking ALL new trades fleet-wide
- Only 1 new canary trade (UNI/USDT, still open) and 3 new control trades (BTC open, ETH/SOL closed with losses) since T0
- Insufficient trade data for a meaningful canary-vs-control comparison
- Max drawdown 82.79% breached critical threshold in all three calculation methods
- Baseline return executed, canary container stopped, incident report filed

---

## 4. Operational priority for agents

### Active priority: Autonomous roadmap loop (H1 → H2 → H3A → H3B → R5A ✅ → R5B-A1 ✅)

**Current state: R5A COMPLETE (PR #560, merge `80f9733`, Issue #527 closed with R5A_PARITY_GREEN). R5B-A1 PLANNING COMPLETE (PR #575 merged).**

The canonical HermesTrader dry-run fleet is persistently deployed and parity-proven (5/5 health, `dry_run=true` validated, Rainbow read-only, kill-switch cycle proven, secret scan clean). ai4trade runtime is locked to `6e850c8f8ba1d8a0ad45250f130280e4171c001d`.

**Next Hermes action:** R5B canonical dry-run cutover Gate 1 (A2). Issue #580 is the active next R5B A2 preflight decision. **Gate 1 is BLOCKED/NOT APPROVABLE** per fresh agent0 evidence (PR #588, merge `6e29263`). Agent0 `trading-freqai-rebel-1` is RUNNING (Up 4 days) with a shared rw mount of the fleet-wide kill switch — a canonical-role-only freeze is impossible. Luke must select one of three decision paths before any `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE` marker may be issued. R5B planning documented in PR #575 / `docs/reports/r5b-cutover-gate-planning-2026-07-13.md` (A1); no data migration and no runtime action.

**Issue #561:** SUPERSEDED/CLOSED — R5B planning complete, superseded by #580 for Gate 1 preflight.

**Blocked pending action (after R5B):**
- R6 — Permanent reconciliation (systemd)
- R7 / Issue #496 — Rainbow dry-run measurement

**Do NOT start** without explicit approval:
- new apply
- restart
- rollback
- pair expansion
- live readiness
- next candidate research
- canary redeployment
- Rainbow producer start
- R7 measurement
- **R5B execution / agent0 mutation** (requires separate `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE` marker; Gate 1 is currently BLOCKED per Issue #580 — 0 remaining UNVERIFIED items; both freqai-rebel config and Legacy Rainbow credential isolation RESOLVED PASS)
- Docker/Compose mutation

**Allowed:**
- read-only audits and reports
- documentation updates
- A1 repository-only roadmap tasks (branch, code/docs/tests, PR, CI, merge)
- A2 dry-run runtime only with full approval gates

### Next runtime action
**Requires explicit human approval.** No runtime action is currently authorized. The following are all blocked:

- Canary dry-run redeploy → human approval + ceremony
- Rainbow producer start → human approval
- Freqtrade bot restart → human approval
- C4 re-execution → new measurement window + human gate
- D1/D2 live rollout → C4 KEEP + `APPROVED_LIVE_FLEET_ROLLOUT`
- R7 measurement → R5B execution + R6 reconciliation + immutable runtime promotion (`30e5ebe`, image digest, smoke gate) approved
- H3B root-executor client activation → **CLOSED — `H3B_RUNTIME_CONTROL_GREEN`** (PR #559 squash-merged 2026-07-13). Host daemon is healthy, dual-protocol, and reachable from Hermes.
- R5A HermesTrader deployment → **COMPLETE and `R5A_PARITY_GREEN`** (PR #560 merged at `80f9733`, Issue #527 closed). Canonical dry-run fleet deployed with 5/5 parity; Rainbow storage fixed; kill-switch provisioned. ai4trade locked to `6e850c8`.
- R5B canonical cutover gate → **Planning COMPLETE (A1)**. No data migration; rebel and `rainbow-live-*` are non-canonical legacy workloads requiring read-only isolation evidence. Execution requires A2 approval (Gate 1: legacy preflight and reversible freeze). **Gate 1 is BLOCKED** per Issue #580 — requires Luke's explicit `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE` marker with command allowlist, UTC time bounds (max 24h), fail-closed rules, and reversible kill-switch-only rollback. No runtime mutation.

### Kill Switch — Fleet-Wide Impact

**The kill switch at `freqtrade/shared/kill_switch.py` is fleet-wide.** Its modes (`NORMAL`, `HALT_NEW`, `EMERGENCY`) apply to ALL four canonical SI-v2 bots simultaneously:

- `freqtrade-freqforge`
- `freqtrade-freqforge-canary`
- `freqtrade-regime-hybrid`
- `freqai-rebel`

There is no role-scoped or bot-scoped freeze in the current architecture. A `HALT_NEW` or `EMERGENCY` mode blocks new entries fleet-wide across all four bots. If role-scoped freeze behavior is desired, it requires a separate architecture decision, implementation, and approval — it does not exist today.

### freqai-rebel — Gate 1 Status

**Rebel config status RESOLVED (PASS)** — read-only evidence investigation (2026-07-14) confirmed:
- `dry_run: true` enforced at config level (`freqtrade/bots/freqai-rebel/user_data/config.example.json`)
- No valid exchange credentials in repo (placeholders only: `CHANGE_ME_LOCAL_ONLY_KEY` / `CHANGE_ME_LOCAL_ONLY_SECRET`)
- Profile-gated in HermesTrader compose (`profiles: ["rebel"]`) — not part of default stack
- R3 classified `NOT_REPRODUCIBLE` (1.2 GB trained FreqAI models not in repo; FreqAI deps + `directory_operations.py` patch missing; base unpinned)
- **No running container on HermesTrader**
- Full evidence: Issue #580 comment 2026-07-14

**SAFETY CORRECTION 2026-07-14 — Agent0 Rebel is RUNNING:** Fresh read-only evidence (2026-07-14) proves `trading-freqai-rebel-1` is RUNNING on agent0 (`Up 4 days`). All four agent0 trading containers (`trading-freqtrade-freqforge-1`, `trading-freqtrade-freqforge-canary-1`, `trading-freqtrade-regime-hybrid-1`, `trading-freqai-rebel-1`) mount the same host directory `/home/hermes/projects/trading/freqtrade/shared` to `/freqtrade/shared` with `rw=true`. The shared kill-switch file at that mount reports `mode=NORMAL`. The kill switch at `freqtrade/shared/kill_switch.py` is **fleet-wide** — no role-scoped or bot-scoped freeze exists.

**Consequence:** The planned Gate 1 freeze of "canonical agent0 roles only" is IMPOSSIBLE with the current kill-switch implementation. Setting `HALT_NEW` would affect the running Rebel bot on agent0, contradicting the Gate 1 boundary that Rebel is dormant/out-of-scope.

**Required Luke decision before any A2 marker:** Luke must explicitly select ONE of three paths:
1. **Fleet-wide freeze:** Include the running Rebel in the approved `HALT_NEW` impact scope for the bounded Gate 1 window; OR
2. **Scoped-freeze architecture:** Implement and prove a separate role-scoped/bot-scoped freeze mechanism before Gate 1. Repository architecture/code work is A1; any dry-run runtime rollout/test is separately A2-approved; A3/live remains prohibited and out of scope; OR
3. **Rebel lifecycle gate first:** Separately approve and execute a reversible Rebel stop/isolation gate before Gate 1, with its own evidence and rollback.

Until one path is explicitly selected and documented, no `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE` marker may be issued. Rebel remains start-prohibited for Gate 1. No rebel start, configuration, or runtime action is authorized for Gate 1 unless Luke explicitly decides otherwise in the Gate 1 approval marker.

**Critical lifecycle clarification:** The agent0 Rebel container `trading-freqai-rebel-1` is **already running**. It must not be stopped, restarted, or reconfigured except under an explicitly selected and separately approved decision path (Path 3 above). The Gate 1 boundary does not mean the running Rebel is merely "start-prohibited" — it is actively running and must not be disturbed unless Luke explicitly selects and documents Path 3 with its own evidence, approval, and rollback plan.

---

**R5B Gate 1 (Issue #580) — BLOCKED:** Preflight evidence showed **0 remaining `UNVERIFIED` items** for the original credential/config questions (both freqai-rebel config and Legacy Rainbow credential isolation RESOLVED PASS). **HOWEVER**, fresh agent0 evidence proves a separate execution-contract contradiction: the running agent0 Rebel shares the fleet-wide kill switch, making the planned canonical-role-only freeze impossible. Gate 1 remains BLOCKED/NOT APPROVABLE pending Luke's explicit decision among the three paths above. No role-scoped freeze exists in current architecture. R6/R7 remain blocked; runtime_mutation=NONE.
**R7 track split (Issue #423 / #423 Track R7):**
- **ai4trade-bot #105** — Shadow validation (read-only evidence collection)
- **trading-hub #496** — Attributed dry-run trading measurement (Rainbow R7)
- Minimum 14-day shadow boundary before any attribution or measurement use.
- Both tracks remain BLOCKED pending R5B + R6 + immutable promotion approval.

---

## 5. Safety layer status

| Component | Current status |
|-----------|----------------|
| Dry-run posture | ✅ Required for all active bots |
| Live trading | `TARGET_ARCHITECTURE_NOT_ENABLED` |
| RiskGuard | Required for trading-affecting decisions; currently PASS |
| Kill switch | **NORMAL** (set 2026-06-29T04:15Z, approved by Luke) |
| Apply path | Policy-gated autonomous dry-run (AUTONOMOUS_DRY_RUN mode) |
| Restart path | Canary-only, L3-token-gated via runtime executor |
| Rollback path | Rehearsed but execution hard-blocked |
| Measurement path | Read-only decision engine on `main` |
| Rainbow advisory | Read-only, fail-closed, disabled by default |
| Root Executor | 🟢 **Reachable and fully proven from Hermes** — `hermes-root-executor.service` active/running (`root:hermes` permissions since the 2026-07-13 systemd fix); complete Issue #531 proof matrix passes 5/5 (positive v1, all read-only actions, full security matrix, audit correlation); secret exposure contained and credential rotation human-attested (`COMPROMISED_GITHUB_PAT_REVOKED_AND_REPLACED`, `confirmed_by=Luke`) |
| Autonomous roadmap loop | Contract defined in `AGENTS.md` and `commands/trading-hub-roadmap-tick.md` |

---

## 6. Architecture decisions

| ADR | Status | Summary |
|-----|--------|---------|
| ADR-2026-06-10-watchdog-ownership | Active | Watchdog ownership and lifecycle |
| ADR-2026-06-27-controlled-self-improvement-human-gated-apply | **Superseded for dry-run** | Human-gated apply (historical) |
| ADR-2026-06-27-si-v2-restart-with-overlay-runtime-proof | Active | Restart-with-overlay runtime proof |
| ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target | **Active** | Policy-gated autonomous dry-run, live as target architecture |
| ADR-2026-07-11-hermes-root-runtime-authority | **Active** | Hermes Root-Runtime-Authority (R0): UID-separated root executor supersedes D1/D2/D3 narrow-slice access; live trading stays externally signature-gated |
| ADR-2026-07-12-hermes-autonomous-repository-loop | **Active** | Autonomous repository loop contract: source-of-truth order, execution classes A0–A3, session algorithm, audit closure |

### Access model (current)

- **Previous model (SEC-1, superseded as primary path):** Hermes had no
  `docker.sock`; access was limited to a read-only Docker proxy (D1), a
  fixed-command allowlisted host runner (D2), and an audited operator bridge
  (D3).
- **Current model (R0 governance-decided; executor shipped in R1, PR #508, active):** Hermes stays unprivileged (UID 10000). A dedicated
  `hermes-root-executor.service` (UID 0) provides full host/Docker runtime
  authority over HermesTrader, reachable only via a local Unix socket with
  peer-credential (`SO_PEERCRED`) authentication, exclusive locks, command
  timeouts, full audit logging, secret redaction, and a kill switch. See
  [`docs/decisions/ADR-2026-07-11-hermes-root-runtime-authority.md`](../decisions/ADR-2026-07-11-hermes-root-runtime-authority.md)
  for the full decision, including the External Live Authority Boundary
  (root authority ≠ live-trading authority; live actions require an
  externally signed, time-limited approval whose private key never resides
  on HermesTrader).
- D1/D2/D3 are not deleted and may keep running as a fallback path during
  the R1–R2 transition; they are superseded as the primary access path.
- **Bot fleet location is unchanged by this decision:** all four active bots
  (`freqtrade-freqforge`, `freqtrade-freqforge-canary`,
  `freqtrade-regime-hybrid`, `freqai-rebel`) continue to run exclusively on
  the old `agent0` VPS. Migrating them to HermesTrader is a later step
  (Root-Runtime-Roadmap phases R3–R5b) and is explicitly out of scope for
  this decision.

---

## 7. Documentation ownership

- `AGENTS.md` — primary operational agent instruction.
- `SOUL.md` — stable project identity and non-negotiable safety principles.
- `CLAUDE.md` — thin Claude Code handoff that defers to `AGENTS.md`.
- `ORCHESTRATOR_CHARTER.md` — durable charter rules.
- `README.md` — repository orientation.
- `commands/trading-hub-roadmap-tick.md` — bounded autonomous roadmap iteration command.
- `docs/state/current-operational-state.md` — this canonical state snapshot.
- `docs/reports/si-v2-phase-*` — phase-specific evidence reports.
- `docs/decisions/ADR-*` — architecture decision records.
- `docs/reports/rainbow-r*-*-2026-07-10.md` — Rainbow R1–R6 reports.
- `docs/reports/rainbow-r5-runtime-preflight-reconciliation-2026-07-11.md` — R5 reconciliation report.
- `docs/reports/hermes-orchestrator-governance-reconciliation-2026-07-12.md` — H1 governance reconciliation report.

---

## C1 planning note (2026-07-09)

- Repository HEAD at C1 planning: `c897c01` (main). Source snapshot referenced elsewhere: `20aee88`.
- Post-snapshot security hardening includes #475 (raw docker socket removed from hermes-green) and #476 (SEC-2 partial fix).
- **Runtime posture remains `AUTONOMOUS_DRY_RUN`** — no fresh runtime measurement performed in C1; runtime re-baseline is a separate, explicitly-gated step (Phase F).
- Workspace bridge (Phase C1A): HermesTrader Hermes container sees this repo at `/workspace/projects/trading-hub` (now read/write); host path `/opt/data/projects/trading-hub`.

## Rainbow R5 reconciliation note (2026-07-11)

- R5 reopened and reconciled against #423.
- C4 decision corrected to `ROLLBACK_RECOMMENDED`.
- Canary state corrected to `Stopped` (intentional baseline return).
- Fleet state corrected: no bots currently running.
- Rainbow producer: UNAVAILABLE (not running).
- All runtime actions mapped to explicit human approval requirements.
- R7 remains blocked pending runtime preflight approval.
- D1/D2 remain blocked per #423.

---

## Root-Runtime Roadmap Status (H1 update, 2026-07-12)

> Supersedes prior R3 update. Reflects merged R7A/R4 via PR #524 and
> H1 governance reconciliation via #525.

| Phase | Status | PR |
|---|---|---|
| R0 — Governance / Root-Authority | COMPLETE | #506 |
| R0.5 — Secret Exposure Architecture Closure | COMPLETE | #507 |
| R1 — Root Executor Service | COMPLETE (shipped + active) | #508 |
| R2 — Audit, Locking, Mutation Evidence | COMPLETE | #509 |
| R3 — Fleet Reproducibility Decision | COMPLETE | (R3 PR) |
| R4 / R7A — Greenfield Compose + Rainbow Runtime | ✅ COMPLETE | #524 (`ee767a10`) |
| H1 — Governance Reconciliation | ✅ COMPLETE | #525 (`408f035`) |
| H2 — Autonomous Roadmap Tick | ✅ COMPLETE | #529 (`f5f36ff`) |
| H3A — Root-Executor Client Contract | ✅ COMPLETE | #533 (`38203a7`) |
| H3B — Root-Executor Client Activation | 🟢 **H3B_RUNTIME_CONTROL_GREEN** (PR #559 squash-merged 2026-07-13; complete Issue #531 proof matrix passes 5/5; secret exposure contained; credential rotation human-attested) | #531 → #549, #550, #551, #553, #554, #555, #557, #558, #559 |
| R5a — HermesTrader Deployment | ✅ COMPLETE (PR #560, `80f9733`, 5/5 parity) | #527 → #560 |
| R5b — agent0 Cutover | BLOCKED (separate Luke approval) | — |
| **R5B Gate 1 Preflight (Issue #580)** | **BLOCKED (A2 approval required)** — 0 remaining UNVERIFIED items; both freqai-rebel config and Legacy Rainbow credential isolation RESOLVED PASS | — |
| R6 — Permanent Reconciliation (systemd) | — | — |
| R7 — SI-v2 Runtime Integration (shadow) | — | — |
| C5 — New Dry-Run Canary Measurement Window | — (replaces C4 ROLLBACK_RECOMMENDED) | — |
| Rainbow R7 / #496 | BLOCKED | — |

### R3 Fleet Decision

- `SELECTED_FLEET_MODEL = OPTION_C`
- `CANONICAL_MEASUREMENT_FLEET = [freqforge, regime-hybrid, canary]` (+ webserver support)
- rebel = `NOT_REPRODUCIBLE` (1.2 GB trained FreqAI models not in repo; FreqAI deps + `directory_operations.py` patch missing; base unpinned).
- freqforge / canary / regime-hybrid = `REPRODUCIBLE_NOW` (verified via greenfield test build from `Dockerfile.hermes10000` + repo strategies + `freqtrade/shared/` modules).
- Full evidence: `docs/reports/r3-fleet-reproducibility-decision-2026-07-11.md`.

### D1/D2 Naming (collision clarified)

- **SEC-1 access paths D1/D2/D3** (Docker-proxy / fixed-command-runner / bridge): `SUPERSEDED_AS_PRIMARY_PATH` by the root-executor (R0/R1); retirement pending. NOT deleted.
- **Live-Roadmap Track D1/D2** (Live Fleet Approval / Rollout): `BLOCKED_BY_C4_KEEP_AND_EXTERNAL_LIVE_APPROVAL`. NOT superseded by the root-executor — these are live-trading gates.

### Bot-Runtime State Discrepancy (flagged, NOT resolved in R3)

R3 live verification (2026-07-11) found the three canonical roles, the non-canonical rebel,
and the webserver **running** in dry-run on agent0 (freqforge Up/healthy, canary Up, regime-hybrid Up, rebel Up 40h, webserver Up 8d).
This **contradicts** the prior snapshot above ("no bots currently running" / all "Not running —
requires explicit approval to restart"). The discrepancy's cause (approved restart vs.
auto-restart vs. unauthorized) is **not investigated in R3** — flagged for separate governance
review. R3 did not mutate any runtime state.

### R7 Track Split (2026-07-14)

> R7 is split into two distinct tracks with separate evidence boundaries and issue ownership.

| Track | Repository | Issue | Focus | Evidence Boundary |
|---|---|---|---|---|
| **R7 Track 1 — Shadow Validation** | ai4trade-bot | #105 | Read-only shadow evidence collection; no attribution | ai4trade-bot evidence bundles |
| **R7 Track 2 — Attributed Dry-Run Measurement** | trading-hub | #496 | Attributed dry-run trading measurement; Rainbow attribution producer | trading-hub measurement window + Rainbow evidence |

**Minimum 14-day shadow boundary** before any attribution or measurement use in either track.

**Both tracks remain BLOCKED** pending:
1. R5B execution + R6 reconciliation complete
2. Immutable ai4trade runtime promotion approved (full commit SHA `30e5ebecaa8b0d3170349311f7a9964fa710d8bf`, OCI digest, smoke gate)
3. Rollback baseline confirmed (full commit SHA `6e850c8f8ba1d8a0ad45250f130280e4171c001d`)

---

## H1 Governance Reconciliation note (2026-07-12)

> Completed as part of Issue #525. This section supersedes the prior
> R7A/R4 reconciliation note below.

- Profile corrected to `trading-hub-orchestrator` in `AGENTS.md` and `SOUL.md`.
- Primary repository workspace corrected to read/write.
- Secondary repository `ai4trade-bot` documented with explicit cross-repo scope.
- Root Executor R1 corrected to shipped and active (was "not yet shipped").
- R4 / R7A marked COMPLETE via PR #524 (`ee767a10`).
- Source-of-truth order, execution classes A0–A3, and autonomous session
  algorithm defined in `AGENTS.md`.
- `commands/trading-hub-roadmap-tick.md` created for bounded autonomous
  iterations.
- ADR-2026-07-12-hermes-autonomous-repository-loop.md created.
- All stale claims removed: no more "workspace read-only", "profile orchestrator",
  "R1 not shipped", "R4 NEXT".

---

## R7A / Root-Runtime R4 reconciliation note (2026-07-11 — superseded by H1 above)

> **Roadmap-Mapping:** Root-Runtime Roadmap
> `R4 — Greenfield Compose + Rainbow Runtime`
> entspricht `R7A` / Issue #504.
>
> PR #519 ist der Docs-only-Architektur-PR (PR-1).
> Compose, Rainbow-Wiring und Tests wurden in PR #524 (PR-2) eingeführt.
> Merge-SHA: `ee767a10ca7cae09485755101048b2ea0f4b5e06`.

- Der durch R3 dokumentierte Runtime-Widerspruch bleibt offen:
  Vier Freqtrade-Bots und der Webserver wurden auf agent0 im Dry-Run
  als laufend verifiziert, während ältere State-Abschnitte sie als
  gestoppt beziehungsweise nicht laufend ausweisen.
- `docker-compose.hermestrader-dryrun.yml` ist die beschlossene
  kanonische Zieldatei und wurde durch PR #524 angelegt.
- `freqai-rebel` bleibt wegen `NOT_REPRODUCIBLE` aus dem
  Greenfield-Default-Deploy ausgeschlossen und wird nur über
  `profiles: ["rebel"]` aktiviert.
- R5a / HermesTrader-Deployment bleibt bis
  `APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT`,
  `BACKUP_GATE_GREEN` und expliziter User-Freigabe blockiert.
- Live-Fleet-Rollout bleibt blockiert, solange die aktuelle
  C4-Entscheidung `ROLLBACK_RECOMMENDED` gilt.
  Eine Freigabe erfordert eine neue C4-Entscheidung `KEEP`
  sowie `APPROVED_LIVE_FLEET_ROLLOUT`.
- Diese Dokumentationsänderung führt keine Runtime- oder Host-Mutation aus.

---

## R5A Dry-Run Fleet — Deployed and Parity-Green (2026-07-13)

The canonical HermesTrader dry-run fleet (Issue #527, PR #560) is persistently
deployed and has passed full 5/5 dry-run parity.

- **Services (all healthy):** `freqforge`, `freqforge-canary`, `regime-hybrid`,
  `webserver` (Freqtrade, all `dry_run=true`) and `rainbow` (advisory,
  read-only/fail-closed). `freqai-rebel` remains profile-gated and excluded.
- **Rainbow storage fix:** the read-only-database startup crash was caused by a
  `999:999`-owned storage volume against a `10000:10000` container. Fixed by
  ai4trade-bot@`6e850c8` (#102): image now `Config.User=10000:10000` and bakes
  an empty 10000-owned `storage/`. Build pinned via
  `ops/ai4trade-rainbow.lock.yml` (immutable checkout of the locked SHA, not a
  moving branch). Only `hermestrader-dryrun_rainbow-storage` was recreated; no
  other volume touched; no `down -v`/prune.
- **Kill switch:** now provisioned at NORMAL (git-ignored
  `freqtrade/shared/kill_switch.json`); it had been fail-closed to HALT_NEW due
  to a missing state file on a read-only mount. HALT_NEW -> NORMAL cycle
  verified across the three canonical roles and the non-canonical rebel.
- **Safety posture:** loopback/internal-only exposure, internal/egress network
  split preserved, DB/WAL owned by UID 10000, Bitget market-data egress works,
  restart/persistence and non-destructive rollback rehearsed, secret scan clean
  (Main Gate green), agent0 untouched.
- **Rollback point:** Restic snapshot `252e9711` (parent `ff6b7dbc`).
- **Measurement gate #496** remains blocked pending its own separate
  prerequisites; R5A proves only the persistent dry-run deployment and parity.

---

## Post-R5A Hermes Orchestrator Reconciliation (2026-07-13)

Post-R5A source-of-truth reconciliation. No runtime mutation (A1 only).

- **Main HEAD:** `80f9733e1cbba9f2408852edfd4741f4188ccf8b` (PR #560 squash-merge)
- **Issue #527:** CLOSED with `R5A_PARITY_GREEN`
- **ai4trade lock:** `6e850c8f8ba1d8a0ad45250f130280e4171c001d` (Rainbow storage-ownership fix #102)
- **Fleet:** 5/5 healthy, persistent dry-run on HermesTrader
- **Roadmap ownership:** Hermes restored as sole orchestrator
- **Cron:** No active or planned Roadmap Cron jobs were observed. Do not create or reactivate one until the separate `/proposals/` fix and active skills-profile manifest are complete.
- **Next sequence:** R5B canonical cutover gate → R6 canonical-fleet reconciliation → immutable runtime promotion → R7/#496 measurement
- **C4:** `ROLLBACK_RECOMMENDED` preserved
- **D1/D2:** Blocked (C4 KEEP + `APPROVED_LIVE_FLEET_ROLLOUT` required)
- **Cross-repo drift (recorded, not deployed):** ai4trade-bot `master` has newer commits beyond `6e850c8`. Lock remains at `6e850c8`; moving branch not pulled.
- **R5B issue:** Created as `[Root-Runtime][R5b] HermesTrader cutover gate and agent0 retirement plan` — inventory/plan/evidence only until A2 approval
- **R5B planning:** COMPLETE — canonical three-role cutover plan documented in `docs/reports/r5b-cutover-gate-planning-2026-07-13.md` (A1); no data migration and no runtime action
- Full report: `docs/reports/post-r5a-hermes-orchestrator-reconciliation-2026-07-13.md`

## Hermes Orchestrator Gateway Restore (2026-07-13)

`HERMES_ORCHESTRATOR_GATEWAY_GREEN` — native Hermes gateway for the
`trading-hub-orchestrator` profile is back online. The pre-existing
s6-supervised service slot at `/run/service/gateway-trading-hub-orchestrator`
was brought up with a single `s6-svc -u` invocation (no new service, no
new systemd unit, no Docker change, no runtime mutation). The cron
job `f18cbcdb56b7` (`trading-hub-roadmap-tick`, `*/30 * * * *`,
`ollama-cloud/nemotron-3-ultra`, workdir `/workspace/projects/trading-hub`)
is now visible to a running dispatcher and will fire automatically on
schedule. Gateway PID 17842 is s6-supervised (parent `s6-supervise
gateway-trading-hub-orchestrator`, PID 152), runs as UID 10000 (user
`hermes`), and the argv contains no secrets/tokens/passwords. The
pre-existing `default`-profile gateway (PID 153) was left alone — it
serves a different profile and has no conflict (no shared port, no
shared cron queue, no shared state). The validation tick confirmed
Issue #561 (R5B) as the next unblocked task and classified it A1
(planning only). R5B work is **out of scope** for this restore; it
begins in a separate future tick.

- Approval marker: `APPROVED_HERMES_ORCHESTRATOR_GATEWAY_RESTORE` (`confirmed_by=Luke`, `scope=HERMES_NATIVE_GATEWAY_ONLY`)
- Cron job: `f18cbcdb56b7` (unchanged)
- Provider/model: `ollama-cloud` / `nemotron-3-ultra` (unchanged)
- Workdir: `/workspace/projects/trading-hub` (unchanged)
- Duplicate jobs: 0
- Runtime mutation: NONE
- Full report: `docs/reports/hermes-orchestrator-gateway-restore-2026-07-13.md`

## Hermes Concurrent-Writer Incident and Recovery (2026-07-13)

**`HERMES_SINGLE_WRITER_GREEN`** — containment of a concurrent-writer
incident where the `trading-hub-roadmap-tick` cron job fan-contaminated
the repository with 7 parallel `docs/debug/*` branches and PRs (#564–#570)
in 12 minutes (2026-07-13 19:24–35 UTC). All 7 PRs included the same
R5B cutover-gate planning report (fan-out contamination).

### Containment actions (completed)

- Cron `f18cbcdb56b7`: **paused** (gateway still running, no active jobs)
- PRs #564–#570: **closed** with `INVALIDATED_BY_CONCURRENT_WORKTREE_CONTAMINATION`; no merge, no cherry-pick
- Embedded PAT in `.git/logs/HEAD` (4 entries): **redacted** (file-level, not history rewrite)
- Remote URLs: **confirmed clean** (both `trading-hub` and `ai4trade-bot`); credential helper `!gh auth git-credential` configured
- Shared canonical checkout: **preserved without reset/clean** (local `main` at `aa0e769`; new work is in isolated worktrees from `origin/main`)
- `COMPROMISED_GITHUB_PAT_REVOKED_AND_REPLACED`: **⏳ REQUIRED** before cron resume. Token in `/opt/data/.config/gh/hosts.yml` must be revoked and replaced.

### New single-writer enforcement (`ops/hermes-single-writer-recovery`)

- `orchestrator/scripts/repo_writer.py` — `RepoWriterLock` (global non-blocking `fcntl.flock`) + `IsolatedWorktree` (per-run worktree from pinned `origin/main` SHA)
- `tests/test_repo_writer.py` — 31 tests, all passing
- `commands/trading-hub-roadmap-tick.md` — updated with mandatory "Repository writer contract" section
- `AGENTS.md` — new "Repository writer contract" section
- `docs/state/current-operational-state.md` — this section

### Post-merge: resume cron

After credential rotation confirmed + this PR merged:

```bash
hermes -p trading-hub-orchestrator cron resume f18cbcdb56b7
```

- Full report: `docs/reports/hermes-concurrent-writer-incident-and-recovery-2026-07-13.md`
- Approval markers: `APPROVED_HERMES_AUTONOMY_CONTAINMENT`, `APPROVED_PAUSE_TRADING_HUB_ROADMAP_TICK`, `APPROVED_CLOSE_CONTAMINATED_PRS_564_570`
- Runtime mutation: NONE
