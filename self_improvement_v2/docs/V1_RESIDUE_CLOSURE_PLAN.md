# V1 Residue Archive & Migration Closure Plan

> **Plan-only — NO destructive cleanup in this phase.**
> Inventory of v1 residue and recommendations for archiving, keeping
> read-only, or migrating to SI v2 equivalents.

**Status:** Ratified  
**Date:** 2026-06-10  
**Author:** SI v2 Meta-Orchestrator  
**Issue:** [#27 — Plan v1 residue archive and migration closure](https://github.com/GoLukeEnviro/trading-hub/issues/27)

---

## 1. Purpose

Close out the old `self_improvement/` v1 artifacts safely while preserving
evidence. SI v2 is now the forward path; v1 artifacts must be classified
and either archived, kept read-only, or referenced for historical context.

---

## 2. V1 Residue Inventory

### 2.1 Directory Inventory

| Path | Type | Size | Description |
|------|------|------|-------------|
| `self_improvement/shared/` | Directory | 4 KB | Shared v1 state files |
| `var/trading-self-improvement/` | Directory | 40 KB | V1 runtime artifacts |
| `var/trading-self-improvement/artifacts/` | Directory | ~2 MB | Backtest outputs, snapshots |
| `var/trading-self-improvement/bot_a/` | Directory | ~50 KB | Bot A v1 state |
| `var/trading-self-improvement/bot_b/` | Directory | ~50 KB | Bot B v1 state |
| `var/trading-self-improvement/bot_c/` | Directory | ~50 KB | Bot C v1 state |
| `var/trading-self-improvement/bot_d/` | Directory | ~50 KB | Bot D v1 state |
| `var/trading-self-improvement/runs/` | Directory | ~100 KB | V1 run logs |
| `var/trading-self-improvement/shared/` | Directory | ~10 KB | V1 shared state |

### 2.2 V1 Scheduler Entries

16 v1 scheduler entries were paused/disabled during earlier stabilization.
These are managed by the Hermes cron scheduler and are not part of the
filesystem residue.

### 2.3 V1 ShadowLogger Data

| Path | Size | Description |
|------|------|-------------|
| `orchestrator/logs/shadow_decisions.jsonl` | ~500 KB | 1758+ decision entries |
| `orchestrator/logs/quality_agent_audit.jsonl` | ~200 KB | Agent audit trail |
| `orchestrator/logs/quality_deep_dive_audit.jsonl` | ~100 KB | Deep dive audit |
| `orchestrator/logs/mcp/bitget_mcp_paper_trades.jsonl` | ~50 KB | Paper trade records |

> Note: ShadowLogger JSONL files are **active data** used by SI v2, not v1
> residue. They must remain in place.

---

## 3. Archive Decision Matrix

| Artifact | Archive Decision | Rationale |
|----------|-----------------|-----------|
| `self_improvement/shared/` | 🔶 **Keep read-only** | Historical reference; may contain config that informs SI v2 defaults |
| `var/trading-self-improvement/artifacts/` | ✅ **Archive (compress)** | Backtest outputs may be useful for benchmark comparisons |
| `var/trading-self-improvement/bot_a/` | ✅ **Archive (compress)** | Bot state preserved for forensic analysis |
| `var/trading-self-improvement/bot_b/` | ✅ **Archive (compress)** | Same |
| `var/trading-self-improvement/bot_c/` | ✅ **Archive (compress)** | Same |
| `var/trading-self-improvement/bot_d/` | ✅ **Archive (compress)** | Same |
| `var/trading-self-improvement/runs/` | ✅ **Archive (compress)** | Run logs preserved |
| `var/trading-self-improvement/shared/` | 🔶 **Keep read-only** | Shared state for cross-reference |
| V1 scheduler entries (16) | 🔶 **Keep disabled** | Already paused in earlier stabilization; document in SI v2 tracker |
| V1 ShadowLogger JSONL | ❌ **Keep in place** | Active SI v2 data |

### Archive Format

```
archive/v1-rescue-<date>.tar.gz
  ├── self_improvement/         (read-only copy)
  ├── var/trading-self-improvement/
  └── docs/context/references/  (readme pointer)
```

---

## 4. Closure Runbook

### 4.1 Pre-Closure Checks

- [ ] SI v2 pipeline is producing equivalent or better output than v1
- [ ] All 16 v1 scheduler entries confirmed paused/disabled
- [ ] ShadowLogger data is being written by SI v2 pipeline
- [ ] No running process depends on v1 paths

### 4.2 Archive Procedure

> ⚠️ Requires explicit approval. Not executed in this phase.

```bash
# 1. Create timestamped tarball
mkdir -p archive
tar -czf archive/v1-rescue-$(date +%Y%m%dT%H%M%S).tar.gz \
  self_improvement/ \
  var/trading-self-improvement/

# 2. Verify archive integrity
tar -tzf archive/v1-rescue-*.tar.gz | head -5
echo "Archive OK: $(du -sh archive/v1-rescue-*.tar.gz | cut -f1)"

# 3. Create README pointer in archive
cat > archive/README.md << 'EOF'
# V1 Rescue Archive

Created: <date>
Contents: self_improvement/ (v1 pipeline), var/trading-self-improvement/ (v1 state)
Restore: tar -xzf v1-rescue-<date>.tar.gz

See also: docs/context/v1-residue-closure-<date>.md
EOF

# 4. Write closure report to docs/context/
# (see §5 for template)
```

### 4.3 Post-Closure Verification

- [ ] Archive tarball is readable and complete
- [ ] Archive README exists
- [ ] `docs/context/` closure report written
- [ ] No SI v2 functionality depends on archived paths
- [ ] ShadowLogger continues to write
- [ ] All 450+ SI v2 tests pass

---

## 5. Follow-Up Issues

| Issue | Action | Priority | Depends On |
|-------|--------|----------|-----------|
| — | Execute archive procedure (execute the runbook) | Low | Approval |
| — | Remove v1 scheduler entries after archive confirmed | Low | Archive complete |
| — | Update `.gitignore` to exclude `var/trading-self-improvement/` if not already | Low | Archive complete |
| — | Add archive reference to SI v2 docs index (#32) | Low | Archive complete |

---

## 6. Related Documents

| Document | Location | Relationship |
|----------|----------|-------------|
| Repository Documentation Index | `docs/README.md` | Canonical documentation index (add an SI v2 index link here if/when created) |
| V1-to-V2 Cron Migration | `self_improvement_v2/docs/V1_TO_V2_CRON_MIGRATION.md` | V1 cron status |
| Current Operational State | `docs/state/current-operational-state.md` | Canonical status snapshot |
