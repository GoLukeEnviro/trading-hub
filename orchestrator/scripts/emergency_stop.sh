#!/usr/bin/env bash
# =============================================================================
# Emergency Stop Script — Live Canary Rollback
# =============================================================================
#
# Usage:
#   ./orchestrator/scripts/emergency_stop.sh [--dry-run] [--reason "message"]
#
# Options:
#   --dry-run    Print actions without executing them
#   --reason     Human-readable reason (default: "emergency stop — no reason given")
#
# Safety:
#   - Targets exactly one bot: freqtrade-freqforge-canary
#   - Does NOT touch fleet bots
#   - Does NOT delete data, configs, or databases
#   - Does NOT require external credentials
#   - Writes timestamped audit record to var/si_v2/emergency/
#
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CANARY_CONTAINER="freqtrade-freqforge-canary"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
EMERGENCY_DIR="$PROJECT_ROOT/var/si_v2/emergency"
DRY_RUN=false
REASON=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --reason) REASON="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ -z "$REASON" ]]; then
    REASON="emergency stop — no reason given"
fi

echo "[EMERGENCY STOP] $TIMESTAMP"
echo "[EMERGENCY STOP] Target: $CANARY_CONTAINER"
echo "[EMERGENCY STOP] Reason: $REASON"
echo ""

# -------------------------------------------------------------------------
# Step 1: Activate kill switch EMERGENCY
# -------------------------------------------------------------------------
echo "[1/5] Activating kill switch EMERGENCY..."
if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [DRY-RUN] Would run: python3 freqtrade/shared/kill_switch.py emergency \"$REASON\""
else
    cd "$PROJECT_ROOT"
    python3 freqtrade/shared/kill_switch.py emergency "$REASON"
    echo "  ✅ Kill switch set to EMERGENCY"
fi

# -------------------------------------------------------------------------
# Step 2: Halt canary container
# -------------------------------------------------------------------------
echo "[2/5] Halting canary container ($CANARY_CONTAINER)..."
if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [DRY-RUN] Would run: docker stop $CANARY_CONTAINER"
else
    if docker ps --format '{{.Names}}' | grep -q "^$CANARY_CONTAINER$"; then
        docker stop "$CANARY_CONTAINER"
        echo "  ✅ Container $CANARY_CONTAINER stopped"
    else
        echo "  ⚠️  Container $CANARY_CONTAINER not running — skipping"
    fi
fi

# -------------------------------------------------------------------------
# Step 3: Write emergency audit record
# -------------------------------------------------------------------------
echo "[3/5] Writing emergency audit record..."
mkdir -p "$EMERGENCY_DIR"
AUDIT_FILE="$EMERGENCY_DIR/emergency_$(date -u +%Y%m%d_%H%M%S).json"

AUDIT_PAYLOAD=$(cat <<EOF
{
  "event": "emergency_stop",
  "timestamp_utc": "$TIMESTAMP",
  "target": "$CANARY_CONTAINER",
  "reason": "$REASON",
  "kill_switch_mode": "EMERGENCY",
  "triggered_by": "emergency_stop.sh",
  "dry_run": $DRY_RUN
}
EOF
)

if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [DRY-RUN] Would write: $AUDIT_FILE"
    echo "  [DRY-RUN] Payload: $AUDIT_PAYLOAD"
else
    echo "$AUDIT_PAYLOAD" > "$AUDIT_FILE"
    echo "  ✅ Audit record written to $AUDIT_FILE"
fi

# -------------------------------------------------------------------------
# Step 4: Verify container is stopped
# -------------------------------------------------------------------------
echo "[4/5] Verifying container state..."
if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [DRY-RUN] Would run: docker ps --filter name=$CANARY_CONTAINER"
else
    if docker ps --format '{{.Names}}' | grep -q "^$CANARY_CONTAINER$"; then
        echo "  ❌ Container $CANARY_CONTAINER is still running — manual intervention required"
        exit 1
    else
        echo "  ✅ Container $CANARY_CONTAINER is stopped"
    fi
fi

# -------------------------------------------------------------------------
# Step 5: Summary
# -------------------------------------------------------------------------
echo ""
echo "[5/5] Emergency stop complete"
echo "  Target:     $CANARY_CONTAINER"
echo "  Kill switch: EMERGENCY"
echo "  Audit:      $AUDIT_FILE"
echo "  Next:       Restore dry-run config and redeploy per C3 rollback plan"
echo "              (see var/si_v2/live_canary_activation_ceremony/live_canary_activation_ceremony.json)"
