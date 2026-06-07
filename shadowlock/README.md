# Shadowlock Writer Service

`shadowlock_writer.py` is a lightweight stdlib-only service that ingests JSON entries from an inbox and appends validated, hash-sealed records to date-partitioned shadowlock logs.

## Run locally

```bash
POLL_INTERVAL_SECONDS=60 LOG_LEVEL=INFO python3 shadowlock/shadowlock_writer.py
```

## Docker

```bash
docker build -t shadowlock-writer ./shadowlock
docker run --rm \
  -e POLL_INTERVAL_SECONDS=60 \
  -e LOG_LEVEL=INFO \
  -v "$PWD/var/trading-shadowlock:/app/var/trading-shadowlock" \
  shadowlock-writer
```

## Inbox entry example

Create a JSON file in `var/trading-shadowlock/inbox/`, for example `sample.json`:

```json
{
  "timestamp_utc": "2026-06-07T00:00:00Z",
  "event_type": "self_improvement_episode",
  "bot_name": "freqforge",
  "schema_version": "1.0",
  "episode_id": "episode-freqforge-20260607-abc123"
}
```

The service will validate and enrich entries with:

- `entry_sha256`
- `sequence_number` (per bot)
- `ingested_at_utc`

## Processing behavior

- Valid entries: appended to `var/trading-shadowlock/logs/YYYY/MM/DD.jsonl`, input moved to `processed/`
- Validation failures: input moved to `quarantine/`
- Write failures after 3 retries: input moved to `dead-letter/`
- Heartbeat every 5 minutes (`HEARTBEAT_INTERVAL_SECONDS=300`): `event_type = shadowlock_heartbeat`

## Directory layout

```text
var/trading-shadowlock/
├── inbox/
├── processed/
├── quarantine/
├── dead-letter/
├── state/
└── logs/
    └── YYYY/
        └── MM/
            └── DD.jsonl
```
