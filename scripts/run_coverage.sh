#!/usr/bin/env bash
# run_coverage.sh — Reproducible coverage workflow for trading-hub
# PEP 668 safe: uses project .venv only, never touches system Python.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# ── 1. Ensure virtualenv ──────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "==> Creating .venv (Python $(python3 -V 2>&1 | awk '{print $2}'))"
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
. .venv/bin/activate

# ── 2. Install dependencies into .venv only ───────────────────────
echo "==> Installing dependencies into .venv"
python -m pip install -U pip setuptools wheel -q

if [ -f "pyproject.toml" ]; then
  python -m pip install -e ".[dev]" -q || true
fi

# Install self_improvement_v2 as editable package (required for si_v2 imports)
if [ -d "self_improvement_v2" ]; then
  python -m pip install -e self_improvement_v2 -q || true
fi

if [ -f "requirements.txt" ]; then
  python -m pip install -r requirements.txt -q || true
fi

python -m pip install coverage -q

# ── 3. Verify toolchain ───────────────────────────────────────────
echo ""
echo "Python:  $(command -v python)  ($(python -V 2>&1))"
echo "Pip:     $(python -m pip -V 2>&1 | cut -d' ' -f1-3)"
echo "Pytest:  $(python -m pytest --version 2>&1 | head -1)"
echo "Coverage: $(python -m coverage --version 2>&1 | head -1)"
echo ""

# Guard: pip MUST point into .venv
PIP_LOC=$(python -m pip -V 2>&1 | grep -o '/.*/pip' | head -1 || true)
if [ -z "$PIP_LOC" ] || ! echo "$PIP_LOC" | grep -q '.venv'; then
  echo "ERROR: pip path does not point into .venv: $PIP_LOC"
  exit 1
fi

# ── 4. Run tests with coverage ────────────────────────────────────
echo "==> Running coverage (self_improvement_v2 + orchestrator + root tests)"
echo ""

python -m pytest \
  self_improvement_v2/tests \
  self_improvement_v2/src \
  orchestrator/tests \
  orchestrator/control/tests \
  tests \
  -q \
  --cov \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml \
  --cov-report=json:coverage.json \
  --cov-report=html:htmlcov \
  "$@"

echo ""
echo "==> Artifacts:"
echo "    coverage.xml"
echo "    coverage.json"
echo "    htmlcov/index.html"
echo ""
echo "==> Coverage complete."
