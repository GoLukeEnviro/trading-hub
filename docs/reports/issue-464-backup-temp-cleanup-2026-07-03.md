# Issue #464 Backup/Temp Cleanup — 2026-07-03

## Scope

Bulk cleanup of untracked `.bak`, `.bak-*`, `.tmp`, `.tmp-*`, `.backup`,
`.backup-*` files across the repo, excluding `.env.bak-*` (security-sensitive).

## Approval marker

```
APPROVED_UNTRACKED_BACKUP_TEMP_CLEANUP_FOR_464_PHASE_1_AND_2
```

## Pre-cleanup counts

| Metric | Value |
|--------|------:|
| Candidate files | 9,169 |
| Total disk usage (as reported by `du`) | 42 MB |
| Tracked in Git | 0 |
| Restore tarball size (compressed) | 1.2 MB |

## Tarball path

```
/home/hermes/projects/trading-cleanup-backups/issue-464/
  untracked-backup-temp-before-cleanup-20260703T103149Z.tar.gz
```

## Cleanup categories

| Category | Count | Source |
|----------|------:|--------|
| `orchestrator/backups/system-optimizer-state/` | ~6,842 | State JSON .bak files |
| `orchestrator/backups/system-optimizer-config/` | ~1,848 | Config JSON .bak files |
| `freqtrade/bots/freqai-rebel/` | ~403 | `config.json.bak-*` |
| `freqtrade/bots/regime-hybrid/` | ~13 | `config.json.bak-*` |
| `freqforge/` & `freqforge-canary/` | ~13 | Misc .bak files |
| `root-level` (docker-compose.yml.bak-*, .venv.bak-*) | ~8 | Compose/venv backups |
| `freqtrade/shared/` (`.fleet_risk_state.json.tmp-*`, *.bak*) | ~10 | Stale lock files, code backups |
| `backups/` (mem0-llm-switch) | ~6 | Pre-deploy snapshots |
| `local-memory/` | ~3 | Code backups |
| `docs/backups/` | ~3 | 838 KB run_agent.py.bak |
| `self_improvement_v2/` | ~1 | Misc |
| **Total** | **9,169** | |

## Files intentionally excluded

| File | Reason |
|------|--------|
| `.env.bak-20260609T210408Z` | Security-sensitive — may contain secrets. Requires separate L3 approval. |

## Post-cleanup counts

```bash
find . \( -name "*.bak" -o -name "*.bak-*" -o -name "*.tmp" -o -name "*.tmp-*" \
  -o -name "*.backup" -o -name "*.backup-*" \) -type f \
  ! -name ".env.bak*" ! -path "./.git/*" -print | wc -l
```
**Result: 0** — all cleanup candidates removed.

## Validation

- Cleanup: `xargs rm -f` → exit 0
- Post-scan: 0 remaining candidates
- `.env.bak-*` still exists: confirmed (73 bytes)
- `git status -sb`: no tracked files modified or deleted
- Git status shows only untracked pre-existing context/log artifacts

## Safety statement

```
No tracked files deleted.
No git clean used.
No runtime config changed.
No Docker/Cron/Freqtrade config/strategy changes.
No .env.bak-* files touched.
Restore tarball created before deletion.
```

## Remaining follow-ups

- `.env.bak-20260609T210408Z` — evaluate and handle separately (L3)
- Periodic cleanup: consider adding automated retention policy for
  `orchestrator/backups/system-optimizer-*/` (keep latest 5, auto-prune older)
