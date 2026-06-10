# SI v2 Documentation Index

> **Self-Improvement v2** — Foundation for autonomous trading bot optimization.
> Central index linking all active documents, ADRs, issues, and current state.

**Last updated:** 2026-06-10  
**Current commit (main):** `f4a5665` — docs(si-v2): decide watchdog ownership boundary between SI v2 and ai4trade-bot  
**Branch:** `main` (2 commits ahead of origin/main)  
**Issue backlog:** [GitHub Issues](https://github.com/GoLukeEnviro/trading-hub/issues)

---

## 1. Active Phase Documents

| Document | Location | Description |
|----------|----------|-------------|
| Master Roadmap | [#15](https://github.com/GoLukeEnviro/trading-hub/issues/15) | Top-level SI v2 roadmap and state tracker |
| Phase 0 Tracker | [#48](https://github.com/GoLukeEnviro/trading-hub/issues/48) | Stabilization and foundation implementation |
| Full E2E Dry-Run Pipeline | `docs/FULL_E2E_DRY_RUN_PIPELINE.md` | Complete 10-stage pipeline specification |
| Controlled Runtime Probe Plan | `docs/CONTROLLED_READ_ONLY_RUNTIME_PROBE_PLAN.md` | Safety-gated runtime probe execution plan |
| Real Adapter Design | `docs/REAL_ADAPTER_DESIGN.md` | Design review for real adapters (Docker, Freqtrade, Telegram) |
| Strategy Adapter Design | `docs/STRATEGY_ADAPTER_DESIGN.md` | Strategy mutation adapter design |
| Real Adapter Risks | `docs/REAL_ADAPTER_RISKS.md` | Risk assessment for real adapter activation |
| Phase M Approval Payload | `docs/PHASE_M_APPROVAL_PAYLOAD_DRAFT.md` | Approval payload template for Phase M |
| V1-to-V2 Cron Migration | `docs/V1_TO_V2_CRON_MIGRATION.md` | Migration plan from v1 to v2 cron architecture |

---

## 2. Architecture Decisions (ADRs)

| ADR | Location | Status |
|-----|----------|--------|
| AI4Trade Integration Boundary | `docs/ADR_AI4TRADE_INTEGRATION_BOUNDARY.md` | ✅ Ratified |
| Watchdog Ownership Boundary | `../docs/decisions/ADR-2026-06-10-watchdog-ownership.md` | ✅ Ratified (from #23) |
| Documentation Architecture | `../docs/decisions/2026-05-14-soul-agents-sync.md` | ✅ Ratified |

### ADRs in this document set

- **2026-06-10 — Watchdog Ownership:** Option 1 (separate ownership). SI v2 owns fleet-level infrastructure watchdog; ai4trade-bot owns signal-service watchdog. Future Option 3 for read-only heartbeat consumption.
- **2026-06-10 — RiskGuard/ShadowLogger Contract:** Defines runtime safety contract, fail-closed behavior, audit trail specification. See `../docs/specs/runtime-safety-contract.md`.

---

## 3. Safety Specifications

| Document | Location | Description |
|----------|----------|-------------|
| Runtime Safety Contract | [`../docs/specs/runtime-safety-contract.md`](../docs/specs/runtime-safety-contract.md) | RiskGuard/ShadowLogger contract, fail-closed policy, audit events |
| SI v2 ↔ ai4trade-bot Compatibility Matrix | `docs/AI4TRADE_COMPATIBILITY_MATRIX.md` | Read-only comparison of overlapping modules |
| AI4Trade Integration Readiness | `docs/AI4TRADE_INTEGRATION_READINESS.md` | Readiness assessment for ai4trade integration |
| REST Boundary Prototype | `docs/AI4TRADE_REST_BOUNDARY_PROTOTYPE.md` | REST API boundary prototype design |

---

## 4. Current Safety State

| Component | Status | Notes |
|-----------|--------|-------|
| `dry_run` | ✅ `True` (all bots) | No live trading |
| RiskGuard contract | ✅ Defined (#22) | `docs/specs/runtime-safety-contract.md` |
| ShadowLogger contract | ✅ Defined (#22) | `docs/specs/runtime-safety-contract.md` |
| RiskGuard implementation | 🔶 SI v2 spec; Guardian container deployed | SI v2 stage gate, not standalone service |
| ShadowLogger implementation | ✅ SI v2 `deploy/shadow_logger.py` | JSONL audit trail; `orchestrator/logs/shadow_decisions.jsonl` |
| FleetRiskManager | ✅ Deployed | `freqtrade/shared/fleet_risk_manager.py` |
| Watchdog domain | ✅ Defined (#23) | Separate ownership per ADR |
| CI safety gates | 🔶 Pending (#31) | Not yet implemented |
| Status dashboard | 🔶 Pending (#30) | Not yet built |

---

## 5. Issue Backlog (Open)

All open issues: [github.com/GoLukeEnviro/trading-hub/issues](https://github.com/GoLukeEnviro/trading-hub/issues)

### Phase 0 — Stabilization & Foundation

| Issue | Title | Priority |
|-------|-------|----------|
| [#48](https://github.com/GoLukeEnviro/trading-hub/issues/48) | Phase 0 Tracker | Highest (tracker) |
| [#43](https://github.com/GoLukeEnviro/trading-hub/issues/43) | Fix FleetRiskManager dry-run entry decision blocker | High (blocker) |
| [#44](https://github.com/GoLukeEnviro/trading-hub/issues/44) | Runtime / Docker Compose ownership and healthcheck hardening | High |
| [#45](https://github.com/GoLukeEnviro/trading-hub/issues/45) | Connect Shadowlock Writer to incremental Indexer trigger | High |
| [#46](https://github.com/GoLukeEnviro/trading-hub/issues/46) | Branch, PR, and worktree hygiene execution plan | Medium |
| [#47](https://github.com/GoLukeEnviro/trading-hub/issues/47) | Canonical roadmap, README, and .gitignore baseline | Medium |

### Older Backlog (pre-Phase 0)

| Issue | Title | Type | Priority |
|-------|-------|------|----------|
| [#12](https://github.com/GoLukeEnviro/trading-hub/issues/12) | shadowlock_indexer.py — SQLite read-cache | `enhancement` | Medium |
| [#17](https://github.com/GoLukeEnviro/trading-hub/issues/17) | Execute controlled read-only runtime probe | `approval-gated` | Low (blocked) |
| [#20](https://github.com/GoLukeEnviro/trading-hub/issues/20) | Design read-only Docker/Freqtrade adapter contracts | `design` | Low |
| [#21](https://github.com/GoLukeEnviro/trading-hub/issues/21) | Implement read-only runtime adapter prototypes | `code-safe` | Low (blocked by #20) |
| [#24](https://github.com/GoLukeEnviro/trading-hub/issues/24) | Plan real ai4trade REST integration | `design` | Low |
| [#25](https://github.com/GoLukeEnviro/trading-hub/issues/25) | Design Telegram approval live adapter | `design` | Low |
| [#26](https://github.com/GoLukeEnviro/trading-hub/issues/26) | Design cron activation ceremony | `design` | Low |
| [#27](https://github.com/GoLukeEnviro/trading-hub/issues/27) | Plan v1 residue archive and migration closure | `plan` | Low |
| [#28](https://github.com/GoLukeEnviro/trading-hub/issues/28) | Design live strategy mutation approval ceremony | `design` | Low |
| [#29](https://github.com/GoLukeEnviro/trading-hub/issues/29) | Design runtime shadow-mode observation | `design` | Low |
| [#30](https://github.com/GoLukeEnviro/trading-hub/issues/30) | Build status dashboard/reporting | `feature` | Medium |
| [#31](https://github.com/GoLukeEnviro/trading-hub/issues/31) | Strengthen CI safety gates | `feature` | Medium |
| [#34](https://github.com/GoLukeEnviro/trading-hub/issues/34) | Prepare real market-data readiness | `feature` | Low |
| [#35](https://github.com/GoLukeEnviro/trading-hub/issues/35) | Define proposal scoring and promotion policy | `design` | Low |
| [#38](https://github.com/GoLukeEnviro/trading-hub/issues/38) | Fix rebel-bot Telegram polling conflict | `bug` | Medium |
| [#39](https://github.com/GoLukeEnviro/trading-hub/issues/39) | Fix watchdog connectivity target | `bug` | Medium |
| [#40](https://github.com/GoLukeEnviro/trading-hub/issues/40) | Re-run dry-run signal validation after F-RM fix | `validation` | Low (blocked by #43) |

---

## 6. Repository Structure

```
self_improvement_v2/
├── src/si_v2/              # Source code
│   ├── approve/            # Approval gate (uses ShadowLogger)
│   ├── deploy/             # Deployment plans, ShadowLogger
│   └── ...                 # Other packages
├── tests/                  # Test suite (457 items)
├── docs/                   # Documentation (this index)
│   ├── ADR_*.md            # ADRs
│   ├── AI4TRADE_*.md       # ai4trade integration docs
│   ├── FULL_E2E_*.md       # Pipeline documentation
│   ├── REAL_ADAPTER_*.md   # Real adapter designs
│   ├── STRATEGY_ADAPTER_*.md
│   └── V1_TO_V2_*.md       # Migration docs
├── scripts/                # CLI scripts
├── reports/                # Generated reports (runtime probe, etc.)
├── cron_defs/              # Cron job definitions
└── pyproject.toml          # Project config (ruff, mypy, pytest)

docs/                        # Root docs
├── specs/                   # Specifications
│   └── runtime-safety-contract.md
├── decisions/               # Architecture decisions
│   ├── ADR-2026-06-10-watchdog-ownership.md
│   └── 2026-05-14-soul-agents-sync.md
├── context/                 # Append-only historical reports
├── prompts/                 # Agent prompt files
└── state/                   # Operational state snapshots
```

---

## 7. Test Baseline

| Metric | Value |
|--------|-------|
| Total tests | 457 items |
| Passing | 456 |
| Skipped | 1 |
| Failing | 0 |
| Python | 3.13 |
| Linter | ruff (strict) |
| Types | mypy (strict, disallow-any) |

---

## 8. Commit Chain (Recent)

```
f4a5665 docs(si-v2): decide watchdog ownership boundary (#23)
995158b docs(si-v2): define RiskGuard/ShadowLogger runtime safety contract (#22)
abbc621 [SI v2] Self-Improvement foundation, safety gates, dry-run pipeline (#36)
4bdca57 fix(tools): support multiple Freqtrade trade DB schemas (#42)
b8e6f49 chore: remove old duplicate orchestrator prompt
71596d3 feat: add Regime Detector v1 + Shadowlock Indexer
7bcd66e docs: add implementation status and next steps
1d79d4a docs: add consolidated SI v1 master architecture
eaf71b4 docs: add context-architecture spec and agent prompt files
b2ef4c0 feat: add comprehensive SI signal intelligence loop spec
```

---

## 9. Related Repositories

| Repository | Description | Integration Status |
|-----------|-------------|-------------------|
| [GoLukeEnviro/trading-hub](https://github.com/GoLukeEnviro/trading-hub) | This repository | Primary |
| [GoLukeEnviro/ai4trade-bot](https://github.com/GoLukeEnviro/ai4trade-bot) | Signal provider (Rainbow/Legacy) | Read-only via adapter protocol |
| [ai-hedge-fund-crypto](https://github.com/GoLukeEnviro/ai-hedge-fund-crypto) | Signal generation core | Container-based deployment |
