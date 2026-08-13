#!/usr/bin/env bash
# hermes-native-change-c.sh -- host-native Hermes agent upgrade 0.19.0 -> 0.20.0
#
# Change C replaces the retired PyPI-wheel install path (hermes-agent has not
# been published to PyPI since 0.19.0) with a minimal, auditable install
# built directly in this script: `git clone --depth 1 --branch <tag>` of the
# pinned upstream release, a `uv venv`, and an editable `uv pip install -e`.
# We deliberately do NOT download or wrap the upstream scripts/install.sh --
# see "Known upstream discrepancy" below.
#
# Layout on disk (side-by-side releases, `current` symlink):
#   /opt/hermes-native/releases/0.19.0/   <- never touched by this script
#   /opt/hermes-native/releases/0.20.0/   <- created by `stage`
#     source/                 git clone of the pinned tag/sha
#     venv/                   uv venv, editable install of ../source
#     bin/hermes              wrapper -> venv/bin/hermes (see build_hermes_wrapper)
#     RELEASE-MANIFEST.json   version/tag/sha/staged_at/staged_by/source_commit_verified
#   /opt/hermes-native/current -> releases/<active version>
#
# Subcommands: plan | stage | pre-cutover | cutover | validate | rollback | report
# Run with no arguments (or --help) for usage.
#
# Known upstream discrepancy (documented, not ours to fix): the upstream
# NousResearch/hermes-agent scripts/install.sh defines NODE_VERSION="22" as
# its pinned constant, but a log line in the very same script tells the
# operator that Node ">=26" is required. We never invoke that script, so the
# discrepancy cannot bite us here -- it is recorded purely so a human
# reviewing this script does not go looking for a resolution we cannot
# provide from the trading-hub side.
#
# Explicitly out of scope (never touched by any subcommand in this script):
#   - The dry-run trading fleet (5 Docker containers): never started, never
#     stopped, never rebuilt. `validate` only asserts its state is unchanged.
#   - hermes-root-executor.service: never stopped, started, restarted, or
#     redeployed, directly or indirectly.
#   - Freqtrade configs, strategy logic, secrets, cron, Docker Compose files.
#   - Creating the backup this script's pre-cutover gate requires proof of.
#
# Safety contract highlights (see individual functions for detail):
#   - set -Eeuo pipefail, flock-serialized against concurrent runs.
#   - `plan` and any subcommand invoked with --dry-run never mutate anything.
#   - `stage` only ever writes releases/0.20.0; `current` and releases/0.19.0
#     are never opened for writing by this script under any subcommand.
#   - Every mutating step is preceded/followed by a JSON audit event.
#   - dry_run=false found anywhere this script reads is an immediate,
#     unconditional, non-continuable abort (DRY_RUN_FALSE_DETECTED).
#   - rollback's target is read from a manifest written by pre-cutover; it is
#     never guessed, and rollback hard-aborts if that manifest is absent.

set -Eeuo pipefail

# ---------------------------------------------------------------------------
# Pinned release identity. These are the production defaults and are what
# ships in this file. The HERMES_NATIVE_CHANGE_C_TEST_* overrides exist
# solely so the test suite can exercise `stage` end-to-end against a local
# git fixture instead of the network -- they are deliberately, distinctly
# named so nobody mistakes them for an operator-facing knob. Unset (the
# normal case, including every production run), the readonly values below
# are exactly the ones hard-coded here.
# ---------------------------------------------------------------------------
readonly HERMES_TARGET_VERSION="${HERMES_NATIVE_CHANGE_C_TEST_TARGET_VERSION:-0.20.0}"
readonly HERMES_TARGET_TAG="${HERMES_NATIVE_CHANGE_C_TEST_TARGET_TAG:-v2026.8.3}"
readonly HERMES_TARGET_SHA="${HERMES_NATIVE_CHANGE_C_TEST_TARGET_SHA:-3c27eb6234bf91b8ceee9e9071591b31e9b148cb}"
readonly HERMES_SOURCE_VERSION="0.19.0"
readonly HERMES_UPSTREAM_REPO="${HERMES_NATIVE_CHANGE_C_TEST_UPSTREAM_REPO:-https://github.com/NousResearch/hermes-agent.git}"

# Upstream's own pyproject.toml pins `requires-python = ">=3.11,<3.14"` and
# says why in a comment: the upper bound is load-bearing, not cosmetic --
# an inherited `UV_PYTHON` env var (or a fresh distro whose newest
# interpreter `uv` auto-picks) can otherwise select 3.14, where Rust-backed
# transitives (e.g. pydantic-core) have no cp314 wheel yet and fall back to
# a maturin source build that fails. We pin explicitly rather than relying
# on pyproject.toml's bound being honored before `uv` has even read it.
readonly HERMES_VENV_PYTHON="${HERMES_NATIVE_CHANGE_C_TEST_VENV_PYTHON:-3.13}"

