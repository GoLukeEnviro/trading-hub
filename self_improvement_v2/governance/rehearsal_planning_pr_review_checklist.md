# Merge-Readiness Review Checklist for SI v2 Rehearsal Planning PRs

> **SI v2 — Mandatory Review Checklist Before Merging Any Rehearsal-Planning PR**
>
> This checklist defines required PR metadata, CI and validation requirements,
> review verdicts, hard blockers, and acceptable residual risks.
>
> **This checklist does not approve production trading.**

---

## 1. Required PR Metadata

| # | Check | Required | Status |
|---|-------|----------|--------|
| M-01 | PR state is OPEN | ✅ | ☐ |
| M-02 | PR is not a draft | ✅ | ☐ |
| M-03 | Base branch is `main` | ✅ | ☐ |
| M-04 | Head branch matches expected | ✅ | ☐ |
| M-05 | Head SHA matches expected (guarded) | ✅ | ☐ |
| M-06 | PR is mergeable (no conflicts) | ✅ | ☐ |
| M-07 | Merge state is CLEAN | ✅ | ☐ |
| M-08 | Required issue references present in PR body | ✅ | ☐ |

---

## 2. CI and Validation Requirements

| # | Check | Required | Status |
|---|-------|----------|--------|
| V-01 | `offline-smoke` CI workflow passed | ✅ | ☐ |
| V-02 | `compileall` passes (no syntax errors) | ✅ | ☐ |
| V-03 | `pytest self_improvement_v2 -q` passes | ✅ | ☐ |
| V-04 | `ruff check self_improvement_v2` passes | ✅ | ☐ |
| V-05 | All JSON files parse correctly | ✅ | ☐ |
| V-06 | `git diff --check` has no whitespace errors | ✅ | ☐ |
| V-07 | Planning pipeline validator passes with GREEN verdict | ✅ | ☐ |
| V-08 | Proposal package schema validates all fixtures | ✅ | ☐ |
| V-09 | Redaction checks pass (safe → GREEN, unsafe → RED) | ✅ | ☐ |

---

## 3. Review Verdicts

| Verdict | Meaning | Next Action |
|---------|---------|-------------|
| **GREEN** | All required checks pass, no hard blockers, residual risks accepted. | May merge after human approval. |
| **YELLOW** | All required checks pass, but minor concerns exist (ambiguous wording, superficial tests, missing cross-artifact consistency). | May merge with explicit human acknowledgment of concerns. |
| **RED** | Hard blocker present: live-trading path, dry_run=false, credentials, runtime activation, broken validation, or non-fail-closed semantics. | Do not merge. Escalate. |

---

## 4. Hard Blockers

The following conditions are **hard blockers**. If any is true, the
verdict is **RED** and the PR must not be merged:

| # | Condition | Verification |
|---|-----------|-------------|
| H-01 | PR introduces `dry_run=false` or live trading mode | Code review + scan |
| H-02 | PR introduces exchange credentials, API keys, secrets, tokens, wallet data | Code review + scan |
| H-03 | PR introduces Docker, Freqtrade runtime, trading bot, or deployment commands | Code review |
| H-04 | PR breaks compilation, tests, or linting | CI status |
| H-05 | PR enables real adapters (`SI_V2_ENABLE_REAL_ADAPTERS=1`) | Code review |
| H-06 | PR changes risk parameters, signal thresholds, or strategy logic | Code review |
| H-07 | Planning pipeline validator returns RED verdict | Validator run |
| H-08 | Stop-condition matrix default verdict is not BLOCKED | Matrix review |

---

## 5. Safety Review

| # | Check | Status |
|---|-------|--------|
| S-01 | No runtime actions introduced | ☐ PASS / ☐ FAIL |
| S-02 | No production-trading approval introduced | ☐ PASS / ☐ FAIL |
| S-03 | All stop conditions fail closed | ☐ PASS / ☐ FAIL |
| S-04 | Governance artifacts explicitly state no-production-trading | ☐ PASS / ☐ FAIL |
| S-05 | Credentials, secrets, tokens confirmed absent | ☐ PASS / ☐ FAIL |

---

## 6. Acceptable Residual Risks

The following residual risks are acceptable for rehearsal-planning PRs:

- Governance-only, not automated (manual verification required)
- Individual artifacts tested, not full end-to-end pipeline
- Observation adapters not yet implemented
- Schema may evolve with future requirements

Any residual risk outside this list must be explicitly documented
and accepted before merging.

---

## 7. Final Sign-Off

| Field | Value |
|-------|-------|
| **Reviewer** | |
| **Review Date (UTC)** | |
| **Verdict** | ☐ GREEN / ☐ YELLOW / ☐ RED |
| **Hard Blockers Identified** | (list if RED) |
| **Concerns Documented** | (list if YELLOW) |
| **Approval Token** | |
| **Merge Decision** | ☐ Approved / ☐ Not Approved |

---

## 8. Change Log

| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Initial version | SI v2 (#147) |

---

*Maintained at `self_improvement_v2/governance/rehearsal_planning_pr_review_checklist.md`*
*Created as part of #147 — Merge-Readiness Review Checklist*
