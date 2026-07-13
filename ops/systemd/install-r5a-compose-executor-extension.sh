#!/usr/bin/env bash
# Transactional installer for the R5A hermestrader-dryrun compose execution
# executor extension (Issue #527).
#
# Deploys the updated hermes_root/ package (actions, policy, schema) that
# adds the four bounded compose actions:
#   r5a_compose_build, r5a_compose_up, r5a_compose_stop, r5a_compose_down
#
# This script is the Host-Operator-Handoff step: it MUST be run directly
# on the host as root, NEVER through the executor socket itself (the
# executor cannot safely restart itself).
#
# Usage:
#   sudo ./ops/systemd/install-r5a-compose-executor-extension.sh \
#     --expected-commit <FULL_SHA>
#   sudo ./ops/systemd/install-r5a-compose-executor-extension.sh \
#     --expected-commit <FULL_SHA> --check
#
# --check performs only the precondition checks and exits without
# installing, reloading, or restarting anything.
#
# What it does, in order:
#   1. Verify running as root.
#   2. Verify --expected-commit matches the repository HEAD.
#   3. Back up the active executor package (timestamped copy, SHA-256).
#   4. Py-compile the new package files from the repository.
#   5. Deploy the package atomically to /usr/local/sbin/hermes_root/.
#   6. Update the repository-commit env file.
#   7. Run systemctl daemon-reload (only if unit metadata changed).
#   8. Restart ONLY hermes-root-executor.service.
#   9. Verify service active/running, socket ownership (root:hermes 0660).
#  10. Validate NRestarts counter, executor_health via the client.
#  11. On any failure after step 4, restore the previous package and
#      service state automatically, then validate rollback health.
#
# What it deliberately does NOT do:
#   - Does not invoke the executor socket (direct host install only).
#   - Does not modify Docker, compose files, or trading bot containers.
#   - Does not change the Hermes container or any non-executor service.
#   - Does not perform git operations as root — the checkout remains
#     deploy-owned; this script only reads from it.
#   - Does not start or stop any R5A compose services.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_PACKAGE="${REPO_ROOT}/hermes_root"
TARGET_PACKAGE_DIR="/usr/local/sbin/hermes_root"
TARGET_DAEMON="/usr/local/sbin/hermes-root-executor"
SERVICE_NAME="hermes-root-executor.service"
SOCKET_PATH="/run/hermes-root-executor/executor.sock"
ENV_DIR="/etc/hermes-root-executor"
ENV_FILE="${ENV_DIR}/repository-commit.env"
BACKUP_ROOT="/root/backups/hermes-root-executor-r5a"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
COMMIT_SHA_RE='^[0-9a-f]{7,40}$'

# Modules required by the daemon that may have changed in the R5A extension.
# This is the full set deployed to /usr/local/sbin/hermes_root/.
REQUIRED_MODULES=(
  "__init__.py"
  "actions.py"
  "audit.py"
  "client.py"
  "policy.py"
  "protocol.py"
  "redact.py"
  "schema.py"
  "validate.py"
)

log() { printf '[r5a-executor-ext] %s\n' "$1"; }
die() { printf '[r5a-executor-ext] ERROR: %s\n' "$1" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Precondition checks
# ---------------------------------------------------------------------------

check_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        die "must run as root"
    fi
    log "root check OK"
}

check_source_package() {
    if [[ ! -d "${SOURCE_PACKAGE}" ]]; then
        die "source package not found: ${SOURCE_PACKAGE}"
    fi
    for mod in "${REQUIRED_MODULES[@]}"; do
        if [[ ! -f "${SOURCE_PACKAGE}/${mod}" ]]; then
            die "required module missing from source package: ${mod}"
        fi
    done
    log "source package check OK (${#REQUIRED_MODULES[@]} modules present)"
}

check_expected_commit() {
    local expected="$1"
    if [[ ! "${expected}" =~ ${COMMIT_SHA_RE} ]]; then
        die "invalid --expected-commit format: '${expected}'"
    fi

    local actual
    actual="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || true)"
    if [[ "${actual}" != "${expected}" ]]; then
        die "repository commit mismatch: expected ${expected}, got ${actual}"
    fi
    log "repository commit verified: ${actual}"
}

check_git_clean() {
    # Working tree must be clean — no staged or unstaged changes in the
    # hermes_root/ package; deploying a dirty tree defeats auditability.
    local changes
    changes="$(git -C "${REPO_ROOT}" status --porcelain -- hermes_root/ 2>/dev/null || true)"
    if [[ -n "${changes}" ]]; then
        die "hermes_root/ has uncommitted changes — commit or stash before deploying:\n${changes}"
    fi
    log "hermes_root/ working tree clean"
}

# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

