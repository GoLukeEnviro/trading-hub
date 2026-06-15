# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project uses [Conventional Commits](https://www.conventionalcommits.org/)
(`feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `test:`).

---

## [Unreleased]

### Added

- Central Kill Switch: `freqtrade/shared/kill_switch.py` with 3 modes (NORMAL / HALT_NEW / EMERGENCY),
  atomic file-based state, auto-clear timer, and drawdown guard integration
- `orchestrator/scripts/kill_switch_trigger.sh` — CLI for status/halt/emergency/clear/auto-check
- Patch to `primo_signal.py:primo_gate_allows()` — kill switch is highest-priority choke point
- `docs/runbooks/kill-switch.md` — full operational runbook
- `docs/GAP-REPORT-2026-06-15-TRADING-HUB.md` — current gap register (TD-01 through TD-10)
- `self_improvement_v2/README.md` — SI v2 subsystem overview, module map, entry points

### Changed

- `README.md` root: updated component table (21 entries), layout tree, roadmap links, docs map
- `AGENTS.md`: Kill-Switch section, SI v2 section, RiskGuard/ShadowLogger status updated, safety rule #7
- `CLAUDE.md`: Kill-Switch in safety rules, architecture diagram, directory table, cron table, runbooks section
- `docs/README.md`: added roadmap/roadmaps clarity notes, linked new docs

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
- **PR #208**: Active Multi-Bot Cycle Runner v1 — scheduled at `17 */6 * * *`, wrapper at
  `/opt/data/scripts/si-v2-active-cycle-runner.sh`
- **PR #217 (docs)**: Runtime ownership map audit for issue #200
- **PR #216 (docs)**: Roadmap reconciliation after SI v2 Rainbow integration

### Changed

- `docs/state/current-operational-state.md`: updated to reflect Rainbow, Ledger, ActiveCycleRunner,
  SI v2 controller status (PAUSED / L3_REPOSITORY_ONLY), scoring gate 0/10
- `docs/state/si-v2-capability-matrix.md`: rebuilt

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
- **ADR-2026-06-10-watchdog-ownership.md**: Watchdog ownership boundary decision record

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
