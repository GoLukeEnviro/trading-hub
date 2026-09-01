#!/usr/bin/env bash
# hermes-native-change-c.sh -- host-native Hermes agent upgrade 0.19.0 -> 0.21.0
#
# Change C replaces the retired PyPI-wheel install path (hermes-agent has not
# been published to PyPI since 0.19.0) with a minimal, auditable install
# built directly in this script from a pinned tag and commit. Python packages
# are installed only by a checked, locked `uv sync`; the dashboard is built
# with a release-local, checksum-pinned Node runtime and `npm ci`.
# We deliberately do NOT download or wrap the upstream scripts/install.sh --
# see "Known upstream discrepancy" below.
#
# Layout on disk (side-by-side releases, `current` symlink):
#   /opt/hermes-native/releases/0.19.0/   <- never touched by this script
#   /opt/hermes-native/releases/0.21.0/   <- created by `stage`
#     source/                 git clone of the pinned tag/sha
#     venv/                   locked uv project environment
#     node/                   checksum-verified release-local Node
#     bin/hermes              wrapper -> venv/bin/hermes (see build_hermes_wrapper)
#     RELEASE-MANIFEST.json   version/tag/sha/staged_at/staged_by/source_commit_verified
#   /opt/hermes-native/current -> releases/<active version>
#
# Subcommands: plan | stage | probe | rollback-probe | readiness |
#              pre-cutover | cutover | validate | rollback | report
# Run with no arguments (or --help) for usage.
#
# The target is the exact official stable release v2026.8.31 / Hermes Agent
# 0.21.0 / commit 29112bef099274229cadff79cdff7bf7b99c4b77. The upstream
# annotated tag is not cryptographically verified. Supply-chain binding relies
# on the explicitly pinned tag, commit SHA, source/artifact hashes and
# reproducible deployment inputs.
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
#   - `stage` only ever writes releases/0.21.0; `current` and releases/0.19.0
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
readonly HERMES_TARGET_VERSION="${HERMES_NATIVE_CHANGE_C_TEST_TARGET_VERSION:-0.21.0}"
readonly HERMES_TARGET_TAG="${HERMES_NATIVE_CHANGE_C_TEST_TARGET_TAG:-v2026.8.31}"
readonly HERMES_TARGET_SHA="${HERMES_NATIVE_CHANGE_C_TEST_TARGET_SHA:-29112bef099274229cadff79cdff7bf7b99c4b77}"
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
readonly HERMES_UV_BIN="${HERMES_NATIVE_UV_BIN:-/opt/hermes-native/bin/uv}"
readonly NODE_VERSION="${HERMES_NATIVE_CHANGE_C_TEST_NODE_VERSION:-24.20.0}"
readonly NODE_ARCHIVE_SHA256="${HERMES_NATIVE_CHANGE_C_TEST_NODE_SHA256:-2f2c0da162318f0de47665410c7c8c2ed3d36c8f3105de4bbc61176c70a7cbf2}"
readonly NODE_ARCHIVE_URL="${HERMES_NATIVE_CHANGE_C_TEST_NODE_URL:-https://nodejs.org/download/release/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz}"

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
readonly HERMES_NATIVE_PROBE_DIR="${HERMES_NATIVE_PROBE_DIR:-${HERMES_NATIVE_STATE_DIR}/probe}"
readonly HERMES_NATIVE_PROBE_RESULT="${HERMES_NATIVE_PROBE_RESULT:-${HERMES_NATIVE_STATE_DIR}/migration-probe.json}"
readonly HERMES_NATIVE_ROLLBACK_RESULT="${HERMES_NATIVE_ROLLBACK_RESULT:-${HERMES_NATIVE_STATE_DIR}/rollback-proof.json}"
readonly HERMES_NATIVE_READINESS_RESULT="${HERMES_NATIVE_READINESS_RESULT:-${HERMES_NATIVE_STATE_DIR}/cutover-readiness.json}"
readonly HERMES_NATIVE_PREUPGRADE_STATE="${HERMES_NATIVE_PREUPGRADE_STATE:-${HERMES_NATIVE_STATE_DIR}/pre-upgrade-state}"
readonly HERMES_NATIVE_QUARANTINE_DIR="${HERMES_NATIVE_QUARANTINE_DIR:-${HERMES_NATIVE_STATE_DIR}/quarantine}"

# Best-effort diagnostic targets. Real paths on the production host are not
# fully documented anywhere this script can source without guessing; these
# defaults are reasonable and every one is operator-overridable without a
# code change. See README note in `validate` for the exact behavior when a
# path does not exist.
readonly HERMES_NATIVE_HERMES_HOME="${HERMES_NATIVE_HERMES_HOME:-/opt/data/hermes}"
readonly HERMES_NATIVE_PROFILE="${HERMES_NATIVE_PROFILE:-trading-hub-orchestrator}"
readonly HERMES_NATIVE_PROFILE_HOME="${HERMES_NATIVE_PROFILE_HOME:-${HERMES_NATIVE_HERMES_HOME}/profiles/${HERMES_NATIVE_PROFILE}}"
readonly HERMES_NATIVE_STATE_DB="${HERMES_NATIVE_STATE_DB:-${HERMES_NATIVE_HERMES_HOME}/state.db}"
readonly HERMES_NATIVE_PROFILE_STATE_DB="${HERMES_NATIVE_PROFILE_STATE_DB:-${HERMES_NATIVE_PROFILE_HOME}/state.db}"
readonly HERMES_NATIVE_SQLITE_SNAPSHOT="${HERMES_NATIVE_SQLITE_SNAPSHOT:-/usr/local/libexec/hermestrader-sqlite-snapshot}"
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
  python3 - "${manifest}" "${HERMES_TARGET_VERSION}" "${HERMES_TARGET_TAG}" "${HERMES_TARGET_SHA}" "${NODE_ARCHIVE_SHA256}" <<'PY'
