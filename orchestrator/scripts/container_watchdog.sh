#!/bin/bash
# container_watchdog.sh v2 — Container health check with Docker-aware fallback
# Runs every 5min via Hermes cron. Only outputs when issues found (silent = OK).
#
# Detection strategy:
#   1. If Docker socket available → docker inspect (authoritative)
#   2. If no Docker socket → file-based heuristic (signal file freshness)
#   3. Silent OK = no output = no Telegram delivery
#
# Root cause of v1 failure: Hermes container has no Docker socket mounted.
# v2 gracefully handles this and reports accurate status in both modes.

set -euo pipefail

LOG="/home/hermes/projects/trading/orchestrator/logs/watchdog.log"
STATE="/home/hermes/projects/trading/orchestrator/state/container_watchdog_state.json"

TRADING_CONTAINERS="freqtrade-freqforge freqtrade-freqforge-canary freqtrade-regime-hybrid freqtrade-momentum freqai-rebel ai-hedge-fund-crypto"

# Map containers to probe files for file-based fallback
# These are files updated by the trading pipeline or bots themselves
declare -A BOT_PROBES
BOT_PROBES["freqtrade-freqforge"]="/home/hermes/projects/trading/freqtrade/shared/primo_signal_state.json"
BOT_PROBES["freqtrade-freqforge-canary"]="/home/hermes/projects/trading/freqtrade/shared/primo_signal_state.json"
BOT_PROBES["freqtrade-regime-hybrid"]="/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json"
BOT_PROBES["freqtrade-momentum"]="/home/hermes/projects/trading/freqtrade/bots/momentum/user_data/primo_signal_state.json"
BOT_PROBES["freqai-rebel"]="/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json"
BOT_PROBES["ai-hedge-fund-crypto"]="/home/hermes/projects/trading/ai-hedge-fund-crypto/output/latest/hermes_signal.json"

STALE_THRESHOLD_MIN=30  # Probe file older than this = possibly down

now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
issues=""
all_status=""
mode="unknown"

# ── Detect Docker availability ──────────────────────────────────
has_docker=false
if [ -S /var/run/docker.sock ] && command -v docker &>/dev/null; then
    if docker info &>/dev/null; then
        has_docker=true
        mode="docker"
    fi
fi

if [ "$has_docker" = false ]; then
    mode="file-based"
fi

# ── Check each container ────────────────────────────────────────
for c in $TRADING_CONTAINERS; do
    if [ "$has_docker" = true ]; then
        # Authoritative check via Docker
        status=$(docker inspect "$c" --format '{{.State.Status}}' 2>/dev/null || echo "not_found")
        started=$(docker inspect "$c" --format '{{.State.StartedAt}}' 2>/dev/null || echo "unknown")

        if [ "$status" != "running" ]; then
            issues="${issues}\n❌ ${c}: ${status}"
        fi
    else
        # File-based heuristic: check probe file freshness
        probe="${BOT_PROBES[$c]:-}"
        if [ -n "$probe" ] && [ -f "$probe" ]; then
            if [ "$(find "$probe" -mmin -${STALE_THRESHOLD_MIN} 2>/dev/null | wc -l)" -gt 0 ]; then
                status="alive(file-based)"
                started="unknown"
            else
                stale_min=$(( ($(date +%s) - $(stat -c %Y "$probe" 2>/dev/null || echo 0)) / 60 ))
                status="stale(${stale_min}min)"
                started="unknown"
                issues="${issues}\n⚠️ ${c}: probe stale (${stale_min}min, no Docker)"
            fi
        else
            status="no_probe_file"
            started="unknown"
            # Don't alert for missing probe files — just note it in state
        fi
    fi

    # Build JSON entry
    all_status="${all_status},\"${c}\":{\"status\":\"${status}\",\"started_at\":\"${started}\"}"
done

# Write state file (always)
all_status="${all_status#,}"
echo "{\"timestamp\":\"${now}\",\"mode\":\"${mode}\",\"containers\":{${all_status}}}" > "$STATE"

if [ -n "$issues" ]; then
    echo -e "🔍 Container Issues detected (${now}) [mode: ${mode}]:\n${issues}"
    echo "[${now}] ISSUES [${mode}]: ${issues}" >> "$LOG"
    exit 0  # exit 0 so stdout gets delivered; content is the alert
fi

# Silent = no output = nothing delivered
exit 0
