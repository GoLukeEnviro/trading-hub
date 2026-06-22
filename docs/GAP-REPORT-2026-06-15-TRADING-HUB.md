# GAP-REPORT — Trading Hub 2026-06-15

> **Status:** Current
> **Scope:** Trading Hub system — SI v2 Phase 2 Runtime Ownership
> **Author:** Meta-Orchestrator (Hermes)
> **Method:** Cross-component audit + PR-body analysis + filesystem evidence

> Historical note (2026-06-16+):
> This GAP report reflects the Trading Hub state *before* the completion of
> Phase 2.0 "Runtime Foundation & Docker Ownership" (issue #200, PR #262).
> For the current canonical view of runtime ownership and SI v2 status, refer to:
> - docs/state/current-operational-state.md
> - docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md
>
> Use this document as an audit artifact, not as the canonical description
> of the current system.

---

## 1. Executive Summary

The Trading Hub continues to converge toward runtime ownership. Since the
2026-06-05 Deep-Dive report, the following gaps have been **closed**:

| Gap ID | Title | Resolution | PR |
|--------|-------|------------|----|
| TD-01 | Central Kill Switch | ✅ Implemented | PR #220 |
| TD-02 | Rainbow §5 read-only source | ✅ Merged | PR #215 |
| TD-03 | Measurement Ledger | ✅ Merged | PR #210/#211 |
| TD-04 | Active Cycle Runner (multi-bot) | ✅ Merged | PR #208 |
| TD-05 | Fleet healthchecks | ✅ Merged | PR #204 |

Remaining gaps cluster around **runtime ownership (#200)**, **telegram production
approval**, and **boot sequence engineering**.

---

## 2. System State

| Property | Value |
|----------|-------|
| Live trading | 🔴 `FORBIDDEN` |
| Deployment | Containerized (Docker Compose) |
| State machine | `LIVE_FORBIDDEN` |
| Signal sources | `ai-hedge-fund-crypto` + Rainbow §5 (read_only, observed only) |
| Meta-orchestrator | `hermes-agent` (orchestrator profile) |
| SI v2 controller | `PAUSED / L3_REPOSITORY_ONLY` |

### Bot Fleet

| Bot | Mode | Strategy |
|-----|------|----------|
| FreqForge | dry-run | `FreqForge_Override` |
| Regime-Hybrid | dry-run | `RegimeSwitchingHybrid_v7_v04_Integration` |
| FreqForge-Canary | dry-run | `FreqForge_Override` |
| FreqAI-Rebel | dry-run | `RebelLiquidation + RebelXGBoostClassifier` |

---

## 3. Gap Register

### TD-01 — Central Kill Switch ✅ CLOSED

**Status:** Implemented via PR #220 (`feat/kill-switch-wiring`, merge pending).
**Evidence:** `freqtrade/shared/kill_switch.py` (270 lines), `orchestrator/scripts/kill_switch_trigger.sh` (127 lines), patch to `primo_signal.py:primo_gate_allows()`.

**Architecture:**
- File-based state in `var/kill_switch.json`
- 3 modes: `NORMAL`, `HALT_NEW`, `EMERGENCY`
- Drawdown thresholds: HALT at 12%, EMERGENCY at 18%
- Auto-clear timer support
- Atomic writes (`.tmp` + `os.replace()`)
- mtime-based read cache

**Integration:**
- Choke point in `primo_signal.py:primo_gate_allows()` — highest priority check
- Graceful degradation: if `kill_switch.py` unimportable, a fallback no-op is used
- CLI via trigger script or direct Python

### TD-02 through TD-05 — Rainbow / Ledger / Cycle Runner / Healthchecks ✅ CLOSED

All merged. See `docs/state/current-operational-state.md` for details.

---

### TD-06 (NEW) — Runtime Ownership & Docker Drift 🟠 OPEN

**Issue:** #200 — Canonicalize Compose project ownership.
**Status:** 7 of 20 running containers have no Compose project label.
**Impact:** Fleet-automation reliability concern. The SI v2 loop is unaffected
(reads only Freqtrade REST + Rainbow stub).

**Remaining work:**
- Assign Compose authority to unmanaged containers (btc5m-bot, claude-worker,
  green-mem0, green-ollama, green-qdrant, trading-hermes-watchdog-1, weatherhermes)
- Document canonical boot sequence
- Container start-order dependency graph

---

### TD-07 (NEW) — Telegram Approval Production Gate 🟠 OPEN

**Status:** Design exists (`PHASE_M_APPROVAL_PAYLOAD_DRAFT.md`) but no production
deployment.
**Required for:** Phase 2.1 (SI v2 Autonomous Dry-Run Operation).

---

### TD-08 (NEW) — Walk-Forward Validation Framework 🟡 BACKLOG

**Status:** Design exists in `walk_forward.py` but not yet integrated into
the active cycle pipeline.

---

### TD-09 (NEW) — Kill-Switch Runbook 🟢 CLOSED

**Status:** Created in `docs/runbooks/kill-switch.md`.

---

### TD-10 (NEW) — SI v2 Entry-Point Documentation 🟢 CLOSED

**Status:** Created in `self_improvement_v2/README.md`.

---

## 4. Phase Progress

See `docs/state/current-operational-state.md` §3 for the canonical phase progress.

| Phase | Name | Status |
|-------|------|--------|
| 0 | Stabilization & Foundation | ✅ Complete |
| 1 | Shadowlock & Foundation | ✅ Complete |
| 2.0 | Runtime Foundation & Docker Ownership | 🟠 IN PROGRESS (#200) |
| 2.1 | SI v2 Autonomous Dry-Run Operation | ⏸ Pending |
| 2.2 | Observability, Hardening & Self-Healing | ⏸ Pending |
| 3 | Signal Weighting & Higher Autonomy | ⏸ Pending |

---

## 5. Action Items (Next)

| Priority | Action | Owner |
|----------|--------|-------|
| 🔴 High | Merge PR #220 (Kill Switch) | Operator |
| 🔴 High | Resolve #200 — Docker Drift | Hermes |
| 🟠 Medium | Design deployment gates for Telegram production approval | Hermes |
| 🟢 Low | Integrate walk-forward into active cycle pipeline | Hermes |

---

## 6. Related Documents

| Document | Location |
|----------|----------|
| Deep-Dive Report (2026-06-05) | `docs/GAP-REPORT-2026-06-05-DEEP-DIVE-AUTONOMES-TRADING.md` |
| Current Operational State | `docs/state/current-operational-state.md` |
| Roadmap v2 | `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md` |
| Kill-Switch Runbook | `docs/runbooks/kill-switch.md` |
| SI v2 README | `self_improvement_v2/README.md` |