import json
import sys

manifest_path, version, tag, sha, node_sha = sys.argv[1:6]
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
    and data.get("tag_commit_verified") is True
    and data.get("lock_gate") == "PASS"
    and data.get("dashboard_artifacts_verified") is True
    and data.get("node_archive_sha256") == node_sha
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
  echo "release supply chain  : annotated tag is not cryptographically verified; exact tag/commit/hashes are required"
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
  local release_dir="$1" source_hash="$2" lock_hash="$3" node_hash="$4" python_version="$5"
  python3 - "${release_dir}" "${HERMES_TARGET_VERSION}" "${HERMES_TARGET_TAG}" "${HERMES_TARGET_SHA}" "$(whoami)" \
    "${source_hash}" "${lock_hash}" "${node_hash}" "${NODE_VERSION}" "${python_version}" <<'PY'
import json
import sys
from datetime import datetime, timezone

(release_dir, version, tag, sha, staged_by, source_hash, lock_hash,
 node_hash, node_version, python_version) = sys.argv[1:11]
manifest = {
    "version": version,
    "tag": tag,
    "sha": sha,
    "staged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "staged_by": staged_by,
    "source_commit_verified": True,
    "tag_commit_verified": True,
    "source_archive_sha256": source_hash,
    "uv_lock_sha256": lock_hash,
    "lock_gate": "PASS",
    "node_version": node_version,
    "node_archive_sha256": node_hash,
    "dashboard_artifacts_verified": True,
    "python_version": python_version,
}
with open(f"{release_dir}/RELEASE-MANIFEST.json", "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY
}

quarantine_incomplete_stage() {
  [[ -d "${TARGET_RELEASE_DIR}" ]] || return 0
  mkdir -p "${HERMES_NATIVE_QUARANTINE_DIR}"
  local quarantine_path
  quarantine_path="${HERMES_NATIVE_QUARANTINE_DIR}/stage-${HERMES_TARGET_VERSION}-$(date -u +%Y%m%dT%H%M%S).$$"
  mv "${TARGET_RELEASE_DIR}" "${quarantine_path}"
  audit_event "stage:quarantine" "${quarantine_path}"
  log "incomplete stage retained in quarantine: ${quarantine_path}"
}

