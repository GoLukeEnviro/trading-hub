# Shadowlock Writer — Minimal Production Image
#
# Implements the Shadowlock Writer spec as a continuously running
# JSONL ledger service. Picks up files from inbox, validates,
# sequences, checksums, and appends them to daily log files.

FROM python:3.11-slim

WORKDIR /app

# Copy only the service script — no other dependencies needed
COPY shadowlock_writer.py .

# Runtime configuration (all overridable via environment)
ENV SHADOWLOCK_BASE_DIR=/app/var/trading-shadowlock
ENV POLL_INTERVAL_SECONDS=60
ENV HEARTBEAT_INTERVAL_SECONDS=300
ENV LOG_LEVEL=INFO

# Healthcheck: verify a heartbeat entry was written within the last 10 minutes
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python -c "
import os, sys, json, glob, time, datetime
basedir = os.environ.get('SHADOWLOCK_BASE_DIR', '/app/var/trading-shadowlock')
now = datetime.datetime.utcnow()
cutoff = now - datetime.timedelta(seconds=600)
logdir = os.path.join(basedir, 'logs', str(now.year), f'{now.month:02d}')
if not os.path.isdir(logdir):
    print('NO_LOG_DIR')
    sys.exit(1)
files = sorted(glob.glob(os.path.join(logdir, '*.jsonl')), reverse=True)
if not files:
    print('NO_LOG_FILES')
    sys.exit(1)
latest = files[0]
with open(latest, 'r') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get('event_type') == 'shadowlock_heartbeat':
            ts = entry.get('timestamp_utc', '')
            if ts.endswith('Z'):
                try:
                    hb_time = datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%SZ')
                    if hb_time >= cutoff:
                        print(f'HEALTHY: heartbeat at {ts}')
                        sys.exit(0)
                except ValueError:
                    continue
print('NO_RECENT_HEARTBEAT')
sys.exit(1)
"

# Run the service
CMD ["python", "shadowlock_writer.py"]
