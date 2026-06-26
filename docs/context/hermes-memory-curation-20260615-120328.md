# Hermes Memory Curation — 2026-06-15 12:03 UTC

## Status

Status: OK  
Operation Level: L2 — safe orchestrator-memory write and documentation only.

## Scope

Curated the active orchestrator profile memory at:

- `/opt/data/profiles/orchestrator/memories/MEMORY.md`

No trading runtime, Docker container, Freqtrade config, strategy logic, RiskGuard behavior, credentials, or live-trading state was changed.

## Changes

- Consolidated GitHub authentication notes into one compact entry.
- Removed duplicate SSH-key workflow entry after merging its operational value into the GitHub entry.
- Replaced stale fleet snapshot wording with a durable dry-run/multi-bot memory rule.
- Replaced PR-progress memory with a compact durable CI-quirks entry.
- Removed duplicate runtime-mutation preference from `memory` because it is already present in the user profile.
- Added the durable correction that Honcho is decommissioned/archived and Honcho/Deriver memory work is stale unless explicitly reactivated.

## Verification Evidence

Read-back and counting command returned:

```txt
chars= 1083
entries= 6
contains_old_honcho_deriver= False
contains_pr_progress= False
contains_stale_container_count= False
```

Memory tool reported final usage:

```txt
49% — 1,083/2,200 chars
entry_count=6
```

## Safety Notes

- No secret values were added or printed.
- Credential-path operational detail remains only in the active Hermes memory for future authenticated Git operations; key material itself was not exposed.
- The cleanup removed task-progress details that should not live in durable memory.

## Next Memory Plan

1. Keep memory under ~1,500/2,200 chars to preserve operating headroom.
2. Replace snapshot-like runtime facts with durable rules.
3. Store task progress, PR numbers, and incident details in `docs/context/`, not canonical memory.
4. Treat Honcho references as stale unless the user explicitly reactivates Honcho.
5. Re-check memory after major runtime architecture changes or GitHub workflow changes.
