#!/usr/bin/env bash
# Canonical HermesTrader Restic backup pipeline.
set -Eeuo pipefail

readonly SCRIPT_NAME="hermestrader-backup"
readonly EXIT_DEFERRED=75
readonly EXIT_TIMEOUT=124
readonly CANONICAL_HERMES_ROOT="/opt/data/hermes"

MODE="normal"
COMMAND="${1:-normal}"
if [[ "$COMMAND" == "__worker" ]]; then
    MODE="${2:-normal}"
elif [[ "$COMMAND" == "normal" || "$COMMAND" == "initial" ]]; then
    MODE="$COMMAND"
fi

readonly HERMES_ROOT="${HERMESTRADER_HERMES_ROOT:-$CANONICAL_HERMES_ROOT}"
readonly PROFILE="${HERMESTRADER_PROFILE:-trading-hub-orchestrator}"
readonly PROFILE_ROOT="$HERMES_ROOT/profiles/$PROFILE"
readonly RESTIC_ENV="${HERMESTRADER_RESTIC_ENV:-/etc/restic/restic-env}"
readonly EXCLUDES="${HERMESTRADER_BACKUP_EXCLUDES:-/etc/restic/excludes.txt}"
readonly STATE_DIR="${HERMESTRADER_BACKUP_STATE_DIR:-/var/lib/hermestrader-backup}"
readonly WORK_DIR="$STATE_DIR/work"
readonly REPORT_DIR="${HERMESTRADER_BACKUP_REPORT_DIR:-/root/reports}"
readonly LATEST_REPORT="$STATE_DIR/latest-report.json"
readonly RESTIC_LOCK="${HERMESTRADER_RESTIC_LOCK:-/run/lock/hermestrader-restic.lock}"
readonly BACKUP_LOCK="${HERMESTRADER_BACKUP_LOCK:-/run/lock/hermestrader-backup.lock}"
readonly WRITER_LOCK="${HERMESTRADER_WRITER_LOCK:-/opt/data/state/repo-writer/hermes-repo-writer.lock}"
readonly WRITER_LOCK_TIMEOUT="${HERMESTRADER_WRITER_LOCK_TIMEOUT:-60}"
readonly BACKUP_TIMEOUT_SECONDS="${HERMESTRADER_BACKUP_TIMEOUT_SECONDS:-9900}"
readonly SQLITE_SNAPSHOT_TOOL="${HERMESTRADER_SQLITE_SNAPSHOT_TOOL:-/usr/local/libexec/hermestrader-sqlite-snapshot}"
readonly SQLITE_SNAPSHOT_TIMEOUT_SECONDS="${HERMESTRADER_SQLITE_SNAPSHOT_TIMEOUT_SECONDS:-300}"

TS="${HERMESTRADER_BACKUP_RUN_TS:-$(date -u +%Y%m%dT%H%M%SZ)}"
readonly TS
START_EPOCH="$(date -u +%s)"
readonly START_EPOCH
readonly STAGING="$WORK_DIR/$TS/staging"
readonly REPORT_FILE="$REPORT_DIR/hermestrader-backup-$TS.json"
readonly SQLITE_INVENTORY="$STAGING/system/sqlite-inventory.json"

readonly -a SOURCES=(
    "/opt/data/projects/trading-hub"
    "$CANONICAL_HERMES_ROOT"
    "/etc/systemd/system"
    "/etc/caddy"
    "/etc/fstab"
    "/root/reports"
)

readonly -a HOST_DB_SPECS=(
    "root-state|$HERMES_ROOT|state.db|hermes-root"
    "root-kanban|$HERMES_ROOT|kanban.db|hermes-root"
    "root-verification-evidence|$HERMES_ROOT|verification_evidence.db|hermes-root"
    "root-projects|$HERMES_ROOT|projects.db|hermes-root"
    "profile-state|$PROFILE_ROOT|state.db|hermes-profile"
    "profile-cron-executions|$PROFILE_ROOT|cron/executions.db|hermes-profile"
    "profile-memory-store|$PROFILE_ROOT|memory_store.db|hermes-profile"
    "profile-projects|$PROFILE_ROOT|projects.db|hermes-profile"
    "profile-verification-evidence|$PROFILE_ROOT|verification_evidence.db|hermes-profile"
)

readonly -a FREQTRADE_SPECS=(
    "freqforge|hermestrader-dryrun-freqtrade-freqforge-1|/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite"
    "freqforge-canary|hermestrader-dryrun-freqtrade-freqforge-canary-1|/freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite"
    "regime-hybrid|hermestrader-dryrun-freqtrade-regime-hybrid-1|/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite"
)

