# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project uses [Conventional Commits](https://www.conventionalcommits.org/)
(`feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `test:`).

---

## [Unreleased]

### Changed

- `docs/ARCHITECTURE.md`: updated system overview — controller AUTONOMOUS_DRY_RUN, kill switch NORMAL, SI-v2 loop architecture aligned with ADR-2026-07-01
- `docs/state/si-v2-capability-matrix.md`: rebuilt to reflect Track A/B/C state, Phase 10.1–10.6, live readiness, live canary, C4 ROLLBACK_RECOMMENDED, D1 BLOCKED
- `self_improvement_v2/README.md`: aligned with AUTONOMOUS_DRY_RUN mode, removed stale HUMAN_GATED claims, added Track A/B/C module map and fleet rollout chain documentation

---

## [2026-07-03] — Track C Complete, C4 ROLLBACK_RECOMMENDED, Backlog Hygiene

### Added

- **PR #437**: C4 — Live Canary Measurement and Decision (992-line module, 7 metrics, 4 decision outcomes)
- **#438**: C4 Decision Triage — validated ROLLBACK_RECOMMENDED (max_drawdown 82.79% breach)
- **#440**: C3 Rollback Plan Review — substantively complete, 5 gaps identified
- **#442**: C4c — Human Decision Gate — rollback path selected
- **PR #446**: C4d — Rollback Readiness Artifacts (emergency_stop.sh, kill-switch procedure, evidence convention, incident report convention)
- **#447**: C4e — Canary Baseline Return (container stopped, kill switch EMERGENCY→NORMAL)
- **#449**: C4f — Post-Return Verification (all 8 checks GREEN)
- **#456**: Post-Closure Recovery Backlog — dry-run canary to future D1 readiness
- **#457**: Docs drift closure issue — critical SI-v2 state drift from read-only audit
- `docs/incidents/incident-2026-07-03-canary-baseline-return.md` — incident report
- `docs/reports/c4-decision-triage-2026-07-03.md` — C4 triage analysis
- `docs/reports/c3-rollback-plan-review-2026-07-03.md` — rollback plan review
- `orchestrator/scripts/emergency_stop.sh` — emergency stop script

### Changed

- Canary container `freqtrade-freqforge-canary`: **Stopped** (Exited 130)
- Kill switch: cycled EMERGENCY → NORMAL
- C4 decision: `ROLLBACK_RECOMMENDED` — D1 BLOCKED

### Closed

- **#441**: Backlog Hygiene — disposed 5 stale PRs, classified remaining issues
- **#325**: Rainbow Lifecycle Hardening — Phases A–D complete (PR #450)
- **#314**: Coverage Quality Gate — policy.py 73%→95% (PR #451)
- **#310**: SI-v2 Post-Readiness Hardening — kill-switch proof, stale evidence gate (PRs #452, #454)

---

## [2026-07-02] — Track C Live Canary Transition

### Added

- **PR #433**: C1 — Human Approval Gate for Live Canary (5 checks, 12 tests)
- `docs/decisions/APPROVED_LIVE_CANARY_TRANSITION.md` — approval marker
- **PR #434**: C2 — Live Canary Config Plan (6 checks, 7 planned deltas, 17 tests)
- **PR #436**: C3 — Live Canary Activation Ceremony (8 checks, 3 snapshots, 27 tests, fail-closed)
- `docs/reports/live-canary-config-plan.md` — config plan report
- `docs/reports/live-canary-activation-ceremony.md` — ceremony report

---

## [2026-07-01] — Track B Complete, ADR Pivot, Phase 10.4

### Added

- **PR #425**: Phase 10.4 — Post-Fleet Measurement Watcher (20 tests)
- **PR #429**: B1 — Live Readiness Evidence Audit (7 checks, 14 tests)
- **PR #430**: B2 — Production Risk Limits Spec (9 acceptance criteria, 202 lines)
- **PR #431**: B3 — Incident Response and Go-Live Runbooks (6 acceptance criteria, 314 lines)
- **PR #432**: B4 — Production Alerting Gate (4 checks, 10 tests)
- `docs/decisions/ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md` — autonomous dry-run pivot ADR
- `docs/specs/production-risk-limits-spec.md` — risk limits specification
- `docs/specs/incident-response-runbooks.md` — runbooks

### Changed

- SI-v2 controller target pivoted to **AUTONOMOUS_DRY_RUN** (ADR-2026-07-01)
- Policy-gated, canary-first, allowlist-based dry-run apply (not per-apply human-gated)

---

## [2026-06-27 to 2026-06-30] — Phase 3B-6A Canary Apply Proven, Track A Begins

### Added

- **PR #379**: Phase 3B-A — Restart with Overlay (45 tests)
- **PR #380**: Phase 3B-B — Restart Gate (23 tests)
- **PR #381**: Phase 3C-A — Runtime Executor (23 tests)
- **PR #382**: Phase 4A — Measurement Decision Engine (37 tests)
- **PR #383**: Phase 5A — Rollback Rehearsal (24 tests)
- **PR #384**: Phase 6A — Candidate Pipeline (36 tests)
- Autonomy Policy module — L3 token bypass, G10 bypass, allowlist enforcement
- First canary dry-run apply proven: `max_open_trades 3→2` on `freqtrade-freqforge-canary`
  — RuntimeEffectProof: **GREEN**
  — Final Decision: **KEEP_CANARY_OVERLAY** (YELLOW/MEDIUM)
- **PR #421**: Phase 10.1 — Fleet Rollout Input Resolver (24 tests)
- **PR #422**: Phase 10.2 — READY-only Fleet Chain Evidence Runner (12 tests)
- **PR #424**: Phase 10.3 — Controlled Dry-Run Fleet Runtime Executor (18 tests)
- **PR #426**: Updated `docs/state/current-operational-state.md` post Phase 10.4

### Changed

- Measurement timeline: T0 GREEN, T1 YELLOW, T2 YELLOW, T3 YELLOW/EXTEND, T4 NOT_ENOUGH_DATA, Final KEEP_CANARY_OVERLAY
- Kill switch: NORMAL (set 2026-06-29)

---

## [2026-06-15] — SI-v2 Controller, Kill Switch, Gap Report

### Added

- Central Kill Switch: `freqtrade/shared/kill_switch.py` with 3 modes (NORMAL / HALT_NEW / EMERGENCY),
  atomic file-based state, auto-clear timer, and drawdown guard integration
- `orchestrator/scripts/kill_switch_trigger.sh` — CLI for status/halt/emergency/clear/auto-check
- Patch to `primo_signal.py:primo_gate_allows()` — kill switch is highest-priority choke point
- `docs/runbooks/kill-switch.md` — full operational runbook
- `docs/GAP-REPORT-2026-06-15-TRADING-HUB.md` — gap register (TD-01 through TD-10)
- `self_improvement_v2/README.md` — SI v2 subsystem overview, module map, entry points

### Changed

- `README.md` root: updated component table (21 entries), layout tree, roadmap links, docs map
- `AGENTS.md`: Kill-Switch section, SI v2 section, RiskGuard/ShadowLogger status updated, safety rule #7
- `CLAUDE.md`: Kill-Switch in safety rules, architecture diagram, directory table, cron table, runbooks section
- `docs/README.md`: added roadmap/roadmaps clarity notes, linked new docs
- `docs/state/current-operational-state.md`: updated to reflect Rainbow, Ledger, ActiveCycleRunner,
  SI v2 controller status (PAUSED / L3_REPOSITORY_ONLY), scoring gate 0/10 *(superseded by ADR-2026-07-01)*
- `docs/state/si-v2-capability-matrix.md`: rebuilt *(superseded by 2026-07-03 update)*

---

## [2026-06-14] — Rainbow Read-Only Runtime + Freshness Guard

### Added

- **PR #215**: Rainbow §5 read_only runtime source with env-var overrides and freshness guard
  - `SI_V2_RAINBOW_ENABLED`, `SI_V2_RAINBOW_MODE` env vars
  - Scoring gate: `fresh=False` when source timestamps are stale (correct behavior)
- **PR #214**: Env-var override for Rainbow observation activation
- **PR #213**: Rainbow read_only signals integrated into active cycle and Measurement Ledger
- **PR #212**: Rainbow read-only signal client (`self_improvement_v2/src/si_v2/rainbow/`)
- **PR #211**: Passive Measurement Ledger wired into Active Cycle Runner
- **PR #210**: Measurement and attribution ledger v1 — 27 fleet cycles, 108 bot measurement points
- **PR #209**: Multi-signal fusion for actionable ShadowProposals
- **PR #208**: Active Multi-Bot Cycle Runner v1 — scheduled at `17 */6 * * *`
- **PR #217 (docs)**: Runtime ownership map audit for issue #200
- **PR #216 (docs)**: Roadmap reconciliation after SI v2 Rainbow integration

### Changed

- `docs/state/current-operational-state.md`: updated to reflect Rainbow, Ledger, ActiveCycleRunner *(historical)*
- `docs/state/si-v2-capability-matrix.md`: rebuilt *(historical)*

### Fixed

- **PR #218**: Hermes-watchdog compose network alignment before Phase 2 adoption

---

## [2026-06-13] — Docker Healthchecks + Phase 2 Foundation

### Added

- **PR #204**: Deterministic Docker healthchecks for Freqtrade fleet
- **PR #203**: Stage B one-shot proof artifact (ISOLATED-ONE-SHOT-PROOF)
- **PR #202 (docs)**: Phase B2 L3 adoption execution plan for #200
- **PR #198**: Branch protection validation (GREEN PR marker)
- **PR #195**: Main-gate CI workflow for branch protection
- **PR #194**: Deterministic weekly review cadence policy (closes #66)
- **PR #193**: Fail-closed scheduler activation ceremony policy (closes #26)
- **PR #192**: SHA validation hardening with module-level regex and regression tests
- **PR #175**: Reusable controller baseline reconciliation command
- **PR #182**: Dedicated Phase 2 proposal-stack CI gate
- **PR #65**: Validation Gate Matrix for Phase 2 proposal review
- **PR #181**: Real no-mock Phase 2 end-to-end integration proof

### Fixed

- Freqtrade read-only registry: fixed to use Docker DNS
- SHA validation: accepts 40-char SHA-1 hashes in reconcile controller baseline
- Episode report contracts: SHA-256, timestamps, verdict truth table, duplicate ID rejection

---

## [2026-06-12] — Phase 1 Intelligence Epic Complete

### Added

- **PR #185**: Episode report builder for proposal review workflow (issue #64)
- **PR #173**: Weight proposal engine with human-approval output only (issue #63)
- **PR #174**: Proposal scoring and promotion policy (issue #35)
- **PR #177**: Market-data readiness specification and tests (issue #34)
- **PR #171 (docs)**: Phase 0 reconciliation — updated stale docs for merged issues #55–#59
- **PR #169**: Issue #60 — derived SQLite cache maintenance module
- **PR #166**: Issue #59 — automated attribution reports
- **PR #165**: Issue #58 — source-regime statistics
- **PR #164**: Issue #57 — performance attribution
- **PR #163**: Issue #56 — regime shadowlock enrichment
- **PR #162 (docs)**: Post-controller reconciliation docs update

### Fixed

- PR #169: 13 M60 safety fixes for issue #60 cache maintenance
- PR #165: Contract audit, schema safety, metric correctness

---

## [2026-06-10] — Controller Layer + Evidence Foundation

### Added

- **PR #158–#160**: Controller Layer (merged)
  - `si-v2-controller` agent with bounded work packages, queue, and human-only merge
  - `orchestrator/control/POLICY.md` — controller policy
- **PR #161**: Phase 1 Intelligence Epic (issues #55–#59, #60)
  - Evidence input pipeline, source readiness summary, evidence bundle builder
  - Episode foundation: offline episode reports for 141 evidence snapshots
- **PR #151**: Read-only adapter contracts (issue #20)
- **PR #152**: RiskGuard + ShadowLogger contracts (issue #22)
- **PR #153**: Watchdog ownership ADR (issue #23)
- **PR #154**: Telegram approval design (issue #25)
- **PR #155**: Cron activation ceremony (issue #26)
- **PR #159**: v1 residue closure (issue #27)
- **PR #160**: Docs index consolidation (issue #32)
- `ADR-2026-06-10-watchdog-ownership.md`: Watchdog ownership boundary decision record

---

## [2026-06-05] — Initial GAP Deep-Dive + Stabilization

### Added

- `docs/GAP-REPORT-2026-06-05-DEEP-DIVE-AUTONOMES-TRADING.md` — 46KB deep-dive analysis
  identifying TD-01 (Kill Switch) as primary gap
- SI v2 Phase 0 closure: all 12 issues closed
- FleetRiskManager dry-run entry bug fix (#43)
- Dry-run signal revalidation (#40)

---

## [2026-06-01 to 2026-06-04] — ShadowLock + Foundation

### Added

- ShadowLock service deployment
- Fleet monitoring and healthcheck framework
- Git hygiene policy (`docs/git-hygiene.md`)
- Backtest and walk-forward infrastructure
- CI safety gates implementation

---

## [2026-05-16] — Initial GAP Reports

### Added

- `docs/GAP-REPORT-2026-05-16.md` — Trading Hub Gesamtsystem GAP-Bericht
- `docs/gap-report-20260516.md` — Hermes-Kosmos GAP-Report

---

## [Prior to 2026-05-16]

### Added

- Repository creation and initial setup
- Freqtrade fleet deployment (FreqForge, Regime-Hybrid, FreqAI-Rebel, Canary)
- ai-hedge-fund-crypto integration
- Signal pipeline and bridge
- Caddy reverse proxy setup
- Docker Compose orchestration
- Initial documentation structure
