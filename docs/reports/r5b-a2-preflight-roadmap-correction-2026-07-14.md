# R5B A2 Preflight Roadmap Correction — 2026-07-14

**Execution class:** A1 (repository-only)  
**Runtime mutation:** NONE  
**Source-of-truth reconciliation:** `AGENTS.md`, `SOUL.md`, `docs/state/current-operational-state.md`, Issue #423, Issue #580, open PRs  
**Branch:** `docs/r5b-a2-preflight-roadmap-alignment`  
**Base SHA:** `90ae5b9e75229a9b78f70f72e6c883549ca81809` (origin/main at task start)  
**Writer lock:** Acquired (session `r5b-preflight-20260714-001`)  
**Worktree:** `/opt/data/projects/trading-hub-worktrees/docs__r5b-a2-preflight-roadmap-alignment`

---

## 1. Executive Summary

This A1 documentation-only iteration reconciles the canonical operational state (`docs/state/current-operational-state.md`) with the actual current state of the repository, GitHub issues, and the live roadmap. It establishes Issue #580 as the active next R5B A2 preflight decision, marks R5B-A1 planning complete, and documents all Gate-1 blockers, approval boundaries, and roadmap sequencing. No runtime mutation occurs. No A2/A3 approval is granted or implied.

---

## 2. Source-of-Truth Reconciliation

### 2.1 Issue #423 (Roadmap Anchor) — Status Assessment

**Issue #423** remains the long-term live-gates anchor but its roadmap table has been superseded by completed work:

| Track | Task | Issue #423 Status | Actual Current Status |
|-------|------|-------------------|----------------------|
| R5A | HermesTrader Dry-Run Deployment | ✅ Done (claimed) | ✅ **VERIFIED COMPLETE** — PR #560 merged `80f9733`, Issue #527 closed `R5A_PARITY_GREEN` |
| R5B | Cutover Gate & agent0 Retirement | 🔜 Next | **PLANNING COMPLETE (A1)** — PR #575 merged; Gate 1 preflight is Issue #580 |
| R6 | Permanent Reconciliation (systemd) | ⬜ After R5B | **BLOCKED** — blocked by R5B execution + reconciliation |
| R7 | Rainbow Dry-Run Measurement | ⬜ Blocked | **SPLIT** — two tracks: ai4trade-bot #105 (shadow) + trading-hub #496 (attributed measurement) |
| D1 | Live Fleet Rollout Approval | ⬜ Blocked | **BLOCKED** — requires C4 KEEP + `APPROVED_LIVE_FLEET_ROLLOUT` (C4 was ROLLBACK_RECOMMENDED) |
| D2 | Live Fleet Staged Rollout | ⬜ Blocked | **BLOCKED** — requires D1 |

