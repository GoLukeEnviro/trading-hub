#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${SI_V2_T4_REPO_ROOT:-/home/hermes/projects/trading}"
WATCHER_CMD="${SI_V2_T4_WATCHER_CMD:-/opt/data/profiles/orchestrator/scripts/si_v2_t4_measurement_watcher.sh}"
LOG_DIR="${SI_V2_T4_LOG_DIR:-/opt/data/logs/si-v2-t4-watcher}"
RUN_DIR="${LOG_DIR}/runs"
ALERT_DIR="${LOG_DIR}/alerts"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_LOG="${RUN_DIR}/t4-watcher-${TS}.log"
CRON_LOG="${LOG_DIR}/cron.log"

mkdir -p "${RUN_DIR}" "${ALERT_DIR}"

TMP_OUTPUT="$(mktemp)"
cleanup() {
  rm -f "${TMP_OUTPUT}"
}
trap cleanup EXIT

log_line() {
  printf '[%s] %s\n' "${TS}" "$1" >> "${CRON_LOG}"
}

set +e
SI_V2_REPO_ROOT="${REPO_ROOT}" bash "${WATCHER_CMD}" >"${TMP_OUTPUT}" 2>&1
WATCHER_RC=$?
set -e

WATCHER_OUTPUT="$(cat "${TMP_OUTPUT}")"
STATUS="$(awk -F= '/^SI_V2_T4_STATUS=/{print $2; exit}' "${TMP_OUTPUT}" || true)"
NEXT_STEP="$(awk -F= '/^NEXT_STEP=/{print $2; exit}' "${TMP_OUTPUT}" || true)"

{
  printf 'timestamp_utc=%s\n' "${TS}"
  printf 'watcher_cmd=%s\n' "${WATCHER_CMD}"
  printf 'repo_root=%s\n' "${REPO_ROOT}"
  printf 'watcher_rc=%s\n' "${WATCHER_RC}"
  printf 'status=%s\n' "${STATUS:-UNKNOWN}"
  printf 'next_step=%s\n' "${NEXT_STEP:-unknown}"
  printf '\n'
  printf '%s\n' "${WATCHER_OUTPUT}"
} > "${RUN_LOG}"

write_alert() {
  local alert_name="$1"
  local normalized
  normalized="$(printf '%s' "${alert_name}" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')"
  local alert_file="${ALERT_DIR}/${normalized}-${TS}.log"
  {
    printf 'alert_type=%s\n' "${alert_name}"
    printf 'run_log=%s\n' "${RUN_LOG}"
    printf '\n'
    printf '%s\n' "${WATCHER_OUTPUT}"
  } > "${alert_file}"
  printf '%s' "${alert_file}"
}

case "${WATCHER_RC}" in
  0)
    log_line "status=${STATUS:-STILL_WAITING} next_step=${NEXT_STEP:-wait_for_canary_close} run_log=${RUN_LOG}"
    exit 0
    ;;
  10)
    ALERT_FILE="$(write_alert "MEASUREMENT_READY")"
    log_line "status=MEASUREMENT_READY next_step=${NEXT_STEP:-run_measurement_decision_engine_read_only} alert_file=${ALERT_FILE} run_log=${RUN_LOG}"
    printf 'SI_V2_T4_ALERT=MEASUREMENT_READY\nALERT_FILE=%s\nRUN_LOG=%s\n%s\n' "${ALERT_FILE}" "${RUN_LOG}" "${WATCHER_OUTPUT}"
    exit 0
    ;;
  20)
    ALERT_FILE="$(write_alert "SAFETY_BLOCKED")"
    log_line "status=SAFETY_BLOCKED next_step=${NEXT_STEP:-investigate_guardrails} alert_file=${ALERT_FILE} run_log=${RUN_LOG}"
    printf 'SI_V2_T4_ALERT=SAFETY_BLOCKED\nALERT_FILE=%s\nRUN_LOG=%s\n%s\n' "${ALERT_FILE}" "${RUN_LOG}" "${WATCHER_OUTPUT}"
    exit 1
    ;;
  30)
    ALERT_FILE="$(write_alert "DATA_UNAVAILABLE")"
    log_line "status=DATA_UNAVAILABLE next_step=${NEXT_STEP:-inspect_data_sources} alert_file=${ALERT_FILE} run_log=${RUN_LOG}"
    printf 'SI_V2_T4_ALERT=DATA_UNAVAILABLE\nALERT_FILE=%s\nRUN_LOG=%s\n%s\n' "${ALERT_FILE}" "${RUN_LOG}" "${WATCHER_OUTPUT}"
    exit 1
    ;;
  40)
    ALERT_FILE="$(write_alert "SCRIPT_ERROR")"
    log_line "status=SCRIPT_ERROR next_step=${NEXT_STEP:-inspect_wrapper_and_watcher} alert_file=${ALERT_FILE} run_log=${RUN_LOG}"
    printf 'SI_V2_T4_ALERT=SCRIPT_ERROR\nALERT_FILE=%s\nRUN_LOG=%s\n%s\n' "${ALERT_FILE}" "${RUN_LOG}" "${WATCHER_OUTPUT}"
    exit 1
    ;;
  *)
    ALERT_FILE="$(write_alert "UNEXPECTED_EXIT")"
    log_line "status=UNEXPECTED_EXIT watcher_rc=${WATCHER_RC} alert_file=${ALERT_FILE} run_log=${RUN_LOG}"
    printf 'SI_V2_T4_ALERT=UNEXPECTED_EXIT\nALERT_FILE=%s\nRUN_LOG=%s\nWATCHER_RC=%s\n%s\n' "${ALERT_FILE}" "${RUN_LOG}" "${WATCHER_RC}" "${WATCHER_OUTPUT}"
    exit 1
    ;;
esac