CURRENT_STAGE="init"
ERROR_MSG=""
ERROR_REASON=""
SNAPSHOT_ID=""
FILES_PROCESSED=0
BYTES_PROCESSED=0
DURATION_SECS=0
CHECK_STATUS="not-run"
FORGET_STATUS="skipped"
STAGING_BYTES=0
SQLITE_EXPECTED=0
SQLITE_ACTUAL=0
EXIT_CODE=0
RESTIC_STDOUT_FILE=""
RESTIC_STDERR_FILE=""
WRITER_LOCK_HELD=false
ACTIVE_CHILD_PID=0
FD_BACKUP_LOCK=201
FD_RESTIC_LOCK=202
FD_WRITER_LOCK=203

declare -a INVENTORY_RECORDS=()

log() { echo "[$(date -u +%H:%M:%S)] [$SCRIPT_NAME] $*" >&2; }
err() { echo "[$(date -u +%H:%M:%S)] [$SCRIPT_NAME] [ERROR] $*" >&2; }

is_sqlite_name() {
    case "$1" in
        *.db|*.sqlite|*.sqlite3) return 0 ;;
        *) return 1 ;;
    esac
}

is_excluded_component() {
    local _path="/$1/"
    local _component
    for _component in \
        backups backup state-snapshots snapshots recovery restore restored \
        cache caches .cache quarantine tmp .tmp temp tests probes probe \
        previous-upgrade-copies previous_upgrade_copies auth pki session sessions; do
        [[ "$_path" == *"/$_component/"* ]] && return 0
    done
    return 1
}

validate_state_root() {
    if [[ "$COMMAND" != "discover-host" && "$HERMES_ROOT" != "$CANONICAL_HERMES_ROOT" ]]; then
        ERROR_MSG="UNEXPECTED_STATE_ROOT: expected $CANONICAL_HERMES_ROOT, got $HERMES_ROOT"
        return 1
    fi
    if [[ "$HERMES_ROOT" == */.hermes || "$HERMES_ROOT" == "/home/hermes/.hermes" ]]; then
        ERROR_MSG="UNEXPECTED_STATE_ROOT: legacy state root is forbidden: $HERMES_ROOT"
        return 1
    fi
    [[ "$PROFILE" == "trading-hub-orchestrator" ]] || {
        ERROR_MSG="UNEXPECTED_PROFILE: refusing unknown profile $PROFILE"
        return 1
    }
}