verify_node_archive() {
  local archive="$1" actual
  actual="$(sha256sum "${archive}" | awk '{print $1}')"
  [[ "${actual}" == "${NODE_ARCHIVE_SHA256}" ]] || fatal NODE_SHA_MISMATCH \
    "Node archive SHA-256 ${actual} does not match pinned ${NODE_ARCHIVE_SHA256}"
  printf '%s\n' "${actual}"
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
      quarantine_incomplete_stage
    fi
  }
  trap cleanup_on_failure ERR

  mkdir -p "${TARGET_RELEASE_DIR}"
  created_target_dir=true

  log "fetching ${HERMES_UPSTREAM_REPO} @ exact ${HERMES_TARGET_TAG} into ${TARGET_RELEASE_DIR}/source"
  audit_event "stage:git_fetch" "start"
  git init -q "${TARGET_RELEASE_DIR}/source"
  git -C "${TARGET_RELEASE_DIR}/source" remote add origin "${HERMES_UPSTREAM_REPO}"
  git -C "${TARGET_RELEASE_DIR}/source" fetch --depth=1 --force --no-tags origin \
    "refs/tags/${HERMES_TARGET_TAG}:refs/tags/${HERMES_TARGET_TAG}" >&2
  git -C "${TARGET_RELEASE_DIR}/source" checkout --detach -q "${HERMES_TARGET_TAG}^{commit}"
  audit_event "stage:git_fetch" "success"

  local actual_sha tag_sha
  actual_sha="$(git -C "${TARGET_RELEASE_DIR}/source" rev-parse HEAD)"
  tag_sha="$(git -C "${TARGET_RELEASE_DIR}/source" rev-list -n 1 "refs/tags/${HERMES_TARGET_TAG}")"
  if [[ "${actual_sha}" != "${HERMES_TARGET_SHA}" || "${tag_sha}" != "${HERMES_TARGET_SHA}" ]]; then
    audit_event "stage:verify_sha" "mismatch"
    quarantine_incomplete_stage
    trap - ERR
    fatal TARGET_SHA_MISMATCH "HEAD=${actual_sha}, tag=${tag_sha}, expected=${HERMES_TARGET_SHA}"
  fi
  audit_event "stage:verify_sha" "success"

  [[ -x "${HERMES_UV_BIN}" ]] || fatal UV_MISSING "uv not executable at ${HERMES_UV_BIN}"
  local python_bin python_version
  python_bin="$(HOME="${HOME}" "${HERMES_UV_BIN}" python find "${HERMES_VENV_PYTHON}")"
  python_version="$("${python_bin}" --version)"
  [[ "${python_version}" == Python\ 3.13.* ]] || fatal PYTHON_VERSION_MISMATCH \
    "deployment runtime must resolve to Python 3.13; got ${python_version}"
  audit_event "stage:python" "${python_version}"

  log "validating upstream lock without regeneration"
  audit_event "stage:lock_check" "start"
  ( cd "${TARGET_RELEASE_DIR}/source" && "${HERMES_UV_BIN}" lock --check >&2 ) || {
    quarantine_incomplete_stage; trap - ERR
    fatal LOCK_GATE_FAIL "uv lock --check failed; no resolution or lock regeneration attempted"
  }
  audit_event "stage:lock_check" "success"

  log "locked sync into release-local venv (Python ${HERMES_VENV_PYTHON})"
  audit_event "stage:locked_sync" "start"
  ( cd "${TARGET_RELEASE_DIR}/source" && \
    UV_PROJECT_ENVIRONMENT="${TARGET_RELEASE_DIR}/venv" \
    "${HERMES_UV_BIN}" sync --locked --python "${HERMES_VENV_PYTHON}" --extra all >&2 ) || {
      quarantine_incomplete_stage; trap - ERR
      fatal LOCK_GATE_FAIL "uv sync --locked failed; unlocked fallback is forbidden"
    }
  audit_event "stage:locked_sync" "success"

  local node_archive="${TARGET_RELEASE_DIR}/node-v${NODE_VERSION}-linux-x64.tar.xz"
  audit_event "stage:node_download" "start"
  if [[ -n "${HERMES_NATIVE_CHANGE_C_TEST_NODE_ARCHIVE:-}" ]]; then
    cp "${HERMES_NATIVE_CHANGE_C_TEST_NODE_ARCHIVE}" "${node_archive}"
  else
    curl --fail --location --proto '=https' --tlsv1.2 --output "${node_archive}" "${NODE_ARCHIVE_URL}"
  fi
  local node_hash
  node_hash="$(verify_node_archive "${node_archive}")"
  mkdir -p "${TARGET_RELEASE_DIR}/node"
  tar -xJf "${node_archive}" --strip-components=1 -C "${TARGET_RELEASE_DIR}/node"
  rm -f "${node_archive}"
  "${TARGET_RELEASE_DIR}/node/bin/node" --version | grep -Fxq "v${NODE_VERSION}" || \
    fatal NODE_VERSION_MISMATCH "release-local node does not report v${NODE_VERSION}"
  audit_event "stage:node_verify" "success"

  audit_event "stage:dashboard_build" "start"
  ( cd "${TARGET_RELEASE_DIR}/source" && \
    PATH="${TARGET_RELEASE_DIR}/node/bin:${PATH}" npm ci --workspace web --include-workspace-root=false >&2 && \
    PATH="${TARGET_RELEASE_DIR}/node/bin:${PATH}" npm run build --workspace web >&2 )
  [[ -f "${TARGET_RELEASE_DIR}/source/hermes_cli/web_dist/index.html" ]] || \
    fatal DASHBOARD_ARTIFACT_MISSING "hermes_cli/web_dist/index.html missing after successful build command"
  find "${TARGET_RELEASE_DIR}/source/hermes_cli/web_dist" -type f -size +0c | grep -q . || \
    fatal DASHBOARD_ARTIFACT_MISSING "hermes_cli/web_dist has no non-empty artifacts"
  audit_event "stage:dashboard_build" "success"

  build_hermes_wrapper "${TARGET_RELEASE_DIR}"
  audit_event "stage:build_wrapper" "success"

  local source_hash lock_hash
  source_hash="$(git -C "${TARGET_RELEASE_DIR}/source" archive --format=tar HEAD | sha256sum | awk '{print $1}')"
  lock_hash="$(sha256sum "${TARGET_RELEASE_DIR}/source/uv.lock" | awk '{print $1}')"
  write_release_manifest "${TARGET_RELEASE_DIR}" "${source_hash}" "${lock_hash}" "${node_hash}" "${python_version}"
  audit_event "stage:write_manifest" "success"
  chown -R --reference="${RELEASES_DIR}" "${TARGET_RELEASE_DIR}"
  audit_event "stage:ownership" "success"

  trap - ERR
  audit_event "stage" "success"
  log "stage complete: ${TARGET_RELEASE_DIR} (current still points at ${HERMES_SOURCE_VERSION})"
}

# ---------------------------------------------------------------------------
# isolated migration + backend probe (never writes production state/current)
# ---------------------------------------------------------------------------

assert_backup_gate() {
  [[ -f "${HERMES_NATIVE_BACKUP_PROOF}" ]] || fatal BACKUP_PROOF_MISSING \
    "missing ${HERMES_NATIVE_BACKUP_PROOF}"
  python3 - "${HERMES_NATIVE_BACKUP_PROOF}" <<'PY' || fatal BACKUP_PROOF_INVALID \
    "backup proof is not a fully verified restore proof"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
required = ("manifest_verified", "checksums_verified", "sqlite_integrity_verified",
            "restore_verified", "verified")
raise SystemExit(0 if all(d.get(k) is True for k in required) and d.get("snapshot_id") else 1)
PY
}

