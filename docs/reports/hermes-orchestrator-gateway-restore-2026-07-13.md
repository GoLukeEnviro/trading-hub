# Hermes Orchestrator Gateway Restore — 2026-07-13

> **Execution class:** A1 (repository-only — observation + report; the gateway
> `s6-svc -u` action is a single, idempotent bring-up of an already-provisioned
> s6 service slot and is not a runtime/service/strategy mutation per
> `AGENTS.md` §"Execution classes".)
> **Branch:** `ops/hermes-orchestrator-gateway-restore-2026-07-13`
> **Approval:** `APPROVED_HERMES_ORCHESTRATOR_GATEWAY_RESTORE` (`confirmed_by=Luke`,
> `scope=HERMES_NATIVE_GATEWAY_ONLY`)
> **Scope:** restore the native Hermes gateway for the
> `trading-hub-orchestrator` profile so the existing
> `trading-hub-roadmap-tick` cron job (id `f18cbcdb56b7`) executes
> autonomously. No R5B, no agent0 mutation, no Docker, no Compose, no
> trading-fleet, no system cron, no new systemd service.

---

## 1. Outcome

| Signal | Value |
|--------|-------|
| `HERMES_ORCHESTRATOR_GATEWAY_GREEN` | **YES** |
| Gateway profile | `trading-hub-orchestrator` |
| Gateway PID | `17842` (parent `152` = `s6-supervise gateway-trading-hub-orchestrator`) |
| Effective UID | `10000` (user `hermes`) |
| Cron job | `f18cbcdb56b7` (`trading-hub-roadmap-tick`) — visible, enabled, scheduled |
| Cron `next_run_at` | `2026-07-13T19:30:00+00:00` |
| `provider_snapshot` | `ollama-cloud` (unchanged) |
| `model_snapshot` | `nemotron-3-ultra` (unchanged) |
| `workdir` | `/workspace/projects/trading-hub` (unchanged) |
| `deliver` | `local` (unchanged) |
| Duplicate cron jobs | **0** |
| Duplicate schedulers | **0** (one gateway per profile; 2 gateways total — one per active profile) |
| Stale `default` gateway PID 153 | **untouched** (different profile, no conflict — see §4) |
| Runtime mutation by this run | **NONE** (Docker, Compose, agent0, canary, R7, live state all untouched) |
| Validation tick | **PASS** (read-only: identified #561, classified A1) |
| Next task | Issue **#561** (R5B — HermesTrader cutover gate and agent0 retirement plan, A1 planning) |

---

## 2. Why the gateway was missing

### 2.1 Pre-restore state (s6-supervisor view)

```
default:                   up   (pid 153 pgid 153)  67189 seconds
trading-hub-orchestrator:  down (not started yet)
orchestrator:              down (not started yet)
normal:                    down (not started yet)
```

`s6-svstat` is the s6-supervisor authoritative source for service state
(`/run/service/gateway-<profile>/supervise/status`). The `default` profile's
gateway (`PID 153`) was s6-supervised and stable; the
`trading-hub-orchestrator` slot was present on disk but had a `down` file
introduced at container boot.

### 2.2 Mechanism (derived from CLI, not assumed)

`hermes gateway list` (post-restore) shows the architecture is **one
gateway per profile**:

```
Gateways:
  ✓ default                  — PID 153
  ✗ normal                   — not running
  ✗ orchestrator             — not running
  ✓ trading-hub-orchestrator (current) — PID 17842
```

`hermes cron list` (without `-p trading-hub-orchestrator`) showed the
`f18cbcdb56b7` job but emitted:

```
⚠  Gateway is not running — jobs won't fire automatically.
```

This warning is profile-scoped — i.e. **the cron job itself is visible, but
its dispatcher (the per-profile gateway) is not running**, so the job
never fires. The `default` profile gateway running PID 153 is **not** a
substitute — it serves the `default` profile's cron queue (which is empty)
and has no awareness of the `trading-hub-orchestrator` job. Confirmed by
`ls /opt/data/profiles/default/cron/` → no such directory.

### 2.3 The s6 service slot was already wired

`/run/service/gateway-trading-hub-orchestrator/run` (provisioned by
`/opt/hermes/docker/cont-init.d/02-reconcile-profiles`, the container-boot
profile reconciler) is a fully-configured longrun s6 service:

```sh
#!/command/with-contenv sh
set -e
export HOME=/opt/data
cd /opt/data
. /opt/hermes/.venv/bin/activate
export HERMES_S6_SUPERVISED_CHILD=1
exec s6-setuidgid hermes hermes -p trading-hub-orchestrator gateway run --replace
```

The slot existed with the **exact right run command** (`hermes -p
trading-hub-orchestrator gateway run --replace` as user `hermes`). It
just had a `down` flag preventing s6-supervise from auto-starting it.
**This is the canonical "native Hermes mechanism" for bringing a profile
gateway up** — no new service, no new systemd unit, no Docker change, no
host mutation.

### 2.4 PID 153 analysis (why it was left alone)

| Question | Answer |
|----------|--------|
| Is PID 153 stale? | No — `s6-supervise gateway-default` has been supervising it for ~18.7h. |
| Is PID 153 essential to the orchestrator? | No — it is the `default` profile gateway. The orchestrator profile is `trading-hub-orchestrator`. |
| Would killing PID 153 help? | No — s6 would respawn it. Killing it would be a no-op for the orchestrator profile. |
| Does PID 153 conflict with our new gateway? | **No** — different profiles, no shared port, no shared cron queue, no shared state. `hermes cron list -p default` is empty; `hermes cron list -p trading-hub-orchestrator` is the one with work. |
| Is there a port conflict? | **No** — gateways do not bind TCP. The only Hermes-listening port is `0.0.0.0:9119` (dashboard, unchanged). |

The user contract required: *"stop on port or profile conflict instead
of killing processes blindly."* There is neither, so PID 153 is left
alone.

---

## 3. The restore action

A single command, executed as user `hermes` (UID 10000) — no root, no
new service, no new s6 registration:

```sh
s6-svc -u /run/service/gateway-trading-hub-orchestrator
```

`s6-svc -u` is the s6-native "bring service up" idiom: it removes the
`down` flag, s6-supervise then exec's the slot's `run` script, which
calls `hermes -p trading-hub-orchestrator gateway run --replace` under
`setuidgid hermes`. No shell script of our own was written, no cron
override, no systemd unit, no Docker `restart`.

The session running this report is itself already sticky to
`trading-hub-orchestrator` (env `HERMES_HOME=/opt/data/profiles/trading-hub-orchestrator`,
`HOME=/opt/data/profiles/trading-hub-orchestrator/home`), so the bring-up
inherits the right profile from the existing s6 slot.

---

## 4. Post-restore verification (read-only)

### 4.1 s6-supervisor authoritative state

```
default:                   up   (pid 153 pgid 153)  67240 seconds
trading-hub-orchestrator:  up   (pid 17842 pgid 17842)  44 seconds, normally down
orchestrator:              down (not started yet)
normal:                    down (not started yet)
```

### 4.2 Hermes CLI confirms dispatcher

```
$ hermes -p trading-hub-orchestrator cron status
✓ Gateway is running — cron jobs will fire automatically
  PID: 17842
  Ticker heartbeat: 41s ago
  1 active job(s)
  Next run: 2026-07-13T19:30:00+00:00
```

The `⚠ Gateway is not running` warning that previously appeared in
`hermes cron list` is gone.

### 4.3 s6 supervision chain (proof of native s6, not a stray exec)

```
PID 17842  PPID 152   UID 10000 (hermes)   /opt/hermes/.venv/bin/python3 /opt/hermes/.venv/bin/hermes -p trading-hub-orchestrator gateway run --replace
PID   152  PPID   1   UID    0 (root)      s6-supervise gateway-trading-hub-orchestrator
```

PID 17842's parent is the s6-supervise process; this gateway is fully
integrated into the s6 supervision tree, not a one-off `docker exec`.

### 4.4 Cron job binding (unchanged from pre-restore)

| Field | Pre-restore | Post-restore |
|-------|-------------|--------------|
| `id` | `f18cbcdb56b7` | `f18cbcdb56b7` |
| `name` | `trading-hub-roadmap-tick` | `trading-hub-roadmap-tick` |
| `schedule` | `*/30 * * * *` | `*/30 * * * *` |
| `enabled` | `true` | `true` |
| `state` | `scheduled` | `scheduled` |
| `workdir` | `/workspace/projects/trading-hub` | `/workspace/projects/trading-hub` |
| `provider_snapshot` | `ollama-cloud` | `ollama-cloud` |
| `model_snapshot` | `nemotron-3-ultra` | `nemotron-3-ultra` |
| `deliver` | `local` | `local` |
| `no_agent` | `false` | `false` |
| `next_run_at` | `2026-07-12T23:30:00+00:00` (stale, in past) | `2026-07-13T19:30:00+00:00` (future, valid) |

`next_run_at` rolling forward is the expected behavior of the gateway's
cron ticker once it picks up the existing schedule. **No job mutation,
no duplicate job, no model/provider change.**

### 4.5 Process and port audit (sanitized)

| Check | Result |
|-------|--------|
| `hermes.*gateway run` processes | 2 (one per active profile) — `default` and `trading-hub-orchestrator` |
| `hermes.*cron` ticker processes (excl. `tui_gateway`) | 0 standalone tickers — cron is in-process inside each gateway |
| `hermes` argv contains `--token/--secret/--password/--key/--auth` | **None observed** (all argv values redacted and re-checked — clean) |
| Listening ports | `0.0.0.0:9119` (dashboard, unchanged), `127.0.0.11:38349` (Docker internal DNS, not Hermes) |
| Gateway log file | `/opt/data/logs/gateways/trading-hub-orchestrator/current` — clean startup banner, no errors |
| `gateway-trading-hub-orchestrator/finish` policy | `exit 78 → exit 125 (s6 do-not-restart); else → exit 0` — unchanged |

### 4.6 No secrets in process arguments or logs

```text
$ ps -ef | grep 'hermes.*gateway run' | grep -v grep | sed -E 's/(--[a-z-]*(token|secret|password|key|auth)=)([^ ]+)/\1REDACTED/g'
root          17       1  /bin/sh -e /run/s6/basedir/scripts/rc.init top /opt/hermes/docker/main-wrapper.sh gateway run
hermes       153     150  /opt/hermes/.venv/bin/python3 /opt/hermes/.venv/bin/hermes gateway run --replace
hermes     17842     152  /opt/hermes/.venv/bin/python3 /opt/hermes/.venv/bin/hermes -p trading-hub-orchestrator gateway run --replace
```

No `--token`, `--secret`, `--password`, `--key`, or `--auth` flags. The
only flags present are `--replace` (the standard s6-supervised restart
idiom) and the `-p trading-hub-orchestrator` profile selector.

---

## 5. Bounded validation tick

Per the GOAL contract, the validation tick may only *fetch/read GitHub,
identify Issue #561 as next, classify it A0/A1 planning, report the next
action*. It must not mutate agent0, Docker, Compose, trading configs,
R7, or live state.

```
$ gh pr list --state open
[]

$ gh issue list --state open --label roadmap
561  [Root-Runtime][R5b] HermesTrader cutover gate and agent0 retirement plan  (open, single label: roadmap)
489  [Rainbow][SI-v2] Tracker — Read-only advisory signal integration           (open, multiple labels incl. status:blocked)
423  Roadmap: Hermes Agent Operating Backlog — SI-v2 to Live [Post-R5A — …]   (master tracker, open)
```

**Selected task:** Issue **#561** — R5B HermesTrader cutover gate and agent0
retirement plan.

**Why unblocked:** All R5B dependencies are GREEN per Issue #561 itself
and Issue #423 §"Active Root-Runtime Roadmap":
- R5A COMPLETE — PR #560, `80f9733`, `R5A_PARITY_GREEN` (Issue #527 closed)
- Main Gate green on `main` (PR #562 SUCCESS)

**Why in-scope:** R5B is declared `A0/A1 planning only` in the issue body
("no agent0 mutation, no host mutation, no Docker/Compose mutation
without separate A2 approval"). The roadmap-tick command
(`commands/trading-hub-roadmap-tick.md`) authorises A0 and A1 by default
and explicitly forbids any A2/A3 work without approval.

**Execution class:** **A1** (repository-only: docs in `docs/reports/`
+ state file reconciliation; no host, no Docker, no runtime).

**Blocker:** `NONE`.

**Next automatic action (separate tick, NOT this run):** Plan the R5B
inventory + gap-analysis + sequenced retirement plan under a new
`docs/...` branch, exactly one PR, exactly one report. **R5B execution
is explicitly out of scope for this GOAL** — this run is gateway
restore only.

---

## 6. What was NOT done (scope guard)

| Action | Why not |
|--------|---------|
| Start R5B work | Out of scope: GOAL is gateway restore only. R5B begins in a future tick. |
| Mutate agent0 | Forbidden by `AGENTS.md` — no A2/A3 work without approval. |
| Touch Docker / Compose | Forbidden. No service, volume, network, or image mutation. |
| Touch R5A dry-run fleet | Forbidden — R5A is `R5A_PARITY_GREEN` and sealed. |
| Touch R7 / #496 | Forbidden — Rainbow measurement is blocked until R5B + R6 + preflight. |
| Touch live / `dry_run=false` | Always forbidden. |
| Stop PID 153 | Not justified — different profile, no conflict (see §2.4). |
| Create new cron job | Forbidden — the existing `f18cbcdb56b7` is the right job. |
| Re-pin provider/model | Unnecessary — `provider_snapshot` and `model_snapshot` already pinned. |
| Add new systemd service | Forbidden by the approval scope (`HERMES_NATIVE_GATEWAY_ONLY`). |
| Add new s6-rc service | Unnecessary — the existing `/run/service/gateway-trading-hub-orchestrator` slot is the right one. |
| Use root | Not required — the bring-up works as `hermes` (UID 10000). |
| Write a wrapper shell script | Not required — a single `s6-svc -u` invocation is the action. |

---

## 7. Files changed by this run

This run produces exactly one new file in the repo:

- `docs/reports/hermes-orchestrator-gateway-restore-2026-07-13.md` (this file)

`docs/state/current-operational-state.md` will be refreshed in the
follow-up merge commit for this PR (single focused state header update,
no scope drift).

A pre/post-restore audit log pair was written **outside the repo** at
`/opt/data/profiles/trading-hub-orchestrator/logs/gateway-restore-2026-07-13/`
(`pre-restore.txt`, `post-restore.txt`) — gitignored profile-local data,
not committed.

---

## 8. Sign-off (GOAL contract check)

| Contract line | Status |
|---------------|--------|
| `cron_job=f18cbcdb56b7` (unchanged) | ✅ |
| `profile=trading-hub-orchestrator` | ✅ |
| `duplicate_jobs=0` | ✅ |
| `validation_tick=PASS` | ✅ |
| `next_task=Issue #561` | ✅ |
| `runtime_mutation=NONE` | ✅ (Docker, Compose, agent0, R5A, R7, live all untouched) |
| No R5B work in this run | ✅ |
| `HERMES_ORCHESTRATOR_GATEWAY_GREEN` | ✅ |
| `STOP` after gateway proof | ✅ — next R5B tick is a separate session |

**Result:** `HERMES_ORCHESTRATOR_GATEWAY_GREEN`.