discover_host_databases() {
    validate_state_root || { err "$ERROR_MSG"; return 1; }

    local _root_real
    _root_real="$(realpath -e -- "$HERMES_ROOT" 2>/dev/null)" || {
        ERROR_MSG="UNEXPECTED_STATE_ROOT: root does not exist: $HERMES_ROOT"
        err "$ERROR_MSG"
        return 1
    }

    local -A _expected=()
    local _spec _name _root _relative _type _source _source_real _export
    local -a _records=()
    for _spec in "${HOST_DB_SPECS[@]}"; do
        IFS='|' read -r _name _root _relative _type <<<"$_spec"
        _source="$_root/$_relative"
        [[ -f "$_source" ]] || {
            ERROR_MSG="MISSING_CANONICAL_DB: $_source"
            err "$ERROR_MSG"
            return 1
        }
        _source_real="$(realpath -e -- "$_source" 2>/dev/null)" || {
            ERROR_MSG="DATABASE_PATH_INVALID: $_source"
            err "$ERROR_MSG"
            return 1
        }
        case "$_source_real" in
            "$_root_real"/*) ;;
            *)
                ERROR_MSG="DATABASE_PATH_ESCAPE: $_source -> $_source_real"
                err "$ERROR_MSG"
                return 1
                ;;
        esac
        _expected["$_source_real"]=1
        _export="sqlite/host/${_source#/}"
        _records+=("$(jq -nc \
            --arg name "$_name" --arg source "$_source" --arg export "$_export" --arg type "$_type" \
            '{name:$name,source:$source,export:$export,type:$type}')")
    done

    local _candidate _candidate_real _relative_candidate
    while IFS= read -r -d '' _candidate; do
        _relative_candidate="${_candidate#"$HERMES_ROOT"/}"
        is_excluded_component "$_relative_candidate" && continue
        is_sqlite_name "$_candidate" || continue
        _candidate_real="$(realpath -e -- "$_candidate" 2>/dev/null)" || {
            ERROR_MSG="DATABASE_PATH_INVALID: $_candidate"
            err "$ERROR_MSG"
            return 1
        }
        if [[ -z "${_expected["$_candidate_real"]:-}" ]]; then
            ERROR_MSG="UNKNOWN_PRODUCTION_DB: $_candidate"
            err "$ERROR_MSG"
            return 1
        fi
    done < <(find "$HERMES_ROOT" \( -type f -o -type l \) \
        \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print0 2>/dev/null)

    printf '%s\n' "${_records[@]}" | jq -s '{count:length,databases:.}'
}

write_report() {
    local _code="${1:-1}"
    local _status="FAILED"
    local _end _inventory='[]'
    _end="$(date -u +%s)"
    DURATION_SECS=$((_end - START_EPOCH))
    if [[ "$_code" -eq 0 ]]; then
        [[ "$MODE" == "initial" ]] && _status="PENDING_RESTORE" || _status="SUCCESS"
    elif [[ "$_code" -eq "$EXIT_DEFERRED" ]]; then
        _status="DEFERRED"
    fi
    if [[ -f "$SQLITE_INVENTORY" ]]; then
        _inventory="$(jq -c . "$SQLITE_INVENTORY" 2>/dev/null || printf '[]')"
    fi

    local _tmp="${REPORT_FILE}.tmp.$$"
    install -d -m 0700 "$REPORT_DIR" "$STATE_DIR"
    jq -n \
        --arg ts "$TS" --arg mode "$MODE" --arg status "$_status" \
        --argjson code "$_code" --arg stage "$CURRENT_STAGE" \
        --arg reason "$ERROR_REASON" --arg error "$ERROR_MSG" \
        --arg snapshot "$SNAPSHOT_ID" --arg source_root "$CANONICAL_HERMES_ROOT" \
        --arg staging_path "$STAGING" --argjson files "$FILES_PROCESSED" \
        --argjson bytes "$BYTES_PROCESSED" --argjson dur "$DURATION_SECS" \
        --arg check "$CHECK_STATUS" --arg forget "$FORGET_STATUS" \
        --argjson staging "$STAGING_BYTES" --argjson sqlite_exp "$SQLITE_EXPECTED" \
        --argjson sqlite_act "$SQLITE_ACTUAL" --argjson inventory "$_inventory" \
        '{timestamp:$ts,mode:$mode,status:$status,exit_code:$code,stage:$stage,
          reason:$reason,error:$error,snapshot_id:$snapshot,source_root:$source_root,
          staging_path:$staging_path,files_processed:$files,bytes_processed:$bytes,
          duration_seconds:$dur,restic_check:$check,forget:$forget,
          staging_bytes:$staging,sqlite_expected:$sqlite_exp,sqlite_actual:$sqlite_act,
          sqlite_databases:$inventory}' >"$_tmp"
    chmod 0600 "$_tmp"
    mv -f -- "$_tmp" "$REPORT_FILE"
    cp -f -- "$REPORT_FILE" "${LATEST_REPORT}.tmp.$$"
    mv -f -- "${LATEST_REPORT}.tmp.$$" "$LATEST_REPORT"
}

release_writer_lock() {
    if [[ "$WRITER_LOCK_HELD" == true ]]; then
        flock -u "$FD_WRITER_LOCK" 2>/dev/null || true
        eval "exec ${FD_WRITER_LOCK}>&-" 2>/dev/null || true
        WRITER_LOCK_HELD=false
    fi
}

release_process_locks() {
    flock -u "$FD_RESTIC_LOCK" 2>/dev/null || true
    eval "exec ${FD_RESTIC_LOCK}>&-" 2>/dev/null || true
    flock -u "$FD_BACKUP_LOCK" 2>/dev/null || true
    eval "exec ${FD_BACKUP_LOCK}>&-" 2>/dev/null || true
}

cleanup_staging() {
    if [[ -n "$STAGING" && -d "$STAGING" && "$STAGING" == "$WORK_DIR"/*/staging ]]; then
        rm -rf -- "$STAGING"
        rmdir -- "${STAGING%/*}" 2>/dev/null || true
    fi
}

cleanup_temp_files() {
    [[ -n "$RESTIC_STDOUT_FILE" && -f "$RESTIC_STDOUT_FILE" ]] && rm -f -- "$RESTIC_STDOUT_FILE" || true
    [[ -n "$RESTIC_STDERR_FILE" && -f "$RESTIC_STDERR_FILE" ]] && rm -f -- "$RESTIC_STDERR_FILE" || true
}

