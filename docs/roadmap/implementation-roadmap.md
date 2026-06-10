# Trading Hub — Implementation Roadmap

> **Canonical roadmap** — Source of truth for implementation phases, current
> state, and next priorities.

**Last updated:** 2026-06-10

---

## Phase Overview

| Phase | Name | Status | Tracker |
|-------|------|--------|---------|
| 0 | Stabilization & Foundation | 🔶 In progress | [#48](https://github.com/GoLukeEnviro/trading-hub/issues/48) |
| 1 | Shadowlock & Foundation | ⬜ Not started | #12/#45 |
| 2 | Runtime Blockers | ⬜ Not started | #43/#44 |
| 3 | Rainbow Signal Integration | ⬜ Not started | ai4trade-bot #55 |

---

## Phase 0 — Stabilization & Foundation

**Goal:** Stabilize the codebase, define safety contracts, and establish
documentation baseline before deeper changes.

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
| #47 | Roadmap/README/.gitignore Baseline | docs | *(this PR)* |

### Open Issues

| Issue | Title | Priority | Dependencies |
|-------|-------|----------|-------------|
| [#43](https://github.com/GoLukeEnviro/trading-hub/issues/43) | Fix FleetRiskManager dry-run entry blocker | 🔴 Critical | None |
| [#44](https://github.com/GoLukeEnviro/trading-hub/issues/44) | Runtime / Docker Compose ownership | 🟠 High | None |
| [#46](https://github.com/GoLukeEnviro/trading-hub/issues/46) | Branch/PR/worktree hygiene | 🟡 Medium | None |
| [#40](https://github.com/GoLukeEnviro/trading-hub/issues/40) | Re-run dry-run signal validation | 🟡 Medium | Blocked by #43 |

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

## Phase 2 — Runtime Blockers

**Goal:** Fix known runtime blockers and harden infrastructure.

| Issue | Title | Priority | Dependencies |
|-------|-------|----------|-------------|
| [#43](https://github.com/GoLukeEnviro/trading-hub/issues/43) | FleetRiskManager dry-run fix | 🔴 Critical | None |
| [#44](https://github.com/GoLukeEnviro/trading-hub/issues/44) | Runtime/Compose ownership audit | 🟠 High | None |
| [#40](https://github.com/GoLukeEnviro/trading-hub/issues/40) | Re-run dry-run validation | 🟡 Medium | #43 |

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

| Document | Location |
|----------|----------|
| SI v2 Documentation Index | `self_improvement_v2/docs/README.md` |
| Phase 0 Tracker | [#48](https://github.com/GoLukeEnviro/trading-hub/issues/48) |
| Issue Backlog | [GitHub Issues](https://github.com/GoLukeEnviro/trading-hub/issues) |
| AGENTS.md | `AGENTS.md` |
