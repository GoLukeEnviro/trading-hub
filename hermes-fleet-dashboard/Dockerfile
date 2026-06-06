FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir flask requests
COPY dashboard.py .
EXPOSE 5000
CMD ["python3", "dashboard.py"]
