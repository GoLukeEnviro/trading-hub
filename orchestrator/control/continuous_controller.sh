#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="${SI_V2_CONTROLLER_ENV:-/opt/data/si-v2-controller/controller.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Controller environment file not found: $ENV_FILE" >&2
  exit 20
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

: "${AGENT_COMMAND:?AGENT_COMMAND is required}"
: "${REPO_ROOT:?REPO_ROOT is required}"
: "${CONTROL_ROOT:?CONTROL_ROOT is required}"
: "${LOG_ROOT:?LOG_ROOT is required}"
: "${LOCK_FILE:?LOCK_FILE is required}"
: "${RUN_TIMEOUT_SECONDS:=5400}"

mkdir -p "$LOG_ROOT" "$(dirname "$LOCK_FILE")"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another controller run is active; exiting safely."
  exit 0
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
log_file="$LOG_ROOT/controller-$timestamp.log"

{
  echo "run_started_at=$timestamp"
  echo "repo_root=$REPO_ROOT"
  echo "control_root=$CONTROL_ROOT"

  cd "$REPO_ROOT"

  python3 "$CONTROL_ROOT/scripts/validate_control_plane.py" \
    --control-root "$CONTROL_ROOT"

  controller_status="$(
    python3 - "$CONTROL_ROOT/STATE.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    state = json.load(handle)

print(state["controller_status"])
PY
  )"

  case "$controller_status" in
    PAUSED|BLOCKED|COMPLETE)
      echo "controller_status=$controller_status; no agent invocation"
      exit 0
      ;;
    READY|RUNNING)
      ;;
    *)
      echo "Unsupported controller status: $controller_status" >&2
      exit 22
      ;;
  esac

  if [[ ! -f "$CONTROL_ROOT/MASTER_AGENT_PROMPT.xml" ]]; then
    echo "Missing master controller prompt." >&2
    exit 21
  fi

  timeout --signal=TERM --kill-after=30s \
    "$RUN_TIMEOUT_SECONDS" \
    bash -lc "$AGENT_COMMAND"

  python3 "$CONTROL_ROOT/scripts/validate_control_plane.py" \
    --control-root "$CONTROL_ROOT"

  echo "run_finished_at=$(date -u +%Y%m%dT%H%M%SZ)"
} >>"$log_file" 2>&1
