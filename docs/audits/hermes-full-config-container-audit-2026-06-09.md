# Hermes Full Config & Container Audit — 2026-06-09

**Audit timestamp (UTC):** 2026-06-09T21:04:08Z  
**Classification:** YELLOW 78/100  
**Auditor:** Hermes External Operations Agent  
**Mode:** Read-only audit + minimal safe fixes (approved execution plan)

---

## 1. .env ACL Fix

### Before
| Field | Value |
|-------|-------|
| Owner | `10000` (no matching user) |
| Group | `hermes` (GID 1337) |
| Mode | `600` |
| ACL | `user:10000:rwx #effective:---` |
| ACL mask | `::---` → **blocked all access** |
| Effective | Unreadable by anyone (including `hermes`) |
| `docker compose config --quiet` | ❌ `open .env: permission denied` |

### Action Taken
```bash
sudo cp -a .env ".env.bak-20260609T210408Z"
sudo setfacl -b .env
sudo chown hermes:hermes .env
sudo chmod 600 .env
```

### After
| Field | Value |
|-------|-------|
| Owner | `hermes:hermes` (1337:1337) |
| Mode | `600` |
| ACL | None (standard POSIX only) |
| `hermes test -r .env` | ✅ OK |
| `docker compose config --quiet` | ✅ OK (exit 0) |

### Backup
- Path: `/home/hermes/projects/trading/.env.bak-20260609T210408Z`
- Owned by: `10000:hermes` (original state preserved)

---

## 2. Mem0 Runtime Patch Preservation

### Before
- `green-mem0` container: Up 5h, healthy
- `hermes-mem0-local-api:stable` image
- Host `/opt/data/local-memory/app/app.py` mounted as bind (ro)
- **No backup** of active container app.py on host

### Action Taken
```bash
sudo docker cp green-mem0:/app/app.py /opt/data/local-memory/app.py.container-active
sudo chmod 600 /opt/data/local-memory/app.py.container-active
```

### After
| Path | Size | SHA256 | Mode |
|------|------|--------|------|
| `/opt/data/local-memory/app.py.container-active` | 12,997 bytes | `0e051250325ad7b052a58b8fac7b363606ce8dfc8083f14225308426c3d59b21` | 600 |

**No runtime mutation:** Container was not restarted, recreated, or modified.

---

## 3. Compose-vs-Runtime Drift (Unchanged)

`docker-compose.yml` and `Caddyfile` timestamps are unchanged from before audit. No compose edits, no rebuilds, no restarts.

Known drift (documented, not fixed this run):
- `docker-compose.yml`: 31 lines changed (Dashboard, MEM0_LLM_MODEL, extraction_policy_v2, sleep infinity removed, :8642 commented out)
- `Caddyfile`: 26 lines changed (momentum + webserver stale routes commented out)
- Both remain uncommitted — compose drift fix deferred until `.env` validation baseline is stable.

---

## 4. Secrets Exposure Risk (Documented)

API keys are visible via `docker inspect` for Docker-authorized users. This is inherent to container environment variables. No runtime changes made.

**Risk accepted for now.** Mitigation (Docker secrets / file-based secrets) deferred to later hardening sprint.

---

## 5. Remaining Open Items

| ID | Issue | Severity | Status |
|----|-------|----------|--------|
| P1 | `.env` ACL (FIXED) | — | ✅ Resolved |
| P1 | `app.py.container-active` missing (FIXED) | — | ✅ Resolved |
| P1 | API keys via `docker inspect` | Secrets leakage | 📝 Documented, not fixed |
| P2 | Compose-vs-Runtime drift | Non-reproducible state | 📝 Deferred (blocked by compose validation — now unblocked) |
| P2 | 37 GB Docker reclaimable | Disk waste | ⏸ Needs approval for `docker system prune` |
| P2 | Port 8642 still open (deprecated) | Attack surface | ⏸ Next compose maintenance |

---

## 6. Verdict

| Criterion | Status |
|-----------|--------|
| `.env` readable by `hermes` | ✅ |
| `docker compose config --quiet` | ✅ |
| `app.py.container-active` preserved | ✅ |
| Audit report written | ✅ |
| Any compose edit, rebuild, restart, `chown -R`, `chmod 644`, or secret output | ❌ None occurred |

**Overall: YELLOW 78/100 remains appropriate** — Runtime is healthy, the blocker is resolved, but compose drift and secrets exposure are still open.

### Recommended Next Action
Proceed to compose drift fix (edit `docker-compose.yml` and `Caddyfile` to match runtime) now that `.env` validation works.
