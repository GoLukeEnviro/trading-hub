# SI-v2: Advance Self-Improvement Loop from ShadowProposal to Measured Iteration

**Status:** Backlog — Approval-Ready  
**Priority:** M  
**Dependencies:** PR #328 merged, Rainbow GREEN, scheduled cycle 061729Z GREEN

---

## Goal

Move from proposal generation to one controlled, human-approved, measurable SI-v2 improvement iteration: select the best ShadowProposal, prepare approval packet, create apply plan, measure effect.

---

## Acceptance Criteria

- ✅ Phase C proof merged (PR #328)
- ✅ Scheduled pre-Phase-C cycle GREEN (061729Z)
- ✅ ShadowProposal inventory created
- ✅ Best candidate selected: `65502d13` (freqforge, `reinforce_profitable_pair_cluster_v1`)
- ✅ Approval-ready report created
- ✅ Controlled apply plan created
- ⬜ Post-Phase-C scheduled cycle confirmed GREEN (12:17 UTC)
- ⬜ Apply executed only with `APPROVE_SI_V2_CONTROLLED_APPLY_65502d13`
- ⬜ Measurement: 2 cycles post-apply
- ⬜ Rollback plan documented

---

## Current State

| Layer | Status |
|-------|--------|
| Rainbow | GREEN (PID 204229, 50 signals, persistent paths) |
| Phase A/B/C | Complete |
| Freqtrade fleet | 4/4 dry-run bots, GREEN |
| SI-v2 loop | GREEN, 0 mutations, PAUSED/L3 |
| Best proposal | `65502d13` APPROVAL_READY |

---

## Selected Candidate

| Attribute | Value |
|-----------|-------|
| Proposal | `65502d13a99bfadd` |
| Bot | `freqtrade-freqforge` |
| Hypothesis | `reinforce_profitable_pair_cluster_v1` |
| Walk-forward | +23.88 USDT, PF 1.56, DD 2.19%, 77 trades |
| Mutation policy | `safe_parameter_overlay_only` |
| Risk | LOW |

---

## Approval Required

```bash
export APPROVE_SI_V2_CONTROLLED_APPLY_65502d13="APPROVE"
```

---

## Bezug zum Self-Improvement Loop

This is the bridge from "analyze → ShadowProposal" into "approve → apply → measure".

```
4 bots → Rainbow → SI-v2 Cycle → ShadowProposals → SELECT → APPROVE → APPLY → MEASURE → next iteration
```

---

## Related Reports

- `docs/reports/si-v2-shadowproposal-inventory-after-phase-c-2026-06-23.md`
- `docs/reports/si-v2-approval-ready-shadowproposal-2026-06-23.md`
- `docs/plans/si-v2-controlled-apply-plan-2026-06-23.md`
- `docs/reports/si-v2-post-phase-c-scheduled-cycle-proof-2026-06-23.md`
