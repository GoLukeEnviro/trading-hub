# Merge-Readiness Review Checklist — Rehearsal Planning (#147)

## Purpose

This checklist governs the **merge-readiness review** for any PR that
touches the rehearsal planning subsystem (issues #135–#154, governance docs
#122–#131).  It defines the required verification steps, PASS/WARNING/BLOCKED
review verdicts, hard blockers, acceptable residual risks, and the final
sign-off section.

---

## Required Verification Steps

Each reviewer **must** confirm the following before signing off:

### 1. Expected-Head Verification
- [ ] The PR targets the correct base branch (`si-v2-*` or `main`).
- [ ] The branch is based on the latest `HEAD` of the target branch.
- [ ] No merge conflicts exist.

### 2. CI Status
- [ ] All CI checks pass (GitHub Actions workflows):
  - [ ] Offline smoke test (`si-v2-offline-smoke.yml`)
  - [ ] Lint / format (ruff)
  - [ ] Type checking (mypy, if configured)
  - [ ] Unit tests (pytest)
- [ ] No CI jobs are pending, cancelled, or skipped without documented reason.

### 3. Schema Validation
- [ ] The rehearsal proposal package schema (`rehearsal_proposal_package.schema.json`)
      is valid JSON.
- [ ] All fixture JSON files in `tests/fixtures/proposal_package/` are valid
      against the schema (or intentionally malformed for negative testing).
- [ ] Schema changes are backward-compatible (additive only) or have a migration
      plan.

### 4. Semantic Consistency
- [ ] Cross-artifact references (#135 → #127–#132, #136, #137, #139) are correct.
- [ ] Approval packet (#138) references planning gate (#135) and stop matrix (#136).
- [ ] Readiness record (#140) references all upstream artifacts (#135–#139).
- [ ] Verdict definitions are consistent (RED = do not proceed, GREEN = proceed).
- [ ] Stop-condition matrix default_verdict = `BLOCKED`.

### 5. Redaction Checks
- [ ] All artifact files contain no unredacted sensitive content
      (API keys, secrets, private keys, wallet addresses, bot tokens,
      internal IPs).
- [ ] Any absolute paths are replaced with relative paths or `[REDACTED_*]`
      placeholders.
- [ ] The redaction checker test suite passes (`test_negative_fixtures.py`).

### 6. Deterministic Output
- [ ] All report renderers produce stable, deterministic output.
- [ ] The status report renderer (#153) tests pass.
- [ ] The golden snapshot regression tests (#154) pass (or are intentionally
      updated via `UPDATE_SNAPSHOTS=1`).

### 7. No-Runtime Checks
- [ ] No code in the PR initiates network requests, subprocess calls,
      Docker operations, or filesystem writes outside of
      `rehearsal/*.py` test fixtures.
- [ ] All observer stubs are offline-only (no `BitgetObserverPlaceholder`,
      `DockerObserverPlaceholder`, or `SubprocessObserverPlaceholder` active).
- [ ] `DisabledObserverPlaceholder` raises `RuntimeError` on instantiation.

---

## Review Verdicts

### ✅ PASS
All required verification steps pass.  No hard blockers.
Residual risks (if any) are documented and acceptable.
**Action:** Merge approved.

### ⚠️ WARNING
One or more verification steps fail for non-blocking reasons
(e.g. documentation-only changes, test-only changes that don't affect
production code, minor formatting issues).
**Action:** Merge permitted with documented acknowledgment of findings.
Reviewer notes must explain each warning and why it is acceptable.

### ❌ BLOCKED
One or more hard blockers are present (see below).
**Action:** PR must not be merged until all hard blockers are resolved.

---

## Hard Blockers

The following conditions **must** be resolved before merge:

- **Live-trading paths:** Any change that enables live trading, sets
  `dry_run=false`, or modifies real trading behaviour.
- **Broken CI:** Any CI job that is failing without a documented, acceptable
  reason.
- **Broken validation:** The planning pipeline validator produces incorrect
  verdicts or crashes.
- **Unreviewed changes:** Files outside the rehearsal planning scope
  (issues #135–#154) that are modified without explicit review.
- **Missing critical artifacts:** Any required artifact file
  (#135–#140, #122–#131, #144) is deleted or empty.
- **Non-deterministic output:** Renderer output differs between identical runs.
- **Active non-offline observers:** Any observer placeholder that would require
  network / subprocess / Docker is accidentally instantiated.

---

## Acceptable Residual Risks

The following risks are acceptable and do **not** block merge:

1. **Governance-only changes** — Updates to markdown governance documents
   (checklists, audit files) that do not affect automation code.
2. **No automation coverage** — Governance documents that are not yet
   backed by automated checks (e.g. a policy document with no corresponding
   test).
3. **No observation implementation** — Observer stubs exist but the real
   integration (Bitget, Docker, subprocess) is not yet implemented.
4. **Test-only changes** — Tests that add coverage without modifying any
   `rehearsal/*.py` production code.
5. **Metadata updates** — Changes to comments, docstrings, error messages,
   or README files that have no behavioural impact.

---

## Final Sign-Off

| Role | Name | Date (UTC) | Verdict | Notes |
|------|------|-------------|---------|-------|
| Reviewer | | | PASS / WARNING / BLOCKED | |
| Reviewer | | | PASS / WARNING / BLOCKED | |
| Approver | | | | |

**By signing above, I confirm that:**
- I have reviewed the PR against all applicable steps in this checklist.
- Hard blockers (if any) are documented and resolved.
- Residual risks are documented and acceptable.
- I understand that a PASS verdict means merge-ready for the rehearsal
  planning subsystem, **not** operational approval for production execution.

---

*Document generated as part of #147 — Rehearsal Planning PR Review Checklist.*
