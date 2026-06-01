#!/usr/bin/env bash
# deploy_cron_scripts.sh — Deploy Git-tracked scripts to active cron runtime
#
# Usage:
#   bash orchestrator/scripts/deploy_cron_scripts.sh          # deploy all
#   bash orchestrator/scripts/deploy_cron_scripts.sh --check  # check drift only
#   bash orchestrator/scripts/deploy_cron_scripts.sh --list   # list active scripts
#
# Source of truth: /home/hermes/projects/trading/orchestrator/scripts/
# Runtime target: /opt/data/profiles/orchestrator/scripts/
#
# Ownership contract:
#   Source: 1337:1337 775 (git-tracked)
#   Target: hermes:hermes (10000:10000) 711 (deployed, executable)
#
# This script NEVER:
#   - Creates new files (only overwrites existing ones)
#   - Deletes files from runtime dir
#   - chmod 777
#   - chown recursively over the project tree
set -euo pipefail

PROJECT_DIR="/home/hermes/projects/trading"
SRC="$PROJECT_DIR/orchestrator/scripts"
DST="/opt/data/profiles/orchestrator/scripts"

# Active scripts from jobs.json
JOBS_JSON="/opt/data/profiles/orchestrator/cron/jobs.json"
DEPLOY_UID=10000
DEPLOY_GID=10000
DEPLOY_MODE=711

ok=0
warn=0
fail=0

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

get_active_scripts() {
    if [ -f "$JOBS_JSON" ]; then
        python3 -c "
import json, sys
try:
    with open('$JOBS_JSON') as f:
        data = json.load(f)
    jobs = data.get('jobs', [])
    for j in jobs:
        s = j.get('script', '')
        if s:
            print(s.split('/')[-1])
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null
    else
        echo "ERROR: $JOBS_JSON not found" >&2
        exit 1
    fi
}

check_drift() {
    echo "=== Drift Report $(ts) ==="
    active=$(get_active_scripts)
    drift_count=0
    cron_only=0
    missing_in_src=0

    for script in $active; do
        src_file="$SRC/$script"
        dst_file="$DST/$script"

        if [ ! -f "$src_file" ]; then
            echo "  CRON_ONLY: $script (NOT in Git — violation!)"
            cron_only=$((cron_only + 1))
            continue
        fi

        if [ ! -f "$dst_file" ]; then
            echo "  MISSING_IN_RUNTIME: $script"
            missing_in_src=$((missing_in_src + 1))
            continue
        fi

        diff_lines=$(diff "$src_file" "$dst_file" 2>/dev/null | wc -l)
        if [ "$diff_lines" -gt 0 ]; then
            echo "  DRIFT ($diff_lines lines): $script"
            drift_count=$((drift_count + 1))
        fi
    done

    echo ""
    echo "  Total active scripts: $(echo "$active" | wc -w)"
    echo "  Drift: $drift_count"
    echo "  CRON_ONLY (not in Git): $cron_only"
    echo "  Missing in runtime: $missing_in_src"

    if [ "$cron_only" -gt 0 ]; then
        echo ""
        echo "  FAIL: $cron_only script(s) not tracked in Git. Fix before deploying."
        return 1
    fi
    return 0
}

deploy() {
    echo "=== Deploy $(ts) ==="
    active=$(get_active_scripts)

    # Pre-flight: fail if any CRON_ONLY scripts exist
    for script in $active; do
        src_file="$SRC/$script"
        if [ ! -f "$src_file" ]; then
            echo "FAIL: $script is active in jobs.json but NOT in Git ($SRC)"
            echo "  Fix: cp $DST/$script $SRC/$script && chown 1337:1337 $SRC/$script"
            exit 1
        fi
    done

    for script in $active; do
        src_file="$SRC/$script"
        dst_file="$DST/$script"

        # Only overwrite existing files (never create new)
        if [ ! -f "$dst_file" ]; then
            echo "  SKIP (not in runtime): $script"
            warn=$((warn + 1))
            continue
        fi

        # Check if already matches
        diff_lines=$(diff "$src_file" "$dst_file" 2>/dev/null | wc -l)
        if [ "$diff_lines" -eq 0 ]; then
            ok=$((ok + 1))
            continue
        fi

        # Deploy
        cp "$src_file" "$dst_file"
        chown "$DEPLOY_UID:$DEPLOY_GID" "$dst_file" 2>/dev/null || true
        chmod "$DEPLOY_MODE" "$dst_file" 2>/dev/null || true

        # Verify
        verify_lines=$(diff "$src_file" "$dst_file" 2>/dev/null | wc -l)
        if [ "$verify_lines" -eq 0 ]; then
            owner=$(stat -c '%u:%g' "$dst_file" 2>/dev/null)
            mode=$(stat -c '%a' "$dst_file" 2>/dev/null)
            echo "  DEPLOYED: $script (owner=$owner mode=$mode)"
            ok=$((ok + 1))
        else
            echo "  VERIFY_FAIL: $script (still $verify_lines lines different after copy)"
            fail=$((fail + 1))
        fi
    done

    echo ""
    echo "  Deployed: $ok"
    echo "  Warnings: $warn"
    echo "  Failures: $fail"

    if [ "$fail" -gt 0 ]; then
        echo ""
        echo "  FAIL: $fail script(s) failed verification."
        exit 1
    fi
}

case "${1:-}" in
    --check)
        check_drift
        ;;
    --list)
        echo "Active scripts in jobs.json:"
        get_active_scripts | sort
        ;;
    "")
        deploy
        ;;
    *)
        echo "Usage: $0 [--check|--list]" >&2
        exit 1
        ;;
esac
