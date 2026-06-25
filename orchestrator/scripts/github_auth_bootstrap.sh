#!/usr/bin/env bash
# github_auth_bootstrap.sh — local-only GitHub auth bootstrap for Hermes / Trading Hub.
#
# This script creates and validates local secret files. It does NOT commit the
# token. The real GitHub token must be pasted into:
#
#   /opt/data/profiles/orchestrator/secrets/github.env
#
# by a human after running --init.
#
# Safety: never print the token, never write secrets into tracked files.
set -euo pipefail

SECRETS_DIR="/opt/data/profiles/orchestrator/secrets"
ENV_FILE="${SECRETS_DIR}/github.env"
REPO_FILE="${SECRETS_DIR}/github-repositories.json"

PLACEHOLDER_TOKEN="PASTE_FINE_GRAINED_GITHUB_TOKEN_HERE"

usage() {
  cat <<'EOF'
Usage: github_auth_bootstrap.sh [--init|--check|--print-source-command|--print-edit-command|--print-repo-edit-command]

  --init                  Create secret files if missing and set permissions.
  --check                 Validate that a real token is present and repo list exists.
  --print-source-command  Print the shell command to source the env file.
  --print-edit-command    Print the command to edit the token file.
  --print-repo-edit-command  Print the command to edit the repository list.
EOF
  exit 1
}

ensure_secrets_dir() {
  if [[ ! -d "${SECRETS_DIR}" ]]; then
    mkdir -p "${SECRETS_DIR}"
    chmod 700 "${SECRETS_DIR}"
    if id -u hermes &>/dev/null && getent group hermes &>/dev/null; then
      chown hermes:hermes "${SECRETS_DIR}" || true
    fi
  fi
}

write_env_file_if_missing() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    cat >"${ENV_FILE}" <<'EOF'
# Local-only GitHub auth for Hermes / Trading Hub.
# Never commit this file.
# Paste a fine-grained GitHub token below.

GITHUB_TOKEN=PASTE_FINE_GRAINED_GITHUB_TOKEN_HERE
GH_TOKEN="${GITHUB_TOKEN}"

# Default repository used when no explicit repo is passed.
GITHUB_REPOSITORY=GoLukeEnviro/trading-hub
EOF
    chmod 600 "${ENV_FILE}"
    if id -u hermes &>/dev/null && getent group hermes &>/dev/null; then
      chown hermes:hermes "${ENV_FILE}" || true
    fi
  fi
}

write_repo_file_if_missing() {
  if [[ ! -f "${REPO_FILE}" ]]; then
    cat >"${REPO_FILE}" <<'EOF'
{
  "default_repository": "GoLukeEnviro/trading-hub",
  "repositories": [
    {
      "name": "GoLukeEnviro/trading-hub",
      "role": "main_trading_hub",
      "required": true
    },
    {
      "name": "GoLukeEnviro/ai4trade-bot",
      "role": "ai_for_trade_bot",
      "required": true
    },
    {
      "name": "GoLukeEnviro/TradeAgentsView_Control_Center",
      "role": "control_center",
      "required": false
    },
    {
      "name": "GoLukeEnviro/Algorithmisches_Trading",
      "role": "algorithmic_trading_archive_or_side_repo",
      "required": false
    }
  ]
}
EOF
    chmod 600 "${REPO_FILE}"
    if id -u hermes &>/dev/null && getent group hermes &>/dev/null; then
      chown hermes:hermes "${REPO_FILE}" || true
    fi
  fi
}

check_token_present() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: ${ENV_FILE} missing. Run: bash orchestrator/scripts/github_auth_bootstrap.sh --init"
    return 1
  fi

  # shellcheck disable=SC1090
  set -a
  # Intentionally do not source the token value anywhere else.
  # shellcheck disable=SC1090
  source "${ENV_FILE}" >/dev/null 2>&1 || true
  set +a

  local token="${GITHUB_TOKEN:-}"
  if [[ -z "${token}" ]]; then
    token="${GH_TOKEN:-}"
  fi

  if [[ -z "${token}" || "${token}" == "${PLACEHOLDER_TOKEN}" || "${token}" == *'${'* ]]; then
    echo "ERROR: GitHub token is missing or still the placeholder."
    echo "Edit the token file: nano /opt/data/profiles/orchestrator/secrets/github.env"
    return 1
  fi

  return 0
}

check_repo_file() {
  if [[ ! -f "${REPO_FILE}" ]]; then
    echo "ERROR: ${REPO_FILE} missing. Run: bash orchestrator/scripts/github_auth_bootstrap.sh --init"
    return 1
  fi
  if ! python3 -m json.tool "${REPO_FILE}" >/dev/null 2>&1; then
    echo "ERROR: ${REPO_FILE} is not valid JSON."
    echo "Edit the repo list: nano /opt/data/profiles/orchestrator/secrets/github-repositories.json"
    return 1
  fi
  return 0
}

main() {
  local mode="${1:-}"

  case "${mode}" in
    --init)
      ensure_secrets_dir
      write_env_file_if_missing
      write_repo_file_if_missing
      echo "Local GitHub auth files prepared."
      echo "Edit the token file: nano /opt/data/profiles/orchestrator/secrets/github.env"
      echo "Edit the repo list: nano /opt/data/profiles/orchestrator/secrets/github-repositories.json"
      if check_token_present; then
        echo "Token appears to be configured."
      else
        exit 1
      fi
      ;;
    --check)
      ensure_secrets_dir
      if ! check_token_present; then
        exit 1
      fi
      if ! check_repo_file; then
        exit 1
      fi
      echo "Local GitHub auth files are present and token is not the placeholder."
      echo "Run the access check: python3 orchestrator/scripts/github_repo_access_check.py"
      ;;
    --print-source-command)
      echo "set -a; source /opt/data/profiles/orchestrator/secrets/github.env; set +a"
      ;;
    --print-edit-command)
      echo "nano /opt/data/profiles/orchestrator/secrets/github.env"
      ;;
    --print-repo-edit-command)
      echo "nano /opt/data/profiles/orchestrator/secrets/github-repositories.json"
      ;;
    *)
      usage
      ;;
  esac
}

main "$@"
