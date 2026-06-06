#!/command/with-contenv sh
# 99-telegram-settle-delay — Patches PTB conflict handler with 15s settle delay
#
# s6-overlay cont-init.d script. Runs after 02-reconcile-profiles.
# Mounts via docker-compose volume:
#   /opt/hermes-green/scripts/99-telegram-settle-delay:/etc/cont-init.d/99-telegram-settle-delay:ro
#
# The 15s delay ensures the total drain+settle time (20s+15s=35s) exceeds
# Telegram's server-side getUpdates session TTL (~30s), preventing the
# cleanup getUpdates from overlapping with the restart.
#
# This is a defense-in-depth measure. Primary fix: single poller via
# gateway_state.json (see telegram-polling-guard.sh).

TELEGRAM_PY="/opt/hermes/gateway/platforms/telegram.py"
MARKER="# Batch 2A patch: additional settle delay"

if [ ! -f "${TELEGRAM_PY}" ]; then
    echo "[99-telegram-settle-delay] SKIP: ${TELEGRAM_PY} not found"
    exit 0
fi

# Check if already patched
if grep -qF "${MARKER}" "${TELEGRAM_PY}" 2>/dev/null; then
    echo "[99-telegram-settle-delay] OK: already patched"
    exit 0
fi

# Apply patch: insert 15s settle delay after _drain_polling_connections()
# Uses a temporary file to avoid sed -i on potentially read-only filesystem
PATCHED=$(mktemp)
if sed '/await self\._drain_polling_connections()/a\
    # Batch 2A patch: additional settle delay to prevent self-inflicted polling conflict\
    await asyncio.sleep(15)
' "${TELEGRAM_PY}" > "${PATCHED}" 2>/dev/null; then

    if grep -qF "${MARKER}" "${PATCHED}" 2>/dev/null; then
        cp "${PATCHED}" "${TELEGRAM_PY}"
        echo "[99-telegram-settle-delay] OK: 15s settle delay applied"
    else
        echo "[99-telegram-settle-delay] WARN: patch marker not found in output"
    fi
else
    echo "[99-telegram-settle-delay] WARN: sed patch failed"
fi

rm -f "${PATCHED}"
