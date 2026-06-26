# Hermes / Trading Hub Cron & Scheduler Audit

## Verdict
YELLOW

## Executive Summary

SI-v2 automation **is installed and executing** via the Hermes orchestrator internal cron scheduler (58 jobs, 44 enabled), not via user/root crontab. The `si-v2-active-cycle (6h, log-only)` job last ran successfully at **2026-06-24T12:17:57Z**, producing **GREEN 4-bot evidence** with **4 ShadowProposals** and **zero mutations**. The user crontab is frozen since 2026-06-11 with no active trading jobs.

However, operational trust is **incomplete**: the host-side `jobs.json` mirror is severely stale (12 jobs, no SI-v2 entry vs 58 live jobs in container), the Guardian emits false `CONTAINER_DOWN` alerts every 5 minutes due to a container name mismatch, one enabled job (`Fleet correlation refresh`) is failing, and the SI-v2 cron wrapper script exists only in runtime (`/opt/data/profiles/orchestrator/scripts/`) but not in the git repo.

## Safety Scope

**Inspected (read-only):**
- Git repo state at `/home/hermes/projects/trading`
- User/root/system crontabs, `/etc/cron.*`
- systemd timers and unit files
- Docker containers (`hermes-green`, `trading-guardian`, freqtrade fleet)
- Live Hermes orchestrator `jobs.json` (container)
- Host `jobs.json` mirror
- Guardian logs, SI-v2 cycle logs, evidence artifacts
- Git history for scheduler provenance

**Not mutated:**
- No crontab edits, no timer enable/disable, no restarts, no apply tokens, no `dry_run=false`, no manual SI-v2 cycle execution

## Repo State

| Check | Value |
|-------|-------|
| Path | `/home/hermes/projects/trading` |
| Branch | `main` |
| HEAD | `0cf5a4d30a8dc2a3d11e942b2f573e142d3acd71` |
| origin/main | `0cf5a4d30a8dc2a3d11e942b2f573e142d3acd71` |
| HEAD == origin/main | Yes |
| Worktree | No tracked modifications; many untracked docs/reports/context files |

## Scheduler Inventory

### Scheduler source classification

| Source | Status | SI-v2 relevance | Job count |
|--------|--------|-------------------|-----------|
| Hermes orchestrator internal cron | **Running** (PID 158, since 2026-06-22) | **Primary** — hosts `si-v2-active-cycle` | 58 (44 enabled) |
| User crontab (`hermes`) | **Frozen** (since 2026-06-11) | None — permission autopilot commented out | 0 active |
| Root crontab | Running | None — VPS backup only | 4 |
| `/etc/cron.d` | Running | None — qdrant-backup, sysstat | 2 |
| systemd timers (`trading-cron-guardian.timer`) | **Disabled** | Superseded by Docker guardian container | 0 active |
| Docker `trading-guardian` | **Running** (5-min loop) | Support — signal freshness, container health | 1 watchdog loop |
| GitHub Actions | CI only | Not runtime scheduler | 3 workflows |
| Python APScheduler / repo schedulers | Not deployed at runtime | Design/tooling only (`cron_planner.py`) | 0 |

### Primary SI-v2 job

| Field | Value |
|-------|-------|
| Job ID | `64866012641a` |
| Name | `si-v2-active-cycle (6h, log-only)` |
| Scheduler type | Hermes internal cron |
| Owner | `hermes` (orchestrator gateway) |
| Source | `/opt/data/profiles/orchestrator/cron/jobs.json` (live, in container) |
| Schedule | `17 */6 * * *` |
| Command | `si_v2_active_cycle_cron.sh` → `/opt/data/scripts/si-v2-active-cycle-runner.sh` |
| Workdir | `/home/hermes/projects/trading` |
| Mode | `no_agent: true`, `deliver: local` |
| Log target | `/opt/data/logs/si-v2-active-cycle/cron.log` + per-cycle logs |
| Locking | Hermes scheduler single-flight per job ID |
| Fleet coverage | **4/4** (explicit bot env vars) |
| Risk | **GREEN** |
| Last run | `2026-06-24T12:17:57Z` — `ok` |
| Next run | `2026-06-24T18:17:00Z` |

