#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="${SI_V2_CONTROLLER_ENV:-/opt/data/si-v2-controller/controller.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Controller environment file not found: $ENV_FILE" >&2
  exit 20
fi

# Export all variables to subprocesses automatically.
# The AGENT_COMMAND runs via `bash -lc` which is a login shell and does not
# inherit non-exported shell variables. Using set -a / set +a ensures every
# variable in controller.env is exported to child processes without requiring
# explicit `export` prefixes on individual lines.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${AGENT_COMMAND:?AGENT_COMMAND is required}"
: "${REPO_ROOT:?REPO_ROOT is required}"
: "${CONTROL_ROOT:?CONTROL_ROOT is required}"
: "${LOG_ROOT:?LOG_ROOT is required}"
: "${LOCK_FILE:?LOCK_FILE is required}"
: "${RUN_TIMEOUT_SECONDS:=5400}"

# SI_V2_STATE_ROOT is mandatory for scheduled/continuous execution.
# Mutable state (STATE.json, QUEUE.json, HANDOFF.md, run logs) must never
# silently fall back to repository paths. The backward-compat default
# STATE_ROOT="${SI_V2_STATE_ROOT:-$CONTROL_ROOT}" is removed.
: "${SI_V2_STATE_ROOT:?SI_V2_STATE_ROOT is required for scheduled controller execution}"

# Separate config (immutable, in repo) from state (mutable, external).
# CONFIG_ROOT: repo path to orchestrator/control/ (schemas, scripts, prompts)
# STATE_ROOT:  external path for mutable runtime state (STATE.json, QUEUE.json, HANDOFF.md)
CONFIG_ROOT="${SI_V2_CONFIG_ROOT:-$CONTROL_ROOT}"
STATE_ROOT="${SI_V2_STATE_ROOT}"

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
  echo "config_root=$CONFIG_ROOT"
  echo "state_root=$STATE_ROOT"

  cd "$REPO_ROOT"

  # Pre-run validation: check config AND state
  python3 "$CONFIG_ROOT/scripts/validate_control_plane.py" \
    --config-root "$CONFIG_ROOT" \
    --state-root "$STATE_ROOT"

  controller_status="$(
    python3 - "$STATE_ROOT/STATE.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    state = json.load(handle)

print(state["controller_status"])
PY
  )"

  case "$controller_status" in
    # NON-INVOCATION states: skip agent, exit cleanly.
    # The canonical set is PAUSED, BLOCKED, COMPLETE, FAILED.
    # Schema parity: every schema-valid controller_status has an explicit
    # runner branch.  No status falls through to the default error case.
    PAUSED|BLOCKED|COMPLETE|FAILED)
      echo "controller_status=$controller_status; no agent invocation (non-invocation state)"
      exit 0
      ;;
    # INVOCATION states: proceed to AGENT_COMMAND.
    READY|RUNNING)
      ;;
    *)
      echo "Unsupported controller status: $controller_status" >&2
      exit 22
      ;;
  esac

  if [[ ! -f "$CONFIG_ROOT/MASTER_AGENT_PROMPT.xml" ]]; then
    echo "Missing master controller prompt." >&2
    exit 21
  fi

  # ── AGENT INVOCATION WITH FAIL-CLOSED HANDLING ──────────────────────
  # set -e is disabled during the agent call so we can capture the exit code
  # and run deterministic failure recovery.  Post-failure, STATE.json is
  # updated atomically before the script returns.
  agent_exit_code=0
  set +e
  timeout --signal=TERM --kill-after=30s \
    "$RUN_TIMEOUT_SECONDS" \
    bash -lc "$AGENT_COMMAND"
  agent_exit_code=$?
  set -e

  if [[ $agent_exit_code -ne 0 ]]; then
    echo "AGENT_COMMAND exited with code $agent_exit_code; entering fail-closed recovery" >&2

    # Determine failure reason
    if [[ $agent_exit_code -eq 124 ]]; then
      reason="timeout after ${RUN_TIMEOUT_SECONDS}s"
    else
      reason="agent exit code $agent_exit_code"
    fi

    # Atomically update STATE.json to BLOCKED.
    # Uses tempfile + os.replace() so the file is never partially written.
    python3 - "$STATE_ROOT/STATE.json" "$reason" <<'PY'
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

state_path = sys.argv[1]
reason = sys.argv[2]

with open(state_path, "r", encoding="utf-8") as handle:
    state = json.load(handle)

state["controller_status"] = "BLOCKED"
state["pause_reason"] = reason
state["last_run_status"] = "FAILED"
state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
state["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Atomic write: temp file + rename
tmp_fd, tmp_path = tempfile.mkstemp(
    dir=os.path.dirname(state_path), suffix=".tmp"
)
try:
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    os.replace(tmp_path, state_path)
finally:
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
PY

    echo "Controller transitioned to BLOCKED ($reason)"
  fi

  # Post-run validation ALWAYS runs — even after agent failure.
  python3 "$CONFIG_ROOT/scripts/validate_control_plane.py" \
    --config-root "$CONFIG_ROOT" \
    --state-root "$STATE_ROOT"

  echo "run_finished_at=$(date -u +%Y%m%dT%H%M%SZ)"
} >>"$log_file" 2>&1

# Propagate agent exit code to the scheduler.
# Non-invocation states exit 0 before reaching this line.
exit $agent_exit_code
