# Phase 12.5 State Drift Audit — 2026-05-07

## Executive Summary

**Status: PASS — No Drift Detected**

All state files schema-stable at v0.2.

## Files Audited

| File | Exists | Valid JSON | Schema | Pairs |
|------|--------|------------|--------|-------|
| rsi | ✅ | ✅ | 0.2 | 7 |
| momentum | ✅ | ✅ | 0.2 | 7 |
| regime-hybrid | ✅ | ✅ | 0.2 | 7 |

## Required Top-Level Fields

| Field | Status |
|-------|--------|
| schema_version | ✅ Present |
| bridge_version | ✅ Present |
| written_at | ✅ Present |
| source_type | ✅ Present |
| riskguard_available | ✅ Present |
| pairs | ✅ Present |
| summary | ✅ Present |

**Missing Fields:** None

## Required Pair Fields

| Field | Status |
|-------|--------|
| pair | ✅ Present |
| source_action | ✅ Present |
| normalized_action | ✅ Present |
| confidence | ✅ Present |
| verdict | ✅ Present |
| reasons | ✅ Present |
| age_seconds | ✅ Present |
| is_fresh | ✅ Present |
| allow_long_bias | ✅ Present |
| allow_short_bias | ✅ Present |
| watch_only | ✅ Present |
| block_entry | ✅ Present |

**Missing Fields:** None

## Schema Consistency

- **All Files:** Schema 0.2
- **Bridge Version:** 0.2.0-risk-aware (consistent)
- **Source Type:** riskguard (consistent)
- **Drift Detected:** No

## Verdict

**PASS — Schema-stable, no drift across 5 wrapper runs.**

---

**Audit Date:** 2026-05-07  
**Status:** PASS  
**Schema Version:** 0.2 (stable)
