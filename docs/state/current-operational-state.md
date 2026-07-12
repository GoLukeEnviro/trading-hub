# Trading Hub — Current Operational State

> **Canonical current-state snapshot** — validated against `main` at
> PR #523 (chore cleanup merge), H3B remains blocked.
>
> **Last updated:** 2026-07-12 after PR #523 merge (chore cleanup)
> **Previous update:** 2026-07-12 after PR #542 merge (state header reconciliation)

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

### Active priority: Autonomous roadmap loop (H1 → H2 → H3A → H3B → R5A)

Current task: **H3B — Root-Executor Client Activation (#531)** — BLOCKED (needs APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION).

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
- R7 measurement → R5A complete + runtime preflight approved
- H3B root-executor client activation → H3A merge + APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION
- R5A HermesTrader deployment → H3B_RUNTIME_CONTROL_GREEN + APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT

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
| Root Executor | `hermes-root-executor.service` shipped and active (PR #508, R1) |
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
| H3A — Root-Executor Client Contract | ✅ COMPLETE | #530 (`38203a7`) |
| H3B — Root-Executor Client Activation | ⬜ BLOCKED (needs APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION) | #531 |
| R5a — HermesTrader Deployment | BLOCKED (needs APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT) | — |
| R5b — agent0 Cutover | BLOCKED (separate Luke approval) | — |
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

R3 live verification (2026-07-11) found all 4 bots + webserver **running** in dry-run on
agent0 (freqforge Up/healthy, canary Up, regime-hybrid Up, rebel Up 40h, webserver Up 8d).
This **contradicts** the prior snapshot above ("no bots currently running" / all "Not running —
requires explicit approval to restart"). The discrepancy's cause (approved restart vs.
auto-restart vs. unauthorized) is **not investigated in R3** — flagged for separate governance
review. R3 did not mutate any runtime state.

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