# ---------------------------------------------------------------------------
# Filesystem / state layout. All overridable for tests; production defaults
# match the real HermesTrader host (docs/state/current-operational-state.md).
# ---------------------------------------------------------------------------
readonly HERMES_NATIVE_ROOT="${HERMES_NATIVE_ROOT:-/opt/hermes-native}"
readonly HERMES_NATIVE_STATE_DIR="${HERMES_NATIVE_STATE_DIR:-/var/lib/hermes-native-change-c}"
readonly HERMES_NATIVE_LOCK_FILE="${HERMES_NATIVE_LOCK_FILE:-/run/hermes-native-change-c.lock}"
readonly HERMES_NATIVE_AUDIT_LOG="${HERMES_NATIVE_AUDIT_LOG:-${HERMES_NATIVE_STATE_DIR}/audit.jsonl}"
readonly HERMES_NATIVE_PRECUTOVER_MANIFEST="${HERMES_NATIVE_PRECUTOVER_MANIFEST:-${HERMES_NATIVE_STATE_DIR}/pre-cutover-manifest.json}"
readonly HERMES_NATIVE_BACKUP_PROOF="${HERMES_NATIVE_BACKUP_PROOF:-${HERMES_NATIVE_STATE_DIR}/backup-proof.json}"
readonly HERMES_NATIVE_FLEET_BASELINE="${HERMES_NATIVE_FLEET_BASELINE:-${HERMES_NATIVE_STATE_DIR}/fleet-baseline-pre-cutover.json}"
readonly HERMES_NATIVE_REPORT_DIR="${HERMES_NATIVE_REPORT_DIR:-${HERMES_NATIVE_STATE_DIR}/reports}"

# Best-effort diagnostic targets. Real paths on the production host are not
# fully documented anywhere this script can source without guessing; these
# defaults are reasonable and every one is operator-overridable without a
# code change. See README note in `validate` for the exact behavior when a
# path does not exist.
readonly HERMES_NATIVE_HERMES_HOME="${HERMES_NATIVE_HERMES_HOME:-/home/hermes/.hermes}"
readonly HERMES_NATIVE_STATE_DB="${HERMES_NATIVE_STATE_DB:-${HERMES_NATIVE_HERMES_HOME}/state.db}"
readonly HERMES_NATIVE_ROOT_EXECUTOR_SOCKET="${HERMES_NATIVE_ROOT_EXECUTOR_SOCKET:-/run/hermes-root-executor/executor.sock}"
# Space-separated list of ports that must never LISTEN on a public address
# (0.0.0.0 / ::). Defaults to the documented dashboard port (127.0.0.1:9119
# only). Empty disables the check with a WARN, never a silent pass-as-skip.
readonly HERMES_NATIVE_PUBLIC_BIND_CHECK_PORTS="${HERMES_NATIVE_PUBLIC_BIND_CHECK_PORTS:-9119}"

readonly RELEASES_DIR="${HERMES_NATIVE_ROOT}/releases"
readonly CURRENT_SYMLINK="${HERMES_NATIVE_ROOT}/current"
readonly TARGET_RELEASE_DIR="${RELEASES_DIR}/${HERMES_TARGET_VERSION}"
readonly SOURCE_RELEASE_DIR="${RELEASES_DIR}/${HERMES_SOURCE_VERSION}"

# systemd units, in the mandated order. hermes-root-executor.service is
# intentionally absent from both arrays; assert_not_root_executor() is a
# second, independent guard against ever touching it.
readonly SVC_GATEWAY="hermes-gateway.service"
readonly SVC_DASHBOARD="hermes-dashboard.service"
readonly SVC_DESKTOP_SERVE="hermes-desktop-serve.service"
readonly -a STOP_ORDER=("${SVC_DESKTOP_SERVE}" "${SVC_DASHBOARD}" "${SVC_GATEWAY}")
readonly -a START_ORDER=("${SVC_GATEWAY}" "${SVC_DASHBOARD}" "${SVC_DESKTOP_SERVE}")

DRY_RUN=false

# ---------------------------------------------------------------------------
# Logging / audit / secret redaction
# ---------------------------------------------------------------------------

log() {
  printf '[hermes-native-change-c] %s\n' "$*" >&2
}

# Redacts KEY=VALUE (optionally `export KEY=VALUE`) assignments whose key
# contains TOKEN, SECRET, PASSWORD, PASS, API_KEY, or PRIVATE_KEY, replacing
# only the value. Used on every code path that echoes file content this
# script did not itself author (backup-proof files, .env snapshots).
redact_secrets() {
  # Deliberately `python3 -c '...'`, NOT `python3 - <<'PY'`: the latter's
  # heredoc supplies python's own *program source* via stdin (that is what
  # the bare `-` argument means), which fully consumes stdin before the
  # program body ever runs -- any `< file` or piped data a caller attaches
  # to this function is then invisible to sys.stdin.read(). `-c` keeps the
  # program on the command line and leaves stdin free for the real data.
  python3 -c '
import re
import sys

pattern = re.compile(
    r"(?im)^(\s*(?:export\s+)?[A-Za-z0-9_]*"
    r"(?:TOKEN|SECRET|PASSWORD|PASS|API_KEY|PRIVATE_KEY)"
    r"[A-Za-z0-9_]*\s*=\s*)\S*"
)
sys.stdout.write(pattern.sub(r"\1<REDACTED>", sys.stdin.read()))
'
}

