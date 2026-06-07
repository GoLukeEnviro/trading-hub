# Self-Improvement Orchestrator — Implementation Spec v1.0

**Project:** trading-hub  
**Version:** 1.0  
**Date:** 2026-06-07  
**Status:** Active

---

## 1. Purpose and Scope

### What This Spec Covers

This document defines **how the system deploys and operates** the Self-Improvement Orchestrator: the runtime environment, invocation interface, integration wiring between agents, directory layout, and operational runbook.

### What the Prompt Covers

The companion file `docs/specs/self-improvement-orchestrator-prompt.md` (v1.1) defines **what the agent does and how it behaves** — the episode procedure, quality gates, error handling, definitions, and output format. It is the authoritative system prompt for the Orchstrator agent when it runs.

### Relationship to ORCHESTRATOR_CHARTER.md

`ORCHESTRATOR_CHARTER.md` (v2.0) defines the binding orchestration rules, role splits, dry-run-only policy, hard limits, and human escalation matrix for the entire trading system. The Orchestrator operates within the constraints of that charter. This spec is the implementation-level companion.

---

## 2. Runtime Requirements

| Requirement | Specification |
|---|---|
| Python | 3.11+ |
| freqtrade CLI | Must be on `$PATH`. Verify with `freqtrade --version`; exit with code 2 if missing. |
| Git | Must be available via `git` on `$PATH`. Fallback: if git is unavailable, generate `episode_id` suffix from a deterministic hash (SHA-256 truncated to 6 hex chars) of the ISO timestamp. |
| pip installs | None beyond what freqtrade provides. The orchestrator uses stdlib only (`json`, `hashlib`, `subprocess`, `os`, `sys`, `datetime`, `typing`). |
| Working directory | Repository root (`/home/hermes/projects/trading` or the CI checkout root). Must contain `docs/`, `freqtrade/`, `var/`, `orchestrator/`, and `shadowlock/` at the top level. |
| File system | Writable `docs/context/`, `var/trading-shadowlock/backtests/`, and the target bot's strategy directory (for candidate strategy files). |

---

## 3. Invocation Interface

### CLI Contract

```
python orchestrator/run_episode.py \
  --trigger {manual|scheduled|post-forensics|post-incident} \
  --bot {freqforge|freqforge-canary|regime-hybrid|freqai-rebel} \
  [--proposal /path/to/proposal.json] \
  [--batch] \
  [--dry-run]
```

| Argument | Required | Description |
|---|---|---|
| `--trigger` | Yes | One of `manual`, `scheduled`, `post-forensics`, `post-incident`. Determines `trigger` field in all artifacts and shadowlock entries. |
| `--bot` | Yes | Target bot name. Must match a bot in `docs/specs/bot-roles-and-shadow-architecture.md`. |
| `--proposal` | No | Path to a manual proposal JSON file. When provided, overrides the recovery_candidates file for this episode. |
| `--batch` | No | Flag. When set, processes all non-EXCLUDED, non-HARD_STOP candidates in priority order rather than just the top candidate. |
| `--dry-run` | No | Flag. When set, runs all phases except the actual freqtrade backtest CLI call. A mock result fixture is used for testing. No shadowlock entries are written. |

### Exit Codes

| Code | Meaning |
|---|---|
| 0 | Episode completed (any outcome including pass, fail, partial, insufficient_data, error, no_candidates). |
| 1 | Episode aborted (BACKTEST_ERROR, LOCKED, TIMEOUT, INVALID_PARAMETER, etc.). |
| 2 | Critical error (ACTIVE_FILE_MODIFIED, artifact_completeness failure). |

---

## 4. Proposal JSON Schema

### Schema

```json
{
  "schema_version": "1.0",
  "target_bot": "<string>",
  "hypothesis": "<string, one sentence, <= 200 chars>",
  "source_forensics_run_id": "<string or \"manual\">",
  "expected_PF_floor": <float, >= 1.0>,
  "stop_conditions": ["<string>", ...],
  "parameters_to_test": [
    {
      "name": "<parameter name>",
      "current_value": <number or string>,
      "proposed_value": <number or string>
    }
  ],
  "episode_window_override": {
    "start_utc": "<ISO 8601 UTC>",
    "end_utc": "<ISO 8601 UTC>"
  }
}
```

