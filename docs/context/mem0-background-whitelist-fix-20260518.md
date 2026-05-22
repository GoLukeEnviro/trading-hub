# Mem0 Background Review Whitelist Fix

**Date:** 2026-05-18
**Status:** PATCHED + QUOTA-BLOCKED — whitelist fix applied, but Mem0 free tier quota exhausted. Needs plan upgrade or billing reset + session restart.
**Severity:** Medium (whitelist bug FIXED, but Mem0 billing quota exhausted — blocking all writes)

## Root Cause

The background skill review in `run_agent.py` builds a tool whitelist from:

```python
get_tool_definitions(enabled_toolsets=["memory", "skills"])
```

Memory Provider tools (`mem0_conclude`, `mem0_search`, `mem0_profile`) are **not**
registered through the toolset system — they're registered via `MemoryManager.add_provider()`.
The whitelist therefore never includes them, and the guardrail denies all provider
tool calls with:

```
Background review denied non-whitelisted tool: mem0_conclude.
Only memory/skill tools are allowed.
```

This means the background review path (which runs after every few turns to save
learnings) **cannot write any memories to Mem0 Cloud**. The only memories that
get saved are those from `sync_turn` (automatic per-turn extraction), which is
subject to Mem0's aggressive server-side deduplication.

## Symptoms

- Mem0 memories stagnate at ~100 entries
- All memories cluster around a single high-conversation session
- Background review logs show `mem0_conclude` denied at 22:08 and 22:19 on 2026-05-17
- No new memories created from background review since Mem0 activation

## Fix

**File:** `/opt/hermes/run_agent.py`
**Lines:** 4411–4421 (inserted after line 4410)
**Backup:** `/home/hermes/projects/trading/docs/backups/run_agent.py.20260518T030244Z.bak`

### Diff

```diff
@@ -4408,6 +4408,17 @@
                             quiet_mode=True,
                         )
                     }
+                    # Memory provider tools (e.g. mem0_conclude) are registered
+                    # via MemoryManager, not through the toolset system.  Add
+                    # them dynamically so the background review can persist
+                    # conclusions through the active provider.
+                    if self._memory_manager:
+                        review_whitelist |= self._memory_manager.get_all_tool_names()
+                    logger.debug(
+                        "Background review whitelist (%d tools): %s",
+                        len(review_whitelist),
+                        sorted(review_whitelist),
+                    )
                     set_thread_tool_whitelist(
                         review_whitelist,
                         deny_msg_fmt=(
```

### What it does

1. After building the toolset-based whitelist, checks if `self._memory_manager` exists
2. If yes, merges all memory provider tool names into the whitelist via set union
3. Logs the full whitelist at DEBUG level for diagnostics (no secrets)
4. The merge is dynamic — if the provider changes, the whitelist auto-updates

### What it does NOT do

- Does not modify `sync_turn` behavior
- Does not add aggressive retry loops
- Does not change memory architecture
- Does not touch Mem0 Cloud config
- Does not reactivate Honcho or Holographic
- Does not delete or modify any existing memories
- Does not increase raw turn storage volume

## Validation

| Test | Result |
|------|--------|
| Python syntax check (`py_compile`) | PASS |
| Existing test suite (62 tests) | 62/62 PASS |
| Lint check (patch tool) | OK |
| Diff review | Minimal (11 lines added, 0 changed, 0 removed) |

### Runtime validation (post-restart required)

- [ ] Background review no longer blocks `mem0_conclude`
- [ ] A conclusion memory can be written via background review
- [ ] Written memory is recallable via Mem0 search
- [ ] No unrelated tools added to whitelist
- [ ] No 429 retry storm in logs
- [ ] Honcho/Holographic remain legacy-disabled
- [ ] Mem0 Cloud remains sole active provider

## Validation Results (2026-05-18 E2E Test)

| Step | Test | Result | Evidence |
|------|------|--------|----------|
| 1 | Patch in run_agent.py | PASS | `get_all_tool_names()` found at expected location |
| 2 | Mem0 Cloud sole provider | PASS | `memory.provider: mem0` |
| 3 | Provider tool names | PASS | `mem0_profile`, `mem0_search`, `mem0_conclude` |
| 4 | Honcho/Holographic disabled | PASS | Legacy-only, not active |
| 5 | Current session has OLD code | INFO | Process started before patch; new session needed |
| 6a | Mem0 API write (validation fact) | PASS | HTTP 200, event_id received |
| 7 | Mem0 API recall search | **FAIL** | HTTP 429 — billing quota exhausted |
| 8 | Background review denial check | **DEFERRED** | Requires new session with patched code |

### Critical Discovery: Mem0 Billing Quota Exhausted

The Mem0 free tier allows **1,000 API calls per billing period**.
During E2E validation, the search endpoint returned:

```
Usage quota exceeded for this billing period.
quota_limit: 1000, quota_used: 1000
```

This is a **hard quota**, not a temporary rate limit. It explains:

1. **Why no new memories appeared since the initial burst** — sync_turn
   calls silently fail with 429, masked by the circuit breaker.
2. **Why the whitelist bug went unnoticed** — even if mem0_conclude had been
   allowed, the API was already quota-exhausted.
3. **Why this audit consumed the last remaining quota** — ~16 API calls
   from the Dream Mode audit alone.

### Whitelist Patch Status

- **Patch is CORRECT** — it fixes the code bug.
- **Patch is INSUFFICIENT alone** — Mem0 billing quota must be addressed first.
- **No damage done** — the 100 existing memories are intact.

### Required Actions

1. **Upgrade Mem0 plan** or **wait for billing period reset**
2. **Reduce API call volume** — sync_turn sends EVERY turn to Mem0;
   most are deduplicated server-side, wasting quota on rejected calls.
3. **Then restart sessions** to activate the whitelist patch.
4. **Then re-run E2E validation** to confirm background review works.

## Remaining Risks

1. **Mem0 billing quota exhaustion** (CURRENT BLOCKER) — free tier 1,000
   calls/billing period is insufficient for an agent that syncs every turn.
   sync_turn alone can consume 50-100 calls per active session per day.
   Multiple concurrent CLI sessions multiply this.

2. **Mem0 server-side dedup** — even with the whitelist fix, Mem0's KI may still
   reject some conclusions as duplicates. This is expected behavior, not a bug.

3. **`mem0_conclude` in non-primary contexts** — subagents and cron jobs have
   `agent_context != "primary"`, and the mem0 plugin already skips writes for
   non-primary contexts. No change needed.

4. **Whitelist scope** — the patch adds ALL provider tools (`mem0_profile`,
   `mem0_search`, `mem0_conclude`), not just `mem0_conclude`. This is acceptable
   because MemoryManager only registers memory-related tools, never terminal/
   code/system tools. Risk: low.

## Rollback

```bash
cp /home/hermes/projects/trading/docs/backups/run_agent.py.20260518T030244Z.bak /opt/hermes/run_agent.py
```

Then restart the affected Hermes session(s).


## Update 2026-05-18T0330Z: Quota-Safe Gating Added

The whitelist patch is correct and remains in place.
However, live E2E validation remains blocked by Mem0 Cloud quota exhaustion (HTTP 429).

A follow-up fix was applied to prevent future quota burn:
`docs/context/mem0-sync-turn-quota-safe-gating-20260518.md`

Key changes:
- `sync_turn` now gates turns through `_should_sync_turn()` before calling Mem0 API
- Tool-heavy/noisy turns are skipped deterministically (no LLM call)
- Explicit memory saves always pass through
- `mem0_conclude` is unaffected (different code path)
- Default policy: `quota_safe` (configurable to `all` for legacy behavior)
