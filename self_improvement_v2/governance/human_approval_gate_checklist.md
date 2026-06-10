# Human Approval Gate Checklist

> **SI v2 — Human Approval Pre-Flight Checklist**
> This checklist must be completed and signed off **before** any controlled
> dry-run rehearsal (#125) or runtime probing (#129) can begin.
>
> **Live trading is strictly prohibited at this phase.**

---

## 1. Required Offline Artifacts

| # | Artifact | Status | Verified By |
|---|----------|--------|-------------|
| 1.1 | Rainbow subsystem complete (validator, snapshot, drift guard, fixture review, status, client, events) | ☐ | |
| 1.2 | Source manifest (`evidence/source_manifest.json`) | ☐ | |
| 1.3 | Evidence bundle schema and builder | ☐ | |
| 1.4 | Evidence bundle output (`reports/evidence/evidence_bundle.json`) | ☐ | |
| 1.5 | Regime fixtures (`fixtures/regime-labels/`) | ☐ | |
| 1.6 | Source-regime stats fixtures (`fixtures/source-regime-stats/`) | ☐ | |
| 1.7 | Attribution aggregator and summary output | ☐ | |
| 1.8 | Quality gate report (`reports/readiness/offline_quality_gate_report.md`) — must be GREEN | ☐ | |
| 1.9 | Episode manifest (`episode/offline_episode_manifest.json`) | ☐ | |
| 1.10 | Episode skeleton (`src/si_v2/episode/offline_episode.py`) | ☐ | |
| 1.11 | Episode report renderer and output | ☐ | |
| 1.12 | Evidence bundle integrity manifest | ☐ | |
| 1.13 | Attribution report renderer and report | ☐ | |
| 1.14 | Phase 1 readiness matrix — GREEN or YELLOW | ☐ | |
| 1.15 | Offline system architecture index | ☐ | |
| 1.16 | Failure taxonomy (`qa/failure_taxonomy.json`) | ☐ | |
| 1.17 | CI offline smoke workflow passing | ☐ | |

## 2. Required Test Evidence

| # | Evidence | Status | Verified By |
|---|----------|--------|-------------|
| 2.1 | All SI v2 pipeline tests pass (`pytest -k "rainbow or evidence or regime or attribution or quality or manifest or readiness or episode"`) | ☐ | |
| 2.2 | All JSON files parse correctly | ☐ | |
| 2.3 | Ruff lint passes | ☐ | |
| 2.4 | No credentials or secrets in source code | ☐ | |
| 2.5 | Python compile check passes | ☐ | |
| 2.6 | CI smoke workflow runs on this branch | ☐ | |

## 3. Manual Approval Fields

| Field | Value |
|-------|-------|
| **Branch name** | |
| **Main HEAD commit** | |
| **Phase 1 readiness verdict** | |
| **Quality gate verdict** | |
| **Primary approver** | |
| **Approval date** | |
| **Approval token** | `APPROVE_PHASE_M_REHEARSAL_<YYMMDD>` |

## 4. Explicit Non-Go Conditions

If **any** of the following is true, the gate is **RED** and rehearsal is **BLOCKED**:

- [ ] A required offline artifact is missing (section 1)
- [ ] Pipeline tests are not all green
- [ ] Quality gate verdict is RED
- [ ] Credentials or secrets found in source code
- [ ] `dry_run=false` or live trading configuration detected
- [ ] Docker/Freqtrade/Telegram/exchange dependencies required for validation
- [ ] Phase 1 readiness verdict is RED

## 5. Approvals Required Before Next Steps

| Step | Required Approval Token |
|------|------------------------|
| Controlled dry-run rehearsal (#125) | `APPROVE_PHASE_M_REHEARSAL_<YYMMDD>` |
| Runtime probing (#129) | Separate approval required |
| Live-readiness assessment (#124 → live) | Separate approval required |
| Live trading | **NOT APPROVED** at this phase |

## 6. No-Live-Trading Confirmation

> **I confirm that live trading, `dry_run=false`, real exchange orders,
> real API keys, Telegram bot tokens, and any form of financial
> exposure remain strictly prohibited in this phase.**
>
> Name: ________________________________
> Date: ________________________________

---

*Checklist maintained at `self_improvement_v2/governance/human_approval_gate_checklist.md`*
*Created as part of #122 — Human Approval Gate Checklist*
