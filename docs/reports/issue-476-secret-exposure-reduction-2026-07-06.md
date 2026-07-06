# Issue #476 — SEC-2: Secret Exposure Reduction

## Verdict
**SEC_2_PARTIALLY_RESOLVED** — orchestrator.env gitignored, exposure documented. Full fix requires compose config change (env_file path) which needs host-level directory creation.

## Scope
- Add `orchestrator.env` to `.gitignore` ✅
- Document all container env secret exposure
- No Freqtrade config changes
- No dry_run=false
- No Canary mutation
- No Docker socket rollback

## Preflight
- **HEAD**: `8afbb90` (main, post-#475 merge)
- **Branch**: `fix/security-reduce-container-secret-exposure-476`
- **hermes-green**: running, socket absent, DOCKER_HOST via proxy

## SEC-2 Inventory

### Container env secrets (names only, no values)

| Container | Secrets in env | Source |
|-----------|---------------|--------|
| **hermes-green** | AIRTABLE_API_KEY, OLLAMA_API_KEY, MSGRAPH_CLIENT_SECRET, DEEPSEEK_API_KEY, API_SERVER_KEY, GLM_API_KEY, HERMES_DASHBOARD_BASIC_AUTH_PASSWORD, NOTION_API_KEY | `--env-file /opt/hermes-green/.env` at runtime (file didn't exist on host, so Docker used the passed file inline) |
| **green-mem0** | OLLAMA_API_KEY, GPG_KEY | `env_file: /home/hermes/projects/trading/.env` in compose |
| **trading-hub-freqai-rebel-1** | GPG_KEY | Inherited from image build |
| **trading-dashboard** | GPG_KEY | Inherited from image build |
| **trading-hub-shadowlock-1** | GPG_KEY | Inherited from image build |
| **beszel-agent** | KEY, TOKEN | Required for beszel operation |

### orchestrator.env exposure
- **Path**: `freqtrade/shared/orchestrator.env`
- **Status**: Untracked, **was** visible in `git status`
- **Contents**: 12 key=value lines including DEEPSEEK_API_KEY, OLLAMA_API_KEY, GLM_API_KEY, API_SERVER_KEY
- **Permissions**: `600 hermes:hermes` — adequate
- **Fix applied**: Added `orchestrator.env` to `.gitignore` — no longer appears in git status

### API_SERVER_KEY issue
- **Value**: `hermes-api-key-123` — trivial, hardcoded
- **Locations**: `freqtrade/shared/orchestrator.env`, `freqforge-canary/.env`, `regime-hybrid/.env`, `freqai-rebel/.env`
- **Risk**: Low (only used for Hermes API server auth, not for exchange access), but trivial key should be rotated
- **Fix**: Requires coordinated rotation — out of scope for this pass

### Dashboard session token
- **Not found** in current `docker inspect` env output
- **Not found** in web_dist HTML (no `__HERMES_SESSION_TOKEN__` in current build)
- **Previously reported** in #476 evidence — may have been in an older build

## Changes Applied

### 1. `.gitignore` — orchestrator.env added
- **File**: `.gitignore` (line 332-334)
- **Pattern**: `orchestrator.env` — matches any `orchestrator.env` at any depth
- **Verification**: `git check-ignore -v freqtrade/shared/orchestrator.env` → `.gitignore:334:orchestrator.env`
- **Commit**: `f0dcb2c` on branch `fix/security-reduce-container-secret-exposure-476`

### 2. /opt/hermes-green/.env — BLOCKED
- **Attempted**: Copy `/opt/data/.env` to `/opt/hermes-green/.env` so `env_file: /opt/hermes-green/.env` in compose actually resolves
- **Result**: `cp: cannot create regular file '/opt/hermes-green/.env': No such file or directory`
- **Root cause**: `/opt/hermes-green/` directory does not exist on the Docker host filesystem (it's a bind-mount source that Docker creates on container start, but the host path doesn't exist)
- **Fix needed**: Create `/opt/hermes-green/` directory on host, copy `.env` there, then recreate hermes-green

## Remaining Exposure

| Finding | Severity | Status | Fix needed |
|---------|----------|--------|------------|
| Secrets in `docker inspect` | HIGH | Open | Create `/opt/hermes-green/` on host, place `.env` there, recreate hermes-green |
| `API_SERVER_KEY=hermes-api-key-123` | MEDIUM | Open | Rotate to strong random token, update all 4 `.env` files |
| GPG_KEY in 3 containers | LOW | Open | Image build issue — needs separate Dockerfile fix |
| Dashboard session token | LOW | Not found in current build | Verify on next dashboard deploy |
| No centralized secret management | MEDIUM | Open | Long-term: Docker secrets or vault |

## Trading Safety
- **dry_run status**: All bots `dry_run=true` ✅
- **Freqtrade config changed**: **NONE** ✅
- **Canary touched**: **NO** ✅
- **Docker socket**: Still absent from hermes-green ✅

## Rollback
- **`.gitignore`**: `git checkout main -- .gitignore` or revert commit
- **orchestrator.env**: Already untracked, just remove from `.gitignore` to expose again

## Next Steps for Full #476 Closure
1. On host: `mkdir -p /opt/hermes-green && cp /opt/data/.env /opt/hermes-green/.env && chmod 600 /opt/hermes-green/.env`
2. Recreate hermes-green (from host, not from inside container!)
3. Verify: `docker inspect hermes-green` shows no high-value secrets
4. Rotate `API_SERVER_KEY` to strong random value
5. Update all 4 `.env` files with new key
