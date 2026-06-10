# Controlled Dry-run Rehearsal Runbook

> **SI v2 — Controlled Dry-run Rehearsal Procedure**
>
> This runbook describes the procedure for executing a controlled
> dry-run rehearsal of the SI v2 pipeline against the live Freqtrade
> fleet in **read-only / dry-run mode only**.
>
> **Live trading, `dry_run=false`, real orders, and real exchange
> credentials remain strictly prohibited.**

---

## 1. Prerequisites

Before starting the rehearsal, all of the following must be true:

- [ ] PR #133 is merged (offline episode layer complete)
- [ ] CI smoke workflow (#120) is passing on `main`
- [ ] Failure taxonomy (#121) is loaded and available
- [ ] Human approval gate checklist (#122) is signed
- [ ] Progress dashboard (#123) shows GREEN offline readiness
- [ ] Live-readiness blocker inventory (#124) is reviewed
- [ ] Phase 1 readiness verdict is GREEN or YELLOW
- [ ] Quality gate verdict is GREEN
- [ ] All pipeline tests pass
- [ ] **Human approval token obtained:** `APPROVE_PHASE_M_REHEARSAL_<YYMMDD>`

If any prerequisite is not met, **stop** and resolve before proceeding.

## 2. Allowed Commands (High-Level)

The rehearsal agent may execute the following categories of commands,
each governed by an explicit step below:

| Category | Examples | Allowed? |
|----------|----------|----------|
| Read-only Docker | `docker ps`, `docker inspect`, `docker logs --tail 50` | ✅ Step 2.1 |
| Read-only config | `docker exec <bot> cat config.json` (redacted) | ✅ Step 2.2 |
| Bot status | `GET /api/v1/ping`, `GET /api/v1/status` | ✅ Step 2.3 |
| Signal file read | `cat` on signal bridge output | ✅ Step 2.4 |
| RiskGuard check | `cat` on RiskGuard decision output | ✅ Step 2.5 |
| Test execution | `pytest` on SI v2 test suite | ✅ Any time |
| Episode run | `python run_offline_episode.py` | ✅ Step 4 |

## 3. Forbidden Actions

The rehearsal agent must **never**:

- ❌ Set `dry_run=false` or modify any Freqtrade config's `dry_run` field
- ❌ Place real orders via any exchange API
- ❌ Read, print, copy, or persist exchange API keys, Telegram tokens, or secrets
- ❌ Call Freqtrade `/api/v1/forcebuy`, `/api/v1/forcesell`, or any mutating endpoint
- ❌ Call Telegram `sendMessage` or any Telegram API
- ❌ Restart, stop, start, recreate, or rebuild Docker containers
- ❌ Modify Freqtrade strategy files
- ❌ Modify cron jobs or scheduler state
- ❌ Write to production ShadowLogger or production databases
- ❌ Use `os.environ` or `os.getenv` to read secrets
- ❌ Execute any command not explicitly listed in the allowed set

## 4. Rehearsal Steps

### Step 1: Preflight Verification

```bash
# 1. Confirm main HEAD
git log --oneline -3

# 2. Confirm all bots are in dry-run
docker ps --format 'table {{.Names}}\t{{.Status}}'

# 3. Run SI v2 pipeline tests
pytest self_improvement_v2/tests -k "rainbow or evidence or regime or attribution or quality or manifest or readiness or episode"

# 4. Run offline episode
python self_improvement_v2/run_offline_episode.py

# 5. Check quality gate
python -c "from si_v2.cli.offline_quality_gate import OfflineQualityGate; print(OfflineQualityGate().run().verdict.value)"
```

### Step 2: Read-Only Fleet Inspection

```bash
# 2.1 Container health
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

# 2.2 Dry-run confirmation (redacted)
# For each bot, confirm dry_run=true in config output (API only, no env dump)
# Use read-only HTTP endpoint if available

# 2.3 Bot ping
curl -fsS --max-time 5 http://<bot-container>:8080/api/v1/ping

# 2.4 Signal bridge status
cat /path/to/signal_bridge_output.json   # if exists and readable

# 2.5 RiskGuard status
cat /path/to/riskguard_output.json       # if exists and readable
```

### Step 3: Evidence Capture

For each step, capture:

- Command output (stdout + stderr)
- Timestamp
- Exit code
- Any warning or error messages

Store captured evidence in `self_improvement_v2/reports/rehearsal/<run-timestamp>/`.

### Step 4: Episode Execution

```bash
python self_improvement_v2/run_offline_episode.py > episode_result.json
cat episode_result.json | python -m json.tool
```

### Step 5: Report Generation

```bash
# Generate episode report
python -c "
from si_v2.episode.offline_episode_report import OfflineEpisodeReportRenderer
r = OfflineEpisodeReportRenderer()
with open('reports/rehearsal/<run-timestamp>/episode_report.md', 'w') as f:
    f.write(r.render())
"
```

## 5. Stop Conditions

The rehearsal must **stop immediately** if any of the following occurs:

| Condition | Action |
|-----------|--------|
| `dry_run=false` detected in any bot config | ⛔ ABORT — report RED |
| Real exchange API keys or secrets exposed | ⛔ ABORT — report RED |
| Telegram token found or Telegram API called | ⛔ ABORT — report RED |
| Docker container stops, crashes, or restarts unexpectedly | ⚠️ PAUSE — investigate |
| Any mutation command executed accidentally | ⛔ ABORT — report RED |
| Pipeline tests fail | ⚠️ PAUSE — investigate |
| Episode returns RED verdict | ⚠️ PAUSE — investigate |
| Network connectivity loss to any bot | ⚠️ PAUSE — investigate |

## 6. Rollback Procedure

If the rehearsal reveals an issue:

1. **Stop** all commands immediately
2. **Document** the issue with evidence (command, output, timestamp)
3. **Reset** to known-good state:
   ```bash
   git checkout main
   git pull --ff-only
   ```
4. **Report** to the repository owner
5. **Do not** restart the rehearsal until the issue is resolved

## 7. Approval Token

> **This runbook requires explicit human approval before execution.**
>
> Approval token format: `APPROVE_PHASE_M_REHEARSAL_<YYMMDD>`
>
> Example: `APPROVE_PHASE_M_REHEARSAL_240610`
>
> Without this token, the rehearsal agent must refuse to proceed.

## 8. Safety Confirmation

> **I confirm:**
> - No live trading is authorized
> - No `dry_run=false` will be set
> - No real orders will be placed
> - No exchange credentials, Telegram tokens, or secrets will be read
> - This rehearsal is read-only / dry-run / observational only
> - All captured evidence will be redacted for secrets before storage
>
> Name: ________________________________
> Date: ________________________________

---

*Runbook maintained at `self_improvement_v2/runbooks/controlled_dry_run_rehearsal.md`*
*Created as part of #125 — Controlled Dry-run Rehearsal Runbook*
