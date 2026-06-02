#!/usr/bin/env bash
# permission_autopilot.sh — selective host-mount ownership stabilizer
#
# Host-only tool. Run as root on the VPS host.
# Default mode is report-only. Summary mode is intended for cron.
# Apply mode only fixes explicit runtime mount roots.

set -euo pipefail

TARGET_UID=10000
TARGET_GID=10000
LOCKFILE="/home/hermes/logs/permission-autopilot.lock"
LOGFILE="/var/log/permission-autopilot.log"

# Paths whose drift we only report because other contracts already manage them.
REPORT_ONLY_ROOTS=(
    "/opt/data/profiles/orchestrator/cron"
    "/opt/data/profiles/orchestrator/scripts"
)

# Paths this tool may remediate when --apply is used.
APPLY_ROOTS=(
    "/home/hermes/projects/trading/ai-hedge-fund-crypto/output"
    "/home/hermes/projects/trading/freqtrade/shared"
    "/home/hermes/projects/trading/freqtrade/logs"
    "/home/hermes/projects/trading/orchestrator/logs"
    "/home/hermes/projects/trading/orchestrator/state"
)

usage() {
    cat <<'EOF'
Usage: permission_autopilot.sh [--check|--summary|--apply|--list]

  --check   Report ownership drift only (default)
  --summary  Report only severity summaries, no sample lines
  --apply   Fix only safe ownership drift on explicit runtime mount roots
  --list    Print managed paths
EOF
}

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() {
    local line
    line=$(printf '[%s] PERM_AUTOPILOT %s' "$(ts)" "$*")
    printf '%s\n' "$line"
    if [ "$(id -u)" -eq 0 ]; then
        printf '%s\n' "$line" >> "$LOGFILE" 2>/dev/null || true
    fi
}

is_root() {
    [ "$(id -u)" -eq 0 ]
}

has_lsof() {
    command -v lsof >/dev/null 2>&1
}

safe_find() {
    find "$@" 2>/dev/null || true
}

is_open() {
    if ! has_lsof; then
        return 1
    fi
    lsof -- "$1" >/dev/null 2>&1
}

classify_root() {
    case "$1" in
        "/opt/data/profiles/orchestrator/cron"|"/opt/data/profiles/orchestrator/scripts")
            printf '%s' "WARN"
            ;;
        "/home/hermes/projects/trading/ai-hedge-fund-crypto/output"|"/home/hermes/projects/trading/freqtrade/shared"|"/home/hermes/projects/trading/freqtrade/logs"|"/home/hermes/projects/trading/orchestrator/logs"|"/home/hermes/projects/trading/orchestrator/state")
            printf '%s' "CRITICAL"
            ;;
        *)
            printf '%s' "WARN"
            ;;
    esac
}