| Field | Required | Description |
|---|---|---|
| `schema_version` | Yes | `"1.0"` |
| `target_bot` | Yes | Bot name slug. Must be resolvable via `docs/specs/bot-roles-and-shadow-architecture.md`. |
| `hypothesis` | Yes | One sentence ≤ 200 characters describing the expected improvement. |
| `source_forensics_run_id` | Yes | The forensics run ID that produced this candidate, or `"manual"`. |
| `expected_PF_floor` | Yes | Minimum PF expected. Must be ≥ 1.0. |
| `stop_conditions` | Yes | Array of condition strings (e.g., `["max_DD >= 15%"]`). At least one required. |
| `parameters_to_test` | Yes | Array of parameter change objects. At least one required. |
| `episode_window_override` | No | Optional override for the backtest window. If absent, default to last 180 days. |

### Worked Example — FreqForge Stoploss Change

```json
{
  "schema_version": "1.0",
  "target_bot": "freqforge",
  "hypothesis": "Tightening stoploss from -0.15 to -0.10 reduces max drawdown while preserving PF above 1.5.",
  "source_forensics_run_id": "forensics-2026-06-07-abc123",
  "expected_PF_floor": 1.5,
  "stop_conditions": [
    "max_DD >= 15%",
    "PF < 1.0",
    "trade_count < 30"
  ],
  "parameters_to_test": [
    {
      "name": "stoploss",
      "current_value": -0.15,
      "proposed_value": -0.10
    }
  ]
}
```

---

## 5. Integration Wiring

### Architecture Overview

```
┌─────────────────────┐
│  Forensics Agent    │
│  (Profitability)    │
└────────┬────────────┘
         │ writes recovery-candidates-YYYY-MM-DD.md
         ▼
┌─────────────────────────────────────┐
│  Self-Improvement Orchestrator     │
│  (run_episode.py)                  │
│                                     │
│  Reads: recovery_candidates file    │
│         forensics context file      │
│         strategy files (read-only)  │
│         shadowlock logs             │
│                                     │
│  Writes: episode reports            │
│          backtest results           │
│          shadowlock JSONL (direct)  │
│          inbox JSON (via service)   │
└────────┬────────────────────────────┘
         │
         ├──→ Shadowlock JSONL (direct, episode events only)
         │
         └──→ var/trading-shadowlock/inbox/ (for non-episode events)
                    │
                    ▼
         ┌──────────────────┐
         │ Shadowlock Writer│
         │ (running service)│
         └──────────────────┘
```

### Forensics Agent → Orchestrator

**Handoff mechanism:** File-system only. No direct API call.

- Forensics writes `docs/context/recovery-candidates-YYYY-MM-DD.md` after each run.
- Orchestrator reads the most recent such file by date.
- If no file exists, the orchestrator emits `NO_CANDIDATES` and terminates cleanly.
- The orchestrator never modifies forensics output files.

### Orchestrator → Shadowlock (Direct JSONL)

**Scope:** Episode events only.

The orchestrator writes directly to the JSONL ledger for:
- `episode_start` — pre-episode lock entry
- `episode_error` — backtest failure
- `self_improvement_episode` — post-episode outcome
- `active_file_modified` — critical sha256 mismatch
- `orchestrator_no_candidates` — clean termination
- `forensics_trigger` — HARD_STOP triggers re-forensics

**Path:** `var/trading-shadowlock/logs/YYYY/MM/DD.jsonl` (derived from current UTC date).

**Lock check:** Before writing any episode entry, the orchestrator checks for a shadowlock heartbeat within the last 10 minutes in today's log file. If absent, logs a non-blocking warning.

### Orchestrator → Shadowlock Writer Service

**Scope:** Non-episode events.

For events that are not part of an episode (e.g., `forensics_trigger` sent as a standalone message), the orchestrator drops a JSON file into `var/trading-shadowlock/inbox/`. The Shadowlock Writer service picks it up on its next poll (every `POLL_INTERVAL_SECONDS`).

**Inbox file format:**

```json
{
  "schema_version": "1.0",
  "event_type": "forensics_trigger",
  "bot_name": "freqforge",
  "timestamp_utc": "2026-06-07T12:00:00Z",
  "reason": "HARD_STOP on episode-abc-20260607",
  "episode_id": "episode-abc-20260607"
}
```

### Shadowlock Writer Service → Orchestrator

**Heartbeat:** The Shadowlock Writer emits a heartbeat entry to the JSONL ledger every `HEARTBEAT_INTERVAL_SECONDS` (default 300s). The orchestrator checks for a heartbeat within the last 10 minutes before writing any episode entry. If the heartbeat is absent, the orchestrator writes a warning to the errors array (non-blocking; the episode proceeds).

---

## 6. Episode Lifecycle Diagram

