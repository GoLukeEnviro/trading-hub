#!/usr/bin/env bash
# Installation contract for the repository-sourced hermes-root-executor daemon.
#
# This script documents and automates the deployment path from
# hermes_root/daemon.py to the production host artifact
# /usr/local/sbin/hermes-root-executor. It is intentionally NOT executed as
# part of the H3B daemon source-migration change (Issue #531) — deployment is
# a separate, explicitly-gated rollout decision.
#
# Usage: sudo ./scripts/install-hermes-root-executor.sh
#
# What it does, in order:
#   1. Resolve and print the repository commit being installed.
#   2. Syntax/import-check the daemon module (python3 -m py_compile).
#   3. Refuse to continue if the check fails.
#   4. Back up the currently installed daemon (timestamped copy).
#   5. Write the new daemon to a temporary file in the same filesystem.
#   6. Atomically rename the temp file onto the target path.
#   7. Set ownership root:root and mode 0750 on the target.
#   8. Restart hermes-root-executor.service only after the above succeeded.
#   9. On any failure, roll back to the backed-up file automatically.
#
# What it deliberately does NOT do:
#   - Does not touch /opt/data/hermes/audit/runtime-actions.jsonl (append-only,
#     never deleted or rotated by this script).
#   - Does not modify any docker-compose file.
#   - Does not recreate or restart the Hermes agent container.
#   - Does not change socket permissions, kill-switch state, or systemd unit
#     files beyond the daemon binary itself.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_FILE="${REPO_ROOT}/hermes_root/daemon.py"
TARGET_FILE="/usr/local/sbin/hermes-root-executor"
SERVICE_NAME="hermes-root-executor.service"
BACKUP_DIR="/root/backups/hermes-root-executor-installs"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: this script must run as root (it writes to ${TARGET_FILE} and manages a root systemd service)." >&2
  exit 1
fi

if [[ ! -f "${SOURCE_FILE}" ]]; then
  echo "ERROR: source file not found: ${SOURCE_FILE}" >&2
  exit 1
fi

REPO_COMMIT="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)"
echo "Installing hermes_root/daemon.py from commit: ${REPO_COMMIT}"

echo "Step 1/6: syntax/import check"
python3 -m py_compile "${SOURCE_FILE}"
echo "  OK"

mkdir -p "${BACKUP_DIR}"
if [[ -f "${TARGET_FILE}" ]]; then
  BACKUP_FILE="${BACKUP_DIR}/hermes-root-executor.${TIMESTAMP}.bak"
  echo "Step 2/6: backing up existing daemon to ${BACKUP_FILE}"
  cp -p "${TARGET_FILE}" "${BACKUP_FILE}"
else
  BACKUP_FILE=""
  echo "Step 2/6: no existing daemon at ${TARGET_FILE}, nothing to back up"
fi

echo "Step 3/6: writing new daemon to temporary file"
TMP_FILE="$(mktemp "$(dirname "${TARGET_FILE}")/.hermes-root-executor.XXXXXX")"
trap 'rm -f "${TMP_FILE}"' EXIT

{
  echo "#!/usr/bin/env python3"
  echo "# Installed from trading-hub commit ${REPO_COMMIT} at ${TIMESTAMP}"
  tail -n +1 "${SOURCE_FILE}"
} > "${TMP_FILE}"

chown root:root "${TMP_FILE}"
chmod 0750 "${TMP_FILE}"

echo "Step 4/6: re-checking the staged file before activation"
python3 -m py_compile "${TMP_FILE}"

echo "Step 5/6: atomically moving into place"
mv -f "${TMP_FILE}" "${TARGET_FILE}"
trap - EXIT

echo "Step 6/6: restarting ${SERVICE_NAME}"
if systemctl restart "${SERVICE_NAME}"; then
  sleep 1
  if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "SUCCESS: ${SERVICE_NAME} is active with commit ${REPO_COMMIT}"
    exit 0
  fi
fi

echo "ERROR: service failed to become active after restart — rolling back" >&2
if [[ -n "${BACKUP_FILE}" ]]; then
  cp -p "${BACKUP_FILE}" "${TARGET_FILE}"
  chown root:root "${TARGET_FILE}"
  chmod 0750 "${TARGET_FILE}"
  systemctl restart "${SERVICE_NAME}" || true
  echo "Rolled back to ${BACKUP_FILE}" >&2
else
  echo "No backup existed — manual recovery required." >&2
fi
exit 1
