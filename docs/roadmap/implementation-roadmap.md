# Trading Hub — Implementation Roadmap

> **SUPERSEDED:** This document is historical. Current roadmap is
> [`docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md`](roadmap-v2-blocker-first-runtime-ownership.md).
> The Phase 0 "not started" claim is wrong — #44 is closed, #200 is the
> current blocker, and the SI v2 scheduled observation loop is
> operational. See `docs/state/current-operational-state.md` for the
> reconciled snapshot.
>
> **Last updated:** 2026-06-11 (historical)
> **HEAD at that update:** `0557b70` (PR #169 — cache maintenance)

---

## Phase Overview

| Phase | Name | Status | Tracker |
|-------|------|--------|---------|
| 0 | Stabilization & Foundation | ✅ Complete | [#48](https://github.com/GoLukeEnviro/trading-hub/issues/48) |
| 1 | Shadowlock & Foundation | ✅ Complete | #12/#45/#47 |
| — | Controller Layer (PR #158–#160) | ✅ Complete | — |
| 1i | Intelligence Layer (Real-Data) | ✅ Complete | [#55–#61](https://github.com/GoLukeEnviro/trading-hub/issues/55) |
| 2 | Runtime Blockers | ⬜ Not started | #43/#44 |
| 3 | Rainbow Signal Integration | ⬜ Not started | ai4trade-bot #55 |

---

## Phase 0 — Stabilization & Foundation

**Goal:** Stabilize the codebase, define safety contracts, and establish
documentation baseline before deeper changes.

**Status:** ✅ **Complete** — all 12 issues closed via PRs #49–#54, #68–#75.

### Completed Issues

| Issue | Title | Type | PR |
|-------|-------|------|----|
| #22 | RiskGuard/ShadowLogger Runtime Safety Contract | docs | [#49](https://github.com/GoLukeEnviro/trading-hub/pull/49) |
| #23 | Watchdog Ownership ADR | docs | [#50](https://github.com/GoLukeEnviro/trading-hub/pull/50) |
| #32 | SI v2 Documentation Index | docs | [#51](https://github.com/GoLukeEnviro/trading-hub/pull/51) |
| #30 | Safety Status Reporting Layer | code + tests | [#52](https://github.com/GoLukeEnviro/trading-hub/pull/52) |
| #31 | CI Safety Gates | tests + CI | [#53](https://github.com/GoLukeEnviro/trading-hub/pull/53) |
| #20 | Read-Only Adapter Contracts | docs | [#54](https://github.com/GoLukeEnviro/trading-hub/pull/54) |
| #21 | Read-Only Adapter Prototypes | code + tests | [#68](https://github.com/GoLukeEnviro/trading-hub/pull/68) |
| #25 | Telegram Approval Adapter Design | docs | [#69](https://github.com/GoLukeEnviro/trading-hub/pull/69) |
| #26 | Cron Activation Ceremony | docs | [#70](https://github.com/GoLukeEnviro/trading-hub/pull/70) |
| #27 | V1 Residue Closure Plan | docs | [#71](https://github.com/GoLukeEnviro/trading-hub/pull/71) |
| #38 | Rebel Telegram Conflict RCA | docs | [#72](https://github.com/GoLukeEnviro/trading-hub/pull/72) |
| #39 | Watchdog Connectivity RCA | docs | [#73](https://github.com/GoLukeEnviro/trading-hub/pull/73) |
| #12 | Shadowlock Indexer | code + tests | [#74](https://github.com/GoLukeEnviro/trading-hub/pull/74) |
| #45 | Writer→Indexer Trigger | tests | [#75](https://github.com/GoLukeEnviro/trading-hub/pull/75) |
| #47 | Roadmap/README/.gitignore Baseline | docs | *(see PR #75)* |

### Open Issues

| Issue | Title | Priority | Status | Dependencies |
|-------|-------|----------|--------|-------------|
| [#44](https://github.com/GoLukeEnviro/trading-hub/issues/44) | Runtime / Docker Compose ownership | 🟠 High | 🔴 BLOCKED — requires Docker/runtime access | None |
| [#46](https://github.com/GoLukeEnviro/trading-hub/issues/46) | Branch/PR/worktree hygiene | 🟡 Medium | 🟡 OPEN — repo-only work | None |

### Recently Completed Issues

| Issue | Title | Priority | PR | Merge SHA |
|-------|-------|----------|----|-----------|
| [#43](https://github.com/GoLukeEnviro/trading-hub/issues/43) | Fix FleetRiskManager dry-run entry blocker | 🔴 Critical | [#77](https://github.com/GoLukeEnviro/trading-hub/pull/77) | `91b10b9` |
| [#40](https://github.com/GoLukeEnviro/trading-hub/issues/40) | Re-run dry-run signal validation | 🟡 Medium | [#142](https://github.com/GoLukeEnviro/trading-hub/pull/142) | `c627b06` |

---

## Phase 1 — Shadowlock & Foundation

**Goal:** Complete the shadowlock indexing pipeline and establish a clean
repository baseline.

| Issue | Title | Priority | Dependencies |
|-------|-------|----------|-------------|
| #12 | Shadowlock Indexer | ✅ Complete | None |
| #45 | Writer→Indexer Trigger | ✅ Complete | #12 |
| #47 | Roadmap/README/.gitignore | ✅ Complete | None |
| #46 | Branch/PR/Worktree Hygiene | 🟡 Medium | None |

---

## Controller Layer (PR #158–#160)

**Goal:** Build and harden the SI v2 continuous controller — a repository-level
control plane for deterministic, offline implementation.

**Status:** ✅ **Complete** — merged at `fdac27c`.

| Work | PR/Commit | Status |
|------|-----------|--------|
| Planning automation and quality (issues #143–#154) | [#158](https://github.com/GoLukeEnviro/trading-hub/pull/158) | ✅ Merged |
| Controller state contract, validator rewrite | [#160](https://github.com/GoLukeEnviro/trading-hub/pull/160) | ✅ Merged |
| 4-defect hardening (subprocess tests, ruff, env export) | Commits in #160 | ✅ Merged |

**Controller operational state:** `PAUSED` — awaiting next approved epic.
External state at `/opt/data/si-v2-controller/state/`.

---

## Phase 1i — Intelligence Layer (Real-Data)

**Goal:** Enable real-data intelligence pipeline — regime detection,
performance attribution, and automated reporting against live Freqtrade
trade data.

**Status:** ✅ **Complete** — all issues #55–#59 merged via PRs #161–#166.

| Issue | Title | Priority | PR | Merge SHA | Status |
|-------|-------|----------|----|-----------|--------|
| [#55](https://github.com/GoLukeEnviro/trading-hub/issues/55) | Define canonical Regime Detector schema | 🔴 Critical | [#161](https://github.com/GoLukeEnviro/trading-hub/pull/161) | `9017dd4` | ✅ Merged |
| [#56](https://github.com/GoLukeEnviro/trading-hub/issues/56) | Implement Regime Detector run and Shadowlock enrichment | 🔴 Critical | [#163](https://github.com/GoLukeEnviro/trading-hub/pull/163) | `fadfefa` | ✅ Merged |
| [#57](https://github.com/GoLukeEnviro/trading-hub/issues/57) | Build Performance Attribution Engine by source and regime | 🔴 Critical | [#164](https://github.com/GoLukeEnviro/trading-hub/pull/164) | `773e9cb` | ✅ Merged |
| [#58](https://github.com/GoLukeEnviro/trading-hub/issues/58) | Implement source_regime_stats summary table | 🟠 High | [#165](https://github.com/GoLukeEnviro/trading-hub/pull/165) | `e806fc8` | ✅ Merged |
| [#59](https://github.com/GoLukeEnviro/trading-hub/issues/59) | Generate automated Attribution Reports | 🟠 High | [#166](https://github.com/GoLukeEnviro/trading-hub/pull/166) | `81884db` | ✅ Merged |
| [#60](https://github.com/GoLukeEnviro/trading-hub/issues/60) | Shadowlock SQLite maintenance and daily job plan | 🟡 Medium | ❌ None | ❌ N/A | 🟡 OPEN |
| [#61](https://github.com/GoLukeEnviro/trading-hub/issues/61) | Tracker — Intelligence Layer implementation | 🟢 Low (tracker) | ❌ None | ❌ N/A | 🟡 OPEN |

**Timer and dedicated-user activation remain blocked** — cron-based scheduler
not installed, credential isolation not created. Both require a separate
root-level phase and human approval.

---

## Phase 2 — Runtime Blockers

**Goal:** Fix known runtime blockers and harden infrastructure.

| Issue | Title | Priority | Dependencies |
|-------|-------|----------|-------------|
| [#44](https://github.com/GoLukeEnviro/trading-hub/issues/44) | Runtime/Compose ownership audit | 🟠 High | None |

---

## Phase 3 — Rainbow Signal Integration

**Goal:** Integrate ai4trade-bot Rainbow as read-only signal provider.

| Issue | Title | Priority | Dependencies |
|-------|-------|----------|-------------|
| ai4trade-bot #51 | Rainbow Signal Provider Contract | 🟡 Medium | Phase 0-2 |
| ai4trade-bot #52 | Rainbow Runtime Health Audit | 🟡 Medium | #51 |
| ai4trade-bot #53 | Metadata Readiness | 🟢 Low | #52 |
| ai4trade-bot #54 | Repo Hygiene Audit | 🟡 Medium | None |

---

## State Machine

```
LIVE_FORBIDDEN (current)
    ↓ Phase 0-3 complete
LIVE_CANDIDATE
    ↓ Human approval + RiskGuard validation
LIVE_APPROVED
    ↓ Monitoring active
LIVE_ACTIVE
```

**Current state:** `LIVE_FORBIDDEN` — all bots in `dry_run=true`.

---

## Related Documents

| Document | Location | Status |
|----------|----------|--------|
| Implementation Roadmap (this doc) | `docs/roadmap/implementation-roadmap.md` | ✅ Current |
| Current Operational State | `docs/state/current-operational-state.md` | ✅ Current |
| SI v2 Capability Matrix | `docs/state/si-v2-capability-matrix.md` | ✅ Current |
| Post-PR-160 Architecture Diagram | `docs/state/post-pr-160-architecture.md` | ✅ Current |
| Phase 1 Intelligence Epic | `docs/state/phase-1-intelligence-epic.md` | ✅ Current |
| Issues #55–#61 Evidence Matrix | `docs/state/issues-55-61-evidence-matrix.md` | ⬜ Updated by this PR |
| SI v2 Documentation Index | `self_improvement_v2/docs/README.md` | 🔶 Historical (pre-controller) |
| AGENTS.md | `AGENTS.md` | ✅ Current |
