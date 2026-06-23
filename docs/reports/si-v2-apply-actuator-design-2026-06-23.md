# SI-v2 Apply Actuator — Design Report

**Date:** 2026-06-23
**Issue:** #332
**PR:** feat/si-v2-apply-actuator-332 (to be opened)
**Status:** Implementation Complete, Awaiting Review

## Problem

The previous SI-v2 controlled apply (PR #331, candidate `65502d13`) created an overlay
file at the WRONG host path (`freqtrade/bots/freqforge/user_data/`) which is NOT the
Docker bind mount for the freqforge container. Even if placed correctly, Freqtrade has
no mechanism to read `overlay_*.json` files natively. The mutation counter was incremented
despite zero runtime effect.

PR #333 corrected the false `APPLIED` status to `NO_RUNTIME_EFFECT`.

## Solution: Fleet-Aware Apply Actuator

The Apply Actuator is a fail-closed, fleet-aware, machine-verifiable mechanism that
connects ShadowProposal → Overlay → Runtime Effect → Mutation Counter → Measurement.

### Core Invariants

1. **Mutation counter increments ONLY if `RuntimeEffectProof.proof_status == "GREEN"`**
2. **Measurement starts ONLY if `ApplyActuatorResult.status == "APPLIED_WITH_RUNTIME_PROOF"`**

### Architecture

```
ShadowProposal → RuntimeBinding → OverlayMerge → RuntimeProof → ActuatorResult
                     ↑                ↑               ↑              ↑
                 Fleet table      Safety check    Docker exec    Mutation gate
                 (verified)      (forbidden keys) (read-only)   Measurement gate
```

### Module Structure

```
self_improvement_v2/src/si_v2/apply_actuator/
├── __init__.py          # Public API
├── models.py            # Typed dataclasses (BotRuntimeBinding, OverlayProposal, etc.)
├── runtime_binding.py   # Fleet-verified path table for all 4 bots
├── overlay_merge.py     # Safe effective config generation (no deployment)
├── proof.py             # Container visibility + loaded config checks
└── policy.py            # Central decision logic (fail-closed)
```

### Key Design Decisions

1. **Fleet binding is hardcoded and verified.** The runtime binding table was
   created via `docker inspect` and read-only `docker exec`. No path guessing.

2. **Config activation strategy: multi-config overlay.** Freqtrade 2026.3 supports
   `--config config.json --config overlay_NNN.json`. This is preferred because:
   - Never modifies base `config.json`
   - Atomic rollback: just remove the overlay file
   - Clear audit trail

3. **No runtime mutation in this task.** The actuator generates EffectiveConfigDrafts
   but deployment requires a separate L3 activation with explicit approval token.

4. **Fail-closed.** Any uncertainty (wrong path, missing binding, dry_run=false,
   strategy change, docker unavailable) → BLOCKED.

5. **Docker-based runtime proof.** Uses `docker exec` read-only to verify file
   visibility and loaded config values. No container state mutation.

### Status Enums

| Status | Meaning |
|--------|---------|
| `NO_RUNTIME_EFFECT` | Overlay exists at wrong path or not loaded |
| `DRAFTED_NOT_APPLIED` | Effective config generated but not deployed |
| `RUNTIME_PROOF_REQUIRED` | File in correct path but not loaded by bot |
| `APPLIED_WITH_RUNTIME_PROOF` | GREEN — runtime effect verified |
| `BLOCKED` | Safety gate blocked |

### Proof Gate

The proof checks:
1. File visibility inside container (Docker exec)
2. Effective config contains expected values
3. Loaded config contains expected values
4. `dry_run=True` preserved
5. Live trading disabled
6. Strategy unchanged

Only GREEN proof allows mutation counter increment and measurement.

## Safety

- No live trading
- No `dry_run=false`
- No strategy changes
- No Docker/Compose mutations
- No bot restarts
- Future L3 activation requires: `APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION="APPROVE"`
