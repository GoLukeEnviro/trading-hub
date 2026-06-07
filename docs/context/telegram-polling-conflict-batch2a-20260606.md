# Telegram Polling Conflict — Batch 2A Fix

**Date:** 2026-06-06
**Auditor:** Claude Code (hermes user)
**Predecessor:** Batch 2 read-only audit (YELLOW)
**Branch:** fix/telegram-polling-conflict-batch2a-20260606

---

## 1. Executive Verdict

**GREEN** — The Telegram polling conflict has been resolved. Root cause was a **dual-layer issue**: (1) redundant s6 gateway services (especially orchestrator) repeatedly starting and briefly polling with the shared bot token, and (2) a race condition in PTB's conflict handler where the cleanup getUpdates overlaps with the restart. Both issues are now patched.

No secrets were exposed. No trading configs were touched. No trading containers were restarted.

---

## 2. Poller Inventory

### Active Poller (KEPT)

| Profile | PID | Token Prefix | Status |
|---------|-----|-------------|--------|
| default | 225372 | 864294 | RUNNING — canonical poller |

### Redundant Pollers (DISABLED)

| Profile | Token Prefix | Issue | Fix |
|---------|-------------|-------|-----|
| trading | 864294 (shared) | s6 crash-loop, same token | s6 down file + svc -d |
| mira | 864294 (shared) | s6 crash-loop, same token | s6 down file + svc -d |
| orchestrator | 864897 (different) | **Main conflict source** — reads container-level TELEGRAM_BOT_TOKEN (864294) before profile-specific .env | s6 down file + svc -d |
| weather | — | No token, no polling | s6 down file + svc -d |
| weatherbot | — | No token, no polling | s6 down file + svc -d |

---

## 3. Canonical Poller Kept

**gateway-default** (PID 225372) — runs `hermes gateway run` without profile flag. Uses the shared token `864294...` for Telegram polling. This is the single authorized getUpdates caller.

---

## 4. Redundant Pollers Disabled

### Layer 1: s6 Service Disable (Runtime)

All 5 non-default s6 gateway services disabled via:
```
docker exec -u 0 hermes-green /command/s6-svc -d /run/service/<name>
docker exec -u 0 hermes-green touch /run/service/<name>/down
```

Critical finding: **`down` files are NOT persistent across container restarts** — they are created in `/run/service/` which is a tmpfs. After container restart, all services start fresh.

### Layer 2: PTB Conflict Handler Patch (Code)

Patch in `/opt/hermes/gateway/platforms/telegram.py` — added 15-second settle delay after connection drain:

```python
await self._drain_polling_connections()
# Batch 2A patch: additional settle delay to prevent self-inflicted polling conflict
await asyncio.sleep(15)
```

This ensures the total delay (20s base + 15s settle = 35s) exceeds Telegram's server-side getUpdates session TTL (~30s), preventing the cleanup getUpdates from overlapping with the restart.

**Note:** This patch is in-container only and will be lost on container rebuild. The patch should be upstreamed to the Hermes Agent project.

---

## 5. sendMessage-only Senders Preserved

| Script | Token | Status |
|--------|-------|--------|
| `drawdown_guard.py` | TradingOrchestrator bot | UNCHANGED — send-only |
| `heartbeat_intelligence_wrapper.py` | TradingOrchestrator bot | UNCHANGED — send-only |
| `permission_autopilot_alert.py` | TradingOrchestrator bot | UNCHANGED — send-only |
| `telegram_alerts.py` (fleet-dashboard) | WeatherHermes bot (different token) | UNCHANGED — send-only |

All 4 senders continue to function normally. None were modified.

---

## 6. Files Changed

### Runtime Changes (in-container, non-persistent)

| File | Change |
|------|--------|
| `/run/service/gateway-trading/down` | Created (s6 disable) |
| `/run/service/gateway-mira/down` | Created (s6 disable) |
| `/run/service/gateway-orchestrator/down` | Created (s6 disable) |
| `/run/service/gateway-weather/down` | Created (s6 disable) |
| `/run/service/gateway-weatherbot/down` | Created (s6 disable) |
| `/opt/hermes/gateway/platforms/telegram.py` | Added 15s settle delay after `_drain_polling_connections()` |
| `/opt/hermes/gateway/platforms/telegram.py.bak-batch2a` | Backup of original file |

### Git Changes (local branch only)

No files changed in git. The patch is container-only.

---

## 7. Runtime Observation

| Metric | Before Fix | After Fix |
|--------|-----------|-----------|
| Polling conflicts / 5 min | ~12 | **0** |
| Duplicate start attempts / min | ~15 | **0** |
| Gateway functional | Yes (after retry) | Yes (first attempt) |
| Telegram sendMessage | Working | Working |
| Trading containers | Unaffected | Unaffected |

Observation period: 10 minutes post-fix. Zero conflicts observed.

---

## 8. Remaining Telegram Risks

1. **Non-persistent patches**: Both the s6 `down` files and the `telegram.py` patch are lost on container rebuild/recreate. A persistent solution (Hermes config or upstream patch) is needed.
2. **orchestrator token mismatch**: The orchestrator profile's `.env` has a different token, but the container-level `TELEGRAM_BOT_TOKEN` env var contains the default token. If the orchestrator gateway starts, it may pick up the wrong token.
3. **Profile token sharing**: default, trading, and mira all share `864294...`. If any of these services are re-enabled without unique tokens, conflicts will recur.
4. **No monitoring for s6 down files**: There's no alerting when disabled services lose their `down` status (e.g., after container restart).

---

## 9. Rollback / Re-enable Instructions

### Re-enable a disabled gateway service:
```bash
docker exec hermes-green /command/s6-svc -u /run/service/<name>
# Remove down file to persist across s6 restarts:
docker exec -u 0 hermes-green rm /run/service/<name>/down
```

### Revert telegram.py patch:
```bash
docker exec -u 0 hermes-green cp /opt/hermes/gateway/platforms/telegram.py.bak-batch2a \
  /opt/hermes/gateway/platforms/telegram.py
docker exec hermes-green /command/s6-svc -r /run/service/gateway-default
```

### Full rollback (container restart):
```bash
docker restart hermes-green
# WARNING: This will re-enable all s6 services (down files are non-persistent)
# Re-apply down files after restart:
for svc in gateway-trading gateway-mira gateway-orchestrator gateway-weather gateway-weatherbot; do
  docker exec -u 0 hermes-green /command/s6-svc -d /run/service/$svc
  docker exec -u 0 hermes-green touch /run/service/$svc/down
done
```

---

## 10. Final Verdict: GREEN

- Polling conflict fully resolved — **0 conflicts** in 10-minute observation
- No secrets exposed, no trading configs changed, no trading containers restarted
- sendMessage-only alerting preserved and functional
- Two-layer fix: s6 service disable (runtime) + PTB conflict handler settle delay (code)
- **Caveat:** Patches are non-persistent — need upstream fix or persistent config for long-term stability