json_escape() {
  python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$1"
}

audit_event() {
  local step="$1" result="$2"
  mkdir -p "$(dirname "${HERMES_NATIVE_AUDIT_LOG}")"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '{"timestamp":%s,"step":%s,"result":%s}\n' \
    "$(json_escape "${ts}")" "$(json_escape "${step}")" "$(json_escape "${result}")" \
    >> "${HERMES_NATIVE_AUDIT_LOG}"
}

fatal() {
  local code="$1"; shift
  local msg="$*"
  log "FATAL ${code}: ${msg}"
  audit_event "fatal" "${code}"
  exit 1
}

# Immediate, unconditional, non-continuable abort if the given text contains
# a dry_run=false (or JSON "dry_run": false) assignment in any shape. Called
# on every piece of external file content this script reads, in every mode.
guard_dry_run_false() {
  local text="$1"
  if printf '%s' "${text}" | grep -Eiq '"?dry_run"?[[:space:]]*[:=][[:space:]]*false\b'; then
    fatal DRY_RUN_FALSE_DETECTED "dry_run=false found in scanned input -- refusing to continue in any mode"
  fi
}

# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------

acquire_lock() {
  mkdir -p "$(dirname "${HERMES_NATIVE_LOCK_FILE}")"
  exec 9>"${HERMES_NATIVE_LOCK_FILE}"
  if ! flock -n 9; then
    fatal MIGRATION_ALREADY_RUNNING "another hermes-native-change-c run holds ${HERMES_NATIVE_LOCK_FILE}"
  fi
}

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

assert_not_root_executor() {
  if [[ "$1" == "hermes-root-executor.service" ]]; then
    fatal INTERNAL_GUARD_VIOLATION "refusing to touch hermes-root-executor.service"
  fi
}

resolved_current_target() {
  # Prints the resolved absolute path `current` points at, or empty if the
  # symlink is absent.
  if [[ -L "${CURRENT_SYMLINK}" ]]; then
    readlink -f "${CURRENT_SYMLINK}" 2>/dev/null || true
  fi
}

release_manifest_path() {
  printf '%s/RELEASE-MANIFEST.json' "$1"
}

