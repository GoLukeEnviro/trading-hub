# Rainbow Producer — Trading Hub Container
# EXPERIMENTAL — NOT THE ACTIVE DEPLOYMENT PATH
# =============================================
# This Dockerfile is a fallback for future use. The current active
# deployment uses the direct uvicorn + manager.sh approach because:
#   - Docker daemon blocks builds on this host (HTTP 403)
#   - ai4trade-bot rainbow.Dockerfile has missing core/ dependency
#
# Build from ai4trade-bot root context:
#   docker build -t trading-rainbow-producer -f /home/hermes/projects/trading/orchestrator/profiles/rainbow-producer.Dockerfile /opt/data/ai4trade-bot
#
# Run:
#   docker run -d --name trading-rainbow-producer-1 \
#     --restart unless-stopped \
#     -p 127.0.0.1:8000:8000 \
#     -v /opt/data/ai4trade-bot/rainbow/storage:/app/rainbow/storage \
#     -v /opt/data/ai4trade-bot/rainbow/config.yaml:/app/rainbow/config.yaml:ro \
#     trading-rainbow-producer

FROM python:3.12-slim

RUN groupadd -r rainbow && useradd -r -g rainbow rainbow

WORKDIR /app

# Install deps first for layer caching
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source (includes core/ and rainbow/)
COPY core/ ./core/
COPY rainbow/ ./rainbow/

RUN chown -R rainbow:rainbow /app
USER rainbow

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import json, urllib.request; \
        h = json.loads(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read()); \
        exit(0 if h.get('status') == 'healthy' else 1)"

ENTRYPOINT ["uvicorn", "rainbow.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
