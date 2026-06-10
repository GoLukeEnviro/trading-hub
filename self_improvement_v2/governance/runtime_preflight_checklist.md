# Runtime Preflight Checklist Report

> **SI v2 — Mandatory Preflight Checklist Before Any Controlled Rehearsal**
>
> This checklist must be completed and verified **before** any controlled
> dry-run rehearsal or runtime probe is executed.
>
> **Live trading, `dry_run=false`, real orders, and real exchange
> credentials remain strictly prohibited.**
>
> This is a governance-only document. It does not authorise any runtime
> execution. It must be read and signed before proceeding to any
> controlled runtime action.

---

## 1. Preflight Status

| # | Check | Required | Status | Verified By | Date |
|---|-------|----------|--------|-------------|------|
| P-01 | All SI v2 offline tests pass (`pytest self_improvement_v2 -q`) | ✅ Must be GREEN | ☐ | | |
| P-02 | No-live-trading invariant tests pass (`test_live_trading_invariants.py`) | ✅ Must be GREEN | ☐ | | |
| P-03 | All source files compile (`python -m compileall self_improvement_v2`) | ✅ Must pass | ☐ | | |
| P-04 | Ruff linting passes (`ruff check self_improvement_v2`) | ✅ Must be clean | ☐ | | |
| P-05 | Dry-run evidence schema validated (`test_dry_run_evidence_schema.py`) | ✅ Must be GREEN | ☐ | | |
| P-06 | External adapter boundary audit exists and is reviewed | ✅ Must exist | ☐ | | |
| P-07 | Rehearsal artifact archive manifest exists and is valid | ✅ Must exist | ☐ | | |
| P-08 | Human approval gate checklist (#122) is signed | ✅ Must be signed | ☐ | | |
| P-09 | Live-readiness blocker inventory (#124) is reviewed | ✅ Must be reviewed | ☐ | | |
| P-10 | Phase 1 readiness verdict is GREEN or YELLOW | ✅ Must be GREEN/YELLOW | ☐ | | |
| P-11 | Quality gate verdict is GREEN | ✅ Must be GREEN | ☐ | | |

---

## 2. Forbidden Conditions

The following conditions **must all be false** before any rehearsal can proceed.
If any condition is true, **stop and escalate**.

| # | Condition | Status | Evidence |
|---|-----------|--------|----------|
| F-01 | `dry_run=false` is set in any Freqtrade config | ☐ Must be false | |
| F-02 | `LIVE_APPROVED` state is active | ☐ Must be false | |
| F-03 | `LIVE_ACTIVE` state is active | ☐ Must be false | |
| F-04 | Exchange API keys or secrets are present in config | ☐ Must be false | |
| F-05 | `SI_V2_ENABLE_REAL_ADAPTERS=1` is set | ☐ Must be false | |
| F-06 | Any Docker container is running with `dry_run=false` | ☐ Must be false | |
| F-07 | Any forcebuy, forcesell, or force_entry command is queued | ☐ Must be false | |
| F-08 | RiskGuard is unavailable during a safety-relevant decision | ☐ Must be false | |
| F-09 | ShadowLogger is unavailable during a decision/write action | ☐ Must be false | |

---

## 3. Explicit Approval Fields

Preflight must be signed off before any rehearsal begins.

| Field | Value |
|-------|-------|
| **Preflight Verifier** | (name / agent ID) |
| **Preflight Timestamp (UTC)** | |
| **Preflight Verdict** | ☐ PASS / ☐ FAIL / ☐ BLOCKED |
| **Rehearsal Approval Token** | |
| **Rehearsal Scope** | |
| **Rollback Contact** | |

### Signature

```
I confirm that all preflight checks have been completed and verified.
I understand that live trading is strictly prohibited at this phase.
Any violation of the forbidden conditions will result in immediate abort.

Signed: ________________________
Date:   ________________________ (UTC)
```

---

## 4. Verification Commands (For Auditor)

These commands may be used to verify preflight conditions in a read-only manner:

```bash
# Confirm all bots are in dry-run mode
grep -r 'dry_run.*false' config/ 2>/dev/null || echo "No dry_run=false found"

# Check for real adapters env var
echo "${SI_V2_ENABLE_REAL_ADAPTERS:-not-set}"

# Check git state
git rev-parse HEAD
git status --short

# Run preflight tests
cd self_improvement_v2
python -m pytest tests/test_live_trading_invariants.py -q
python -m pytest tests/test_dry_run_evidence_schema.py -q
```

---

## 5. Escalation Rules

If any preflight check fails or any forbidden condition is true:

1. **Stop immediately.** Do not proceed to rehearsal.
2. **Document the blocker** with evidence (paths, logs, timestamps).
3. **Escalate** to the project governance contact.
4. **Do not override** any safety check without written human approval.
5. **Do not change** configs, adapters, flags, or env vars to bypass a check.

---

> **This document is not an approval to trade live.**
> It is a mandatory safety gate before any controlled rehearsal.
