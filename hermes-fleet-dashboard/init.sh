#!/bin/bash
set -e
pip install --quiet flask requests
exec python3 /app/dashboard.py
