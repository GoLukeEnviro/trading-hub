#!/usr/bin/env bash
#
# SI-v2 T4 Watcher Job Wrapper — Hermes no_agent entrypoint
#
# Contract:
#   - STILL_WAITING (exit 0 from underlying watcher) is healthy and SILENT.
#   - MEASUREMENT_READY (exit 10) emits a visible local alert but stays non-error.
#   - SAFETY_BLOCKED / DATA_UNAVAILABLE / SCRIPT_ERROR remain alert-worthy failures.
#   - Detection only: no Decision Engine, no apply, no restart, no rollback.
#
# Logs:
#   /opt/data/logs/si-v2-t4-watcher/watcher-<timestamp>.log
#
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DEFAULT_REPO_ROOT="$(git -C "${SCRIPT_DIR}/../.." rev-parse --show-toplevel 2>/dev/null || true)"
REPO_ROOT="${SI_V2_REPO_ROOT:-${DEFAULT_REPO_ROOT}}"
UNDERLYING_WATCHER="${SI_V2_T4_WATCHER_SCRIPT:-${REPO_ROOT}/orchestrator/scripts/si_v2_t4_measurement_watcher.sh}"
LOG_DIR="${SI_V2_T4_WATCHER_LOG_DIR:-/opt/data/logs/si-v2-t4-watcher}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${LOG_DIR}/watcher-${STAMP}.log"
LATEST_LOG="${LOG_DIR}/latest.log"

mkdir -p "${LOG_DIR}"

if [ -z "${REPO_ROOT}" ] || [ ! -d "${REPO_ROOT}" ]; then
  {
    echo "wrapper_status=SCRIPT_ERROR"
    echo "error=repo_root_not_found"
  } | tee "${LOG_FILE}" > /dev/null
  cp "${LOG_FILE}" "${LATEST_LOG}"
  echo "SI_V2_T4_WATCHER_ALERT=SCRIPT_ERROR"
  echo "ERROR=repo_root_not_found"
  echo "LOG_FILE=${LOG_FILE}"
  exit 40
fi

if [ ! -x "${UNDERLYING_WATCHER}" ]; then
  {
    echo "wrapper_status=DATA_UNAVAILABLE"
    echo "error=underlying_watcher_not_executable:${UNDERLYING_WATCHER}"
  } | tee "${LOG_FILE}" > /dev/null
  cp "${LOG_FILE}" "${LATEST_LOG}"
  echo "SI_V2_T4_WATCHER_ALERT=DATA_UNAVAILABLE"
  echo "ERROR=underlying_watcher_not_executable:${UNDERLYING_WATCHER}"
  echo "LOG_FILE=${LOG_FILE}"
  exit 30
fi

watcher_output=""
watcher_rc=0
set +e
watcher_output="$(SI_V2_REPO_ROOT="${REPO_ROOT}" "${UNDERLYING_WATCHER}" 2>&1)"
watcher_rc=$?
set -e

{
  echo "timestamp_utc=${STAMP}"
  echo "repo_root=${REPO_ROOT}"
  echo "underlying_watcher=${UNDERLYING_WATCHER}"
  echo "underlying_exit_code=${watcher_rc}"
  if [ -n "${watcher_output}" ]; then
    printf '%s\n' "${watcher_output}"
  fi
} > "${LOG_FILE}"
cp "${LOG_FILE}" "${LATEST_LOG}"

case "${watcher_rc}" in
  0)
    exit 0
    ;;
  10)
    echo "SI_V2_T4_WATCHER_ALERT=MEASUREMENT_READY"
    echo "LOG_FILE=${LOG_FILE}"
    printf '%s\n' "${watcher_output}"
    exit 0
    ;;
  20)
    echo "SI_V2_T4_WATCHER_ALERT=SAFETY_BLOCKED"
    echo "LOG_FILE=${LOG_FILE}"
    printf '%s\n' "${watcher_output}"
    exit 20
    ;;
  30)
    echo "SI_V2_T4_WATCHER_ALERT=DATA_UNAVAILABLE"
    echo "LOG_FILE=${LOG_FILE}"
    printf '%s\n' "${watcher_output}"
    exit 30
    ;;
  40)
    echo "SI_V2_T4_WATCHER_ALERT=SCRIPT_ERROR"
    echo "LOG_FILE=${LOG_FILE}"
    printf '%s\n' "${watcher_output}"
    exit 40
    ;;
  *)
    echo "SI_V2_T4_WATCHER_ALERT=SCRIPT_ERROR"
    echo "ERROR=unexpected_exit_code:${watcher_rc}"
    echo "LOG_FILE=${LOG_FILE}"
    printf '%s\n' "${watcher_output}"
    exit 40
    ;;
esac
