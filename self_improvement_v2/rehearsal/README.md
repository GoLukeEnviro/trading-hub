# SI v2 Rehearsal Planning Package

> **Central index for the rehearsal planning governance layer.**
>
> This directory contains all artifacts, schemas, validators, and
> documentation for the SI v2 rehearsal planning pipeline.
>
> **All artifacts are governance-only.**
> No artifact in this directory activates runtime operations,
> trading decisions, or production deployment.

---

## Index: Planning Artifacts

### Governance Layer (#127–#132, #135–#140)

| Artifact | Issue | Description | Status |
|----------|-------|-------------|--------|
| `controlled_rehearsal_planning_gate.md` | #135 | Planning gate with prerequisites, forbidden conditions, verdicts | ✅ Implemented |
| `rehearsal_stop_condition_matrix.json` | #136 | 20 stop conditions, fail-closed semantics, verdict map | ✅ Implemented |
| `rehearsal_evidence_bundle_plan.md` | #137 | Evidence collection plan, SHA-256 integrity, sanitisation | ✅ Implemented |
| `operator_rehearsal_approval_packet.md` | #138 | Human operator approval template, allowed/forbidden actions | ✅ Implemented |
| `read_only_observation_plan.md` | #139 | 3-tier observation sources, disabled-by-default adapters | ✅ Implemented |
| `rehearsal_readiness_decision_record.md` | #140 | GREEN/YELLOW/RED verdict, residual risks, next actions | ✅ Implemented |

### Planning Automation Layer (#143–#147, #149)

| Artifact | Issue | Description | Status |
|----------|-------|-------------|--------|
| `planning_pipeline_validator.py` | #143 | End-to-end validator: presence, content, cross-refs, verdicts | ✅ Implemented |
| `rehearsal_proposal_package.schema.json` | #144 | Machine-readable proposal schema (draft/final stages) | ✅ Implemented |
| *(CI workflow extension)* | #145 | Offline CI gate (extends `si-v2-offline-smoke.yml`) | ✅ Implemented |
| `../security/rehearsal_artifact_redaction_policy.md` | #146 | Redaction rules, placeholders, fail-closed checks | ✅ Implemented |
| `../governance/rehearsal_planning_pr_review_checklist.md` | #147 | Merge-readiness review checklist with verdicts | ✅ Implemented |
| `README.md` (this file) | #149 | Central planning package index | ✅ Implemented |

### Test Artifacts

| Test File | Covers Issues | Description |
|-----------|---------------|-------------|
| `tests/test_planning_pipeline_validator.py` | #143 | Validator unit tests |
| `tests/test_rehearsal_proposal_package_schema.py` | #144 | Schema validation tests |
| `tests/test_rehearsal_artifact_redaction_policy.py` | #146 | Redaction detection tests |
| `tests/test_rehearsal_planning_pr_review_checklist.py` | #147 | Checklist structure tests |

### Fixtures

| Fixture | Description |
|---------|-------------|
| `tests/fixtures/proposal_package/valid/` | Valid complete proposal package for schema testing |
| `tests/fixtures/proposal_package/invalid/` | Invalid/malformed proposal packages |
| `tests/fixtures/redaction/safe/` | Clean fixture with all sensitive material redacted |
| `tests/fixtures/redaction/unsafe/` | Unsafe fixture with unredacted sensitive content |

### Validation Reports

| Report | Description |
|--------|-------------|
| `reports/rehearsal_planning_pipeline_validation.json` | Latest JSON validation output |
| `reports/rehearsal_planning_pipeline_validation.md` | Latest Markdown validation output |

---

## Intended Review and Validation Order

When modifying or extending this package, follow this order:

1. **#144** — Schema first (defines the contract)
2. **#146** — Redaction policy (defines what is unsafe)
3. **#143** — Pipeline validator (validates artifacts against schema + policy)
4. **#147** — Review checklist (governs how PRs are reviewed)
5. **#149** — Update this index
6. **#145** — CI gate (last, after all validations pass)

---

## Current Implementation Status

| Layer | Status | Notes |
|-------|--------|-------|
| Governance (#127–#132) | ✅ Complete | Rehearsal control, evidence, preflight, audit, manifest |
| Planning Gate (#135–#140) | ✅ Complete | Gate, stop matrix, evidence plan, approval, observation, readiness |
| Planning Automation (#143–#147, #149) | ✅ Complete | Validator, schema, redaction, review checklist, CI, index |
| Observation/Runtime (#148+) | ⏭️ Not started | Will build on this planning layer |

---

*Maintained at `self_improvement_v2/rehearsal/README.md`*
*Created as part of #149 — Rehearsal Planning Package Index*
