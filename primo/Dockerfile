FROM python:3.11-slim

WORKDIR /app

# System deps for TA-lib / numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || true
RUN pip install --no-cache-dir \
    ccxt>=4.4.0 \
    fastapi>=0.110.0 \
    uvicorn[standard]>=0.29.0 \
    pydantic>=2.6.0 \
    "langchain-openai>=0.3.0" \
    "ta>=0.11.0" \
    pandas>=2.0.0 \
    numpy>=1.24.0

# Copy PrimoAgent source code
COPY . /app/

# Copy our API wrapper (must be in build context — copied there beforehand)
COPY primo_api.py /app/primo_api.py

# Remove any .env secrets from image
RUN rm -f /app/.env /app/src/.env

# Create log directory
RUN mkdir -p /logs && chmod 777 /logs

# Expose API port
EXPOSE 8420

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8420/health || exit 1

CMD ["python", "-u", "/app/primo_api.py"]
