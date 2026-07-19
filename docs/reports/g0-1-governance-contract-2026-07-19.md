# G0.1 Evidence Report — Canonical Program Governance Contract

## Verdict

**GREEN** — Full local gate passes. 1064 tests passed, 0 failed, 52 skipped
(pre-existing, unrelated to this batch). `ruff check` clean on the new
renderer. No runtime, Docker, trading, kill-switch, credential, service,
socket, or controller file was touched anywhere in this batch.

## Summary

This report closes out G0.1 (Task 12 of the approved implementation plan):
the canonical, machine-readable program governance contract for
trading-hub — a JSON-Schema-validated program contract and roadmap DAG, a
deterministic Markdown renderer producing a "Derived View," an ADR
formalizing the authority model, and the supersession of four competing
free-text roadmap documents. This was documentation/config/tooling work only
(`docs/`, `config/governance/`, `orchestrator/scripts/`, `tests/`,
`pyproject.toml`, `AGENTS.md`) — no strategy, execution, risk, Docker, or
credential surface was modified.

## Base SHA

- **Authoritative GitHub `main` base for the whole G0.1 PR:**
  `ff791d6967662cb658b4cfa2e7d1c545ae1b33ff`
- Merged into this working branch at commit `dc7afd0` ("chore: merge
  origin/main (ff791d69) into G0 branch for correct base").
- Verified: `git merge-base --is-ancestor ff791d6967662cb658b4cfa2e7d1c545ae1b33ff HEAD`
  → true (base SHA is an ancestor of the current branch tip).

## Commit range

Full G0.1 commit range: `2911c2c..ceafbc3` (16 commits), verified via
`git log --oneline 2911c2c..ceafbc3`:

```
ceafbc3 docs(roadmap): mark competing roadmaps superseded by canonical roadmap
712ce3c docs(state): add decoupled governance/roadmap revision fields
0f3a52f docs(proposals): add advisory proposal header convention
1309bd8 docs(agents): reference canonical program contract (minimal-touch)
7290f42 docs(adr): tighten AGENTS.md hierarchy scoping and fix dangling batch reference
2809a81 fix(governance): tighten ADR bootstrap and reconcile AGENTS.md hierarchy overlap
0209302 docs(adr): add canonical program governance ADR (Proposed)
bebc81c docs(plan): sync G0.1 Task 6 renderer code to the hardened version actually shipped
e3e9f33 fix(governance): harden renderer path resolution, surface external mandate
66b0234 feat(governance): add deterministic roadmap renderer and Derived View
8a043f6 feat(governance): add canonical roadmap DAG (G0-H)
65f4616 docs(spec): fix missing exit_gate on phase H in canonical-roadmap example
069b71f feat(governance): add canonical-roadmap JSON schema
a2a48e7 feat(governance): add machine-readable program contract
d300ae6 feat(governance): add program-contract JSON schema with pending-CI rule
542ca39 chore(governance): add jsonschema dev dependency for G0 schema validation
```

## Files created

| File | Purpose |
|---|---|
| `config/governance/program-contract.yaml` | Machine-readable program contract: north star, safety invariants, authority model |
| `config/governance/program-contract.schema.json` | JSON Schema validating the program contract, including a pending-CI rule |
| `config/governance/canonical-roadmap.yaml` | Canonical roadmap DAG (phases G0–H), single source of program-direction truth |
| `config/governance/canonical-roadmap.schema.json` | JSON Schema validating the roadmap DAG (acyclicity, execution-class enum, required `exit_gate`, etc.) |
| `orchestrator/scripts/render_canonical_roadmap.py` | Deterministic renderer: `canonical-roadmap.yaml` → human-readable "Derived View" Markdown |
| `docs/roadmap/canonical-program-roadmap.md` | Committed, renderer-generated Derived View (must match a fresh render byte-for-byte, enforced by test) |
| `docs/decisions/ADR-2026-07-19-canonical-program-governance.md` | ADR establishing the contract/roadmap as canonical authority. **Status: Proposed — NOT Accepted** (see below) |
| `docs/proposals/README.md` | Advisory proposal header convention for future ShadowProposal-adjacent docs |
| `tests/test_governance_contract_schema.py` | Schema validity + safety-invariant tests for program-contract and canonical-roadmap |
| `tests/test_render_canonical_roadmap.py` | Renderer determinism test + "committed Markdown matches fresh render" drift guard |

## Files modified

| File | Change | Note |
|---|---|---|
| `pyproject.toml` | +1 line: `jsonschema` dev dependency | Additive only |
| `AGENTS.md` | +13 lines: minimal-touch reference section pointing at the canonical program contract | Zero lines removed; the existing "Source-of-truth order" list is untouched |
| `docs/state/current-operational-state.md` | +13 lines: governance revision pointer section | Zero lines removed |
| `docs/roadmap/implementation-roadmap.md` | +6 lines: supersession stamp | See supersede decisions below |
| `docs/roadmap/live-readiness-roadmap-rainbow-si-v2-2026-07-10.md` | +6 lines: supersession stamp | See supersede decisions below |
| `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md` | +6 lines: supersession stamp | See supersede decisions below |
| `docs/roadmap/simplified-target-architecture-roadmap-2026-07-14.md` | +6 lines: supersession stamp | See supersede decisions below |

(Two additional files under `docs/context/` and `docs/proposals/` — the
design-spec fix and a dangling-batch-reference fix — were touched as part of
in-flight defect corrections; see "Defects found and fixed" below. They are
plan artifacts, not governance-contract runtime files.)

`git diff --stat 2911c2c..ceafbc3` (full batch, confirmed clean scope — no
`docker`, `freqtrade`, `.env`, `guardian`, or `cron` paths touched):

```
 AGENTS.md                                          |  13 +
 config/governance/canonical-roadmap.schema.json    |  30 ++
 config/governance/canonical-roadmap.yaml           |  56 ++++
 config/governance/program-contract.schema.json     |  49 +++
 config/governance/program-contract.yaml            |  67 +++++
 .../ADR-2026-07-19-canonical-program-governance.md | 335 +++++++++++++++++++++
 docs/proposals/README.md                           |  15 +
 docs/roadmap/canonical-program-roadmap.md          |  21 ++
 docs/roadmap/implementation-roadmap.md             |   6 +
 ...e-readiness-roadmap-rainbow-si-v2-2026-07-10.md |   6 +
 .../roadmap-v2-blocker-first-runtime-ownership.md  |   6 +
 ...ified-target-architecture-roadmap-2026-07-14.md |   6 +
 docs/state/current-operational-state.md            |  13 +
 ...026-07-19-g0-1-canonical-governance-contract.md |  27 +-
 ...07-19-canonical-program-governance-g0-design.md |   1 +
 orchestrator/scripts/render_canonical_roadmap.py   |  55 ++++
 pyproject.toml                                     |   1 +
 tests/test_governance_contract_schema.py           |  75 +++++
 tests/test_render_canonical_roadmap.py             |  24 ++
 19 files changed, 795 insertions(+), 11 deletions(-)
```

## Supersede decisions (Task 11 / commit `ceafbc3`)

The canonical roadmap (`config/governance/canonical-roadmap.yaml`) is now the
single source of program-direction truth. Four pre-existing free-text
roadmap documents in `docs/roadmap/` were competing program-direction
roadmaps and were stamped `authority: historical`, `status: superseded`,
`superseded_by: config/governance/canonical-roadmap.yaml`:

1. `docs/roadmap/implementation-roadmap.md`
2. `docs/roadmap/live-readiness-roadmap-rainbow-si-v2-2026-07-10.md`
3. `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md`
4. `docs/roadmap/simplified-target-architecture-roadmap-2026-07-14.md`

Each of these previously stated or implied an authoritative program
direction/phase sequence, which is now duplicated authority once the
canonical roadmap exists — hence supersession, not deletion (history is
preserved, authority is redirected).

**One candidate was reviewed and deliberately left untouched:**
`docs/roadmaps/SI_V2_CONTINUOUS_IMPLEMENTATION_ROADMAP.md` (note: distinct
directory, `docs/roadmaps/` not `docs/roadmap/`). This was judged *not* a
competing program-direction roadmap — it is a controller
operating-procedure document (describes the SI-v2 continuous-improvement
control loop's mechanics), not a statement of overall program phases/
direction. This classification is corroborated by the repository's own
`docs/README.md`, which already treats that file/directory as historical and
distinct from `docs/roadmap/`. Leaving it alone avoids conflating an
operating procedure with a competing authority claim.

## Defects found and fixed during implementation

1. **Missing `exit_gate` on phase H (TDD-driven fix).** The design spec's
   phase-H example for the canonical roadmap was missing the
   schema-required `exit_gate` field. A test written first caught this
   (schema validation failure), and the fix —
   `exit_gate: micro_live_canary_validated` — was applied to both the
   design spec and the shipped implementation. Commits: `65f4616` (spec fix)
   and `8a043f6` (implementation, canonical roadmap DAG).

2. **ADR bootstrap self-ratification loopholes (two rounds of review).**
   `docs/decisions/ADR-2026-07-19-canonical-program-governance.md` underwent
   two rounds of code-quality review that found and fixed real gaps:
   - Round 1: reconciled the ADR's authority claims against `AGENTS.md`'s
     pre-existing "Source-of-truth order" list, to prevent a silent
     dual-authority conflict between the two documents (commit `2809a81`,
     further tightened in `7290f42`).
   - Round 2: closed two self-ratification loopholes in the bootstrap
     acceptance sequence — (a) the human confirmation that flips the ADR to
     Accepted must now name the exact PR-head SHA it is confirming, and
     (b) the Accepted-flip commit must be diff-isolated to the `Status:`
     line only (no bundling other changes into the acceptance commit).

3. **Renderer hardening (review-driven).**
   `orchestrator/scripts/render_canonical_roadmap.py` underwent a
   review-driven fix (commit `e3e9f33`):
   - Path resolution was hardcoded relative to the invocation directory;
     hardened to resolve correctly from any CWD.
   - The renderer's Derived View table was silently dropping the
     safety-relevant `requires_external_mandate` field; added an
     "External mandate" column so this field is visible in the
     human-readable output rather than only in the machine-readable YAML.
   - Commit `bebc81c` then synced the design-spec's documented renderer code
     to match the hardened version actually shipped, so spec and
     implementation don't drift.

## Test results (Step 1)

Command: `python3 -m pytest tests -q` (run via
`/tmp/g01_batchb_venv/bin/python3 -m pytest tests -q`, pytest 9.1.1)

```
........................................................................ [  6%]
..............................................................ssssssssss [ 12%]
sssssssssssss........................................................... [ 19%]
........................................................................ [ 25%]
........................................................................ [ 32%]
........................................................................ [ 38%]
........................................................................ [ 45%]
........................................................................ [ 51%]
...........................................................s............ [ 58%]
........................................................................ [ 64%]
........................................................................ [ 71%]
..sssssssssssssssssssssss............................................... [ 77%]
........................................................................ [ 83%]
........................................................................ [ 90%]
........s.s..ss......................................................... [ 96%]
...................................                                      [100%]
1064 passed, 52 skipped, 14 warnings in 17.84s
```

Result: **PASS**. 1064 passed, 0 failed, 52 skipped (skips are pre-existing
and unrelated to this batch — e.g. environment-gated integration tests). 14
warnings, all pre-existing `DeprecationWarning`s in unrelated modules
(`primo/primo_api.py` FastAPI `on_event` lifecycle, `shadowlock`
`datetime.utcnow()` usage) — none originate from files touched in this
batch.

The two new governance test files were additionally run in isolation to
confirm targeted coverage:

```
tests/test_governance_contract_schema.py::test_contract_schema_is_valid_jsonschema PASSED
tests/test_governance_contract_schema.py::test_contract_schema_rejects_missing_north_star PASSED
tests/test_governance_contract_schema.py::test_program_contract_validates_and_holds_safety_invariants PASSED
tests/test_governance_contract_schema.py::test_roadmap_schema_is_valid_jsonschema PASSED
tests/test_governance_contract_schema.py::test_roadmap_schema_rejects_unknown_execution_class PASSED
tests/test_governance_contract_schema.py::test_canonical_roadmap_valid_acyclic_and_revision_aligned PASSED
tests/test_render_canonical_roadmap.py::test_render_is_deterministic PASSED
tests/test_render_canonical_roadmap.py::test_render_has_do_not_edit_header PASSED
tests/test_render_canonical_roadmap.py::test_committed_markdown_matches_render PASSED
9 passed in 0.49s
```

## Ruff result (Step 2)

Command: `ruff check orchestrator/scripts/render_canonical_roadmap.py` (run
via `/tmp/g01_batchb_venv/bin/python3 -m ruff check
orchestrator/scripts/render_canonical_roadmap.py`, ruff 0.15.22)

```
All checks passed!
```

Result: **PASS**, no errors.

## Safety / scope confirmation

- `git diff --stat 2911c2c..ceafbc3 -- '*docker*' '*freqtrade*' '*.env*' 'guardian*' 'cron*'`
  → empty output, confirming zero touch on Docker, Freqtrade config/strategy,
  env/credential files, Guardian, or cron across the entire G0.1 batch.
- No file under this batch sets `dry_run`, touches exchange credentials,
  modifies strategy logic, signal thresholds, pair allowlists, or any
  runtime/service/socket surface.
- Every task in this batch was scoped to `docs/`, `config/governance/`,
  `orchestrator/scripts/` (a new pure-Python renderer script, no service
  wiring), `tests/`, `pyproject.toml` (dev-dependency only), and `AGENTS.md`
  (additive reference section only).
- This was verified per-task via `git diff --stat` scope checks throughout
  implementation (Tasks 1–11), and reconfirmed here for the full range as
  part of this final gate.
- No container restart, recreation, volume operation, data deletion, prune,
  or broad permission change occurred.
- No `git add .` was used; all commits staged files explicitly by path (see
  individual commit diffs in the range above).

## Status of the ADR

`docs/decisions/ADR-2026-07-19-canonical-program-governance.md` has
`Status: Proposed` (verified: `grep -n "^Status" ...` →
`2:Status: Proposed`). It is **not yet Accepted**. Per the ADR's own
bootstrap sequence (hardened in commit `2809a81`/`7290f42` to close the
self-ratification loopholes described above), acceptance requires Luke's
explicit confirmation naming the exact PR-head SHA, followed by a
diff-isolated commit that flips only the `Status:` line to `Accepted`. That
step has not happened and is out of scope for this report — it is Task 13
of the plan, a separate human-gated step that occurs after the G0.1 PR is
opened.

## Conclusion

Full local gate is green: 1064/1064 non-skipped tests pass, ruff is clean on
the new renderer, and the batch's scope is confirmed to be strictly
documentation/config/tooling with no runtime or safety-relevant mutation.
G0.1 is ready for PR review. Acceptance of the ADR and any further
runtime-facing follow-up remain explicitly gated on Luke's separate
confirmation (Task 13).
