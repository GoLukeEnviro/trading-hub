# =============================================================================
# HERMES-BRIDGE — Lightweight Python status server + Primo poller
# =============================================================================
# Kein Freqtrade, keine schweren Dependencies — nur Python stdlib.
# Läuft als separater Container auf ki-fabrik, pollt PrimoAgent alle 60s
# und schreibt genehmigte Signale in per-pair Dateien.
# =============================================================================

FROM python:3.11-slim

LABEL hermes.layer="bridge"
LABEL hermes.component="signal-orchestrator"

# Keine externen Dependencies nötig — alles stdlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Script wird als Volume gemountet
COPY hermes_primo_bridge.py /app/hermes_primo_bridge.py

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${HERMES_BRIDGE_PORT:-9118}/health || exit 1

USER nobody

CMD ["python3", "-u", "/app/hermes_primo_bridge.py"]
