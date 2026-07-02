# Production Alerting Readiness Gate

> **Status:** Draft · **B4** — required before live canary transition
> **Date:** 2026-07-02
> **Author:** SI v2 Meta-Orchestrator
> **Dependencies:** B1 (Live Readiness Audit), B2 (Risk Limits), B3 (Runbooks)

---

## Purpose

The Production Alerting Gate is a **hard readiness gate** that blocks live
preparation if required production alerts are not configured and proven. It
must pass before C1 (Human Approval Gate for Live Canary) can proceed.

---

## Gate Checks

| # | Check | What It Verifies | Blocks? |
|---|-------|------------------|---------|
| 1 | Alert config evidence | Kill switch file, runbooks, risk limits spec, incident response runbook exist | ✅ |
| 2 | Delivery proof | Telegram adapter module and test exist | ✅ |
| 3 | Drawdown alert proof | Kill switch module and procedure doc exist | ✅ |
| 4 | Runtime failure alert proof | Scheduler cron dir and active cycle runner script exist | ✅ |

---

## Expected Artifacts

### Alert Config Evidence

| Artifact | Path | Required |
|----------|------|----------|
| Kill switch file | `freqtrade/shared/kill_switch.py` | ✅ |
| Kill switch runbook | `docs/runbooks/kill-switch.md` | ✅ |
| RiskGuard runbook | `docs/runbooks/riskguard-pair-universe.md` | ✅ |
| Incident response runbook | `docs/specs/incident-response-runbooks.md` | ✅ |
| Risk limits spec | `docs/specs/production-risk-limits-spec.md` | ✅ |

### Delivery Proof

| Artifact | Path | Required |
|----------|------|----------|
| Telegram adapter module | `self_improvement_v2/src/si_v2/adapters/telegram_adapter.py` | ✅ |
| Telegram adapter test | `self_improvement_v2/tests/test_telegram_adapter.py` | ✅ |

### Drawdown Alert Proof

| Artifact | Path | Required |
|----------|------|----------|
| Kill switch module | `freqtrade/shared/kill_switch.py` | ✅ |
| Kill switch procedure | `docs/references/freqtrade-kill-switch-procedure.md` | ✅ |

### Runtime Failure Alert Proof

| Artifact | Path | Required |
|----------|------|----------|
| Scheduler cron directory | `orchestrator/cron/` | ✅ |
| Active cycle runner script | `orchestrator/scripts/si-v2-active-cycle-runner.sh` | ✅ |

---

## Output

| Status | Meaning |
|--------|---------|
| `PRODUCTION_ALERTING_READY` | All 4 checks pass. Live preparation may proceed to C1. |
| `PRODUCTION_ALERTING_BLOCKED` | One or more checks fail. Review blocked reasons and fix before re-running. |

---

## Integration

The gate is invoked as part of the live readiness pipeline:

```text
B1 Live Readiness Audit
  → B2 Risk Limits Spec
    → B3 Incident Response Runbooks
      → B4 Production Alerting Gate  ← YOU ARE HERE
        → C1 Human Approval Gate for Live Canary
```

---

## Related Documents

| Document | Location |
|----------|----------|
| Production Alerting Gate module | `self_improvement_v2/src/si_v2/readiness/production_alerting_gate.py` |
| Production Alerting Gate tests | `self_improvement_v2/tests/test_production_alerting_gate.py` |
| Production Risk Limits Spec | `docs/specs/production-risk-limits-spec.md` |
| Incident Response Runbooks | `docs/specs/incident-response-runbooks.md` |
| Live Readiness Evidence Audit | `var/si_v2/live_readiness_audit/live_readiness_evidence_audit.md` |