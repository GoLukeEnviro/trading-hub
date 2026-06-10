# Read-Only Observation Plan

> **SI v2 — Read-Only Observation Plan for Future Rehearsal**
>
> This plan defines what may be observed and reported during a rehearsal
> without requiring service calls, Docker commands, or runtime activation.
>
> **This is a plan for future observation.**
> No observation or data collection takes place during planning.
> All observations are read-only and must not modify any system state.

---

## 1. Purpose

The observation plan ensures that:

- Future rehearsals can observe system state without side effects.
- All observation sources are categorised by access method and risk.
- Write-capable adapters are disabled by default.
- No automatic action is taken based on observations.
- The plan is pre-approved for use during a rehearsal.

---

## 2. Observation Sources

### 2.1 Read-Only Sources (Safe, Always Enabled)

| Source | Description | Access Method | Write-Capable | Default State |
|--------|-------------|---------------|---------------|---------------|
| Filesystem (read-only paths) | Static config files, report files, log files | `open()` read-only | No | Enabled |
| Signal output file | `ai-hedge-fund-crypto/output/hermes_signal.json` | File read (no parse/validate) | No | Enabled |
| Dry-run bot SQLite DB | `tradesv3.*.dryrun.sqlite` | Read-only SQLite query | No | Enabled |
| Health check endpoints | `/health` on Freqtrade REST API ports | `requests.get()` read-only | No | Enabled |
| Container status (dry-run stubs) | `DryRunStubDocker` container status | Stub method call | No | Enabled |
| Config contents | Freqtrade config JSON files | File read (no parse/validate) | No | Enabled |

### 2.2 Conditional Sources (Require Explicit Opt-In)

| Source | Description | Access Method | Write-Capable | Default State |
|--------|-------------|---------------|---------------|---------------|
| Docker exec (read-only commands) | `docker exec <container> <cmd>` | Docker exec (stub or real) | No | Disabled-by-default |
| REST API status endpoints | `/status`, `/balance`, `/show_config` on Freqtrade | HTTP GET | No | Disabled-by-default |
| Signal trigger endpoint | `/trigger` on ai-hedge-fund-crypto | HTTP POST (read-only trigger) | No | Disabled-by-default |

### 2.3 Forbidden Sources (Never Observed During Rehearsal)

| Source | Reason |
|--------|--------|
| Exchange API endpoints | Would require credentials and create financial risk |
| Real exchange accounts | Would require credentials and create financial risk |
| Telegram bot API | Would require bot token and enable write capability |
| Docker container modification | Would modify system state |
| Freqtrade force-entry/force-exit | Would modify trading state |
| Secret stores / env with credentials | Would expose sensitive data |
| Production/live bot databases | Would indicate live trading state |

---

## 3. Observation Rules

- All observations must be read-only.
- No observation may modify the state of the observed system.
- No automatic action may be taken based on observation results.
- Observations must be logged with timestamps and source identifiers.
- Observations must not reveal credentials, secrets, tokens, or keys.
- Observations from conditional sources must be explicitly approved
  in the rehearsal approval packet (#138).
- Observations from forbidden sources must never be performed.

---

## 4. Reporting

Observations must be recorded in a structured format:

| Field | Required | Description |
|-------|----------|-------------|
| `observation_id` | ✅ | Unique identifier (`obs-<timestamp>-<random4>`) |
| `source` | ✅ | Observation source name from section 2 |
| `observed_at` | ✅ | ISO 8601 UTC timestamp |
| `observed_by` | ✅ | Agent or operator identifier |
| `observation` | ✅ | What was observed (value, state, output) |
| `expected` | ❌ | Expected value, if known |
| `deviation` | ❌ | Description of any deviation from expected |
| `severity` | ❌ | INFO / WARNING / ERROR |
| `approval_reference` | ✅ | Reference to the rehearsal approval token |

---

## 5. Disabled-by-Default Adapters

The following adapters have write capability and must remain **disabled**
by default during any rehearsal:

| Adapter | Write Capability | Default State | Env Gate |
|---------|-----------------|---------------|----------|
| `RealDockerAdapter` | Docker exec/write operations (but designed read-only) | Disabled | `SI_V2_ENABLE_REAL_ADAPTERS=1` |
| `RealFreqtradeAdapter` | Freqtrade config modification (but designed read-only) | Disabled | `SI_V2_ENABLE_REAL_ADAPTERS=1` |

These adapters may only be enabled after explicit human approval in the
rehearsal approval packet (#138).

---

## 6. No-Automatic-Action Rule

> **Observation results must never trigger automatic actions.**
>
> - Observations are for reporting and awareness only.
> - No script, cron job, or automated process may act on observations.
> - All actions based on observations require separate human approval.
> - This rule applies regardless of the observation result.
> - Violation of this rule constitutes a safety incident.

---

## 7. Change Log

| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Initial version | SI v2 (#139) |

---

*Maintained at `self_improvement_v2/rehearsal/read_only_observation_plan.md`*
*Created as part of #139 — Read-Only Observation Plan for Future Rehearsal*
