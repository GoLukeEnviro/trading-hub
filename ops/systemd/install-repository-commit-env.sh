#!/usr/bin/env bash
# Transactional installer for the hermes-root-executor.service repository-
# commit traceability fix (Issue #531 / H3B).
#
# Before this fix, every audit entry logged repository_commit="unknown"
# because RootExecutorDaemon() was always constructed with its default —
# nothing ever told the daemon what commit was actually deployed. This
# installer writes the *currently checked-out repository commit* into a
# root-owned environment file that systemd loads via EnvironmentFile=, and
# hermes_root.daemon.main() now fails closed if that value is missing or
# malformed (see hermes_root/daemon.py).
#
# Usage: sudo ./ops/systemd/install-repository-commit-env.sh
#        sudo ./ops/systemd/install-repository-commit-env.sh --check
#
# --check performs only the precondition checks and exits without writing
# or restarting anything.
#
# What it does, in order:
#   1. Verify running as root.
#   2. Resolve the repository's current commit SHA and validate its shape.
#   3. Back up the active unit's drop-ins and any existing env file.
#   4. Install the EnvironmentFile= drop-in atomically as root:root 0644.
#   5. Write the commit env file atomically as root:root 0600 (not group-
#      or world-readable — the file only ever contains a commit SHA today,
#      but the pattern should default to closed).
#   6. Run systemctl daemon-reload.
#   7. Restart hermes-root-executor.service (only this service).
#   8. Verify the service is active/running and the socket is reachable.
#   9. On any failure after step 4, restore the previous state and
#      validate rollback health before exiting non-zero.
#
# What it deliberately does NOT do:
#   - Does not deploy the daemon binary or the hermes_root/ package itself
#     (that remains scripts/install-hermes-root-executor.sh's job).
#   - Does not modify the group-permissions drop-in
#     (10-hermes-group-permissions.conf, installed separately).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DROPIN_SOURCE="${REPO_ROOT}/ops/systemd/hermes-root-executor.service.d/20-repository-commit.conf"
SERVICE_NAME="hermes-root-executor.service"
DROPIN_DIR="/etc/systemd/system/${SERVICE_NAME}.d"
DROPIN_TARGET="${DROPIN_DIR}/20-repository-commit.conf"
ENV_DIR="/etc/hermes-root-executor"
ENV_FILE="${ENV_DIR}/repository-commit.env"
SOCKET_PATH="/run/hermes-root-executor/executor.sock"
BACKUP_ROOT="/root/backups/hermes-root-executor-repository-commit"
COMMIT_SHA_RE='^[0-9a-f]{7,40}$'

log() { printf '[repository-commit] %s\n' "$1"; }
die() { printf '[repository-commit] ERROR: %s\n' "$1" >&2; exit 1; }

check_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        die "must run as root"
    fi
    log "root check OK"
}

resolve_commit() {
    local sha
    sha="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || true)"
    if [[ ! "${sha}" =~ ${COMMIT_SHA_RE} ]]; then
        die "could not resolve a valid commit SHA from ${REPO_ROOT} (got: '${sha}')"
    fi
    printf '%s' "${sha}"
}

check_source_dropin() {
    if [[ ! -f "${DROPIN_SOURCE}" ]]; then
        die "drop-in source not found at ${DROPIN_SOURCE}"
    fi
}

do_backup() {
    local stamp backup_dir
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    backup_dir="${BACKUP_ROOT}/${stamp}"
    mkdir -p "${backup_dir}"
    chmod 700 "${BACKUP_ROOT}" "${backup_dir}"

    if [[ -d "${DROPIN_DIR}" ]]; then
        cp -a "${DROPIN_DIR}" "${backup_dir}/service.d"
    fi
    if [[ -f "${ENV_FILE}" ]]; then
        cp -p "${ENV_FILE}" "${backup_dir}/repository-commit.env"
    else
        echo "no pre-existing env file" > "${backup_dir}/no-env-file.txt"
    fi

    printf '%s' "${backup_dir}"
}

install_dropin_and_env() {
    local commit_sha="$1"

    mkdir -p "${DROPIN_DIR}"
    install -o root -g root -m 0644 "${DROPIN_SOURCE}" "${DROPIN_TARGET}.new"
    mv -f "${DROPIN_TARGET}.new" "${DROPIN_TARGET}"
    log "drop-in installed at ${DROPIN_TARGET}"

    mkdir -p "${ENV_DIR}"
    chmod 700 "${ENV_DIR}"
    umask 077
    printf 'HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT=%s\n' "${commit_sha}" > "${ENV_FILE}.new"
    chown root:root "${ENV_FILE}.new"
    chmod 0600 "${ENV_FILE}.new"
    mv -f "${ENV_FILE}.new" "${ENV_FILE}"
    log "env file written at ${ENV_FILE} (commit ${commit_sha})"
}

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
    die "service did not reach active/running with a socket within 15s (check: is the env file valid?)"
}

rollback() {
    local backup_dir="$1"
    log "rolling back to pre-install state (${backup_dir})"

    rm -f "${DROPIN_TARGET}" "${ENV_FILE}"
    if [[ -d "${backup_dir}/service.d" ]]; then
        cp -a "${backup_dir}/service.d/." "${DROPIN_DIR}/" 2>/dev/null || true
    fi
    if [[ -f "${backup_dir}/repository-commit.env" ]]; then
        cp -p "${backup_dir}/repository-commit.env" "${ENV_FILE}"
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

main() {
    check_root
    check_source_dropin
    local commit_sha
    commit_sha="$(resolve_commit)"
    log "resolved repository commit: ${commit_sha}"

    if [[ "${1:-}" == "--check" ]]; then
        log "precondition check passed, no changes made (--check mode)"
        exit 0
    fi

    local backup_dir
    backup_dir="$(do_backup)"
    log "backup created at ${backup_dir}"

    trap 'rollback "${backup_dir}"' ERR

    install_dropin_and_env "${commit_sha}"
    systemctl daemon-reload
    systemctl restart "${SERVICE_NAME}"
    verify_service_stability

    trap - ERR
    log "install complete: ${SERVICE_NAME} running with repository_commit=${commit_sha}"
}

main "$@"