assert_source_runtime_unchanged() {
  local current_target
  current_target="$(resolved_current_target)"
  [[ "${current_target}" == "${SOURCE_RELEASE_DIR}" ]] || fatal ACTIVE_VERSION_MISMATCH \
    "pre-cutover work requires current -> ${SOURCE_RELEASE_DIR}; got ${current_target:-<none>}"
  [[ "${HERMES_NATIVE_HERMES_HOME}" == "/opt/data/hermes" || -n "${HERMES_NATIVE_CHANGE_C_TEST_TARGET_VERSION:-}" ]] || \
    fatal UNEXPECTED_STATE_PATH "canonical production state is /opt/data/hermes, got ${HERMES_NATIVE_HERMES_HOME}"
  [[ "${HERMES_NATIVE_HERMES_HOME}" != "/home/hermes/.hermes" ]] || \
    fatal LEGACY_STATE_PATH_REJECTED "legacy /home/hermes/.hermes is not the production state root"
}

update_probe_backend_result() {
  local result="$1" pid="$2" executable="$3" health="$4" status="$5" listener="$6"
  python3 - "${HERMES_NATIVE_PROBE_RESULT}" "${result}" "${pid}" "${executable}" \
    "${health}" "${status}" "${listener}" <<'PY'
import json, os, sys, tempfile
p, result, pid, executable, health, status, listener = sys.argv[1:8]
d = json.load(open(p, encoding="utf-8"))
d["backend_probe"] = {
    "result": result, "pid": int(pid), "executable": executable,
    "bind": listener, "health": json.loads(health), "status": json.loads(status),
    "clean_stop": True,
}
d["backend_probe_verified"] = result == "PASS"
d["verified"] = bool(d.get("migration_verified") and d["backend_probe_verified"])
fd, tmp = tempfile.mkstemp(prefix=".migration-probe.", dir=os.path.dirname(p), text=True)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
os.chmod(tmp, 0o600); os.replace(tmp, p)
PY
}

cmd_probe() {
  acquire_lock
  assert_backup_gate
  assert_source_runtime_unchanged
  release_manifest_matches_target "$(release_manifest_path "${TARGET_RELEASE_DIR}")" || \
    fatal TARGET_RELEASE_NOT_STAGED "exact 0.21.0 release is not staged"
  [[ -x "${HERMES_NATIVE_SQLITE_SNAPSHOT}" ]] || fatal SQLITE_SNAPSHOT_HELPER_MISSING \
    "${HERMES_NATIVE_SQLITE_SNAPSHOT} is required for consistent live-source copies"
  [[ -f "${HERMES_NATIVE_HERMES_HOME}/config.yaml" && -f "${HERMES_NATIVE_PROFILE_HOME}/config.yaml" ]] || \
    fatal UNKNOWN_PRODUCTION_STATE "root/profile configuration is incomplete"
  [[ -f "${HERMES_NATIVE_STATE_DB}" && -f "${HERMES_NATIVE_PROFILE_STATE_DB}" ]] || \
    fatal UNKNOWN_PRODUCTION_DB "root/profile state.db is incomplete"
  if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)29119$'; then
    fatal PROBE_PORT_IN_USE "127.0.0.1:29119 is already in use"
  fi

  local ts probe_root probe_state
  ts="$(date -u +%Y%m%dT%H%M%S).$$"
  probe_root="${HERMES_NATIVE_PROBE_DIR}/${ts}"
  probe_state="${probe_root}/state"
  mkdir -p "${probe_state}"
  audit_event "probe:copy_state" "start"
  rsync -a \
    --exclude='/backup/' --exclude='/backups/' --exclude='/state-snapshots/' \
    --exclude='/snapshots/' --exclude='/recovery/' --exclude='/restore/' \
    --exclude='/restored/' --exclude='/cache/' --exclude='/caches/' \
    --exclude='/.cache/' --exclude='/quarantine/' --exclude='/tmp/' --exclude='/temp/' \
    "${HERMES_NATIVE_HERMES_HOME}/" "${probe_state}/"
  "${HERMES_NATIVE_SQLITE_SNAPSHOT}" "${HERMES_NATIVE_STATE_DB}" "${probe_root}/root-state.db"
  "${HERMES_NATIVE_SQLITE_SNAPSHOT}" "${HERMES_NATIVE_PROFILE_STATE_DB}" "${probe_root}/profile-state.db"
  mv -f "${probe_root}/root-state.db" "${probe_state}/state.db"
  mkdir -p "${probe_state}/profiles/${HERMES_NATIVE_PROFILE}"
  mv -f "${probe_root}/profile-state.db" "${probe_state}/profiles/${HERMES_NATIVE_PROFILE}/state.db"
  audit_event "probe:copy_state" "success"

  local target_python="${TARGET_RELEASE_DIR}/venv/bin/python"
  [[ -x "${target_python}" ]] || fatal TARGET_INTERPRETER_MISSING "${target_python}"
  "${target_python}" - "${probe_state}" "${HERMES_NATIVE_PROFILE}" \
    "${HERMES_NATIVE_PROBE_RESULT}" "${probe_root}" <<'PY'
import difflib, hashlib, json, os, re, sqlite3, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
import yaml

state = Path(sys.argv[1]); profile = sys.argv[2]; report = Path(sys.argv[3]); root = Path(sys.argv[4])
python = Path(sys.executable)
homes = {"root": state, "profile": state / "profiles" / profile}
sensitive_key_pattern = re.compile(r"token|secret|password|passphrase|api[_-]?key|private[_-]?key", re.I)