```
                    ┌──────────────────────────┐
                    │    PROPOSAL SOURCE        │
                    │  (recovery_candidates or  │
                    │   manual_proposal)        │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │  Phase 0: Preflight       │
                    │  - Verify paths, sha256   │
                    │  - Verify git, freqtrade  │
                    │  - Generate episode_id    │
                    │  - Acquire per-bot lock   │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │  Phase 1: Load & Rank     │
                    │  - Filter EXCLUDED        │
                    │  - Sort by priority_score │
                    │  - Check history          │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │  Phase 2: Prepare         │
                    │  - Define episode_window  │
                    │  - Create candidate strat │
                    │  - Write episode_start    │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │  Phase 3: Backtest        │
                    │  - Run freqtrade backtest │
                    │  - Save raw JSON          │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │  Phase 4: Evaluate        │
                    │  - Classify outcome       │
                    │  - Compare to baseline    │
                    │  - Compute confidence     │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │  Phase 5: Next Action     │
                    │  pass → READY_FOR_REVIEW  │
                    │  partial → FOLLOW_UP      │
                    │  fail → HARD_STOP / soft  │
                    │  insuff. → EXTEND_WINDOW  │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │  Phase 6: Report          │
                    │  - Write episode report   │
                    │  - Write reproducibility  │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │  Phase 7: Finalize        │
                    │  - Verify sha256 (post)   │
                    │  - Write shadowlock entry │
                    │  - Release lock           │
                    │  - Return JSON            │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │      JSON OUTPUT          │
                    └──────────────────────────┘

    Branch paths:

    Phase 0:
      LOCKED ──────────────────────────────→ ABORT (exit 1)
      ACTIVE_STRATEGY_UNRESOLVED ──────────→ ABORT (exit 1)

    Phase 1:
      NO_CANDIDATES ───────────────────────→ terminate (exit 0)

    Phase 3:
      BACKTEST_ERROR / TIMEOUT ────────────→ Phase 6 (ERROR outcome)

    Phase 4:
      (all outcomes proceed to Phase 5)

    Phase 5 (fail hard stop):
      HARD_STOP ──→ write forensics_trigger → Phase 6

    Phase 7:
      ACTIVE_FILE_MODIFIED ────────────────→ ABORT (exit 2)
      artifact_completeness failure ───────→ ABORT (exit 2)
```

---

## 7. Directory Layout

```
trading-hub/
│
├── docs/
│   ├── context/
│   │   ├── forensics-profitability-YYYY-MM-DD.md      # Forensics Agent output (read)
│   │   ├── recovery-candidates-YYYY-MM-DD.md           # Forensics Agent output (read)
│   │   ├── self-improvement-run-{episode_id}.md        # Orchestrator output (write)
│   │   └── reconstruction/                              # Forensics helper tables
│   │       └── profitability-map-YYYY-MM-DD.csv
│   │
│   └── specs/
│       ├── self-improvement-orchestrator-prompt.md      # Agent system prompt
│       ├── self-improvement-orchestrator-spec.md         # THIS FILE — implementation spec
│       ├── shadowlock-writer-spec.md                    # Shadowlock spec (read)
│       ├── profitability-forensics-agent-spec.md        # Forensics spec (read)
│       ├── bot-roles-and-shadow-architecture.md         # Bot registry (read)
│       └── trading-system-audit-2026-06-07.md           # System snapshot (read)
│
├── orchestrator/
│   ├── run_episode.py                                   # NOT YET IMPLEMENTED — entry point
│   └── ...                                              # Helper modules (future)
│
├── shadowlock/
│   ├── shadowlock_writer.py                             # Running service
│   ├── Dockerfile                                       # Container image
│   └── README.md                                        # Service documentation
│
├── tools/
│   ├── export_trade_history.py                          # Trade history export CLI
│   └── README.md                                        # Tool documentation
│
├── var/
│   └── trading-shadowlock/
│       ├── logs/YYYY/MM/DD.jsonl                        # Append-only JSONL ledger
│       ├── inbox/                                       # Inbound JSON files (service picks up)
│       ├── processed/                                   # Successfully processed inbox files
│       ├── quarantine/                                  # Malformed entries (schema violation)
│       ├── dead-letter/                                 # Failed writes (retries exhausted)
│       ├── intents/                                     # Run intent lock files
│       ├── archive/                                     # Compressed historical logs
│       ├── backtests/                                   # Backtest result artifacts
│       │   ├── {episode_id}-raw.json                    # Raw freqtrade backtest output
│       │   └── {episode_id}.jsonl                       # Backtest reproducibility record
│       └── state/                                       # Runtime state (sequence numbers)
│           └── {bot_name}.seq                           # Per-bot monotonic sequence counter
│
└── freqtrade/
    ├── bots/
    │   ├── freqforge/user_data/strategies/              # Active + candidate strategies
    │   ├── freqforge-canary/user_data/strategies/
    │   ├── regime-hybrid/user_data/strategies/
    │   └── freqai-rebel/user_data/strategies/
    └── shared/
```

