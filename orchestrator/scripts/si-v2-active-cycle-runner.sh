#!/usr/bin/env bash
#
# SI v2 Active Cycle Runner — Scheduled Wrapper
#
# Read-only, proposal-only observation loop.
# No live trading. No dry_run=false. No Docker mutation.
# No config mutation. No strategy mutation. No apply path.
#
# Owner: hermes:hermes   Mode: 700
# Secrets: loaded from /opt/data/secrets/si-v2-freqtrade.env (never echoed)

set -euo pipefail
set +x

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO="/home/hermes/projects/trading"
SI_V2_DIR="${REPO}/self_improvement_v2"
SECRET_ENV="/opt/data/secrets/si-v2-freqtrade.env"
LOG_DIR="/opt/data/logs/si-v2-active-cycle"
RUNNER="src/si_v2/loop/active_cycle_runner.py"
VENV_PY="${SI_V2_DIR}/.venv/bin/python"
STATE_FILE="${SI_V2_DIR}/reports/phase2/cycle_state/active_cycle_latest.state.json"
SUMMARY_FILE="${SI_V2_DIR}/reports/phase2/measurement/measurement_summary.json"

# ---------------------------------------------------------------------------
# Rainbow read_only stub server (only used when SI_V2_RAINBOW_MODE=read_only)
# The stub is a tiny, credential-free HTTP server that exposes the local
# Rainbow signals.db on GET /signals/latest.  It opens the DB in mode=ro,
# binds to 127.0.0.1, and is started/stopped inside this wrapper so the
# scheduler only ever runs the cycle against a known, single-purpose source.
# ---------------------------------------------------------------------------
STUB_SCRIPT="${REPO}/orchestrator/scripts/rainbow_db_stub_server.py"
STUB_DB="/opt/data/ai4trade-bot/rainbow/storage/signals.db"
# Default port range; we let the OS pick a free one if --port 0 is given
# (but for reproducibility we pin a single port; the wrapper retries on
# EADDRINUSE up to 5 ports).
STUB_PORT="${SI_V2_RAINBOW_STUB_PORT:-8765}"
STUB_HOST="127.0.0.1"
STUB_PID=""

# ---------------------------------------------------------------------------
# Timestamped log file
# ---------------------------------------------------------------------------
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${LOG_DIR}/cycle-${STAMP}.log"

mkdir -p "${LOG_DIR}"

# ---------------------------------------------------------------------------
# Start banner (to stdout AND log)
# ---------------------------------------------------------------------------
log() { echo "$1" | tee -a "${LOG_FILE}"; }

log "=== SI v2 Active Cycle Runner (wrapper) ==="
log "start_timestamp=${STAMP}"

# ---------------------------------------------------------------------------
# Repo HEAD
# ---------------------------------------------------------------------------
cd "${REPO}"
HEAD_SHA="$(git rev-parse --short HEAD)"
BRANCH="$(git branch --show-current)"
log "branch=${BRANCH}"
log "head=${HEAD_SHA}"

# ---------------------------------------------------------------------------
# Load secrets (no values echoed)
# ---------------------------------------------------------------------------
set -a
. "${SECRET_ENV}"
set +a

# ---------------------------------------------------------------------------
# Enable Rainbow external signal observation.
#
# Code default remains disabled; the env-vars below are the runtime opt-in.
# Two modes:
#   * fixture  — read signals from in-tree fixture files (no network)
#   * read_only — fetch from a credential-free HTTP source configured via
#                 SI_V2_RAINBOW_BASE_URL / SI_V2_RAINBOW_ENDPOINT_PATH
#
# The 6h scheduler job keeps the fixture default for safety.  The
# ``si-v2-rainbow-read-only-runtime-proof`` one-shot job can override
# SI_V2_RAINBOW_MODE=read_only to exercise the new code path; this
# wrapper detects that and starts/stops the local DB-backed stub.
# ---------------------------------------------------------------------------
export SI_V2_RAINBOW_ENABLED=true
export SI_V2_RAINBOW_MODE="${SI_V2_RAINBOW_MODE:-read_only}"

log "rainbow_enabled=true"
log "rainbow_mode=${SI_V2_RAINBOW_MODE}"

# ---------------------------------------------------------------------------
# If read_only mode is requested, start the local DB-backed stub server
# for the duration of the cycle, then stop it cleanly afterwards.
# ---------------------------------------------------------------------------
start_stub() {
  if [ ! -f "${STUB_SCRIPT}" ]; then
    log "stub_start_status=ERROR script_not_found=${STUB_SCRIPT}"
    return 1
  fi
  # Pick a free port if the configured one is in use (max 5 attempts).
  local port="${STUB_PORT}"
  local attempt=0
  while [ "${attempt}" -lt 5 ]; do
    "${VENV_PY}" "${STUB_SCRIPT}" \
      --host "${STUB_HOST}" --port "${port}" --db "${STUB_DB}" \
      >> "${LOG_FILE}" 2>&1 &
    STUB_PID=$!
    # Brief wait for the server to bind.
    sleep 0.5
    if kill -0 "${STUB_PID}" 2>/dev/null; then
      log "stub_start_status=OK host=${STUB_HOST} port=${port} pid=${STUB_PID}"
      export SI_V2_RAINBOW_BASE_URL="http://${STUB_HOST}:${port}"
      export SI_V2_RAINBOW_ENDPOINT_PATH="${SI_V2_RAINBOW_ENDPOINT_PATH:-/signals/latest}"
      return 0
    fi
    attempt=$((attempt + 1))
    port=$((port + 1))
  done
  log "stub_start_status=ERROR reason=eaddrinuse_retries_exhausted"
  return 1
}

