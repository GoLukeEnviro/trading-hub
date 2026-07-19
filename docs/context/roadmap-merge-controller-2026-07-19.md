# Roadmap Merge Controller — Implementation Notes

**Date:** 2026-07-19
**PR:** (this replacement PR)
**ADR:** [ADR-2026-07-19](../decisions/ADR-2026-07-19-roadmap-autonomous-merge-controller.md)
**Scope:** A1 repository-only; governance transition
**Base:** PR #637 merge SHA `b18bbf0`

## Architecture

### Components

```
┌─────────────────────────────────────────┐
│ Hermes Agent (UID 10000)                │
│  ┌─────────────────────────────────┐    │
│  │ roadmap_merge_controller.py     │    │
│  │ (client, slim pre-check only)   │    │
│  │ → checks disable/halt switch    │    │
│  │ → sends IPC request to broker   │    │
│  └───────────┬─────────────────────┘    │
│              │ Unix socket              │
│              │ SO_PEERCRED              │
└──────────────┼──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ Root Broker (UID 0)                     │
│ /var/run/roadmap-merge-broker.sock      │
│ runs as root systemd service            │
│                                          │
│ roadmap_merge_controller_broker.py      │
│  → peer-credential check                │
│  → independent GitHub snapshot          │
│  → independent guard evaluation         │
│  → denylist + path allowlist + A1-only  │
│  → pre-merge TOCTOU re-snapshot         │
│  → INTENT audit (chattr +a)            │
│  → gh pr merge --squash --match-head-commit
│  → on timeout: re-query GitHub          │
│  → COMPLETION audit (chattr +a)        │
│  → on failure: halt file + journald    │
└──────────────────────────────────────────┘
```

### Threat model boundaries (acknowledged)

- `chattr +a` protects against the unprivileged controller (UID 10000) but
  NOT against a compromised root. Root can remove `+a`, rewrite the audit,
  and impersonate the broker. This boundary is explicitly documented and
  accepted. Root-level integrity requires host-level security (Kernel LSM,
  SecureBoot, TPM, remote audit forwarding).

## Files changed

### New
- `orchestrator/scripts/roadmap_merge_controller.py` — client client
- `orchestrator/scripts/roadmap_merge_controller_broker.py` — root broker
- `orchestrator/scripts/roadmap_merge_controller_denylist.txt` — human-only paths
- `orchestrator/scripts/roadmap_merge_controller_allowlist.txt` — identity allowlist
- `orchestrator/scripts/roadmap_merge_controller_paths_allowlist.txt` — canary phase-0
- `tests/test_roadmap_merge_controller.py` — 19+12 tests
- `docs/decisions/ADR-2026-07-19-roadmap-autonomous-merge-controller.md`
- `docs/context/roadmap-merge-controller-2026-07-19.md` (this file)

### Modified
- `orchestrator/scripts/repo_writer.py` — adds `perform_governed_merge()`
- `AGENTS.md` — updated merge boundary section
- `commands/trading-hub-roadmap-tick.md` — step 8 update

### Unchanged (verified)
- `orchestrator/scripts/roadmap_merge_guard.py` — 0 lines changed, 21 tests pass
- `tests/test_roadmap_merge_guard.py` — 0 lines changed

## Activation prerequisites (separate step, not in this PR)

See ADR-2026-07-19 §"Activation prerequisites" for the complete list.
Key items:
- Root-broker systemd service installation
- `chattr +a` on audit file
- Switch file creation by operator
- GitHub branch-protection audit
- Credential-isolation proof