**Key annotations:**

- All paths are relative to the repository root.
- `docs/context/` is append-only. Orchestrator writes new files; never modifies existing ones.
- `var/trading-shadowlock/` is append-only after creation. Orchestrator writes to `logs/` and `backtests/`, drops inbox JSONs, and reads `state/`.
- Candidate strategy files are written to the target bot's strategy directory with the suffix `_episode_{episode_id}.py`.
- The `state/{bot_name}.seq` file is a simple text file containing a single integer (the last sequence number). The Shadowlock Writer manages this per-bot.

---

## 8. Operational Runbook

### Scenario A — Running a Manual Episode on FreqForge

1. **Prepare a proposal JSON file:** Create a file like `/tmp/proposal-freqforge.json` following the schema in Section 4.
2. **Verify runtime:**
   ```bash
   cd /home/hermes/projects/trading
   freqtrade --version
   git status
   ```
3. **Run the episode:**
   ```bash
   python orchestrator/run_episode.py \
     --trigger manual \
     --bot freqforge \
     --proposal /tmp/proposal-freqforge.json
   ```
4. **Expected outcomes:**
   - Exit code 0: episode completed. Find artifacts at:
     - `docs/context/self-improvement-run-{episode_id}.md`
     - `var/trading-shadowlock/backtests/{episode_id}-raw.json`
   - Exit code 1: episode aborted. Check stderr for the error reason.
   - Exit code 2: critical error. Check shadowlock for `active_file_modified` or `artifact_completeness` entry.
5. **Inspect results:**
   ```bash
   cat docs/context/self-improvement-run-{episode_id}.md
   ```

### Scenario B — Checking Episode Status After a Run

1. **Check exit code:**
   ```bash
   echo $?
   ```
2. **List recent episode reports:**
   ```bash
   ls -lt docs/context/self-improvement-run-*.md | head -5
   ```
3. **Check shadowlock for the episode entry:**
   ```bash
   grep -l "{episode_id}" var/trading-shadowlock/logs/$(date +%Y)/$(date +%m)/$(date +%d).jsonl
   ```
4. **Check per-bot lock status:**
   Look for the most recent `episode_start` entry for the bot in today's shadowlock log. Status transitions: `locked` → `in_progress` → `released | aborted`.

### Scenario C — Recovering from a Stale Per-Bot Lock

1. **Detect stale lock:** An `episode_start` entry with status `locked` or `in_progress` that is older than 24 hours.
2. **Verify no episode is actually running:**
   ```bash
   ps aux | grep run_episode.py
   ```
3. **Force-release the lock:**
   Write a shadowlock entry documenting the force-release:
   ```
   event_type: episode_lock_released
   reason: "stale lock reclaimed — last updated at {timestamp}, > 24h old"
   ```
   Then proceed with the new episode.
4. **Run the new episode:**
   ```bash
   python orchestrator/run_episode.py \
     --trigger manual \
     --bot freqforge
   ```
   The orchestrator will acquire a fresh lock.

---

## 9. Known Limitations (as of 2026-06-07)

1. **Orchestrator is spec-only:** The runtime code (`orchestrator/run_episode.py`) is not yet implemented. This spec and the companion prompt define the interface and behaviour but no executable exists yet.

2. **Trade history must be exported manually:** Before the first Forensics Agent run, trade history must be exported using `tools/export_trade_history.py`. See `tools/README.md` for usage instructions.

3. **Shadowlock Writer service must be running:** The Shadowlock Writer service (implemented in `shadowlock/shadowlock_writer.py`) must be deployed and running before the first episode writes inbox files. Without the service, inbox entries accumulate unprocessed.

4. **No automatic Forensics scheduling:** There is no cron job or scheduler that triggers the Forensics Agent automatically. It must be invoked manually or via a CI hook until a scheduler is configured.

5. **Docker Compose integration pending:** The shadowlock service is defined in `docker-compose.yml` but is not part of any existing stack's `depends_on` chain. It runs independently.

6. **No walk-forward validation:** The current spec defines hold-out backtest windows but does not require walk-forward analysis. This is a known gap for future versions.

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-06-07 | Initial implementation spec — companion to orchestrator prompt v1.1 |
