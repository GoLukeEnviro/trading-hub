# SI-v2 Apply Correction — NO_RUNTIME_EFFECT

## Status
**NO_RUNTIME_EFFECT** 🔴

## Finding
Post-merge audit discovered that PR #331 overlay has zero runtime effect on freqforge bot.

### Root Causes

| Layer | Finding | Impact |
|-------|---------|--------|
| **Path mismatch** | Overlay committed to `freqtrade/bots/freqforge/user_data/overlay_65502d13.json` but freqforge container mounts `freqforge/user_data/` (from `docker-compose.yml`) | Bot cannot see the overlay file |
| **No loader mechanism** | Freqtrade reads `config.json` only — no native `overlay_*.json` merging exists | Even correct placement would have no effect |

### Evidence

**Container mount source** (from `docker inspect`):
```
/home/hermes/projects/trading/freqforge/user_data → /freqtrade/user_data (rw)
```

**Overlay location** (from PR #331):
```
/home/hermes/projects/trading/freqtrade/bots/freqforge/user_data/overlay_65502d13.json
```

These are **different directory trees**. The overlay is in a path the container does not mount.

**Active bot config** (loaded, unchanged):
```json
{
    "max_open_trades": 5,
    "stake_amount": 50,
    "tradable_balance_ratio": 0.95,
    "dry_run": true
}
```

**Overlay intended values** (never loaded):
```json
{
    "max_open_trades": 3,
    "stake_amount": "unlimited",
    "tradable_balance_ratio": 0.99
}
```

### Loop State After Audit

```
ShadowProposal    ✅
Approval          ✅
Overlay Artifact  ✅ (file exists but inert)
Runtime Effect    ❌ (bot config unchanged)
Measurement       ❌ (blocked — would measure zero effect)
```

### Reclassification

PR #331 must be reclassified from `APPLIED` to `NO_RUNTIME_EFFECT`.

The apply was an artifact commit, not a runtime mutation.

### Blocked Actions

- ❌ No measurement cycles for 65502d13 (would produce false attribution)
- ❌ No mutation counter increment
- ❌ No keep/rollback decision (nothing to keep or rollback from runtime)

### Unblocked Actions

- ✅ Issue #332: Build fleet-aware overlay activation mechanism
- ✅ Future proposals with working actuator

## Next Step

See **Issue #332**: "SI-v2: Implement fleet-aware overlay activation before measurement"

No further SI-v2 apply or measurement until the actuator is implemented and verified.
