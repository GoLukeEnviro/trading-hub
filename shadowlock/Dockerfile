# Shadowlock Writer — Minimal Production Image
#
# Implements the Shadowlock Writer spec as a continuously running
# JSONL ledger service. Picks up files from inbox, validates,
# sequences, checksums, and appends them to daily log files.

FROM python:3.11-slim

WORKDIR /app

# Copy service script and healthcheck helper
COPY shadowlock_writer.py .
COPY healthcheck.py .

# Runtime configuration (all overridable via environment)
ENV SHADOWLOCK_BASE_DIR=/app/var/trading-shadowlock
ENV POLL_INTERVAL_SECONDS=60
ENV HEARTBEAT_INTERVAL_SECONDS=300
ENV LOG_LEVEL=INFO

# Healthcheck: verify a heartbeat entry was written within the last 10 minutes.
# healthcheck.py exits 0 (healthy) or 1 (unhealthy).
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python healthcheck.py

# Run the service
CMD ["python", "shadowlock_writer.py"]