stop_stub() {
  if [ -n "${STUB_PID}" ] && kill -0 "${STUB_PID}" 2>/dev/null; then
    kill "${STUB_PID}" 2>/dev/null || true
    wait "${STUB_PID}" 2>/dev/null || true
    log "stub_stop_status=OK pid=${STUB_PID}"
  fi
  STUB_PID=""
}

STUB_STARTED=0
if [ "${SI_V2_RAINBOW_MODE}" = "read_only" ]; then
  if start_stub; then
    STUB_STARTED=1
    # Wait briefly for the HTTP listener to be reachable.
    sleep 0.3
  else
    log "stub_start_failed_fall_back=fixture"
    export SI_V2_RAINBOW_MODE=fixture
  fi
fi

# Cleanup trap: ensure the stub is stopped on any exit path.
cleanup() {
  if [ "${STUB_STARTED}" -eq 1 ]; then
    stop_stub
  fi
}
trap cleanup EXIT INT TERM

log "== env presence =="
for v in \
  SI_V2_FREQTRADE_FREQFORGE_USERNAME \
  SI_V2_FREQTRADE_FREQFORGE_PASSWORD \
  SI_V2_FREQTRADE_REGIME_HYBRID_USERNAME \
  SI_V2_FREQTRADE_REGIME_HYBRID_PASSWORD \
  SI_V2_FREQTRADE_FREQFORGE_CANARY_USERNAME \
  SI_V2_FREQTRADE_FREQFORGE_CANARY_PASSWORD \
  SI_V2_FREQTRADE_FREQAI_REBEL_USERNAME \
  SI_V2_FREQTRADE_FREQAI_REBEL_PASSWORD
do
  if [ -n "${!v:-}" ]; then
    log "${v}=SET"
  else
    log "${v}=MISSING"
  fi
done

# ---------------------------------------------------------------------------
# Run active cycle (output to log file only — NOT stdout to avoid secret leak)
# ---------------------------------------------------------------------------
cd "${SI_V2_DIR}"

RUNNER_RC=0
PYTHONPATH=src "${VENV_PY}" "${RUNNER}" >> "${LOG_FILE}" 2>&1 || RUNNER_RC=$?

log "runner_exit_code=${RUNNER_RC}"

# ---------------------------------------------------------------------------
# Extract key results from state JSON (secret-safe)
# ---------------------------------------------------------------------------
if [ -f "${STATE_FILE}" ]; then
  "${VENV_PY}" -c "
import json
d = json.load(open('${STATE_FILE}'))
print('cycle_id=' + str(d.get('cycle_id', '')))
print('fleet_verdict=' + str(d.get('fleet_verdict', '')))
print('controller=' + str(d.get('controller_state', '')))
print('ping_ok=' + str(d.get('ping_ok_count', '')) + '/' + str(d.get('total_bots', '')))
print('mutation_runtime=' + str(d.get('runtime_mutations', 'N/A')))
print('mutation_config=' + str(d.get('config_mutations', 'N/A')))
print('mutation_live_trading=' + str(d.get('live_trading_mutations', 'N/A')))
print('mutation_docker=' + str(d.get('docker_mutations', 'N/A')))
print('mutation_strategy=' + str(d.get('strategy_mutations', 'N/A')))
rainbow = d.get('external_signals', {}).get('rainbow', {})
print('rainbow_status=' + str(rainbow.get('status', 'N/A')))
print('rainbow_source=' + str(rainbow.get('source', 'N/A')))
print('rainbow_count=' + str(rainbow.get('count', 'N/A')))
print('rainbow_errors=' + str(len(rainbow.get('errors', []) or [])))
print('rainbow_freshness_seconds=' + str(rainbow.get('freshness_seconds', 'N/A')))
print('rainbow_freshness_max_seconds=' + str(rainbow.get('freshness_max_seconds', 'N/A')))
print('rainbow_fresh=' + str(rainbow.get('fresh', False)))
" 2>&1 | while IFS= read -r line; do log "${line}"; done
else
  log "state_file=NOT_FOUND"
fi

if [ -f "${SUMMARY_FILE}" ]; then
  "${VENV_PY}" -c "
import json
d = json.load(open('${SUMMARY_FILE}'))
print('ledger_status=SUCCESS')
print('cycles_scanned=' + str(d.get('total_cycles_scanned', '')))
print('bot_measurement_points=' + str(d.get('total_bot_points', '')))
print('proposal_records=' + str(d.get('total_proposal_records', '')))
print('mutations_all_zero=' + str(d.get('mutations_all_zero', '')))
print('secrets_found=' + str(d.get('secrets_found', '')))
" 2>&1 | while IFS= read -r line; do log "${line}"; done
else
  log "summary_file=NOT_FOUND"
fi

log "log_file=${LOG_FILE}"
log "=== wrapper complete ==="

exit "${RUNNER_RC}"