final_cleanup() {
    local _code=$?
    trap - EXIT TERM INT HUP
    set +e
    [[ "$EXIT_CODE" -ne 0 ]] && _code="$EXIT_CODE"
    write_report "$_code"
    cleanup_staging
    release_writer_lock
    release_process_locks
    cleanup_temp_files
    exit "$_code"
}

on_error() {
    local _code=$?
    local _line="${BASH_LINENO[0]:-unknown}"
    [[ -n "$ERROR_MSG" ]] || ERROR_MSG="command failed at line $_line (exit $_code) in stage [$CURRENT_STAGE]"
    [[ -n "$ERROR_REASON" ]] || ERROR_REASON="COMMAND_FAILED"
    [[ "$EXIT_CODE" -ne 0 ]] || EXIT_CODE="$_code"
}

on_signal() {
    local _name="$1" _code="$2"
    if [[ "$ACTIVE_CHILD_PID" -gt 0 ]]; then
        kill -TERM "$ACTIVE_CHILD_PID" 2>/dev/null || true
        wait "$ACTIVE_CHILD_PID" 2>/dev/null || true
        ACTIVE_CHILD_PID=0
    fi
    ERROR_REASON="SIGNAL_$_name"
    ERROR_MSG="received SIG$_name in stage [$CURRENT_STAGE]"
    EXIT_CODE="$_code"
    exit "$_code"
}

install_traps() {
    trap final_cleanup EXIT
    trap on_error ERR
    trap 'on_signal TERM 143' TERM
    trap 'on_signal INT 130' INT
    trap 'on_signal HUP 129' HUP
}

