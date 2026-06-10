# Rehearsal Evidence Bundle Plan

> **SI v2 — Evidence Collection Plan for Future Rehearsal Proposals**
>
> This document defines what evidence must be collected, how it must be
> structured, and what integrity/security requirements apply.
>
> **This is a plan for future collection.**
> No evidence is collected during planning. This document specifies
> the requirements that the actual collection must satisfy when
> a rehearsal is executed.

---

## 1. Purpose

The evidence bundle plan ensures that:

- All relevant evidence is identified before rehearsal execution.
- Evidence collection is repeatable, verifiable, and auditable.
- Integrity checks prevent tampering or corruption.
- Sensitive paths are sanitised or excluded.
- Missing evidence causes a fail-closed behaviour.

---

## 2. Evidence Categories

| Category | Description | Collection Method | Integrity Required |
|----------|-------------|-------------------|--------------------|
| **Preflight Results** | Results of preflight checks before rehearsal | Automated check | SHA-256 |
| **Config Snapshots** | Static copies of relevant config files at rehearsal start | File copy (read-only) | SHA-256 |
| **Log Samples** | Log excerpts from target components during observation | Read-only log tail | SHA-256 |
| **Health Check Results** | Health endpoint responses from observed services | Read-only HTTP GET | SHA-256 |
| **Signal Snapshots** | Current signal output from ai-hedge-fund-crypto | Read-only file read | SHA-256 |
| **Trade State** | Current open trade state from dry-run bots | Read-only SQLite query | SHA-256 |
| **Observation Notes** | Operator notes recorded during rehearsal | Manual entry | Not required |
| **Deviation Log** | Record of any observed deviations from expected behaviour | Automated + manual | SHA-256 |

---

## 3. Required Evidence Fields

Each evidence record must contain:

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `id` | ✅ | string | Unique evidence identifier (`ev-<category>-<timestamp>-<random4>`) |
| `category` | ✅ | string | Evidence category from section 2 |
| `collected_at` | ✅ | string | ISO 8601 UTC timestamp of collection |
| `collected_by` | ✅ | string | Agent or operator identifier |
| `source` | ✅ | string | Path or endpoint the evidence was collected from |
| `content_hash` | ✅ | string | SHA-256 hex digest of the collected content |
| `sanitized_path` | ✅ | boolean | Whether the source path was sanitised to remove secrets |
| `approval_reference` | ✅ | string | Reference to the approval token that authorised collection |
| `rehearsal_proposal_id` | ✅ | string | Reference to the rehearsal proposal (#135) |
| `checksum_verified` | ✅ | boolean | Whether the content hash was verified after collection |
| `notes` | ❌ | string | Optional operator notes |

---

## 4. Integrity Requirements

- Every evidence record must have a SHA-256 content hash.
- The hash must be computed at collection time and stored with the record.
- A separate integrity manifest must record all hashes for batch verification.
- If a hash does not match on verification, the evidence is considered
  corrupted and must be re-collected or flagged.
- Evidence without a verifiable hash must be treated as **missing**.

---

## 5. Sanitisation Rules

- Evidence source paths must not contain:
  - Absolute home directory paths (replace `$HOME` or `/home/` with `~/`)
  - Secret file names (e.g. `config.json` containing API keys)
  - Environment variable values that contain credentials
  - Docker container IDs (replace with container names)
- Sanitised paths must be clearly marked with `sanitized_path: true`.

---

## 6. Missing-Evidence Behaviour

If required evidence cannot be collected (e.g. component unavailable,
permission denied, timeout):

| Condition | Verdict | Action |
|-----------|---------|--------|
| Evidence category is mandatory and missing | **RED** | Do not proceed. Escalate. |
| Evidence category is optional and missing | **YELLOW** | Document gap, proceed with operator awareness. |
| Evidence hash verification fails | **RED** | Do not proceed. Re-collect or escalate. |
| Evidence source is inaccessible without runtime action | **RED** | Do not proceed. Scope violation (see #136 SC-12). |

---

## 7. Approval Reference

Every evidence record must reference the approval token that authorised
the rehearsal. The token must match the scope of the evidence collection.
If no valid approval token exists, evidence collection must not begin.

---

## 8. No-Collection Statement

> **This document is a plan for future evidence collection.**
> No evidence is collected during planning.
> Actual evidence collection may only occur after a rehearsal is
> approved with a valid human approval token.
>
> **Live trading, `dry_run=false`, real orders, and financial exposure
> remain strictly prohibited.**

---

## 9. Change Log

| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Initial version | SI v2 (#137) |

---

*Maintained at `self_improvement_v2/rehearsal/rehearsal_evidence_bundle_plan.md`*
*Created as part of #137 — Rehearsal Evidence Bundle Plan*