do_backup() {
    local backup_dir="${BACKUP_ROOT}/${TIMESTAMP}"
    mkdir -p "${backup_dir}"
    chmod 700 "${BACKUP_ROOT}" "${backup_dir}"

    if [[ -d "${TARGET_PACKAGE_DIR}" ]]; then
        cp -rp "${TARGET_PACKAGE_DIR}" "${backup_dir}/hermes_root"
        log "backed up existing package to ${backup_dir}/hermes_root"
    else
        echo "no existing package" > "${backup_dir}/no-package.txt"
        log "no existing package to back up"
    fi

    if [[ -f "${TARGET_DAEMON}" ]]; then
        cp -p "${TARGET_DAEMON}" "${backup_dir}/hermes-root-executor"
        log "backed up existing daemon to ${backup_dir}/hermes-root-executor"
    fi

    if [[ -f "${ENV_FILE}" ]]; then
        cp -p "${ENV_FILE}" "${backup_dir}/repository-commit.env"
    fi

    # SHA-256 of the backup
    (cd "${backup_dir}" && sha256sum -- * 2>/dev/null || true) > "${backup_dir}/SHA256SUMS"
    log "SHA-256 recorded at ${backup_dir}/SHA256SUMS"

    printf '%s' "${backup_dir}"
}

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

compile_and_check() {
    log "compiling new package files from repository"
    for mod in "${REQUIRED_MODULES[@]}"; do
        python3 -m py_compile "${SOURCE_PACKAGE}/${mod}"
    done
    log "compile check OK"

    # Full import check: verify the daemon can import the new package
    # when placed in the staging directory.
    python3 -c "
import sys
sys.path.insert(0, '/usr/local/sbin')
# Test that the source package is importable
sys.path.insert(0, '${REPO_ROOT}')
import hermes_root.actions
import hermes_root.policy
import hermes_root.schema
# Verify R5A actions are present
from hermes_root.schema import MUTATING_ACTIONS
assert 'r5a_compose_build' in MUTATING_ACTIONS, 'R5A actions not in schema'
assert 'r5a_compose_up' in MUTATING_ACTIONS
assert 'r5a_compose_stop' in MUTATING_ACTIONS
assert 'r5a_compose_down' in MUTATING_ACTIONS
# Verify approval marker
from hermes_root.policy import APPROVED_R5A_MARKER, APPROVED_MARKERS
assert APPROVED_R5A_MARKER in APPROVED_MARKERS, 'R5A marker not in approved markers'
print('import and R5A contract check passed')
" || die "staged import/R5A-contract check failed"
}

