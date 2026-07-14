# R5B Gate 1 Fleet-Wide Rebel Safety Correction — 2026-07-14

**Execution class:** A1 (repository-only: docs/state + report; no host mutation, no Docker/Compose mutation, no agent0 mutation, no kill-switch mutation, no runtime action)
**Runtime mutation:** NONE
**Source-of-truth reconciliation:** `AGENTS.md`, `SOUL.md`, `docs/state/current-operational-state.md`, Issue #423, Issue #580, Issue #580 comment 4968789848, open PRs
**Branch:** `docs/r5b-gate1-fleetwide-rebel-correction`
**Base SHA:** `aa0ac1009e454274da2657ef0da0c8edb3129f3e` (origin/main at task start)
**Writer lock:** Acquired (session `safety-correction-20260714-001`)
**Worktree:** `/opt/data/projects/trading-hub-worktrees/docs__r5b-gate1-fleetwide-rebel-correction`

---

## 1. Executive Summary

This A1 documentation-only iteration records a **safety correction** that invalidates the planned Gate 1 freeze execution contract. Fresh read-only agent0 evidence (2026-07-14) proves the running `trading-freqai-rebel-1` container shares the fleet-wide writable kill-switch mount with the three canonical agent0 roles. The existing kill switch at `freqtrade/shared/kill_switch.py` has no role-scoped or bot-scoped freeze capability. Therefore, the planned "canonical-role-only freeze" via `HALT_NEW` is **impossible** with the current implementation — it would affect the running Rebel bot, contradicting the Gate 1 boundary that Rebel is dormant/out-of-scope/start-prohibited.

**Gate 1 remains BLOCKED and NOT APPROVABLE** until Luke explicitly selects one of three decision paths. No `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE` marker may be issued until that decision is documented. R6/R7 remain blocked. Runtime mutation remains NONE.

The 2026-07-13 planning report (`docs/reports/r5b-cutover-gate-planning-2026-07-13.md`) is treated as historical and its role-scoped freeze wording is explicitly superseded by this correction. That historical report is NOT edited.

---

## 2. Fresh Authoritative A0 Evidence

| Evidence Point | Value | Source |
|---|---|---|
| Agent0 host | `Agent0` | Read-only host inspection |
| Running containers | `trading-freqai-rebel-1`, `trading-freqtrade-freqforge-1`, `trading-freqtrade-freqforge-canary-1`, `trading-freqtrade-regime-hybrid-1`, `trading-freqtrade-webserver-1` | `docker ps` (read-only) |
| Shared mount | All four trading containers mount `/home/hermes/projects/trading/freqtrade/shared` → `/freqtrade/shared` with `rw=true` | `docker inspect` (read-only) |
| Kill switch file | `/home/hermes/projects/trading/freqtrade/shared/kill_switch.json` reports `mode=NORMAL` | Read-only file inspection |
| Kill switch code | `freqtrade/shared/kill_switch.py` is fleet-wide; modes `NORMAL`/`HALT_NEW`/`EMERGENCY` apply to ALL four canonical SI-v2 bots | Source code inspection |
| Contradiction record | Issue #580 comment 4968789848 (SAFETY CORRECTION) | GitHub API |
| Runtime mutation | NONE | A1 class enforcement |

---

## 3. Contradiction Analysis

### 3.1 Planned Gate 1 Contract (from merged planning report)

