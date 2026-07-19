# ADR-2026-07-19: Roadmap Autonomous Merge Controller (Root Broker Architecture)

**Status:** Accepted (controller shipped disabled; activation deferred)
**Date:** 2026-07-19
**Author:** Governance transition PR (HermesWriter, Issue #638)
**Supersedes:** PR #639 (CLOSED — architecturally insufficient)
**Amends:**
- ADR-2026-07-12 §2.4 "Audit closure" (now layered via root-broker IPC)

---

## 1. Context

See Issue #638 Spec Rev 2 for the full design context. Three architectural
blockers (§A1 Credential Isolation, §A2 Tamper-Proof Audit, §A3 Incident
Semantics) were resolved via Issue #638 comment discussions on 2026-07-19.

## 2. Decision

### 2.1 Architecture: Root Broker

A root-owned Unix-socket broker at `/var/run/roadmap-merge-broker.sock`
is the **sole** holder of the GitHub merge credential. The controller
client (running as UID 10000 `hermes`) sends merge requests to the broker
over the socket. The broker independently re-verifies EVERY precondition:

1. SO_PEERCRED checks the caller is UID 10000.
2. Independent `gh api user` → principal resolved against allowlist.
3. Independent `gh pr view` / `gh issue view` → PR snapshot collected
   from scratch (no trust of client data).
4. Independent guard evaluation (mirrors `roadmap_merge_guard.py` logic
   in-broker, not by importing the guard).
5. Denylist check against `roadmap_merge_controller_denylist.txt`
   (self-protecting — the denylist file itself is in the denylist).
6. Phase-0 positive path allowlist check
   (`roadmap_merge_controller_paths_allowlist.txt`).
7. A1-only trigger scan (A2/A3/live-trading markers in issue/PR/comments).
8. Pre-merge re-snapshot → full-field TOCTOU comparison
   (HEAD, issue state, labels, tracker body, review decision, threads,
    comments, required check conclusions, governance blocks).
9. INTENT audit record written to `chattr +a`-protected JSONL.
10. `gh pr merge --squash --match-head-commit <sha>` executed.
11. On timeout/5xx/connection abort → re-query GitHub PR state.
12. COMPLETION audit record written.
13. On completion-audit failure → write halt file + journald incident,
    auto-deactivate controller, no further merges until reconciliation.

### 2.2 Three merge outcome states

| State | Meaning | merged field |
|-------|---------|-------------|
| `MERGED` | GitHub merge confirmed, audit completed | `true` |
| `MERGE_REJECTED` | Precondition failed or GitHub rejected | `false` |
| `MERGE_OUTCOME_UNKNOWN` | Merge executed but audit completion failed | `true` (merge sticks) |

### 2.3 Threat model boundary (acknowledged)

`chattr +a` protects against the unprivileged controller (UID 10000).
It does NOT protect against a compromised root. Root-level integrity
requires host-level controls (Kernel LSM, SecureBoot, TPM, remote audit).
This is an accepted boundary documented here and in the implementation notes.

### 2.4 Files

See `docs/context/roadmap-merge-controller-2026-07-19.md` for the file manifest.
`orchestrator/scripts/roadmap_merge_guard.py` and
`orchestrator/scripts/repo_writer.py` lock/worktree semantics are unchanged.

### 2.5 Writer contract extension

`repo_writer.RepoWriterLock` gains a new method `perform_governed_merge()`
that calls `assert_held()` and then delegates to the controller client.
The lock and worktree primitives are unchanged; existing writer tests pass
unmodified.

### 2.6 Activation

The controller is **shipped disabled**. No enable switch, no merge credential,
no broker systemd service is deployed by this PR. Activation is a separate,
operator-only step (see Issue #638 §"Activation prerequisites").

## 3. Consequences

- **Positive:** Real security boundary through root-broker credential isolation.
- **Positive:** Independent verification of every invariant by the broker.
- **Positive:** Three unambiguous merge outcome states handle the edge case
  where a GitHub merge succeeds but the audit fails.
- **Negative:** Broker adds operational complexity (systemd service, socket,
  credential delivery, `chattr +a` management).
- **Risk:** See §2.3 — root compromise defeats `chattr +a`.

## 4. References

- Issue #638 (binding specification)
- `orchestrator/scripts/roadmap_merge_controller.py`
- `orchestrator/scripts/roadmap_merge_controller_broker.py`
- `orchestrator/scripts/roadmap_merge_controller_denylist.txt`
- `orchestrator/scripts/roadmap_merge_controller_allowlist.txt`
- `orchestrator/scripts/roadmap_merge_controller_paths_allowlist.txt`
- `orchestrator/scripts/repo_writer.py` (new `perform_governed_merge()`)
- `tests/test_roadmap_merge_controller.py`