### SI-v2 support chain jobs (enabled, recent `ok`)

| Job | Schedule | Last run (UTC) | Fleet role |
|-----|----------|----------------|------------|
| `trading-pipeline` | `*/10 * * * *` | 2026-06-24T16:41:16Z | Signal → fleet gates |
| `unified-signal-heartbeat` | `*/20 * * * *` | 2026-06-24T16:31:44Z | Canonical signal freshness |
| `Heartbeat Intelligence Report` | every 360m | 2026-06-24T12:00:55Z | 4-bot intelligence |
| `Fleet Report (alle 6h)` | every 360m | 2026-06-24T13:54:01Z | Fleet audit (agent) |
| `drawdown-guard` | `*/5 * * * *` | 2026-06-24T16:31:19Z | Portfolio risk |
| `riskguard-service` | `*/5 * * * *` | 2026-06-24T16:31:20Z | Signal integrity |
| `container-watchdog` | `*/5 * * * *` | 2026-06-24T16:31:19Z | Bot container health |
| `fleet-auto-repair` | `*/5 * * * *` | 2026-06-24T16:04:06Z | Fleet self-heal |
| `observation-runner` | `*/30 * * * *` | 2026-06-24T16:41:21Z | Data quality |
| `ledger-integrity-watchdog` | `*/30 * * * *` | 2026-06-24T16:25:59Z | Measurement integrity |

### Legacy / disabled jobs (14)

All `si-bot-a/b/c/d-*` jobs are `enabled=false`, `state=paused`, last error `exit 127` (missing `self_improvement/bot_*` paths). Correctly superseded by SI-v2; cleanup candidate only.

### Failing enabled job (1)

| Job | Last run | Error | Risk |
|-----|----------|-------|------|
| `Fleet correlation refresh` | 2026-06-23T22:11:06Z | Script exit code 1 | **RED** |

Full 58-job machine-readable inventory: `docs/reports/hermes-cron-scheduler-audit-20260624-1844.json`

## Active SI-v2 Automation Chain

```text
Hermes orchestrator gateway (s6, PID 158)
  → si_v2_active_cycle_cron.sh (runtime script)
  → si-v2-active-cycle-runner.sh
  → active_cycle_runner.py
  → freqtrade REST adapters (4 bots, env auth)
  → fleet analyzer + ShadowProposal generation
  → evidence bundle + cycle state + telemetry history
  → local logs (/opt/data/logs/si-v2-active-cycle/)
```

| Stage | Status | Evidence |
|-------|--------|----------|
| Scheduler fires on cadence | **GREEN** | 4 scheduled cycles in 24h at ~6h intervals; logs through 2026-06-24T12:17 |
| Command/script resolves | **GREEN** | `cron.log` shows `runner_exit_code=0`, `fleet_verdict=GREEN` |
| 4-bot telemetry access | **GREEN** | `active_cycle_20260624T121756Z.json`: 4/4 AUTHENTICATED, ping OK |
| Proposal generation | **GREEN** | `shadow_proposal_count: 4`, controller `PAUSED / L3_REPOSITORY_ONLY` |
| Evidence artifacts | **GREEN** | 57 cycle evidence files since 2026-06-15 |
| Notification/log output | **GREEN** | Per-cycle logs + measurement ledger updated |
| Host audit mirror | **RED** | Host `jobs.json` missing SI-v2 job entirely |
| Guardian observability | **YELLOW** | False `CONTAINER_DOWN: ai-hedge-fund-crypto` every 5 min |
| Correlation upstream data | **RED** | `Fleet correlation refresh` failing |

## Execution Proof

### SI-v2 active cycle — last 5 cycles (24h window)