preflight() {
    CURRENT_STAGE="preflight"
    validate_state_root || { err "$ERROR_MSG"; return 1; }
    local _bin
    for _bin in restic rsync flock jq docker sqlite3 sha256sum realpath timeout; do
        command -v "$_bin" >/dev/null 2>&1 || {
            ERROR_MSG="MISSING_BINARY: $_bin"
            ERROR_REASON="PREFLIGHT_FAILED"
            err "$ERROR_MSG"
            return 1
        }
    done
    [[ -f "$RESTIC_ENV" ]] || { ERROR_MSG="MISSING_RESTIC_ENV: $RESTIC_ENV"; return 1; }
    [[ -f "$EXCLUDES" ]] || { ERROR_MSG="MISSING_EXCLUDES: $EXCLUDES"; return 1; }
    [[ -e "$WRITER_LOCK" ]] || { ERROR_MSG="WRITER_LOCK_MISSING: $WRITER_LOCK"; return 1; }
    [[ -x "$SQLITE_SNAPSHOT_TOOL" ]] || { ERROR_MSG="SQLITE_SNAPSHOT_TOOL_MISSING: $SQLITE_SNAPSHOT_TOOL"; return 1; }
    [[ "$SQLITE_SNAPSHOT_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || {
        ERROR_MSG="SQLITE_SNAPSHOT_TIMEOUT_INVALID: $SQLITE_SNAPSHOT_TIMEOUT_SECONDS"
        return 1
    }
    set -a
    # shellcheck disable=SC1090
    source "$RESTIC_ENV"
    set +a
    [[ -n "${RESTIC_REPOSITORY:-}" ]] || { ERROR_MSG="RESTIC_REPOSITORY_MISSING"; return 1; }
}

acquire_process_locks() {
    CURRENT_STAGE="acquire-process-locks"
    eval "exec ${FD_BACKUP_LOCK}>>'$BACKUP_LOCK'"
    if ! flock -n "$FD_BACKUP_LOCK"; then
        EXIT_CODE=$EXIT_DEFERRED
        ERROR_REASON="BACKUP_LOCK_BUSY"
        ERROR_MSG="backup lock busy"
        return "$EXIT_DEFERRED"
    fi
    eval "exec ${FD_RESTIC_LOCK}>>'$RESTIC_LOCK'"
    if ! flock -n "$FD_RESTIC_LOCK"; then
        EXIT_CODE=$EXIT_DEFERRED
        ERROR_REASON="RESTIC_LOCK_BUSY"
        ERROR_MSG="restic lock busy"
        return "$EXIT_DEFERRED"
    fi
}

acquire_writer_lock() {
    CURRENT_STAGE="acquire-writer-lock"
    eval "exec ${FD_WRITER_LOCK}<'$WRITER_LOCK'"
    if ! flock --shared --wait "$WRITER_LOCK_TIMEOUT" "$FD_WRITER_LOCK"; then
        ERROR_REASON="WRITER_LOCK_BUSY"
        ERROR_MSG="writer lock busy after ${WRITER_LOCK_TIMEOUT}s"
        return 1
    fi
    WRITER_LOCK_HELD=true
}

prepare_staging() {
    CURRENT_STAGE="prepare-staging"
    install -d -m 0700 "$STAGING/sqlite/host" "$STAGING/sqlite/freqtrade" "$STAGING/system"
    RESTIC_STDOUT_FILE="$(mktemp /tmp/hermes-backup-stdout.XXXXXX)"
    RESTIC_STDERR_FILE="$(mktemp /tmp/hermes-backup-stderr.XXXXXX)"
}

rsync_sources() {
    CURRENT_STAGE="rsync-sources"
    local _src _dest
    for _src in "${SOURCES[@]}"; do
        [[ -e "$_src" ]] || { log "source absent, skipping: $_src"; continue; }
        _dest="$STAGING$_src"
        if [[ -d "$_src" ]]; then
            install -d -m 0700 "$_dest"
            rsync -aHAX --delete --exclude-from="$EXCLUDES" "${_src}/" "${_dest}/" || {
                ERROR_REASON="SOURCE_CAPTURE_FAILED"
                ERROR_MSG="rsync failed for $_src"
                return 1
            }
        else
            install -d -m 0700 "$(dirname "$_dest")"
            rsync -aHAX "$_src" "$_dest" || {
                ERROR_REASON="SOURCE_CAPTURE_FAILED"
                ERROR_MSG="rsync failed for $_src"
                return 1
            }
        fi
    done
}

sqlite_integrity_ok() {
    [[ "$(sqlite3 -readonly "$1" 'PRAGMA integrity_check;' 2>/dev/null)" == "ok" ]]
}

snapshot_host_sqlite() {
    local _source="$1" _destination="$2" _result_file="${2}.snapshot.json" _rc
    set +e
    timeout --signal=TERM --kill-after=10s "${SQLITE_SNAPSHOT_TIMEOUT_SECONDS}s" \
        "$SQLITE_SNAPSHOT_TOOL" "$_source" "$_destination" >"$_result_file"
    _rc=$?
    set -e
    if [[ "$_rc" -eq 124 || "$_rc" -eq 137 ]]; then
        ERROR_REASON="SQLITE_SNAPSHOT_TIMEOUT"
        ERROR_MSG="SQLITE_SNAPSHOT_TIMEOUT: $_source after ${SQLITE_SNAPSHOT_TIMEOUT_SECONDS}s"
        return 1
    fi
    if [[ "$_rc" -ne 0 ]]; then
        ERROR_REASON="SQLITE_EXPORT_FAILED"
        ERROR_MSG="SQLITE_EXPORT_FAILED: bounded snapshot failed for $_source (exit $_rc)"
        return 1
    fi
    jq -e '(.method == "sqlite_backup_full_step" or .method == "sqlite_stable_raw_copy") and .integrity_check == "ok"' \
        "$_result_file" >/dev/null || {
        ERROR_REASON="SQLITE_EXPORT_FAILED"
        ERROR_MSG="SQLITE_EXPORT_FAILED: invalid snapshot result for $_source"
        return 1
    }
}

add_inventory_record() {
    INVENTORY_RECORDS+=("$(jq -nc \
        --arg name "$1" --arg source "$2" --arg export "$3" --arg type "$4" --arg method "$5" \
        '{name:$name,source:$source,export:$export,type:$type,
          snapshot_method:$method}')")
}

export_host_sqlite() {
    CURRENT_STAGE="export-host-sqlite"
    discover_host_databases >/dev/null || {
        ERROR_REASON="DISCOVERY_FAILED"
        return 1
    }
    local _spec _name _root _relative _type _source _export _destination _method
    for _spec in "${HOST_DB_SPECS[@]}"; do
        IFS='|' read -r _name _root _relative _type <<<"$_spec"
        _source="$_root/$_relative"
        _export="sqlite/host/${_source#/}"
        _destination="$STAGING/$_export"
        install -d -m 0700 "$(dirname "$_destination")"
        snapshot_host_sqlite "$_source" "$_destination" || return 1
        _method="$(jq -er '.method' "${_destination}.snapshot.json")" || {
            ERROR_REASON="SQLITE_EXPORT_FAILED"
            ERROR_MSG="SQLITE_EXPORT_FAILED: missing snapshot method for $_source"
            return 1
        }
        if ! sqlite_integrity_ok "$_destination"; then
            ERROR_REASON="SQLITE_INTEGRITY_FAILED"
            ERROR_MSG="SQLITE_INTEGRITY_FAILED: $_source"
            return 1
        fi
        add_inventory_record "$_name" "$_source" "$_export" "$_type" "$_method"
    done
    SQLITE_EXPECTED="${#HOST_DB_SPECS[@]}"
}

export_freqtrade_sqlite() {
    CURRENT_STAGE="export-freqtrade-sqlite"
    local _spec _name _container _source _temp _tool_temp _export _destination _result_file _method _rc
    for _spec in "${FREQTRADE_SPECS[@]}"; do
        IFS='|' read -r _name _container _source <<<"$_spec"
        _temp=".hermes-backup-${_name}-${TS}.sqlite"
        _tool_temp=".hermes-sqlite-snapshot-${_name}-${TS}.py"
        _export="sqlite/freqtrade/tradesv3.${_name}.sqlite"
        _destination="$STAGING/$_export"
        _result_file="${_destination}.snapshot.json"
        if ! docker cp "$SQLITE_SNAPSHOT_TOOL" "$_container:/tmp/$_tool_temp"; then
            ERROR_REASON="SQLITE_EXPORT_FAILED"
            ERROR_MSG="SQLITE_EXPORT_FAILED: helper copy failed for $_name"
            return 1
        fi
        set +e
        docker exec "$_container" timeout --signal=TERM --kill-after=10s \
            "${SQLITE_SNAPSHOT_TIMEOUT_SECONDS}s" python "/tmp/$_tool_temp" \
            "$_source" "/tmp/$_temp" >"$_result_file"
        _rc=$?
        set -e
        if [[ "$_rc" -ne 0 ]]; then
            docker exec "$_container" rm -f "/tmp/$_temp" "/tmp/$_tool_temp" 2>/dev/null || true
            if [[ "$_rc" -eq 124 || "$_rc" -eq 137 ]]; then
                ERROR_REASON="SQLITE_SNAPSHOT_TIMEOUT"
                ERROR_MSG="SQLITE_SNAPSHOT_TIMEOUT: $_name after ${SQLITE_SNAPSHOT_TIMEOUT_SECONDS}s"
            else
                ERROR_REASON="SQLITE_EXPORT_FAILED"
                ERROR_MSG="SQLITE_EXPORT_FAILED: bounded snapshot failed for $_name (exit $_rc)"
            fi
            return 1
        fi
        if ! jq -e '(.method == "sqlite_backup_full_step" or .method == "sqlite_stable_raw_copy") and .integrity_check == "ok"' \
            "$_result_file" >/dev/null; then
            docker exec "$_container" rm -f "/tmp/$_temp" "/tmp/$_tool_temp" 2>/dev/null || true
            ERROR_REASON="SQLITE_EXPORT_FAILED"
            ERROR_MSG="SQLITE_EXPORT_FAILED: invalid snapshot result for $_name"
            return 1
        fi
        if ! docker cp "$_container:/tmp/$_temp" "$_destination"; then
            docker exec "$_container" rm -f "/tmp/$_temp" "/tmp/$_tool_temp" 2>/dev/null || true
            ERROR_REASON="SQLITE_EXPORT_FAILED"
            ERROR_MSG="SQLITE_EXPORT_FAILED: docker cp $_name"
            return 1
        fi
        _method="$(jq -er '.method' "$_result_file")" || {
            ERROR_REASON="SQLITE_EXPORT_FAILED"
            ERROR_MSG="SQLITE_EXPORT_FAILED: missing snapshot method for $_name"
            return 1
        }
        docker exec "$_container" rm -f "/tmp/$_temp" "/tmp/$_tool_temp" 2>/dev/null || true
        if ! sqlite_integrity_ok "$_destination"; then
            ERROR_REASON="SQLITE_INTEGRITY_FAILED"
            ERROR_MSG="SQLITE_INTEGRITY_FAILED: $_name"
            return 1
        fi
        add_inventory_record "$_name" "container:${_container}:${_source}" "$_export" "freqtrade-dry-run" "$_method"
    done
    SQLITE_EXPECTED=$((SQLITE_EXPECTED + ${#FREQTRADE_SPECS[@]}))
}

export_system_metadata() {
    CURRENT_STAGE="export-system-metadata"
    dpkg --get-selections >"$STAGING/system/dpkg-selections.txt" 2>/dev/null || true
    systemctl list-unit-files --no-pager --no-legend >"$STAGING/system/systemd-unit-files.txt" 2>/dev/null || true
    systemctl list-units --all --no-pager --no-legend >"$STAGING/system/systemd-units-active.txt" 2>/dev/null || true
    docker ps -a --format '{{json .}}' >"$STAGING/system/docker-containers.jsonl" 2>/dev/null || true
    docker images --format '{{json .}}' >"$STAGING/system/docker-images.jsonl" 2>/dev/null || true
    printf '%s\n' "${INVENTORY_RECORDS[@]}" | jq -s . >"$SQLITE_INVENTORY"
}

generate_sha256sums() {
    CURRENT_STAGE="generate-sha256sums"
    (
        cd "$STAGING"
        find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 -r sha256sum
    ) >"$STAGING/SHA256SUMS"
    STAGING_BYTES="$(du -sb "$STAGING" | cut -f1)"
}

run_restic_backup() {
    CURRENT_STAGE="restic-backup"
    local -a _tags=(--tag hermestrader --host hermestrader)
    [[ "$MODE" == "initial" ]] && _tags+=(--tag initial) || _tags+=(--tag automated)
    if ! restic backup --json "${_tags[@]}" "$STAGING" >"$RESTIC_STDOUT_FILE" 2>"$RESTIC_STDERR_FILE"; then
        ERROR_REASON="BACKUP_FAILED"
        ERROR_MSG="BACKUP_FAILED: $(tail -3 "$RESTIC_STDERR_FILE" | tr '\n' ' ')"
        return 1
    fi
    local _summary
    _summary="$(jq -c 'select(.message_type=="summary")' "$RESTIC_STDOUT_FILE" | tail -1)"
    [[ -n "$_summary" ]] || { ERROR_REASON="BACKUP_FAILED"; ERROR_MSG="missing restic summary"; return 1; }
    SNAPSHOT_ID="$(jq -r '.snapshot_id // empty' <<<"$_summary")"
    FILES_PROCESSED="$(jq -r '.total_files_processed // 0' <<<"$_summary")"
    BYTES_PROCESSED="$(jq -r '.total_bytes_processed // 0' <<<"$_summary")"
    [[ "$SNAPSHOT_ID" =~ ^[0-9a-f]{64}$ && "$FILES_PROCESSED" -gt 0 && "$BYTES_PROCESSED" -gt 0 ]] || {
        ERROR_REASON="BACKUP_FAILED"
        ERROR_MSG="invalid restic summary"
        return 1
    }
}

verify_snapshot() {
    CURRENT_STAGE="verify-snapshot"
    local _listing _leaks
    _listing="$(mktemp /tmp/hermes-backup-list.XXXXXX)"
    if ! restic snapshots --json --host hermestrader | jq -e --arg id "$SNAPSHOT_ID" '[.[]|select(.id==$id)]|length==1' >/dev/null; then
        rm -f -- "$_listing"
        ERROR_REASON="SNAPSHOT_VERIFY_FAILED"
        ERROR_MSG="snapshot not found exactly once: $SNAPSHOT_ID"
        return 1
    fi
    if ! restic ls --json "$SNAPSHOT_ID" >"$_listing"; then
        rm -f -- "$_listing"
        ERROR_REASON="SNAPSHOT_VERIFY_FAILED"
        ERROR_MSG="restic ls failed"
        return 1
    fi
    _leaks="$(jq -r 'select(.struct_type=="node" and .type=="file")|.path' "$_listing" | \
        grep -E '/(etc/restic|var/lib/docker/volumes)/|/(auth|token|tokens|session|sessions|secrets)/|\.(key|pem)$|/\.env([.-]|$)|/\.(netrc|npmrc|pypirc)$|/(hosts\.yml|credentials\.json|approval\.token)$' || true)"
    if [[ -n "$_leaks" ]]; then
        rm -f -- "$_listing"
        ERROR_REASON="SECRET_PATH_LEAK"
        ERROR_MSG="forbidden secret path present in snapshot"
        return 1
    fi
    SQLITE_ACTUAL="$(jq -r 'select(.struct_type=="node" and .type=="file")|.path' "$_listing" | grep -cE '/sqlite/.*\.(db|sqlite|sqlite3)$' || true)"
    rm -f -- "$_listing"
    [[ "$SQLITE_ACTUAL" -eq "$SQLITE_EXPECTED" ]] || {
        ERROR_REASON="SQLITE_COUNT_MISMATCH"
        ERROR_MSG="expected=$SQLITE_EXPECTED actual=$SQLITE_ACTUAL"
        return 1
    }
}

run_restic_check() {
    CURRENT_STAGE="restic-check"
    CHECK_STATUS="running"
    if restic check --no-cache; then
        CHECK_STATUS="ok"
    else
        CHECK_STATUS="failed"
        ERROR_REASON="RESTIC_CHECK_FAILED"
        ERROR_MSG="restic check failed"
        return 1
    fi
}

run_forget() {
    [[ "$MODE" == "normal" ]] || return 0
    CURRENT_STAGE="restic-forget"
    FORGET_STATUS="running"
    if restic forget --host hermestrader --tag automated --keep-daily 7 --keep-weekly 4 --keep-monthly 6; then
        FORGET_STATUS="ok"
    else
        FORGET_STATUS="failed"
        log "non-load-bearing retention update failed"
    fi
}

worker_main() {
    install -d -m 0700 "$REPORT_DIR" "$STATE_DIR" "$WORK_DIR"
    install_traps
    preflight
    acquire_process_locks
    prepare_staging
    acquire_writer_lock
    rsync_sources
    export_host_sqlite
    export_freqtrade_sqlite
    export_system_metadata
    generate_sha256sums
    release_writer_lock
    run_restic_backup
    verify_snapshot
    run_restic_check
    run_forget
    CURRENT_STAGE="done"
    EXIT_CODE=0
}

force_timeout_report() {
    install -d -m 0700 "$REPORT_DIR" "$STATE_DIR"
    local _tmp="${REPORT_FILE}.timeout.tmp.$$"
    if [[ -f "$LATEST_REPORT" ]]; then
        jq --arg stage "${CURRENT_STAGE:-watchdog}" \
            '.status="FAILED" | .exit_code=124 | .reason="TIMEOUT" |
             .error="internal backup watchdog expired" |
             .stage=(if .stage == "done" then $stage else .stage end)' \
            "$LATEST_REPORT" >"$_tmp"
    else
        jq -n --arg ts "$TS" --arg mode "$MODE" \
            '{timestamp:$ts,mode:$mode,status:"FAILED",exit_code:124,
              stage:"watchdog",reason:"TIMEOUT",error:"internal backup watchdog expired",
              snapshot_id:"",source_root:"/opt/data/hermes",verified:false}' >"$_tmp"
    fi
    chmod 0600 "$_tmp"
    mv -f -- "$_tmp" "$REPORT_FILE"
    cp -f -- "$REPORT_FILE" "${LATEST_REPORT}.tmp.$$"
    mv -f -- "${LATEST_REPORT}.tmp.$$" "$LATEST_REPORT"
}

run_with_watchdog() {
    local _worker_mode="$1" _rc
    [[ "$BACKUP_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || {
        echo "invalid HERMESTRADER_BACKUP_TIMEOUT_SECONDS" >&2
        return 64
    }
    set +e
    HERMESTRADER_BACKUP_RUN_TS="$TS" timeout --signal=TERM --kill-after=30s \
        "${BACKUP_TIMEOUT_SECONDS}s" "$0" __worker "$_worker_mode"
    _rc=$?
    set -e
    if [[ "$_rc" -eq 124 || "$_rc" -eq 137 ]]; then
        force_timeout_report
        return "$EXIT_TIMEOUT"
    fi
    return "$_rc"
}

case "$COMMAND" in
    discover-host)
        discover_host_databases
        ;;
    test-watchdog)
        MODE="normal"
        run_with_watchdog "test-hold"
        ;;
    test-signal-wait)
        MODE="normal"
        install -d -m 0700 "$REPORT_DIR" "$STATE_DIR" "$WORK_DIR"
        install_traps
        CURRENT_STAGE="test-signal-wait"
        sleep "${HERMESTRADER_BACKUP_TEST_HOLD_SECONDS:-30}" &
        ACTIVE_CHILD_PID=$!
        wait "$ACTIVE_CHILD_PID"
        ACTIVE_CHILD_PID=0
        ;;
    __worker)
        if [[ "$MODE" == "test-hold" ]]; then
            MODE="normal"
            install -d -m 0700 "$REPORT_DIR" "$STATE_DIR" "$WORK_DIR"
            install_traps
            CURRENT_STAGE="test-watchdog"
            sleep "${HERMESTRADER_BACKUP_TEST_HOLD_SECONDS:-30}"
        elif [[ "$MODE" == "normal" || "$MODE" == "initial" ]]; then
            worker_main
        else
            echo "invalid worker mode: $MODE" >&2
            exit 64
        fi
        ;;
    normal|initial)
        run_with_watchdog "$MODE"
        ;;
    *)
        echo "usage: $0 [normal|initial|discover-host]" >&2
        exit 64
        ;;
esac