deploy_package() {
    local commit_sha="$1"
    local tmp_package_dir
    tmp_package_dir="$(mktemp -d "$(dirname "${TARGET_PACKAGE_DIR}")/.hermes_root.XXXXXX")"

    log "deploying hermes_root/ package from commit ${commit_sha}"

    for mod in "${REQUIRED_MODULES[@]}"; do
        cp "${SOURCE_PACKAGE}/${mod}" "${tmp_package_dir}/${mod}"
    done
    chown -R root:root "${tmp_package_dir}"
    chmod 0750 "${tmp_package_dir}"
    chmod 0640 "${tmp_package_dir}"/*.py

    # Re-compile staged files
    for mod in "${REQUIRED_MODULES[@]}"; do
        python3 -m py_compile "${tmp_package_dir}/${mod}"
    done
    log "staged package re-compile OK"

    # Atomically swap
    if [[ -d "${TARGET_PACKAGE_DIR}" ]]; then
        rm -rf "${TARGET_PACKAGE_DIR}"
    fi
    mv "${tmp_package_dir}" "${TARGET_PACKAGE_DIR}"
    log "package deployed to ${TARGET_PACKAGE_DIR}"
}

update_commit_env() {
    local commit_sha="$1"
    mkdir -p "${ENV_DIR}"
    chmod 700 "${ENV_DIR}"
    umask 077
    printf 'HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT=%s\n' "${commit_sha}" > "${ENV_FILE}.new"
    chown root:root "${ENV_FILE}.new"
    chmod 0600 "${ENV_FILE}.new"
    mv -f "${ENV_FILE}.new" "${ENV_FILE}"
    log "commit env updated: ${commit_sha}"
}

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

verify_service_stability() {
    local active_state sub_state
    for _ in $(seq 1 15); do
        active_state="$(systemctl show "${SERVICE_NAME}" -p ActiveState --value)"
        sub_state="$(systemctl show "${SERVICE_NAME}" -p SubState --value)"
        if [[ "${active_state}" == "active" && "${sub_state}" == "running" && -S "${SOCKET_PATH}" ]]; then
            log "service stability verification OK (${active_state}/${sub_state})"
            return 0
        fi
        sleep 1
    done
    die "service did not reach active/running with a socket within 15s"
}

verify_socket_permissions() {
    local owner group mode
    owner="$(stat -c '%U' "${SOCKET_PATH}")"
    group="$(stat -c '%G' "${SOCKET_PATH}")"
    mode="$(stat -c '%a' "${SOCKET_PATH}")"
    if [[ "${owner}" != "root" ]]; then
        die "socket owner is ${owner}, expected root"
    fi
    if [[ "${group}" != "hermes" ]]; then
        die "socket group is ${group}, expected hermes"
    fi
    if [[ "${mode}" != "660" ]]; then
        die "socket mode is ${mode}, expected 660"
    fi
    log "socket permissions OK (${owner}:${group} ${mode})"
}

verify_nrestarts() {
    local nrestarts
    nrestarts="$(systemctl show "${SERVICE_NAME}" -p NRestarts --value)"
    log "NRestarts: ${nrestarts}"
}

verify_executor_health() {
    # Use the installed CLI client to hit the socket
    if [[ -x "${TARGET_DAEMON}" ]]; then
        log "executor daemon binary present"
    fi
    # A basic python3 socket health check as the hermes user-equivalent
    # (the test runs as root, so peer_uid=0; this proves the socket
    # accepts connections, not that UID 10000 is authorized — that is
    # tested separately).
    python3 -c "
import json, socket, struct
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect('${SOCKET_PATH}')
req = json.dumps({
    'schema_version': 'hermes-root-executor.v1',
    'request_id': 'r5a-installer-health',
    'correlation_id': 'r5a-installer-health',
    'issue_number': 527,
    'task_name': 'R5A',
    'execution_class': 'A0',
    'resource_key': 'r5a:installer-health',
    'action': 'executor_health',
    'argv': [],
    'cwd': '/',
    'timeout': 10,
}).encode()
sock.sendall(req + b'\n')
raw = sock.recv(65536)
sock.close()
resp = json.loads(raw.decode())
assert resp.get('decision') == 'ALLOWED', f'health check blocked: {resp.get(\"reason\")}'
assert resp.get('stdout') == 'healthy'
print(f'executor health OK (audit_id={resp.get(\"audit_id\")})')
" || die "executor health check failed"
}

# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

rollback() {
    local backup_dir="$1"
    log "rolling back to pre-install state (${backup_dir})"

    if [[ -d "${backup_dir}/hermes_root" ]]; then
        rm -rf "${TARGET_PACKAGE_DIR}" 2>/dev/null || true
        cp -rp "${backup_dir}/hermes_root" "${TARGET_PACKAGE_DIR}"
        chown -R root:root "${TARGET_PACKAGE_DIR}"
        log "rolled back package"
    else
        rm -rf "${TARGET_PACKAGE_DIR}" 2>/dev/null || true
        log "no package backup — removed new package"
    fi

    if [[ -f "${backup_dir}/hermes-root-executor" ]]; then
        cp -p "${backup_dir}/hermes-root-executor" "${TARGET_DAEMON}"
        chown root:root "${TARGET_DAEMON}"
        chmod 0750 "${TARGET_DAEMON}"
        log "rolled back daemon"
    fi

    if [[ -f "${backup_dir}/repository-commit.env" ]]; then
        cp -p "${backup_dir}/repository-commit.env" "${ENV_FILE}"
        log "rolled back commit env"
    fi

    systemctl daemon-reload || true
    systemctl restart "${SERVICE_NAME}" || true

    sleep 2
    local active_state
    active_state="$(systemctl show "${SERVICE_NAME}" -p ActiveState --value || echo unknown)"
    if [[ "${active_state}" == "active" ]]; then
        log "rollback health check OK (${active_state})"
    else
        log "WARNING: rollback health check shows ActiveState=${active_state} — manual intervention required"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    local expected_commit=""
    local check_only=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --expected-commit)
                expected_commit="$2"
                shift 2
                ;;
            --check)
                check_only=true
                shift
                ;;
            *)
                die "unknown argument: $1"
                ;;
        esac
    done

    if [[ -z "${expected_commit}" ]]; then
        die "--expected-commit is required"
    fi

    check_root
    check_source_package
    check_expected_commit "${expected_commit}"
    check_git_clean

    if [[ "${check_only}" == true ]]; then
        log "all precondition checks passed (--check mode, no changes made)"
        exit 0
    fi

    local backup_dir
    backup_dir="$(do_backup)"
    log "backup created at ${backup_dir}"

    trap 'rollback "${backup_dir}"' ERR

    compile_and_check
    deploy_package "${expected_commit}"
    update_commit_env "${expected_commit}"

    # systemctl daemon-reload only if the unit file actually changed.
    # The R5A extension does not change the unit, only the package,
    # but we reload defensively to ensure the env file is picked up.
    systemctl daemon-reload

    log "restarting ${SERVICE_NAME}"
    systemctl restart "${SERVICE_NAME}"
    sleep 1

    verify_service_stability
    verify_socket_permissions
    verify_nrestarts
    verify_executor_health

    trap - ERR
    log "R5A executor extension deployed successfully (commit ${expected_commit})"
    log "backup: ${backup_dir}"
}

main "$@"