**Key stale claims in #423 corrected by this reconciliation:**
- "Next automatic Hermes action: R5B — Issue #561" → **Superseded**; #561 planning is complete; Gate 1 preflight is **Issue #580**
- "R7 — SI-v2 Runtime Integration (shadow)" → **Split into two tracks** with separate issue ownership
- "R5B planning COMPLETE" → **Correct**, but the Gate 1 execution gate is a separate A2 step (Issue #580)
- No mention of R5B Gate 1 `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE` marker requirements
- No mention of fleet-wide kill-switch impact or Rebel dormancy for Gate 1

### 2.2 Issue #561 — Status Update

Issue #561 (`[Root-Runtime][R5b] HermesTrader cutover gate and agent0 retirement plan`) was the A1 planning task. Its planning report was merged in **PR #575** (`docs/reports/r5b-cutover-gate-planning-2026-07-13.md`). Issue #561 is **superseded/closed for execution purposes**; the active next decision is **Issue #580**.

### 2.3 Issue #580 — Active R5B Gate 1 Preflight Decision

**Status:** `OPEN` / `BLOCKED` (not a request for execution)  
**Title:** `R5B A2 / Gate 1 - BLOCKED Preflight-Evidenz (kein Freigabeantrag)`

**Preflight results (read-only, no runtime action):**

| Area | Result | Notes |
|------|--------|-------|
| Primary Checkout | PASS | main, clean, HEAD `6fff2bc`, 3 behind origin/main |
| Roadmap Cron | PASS (caveat) | No active roadmap cron; dormant tick definition exists (paused) |
| Canonical Fleet | PASS | 5/5 running & healthy, restarts=0 |
| Kill Switch | PASS | mode=NORMAL |
| freqai-rebel Isolation | **UNVERIFIED** | Not running at runtime, but defined as non-canonical service in repo Compose; config status to be verified |
| Legacy Rainbow Isolation | **UNVERIFIED** | Volumes/networks/ports/delivery structurally separated (PASS). Credential separation not positively provable without value reading → fail-closed |

**Gate-1 Approval Contract (not yet issued):**

A future marker `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE` issued **exclusively by Luke** must contain:
- This issue reference (#580)
- Owner: Luke
- UTC start/end time (max 24h window)
- Explicit command allowlist
- Fail-closed and stop rules
- The sole permitted reversible action: kill-switch rollback (HALT_NEW → NORMAL)

**No such marker exists.** Without it, **no freeze, no agent0 mutation, no Docker/Compose mutation is authorized.**

---

## 3. Credential-Boundary Attestation Requirement

The Legacy Rainbow credential isolation finding (`UNVERIFIED`) requires a separate, dedicated evidence task to prove credential separation **without exposing any secret values, hashes of secrets, or credential paths**.

**Required evidence (read-only, no runtime mutation):**
- Structural proof: separate Docker networks, no shared writable volumes, no shared config source trees, no shared docker socket
- Credential source isolation: distinct secret injection paths per workload (e.g., distinct Docker secrets, distinct env file mounts, distinct vault paths)
- No cross-contamination in Compose definitions

**Scope and approval for this evidence task are separate** and must be explicitly granted. No secret values or hashes thereof may appear in any artifact.

---

## 4. freqai-rebel — Explicit Gate 1 Decision Requirement

**Current state (R3 decision, 2026-07-11):**
- `NOT_REPRODUCIBLE`: 1.2 GB trained FreqAI models not in repo; FreqAI deps + `directory_operations.py` patch missing; base image unpinned
- Defined as a non-canonical service in repo Compose (`profiles: ["rebel"]`)
- Not part of the canonical measurement fleet (`freqforge`, `regime-hybrid`, `canary` + webserver)

**Gate 1 disposition (this reconciliation):**
- **Rebel is dormant / out-of-scope / start-prohibited for Gate 1**
- No rebel start, configuration, or runtime action is authorized for Gate 1
- Luke must explicitly decide in the Gate 1 approval marker whether Rebel remains excluded or is included with a separate config-verification step

**Rationale:** Including a `NOT_REPRODUCIBLE` workload in a reversible freeze gate adds risk without measurement value. The canonical cutover targets the three reproducible roles plus webserver.

---

## 5. Kill Switch — Fleet-Wide Impact and Decision Fork

**Current implementation:** `freqtrade/shared/kill_switch.py` (file-based, git-ignored state at `freqtrade/shared/kill_switch.json`)

**Modes:** `NORMAL` | `HALT_NEW` | `EMERGENCY`

**Scope:** **FLEET-WIDE** — applies to ALL four canonical SI-v2 bots simultaneously:
1. `freqtrade-freqforge`
2. `freqtrade-freqforge-canary`
3. `freqtrade-regime-hybrid`
4. `freqai-rebel`

**There is no role-scoped or bot-scoped freeze in the current architecture.** A `HALT_NEW` or `EMERGENCY` mode blocks new entries across the entire fleet.

**Decision fork if role-scoped freeze is desired:**
1. **Architecture Decision Required** — new ADR defining scope, implementation, and safety boundaries
2. **Implementation** — modify `kill_switch.py` and all bot entry points to respect scope
3. **Testing** — prove role-scoped behavior in dry-run without affecting other bots
4. **Approval** — separate A2/A3 gate for the freeze behavior change

**This is NOT in scope for Gate 1.** Gate 1 uses the existing fleet-wide kill switch for its reversible freeze (HALT_NEW → NORMAL rollback only).

---

## 6. R5B Gates 1–4 Sequencing (Separate A2 Approval Per Gate)

| Gate | Focus | Approval Marker | Runtime Mutation |
|------|-------|-----------------|------------------|
| **Gate 1** (Issue #580) | Legacy preflight + reversible freeze (kill-switch only) | `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE` | Kill-switch HALT_NEW → NORMAL rollback only |
| **Gate 2** | Agent0 service stop + Compose cutover (3 roles + webserver) | `APPROVED_R5B_GATE_2_CUTOVER` | Docker Compose service migration |
| **Gate 3** | Legacy workload isolation verification (rebel, rainbow-live-*) | `APPROVED_R5B_GATE_3_LEGACY_ISOLATION` | Read-only verification; no mutation |
| **Gate 4** | Canonical fleet validation on HermesTrader + parity proof | `APPROVED_R5B_GATE_4_PARITY` | None (read-only validation) |

**Each gate requires a separate, explicit human approval marker.** No gate implies the next. The current blocked state is at **Gate 1**.

---

## 7. Root-Runtime R6 Acceptance Boundary

**R6 (Permanent Reconciliation / systemd)** is **blocked by R5B execution and reconciliation**. It cannot start until:
1. R5B Gates 1–4 complete
2. Canonical fleet is running on HermesTrader with parity proven
3. Agent0 retirement is verified

**R6 scope:** systemd unit installation, enablement, and persistence for the canonical fleet on HermesTrader. This is an A2 runtime action requiring its own approval marker.

---

## 8. ai4trade-bot Immutable Promotion — Full SHAs and Rollback Baseline

**Promotion target (immutable, by full commit SHA):**
- **Commit SHA:** `30e5ebecaa8b0d3170349311f7a9964fa710d8bf`
- **OCI Image Digest:** (to be recorded at promotion time via `docker inspect --format='{{.RepoDigests}}'`)
- **Smoke Gate:** Must pass Rainbow storage ownership, read-only advisory, and fail-closed verification

**Rollback baseline (immutable, by full commit SHA):**
- **Commit SHA:** `6e850c8f8ba1d8a0ad45250f130280e4171c001d`
- **OCI Image Digest:** (recorded at R5A deployment)
- **Current lock file:** `ops/ai4trade-rainbow.lock.yml` pins this baseline

**Promotion is a separate A2/A3 gate** — it requires:
- R5B execution complete
- R6 reconciliation complete
- Explicit approval for immutable runtime promotion with rollback capability

---

## 9. R7 Track Split — Two Distinct Tracks, Two Repositories, Two Issues

| Track | Repository | Issue | Focus | Evidence Boundary |
|-------|------------|-------|-------|-------------------|
| **R7 Track 1 — Shadow Validation** | ai4trade-bot | #105 | Read-only shadow evidence collection; no attribution | ai4trade-bot evidence bundles |
| **R7 Track 2 — Attributed Dry-Run Measurement** | trading-hub | #496 | Attributed dry-run trading measurement; Rainbow attribution producer | trading-hub measurement window + Rainbow evidence |

**Minimum 14-day shadow boundary** before any attribution or measurement use in either track.

**Both tracks remain BLOCKED** pending:
1. R5B execution + R6 reconciliation complete
2. Immutable ai4trade runtime promotion approved (full commit SHA `30e5ebecaa8b0d3170349311f7a9964fa710d8bf`, OCI digest, smoke gate)
3. Rollback baseline confirmed (full commit SHA `6e850c8f8ba1d8a0ad45250f130280e4171c001d`)

---

## 10. No Live / A3 Authorization — Runtime Mutation Status

| Item | Status |
|------|--------|
| `dry_run=false` | **PROHIBITED** — no A3 approval |
| Live orders | **PROHIBITED** — no A3 approval |
| Live exchange credentials | **NOT DEPLOYED** — no A3 approval |
| Capital/risk limit increases | **PROHIBITED** — no A3 approval |
| RiskGuard weakening | **PROHIBITED** — no A3 approval |
| Kill-switch bypass/deactivation | **PROHIBITED** — no A3 approval |
| R5B execution / agent0 mutation | **BLOCKED** — Gate 1 A2 approval missing (`APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE`) |
| Docker/Compose mutation | **BLOCKED** — no A2 approval |
| Freqtrade bot restart | **BLOCKED** — no approval |
| Canary redeployment | **BLOCKED** — no approval |
| Rainbow producer start | **BLOCKED** — no approval |
| **Runtime mutation by this A1 task** | **NONE** |

**Runtime mutation for this iteration:** `NONE` (A1 docs-only)

---

## 11. Files Modified

| File | Change Type | Purpose |
|------|-------------|---------|
| `docs/state/current-operational-state.md` | Update | Make 2026-07-14 roadmap correction the latest superseding state; identify #580 as active next R5B A2 preflight decision; mark R5B-A1 planning complete and #561 superseded; state Gate 1 remains blocked; state fleet-wide kill-switch impact; state Rebel dormant/out-of-scope/start-prohibited for Gate 1; keep R6 blocked by R5B; split R7 into #105 + #496; preserve historical evidence |
| `docs/reports/r5b-a2-preflight-roadmap-correction-2026-07-14.md` | Create | This report — source-of-truth reconciliation, #580 PREPARED contract, credential-boundary attestation, Rebel decision requirement, fleet-wide kill-switch, R5B Gates 1-4 sequencing, R6 boundary, ai4trade immutable promotion SHAs, R7 track split, no A3 authorization |

---

## 12. Validation Checklist

| Check | Result |
|-------|--------|
| `docs/state/current-operational-state.md` UTF-8 readable, newline-terminated | ✅ |
| `docs/reports/r5b-a2-preflight-roadmap-correction-2026-07-14.md` UTF-8 readable, newline-terminated | ✅ |
| `git diff --check` passes | ✅ (verified in worktree) |
| Report contains `runtime_mutation=NONE` | ✅ |
| Report references Issue #580 | ✅ |
| Report states fleet-wide kill-switch impact | ✅ |
| Report states Rebel dormant/out-of-scope/start-prohibited for Gate 1 | ✅ |
| Report references both R7 issue numbers (#105, #496) | ✅ |
| Report references both full ai4trade SHAs (`30e5ebec...` and `6e850c8f...`) | ✅ |
| No secret-like token patterns added | ✅ |
| Shared checkout `/workspace/projects/trading-hub` remains clean and on `main` | ✅ |
| Worktree clean, on branch `docs/r5b-a2-preflight-roadmap-alignment` | ✅ |
| No modifications to AGENTS.md, SOUL.md, runtime code, Docker, Cron, configs, bots, strategies, kill switch, issues, or runtime state | ✅ |

---

## 13. Next Action

**Open PR:** `docs: align R5B preflight roadmap` (A1, docs-only, `runtime_mutation=NONE`, #580 remains blocked, no Gate-1 approval)  
**Do not merge in this iteration** — await CI and review.  
**Next roadmap tick:** Will select the next unblocked task after this PR merges (subject to writer lock and open PR check).

---

**End of Report**