# Returns 0 and prints nothing if the manifest at $1 is well-formed AND
# matches the currently-pinned target version/tag/sha; returns 1 otherwise.
release_manifest_matches_target() {
  local manifest="$1"
  [[ -f "${manifest}" ]] || return 1
  python3 - "${manifest}" "${HERMES_TARGET_VERSION}" "${HERMES_TARGET_TAG}" "${HERMES_TARGET_SHA}" <<'PY'
import json
import sys

manifest_path, version, tag, sha = sys.argv[1:5]
try:
    with open(manifest_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
except (OSError, json.JSONDecodeError):
    sys.exit(1)
ok = (
    data.get("version") == version
    and data.get("tag") == tag
    and data.get("sha") == sha
    and data.get("source_commit_verified") is True
)
sys.exit(0 if ok else 1)
PY
}

# ---------------------------------------------------------------------------
# Fleet baseline capture (read-only w.r.t. the fleet: no start/stop/build)
# ---------------------------------------------------------------------------

capture_fleet_state_json() {
  local captured_at
  captured_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if command -v docker >/dev/null 2>&1; then
    local raw
    raw="$(docker ps -a --format '{{.Names}}|{{.Status}}' 2>/dev/null | LC_ALL=C sort || true)"
    guard_dry_run_false "${raw}"
    python3 - "${captured_at}" "${raw}" <<'PY'
import json
import sys

captured_at, raw = sys.argv[1], sys.argv[2]
containers = []
for line in raw.splitlines():
    if not line.strip():
        continue
    name, _, status = line.partition("|")
    containers.append({"name": name, "status": status})
print(json.dumps({"captured_at": captured_at, "docker_available": True, "containers": containers}, sort_keys=True))
PY
  else
    python3 -c "import json,sys; print(json.dumps({'captured_at': sys.argv[1], 'docker_available': False, 'containers': []}))" "${captured_at}"
  fi
}

# ---------------------------------------------------------------------------
# plan (read-only; never called with mutating side effects)
# ---------------------------------------------------------------------------

cmd_plan() {
  local current_target
  current_target="$(resolved_current_target)"

  echo "=== hermes-native-change-c: PLAN (no mutation performed) ==="
  echo "target version/tag/sha : ${HERMES_TARGET_VERSION} / ${HERMES_TARGET_TAG} / ${HERMES_TARGET_SHA}"
  echo "hermes-native root     : ${HERMES_NATIVE_ROOT}"
  echo "current -> $( [[ -n "${current_target}" ]] && echo "${current_target}" || echo "(no symlink present)" )"
  echo "target release dir     : ${TARGET_RELEASE_DIR} $( [[ -e "${TARGET_RELEASE_DIR}" ]] && echo "(exists)" || echo "(would be created by stage)" )"
  echo "source release dir     : ${SOURCE_RELEASE_DIR} (never touched by this script)"
  echo "stop order (cutover)   : ${STOP_ORDER[*]}"
  echo "start order (cutover)  : ${START_ORDER[*]}"
  echo "lock file               : ${HERMES_NATIVE_LOCK_FILE}"
  echo "state dir               : ${HERMES_NATIVE_STATE_DIR}"
  echo "pre-cutover manifest    : ${HERMES_NATIVE_PRECUTOVER_MANIFEST} $( [[ -f "${HERMES_NATIVE_PRECUTOVER_MANIFEST}" ]] && echo "(present)" || echo "(absent)" )"
  echo "backup proof            : ${HERMES_NATIVE_BACKUP_PROOF} $( [[ -f "${HERMES_NATIVE_BACKUP_PROOF}" ]] && echo "(present)" || echo "(absent)" )"
  if command -v systemctl >/dev/null 2>&1; then
    local svc
    for svc in "${START_ORDER[@]}"; do
      echo "service ${svc}: $(systemctl is-active "${svc}" 2>/dev/null || echo "unknown")"
    done
  fi
  echo "known upstream discrepancy: ${HERMES_UPSTREAM_REPO} scripts/install.sh NODE_VERSION=22 vs logged floor >=26 (documented, not resolved here)"
  echo "=== end plan ==="
}

# ---------------------------------------------------------------------------
# stage
# ---------------------------------------------------------------------------

build_hermes_wrapper() {
  local release_dir="$1"
  local wrapper="${release_dir}/bin/hermes"
  mkdir -p "${release_dir}/bin"
  cat > "${wrapper}" <<'WRAPPER'
#!/usr/bin/env bash
# Generated by hermes-native-change-c.sh. Deterministic PATH wiring only:
# does not set/override HERMES_HOME, does not log environment values, and
# forwards all arguments unchanged.
set -euo pipefail
RELEASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_BIN="${RELEASE_DIR}/venv/bin"
MANAGED_NODE_BIN="${RELEASE_DIR}/node/bin"
if [[ -d "${MANAGED_NODE_BIN}" ]]; then
  PATH="${MANAGED_NODE_BIN}:${VENV_BIN}:${PATH}"
else
  PATH="${VENV_BIN}:${PATH}"
fi
export PATH
exec "${VENV_BIN}/hermes" "$@"
WRAPPER
  chmod 0755 "${wrapper}"
}

write_release_manifest() {
  local release_dir="$1"
  python3 - "${release_dir}" "${HERMES_TARGET_VERSION}" "${HERMES_TARGET_TAG}" "${HERMES_TARGET_SHA}" "$(whoami)" <<'PY'
import json
import sys
from datetime import datetime, timezone

release_dir, version, tag, sha, staged_by = sys.argv[1:6]
manifest = {
    "version": version,
    "tag": tag,
    "sha": sha,
    "staged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "staged_by": staged_by,
    "source_commit_verified": True,
}
with open(f"{release_dir}/RELEASE-MANIFEST.json", "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY
}

cmd_stage() {
  acquire_lock

  if [[ -e "${TARGET_RELEASE_DIR}" ]]; then
    if release_manifest_matches_target "$(release_manifest_path "${TARGET_RELEASE_DIR}")"; then
      log "releases/${HERMES_TARGET_VERSION} already staged with a matching manifest -- nothing to do"
      audit_event "stage" "already_staged"
      return 0
    fi
    fatal TARGET_RELEASE_PATH_EXISTS "${TARGET_RELEASE_DIR} already exists and its manifest does not match the pinned target; refusing to clobber"
  fi

  audit_event "stage" "start"
  mkdir -p "${RELEASES_DIR}"

  local created_target_dir=false
  cleanup_on_failure() {
    if [[ "${created_target_dir}" == "true" && -d "${TARGET_RELEASE_DIR}" ]]; then
      log "cleaning up incomplete stage at ${TARGET_RELEASE_DIR}"
      rm -rf "${TARGET_RELEASE_DIR}"
    fi
  }
  trap cleanup_on_failure ERR

  mkdir -p "${TARGET_RELEASE_DIR}"
  created_target_dir=true

  log "cloning ${HERMES_UPSTREAM_REPO} @ ${HERMES_TARGET_TAG} into ${TARGET_RELEASE_DIR}/source"
  audit_event "stage:git_clone" "start"
  git clone --depth 1 --branch "${HERMES_TARGET_TAG}" "${HERMES_UPSTREAM_REPO}" "${TARGET_RELEASE_DIR}/source" >&2
  audit_event "stage:git_clone" "success"

  local actual_sha
  actual_sha="$(git -C "${TARGET_RELEASE_DIR}/source" rev-parse HEAD)"
  if [[ "${actual_sha}" != "${HERMES_TARGET_SHA}" ]]; then
    audit_event "stage:verify_sha" "mismatch"
    # Explicit cleanup here rather than relying on the ERR trap: `fatal`
    # terminates via the `exit` builtin, and whether a bare `exit` inside a
    # called function re-triggers the caller's ERR trap is not something to
    # depend on. Clean up deterministically, then report the failure.
    rm -rf "${TARGET_RELEASE_DIR}"
    trap - ERR
    fatal TARGET_SHA_MISMATCH "cloned HEAD ${actual_sha} does not match pinned HERMES_TARGET_SHA ${HERMES_TARGET_SHA}"
  fi
  audit_event "stage:verify_sha" "success"

  log "creating venv at ${TARGET_RELEASE_DIR}/venv (python ${HERMES_VENV_PYTHON})"
  audit_event "stage:uv_venv" "start"
  # Explicit --python pin (see HERMES_VENV_PYTHON comment above): never let
  # an inherited UV_PYTHON or uv's own newest-interpreter default decide.
  UV_PYTHON="${HERMES_VENV_PYTHON}" uv venv --python "${HERMES_VENV_PYTHON}" "${TARGET_RELEASE_DIR}/venv" >&2
  audit_event "stage:uv_venv" "success"

  log "editable install: uv pip install -e '.[all]'"
  audit_event "stage:uv_pip_install" "start"
  ( cd "${TARGET_RELEASE_DIR}/source" && uv pip install --python "${TARGET_RELEASE_DIR}/venv/bin/python" -e '.[all]' >&2 )
  audit_event "stage:uv_pip_install" "success"

  build_hermes_wrapper "${TARGET_RELEASE_DIR}"
  audit_event "stage:build_wrapper" "success"

  write_release_manifest "${TARGET_RELEASE_DIR}"
  audit_event "stage:write_manifest" "success"

  trap - ERR
  audit_event "stage" "success"
  log "stage complete: ${TARGET_RELEASE_DIR} (current still points at ${HERMES_SOURCE_VERSION})"
}

# ---------------------------------------------------------------------------
# pre-cutover
# ---------------------------------------------------------------------------

write_precutover_manifest() {
  local previous_target="$1"
  python3 - "${HERMES_NATIVE_PRECUTOVER_MANIFEST}" "${previous_target}" "${HERMES_SOURCE_VERSION}" \
    "${HERMES_TARGET_VERSION}" "${HERMES_TARGET_SHA}" "$(whoami)" \
    "${HERMES_NATIVE_BACKUP_PROOF}" "${HERMES_NATIVE_FLEET_BASELINE}" <<'PY'
import json
import sys
from datetime import datetime, timezone

(manifest_path, previous_target, previous_version, target_version,
 target_sha, operator, backup_proof_ref, fleet_baseline_ref) = sys.argv[1:9]
manifest = {
    "previous_symlink_target": previous_target,
    "previous_version": previous_version,
    "target_version": target_version,
    "target_sha": target_sha,
    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "gates_passed": True,
    "operator": operator,
    "backup_proof_ref": backup_proof_ref,
    "fleet_baseline_ref": fleet_baseline_ref,
}
with open(manifest_path, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY
}

cmd_pre_cutover() {
  acquire_lock
  audit_event "pre-cutover" "start"

  # Gate 1: backup proof.
  if [[ ! -f "${HERMES_NATIVE_BACKUP_PROOF}" ]]; then
    audit_event "pre-cutover:backup_gate" "failed"
    fatal BACKUP_PROOF_MISSING "no backup proof at ${HERMES_NATIVE_BACKUP_PROOF}; this script never creates the backup itself, it only requires proof of one"
  fi
  local backup_proof_content
  backup_proof_content="$(cat "${HERMES_NATIVE_BACKUP_PROOF}")"
  guard_dry_run_false "${backup_proof_content}"
  if ! python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get('verified') is True else 1)" "${HERMES_NATIVE_BACKUP_PROOF}" 2>/dev/null; then
    audit_event "pre-cutover:backup_gate" "failed"
    fatal BACKUP_PROOF_MISSING "backup proof at ${HERMES_NATIVE_BACKUP_PROOF} does not have verified=true"
  fi
  audit_event "pre-cutover:backup_gate" "success"

  # Gate 2: target release staged with a verified matching manifest.
  if ! release_manifest_matches_target "$(release_manifest_path "${TARGET_RELEASE_DIR}")"; then
    audit_event "pre-cutover:staged_release_gate" "failed"
    fatal TARGET_RELEASE_NOT_STAGED "no verified RELEASE-MANIFEST.json for ${HERMES_TARGET_VERSION} at ${TARGET_RELEASE_DIR}; run stage first"
  fi
  audit_event "pre-cutover:staged_release_gate" "success"

  # Capture current symlink target for the rollback contract.
  local previous_target
  previous_target="$(resolved_current_target)"
  if [[ -z "${previous_target}" ]]; then
    audit_event "pre-cutover:symlink_gate" "failed"
    fatal ACTIVE_SYMLINK_MISSING "${CURRENT_SYMLINK} does not exist or is not a symlink; refusing to plan a cutover with no known previous state"
  fi

  # Capture fleet baseline (read-only; stopped fleet is not an error).
  mkdir -p "${HERMES_NATIVE_STATE_DIR}"
  local fleet_json
  fleet_json="$(capture_fleet_state_json)"
  printf '%s\n' "${fleet_json}" > "${HERMES_NATIVE_FLEET_BASELINE}"
  audit_event "pre-cutover:fleet_baseline_capture" "success"

  write_precutover_manifest "${previous_target}"
  audit_event "pre-cutover" "success"
  log "pre-cutover gates passed; manifest written to ${HERMES_NATIVE_PRECUTOVER_MANIFEST}"
}

# ---------------------------------------------------------------------------
# cutover / rollback shared service + symlink primitives
# ---------------------------------------------------------------------------

stop_services_in_order() {
  local svc
  for svc in "${STOP_ORDER[@]}"; do
    assert_not_root_executor "${svc}"
    audit_event "stop_service:${svc}" "start"
    if systemctl stop "${svc}"; then
      audit_event "stop_service:${svc}" "success"
    else
      audit_event "stop_service:${svc}" "failure"
      fatal SERVICE_STOP_FAILED "systemctl stop ${svc} failed"
    fi
  done
}

start_services_in_order() {
  local svc
  for svc in "${START_ORDER[@]}"; do
    assert_not_root_executor "${svc}"
    audit_event "start_service:${svc}" "start"
    if systemctl start "${svc}"; then
      audit_event "start_service:${svc}" "success"
    else
      audit_event "start_service:${svc}" "failure"
      fatal SERVICE_START_FAILED "systemctl start ${svc} failed"
    fi
  done
}

atomic_symlink_swap() {
  local target_dir="$1"
  local tmp_link="${HERMES_NATIVE_ROOT}/.current.tmp.$$"
  rm -f "${tmp_link}"
  ln -s "${target_dir}" "${tmp_link}"
  mv -T "${tmp_link}" "${CURRENT_SYMLINK}"
}

# ---------------------------------------------------------------------------
# cutover
# ---------------------------------------------------------------------------

cmd_cutover() {
  acquire_lock
  audit_event "cutover" "start"

  if [[ ! -f "${HERMES_NATIVE_PRECUTOVER_MANIFEST}" ]]; then
    fatal PRECUTOVER_NOT_PASSED "no pre-cutover manifest at ${HERMES_NATIVE_PRECUTOVER_MANIFEST}; run pre-cutover first"
  fi
  if ! python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
sys.exit(0 if (d.get('gates_passed') is True and d.get('target_version') == sys.argv[2] and d.get('target_sha') == sys.argv[3]) else 1)
" "${HERMES_NATIVE_PRECUTOVER_MANIFEST}" "${HERMES_TARGET_VERSION}" "${HERMES_TARGET_SHA}" 2>/dev/null; then
    fatal PRECUTOVER_NOT_PASSED "pre-cutover manifest at ${HERMES_NATIVE_PRECUTOVER_MANIFEST} is stale or does not show gates_passed for the current pinned target"
  fi

  if ! release_manifest_matches_target "$(release_manifest_path "${TARGET_RELEASE_DIR}")"; then
    fatal TARGET_RELEASE_NOT_STAGED "staged release at ${TARGET_RELEASE_DIR} no longer matches the pinned target; re-run stage"
  fi

  stop_services_in_order

  audit_event "cutover:symlink_swap" "start"
  atomic_symlink_swap "${TARGET_RELEASE_DIR}"
  audit_event "cutover:symlink_swap" "success"

  start_services_in_order

  audit_event "cutover" "success"
  log "cutover complete: current -> ${TARGET_RELEASE_DIR}"
}

# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

check_state_db() {
  [[ -f "${HERMES_NATIVE_STATE_DB}" ]] || return 1
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "${HERMES_NATIVE_STATE_DB}" "PRAGMA integrity_check;" 2>/dev/null | grep -q '^ok$'
  else
    [[ -s "${HERMES_NATIVE_STATE_DB}" ]]
  fi
}

check_sessions_readable() {
  [[ -f "${HERMES_NATIVE_STATE_DB}" ]] || return 1
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "${HERMES_NATIVE_STATE_DB}" "SELECT COUNT(*) FROM sessions;" >/dev/null 2>&1
  else
    return 1
  fi
}

check_public_binds() {
  # Returns 0 if none of HERMES_NATIVE_PUBLIC_BIND_CHECK_PORTS are LISTENing
  # on a public address. Prints a WARN and returns 0 if the check is
  # unconfigured, or if `ss` is unavailable -- an unrunnable check must never
  # masquerade as a pass by staying silent, but it also must not be treated
  # as equivalent to a public-bind finding.
  if [[ -z "${HERMES_NATIVE_PUBLIC_BIND_CHECK_PORTS}" ]]; then
    log "WARN: public-bind check skipped (HERMES_NATIVE_PUBLIC_BIND_CHECK_PORTS is empty)"
    return 0
  fi
  if ! command -v ss >/dev/null 2>&1; then
    log "WARN: public-bind check skipped ('ss' not available)"
    return 0
  fi
  local listen_output port
  listen_output="$(ss -tuln 2>/dev/null || true)"
  for port in ${HERMES_NATIVE_PUBLIC_BIND_CHECK_PORTS}; do
    if printf '%s\n' "${listen_output}" | grep -Eq "(^|[[:space:]])(0\.0\.0\.0|\*|:::):${port}([[:space:]]|$)"; then
      return 1
    fi
  done
  return 0
}

cmd_validate() {
  local -a rollback_codes=()
  local overall_ok=true

  local current_target current_version
  current_target="$(resolved_current_target)"
  current_version="$(basename "${current_target:-}")"
  if [[ "${current_version}" != "${HERMES_TARGET_VERSION}" ]]; then
    log "FAIL ACTIVE_VERSION_MISMATCH: current -> ${current_target:-<none>} (expected version ${HERMES_TARGET_VERSION})"
    rollback_codes+=("ACTIVE_VERSION_MISMATCH")
    overall_ok=false
  fi

  if command -v systemctl >/dev/null 2>&1; then
    if ! systemctl is-active --quiet "${SVC_GATEWAY}"; then
      log "FAIL GATEWAY_START_FAIL: ${SVC_GATEWAY} is not active"
      rollback_codes+=("GATEWAY_START_FAIL"); overall_ok=false
    fi
    if ! systemctl is-active --quiet "${SVC_DASHBOARD}"; then
      log "FAIL DASHBOARD_START_FAIL: ${SVC_DASHBOARD} is not active"
      rollback_codes+=("DASHBOARD_START_FAIL"); overall_ok=false
    fi
    if ! systemctl is-active --quiet "${SVC_DESKTOP_SERVE}"; then
      log "FAIL DESKTOP_SERVE_START_FAIL: ${SVC_DESKTOP_SERVE} is not active"
      rollback_codes+=("DESKTOP_SERVE_START_FAIL"); overall_ok=false
    fi
  fi

  if ! check_state_db; then
    log "FAIL STATE_DB_ERROR: ${HERMES_NATIVE_STATE_DB} missing or failed integrity check"
    rollback_codes+=("STATE_DB_ERROR"); overall_ok=false
  fi

  if ! check_sessions_readable; then
    log "FAIL SESSION_READ_FAIL: sessions table unreadable at ${HERMES_NATIVE_STATE_DB}"
    rollback_codes+=("SESSION_READ_FAIL"); overall_ok=false
  fi

  if [[ ! -S "${HERMES_NATIVE_ROOT_EXECUTOR_SOCKET}" && ! -e "${HERMES_NATIVE_ROOT_EXECUTOR_SOCKET}" ]]; then
    log "FAIL ROOT_EXECUTOR_SOCKET_MISSING: ${HERMES_NATIVE_ROOT_EXECUTOR_SOCKET} absent (socket read-only check; service itself is never touched)"
    rollback_codes+=("ROOT_EXECUTOR_SOCKET_MISSING"); overall_ok=false
  fi

  if [[ -f "${HERMES_NATIVE_FLEET_BASELINE}" ]]; then
    local baseline_content current_fleet_json
    baseline_content="$(cat "${HERMES_NATIVE_FLEET_BASELINE}")"
    guard_dry_run_false "${baseline_content}"
    current_fleet_json="$(capture_fleet_state_json)"
    if ! python3 -c "
import json, sys
a = json.loads(sys.argv[1])
b = json.loads(sys.argv[2])
sys.exit(0 if a.get('containers') == b.get('containers') else 1)
" "${baseline_content}" "${current_fleet_json}" 2>/dev/null; then
      log "FAIL FLEET_STATE_CHANGED: fleet container state differs from the pre-cutover baseline; this script must never change fleet state"
      overall_ok=false
    fi
  fi

  if ! check_public_binds; then
    log "FAIL UNEXPECTED_PUBLIC_BIND: one or more of [${HERMES_NATIVE_PUBLIC_BIND_CHECK_PORTS}] is listening on a public address"
    rollback_codes+=("UNEXPECTED_PUBLIC_BIND"); overall_ok=false
  fi

  local code
  for code in "${rollback_codes[@]+"${rollback_codes[@]}"}"; do
    echo "AUTO_ROLLBACK_RECOMMENDED=${code}"
  done

  if [[ "${overall_ok}" == "true" ]]; then
    audit_event "validate" "pass"
    echo "VALIDATE_PASS"
    return 0
  fi
  audit_event "validate" "fail"
  return 1
}

# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------

cmd_rollback() {
  acquire_lock
  audit_event "rollback" "start"

  if [[ ! -f "${HERMES_NATIVE_PRECUTOVER_MANIFEST}" ]]; then
    fatal ROLLBACK_MANIFEST_MISSING "no pre-cutover manifest at ${HERMES_NATIVE_PRECUTOVER_MANIFEST}; refusing to guess a rollback target"
  fi

  local previous_target
  previous_target="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('previous_symlink_target',''))" "${HERMES_NATIVE_PRECUTOVER_MANIFEST}" 2>/dev/null || true)"
  if [[ -z "${previous_target}" || ! -d "${previous_target}" || ! -x "${previous_target}/bin/hermes" ]]; then
    fatal ROLLBACK_TARGET_INVALID "manifest previous_symlink_target=${previous_target:-<empty>} does not point at a valid release (missing bin/hermes)"
  fi

  stop_services_in_order

  audit_event "rollback:symlink_swap" "start"
  atomic_symlink_swap "${previous_target}"
  audit_event "rollback:symlink_swap" "success"

  start_services_in_order

  audit_event "rollback" "success"
  log "rollback complete: current -> ${previous_target}"
}

# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

render_redacted_env_file() {
  local file="$1"
  if [[ -f "${file}" ]]; then
    redact_secrets < "${file}"
  else
    echo "(no .env file present at ${file})"
  fi
}

cmd_report() {
  mkdir -p "${HERMES_NATIVE_REPORT_DIR}"
  local ts report_path
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  report_path="${HERMES_NATIVE_REPORT_DIR}/report-${ts}.md"

  local current_target
  current_target="$(resolved_current_target)"

  {
    echo "# hermes-native-change-c report (${ts})"
    echo
    echo "## Target release"
    echo "- version: ${HERMES_TARGET_VERSION}"
    echo "- tag: ${HERMES_TARGET_TAG}"
    echo "- sha: ${HERMES_TARGET_SHA}"
    echo
    echo "## Current state"
    echo "- current -> ${current_target:-(no symlink present)}"
    echo
    echo "## Known upstream discrepancy"
    echo "- upstream scripts/install.sh: NODE_VERSION constant is \"22\", but a log line in the same script states the required floor is \">=26\". Not resolvable from this script; documented only."
    echo
    echo "## Pre-cutover manifest"
    if [[ -f "${HERMES_NATIVE_PRECUTOVER_MANIFEST}" ]]; then
      echo '```json'
      cat "${HERMES_NATIVE_PRECUTOVER_MANIFEST}"
      echo '```'
    else
      echo "(none written)"
    fi
    echo
    echo "## Fleet baseline"
    if [[ -f "${HERMES_NATIVE_FLEET_BASELINE}" ]]; then
      echo '```json'
      cat "${HERMES_NATIVE_FLEET_BASELINE}"
      echo '```'
    else
      echo "(none captured)"
    fi
    echo
    echo "## Target release .env (redacted)"
    echo '```'
    render_redacted_env_file "${TARGET_RELEASE_DIR}/.env"
    echo '```'
    echo
    echo "## Audit log"
    echo '```'
    if [[ -f "${HERMES_NATIVE_AUDIT_LOG}" ]]; then
      tail -n 200 "${HERMES_NATIVE_AUDIT_LOG}"
    else
      echo "(no audit log at ${HERMES_NATIVE_AUDIT_LOG})"
    fi
    echo '```'
  } > "${report_path}"

  audit_event "report" "success"
  echo "${report_path}"
}

# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------

usage() {
  cat <<'USAGE'
Usage: hermes-native-change-c.sh <subcommand> [--dry-run]

Subcommands:
  plan          Show planned actions. Never mutates anything.
  stage         Install HERMES_TARGET_VERSION into releases/<version>.
                Never touches `current` or releases/0.19.0.
  pre-cutover   Run pre-cutover gate checks. Writes only this script's own
                state manifest; exits non-zero if any gate fails.
  cutover       Stop services, atomically swap `current`, start services.
  validate      Post-cutover checks. Exits non-zero and prints
                AUTO_ROLLBACK_RECOMMENDED=<CODE> lines on failure.
  rollback      Swap `current` back to the pre-cutover manifest's target.
  report        Write a markdown report of this run's collected state.

--dry-run forces plan-mode behavior for any subcommand: no mutating command
is ever executed.
USAGE
}

main() {
  if [[ $# -eq 0 ]]; then
    usage
    exit 1
  fi

  local mode=""
  local arg
  for arg in "$@"; do
    if [[ "${arg}" == "--dry-run" ]]; then
      DRY_RUN=true
    elif [[ "${arg}" == "--help" || "${arg}" == "-h" ]]; then
      usage
      exit 0
    elif [[ -z "${mode}" ]]; then
      mode="${arg}"
    fi
  done

  if [[ "${DRY_RUN}" == "true" ]]; then
    log "--dry-run requested for subcommand '${mode}': showing plan only, no mutation will occur"
    cmd_plan
    return 0
  fi

  case "${mode}" in
    plan) cmd_plan ;;
    stage) cmd_stage ;;
    pre-cutover) cmd_pre_cutover ;;
    cutover) cmd_cutover ;;
    validate) cmd_validate ;;
    rollback) cmd_rollback ;;
    report) cmd_report ;;
    *)
      usage
      exit 1
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
  main "$@"
fi