| Cycle ID | Timestamp (UTC) | Scheduled? | Fleet | Bots | Proposals | Mutations |
|----------|-----------------|------------|-------|------|-----------|-----------|
| `20260623T181740Z` | 18:17 | Yes | GREEN | 4/4 | 4 | 0 |
| `20260624T002122Z` | 00:21 | ~Yes | GREEN | 4/4 | 4 | 0 |
| `20260624T055059Z` | 05:50 | No (manual/extra) | GREEN | 4/4 | 4 | 0 |
| `20260624T061755Z` | 06:17 | Yes | GREEN | 4/4 | 4 | 0 |
| `20260624T121756Z` | 12:17 | Yes | GREEN | 4/4 | 4 | 0 |

**Latest artifact:** `self_improvement_v2/reports/phase2/evidence/active_cycle_20260624T121756Z.json` (2026-06-24 14:17 local / 12:17 UTC)

**Latest cron wrapper log excerpt (2026-06-24T12:17):**
- `fleet_verdict=GREEN`, `ping_ok=4/4`, `mutation_*=0`
- `controller=PAUSED / L3_REPOSITORY_ONLY`
- `rainbow_status=SUCCESS`, `ledger_status=SUCCESS`, `secrets_found=False`

**Cadence assessment:** No missed scheduled runs in the 24h proof window. One extra non-scheduled cycle (`055059Z`) present from manual/rerun activity — does not indicate scheduler failure.

**Staleness:** Latest scheduled evidence is ~4.5h old at audit time; next scheduled run `18:17 UTC` not yet due.

### Support pipeline

- `trading-pipeline`: last `ok` at 2026-06-24T16:41:16Z (~3 min before prior audit)
- Guardian: `OK: Signal fresh` consistently; false container-down on every cycle
- Host syslog/journal: no SI-v2 cron entries (expected — jobs run inside Hermes, not system cron)

## Fleet Coverage

**Canonical 4-bot fleet confirmed in latest evidence:**

| Bot ID | Auth | Ping | ShadowProposal |
|--------|------|------|----------------|
| `freqtrade-freqforge` | AUTHENTICATED | OK | Yes |
| `freqtrade-freqforge-canary` | AUTHENTICATED | OK | Yes |
| `freqtrade-regime-hybrid` | AUTHENTICATED | OK | Yes |
| `freqai-rebel` | AUTHENTICATED | OK | Yes |

- No 6-bot references in live scheduler config
- Momentum/MVS not present in active cycle evidence
- `total_bots: 4` in fleet_summary

## Creation Provenance

| Item | Strength | Evidence |
|------|----------|----------|
| SI-v2 active cycle job | **Strong** | Job ID `64866012641a` in live jobs.json; commits `f14b286`, `9758a75`, `c45d6c5`; P3 continuity proof report |
| Hermes orchestrator gateway | **Strong** | s6 supervision since container start 2026-06-22; `hermes -p orchestrator gateway run` |
| Guardian watchdog | **Strong** | `trading-guardian` container; git `cron-recovery-v2-external-guardian-20260519` |
| User crontab SI automation | **Missing** | Frozen 2026-06-11; never held SI-v2 job |
| Host jobs.json | **Weak/stale** | 12 jobs from 2026-06-13; no SI-v2 entry; container diverged to 58 jobs |
| `si_v2_active_cycle_cron.sh` in repo | **Missing** | Exists at runtime in container only; not tracked in git |

## Broken / Stale / Risky Items

