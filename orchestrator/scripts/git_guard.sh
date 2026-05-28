#!/usr/bin/env bash
set -euo pipefail

# git_guard.sh — Pre-commit sanity check for trading-hub
# Verifies: correct user, ownership, SSH key perms, no runtime-state leakage

ERRORS=0

# 1) User check
CURRENT_USER=$(whoami)
if [[ "$CURRENT_USER" != "hermes" ]]; then
  echo "FAIL: Running as '$CURRENT_USER', expected 'hermes'"
  ERRORS=$((ERRORS + 1))
else
  echo "OK:   Running as hermes"
fi

# 2) Ownership check on project dir
BAD_OWNERS=$(find . -maxdepth 3 -not -user hermes -o -not -group hermes 2>/dev/null | head -5)
if [[ -n "$BAD_OWNERS" ]]; then
  echo "FAIL: Files not owned by hermes:hermes:"
  echo "$BAD_OWNERS"
  ERRORS=$((ERRORS + 1))
else
  echo "OK:   All files owned by hermes:hermes"
fi

# 3) SSH key permissions
SSH_KEY=".ssh_local/id_ed25519_trading_hub"
if [[ -f "$SSH_KEY" ]]; then
  KEY_PERM=$(stat -c %a "$SSH_KEY")
  if [[ "$KEY_PERM" != "600" ]]; then
    echo "WARN: SSH key permissions are $KEY_PERM, fixing to 600"
    chmod 600 "$SSH_KEY"
  else
    echo "OK:   SSH key permissions 600"
  fi
else
  echo "OK:   No local SSH key (using agent or default path)"
fi

# 4) Forbidden runtime-state files (should NOT be committed)
FORBIDDEN_PATTERNS=(
  "primo_signal_state.json"
  "decisions.jsonl"
  "*/user_data/*.json"
  "tradesv3.sqlite"
  "*.sqlite-wal"
  "*.sqlite-shm"
)

STAGED_FORBIDDEN=""
for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
  FOUND=$(git diff --cached --name-only 2>/dev/null | grep -E "$pattern" || true)
  if [[ -n "$FOUND" ]]; then
    STAGED_FORBIDDEN="$STAGED_FORBIDDEN\n$FOUND"
  fi
done

if [[ -n "$STAGED_FORBIDDEN" ]]; then
  echo "FAIL: Forbidden runtime-state files are staged:"
  echo -e "$STAGED_FORBIDDEN"
  ERRORS=$((ERRORS + 1))
else
  echo "OK:   No forbidden runtime-state files staged"
fi

# 5) .git directory ownership
GIT_OWNER=$(stat -c %U .git 2>/dev/null || echo "unknown")
if [[ "$GIT_OWNER" != "hermes" ]]; then
  echo "FAIL: .git owned by '$GIT_OWNER', expected 'hermes'"
  ERRORS=$((ERRORS + 1))
else
  echo "OK:   .git owned by hermes"
fi

# Summary
echo "---"
if [[ $ERRORS -eq 0 ]]; then
  echo "PASS: All checks OK"
  exit 0
else
  echo "FAIL: $ERRORS check(s) failed — fix before committing"
  exit 1
fi
