#!/usr/bin/env bash
# Transactional installer for the hermes-root-executor.service systemd
# group-permission fix (Issue #531 / H3B).
#
# Codifies the live host fix applied on 2026-07-13: the executor's runtime
# directory and socket were root:root, denying Hermes (UID/GID 10000) any
# access despite the daemon's own allowlist already including it. This
# installer applies the fix via a systemd drop-in rather than editing the
# unit file directly, and is safe to re-run (idempotent: reinstalling the
# same drop-in content and restarting is a no-op from the daemon's
# perspective beyond a clean restart).
#
# Usage: sudo ./ops/systemd/install-hermes-executor-permissions-fix.sh
#        sudo ./ops/systemd/install-hermes-executor-permissions-fix.sh --check
#
# --check performs only the precondition checks (root, hermes GID) and
# exits without installing, reloading, or restarting anything — safe to
# run repeatedly to validate host readiness.
#
# What it does, in order:
#   1. Verify running as root.
#   2. Verify the "hermes" group exists with exactly GID 10000.
#   3. Back up the active unit file and all existing drop-ins.
#   4. Install the drop-in atomically as root:root 0644.
#   5. Run systemctl daemon-reload.
#   6. Verify the merged unit now reports Group=hermes.
#   7. Restart hermes-root-executor.service (only this service).
#   8. Verify the runtime directory and socket are root:hermes with the
#      expected mode.
#   9. Verify the service is active/running and the socket is reachable.
#  10. On any failure after step 4, restore the previous drop-in state
#      and validate rollback health before exiting non-zero.
#
# What it deliberately does NOT do:
#   - Does not touch the daemon binary or the hermes_root/ package.
#   - Does not modify Docker, compose files, or the Hermes container.
#   - Does not change User= (stays root) or RuntimeDirectory= name.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DROPIN_SOURCE="${REPO_ROOT}/ops/systemd/hermes-root-executor.service.d/10-hermes-group-permissions.conf"
SERVICE_NAME="hermes-root-executor.service"
DROPIN_DIR="/etc/systemd/system/${SERVICE_NAME}.d"
DROPIN_TARGET="${DROPIN_DIR}/10-hermes-group-permissions.conf"
RUNTIME_DIR="/run/hermes-root-executor"
SOCKET_PATH="${RUNTIME_DIR}/executor.sock"
REQUIRED_GID="10000"
BACKUP_ROOT="/root/backups/hermes-root-executor-permissions-fix"

log() { printf '[permissions-fix] %s\n' "$1"; }
die() { printf '[permissions-fix] ERROR: %s\n' "$1" >&2; exit 1; }

check_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        die "must run as root"
    fi
    log "root check OK"
}

check_hermes_gid() {
    local entry gid
    entry="$(getent group hermes || true)"
    if [[ -z "${entry}" ]]; then
        die "group 'hermes' does not exist on this host"
    fi
    gid="$(printf '%s' "${entry}" | cut -d: -f3)"
    if [[ "${gid}" != "${REQUIRED_GID}" ]]; then
        die "group 'hermes' has GID ${gid}, expected ${REQUIRED_GID}"
    fi
    log "hermes group GID check OK (${gid})"
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

    if [[ -f "/etc/systemd/system/${SERVICE_NAME}" ]]; then
        cp -p "/etc/systemd/system/${SERVICE_NAME}" "${backup_dir}/"
    fi
    if [[ -d "${DROPIN_DIR}" ]]; then
        cp -a "${DROPIN_DIR}" "${backup_dir}/service.d"
    else
        echo "no pre-existing drop-in directory" > "${backup_dir}/no-dropins.txt"
    fi

    printf '%s' "${backup_dir}"
}

install_dropin() {
    mkdir -p "${DROPIN_DIR}"
    install -o root -g root -m 0644 "${DROPIN_SOURCE}" "${DROPIN_TARGET}.new"
    mv -f "${DROPIN_TARGET}.new" "${DROPIN_TARGET}"
    log "drop-in installed at ${DROPIN_TARGET}"
}

verify_merged_unit() {
    local group
    group="$(systemctl show "${SERVICE_NAME}" -p Group --value)"
    if [[ "${group}" != "hermes" ]]; then
        die "merged unit Group is '${group}', expected 'hermes'"
    fi
    log "merged unit verification OK (Group=${group})"
}

verify_ownership() {
    local dir_owner sock_owner dir_mode sock_mode
    dir_owner="$(stat -c '%U:%G' "${RUNTIME_DIR}")"
    dir_mode="$(stat -c '%a' "${RUNTIME_DIR}")"
    sock_owner="$(stat -c '%U:%G' "${SOCKET_PATH}")"
    sock_mode="$(stat -c '%a' "${SOCKET_PATH}")"

    if [[ "${dir_owner}" != "root:hermes" || "${dir_mode}" != "750" ]]; then
        die "runtime directory is ${dir_owner} ${dir_mode}, expected root:hermes 750"
    fi
    if [[ "${sock_owner}" != "root:hermes" || "${sock_mode}" != "660" ]]; then
        die "socket is ${sock_owner} ${sock_mode}, expected root:hermes 660"
    fi
    log "ownership verification OK (${dir_owner} ${dir_mode} / ${sock_owner} ${sock_mode})"
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
    die "service did not reach active/running with a socket within 15s"
}

rollback() {
    local backup_dir="$1"
    log "rolling back to pre-install state (${backup_dir})"

    rm -f "${DROPIN_TARGET}"
    if [[ -d "${backup_dir}/service.d" ]]; then
        cp -a "${backup_dir}/service.d/." "${DROPIN_DIR}/" 2>/dev/null || true
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
    check_hermes_gid
    check_source_dropin

    if [[ "${1:-}" == "--check" ]]; then
        log "precondition check passed, no changes made (--check mode)"
        exit 0
    fi

    local backup_dir
    backup_dir="$(do_backup)"
    log "backup created at ${backup_dir}"

    trap 'rollback "${backup_dir}"' ERR

    install_dropin
    systemctl daemon-reload
    verify_merged_unit
    systemctl restart "${SERVICE_NAME}"
    verify_ownership
    verify_service_stability

    trap - ERR
    log "install complete: ${SERVICE_NAME} is root:hermes, active/running"
}

main "$@"
