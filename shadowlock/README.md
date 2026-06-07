# Shadowlock Writer Service

Append-only JSONL ledger service for the trading-hub system. Implements the
[Shadowlock Writer spec v2.0](../docs/specs/shadowlock-writer-spec.md).

Picks up JSON files from the `inbox/` directory, validates them, assigns
sequence numbers, computes SHA-256 checksums, and appends them to daily
JSONL log files. Never mutates or deletes historical entries.

---

## What It Does

- Polls `var/trading-shadowlock/inbox/` every `POLL_INTERVAL_SECONDS` for `*.json` files
- Validates required fields (`schema_version`, `event_type`, `timestamp_utc`, `bot_name`/`target_bot`)
- Computes SHA-256 of each entry (with `entry_sha256` set to `""` beforehand)
- Assigns monotonically increasing sequence numbers per bot
- Appends to `var/trading-shadowlock/logs/YYYY/MM/DD.jsonl` with file locking
- Emits periodic heartbeats (every `HEARTBEAT_INTERVAL_SECONDS`)
- Quarantines invalid entries, dead-letters entries after write retry exhaustion
- Handles SIGTERM/SIGINT gracefully

---

## How to Run

### Standalone (from repo root)

```bash
cd /path/to/trading-hub
SHADOWLOCK_BASE_DIR=var/trading-shadowlock \
POLL_INTERVAL_SECONDS=60 \
HEARTBEAT_INTERVAL_SECONDS=300 \
LOG_LEVEL=INFO \
python shadowlock/shadowlock_writer.py
```

### Via Docker Compose

```bash
docker compose up shadowlock
```

This starts the service defined in `docker-compose.yml`. Logs are visible via:

```bash
docker compose logs -f shadowlock
```

---

## How to Write an Inbox Entry

Create a JSON file in `var/trading-shadowlock/inbox/` matching the required
schema. The service picks it up within `POLL_INTERVAL_SECONDS` seconds.

### Worked Example

Save this as `var/trading-shadowlock/inbox/my-entry.json`:

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

After the service picks it up:
- The file moves to `processed/2026-06-07-my-entry.json`
- The entry appears in `logs/2026/06/07.jsonl` with `sequence_number` and `entry_sha256` populated

---

## Directory Layout

```
var/trading-shadowlock/
├── inbox/                          # Drop JSON files here for processing
│   └── my-entry.json
├── processed/                      # Successfully processed inbox files
│   └── YYYY-MM-DD-my-entry.json
├── logs/YYYY/MM/DD.jsonl           # Append-only JSONL ledger (one per day)
├── state/                          # Per-bot sequence counters
│   ├── freqforge.seq              # Monotonically increasing integer
│   ├── shadowlock-writer.seq      # Heartbeat sequence counter
│   └── ...
├── quarantine/                     # Malformed entries (schema validation failure)
│   └── YYYY-MM-DD-filename.json
├── dead-letter/                    # Valid entries that failed all write retries
│   └── YYYY-MM-DD-filename.json
├── backtests/                      # Backtest reproducibility artifacts
├── intents/                        # Run intent lock files
└── archive/                        # Compressed historical logs
```

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `SHADOWLOCK_BASE_DIR` | `var/trading-shadowlock` | Base directory for all shadowlock data. Relative paths resolve from the working directory. |
| `POLL_INTERVAL_SECONDS` | `60` | How often to scan the inbox directory for new files. |
| `HEARTBEAT_INTERVAL_SECONDS` | `300` | How often to write a heartbeat entry to the daily log. |
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

---

## Troubleshooting

### Entry in `dead-letter/`

**Symptom:** A file appeared in `dead-letter/` instead of `processed/`.

**Cause:** The entry was valid but the service exhausted 3 write retries
(1s, 2s, 4s exponential backoff) when trying to append to the JSONL log file.
Possible reasons:
- Disk full
- Permission denied on the log directory
- File lock contention

**Action:**
1. Check the service logs for the specific error.
2. Resolve the underlying issue (free disk space, fix permissions).
3. Move the file back to `inbox/` for re-processing:
   ```bash
   mv var/trading-shadowlock/dead-letter/YYYY-MM-DD-filename.json \
      var/trading-shadowlock/inbox/
   ```
4. The service picks it up within `POLL_INTERVAL_SECONDS`.
5. Verify the sequence number was not already used (check `state/{bot}.seq`
   and the log file). If it was, increment the sequence manually before
   moving back.

### Entry in `quarantine/`

**Symptom:** A file appeared in `quarantine/`.

**Cause:** The entry failed schema validation. Common reasons:
- Missing required field (`schema_version`, `event_type`, `timestamp_utc`, `bot_name`)
- `timestamp_utc` does not end with `Z` or is not ISO 8601
- JSON is malformed (unparseable)

**Action:**
1. Inspect the quarantined file:
   ```bash
   cat var/trading-shadowlock/quarantine/YYYY-MM-DD-filename.json | python3 -m json.tool
   ```
2. Fix the JSON (add missing fields, correct timestamp format).
3. Move the fixed file back to `inbox/`:
   ```bash
   mv var/trading-shadowlock/quarantine/YYYY-MM-DD-filename.json \
      var/trading-shadowlock/inbox/
   ```

### Stale `.lock` File

**Symptom:** Log writes are blocked.

**Cause:** The service crashed while holding a file lock on a log file,
leaving the lock unreleased.

**On Linux (fcntl):** File locks are automatically released when the
holding process dies. No manual cleanup needed.

**On other platforms (sidecar .lock file):**
1. Verify no shadowlock process is running:
   ```bash
   ps aux | grep shadowlock_writer
   ```
2. Remove the stale lock file:
   ```bash
   rm -f var/trading-shadowlock/logs/YYYY/MM/DD.jsonl.lock
   ```

---

## Schema Version Compatibility

The service currently writes and expects `schema_version: "1.0"`.

- Entries with an unknown `schema_version` are **accepted with a warning** (not quarantined).
- The WARNING is logged, and the entry is processed normally.
- This ensures forward compatibility when new schema versions are introduced.
