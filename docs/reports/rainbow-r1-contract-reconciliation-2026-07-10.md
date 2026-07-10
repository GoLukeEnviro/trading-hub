# Rainbow R1 — Contract Reconciliation Report

**Issue:** #490
**Branch:** `feat/rainbow-r1-contract-reconciliation`
**Base SHA:** `eb081ca427168930a9c326531c2ffbaecd4f7d74`
**Head SHA:** *(set on commit)*
**Date:** 2026-07-10

## Upstream Baseline

| Property | Value |
|----------|-------|
| Merged upstream baseline | `bbcaf25e9636cfacc9ae1c7c9cf4ea37aa013687` |
| Historical roadmap reference | `f6c42c6e7483af413dbf30fa91aa68917952c632` |
| Contract document blob | Git blob SHA: `1b49e515cb39084ea4517fb3ddf45a6376984fe7` |
| Contract identity | Identical at both references — no schema or validator change required |

## Files Audited

| File | Action | Classification |
|------|--------|---------------|
| `self_improvement_v2/contracts/rainbow_signal_envelope.schema.json` | Read-only audit | EXPECTED — no change needed |
| `self_improvement_v2/contracts/README.md` | Updated | Baseline pin, excluded PRs, canonical endpoint doc |
| `self_improvement_v2/src/si_v2/rainbow/validator.py` | Read-only audit | EXPECTED — no change needed |
| `self_improvement_v2/src/si_v2/rainbow/drift_guard.py` | Read-only audit | EXPECTED — no change needed |
| `self_improvement_v2/fixtures/rainbow-signals/` | New fixture added | Canonical envelope fixture for contract coverage |
| `self_improvement_v2/tests/test_rainbow_contract_snapshot.py` | Read-only audit | PASS — no change needed |
| `self_improvement_v2/tests/test_rainbow_contract_drift_guard.py` | Updated | Fixture count 7→8, name set extended |
| `self_improvement_v2/tests/test_rainbow_signal_validator.py` | Read-only audit | PASS — no change needed |

## Differences and Classifications

| Difference | Classification | Detail |
|------------|---------------|--------|
| Schema vs upstream §5 envelope | EXPECTED | Schema has `event_type` (not in §5 table); all §5 fields present |
| Validator required fields vs schema | EXPECTED | Identical set of 11 required fields |
| Fixture timestamps differ from upstream | EXPECTED | Local fixtures use synthetic 2028 dates; upstream uses 2026-06-10. Content structure identical. |
| `partial_metadata_signal.json` content differs | EXPECTED | Local fixture has different emitted_at/timestamp_utc values; schema structure identical |
| `valid_long_signal.json` content differs | EXPECTED | Same as above — synthetic dates only |
| `valid_short_signal.json` content differs | EXPECTED | Same as above — synthetic dates only |
| PR #66 `canonical_symbol` delta | PENDING_UNMERGED_UPSTREAM | Not merged upstream; excluded from R1 baseline |
| PR #488 client changes | PENDING_UNMERGED_UPSTREAM | Blocked on final PR #66 contract; excluded from R1 |

## Deferred to R2 (Issue #491)

The following client changes were implemented on the R1 branch during development and then removed to restore R1 scope. They are recorded here for reconstruction on the R2 branch:

- `canonical_endpoint_path` config field
- `KNOWN_READ_ONLY_ENDPOINTS` constant
- `is_canonical_endpoint` property
- Endpoint branching in `_get_latest_read_only_signals`
- `_canonical_direction_to_hub` mapping
- `_map_canonical_signal_to_envelope` mapper
- Actionability checks in runtime client

**Status:** `DEFERRED_TO_R2_ISSUE_491`

## Tests

| Test Suite | Result |
|------------|--------|
| `test_rainbow_contract_snapshot.py` | PASS |
| `test_rainbow_contract_drift_guard.py` | PASS (updated for 8 fixtures) |
| `test_rainbow_signal_validator.py` | PASS |
| Ruff (changed Python paths) | PASS |
| `git diff --check` | PASS |

## Safety Verification

- ✅ No runtime behavior change
- ✅ No client enablement
- ✅ No PR #66 code copied
- ✅ No PR #488 code copied
- ✅ Fail-closed validation unchanged
- ✅ No secrets or credentials
- ✅ No Docker, Cron, Scheduler, or Freqtrade mutation
- ✅ No live trading authorization

## Rollback

`git revert` of the merge commit on `main` restores the previous state. No data migration required.

## Next Gate

`R1_CONTRACT_RECONCILIATION_MERGED_R2_SELECTED`