The R5B Gate 1 planning report (`docs/reports/r5b-cutover-gate-planning-2026-07-13.md`, merged via PR #575) describes Phase 1 Step 1.4:

> **Freeze only canonical agent0 roles after steps 1.1–1.3 pass** — Scoped kill switch → `HALT_NEW` — Previous state recorded; freeze verified — Restore the prior kill-switch state

And the approval contract requires:
> **Fail closed: failed or incomplete isolation evidence aborts before mutation; after a freeze, only restoring the immediately preceding kill-switch state is allowed.**

### 3.2 Fresh Evidence Reality

- `trading-freqai-rebel-1` is **running** on agent0 (Up 4 days)
- All four agent0 trading containers share the **same** kill-switch file via the shared `rw=true` mount
- The kill switch is **fleet-wide** — `HALT_NEW` blocks new entries for ALL four bots simultaneously
- No role-scoped or bot-scoped freeze exists in the current architecture

### 3.3 The Contradiction

Executing the planned Step 1.4 ("Scoped kill switch → `HALT_NEW`") would:
1. Set `mode=HALT_NEW` in the shared kill-switch file
2. This affects `trading-freqai-rebel-1` (running) equally with the three canonical roles
3. This **contradicts** the Gate 1 boundary that Rebel is dormant/out-of-scope/start-prohibited
4. This **contradicts** the "canonical-role-only" freeze scope in the approval contract

---

## 4. Three Decision Paths (Luke Must Select ONE)

### Path 1: Fleet-Wide Gate 1 Freeze (Accept Rebel Impact)
- **Scope:** Approved `HALT_NEW` impact includes the running Rebel bot for the bounded Gate 1 window (max 24h UTC)
- **Requirements:** Explicit documentation that Rebel impact is accepted; Rebel remains in `HALT_NEW` during the freeze window
- **Risk:** Rebel trading activity (if any) is blocked; measurement attribution complicated by Rebel inclusion
- **Rollback:** Restore `mode=NORMAL` (same as canonical roles)

### Path 2: Scoped-Freeze Architecture (Separate Implementation)
- **Scope:** Keep Rebel out of Gate 1 freeze; implement genuine role-scoped/bot-scoped freeze before Gate 1
- **Requirements:** 
  1. New ADR defining scope, implementation, and safety boundaries
  2. Modify `kill_switch.py` and all bot entry points to respect scope
  3. Prove role-scoped behavior in dry-run without affecting other bots
  4. Separate A2/A3 gate for the freeze behavior change
- **Timeline:** Separate implementation phase before Gate 1 can proceed
- **Note:** This is NOT in scope for Gate 1 per current planning

### Path 3: Rebel Lifecycle Gate First (Separate Isolation)
- **Scope:** Separately approve and execute a reversible Rebel stop/isolation gate BEFORE Gate 1
- **Requirements:**
  1. Own evidence, approval marker, and rollback for Rebel stop/isolation
  2. Rebel fully stopped/isolated on agent0 before Gate 1 freeze
  3. Gate 1 then proceeds with canonical roles only (as originally planned)
- **Sequencing:** New gate → Gate 1

---

## 5. Updated Issue #580 Contract

| Contract Element | Status |
|---|---|
| Original UNVERIFIED items (2) | **RESOLVED PASS** — freqai-rebel config + Legacy Rainbow credential isolation (per PR #584 / Issue #583) |
| **NEW blocker** | **Fleet-wide kill-switch contradiction** — running agent0 Rebel shares kill switch |
| Gate 1 overall status | **BLOCKED / NOT APPROVABLE** |
| `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE` | **MUST NOT BE ISSUED** until Luke decision documented |
| R6/R7 status | **BLOCKED** (depend on R5B execution) |
| Runtime mutation | **NONE** |

---

## 6. Stop Rules (Hard Boundaries)

1. **No Gate 1 freeze execution** without explicit Luke decision among the three paths
2. **No `APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE` marker** until decision documented in `current-operational-state.md`
3. **No role-scoped freeze claim** — does not exist in current architecture
4. **No Rebel runtime action** for Gate 1 unless Luke explicitly decides otherwise in the Gate 1 marker
5. **No A2/A3 approval** for R5B execution until Gate 1 unblocked
6. **Runtime mutation remains NONE** for this correction and all prior A1 work

---

## 7. Files Modified

| File | Change Type | Purpose |
|---|---|---|
| `docs/state/current-operational-state.md` | Update | Add 2026-07-14 SAFETY CORRECTION header; correct Rebel Gate 1 section with fresh evidence, contradiction, three decision paths, updated #580 contract, stop rules |
| `docs/reports/r5b-gate1-fleetwide-rebel-safety-correction-2026-07-14.md` | Create | This report — evidence, contradiction analysis, three decision paths, updated #580 contract, stop rules, runtime_mutation=NONE |

---

## 8. Validation Checklist

| Check | Result |
|---|---|
| `docs/state/current-operational-state.md` UTF-8 readable, newline-terminated | ✅ |
| `docs/reports/r5b-gate1-fleetwide-rebel-safety-correction-2026-07-14.md` UTF-8 readable, newline-terminated | ✅ |
| `git diff --check` passes | ✅ (verified in worktree) |
| Report contains `runtime_mutation=NONE` | ✅ |
| Report references Issue #580 and comment 4968789848 | ✅ |
| Report states fleet-wide kill-switch impact | ✅ |
| Report states three decision paths explicitly | ✅ |
| Report references Agent0, running Rebel, shared rw mount | ✅ |
| Report treats 2026-07-13 planning report as historical, explicitly superseded | ✅ |
| No secret-like token patterns added | ✅ |
| Shared checkout `/workspace/projects/trading-hub` remains clean and on `main` | ✅ |
| Worktree clean, on branch `docs/r5b-gate1-fleetwide-rebel-correction` | ✅ |
| Only the two intended Markdown paths changed | ✅ |
| No changes to AGENTS.md, SOUL.md, runtime code, Docker, Cron, configs, bots, kill switch, issues, or runtime state | ✅ |

---

## 9. Historical Report Supersession Note

The 2026-07-13 planning report (`docs/reports/r5b-cutover-gate-planning-2026-07-13.md`) contains the original role-scoped freeze wording in Phase 1 Step 1.4. That report is **historical** and is **explicitly superseded** by this safety correction. The historical report is NOT edited — this correction takes precedence per the source-of-truth order (freshly verified evidence > latest explicitly superseding section in `current-operational-state.md`).

---

## 10. Next Action

**Open PR:** `docs: block R5B Gate 1 on fleet-wide Rebel impact` (A1, docs-only, `runtime_mutation=NONE`, #580 remains blocked/not approvable)
**Do not merge in this iteration** — await CI and review.
**Next roadmap tick:** Will select the next unblocked task after this PR merges (subject to writer lock and open PR check).

**Blocker for Gate 1:** Luke must explicitly select and document one of the three decision paths before any A2 approval marker can be issued.

---

**End of Report**