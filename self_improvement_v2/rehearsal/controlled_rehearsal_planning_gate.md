# Controlled Rehearsal Planning Gate

> **SI v2 — Mandatory Planning Gate Before Any Rehearsal Proposal**
>
> This gate defines the requirements, dependencies, approval fields, and
> forbidden conditions that must be satisfied before any read-only,
> shadow-mode, or controlled dry-run rehearsal can be proposed.
>
> **This gate does not approve rehearsal execution.**
> It only approves the creation of a rehearsal proposal.
> Separate approval is required for actual rehearsal execution.

---

## 1. Purpose

The planning gate ensures that:

- All prerequisite governance layers (#127–#132) are in place and validated.
- The rehearsal scope is explicitly bounded and documented.
- Forbidden conditions are checked before any proposal is created.
- The operator has a clear record of what is and is not approved.
- No runtime action, Docker command, Freqtrade operation, exchange
  connection, or trading decision is made during planning.

---

## 2. Prerequisite Dependencies

| # | Artifact | Issue | Status Requirement |
|---|----------|-------|--------------------|
| P-01 | No-live-trading invariant tests | #127 | Must exist and pass |
| P-02 | Dry-run evidence schema | #128 | Must exist and be valid |
| P-03 | Runtime preflight checklist | #129 | Must exist and be reviewed |
| P-04 | Rehearsal report template | #130 | Must exist |
| P-05 | External adapter boundary audit | #131 | Must exist and be reviewed |
| P-06 | Rehearsal artifact archive manifest | #132 | Must exist and be valid |

**Gate is BLOCKED** if any prerequisite is missing or not in a passing state.

---

## 3. Required Planning Fields

Every rehearsal proposal must include the following fields before it can
be submitted for operator review:

| Field | Required | Description |
|-------|----------|-------------|
| **Proposal ID** | ✅ | Unique identifier (`rp-<YYYYMMDD>-<HHMMSS>-<random4>`) |
| **Proposal Name** | ✅ | Short human-readable name |
| **Proposed By** | ✅ | Agent or operator identifier |
| **Proposed Date (UTC)** | ✅ | Timestamp of proposal creation |
| **Rehearsal Mode** | ✅ | One of: `read-only` / `shadow-mode` / `controlled-dry-run` |
| **Scope Description** | ✅ | What will be observed, tested, or measured |
| **Out-of-Scope** | ✅ | What is explicitly excluded |
| **Duration Estimate** | ✅ | Expected duration (minutes/hours) |
| **Target Components** | ✅ | List of bots, services, or modules involved |
| **Prerequisite Status** | ✅ | Reference to prerequisite check results |
| **Stop Conditions** | ✅ | Reference to #136 stop-condition matrix |
| **Evidence Plan** | ✅ | Reference to #137 evidence bundle plan |
| **Observation Plan** | ✅ | Reference to #139 observation plan |
| **Residual Risks** | ✅ | Risks identified during planning |
| **Approval Token** | ✅ | `APPROVE_REHEARSAL_PROPOSAL_<YYMMDD>` |

---

## 4. Forbidden Conditions

The following conditions **must all be false** for a rehearsal proposal
to be valid. If any condition is true, the gate is **RED** and the
proposal must not be created.

| # | Condition | Status |
|---|-----------|--------|
| F-01 | `dry_run=false` is set in any Freqtrade config | ☐ Must be false |
| F-02 | `LIVE_APPROVED` or `LIVE_ACTIVE` state is active | ☐ Must be false |
| F-03 | Exchange API keys or secrets are accessible | ☐ Must be false |
| F-04 | `SI_V2_ENABLE_REAL_ADAPTERS=1` is set | ☐ Must be false |
| F-05 | RiskGuard is unavailable during proposal review | ☐ Must be available |
| F-06 | ShadowLogger is unavailable during proposal creation | ☐ Must be available |
| F-07 | Proposal would trigger any runtime action | ☐ Must be false |
| F-08 | Proposal would modify any configuration | ☐ Must be false |
| F-09 | Proposal would create financial exposure | ☐ Must be false |
| F-10 | Proposal would touch credentials or secrets | ☐ Must be false |

---

## 5. Gate Verdicts

| Verdict | Meaning | Next Action |
|---------|---------|-------------|
| **GREEN** | All prerequisites met, forbidden conditions clear, planning fields complete | Proposal may proceed to operator review |
| **YELLOW** | Minor gaps (e.g. missing optional field, stale review date) | Document gaps, may proceed with operator awareness |
| **RED** | Prerequisite missing, forbidden condition true, or required field incomplete | Do not proceed. Escalate to governance contact |

---

## 6. Escalation

If the gate verdict is **RED**:

1. Document the blocker with evidence (paths, logs, timestamps).
2. Identify which prerequisite or condition is failing.
3. Do not bypass, override, or suppress the blocker.
4. Report to the project governance contact.
5. Only proceed after the blocker is resolved and re-verified.

---

## 7. No-Approval Statement

> **This planning gate does not approve rehearsal execution.**
> It only verifies that a rehearsal proposal may be created.
> Rehearsal execution requires a separate, explicit human approval
> token after the proposal is reviewed.
>
> **Live trading, `dry_run=false`, real orders, real exchange credentials,
> and any financial exposure remain strictly prohibited at all phases.**

---

## 8. Change Log

| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Initial version | SI v2 (#135) |

---

*Maintained at `self_improvement_v2/rehearsal/controlled_rehearsal_planning_gate.md`*
*Created as part of #135 — Controlled Rehearsal Planning Gate*
