# Operator Rehearsal Approval Packet

> **SI v2 — Human Operator Approval Packet for Rehearsal Proposals**
>
> This template makes a future rehearsal approval explicit, bounded, and
> safe. It must be completed and signed by a human operator before any
> rehearsal can be executed.
>
> **This packet does not approve rehearsal execution by itself.**
> It documents the human operator's review and approval of a rehearsal
> proposal created under the #135 planning gate.

---

## 1. Proposal Reference

| Field | Value |
|-------|-------|
| **Proposal ID** | |
| **Proposal Name** | |
| **Proposed By** | |
| **Proposed Date (UTC)** | |
| **Rehearsal Mode** | ☐ Read-only / ☐ Shadow-mode / ☐ Controlled Dry-run |
| **Planning Gate Verdict** | ☐ GREEN / ☐ YELLOW |

---

## 2. Planning Gate Verification

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| PG-01 | Prerequisites #127–#132 verified | ☐ PASS / ☐ FAIL | |
| PG-02 | Forbidden conditions checked (F-01..F-10) | ☐ PASS / ☐ FAIL | |
| PG-03 | Stop-condition matrix (#136) evaluated | ☐ PASS / ☐ FAIL | |
| PG-04 | Evidence bundle plan (#137) referenced | ☐ PASS / ☐ FAIL | |
| PG-05 | Observation plan (#139) included | ☐ PASS / ☐ FAIL | |
| PG-06 | All required planning fields present | ☐ PASS / ☐ FAIL | |
| PG-07 | Scope boundaries clear and documented | ☐ PASS / ☐ FAIL | |
| PG-08 | Residual risks documented | ☐ PASS / ☐ FAIL | |

---

## 3. Allowed Actions

The following actions are approved **within** the rehearsal scope only:

- [ ] Read-only file inspection
- [ ] Read-only config inspection
- [ ] Read-only health check queries
- [ ] Read-only SQLite queries against dry-run bot databases
- [ ] Read-only signal file reads
- [ ] Log inspection (tail only, no modification)
- [ ] Observation note recording
- [ ] Evidence collection per #137 plan

---

## 4. Forbidden Actions

The following actions are **never** approved in this rehearsal:

- [ ] Setting `dry_run=false` or live trading configuration
- [ ] Placing real or simulated orders
- [ ] Connecting to exchanges
- [ ] Modifying Freqtrade configs
- [ ] Modifying strategy logic
- [ ] Modifying signal thresholds or risk parameters
- [ ] Running Docker commands
- [ ] Starting or stopping containers
- [ ] Deploying any code or configuration
- [ ] Accessing API keys, secrets, tokens, or wallet data
- [ ] Creating financial exposure of any kind
- [ ] Calling any write-capable adapter
- [ ] Modifying cron jobs or schedules
- [ ] Making network calls to external services beyond health checks

---

## 5. Human Approval Fields

| Field | Value |
|-------|-------|
| **Operator Name** | |
| **Operator Role** | |
| **Review Date (UTC)** | |
| **Approval Token** | `APPROVE_REHEARSAL_<YYMMDD>_<random4>` |
| **Approval Scope** | (copy from proposal scope) |
| **Rehearsal Duration Limit** | (max hours/minutes) |
| **Rollback Contact** | |

---

## 6. Non-Live Statement

> **I confirm that this rehearsal:**
>
> - Does not authorise live trading.
> - Does not authorise `dry_run=false`.
> - Does not authorise real exchange orders.
> - Does not authorise the use of real API keys or secrets.
> - Does not authorise financial exposure.
> - Is bounded to the scope defined in the proposal.
> - Will be aborted immediately if any forbidden condition is triggered.
>
> **I understand that violation of these boundaries constitutes a safety
> incident and must be reported, documented, and escalated.**
>
> Signed: ________________________
> Date:   ________________________ (UTC)

---

## 7. References

| Reference | Link |
|-----------|------|
| Controlled rehearsal planning gate (#135) | `self_improvement_v2/rehearsal/controlled_rehearsal_planning_gate.md` |
| Stop-condition and abort matrix (#136) | `self_improvement_v2/rehearsal/rehearsal_stop_condition_matrix.json` |
| Evidence bundle plan (#137) | `self_improvement_v2/rehearsal/rehearsal_evidence_bundle_plan.md` |
| Read-only observation plan (#139) | `self_improvement_v2/rehearsal/read_only_observation_plan.md` |

---

## 8. Change Log

| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Initial version | SI v2 (#138) |

---

*Maintained at `self_improvement_v2/rehearsal/operator_rehearsal_approval_packet.md`*
*Created as part of #138 — Operator Approval Packet Template*
