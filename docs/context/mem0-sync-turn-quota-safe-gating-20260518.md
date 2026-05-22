# Mem0 sync_turn Quota-Safe Gating — 2026-05-18

## Root Cause

`sync_turn` in the Mem0 plugin sends **every raw conversation turn** to Mem0 Cloud.
Tool-heavy sessions (terminal output, diffs, tracebacks, grep results, file reads)
consume Mem0 quota on content that Mem0's server-side deduplication rejects anyway.
This burns through the free tier quota (1000 calls/month) without producing useful memories.

## Solution

Added a deterministic, cheap gating function `_should_sync_turn()` in the Mem0 plugin
that evaluates whether a turn is worth syncing before making the API call.

### Changed Files

| File | Change |
|------|--------|
| `/opt/hermes/plugins/memory/mem0/__init__.py` | Added `_should_sync_turn()`, `_is_noise_line()`, noise markers, memory keywords, gate in `sync_turn()` |

### Backup

| File | Path |
|------|------|
| mem0 plugin | `/home/hermes/projects/trading/docs/backups/mem0_plugin.20260518T032225Z.bak` |

### Config

New config key `sync_policy` in Mem0 config (`mem0.json` or `config.yaml`):

| Value | Behavior |
|-------|----------|
| `quota_safe` (default) | Skip tool-heavy/noisy turns |
| `all` | Sync everything (legacy behavior) |

### Gating Rules (in order)

1. **Empty content** → SKIP
2. **Explicit memory keywords** in user message → ALLOW (remember, merk dir, speicher, save this, etc.)
3. **Tool-noise line ratio > 60%** → SKIP (lines > 3, noise markers detected)
4. **Short conversational turn** (< 200 chars user, < 3000 chars assistant) → ALLOW
5. **Very long assistant** (> 5000 chars) without memory keywords → SKIP
6. **Default** → ALLOW

### Noise Markers

exit_code, stderr, stdout, Traceback, File "<, docker exec, docker ps, grep:, cat:,
--- stderr ---, tool_calls_made, duration_seconds, LINE_NUM| pattern (read_file output)

### Memory Keywords (always pass gate)

remember, merk dir, speicher, save this, note that, never forget, wichtig,
important:, conclusion:, decision:, architecture:, config:, hard rule, critical rule

### Not Affected

- `mem0_conclude` — goes through `handle_tool_call()`, NOT `sync_turn()`. Always passes.
- `mem0_search` — read-only, no quota impact
- `mem0_profile` — read-only, no quota impact
- Background whitelist patch — unchanged

### Test Results

```
18/18 PASS
- explicit memory requests: ALLOW
- short conversational turns: ALLOW  
- tool-heavy dumps: SKIP
- traceback floods: SKIP
- read_file output: SKIP
- very long outputs without keywords: SKIP
- policy=all: everything ALLOW (backward compat)
- empty content: SKIP
- German keywords: ALLOW
```

### Estimated Quota Reduction

| Session Type | Turns | Before | After | Reduction |
|---|---|---|---|---|
| Tool-heavy (Dream Mode) | 50 | 50 API calls | ~20 API calls | ~60% |
| Conversational | 20 | 20 API calls | ~18 API calls | ~10% |
| Mixed | 30 | 30 API calls | ~15 API calls | ~50% |

### Remaining Risks

1. **False negatives**: Some meaningful content might be skipped if it looks like tool output.
   Mitigation: Memory keywords override the gate; explicit saves always pass.
2. **False positives**: Some noise might pass if under the threshold.
   Mitigation: Conservative by design; better to let some noise through than block useful content.
3. **Config migration**: Default is `quota_safe`. If a user expects `all`, they need to set it explicitly.

### Rollback

```bash
cp /home/hermes/projects/trading/docs/backups/mem0_plugin.20260518T032225Z.bak \
   /opt/hermes/plugins/memory/mem0/__init__.py
```

### Related

- Whitelist patch: `docs/context/mem0-background-whitelist-fix-20260518.md`
- Mem0 quota exhaustion: 1000/1000 calls used (HTTP 429)
- E2E validation: Blocked until quota resets or plan is upgraded
