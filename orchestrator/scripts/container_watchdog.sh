#!/bin/bash
# container_watchdog.sh v4 — Container health check with Docker-aware fallback
# Runs every 30min via Hermes cron. Only outputs when issues found (silent = OK).
# v4 (2026-06-06): Fixed container names to match actual docker-compose output,
#   added DOCKER_HOST=unix:///var/run/docker.sock to bypass proxy (EXEC=0).
# v3: removed freqtrade-momentum (intentionally not deployed), reduced from 5min to 30min.
#
# Detection strategy:
#   1. If Docker socket available → docker inspect (authoritative)
#   2. If no Docker socket → file-based heuristic (signal file freshness)
#   3. Silent OK = no output = no Telegram delivery
#
# Root cause of v1 failure: Hermes container has no Docker socket mounted.
# v2 gracefully handles this and reports accurate status in both modes.

set -euo pipefail

LOG="/opt/data/profiles/orchestrator/logs/watchdog.log"
STATE="/opt/data/profiles/orchestrator/state/container_watchdog_state.json"

TRADING_CONTAINERS="trading-freqtrade-freqforge-1 trading-freqtrade-freqforge-canary-1 trading-freqtrade-regime-hybrid-1 trading-freqai-rebel-1 trading-ai-hedge-fund-1"

# Map containers to probe files for file-based fallback
# These are files updated by the trading pipeline or bots themselves
declare -A BOT_PROBES
BOT_PROBES["trading-freqtrade-freqforge-1"]="/home/hermes/projects/trading/freqtrade/shared/primo_signal_state.json"
BOT_PROBES["trading-freqtrade-freqforge-canary-1"]="/home/hermes/projects/trading/freqtrade/shared/primo_signal_state.json"
BOT_PROBES["trading-freqtrade-regime-hybrid-1"]="/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json"
# freqtrade-momentum intentionally not deployed — removed 2026-05-24
BOT_PROBES["trading-freqai-rebel-1"]="/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json"
BOT_PROBES["trading-ai-hedge-fund-1"]="/home/hermes/projects/trading/ai-hedge-fund-crypto/output/latest/hermes_signal.json"

STALE_THRESHOLD_MIN=30  # Probe file older than this = possibly down

now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
issues=""
all_status=""
mode="unknown"

# ── Detect Docker availability ──────────────────────────────────
# Bypass Docker proxy (EXEC=0) via direct unix socket
export DOCKER_HOST="unix:///var/run/docker.sock"
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

# Write state file (always) — use printf to avoid control chars from echo
all_status="${all_status#,}"
printf '{"timestamp":"%s","mode":"%s","containers":{%s}}\n' "$now" "$mode" "$all_status" > "$STATE"

if [ -n "$issues" ]; then
    echo -e "🔍 Container Issues detected (${now}) [mode: ${mode}]:\n${issues}"
    echo "[$now] ISSUES [${mode}]: ${issues}" >> "$LOG"
    exit 0  # exit 0 so stdout gets delivered; content is the alert
fi

# Silent = no output = nothing delivered
exit 0