| Priority | Item | Status | Impact |
|----------|------|--------|--------|
| P1 | Host `jobs.json` stale (12 vs 58 jobs) | Stale | Audits from host path falsely imply SI-v2 scheduler missing |
| P1 | Guardian container name `ai-hedge-fund-crypto` | Bug | False `CONTAINER_DOWN` every 5 min; obscures real failures |
| P2 | `Fleet correlation refresh` failing | Error | Correlation data stale since 2026-06-23 |
| P2 | `si_v2_active_cycle_cron.sh` not in git | Drift | Rebuild/redeploy risk; repo ≠ runtime |
| P3 | `trading-cron-guardian.timer` disabled | Mitigated | Docker guardian covers; host systemd path inactive |
| P3 | Legacy SI-v1 jobs in error state | Benign | Disabled; noise in job inventory |
| P3 | Extra manual cycle `055059Z` in 24h | Informational | Not a scheduler gap |

## Failure Tree

1. **State/report location drift** — Host jobs.json not synced with live orchestrator state → audit false negatives
2. **Job depends on wrong container name** — Guardian references `ai-hedge-fund-crypto`; actual `trading-ai-hedge-fund-1` → perpetual false alerts
3. **Script exits nonzero** — `fleet_correlation_refresh.sh` exit 1 → stale correlation inputs
4. **Git/runtime divergence** — Cron wrapper in container only, absent from repo → recovery fragility
5. **Scheduler not in user crontab** — By design; Hermes internal scheduler is the actual runtime path (not a failure)
6. **Success = job ran vs valid evidence** — For SI-v2, evidence is valid: latest cycle proves 4-bot GREEN bundle

## Final Verdict

**YELLOW** — Core SI-v2 automation is installed, scheduled, executing, and producing current valid 4-bot evidence with ShadowProposals and zero mutations. The self-improvement loop is **operationally alive**. Trust is reduced by stale host-side scheduler mirrors, Guardian false-positive noise, one failing correlation job, and runtime-only script drift not reflected in the repository.

Not RED because: scheduled 6h cycles run reliably, artifacts are fresh within cadence, and full fleet coverage is proven.

Not GREEN because: host audit surface is misleading, observability has systematic false alarms, and one enabled job is failing.

## Single Next Repair Step

**Fix Guardian container name references** in `orchestrator/guardian/scripts/external_cron_guardian.sh`:

- Replace `ai-hedge-fund-crypto` with `trading-ai-hedge-fund-1` in `CRITICAL_CONTAINERS` and all `docker exec` heartbeat paths
- Rebuild/restart `trading-guardian` container after merge
- Acceptance: Guardian log shows zero `CONTAINER_DOWN: ai-hedge-fund-crypto` / `CONTAINER_RESTART_FAILED` entries over 30 minutes while `trading-ai-hedge-fund-1` remains Up

Requires L2 ops approval for container redeploy. No SI-v2 apply token needed.

## Suggested Backlog Issues

### P1: Sync host jobs.json mirror with live orchestrator state
- **Goal:** Host `/opt/data/profiles/orchestrator/cron/jobs.json` reflects live 58-job state including SI-v2 entry
- **AC:** Host file job count = container job count; SI-v2 job visible from host path
- **Effort:** S
- **Dependencies:** None
- **Relation:** Operability — scheduler audit trust

### P1: Repair Fleet correlation refresh job
- **Goal:** `fleet_correlation_refresh.sh` runs successfully on schedule
- **AC:** `last_status=ok`; correlation output file timestamp < 72h
- **Effort:** M
- **Dependencies:** Log/root-cause from `fleet_correlation_refresh.sh` stderr
- **Relation:** SI-v2 upstream signal quality

### P2: Commit runtime SI-v2 cron scripts to repository
- **Goal:** `si_v2_active_cycle_cron.sh` and runner wrapper tracked in git under `orchestrator/scripts/`
- **AC:** Repo script hash matches runtime; deploy contract documented
- **Effort:** S
- **Dependencies:** None
- **Relation:** SI-v2 loop maintainability

### P3: Cleanup legacy SI-v1 cron job entries
- **Goal:** Remove or archive 14 disabled `si-bot-*` jobs from jobs.json
- **AC:** jobs.json contains only active/relevant jobs; no error-state noise
- **Effort:** S
- **Dependencies:** L2 approval for jobs.json mutation
- **Relation:** Operability