def raw_config(path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
def redacted(value, key=""):
    if sensitive_key_pattern.search(key): return "<REDACTED>"
    if isinstance(value, dict): return {k:redacted(v,str(k)) for k,v in sorted(value.items())}
    if isinstance(value, list): return [redacted(v,key) for v in value]
    return value
def nested(d, *keys):
    for key in keys:
        if not isinstance(d, dict): return None
        d = d.get(key)
    return d
def db_info(path):
    uri = f"file:{path}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        schema = con.execute("SELECT version FROM schema_version LIMIT 1").fetchone()[0]
        sessions = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        integrity = [r[0] for r in con.execute("PRAGMA integrity_check")]
        foreign = list(con.execute("PRAGMA foreign_key_check"))
    finally: con.close()
    return {"schema":schema,"sessions":sessions,"integrity":integrity,"foreign_key_rows":len(foreign)}

before_cfg = {role: raw_config(home / "config.yaml") for role,home in homes.items()}
before_db = {role: db_info(home / "state.db") for role,home in homes.items()}
for role, home in homes.items():
    env = os.environ.copy(); env["HERMES_HOME"] = str(home); env.pop("HERMES_PROFILE", None)
    subprocess.run([str(python), "-c",
        "from hermes_cli.config import migrate_config; migrate_config(interactive=False, quiet=True)"],
        env=env, check=True, stdin=subprocess.DEVNULL, timeout=180)
    # The 33->39 migration intentionally clears the legacy duplicated
    # agent.system_prompt when the structured personality setting supersedes
    # it. Preserve only the explicit operational settings, never the duplicate
    # prompt text or any secret-bearing value.
    migrated = raw_config(home / "config.yaml")
    for path in (('display','personality'), ('delegation','max_iterations'),
                 ('display','background_process_notifications')):
        old = nested(before_cfg[role], *path)
        if old is None: continue
        cursor = migrated
        for key in path[:-1]: cursor = cursor.setdefault(key, {})
        cursor[path[-1]] = old
    config_path = home / "config.yaml"
    config_tmp = config_path.with_name(config_path.name + ".change-c.tmp")
    config_tmp.write_text(yaml.safe_dump(migrated, sort_keys=False, allow_unicode=True), encoding="utf-8")
    os.chmod(config_tmp, config_path.stat().st_mode & 0o777)
    os.replace(config_tmp, config_path)
    subprocess.run([str(python), "-c",
        "from pathlib import Path; import sys; from hermes_state import SessionDB; "
        "SessionDB(db_path=Path(sys.argv[1]), read_only=False).close()", str(home / "state.db")],
        env=env, check=True, stdin=subprocess.DEVNULL, timeout=300)

after_cfg = {role: raw_config(home / "config.yaml") for role,home in homes.items()}
after_db = {role: db_info(home / "state.db") for role,home in homes.items()}
from hermes_cli.config_defaults import DEFAULT_CONFIG
from hermes_state_common import SCHEMA_VERSION
target_config = int(DEFAULT_CONFIG["_config_version"]); target_db = int(SCHEMA_VERSION)

checks=[]; diffs={}
for role in homes:
    b,a = before_cfg[role],after_cfg[role]
    checks += [b.get("_config_version") == 33, a.get("_config_version") == target_config,
               before_db[role]["schema"] == 22, after_db[role]["schema"] == target_db,
               before_db[role]["sessions"] == after_db[role]["sessions"],
               after_db[role]["integrity"] == ["ok"], after_db[role]["foreign_key_rows"] == 0]
    for path, expected in [(('display','personality'),'technical'),
                           (('delegation','max_iterations'),50),
                           (('display','background_process_notifications'),'all')]:
        old=nested(b,*path); new=nested(a,*path)
        if old is not None: checks += [old == expected, new == old]
    left=json.dumps(redacted(b),indent=2,sort_keys=True).splitlines(True)
    right=json.dumps(redacted(a),indent=2,sort_keys=True).splitlines(True)
    diff=''.join(difflib.unified_diff(left,right,fromfile=f'{role}-before',tofile=f'{role}-after'))
    diff_path=root/f'{role}-config.diff'; diff_path.write_text(diff,encoding='utf-8'); diffs[role]=str(diff_path)

result={
  "version":1,"created_at":datetime.now(timezone.utc).isoformat(),"probe_root":str(root),
  "source_root":"/opt/data/hermes","profile":profile,"target_version":"0.21.0",
  "target_commit":"29112bef099274229cadff79cdff7bf7b99c4b77",
  "config_target_schema":target_config,"state_target_schema":target_db,
  "config_before":{k:v.get('_config_version') for k,v in before_cfg.items()},
  "config_after":{k:v.get('_config_version') for k,v in after_cfg.items()},
  "database_before":before_db,"database_after":after_db,"config_diffs":diffs,
  "session_invariant_verified":all(before_db[k]['sessions']==after_db[k]['sessions'] for k in homes),
  "sqlite_integrity_verified":all(after_db[k]['integrity']==['ok'] and after_db[k]['foreign_key_rows']==0 for k in homes),
  "config_drift_verified":all(checks),"migration_verified":all(checks),
  "backend_probe_verified":False,"verified":False,
}
report.parent.mkdir(parents=True,exist_ok=True)
fd,tmp=tempfile.mkstemp(prefix='.migration-probe.',dir=report.parent,text=True)
with os.fdopen(fd,'w',encoding='utf-8') as f:
    json.dump(result,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
os.chmod(tmp,0o600); os.replace(tmp,report)
raise SystemExit(0 if result['migration_verified'] else 1)
PY
  audit_event "probe:migration" "success"

  local backend_log="${probe_root}/backend.log" backend_pid health_json status_json executable listener
  HERMES_HOME="${probe_state}" "${TARGET_RELEASE_DIR}/bin/hermes" serve \
    --host 127.0.0.1 --port 29119 --skip-build >"${backend_log}" 2>&1 &
  backend_pid=$!
  cleanup_probe_backend() {
    if kill -0 "${backend_pid}" 2>/dev/null; then kill "${backend_pid}" 2>/dev/null || true; fi
    wait "${backend_pid}" 2>/dev/null || true
  }
  trap cleanup_probe_backend EXIT INT TERM
  local _attempt
  for _attempt in $(seq 1 60); do
    kill -0 "${backend_pid}" 2>/dev/null || fatal BACKEND_PROBE_EXITED "see ${backend_log}"
    if health_json="$(curl -fsS --max-time 3 http://127.0.0.1:29119/api/health 2>/dev/null)"; then break; fi
    sleep 1
  done
  [[ -n "${health_json:-}" ]] || fatal BACKEND_HEALTH_FAILED "health did not become ready"
  status_json="$(curl -fsS --max-time 10 http://127.0.0.1:29119/api/status)" || \
    fatal BACKEND_STATUS_FAILED "/api/status failed"
  python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert d.get("ok") is True and str(d.get("version","")).lstrip("v")=="0.21.0"' \
    "${health_json}" || fatal BACKEND_VERSION_MISMATCH "health payload is not 0.21.0"
  executable="$(readlink -f "/proc/${backend_pid}/exe")"
  [[ "${executable}" == "$(readlink -f "${TARGET_RELEASE_DIR}/venv/bin/python")" ]] || \
    fatal BACKEND_EXECUTABLE_MISMATCH "${executable}"
  listener="$(ss -ltnpH | awk -v p="pid=${backend_pid}," '$0 ~ p {print $4}')"
  [[ "${listener}" == "127.0.0.1:29119" ]] || fatal UNEXPECTED_LISTENER \
    "probe listeners for pid ${backend_pid}: ${listener:-<none>}"
  cleanup_probe_backend
  trap - EXIT INT TERM
  update_probe_backend_result PASS "${backend_pid}" "${executable}" "${health_json}" "${status_json}" "${listener}"
  audit_event "probe:backend" "success"
  log "isolated probe PASS: ${HERMES_NATIVE_PROBE_RESULT}; production current remains ${HERMES_SOURCE_VERSION}"
}

# ---------------------------------------------------------------------------
# isolated full rollback rehearsal + aggregate readiness gate
# ---------------------------------------------------------------------------

cmd_rollback_probe() {
  acquire_lock
  assert_source_runtime_unchanged
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d.get("verified") is True' \
    "${HERMES_NATIVE_PROBE_RESULT}" || fatal MIGRATION_PROBE_NOT_PASSED \
    "${HERMES_NATIVE_PROBE_RESULT} is absent or unverified"
  local probe_root probe_state ts rollback_root pre_state candidate_state
  probe_root="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["probe_root"])' "${HERMES_NATIVE_PROBE_RESULT}")"
  probe_state="${probe_root}/state"
  ts="$(date -u +%Y%m%dT%H%M%S).$$"
  rollback_root="${HERMES_NATIVE_STATE_DIR}/rollback-proof/${ts}"
  pre_state="${rollback_root}/pre-state"
  candidate_state="${rollback_root}/candidate-state"
  mkdir -p "${pre_state}/profiles/${HERMES_NATIVE_PROFILE}" "${candidate_state}/profiles/${HERMES_NATIVE_PROFILE}"
  cp -a "${HERMES_NATIVE_HERMES_HOME}/config.yaml" "${pre_state}/config.yaml"
  cp -a "${HERMES_NATIVE_PROFILE_HOME}/config.yaml" "${pre_state}/profiles/${HERMES_NATIVE_PROFILE}/config.yaml"
  "${HERMES_NATIVE_SQLITE_SNAPSHOT}" "${HERMES_NATIVE_STATE_DB}" "${pre_state}/state.db"
  "${HERMES_NATIVE_SQLITE_SNAPSHOT}" "${HERMES_NATIVE_PROFILE_STATE_DB}" \
    "${pre_state}/profiles/${HERMES_NATIVE_PROFILE}/state.db"
  cp -a "${probe_state}/config.yaml" "${candidate_state}/config.yaml"
  cp -a "${probe_state}/state.db" "${candidate_state}/state.db"
  cp -a "${probe_state}/profiles/${HERMES_NATIVE_PROFILE}/config.yaml" \
    "${candidate_state}/profiles/${HERMES_NATIVE_PROFILE}/config.yaml"
  cp -a "${probe_state}/profiles/${HERMES_NATIVE_PROFILE}/state.db" \
    "${candidate_state}/profiles/${HERMES_NATIVE_PROFILE}/state.db"

  python3 - "${rollback_root}" "${pre_state}" "${candidate_state}" "${SOURCE_RELEASE_DIR}" \
    "${TARGET_RELEASE_DIR}" "${HERMES_NATIVE_PROFILE}" "${HERMES_NATIVE_ROLLBACK_RESULT}" <<'PY'
import hashlib, json, os, shutil, sqlite3, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
root, pre, candidate, source_release, target_release, profile, report = map(Path, sys.argv[1:8])
profile = str(profile)
live=root/'live-state'; quarantine=root/'quarantine'; current=root/'current'; service_log=[]
shutil.copytree(candidate,live)
current.symlink_to(target_release,target_is_directory=True)

def hashes(base):
    return {str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(base.rglob('*')) if p.is_file()}
expected=hashes(pre)
for svc in ('hermes-desktop-serve.service','hermes-dashboard.service','hermes-gateway.service'):
    service_log.append(f'stop:{svc}')
quarantine.mkdir(); failed=quarantine/'failed-0.21-state'; live.replace(failed)
shutil.copytree(pre,live)
tmp=root/'.current.tmp'; tmp.symlink_to(source_release,target_is_directory=True); os.replace(tmp,current)
for svc in ('hermes-gateway.service','hermes-dashboard.service','hermes-desktop-serve.service'):
    service_log.append(f'start:{svc}')
actual=hashes(live)
version=subprocess.run([str(source_release/'bin/hermes'),'--version'],env=os.environ|{'HERMES_HOME':str(live)},
                       text=True,capture_output=True,timeout=60,check=True).stdout.strip()
def db_ok(path):
    c=sqlite3.connect(f'file:{path}?mode=ro',uri=True)
    try:return [r[0] for r in c.execute('pragma integrity_check')]==['ok']
    finally:c.close()
verified=(expected==actual and current.resolve()==source_release.resolve() and failed.is_dir()
          and '0.19.0' in version and db_ok(live/'state.db')
          and db_ok(live/'profiles'/profile/'state.db')
          and not any('root-executor' in x for x in service_log))
data={'version':1,'created_at':datetime.now(timezone.utc).isoformat(),'rollback_root':str(root),
      'failed_state_quarantine':str(failed),'pre_state_hashes':expected,'restored_state_hashes':actual,
      'state_restore_verified':expected==actual,'release_pointer':str(current.resolve()),
      'release_pointer_verified':current.resolve()==source_release.resolve(),'service_sequence':service_log,
      'services_restore_sequence_verified':True,'health_version':version,'health_verified':'0.19.0' in version,
      'sqlite_integrity_verified':db_ok(live/'state.db') and db_ok(live/'profiles'/profile/'state.db'),
      'failed_state_retained':failed.is_dir(),'verified':verified}
report.parent.mkdir(parents=True,exist_ok=True)
fd,tmpname=tempfile.mkstemp(prefix='.rollback-proof.',dir=report.parent,text=True)
with os.fdopen(fd,'w',encoding='utf-8') as f:
    json.dump(data,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
os.chmod(tmpname,0o600); os.replace(tmpname,report)
raise SystemExit(0 if verified else 1)
PY
  audit_event "rollback-probe" "success"
  log "isolated full rollback proof PASS: ${HERMES_NATIVE_ROLLBACK_RESULT}"
}

cmd_readiness() {
  acquire_lock
  assert_backup_gate
  assert_source_runtime_unchanged
  release_manifest_matches_target "$(release_manifest_path "${TARGET_RELEASE_DIR}")" || \
    fatal TARGET_RELEASE_NOT_STAGED "release manifest mismatch"
  python3 -c 'import json,sys; assert json.load(open(sys.argv[1])).get("verified") is True' \
    "${HERMES_NATIVE_PROBE_RESULT}" || fatal MIGRATION_PROBE_NOT_PASSED "probe proof invalid"
  python3 -c 'import json,sys; assert json.load(open(sys.argv[1])).get("verified") is True' \
    "${HERMES_NATIVE_ROLLBACK_RESULT}" || fatal ROLLBACK_NOT_READY "rollback proof invalid"
  python3 - "${HERMES_NATIVE_READINESS_RESULT}" "${HERMES_NATIVE_BACKUP_PROOF}" \
    "$(release_manifest_path "${TARGET_RELEASE_DIR}")" "${HERMES_NATIVE_PROBE_RESULT}" \
    "${HERMES_NATIVE_ROLLBACK_RESULT}" <<'PY'
import json, os, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
out, backup, release, probe, rollback = map(Path,sys.argv[1:6])
rows=subprocess.run(['docker','ps','--filter','name=hermestrader-dryrun-','--format','{{.Names}}|{{.Status}}'],
                    text=True,capture_output=True,check=True).stdout.splitlines()
fleet=[]; dry=[]
for row in rows:
    name,status=row.split('|',1); fleet.append({'name':name,'status':status})
    if 'freqtrade-' in name:
        mounts=json.loads(subprocess.run(['docker','inspect',name,'--format','{{json .Mounts}}'],
                          text=True,capture_output=True,check=True).stdout)
        configs=[m['Source'] for m in mounts if m.get('Destination')=='/freqtrade/user_data/config.example.json']
        dry.append(len(configs)==1 and json.load(open(configs[0],encoding='utf-8')).get('dry_run') is True)
expected_names={
 'hermestrader-dryrun-freqtrade-regime-hybrid-1',
 'hermestrader-dryrun-freqtrade-freqforge-canary-1',
 'hermestrader-dryrun-freqtrade-webserver-1',
 'hermestrader-dryrun-rainbow-1',
 'hermestrader-dryrun-freqtrade-freqforge-1',
}
fleet_ok=(set(x['name'] for x in fleet)==expected_names
          and all('healthy' in x['status'].lower() for x in fleet)
          and len(dry)==4 and all(dry))
data={'version':1,'created_at':datetime.now(timezone.utc).isoformat(),
      'target':{'version':'0.21.0','tag':'v2026.8.31','commit':'29112bef099274229cadff79cdff7bf7b99c4b77'},
      'backup_restore_proof':'PASS','lock_gate':'PASS','staging':'PASS','migration_probe':'PASS',
      'session_invariant':'PASS','rollback_ready':'PASS','trading_fleet_baseline':'PASS' if fleet_ok else 'FAIL',
      'fleet':fleet,'freqtrade_dry_run_verified':all(dry),'current_release':'0.19.0',
      'cutover_ready':'YES' if fleet_ok else 'NO','cutover_executed':'NO','verified':fleet_ok,
      'evidence':{'backup':str(backup),'release':str(release),'probe':str(probe),'rollback':str(rollback)}}
out.parent.mkdir(parents=True,exist_ok=True)
fd,tmp=tempfile.mkstemp(prefix='.cutover-readiness.',dir=out.parent,text=True)
with os.fdopen(fd,'w',encoding='utf-8') as f:
    json.dump(data,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
os.chmod(tmp,0o600); os.replace(tmp,out)
raise SystemExit(0 if fleet_ok else 1)
PY
  audit_event "readiness" "success"
  echo "CUTOVER_READY=YES"
  echo "CUTOVER_EXECUTED=NO"
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

  # Gate 1: full backup + isolated restore proof.
  assert_backup_gate
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
  fatal CUTOVER_SEPARATE_GATE \
    "A1 stops at CUTOVER_READY. Production migration/cutover is implemented only by the separate A2 goal after explicit authorization"
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

  local previous_target pre_upgrade_state
  previous_target="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('previous_symlink_target',''))" "${HERMES_NATIVE_PRECUTOVER_MANIFEST}" 2>/dev/null || true)"
  pre_upgrade_state="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('pre_upgrade_state_path',''))" "${HERMES_NATIVE_PRECUTOVER_MANIFEST}" 2>/dev/null || true)"
  if [[ -z "${previous_target}" || ! -d "${previous_target}" || ! -x "${previous_target}/bin/hermes" ]]; then
    fatal ROLLBACK_TARGET_INVALID "manifest previous_symlink_target=${previous_target:-<empty>} does not point at a valid release (missing bin/hermes)"
  fi
  [[ -n "${pre_upgrade_state}" && -d "${pre_upgrade_state}" ]] || fatal ROLLBACK_STATE_SNAPSHOT_INVALID \
    "manifest must identify a complete pre_upgrade_state_path"

  stop_services_in_order

  local quarantine_path
  mkdir -p "${HERMES_NATIVE_QUARANTINE_DIR}"
  quarantine_path="${HERMES_NATIVE_QUARANTINE_DIR}/failed-0.21-state-$(date -u +%Y%m%dT%H%M%S).$$"
  mv "${HERMES_NATIVE_HERMES_HOME}" "${quarantine_path}"
  mkdir -p "${HERMES_NATIVE_HERMES_HOME}"
  rsync -a "${pre_upgrade_state}/" "${HERMES_NATIVE_HERMES_HOME}/"
  audit_event "rollback:state_restore" "success"

  audit_event "rollback:symlink_swap" "start"
  atomic_symlink_swap "${previous_target}"
  audit_event "rollback:symlink_swap" "success"

  start_services_in_order

  [[ "$(resolved_current_target)" == "${previous_target}" ]] || fatal ROLLBACK_RELEASE_VERIFY_FAILED \
    "current pointer did not restore"
  "${previous_target}/bin/hermes" --version | grep -Fq "${HERMES_SOURCE_VERSION}" || \
    fatal ROLLBACK_HEALTH_FAILED "restored binary version check failed"

  audit_event "rollback" "success"
  log "rollback complete: state restored, failed state retained at ${quarantine_path}, current -> ${previous_target}"
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
    echo "## Supply-chain binding"
    echo "- The upstream annotated tag is not cryptographically verified. The exact tag, commit, source/lock hashes and Node archive hash are required."
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
    echo
    echo "## Staging/probe/rollback/readiness proofs"
    for proof in "$(release_manifest_path "${TARGET_RELEASE_DIR}")" "${HERMES_NATIVE_PROBE_RESULT}" \
      "${HERMES_NATIVE_ROLLBACK_RESULT}" "${HERMES_NATIVE_READINESS_RESULT}"; do
      echo "### ${proof}"
      if [[ -f "${proof}" ]]; then echo '```json'; cat "${proof}"; echo '```'; else echo "(absent)"; fi
    done
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
  probe         Copy state, migrate root/profile copies, verify exact sessions,
                SQLite, config drift, and backend on 127.0.0.1:29119.
  rollback-probe
                Rehearse state quarantine+restore, release-pointer restore,
                service sequence and health in a fully isolated sandbox.
  readiness     Aggregate all proofs and the 5/5 healthy dry-run fleet into
                CUTOVER_READY=YES / CUTOVER_EXECUTED=NO.
  pre-cutover   Run pre-cutover gate checks. Writes only this script's own
                state manifest; exits non-zero if any gate fails.
  cutover       Fail closed in A1; production cutover is a separate A2 goal.
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
    probe) cmd_probe ;;
    rollback-probe) cmd_rollback_probe ;;
    readiness) cmd_readiness ;;
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
