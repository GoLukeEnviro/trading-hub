# Rehearsal Planning Package — Artifact Index (#149)

This document indexes all rehearsal planning artifacts from **#127** through
**#154**, documents the intended review and validation order, and provides
a current implementation status matrix.

---

## Artifact Index

### Governance Layer (Issues #122–#131)

| Issue | Artifact | Type | Status |
|-------|----------|------|--------|
| #122 | `governance/human_approval_gate_checklist.md` | Checklist | ✅ Complete |
| #124 | `governance/live_readiness_blocker_inventory.md` | Inventory | ✅ Complete |
| #129 | `governance/runtime_preflight_checklist.md` | Checklist | ✅ Complete |
| #131 | `governance/external_adapter_boundary_audit.json` | Audit | ✅ Complete |
| #147 | `governance/rehearsal_planning_pr_review_checklist.md` | Checklist | ✅ Complete |

### Planning Gate Layer (Issues #135–#140)

| Issue | Artifact | Type | Status |
|-------|----------|------|--------|
| #135 | `rehearsal/controlled_rehearsal_planning_gate.md` | Gate doc | ✅ Complete |
| #136 | `rehearsal/rehearsal_stop_condition_matrix.json` | Matrix | ✅ Complete |
| #137 | `rehearsal/rehearsal_evidence_bundle_plan.md` | Plan | ✅ Complete |
| #138 | `rehearsal/operator_rehearsal_approval_packet.md` | Packet | ✅ Complete |
| #139 | `rehearsal/read_only_observation_plan.md` | Plan | ✅ Complete |
| #140 | `rehearsal/rehearsal_readiness_decision_record.md` | Record | ✅ Complete |

### Automation Layer (Issues #143–#154)

| Issue | Artifact | Type | Status |
|-------|----------|------|--------|
| #143 | `rehearsal/planning_pipeline_validator.py` | Validator | ✅ Complete |
| #144 | `rehearsal/rehearsal_proposal_package.schema.json` | Schema | ✅ Complete |
| #145 | `.github/workflows/si-v2-offline-smoke.yml` | CI workflow | ✅ Complete |
| #146 | `rehearsal/redaction_checker.py` | Checker | ✅ Complete |
| #148 | `rehearsal/observation_interfaces.py` | Interfaces | ✅ Complete |
| #150 | `cli/planning_checker.py` | CLI | ✅ Complete |
| #151 | `rehearsal/semantic_consistency.py` | Engine | ✅ Complete |
| #152 | `tests/fixtures/proposal_package/` | Fixtures | ✅ Complete |
| #153 | `rehearsal/status_report_renderer.py` | Renderer | ✅ Complete |
| #154 | `tests/test_planning_policy_regression.py` | Golden suite | ✅ Complete |

### Quality Layer (Test files)

| Issue | Test File | Type | Status |
|-------|-----------|------|--------|
| #146 | `tests/test_negative_fixtures.py` | Redaction tests | ✅ Complete |
| #151 | `tests/test_semantic_consistency.py` | Consistency tests | ✅ Complete |
| #152 | `tests/test_negative_fixtures.py` | Fixture tests | ✅ Complete |
| #153 | `tests/test_status_report_renderer.py` | Renderer tests | ✅ Complete |
| #148 | `tests/test_observation_interfaces.py` | Observer tests | ✅ Complete |
| #154 | `tests/test_planning_policy_regression.py` | Golden tests | ✅ Complete |

---

## Intended Review and Validation Order

The artifacts should be reviewed and validated in the following logical order:

1. **Governance layer** (#122, #124, #129, #131) — Establish the safety boundary
   and approval process first.
2. **Planning gate docs** (#135–#140) — Define the gate, stop conditions,
   evidence bundle, approval packet, observation plan, and readiness record.
3. **Schema** (#144) — Define the proposal package schema that all inputs must
   conform to.
4. **Validation fixtures** (#152) — Create known-good and known-bad fixtures.
5. **Redaction checker** (#146) — Implement content-safety scanning.
6. **Semantic consistency engine** (#151) — Cross-reference and verdict checking.
7. **Pipeline validator** (#143) — Wire everything together.
8. **Status report renderer** (#153) — Produce deterministic reports.
9. **Golden snapshot suite** (#154) — Lock down behaviour with regression tests.
10. **CLI** (#150) — Expose validation via command-line interface.
11. **Observation interfaces** (#148) — Define offline observer contracts.
12. **CI workflow** (#145) — Automate all checks on every push.
13. **PR review checklist** (#147) — Document the merge-readiness process.

---

## Current Implementation Status Matrix

| Layer | Total Issues | Complete | In Progress | Not Started |
|-------|-------------|----------|-------------|-------------|
| **Governance** (#122–#131, #147) | 5 | 5 | 0 | 0 |
| **Planning Gate** (#135–#140) | 6 | 6 | 0 | 0 |
| **Automation** (#143–#154) | 10 | 10 | 0 | 0 |
| **Quality** (Tests) | 6 | 6 | 0 | 0 |
| **Total** | **27** | **27** | **0** | **0** |

---

## Reference Information

### Test Coverage
- Test files: `tests/test_negative_fixtures.py`, `tests/test_semantic_consistency.py`,
  `tests/test_status_report_renderer.py`, `tests/test_observation_interfaces.py`,
  `tests/test_planning_policy_regression.py`
- Run with: `uv run --project . pytest tests/ -q`

### CLI
- Entrypoint: `python -m cli.planning_checker`
- Commands: `check-package`, `check-artifacts`, `render-report`, `explain-finding`
- Returns: PASS=0, WARNING=2, BLOCKED=10

### Fixtures
- Location: `tests/fixtures/proposal_package/`
- Categories: valid, draft, missing, malformed, contradictory, duplicate, orphan,
  unsafe, combined
- Golden snapshots: `tests/fixtures/golden/{pass,warning,blocked}/`

### Golden Suite
- Location: `tests/fixtures/golden/`
- Update: `UPDATE_SNAPSHOTS=1 uv run --project . pytest tests/test_planning_policy_regression.py -q`
- Each snapshot includes a JSON report and a Markdown report with normalised
  timestamps (`2026-06-10T00:00:00Z`) and paths (`./`).

---

*Document generated as part of #149 — Rehearsal Planning Package Index.*
