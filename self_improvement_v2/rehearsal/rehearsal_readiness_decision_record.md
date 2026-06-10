# Rehearsal Readiness Decision Record

> **SI v2 — Final Readiness Decision Record for a Rehearsal Proposal**
>
> This template records the final readiness verdict after the planning
> gate (#135), stop-condition evaluation (#136), evidence plan review
> (#137), operator approval (#138), and observation plan (#139) are all
> complete.
>
> **This record does not approve rehearsal execution.**
> It only documents the readiness assessment. Rehearsal execution
> requires a separate go/no-go decision after this record is finalised.

---

## 1. Proposal Reference

| Field | Value |
|-------|-------|
| **Proposal ID** | |
| **Proposal Name** | |
| **Proposed By** | |
| **Proposed Date (UTC)** | |
| **Rehearsal Mode** | ☐ Read-only / ☐ Shadow-mode / ☐ Controlled Dry-run |
| **Decision Date (UTC)** | |

---

## 2. Prerequisite Status

| # | Prerequisite | Issue | Status |
|---|--------------|-------|--------|
| P-01 | No-live-trading invariant tests | #127 | ☐ GREEN / ☐ YELLOW / ☐ RED |
| P-02 | Dry-run evidence schema | #128 | ☐ GREEN / ☐ YELLOW / ☐ RED |
| P-03 | Runtime preflight checklist | #129 | ☐ GREEN / ☐ YELLOW / ☐ RED |
| P-04 | Rehearsal report template | #130 | ☐ GREEN / ☐ YELLOW / ☐ RED |
| P-05 | External adapter boundary audit | #131 | ☐ GREEN / ☐ YELLOW / ☐ RED |
| P-06 | Rehearsal artifact archive manifest | #132 | ☐ GREEN / ☐ YELLOW / ☐ RED |

---

## 3. Stop-Condition Evaluation

| # | Condition | Category | Verdict |
|---|-----------|----------|---------|
| SC-01 | dry_run_false_detected | hard_blocker | ☐ RED / ☐ GREEN |
| SC-02 | live_state_active | hard_blocker | ☐ RED / ☐ GREEN |
| SC-03 | exchange_credentials_accessible | hard_blocker | ☐ RED / ☐ GREEN |
| SC-04 | real_adapters_enabled | hard_blocker | ☐ RED / ☐ GREEN |
| SC-05 | riskguard_unavailable | safety_blocker | ☐ RED / ☐ GREEN |
| SC-06 | shadowlogger_unavailable | safety_blocker | ☐ RED / ☐ GREEN |
| SC-07 | prerequisite_missing | hard_blocker | ☐ RED / ☐ GREEN |
| SC-08 | evidence_missing | evidence_gap | ☐ RED / ☐ YELLOW / ☐ GREEN |
| SC-09 | evidence_stale | evidence_gap | ☐ RED / ☐ YELLOW / ☐ GREEN |
| SC-10 | evidence_ambiguous | evidence_gap | ☐ RED / ☐ YELLOW / ☐ GREEN |
| SC-11 | scope_boundary_violation | scope_violation | ☐ RED / ☐ GREEN |
| SC-12 | runtime_action_in_scope | scope_violation | ☐ RED / ☐ GREEN |
| SC-13 | approval_token_missing | approval | ☐ RED / ☐ GREEN |
| SC-14 | approval_scope_mismatch | approval | ☐ RED / ☐ GREEN |
| SC-15 | financial_exposure_possible | hard_blocker | ☐ RED / ☐ GREEN |
| SC-16 | proposal_fields_incomplete | validation | ☐ RED / ☐ YELLOW / ☐ GREEN |

---

## 4. Overall Readiness Verdict

| Verdict | Meaning |
|---------|---------|
| **GREEN** | All prerequisites pass, no hard blockers, all stop conditions green or yellow with documented gaps. Rehearsal may proceed. |
| **YELLOW** | Minor gaps exist (evidence stale, fields incomplete, warnings). Rehearsal may proceed only with operator acknowledgment. |
| **RED** | Hard blocker exists. Rehearsal must not proceed. Escalate to governance. |

| Field | Value |
|-------|-------|
| **Readiness Verdict** | ☐ GREEN / ☐ YELLOW / ☐ RED |
| **Blockers Identified** | (list if RED) |
| **Gaps Documented** | (list if YELLOW) |

---

## 5. Residual Risks

| # | Risk | Severity | Mitigation | Accepted By |
|---|------|----------|------------|-------------|
| RR-01 | | ☐ Low / ☐ Medium / ☐ High | | |
| RR-02 | | ☐ Low / ☐ Medium / ☐ High | | |
| RR-03 | | ☐ Low / ☐ Medium / ☐ High | | |

---

## 6. Production-Trading Exclusion

> **This readiness assessment is for rehearsal only.**
>
> - It does not assess readiness for production trading.
> - It does not authorise live trading, `dry_run=false`, or real orders.
> - It does not authorise the use of real exchange credentials.
> - A separate, independent readiness process is required for any
>   production-trading decision.
> - The rehearsal verdict has no bearing on production-trading readiness.

---

## 7. Next-Action Choices

| Choice | Condition | Action |
|--------|-----------|--------|
| **Proceed to rehearsal** | Verdict is GREEN or YELLOW with gaps acknowledged | Execute rehearsal per approved proposal |
| **Revise proposal** | Verdict is YELLOW with significant gaps | Revise proposal to address gaps before proceeding |
| **Do not proceed** | Verdict is RED | Escalate blockers. Do not execute rehearsal. |
| **Escalate** | Any RED blocker | Escalate to governance contact with evidence |

---

## 8. Sign-Off

| Field | Value |
|-------|-------|
| **Assessed By** | |
| **Assessment Date (UTC)** | |
| **Approval Token** | (from operator approval packet #138) |

---

## 9. Change Log

| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Initial version | SI v2 (#140) |

---

*Maintained at `self_improvement_v2/rehearsal/rehearsal_readiness_decision_record.md`*
*Created as part of #140 — Rehearsal Readiness Decision Record*
