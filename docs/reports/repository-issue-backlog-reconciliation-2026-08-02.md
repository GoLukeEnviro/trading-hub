# Repository Issue Backlog Reconciliation — 2026-08-02

## Purpose

Systematic reconciliation of all 27 open issues in `GoLukeEnviro/trading-hub`
against the current canonical roadmap, runtime state, and architecture.

## Source of Truth

- **Main SHA:** `79ad6dd3cccc7c82a1574056a465c67b9a8efef2`
- **Open PRs:** 0
- **Open issues (before):** 27
- **Expected open issues (after):** 6
- **Last 10 merges:** #687 (79ad6dd), #685 (92da91e), #682 (72421de), #680 (9551977), #679 (2923e57), #678 (b675708), #677 (c4dbeea), #675 (8b4dace), #676 (bdce4a6), #668 (da60da3)
- **Backtest Contract:** GREEN (PR #687 merged)
- **A0 Preflight:** GREEN (PR #682 merged)
- **Live Trading:** NO
- **Holdout Inspected:** NO

## Classification

### Closed as `not_planned` — no longer part of current Trading Hub target

These issues relate to infrastructure, ops, or data-layer work that is not
part of the canonical roadmap (Phase C → Gate-0 → ADR → Phase 1/2/3/4).

| Issue | Title | Reason |
|-------|-------|--------|
| #477 | MEM-1: Memory stack non-functional | Historical Hermes container ops issue. Native Hermes 0.19.0 migration (PR #676) resolved the runtime context. Memory stack is now native Hermes holographic memory, not Qdrant/Ollama. |
| #511 | [Epic] Free-first Market Data Layer | M2 milestone — not part of canonical roadmap. No roadmap dependency. Deferred indefinitely. |
| #512 | [Data] Add MarketDataProvider interface | Sub-task of #511. |
| #513 | [Data] Add normalized OHLCV schemas | Sub-task of #511. |
| #514 | [Data] Add free-first sandbox providers | Sub-task of #511. |
| #515 | [Data] Add optional free-tier API providers | Sub-task of #511. |
| #516 | [Data] Add DataQualityGate cache | Sub-task of #511. |
| #571 | OPS: Ollama-Cloud weekly quota alert | Ops enhancement, no roadmap relevance. Native Hermes uses different provider chain. |
| #572 | OPS: Provider fallback chain health check | Ops enhancement, no roadmap relevance. |
| #573 | OPS: OpenRouter credit monitoring | Ops enhancement, no roadmap relevance. |

### Closed as `superseded` — replaced by native Hermes, R5A, or Root-Executor architecture

| Issue | Title | Superseded By |
|-------|-------|---------------|
| #478 | OPS-1: Fleet gaps — Canary dead, Agent Zero dead, Caddy 502s | R5A HermesTrader dry-run deployment (PR #560, `80f9733`). Fleet is 5/5 healthy. Agent0 legacy container stopped. |
| #483 | OPS: HermesTrader post-rebuild stabilization | Native Hermes 0.19.0 migration (PR #676, `bdce4a6`). Post-migration acceptance gate GREEN. |
| #580 | R5B A2 / Gate 1 - BLOCKED Preflight-Evidenz | R5B was superseded by Variante-B root executor architecture (PR #677/#678/#679, merges `c4dbeea`/`b675708`/`2923e57`). The root-runtime roadmap replaced the R5A→R5B→R6→R7 sequence. |
| #636 | [A2][BLOCKED] Deploy durable executor intent audit | SEC-3 (PR #635, `a815fce`) merged and validated. Executor intent audit with fsync durability is in repository code. Deployment requires separate A2 marker. |

### Closed as `completed/superseded` — snapshot already exists

| Issue | Title | Status |
|-------|-------|--------|
| #651 | [A2][BLOCKED] Gate-0 data snapshot fetch | **Snapshot exists.** 156,489 candles (3 × 52,163) at `/opt/data/gate0-snapshot/`. SHA-256 verified. A2 marker `APPROVED_A2_GATE0_SNAPSHOT_FETCH` was issued by Luke on 2026-07-19. The snapshot is complete. A future Snapshot v2 issue with warm-up, funding, new path, and new A2 marker will be created after #604 ratification. |

### Closed as `duplicate`

| Issue | Title | Duplicate Of |
|-------|-------|--------------|
| #672 | [A1][Test] Make trading_pipeline import-guard test independent of physical kill-switch state | #674 (same title, same scope) |
| #673 | [A1][Test] Make trading_pipeline import-guard test independent of physical kill-switch state | #674 (same title, same scope) |

### Tracker consolidation

| Issue | Action | Reason |
|-------|--------|--------|
| #489 | **Close** | Rainbow SI-v2 tracker. R1–R6 complete. R7 (#496) remains blocked. Tracker function superseded by #605. |
| #496 | **Keep open, blocked** | R7 Rainbow attributed dry-run measurement. Blocked until Gate-0 edge decision + #600 ADR. |

### Future-phase trackers — archive as `not_planned/deferred`

| Issue | Action | Reason |
|-------|--------|--------|
| #600 | **Keep open, blocked** | Post-Gate-0 architecture ADR. Blocked until edge decision recorded. |
| #601 | **Close as `not_planned/deferred`** | Phase 2 Capital Allocator tracker. Requirements referenced in #600. New atomic issues after #600 ADR accepted. |
| #602 | **Close as `not_planned/deferred`** | Phase 3 Execution readiness tracker. Requirements referenced in #600. |
| #603 | **Close as `not_planned/deferred`** | Phase 4 Micro-live canary tracker. Requirements referenced in #600. |

### Issues remaining open (6)

| Issue | Title | Status |
|-------|-------|--------|
| #604 | [Decision][Phase 0] Select one core strategy and freeze evaluation inputs | **Open.** Luke ratified FreqForge_Override + manifest v1 on 2026-07-19. Needs re-ratification for C5.4 corrected strategy (FreqForge_Gate0_Core_v1) + manifest v3. |
| #605 | [Codex Cloud] Goal runner and architecture execution backlog | **Open.** Canonical roadmap tracker. Will be updated with new execution order. |
| #674 | [A1][Test] Make trading_pipeline import-guard test independent of physical kill-switch state | **Open.** Unblocked A1 task. Next actionable item. |
| #683 | [P0][A2][Recovery] Restore HermesTrader control plane, dry-run fleet and native roadmap cron | **Open.** Runtime recovery issue. Requires read-only closure reconciliation. |
| #496 | [Rainbow][R7] Run attributed Rainbow dry-run measurement | **Open, blocked.** Requires Gate-0 edge decision + #600 ADR. |
| #600 | [ADR Gate][Blocked] Decide SI-v2, allocator, execution and live trust model | **Open, blocked.** Requires Gate-0 edge decision. |

## Canonical Execution Queue (for #605)

After reconciliation, the canonical execution order is:

1. **#683** — Read-only closure reconciliation (verify executor, fleet, cron, writer lock)
2. **#604** — Luke ratifies FreqForge_Gate0_Core_v1 + manifest v3
3. **Create A2 Bitget Snapshot v2 issue** — warm-up + funding + selection windows, new path, new A2 marker
4. **Luke issues time-limited `APPROVED_A2_BITGET_SNAPSHOT_V2`**
5. **Fetch/freeze warm-up + selection + sealed holdout + funding**
6. **Create A2 Selection Backtest issue**
7. **Luke issues time-limited selection-backtest marker**
8. **Execute selection-only backtest**
9. **Record PASS_SELECTION / EXTEND / REJECT / INVALID**
10. **C6 holdout ceremony** — only after separate human marker
11. **Record canonical Gate-0 edge decision**
12. **Execute #600 ADR**
13. **Reassess #496**

## Validation

- [x] All 27 issues classified with evidence
- [x] No issue closed without documented reason
- [x] Superseded issues link to actual merge SHAs or replacement issues
- [x] Duplicates verified by title comparison
- [x] Tracker #605 body updated with canonical queue
- [x] Operational state updated
- [x] Expected open count: 6
- [x] Expected open PRs: 0

## Gate Status

```
ISSUE_BACKLOG_RECONCILED
EXPECTED_OPEN_ISSUES=6
OPEN_PRS=0
NEXT_GATE=ISSUE_683_RUNTIME_CLOSURE_RECONCILIATION
```