should_repair_item() {
    local root="$1"
    local item="$2"

    if [ "$item" = "$root" ]; then
        return 0
    fi

    case "$root" in
        "/home/hermes/projects/trading/ai-hedge-fund-crypto/output"|"/home/hermes/projects/trading/freqtrade/logs"|"/home/hermes/projects/trading/orchestrator/logs")
            return 0
            ;;
        "/home/hermes/projects/trading/freqtrade/shared")
            case "$item" in
                "$root"/*.json|"$root"/*.jsonl|"$root"/*.log|"$root"/*.txt|"$root"/*.csv|"$root"/*.lock|"$root"/*.feather|"$root"/*.parquet|"$root"/*.md|"$root"/config/*|"$root"/downloads/*|"$root"/images/*|"$root"/logs/*|"$root"/signals/*|"$root"/strategies/*)
                    return 0
                    ;;
            esac
            return 1
            ;;
        "/home/hermes/projects/trading/orchestrator/state")
            case "$item" in
                "$root"/*.json|"$root"/*.jsonl|"$root"/*.log|"$root"/*.txt|"$root"/*.csv|"$root"/*.lock|"$root"/*.md|"$root"/*.yaml|"$root"/*.yml|"$root"/config_diff/*|"$root"/riskguard/*|"$root"/auto_params/*|"$root"/standby/*)
                    return 0
                    ;;
            esac
            return 1
            ;;
    esac

    return 1
}

print_list() {
    printf '%s\n' "${REPORT_ONLY_ROOTS[@]}" "${APPLY_ROOTS[@]}"
}

scan_root() {
    local root="$1"
    local detail="$2"
    if [ ! -d "$root" ]; then
        log "SKIP missing root=$root"
        return 0
    fi

    local severity total root_owned target_owned sample
    severity=$(classify_root "$root")
    total=$(safe_find "$root" -xdev \( -type f -o -type d \) | wc -l | tr -d ' ')
    root_owned=$(safe_find "$root" -xdev \( -uid 0 -o -uid 1337 \) | wc -l | tr -d ' ')
    target_owned=$(safe_find "$root" -xdev -uid "$TARGET_UID" | wc -l | tr -d ' ')

    log "SCAN severity=$severity root=$root total=$total drift_uid0_1337=$root_owned target_uid=$target_owned"

    if [ "$detail" -eq 1 ]; then
        sample=$(safe_find "$root" -xdev \( -uid 0 -o -uid 1337 \) | head -n 5 || true)
        if [ -n "$sample" ]; then
            while IFS= read -r item; do
                [ -n "$item" ] || continue
                stat -c 'SAMPLE %u:%g %a %n' "$item" 2>/dev/null || true
            done <<EOF
$sample
EOF
        fi
    fi
}

apply_root() {
    local root="$1"
    if [ ! -d "$root" ]; then
        log "SKIP missing root=$root"
        return 0
    fi

    log "APPLY root=$root"

    # Ownership repair: only known drift UIDs, only inside explicit roots.
    while IFS= read -r -d '' item; do
        [ -e "$item" ] || continue

        if ! should_repair_item "$root" "$item"; then
            continue
        fi

        if is_open "$item"; then
            log "SKIP_OPEN $item"
            continue
        fi

        old_owner=$(stat -c '%u:%g' "$item" 2>/dev/null || echo 'unknown')
        chown "$TARGET_UID:$TARGET_GID" "$item"
        new_owner=$(stat -c '%u:%g' "$item" 2>/dev/null || echo 'unknown')
        log "FIX_OWNER $item $old_owner->$new_owner"
    done < <(safe_find "$root" -xdev \( -uid 0 -o -uid 1337 \) -print0)

    # Drift prevention: let new files inherit the managed group.
    while IFS= read -r -d '' dir; do
        [ -d "$dir" ] || continue
        chmod g+s "$dir" 2>/dev/null || true
    done < <(safe_find "$root" -xdev -type d -print0)
}

main() {
    local mode="${1:---check}"
    local detail=1

    case "$mode" in
        --check|--summary|--apply|--list) ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 1
            ;;
    esac

    if [ "$mode" = "--summary" ]; then
        detail=0
    fi

    if [ "$mode" = "--apply" ] && ! is_root; then
        log "FAIL apply mode requires root"
        exit 1
    fi

    exec 200>"$LOCKFILE"
    if ! flock -n 200; then
        log "SKIP another run is active"
        exit 0
    fi

    case "$mode" in
        --list)
            print_list
            ;;
        --check)
            for root in "${REPORT_ONLY_ROOTS[@]}" "${APPLY_ROOTS[@]}"; do
                scan_root "$root" "$detail"
            done
            ;;
        --summary)
            for root in "${REPORT_ONLY_ROOTS[@]}" "${APPLY_ROOTS[@]}"; do
                scan_root "$root" "$detail"
            done
            ;;
        --apply)
            for root in "${APPLY_ROOTS[@]}"; do
                apply_root "$root"
            done
            for root in "${REPORT_ONLY_ROOTS[@]}"; do
                scan_root "$root" "$detail"
            done
            ;;
    esac

    log "DONE mode=$mode"
}

main "$@"
