# Phase 12 Risk-Aware Bridge Contract — 2026-05-07

## Executive Summary

This document defines the exact state contract for the risk-aware bridge upgrade.

---

## State File Schema

**Path:** `bots/<bot>/user_data/primo_signal_state.json`

### Required Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | "0.2" (upgraded from 0.1) |
| `bridge_version` | string | "0.2.0-risk-aware" |
| `written_at` | string | ISO timestamp of write |
| `source_type` | string | "riskguard" / "raw_fallback" / "fail_open_no_riskguard" |
| `source_file` | string | Path to source JSON |
| `riskguard_available` | boolean | Whether RiskGuard output was available |
| `riskguard_version` | string | RiskGuard version if available |
| `source_generated_at` | string | ISO timestamp from source |
| `max_signal_age_hours` | number | Max age for ACCEPTED verdict |
| `pairs` | object | Per-pair state |
| `summary` | object | Aggregate counts |

### Required Pair Fields

| Field | Type | Description |
|-------|------|-------------|
| `pair` | string | Normalized pair name |
| `source_action` | string | Action from source (BUY/SELL/HOLD/etc.) |
| `normalized_action` | string | Normalized action (BUY/LONG/SELL/SHORT/HOLD) |
| `confidence` | number | Signal confidence 0.0-1.0 |
| `verdict` | string | "ACCEPTED" / "WATCH_ONLY" / "BLOCK_ENTRY" / "UNKNOWN" |
| `reasons` | array | Reason codes from RiskGuard |
| `age_seconds` | number | Signal age in seconds |
| `is_fresh` | boolean | Within max age threshold |
| `allow_long_bias` | boolean | Long entry permission |
| `allow_short_bias` | boolean | Short entry permission |
| `watch_only` | boolean | WATCH_ONLY verdict flag |
| `block_entry` | boolean | BLOCK_ENTRY verdict flag |

### Summary Fields

| Field | Type | Description |
|-------|------|-------------|
| `total` | number | Total pairs |
| `accepted_count` | number | ACCEPTED verdicts |
| `watch_only_count` | number | WATCH_ONLY verdicts |
| `blocked_count` | number | BLOCK_ENTRY verdicts |
| `stale_count` | number | Stale signals |
| `long_bias_count` | number | Pairs with long bias |
| `short_bias_count` | number | Pairs with short bias |
| `fail_open` | boolean | Whether fail-open occurred |

---

## Verdict Logic

### ACCEPTED + BUY/LONG

```json
{
  "verdict": "ACCEPTED",
  "source_action": "BUY",
  "normalized_action": "BUY",
  "allow_long_bias": true,
  "allow_short_bias": false,
  "watch_only": false,
  "block_entry": false
}
```

**Effect:** Strategy may allow long entries (conservative filter).

---

### ACCEPTED + SELL/SHORT

```json
{
  "verdict": "ACCEPTED",
  "source_action": "SELL",
  "normalized_action": "SELL",
  "allow_long_bias": false,
  "allow_short_bias": true,
  "watch_only": false,
  "block_entry": false
}
```

**Effect:** Strategy may allow short entries (conservative filter).

---

### WATCH_ONLY (any action)

```json
{
  "verdict": "WATCH_ONLY",
  "source_action": "HOLD",
  "normalized_action": "HOLD",
  "allow_long_bias": false,
  "allow_short_bias": false,
  "watch_only": true,
  "block_entry": false
}
```

**Effect:** No directional bias. Strategy uses normal logic.

---

### BLOCK_ENTRY (any action)

```json
{
  "verdict": "BLOCK_ENTRY",
  "source_action": "BUY",
  "normalized_action": "BUY",
  "allow_long_bias": false,
  "allow_short_bias": false,
  "watch_only": false,
  "block_entry": true
}
```

**Effect:** No Primo directional permission. Strategy uses normal logic.

---

### HOLD/WATCH/TREND_HOLD (raw fallback)

```json
{
  "verdict": "UNKNOWN",
  "source_action": "HOLD",
  "normalized_action": "HOLD",
  "allow_long_bias": false,
  "allow_short_bias": false,
  "watch_only": false,
  "block_entry": false
}
```

**Effect:** No directional bias. Strategy uses normal logic.

---

### Fail-Open (missing/invalid RiskGuard)

```json
{
  "source_type": "fail_open_no_riskguard",
  "riskguard_available": false,
  "pairs": {},
  "summary": {
    "fail_open": true
  }
}
```

**Effect:** No Primo directional bias. Strategy uses normal logic.

---

## Source Type Values

| Value | Meaning |
|-------|---------|
| `riskguard` | RiskGuard output was used as primary source |
| `raw_fallback` | RiskGuard unavailable, fell back to raw signal (only if explicitly configured) |
| `fail_open_no_riskguard` | RiskGuard missing/invalid, no directional bias applied |

---

## Bridge Behavior Matrix

| Condition | source_type | riskguard_available | fail_open | Effect |
|-----------|-------------|---------------------|-----------|--------|
| RiskGuard valid | `riskguard` | `true` | `false` | Use verdicts |
| RiskGuard missing | `fail_open_no_riskguard` | `false` | `true` | No bias |
| RiskGuard invalid JSON | `fail_open_no_riskguard` | `false` | `true` | No bias |
| RiskGuard stale | `fail_open_no_riskguard` | `false` | `true` | No bias |
| Raw fallback enabled + RiskGuard missing | `raw_fallback` | `false` | `true` | Use raw (not recommended) |

---

## Helper Compatibility

### Backward Compatibility

Helper MUST handle both schema versions:

**Schema 0.1 (old):**
- No `verdict` field
- Uses `action` directly
- `allow_long` / `allow_short` booleans

**Schema 0.2 (new):**
- Has `verdict` field
- Uses `allow_long_bias` / `allow_short_bias`
- `watch_only` and `block_entry` flags

### Helper Logic (Schema 0.2)

```python
def primo_gate_allows(pair, side, state_file, max_age_minutes):
    state = load_signal_state(state_file)
    if not state:
        return True  # fail-open
    
    if not state.get("fresh", False):
        return True  # stale
    
    # Check age
    if state.get("age_minutes", 0) > max_age_minutes:
        return True
    
    pairs = state.get("pairs", {})
    entry = pairs.get(normalize_pair(pair))
    if not entry:
        return True
    
    # NEW: Check verdict first (schema 0.2)
    verdict = entry.get("verdict", "UNKNOWN")
    if verdict == "WATCH_ONLY":
        return True  # neutral, no bias
    if verdict == "BLOCK_ENTRY":
        return True  # neutral, no bias
    
    # ACCEPTED: use bias flags
    if verdict == "ACCEPTED":
        if side == "long":
            return entry.get("allow_long_bias", False)
        if side == "short":
            return entry.get("allow_short_bias", False)
    
    # FALLBACK: backward compatible with schema 0.1
    action = entry.get("action", "")
    if action in {"BUY", "LONG"}:
        return side != "short"
    if action in {"SELL", "SHORT"}:
        return side != "long"
    
    return True
```

---

## Atomic Write Pattern

Bridge MUST use atomic writes:

```python
from tempfile import NamedTemporaryFile
from pathlib import Path

def atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", delete=False, dir=str(path.parent), prefix=path.name + ".tmp.") as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
```

**Why:** Prevents partial writes from corrupting state during bridge execution.

---

## Next Steps

1. ✅ Contract defined
2. → Patch bridge (Phase 3)
3. → Patch helper only if needed (Phase 4)

---

**Contract Date:** 2026-05-07  
**Schema Version:** 0.2  
**Bridge Version:** 0.2.0-risk-aware
