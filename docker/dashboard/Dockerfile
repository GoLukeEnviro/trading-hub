FROM python:3.12-slim

WORKDIR /app

# Install Flask (required by the mounted dashboard.py)
RUN pip install --no-cache-dir flask>=3.0

# The actual dashboard.py is mounted at runtime via docker-compose volume:
#   ./dashboard.py:/app/dashboard.py:ro
# This Dockerfile provides the runtime environment only.

EXPOSE 5000

CMD ["python3", "/app/dashboard.py"]
