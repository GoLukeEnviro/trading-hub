# Guardian container-name false positive fix

**Date (UTC):** 2026-06-25T10:35:00Z  •  **Operation Level:** L2  •  **Author:** Grok (Claudio session)

## Verdict

- **Guardian observability: GREEN** — false `CONTAINER_DOWN: ai-hedge-fund-crypto` noise eliminated.
- **Scheduler/restore safety:** unchanged GREEN (#344 + #346).

## Problem

`trading-guardian` baked script checked/restarted container `ai-hedge-fund-crypto`, which does not exist.
The real signal container is `trading-ai-hedge-fund-1` (compose service `ai-hedge-fund`).

Before fix: **2393** log lines with `CONTAINER_DOWN: ai-hedge-fund-crypto` (every 5 min).

## Change

| File | Change |
|---|---|
| `orchestrator/guardian/scripts/external_cron_guardian.sh` | Add `AI_HEDGE_CONTAINER="trading-ai-hedge-fund-1"`; use for `docker exec` + `CRITICAL_CONTAINERS` + related log strings only |

**Hard constraint respected:** `SIGNAL_FILE="$WORKDIR/ai-hedge-fund-crypto/output/hermes_signal.json"` unchanged (repo dir path, not container name).

## Deploy

```bash
cd orchestrator/guardian
docker image tag guardian-trading-guardian:latest guardian-trading-guardian:pre-container-name-fix
docker compose build trading-guardian
docker compose up -d --no-deps trading-guardian
```

Only `trading-guardian` recreated. No `hermes-green`/Freqtrade restart. No broad `compose up -d`.

## Validation (9 points)

| # | Check | Result |
|---|-------|--------|
| 1 | No new `CONTAINER_DOWN: ai-hedge-fund-crypto` after redeploy | **GREEN** — last false positive `2026-06-25T10:31:05Z`; post-redeploy cycles show `OK: All checks passed` |
| 2 | Baked script uses `trading-ai-hedge-fund-1` in docker exec / CRITICAL_CONTAINERS | **GREEN** — `AI_HEDGE_CONTAINER` in `/guardian/entrypoint/external_cron_guardian.sh` |
| 3 | `SIGNAL_FILE` still `ai-hedge-fund-crypto/output/hermes_signal.json` | **GREEN** — line 18 unchanged |
| 4 | `trading-ai-hedge-fund-1` running/healthy | **GREEN** — `status=running health=healthy` |
| 5 | `/guardian/cron/jobs.json` 58 jobs + `64866012641a` | **GREEN** |
| 6 | `/guardian/cron` mount read-only | **GREEN** — `mode=ro`, source `/opt/hermes-green/config/profiles/orchestrator/cron` |
| 7 | Only `trading-guardian` container ID changed | **GREEN** — `4f80c27e19ac` → `45725333e8ff` |
| 8 | `hermes-green` + 4 Freqtrade IDs unchanged | **GREEN** — `e08bb99fe7f8`, `129f95a97ca8`, `f3f8488b2c92`, `042c7276ef3d`, `fcc20f400092` |
| 9 | Repo/baked SHA identical | **GREEN** — `fbc297b3262f7847114dd3e457c8ad23ac2c978a9d94bf5b6a1997ccc1b73148` |

## Log evidence

**Before (last false positives):**
```
[2026-06-25T10:26:04Z] CONTAINER_DOWN: ai-hedge-fund-crypto — attempting docker start
[2026-06-25T10:26:04Z] CONTAINER_RESTART_FAILED: ai-hedge-fund-crypto
[2026-06-25T10:31:05Z] CONTAINER_DOWN: ai-hedge-fund-crypto — attempting docker start
[2026-06-25T10:31:05Z] CONTAINER_RESTART_FAILED: ai-hedge-fund-crypto
```

**After (first cycles post-redeploy):**
```
[2026-06-25T10:34:02Z] OK: All checks passed (jobs healthy, signal fresh, scripts present, permissions clean)
[2026-06-25T10:34:06Z] OK: Signal fresh (2.8min < 30min)
[2026-06-25T10:34:06Z] OK: All checks passed (jobs healthy, signal fresh, scripts present, permissions clean)
```

## Rollback

```bash
docker tag guardian-trading-guardian:pre-container-name-fix guardian-trading-guardian:latest
cd orchestrator/guardian && docker compose up -d --no-deps trading-guardian
```

## Out of scope

- Legacy `orchestrator/scripts/external_cron_guardian.sh`
- SI-v2 schedule, restore scripts, strategy/config mutation
- Stale host orphan dirs cleanup