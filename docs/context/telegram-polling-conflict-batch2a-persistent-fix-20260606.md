# Telegram Polling Conflict — Batch 2A Persistent Fix

**Date:** 2026-06-06
**Predecessor:** Batch 2A runtime fix (GREEN)
**Branch:** fix/telegram-polling-conflict-batch2a-20260606

---

## 1. Executive Verdict

**GREEN** — The Telegram polling conflict fix is now persistent across container restarts. Three mechanisms ensure longevity:

1. **gateway_state.json** — Redundant profiles set to `"stopped"` on persistent Docker volume
2. **docker-compose volume mount** — Init script auto-patches telegram.py settle delay on every boot
3. **telegram-polling-guard.sh** — Management script for apply/revert/status

No secrets exposed. No trading configs changed. No trading containers restarted.

---

## 2. Problem Summary

The runtime fix (s6 `down` files + in-container telegram.py patch) was **non-persistent**:
- s6 `down` files live on tmpfs (`/run/service/`) — lost on container restart
- telegram.py patch lives in container filesystem — lost on image update/rebuild

After a `docker restart`, the s6 reconciler would re-read `gateway_state.json` and potentially restart redundant pollers.

---

## 3. Persistence Mechanisms

### Layer 1: gateway_state.json (Primary Fix)

The s6 reconciler (`hermes_cli.container_boot`) reads `gateway_state.json` per profile. Only `"running"` triggers auto-start. All other states (including missing file) register the service as DOWN.

**Changes on persistent volume** (`/opt/hermes-green/config/profiles/*/gateway_state.json`):

| Profile | Before | After | Method |
|---------|--------|-------|--------|
| default (root) | running | running (KEPT) | No change |
| trading | no file | stopped | Created with exit_reason: telegram_polling_guard |
| mira | no file | stopped | Created with exit_reason: telegram_polling_guard |
| orchestrator | starting | stopped | Updated, exit_reason: telegram_polling_guard |
| weather | no file | stopped | Created with exit_reason: telegram_polling_guard |
| weatherbot | no file | stopped | Created with exit_reason: telegram_polling_guard |

**Key insight from container_boot.py:**
```python
_AUTOSTART_STATES = frozenset({"running"})
```
Profiles with `"stopped"`, `"starting"`, `None`, or missing files are registered with a `down` file in the s6 service directory and never auto-started.

### Layer 2: Init Script Volume Mount (Settle Delay)

A custom s6-overlay cont-init.d script patches `telegram.py` with the 15-second settle delay on every container boot.

**Host path:** `/opt/hermes-green/scripts/99-telegram-settle-delay`
**Container path:** `/etc/cont-init.d/99-telegram-settle-delay` (mounted read-only)

**docker-compose.yml change:**
```yaml
volumes:
  - /opt/hermes-green/scripts/99-telegram-settle-delay:/etc/cont-init.d/99-telegram-settle-delay:ro
```

The script:
- Runs after `02-reconcile-profiles` (lexicographic order: `99-` > `02-`)
- Checks if already patched (idempotent)
- Inserts `await asyncio.sleep(15)` after `_drain_polling_connections()` with correct indentation
- Uses atomic temp-file write to avoid corruption

### Layer 3: Management Script

`scripts/telegram-polling-guard.sh` provides a CLI for ongoing management:

```bash
sudo bash scripts/telegram-polling-guard.sh apply    # Disable redundant pollers
sudo bash scripts/telegram-polling-guard.sh revert   # Re-enable all pollers
sudo bash scripts/telegram-polling-guard.sh status   # Show current states
```

---

## 4. Files Changed

### Git (committed to branch)

| File | Change |
|------|--------|
| `docker-compose.yml` | Added volume mount for settle delay init script |
| `scripts/telegram-polling-guard.sh` | New — gateway_state.json management |
| `scripts/telegram-settle-delay-init.sh` | New — s6-overlay init script for telegram.py patch |
| `docs/context/telegram-polling-conflict-batch2a-20260606.md` | Batch 2A runtime fix report |
| `docs/context/telegram-polling-conflict-batch2a-persistent-fix-20260606.md` | This report |

### Host (non-git, persistent)

| Path | Change |
|------|--------|
| `/opt/hermes-green/config/profiles/*/gateway_state.json` | 5 profiles set to "stopped" |
| `/opt/hermes-green/scripts/99-telegram-settle-delay` | Init script deployed |
| `/opt/hermes-green/docker-compose.yml` | Volume mount added (live copy) |

---

## 5. Runtime Verification

| Metric | Result |
|--------|--------|
| gateway-default uptime | 200+ seconds (stable) |
| Polling conflicts (post-settle) | 0 |
| Trading containers | All healthy, unchanged |
| Secrets in git diff | None |
| sendMessage-only alerts | Unchanged, functional |

---

## 6. Architecture: How It Survives Restarts

```
Container restart
  -> s6-overlay starts
  -> cont-init.d/01-hermes-setup (chown, seed)
  -> cont-init.d/015-supervise-perms (s6 perms)
  -> cont-init.d/02-reconcile-profiles (container_boot.py)
     -> reads gateway_state.json per profile
     -> "running" -> create service (no down file) -> auto-start
     -> "stopped" -> create service WITH down file -> stays down
     -> missing  -> create service WITH down file -> stays down
  -> cont-init.d/99-telegram-settle-delay (our patch)
     -> patches telegram.py with 15s settle delay
  -> s6-svscan starts scanning /run/service/
     -> default: no down file -> starts -> canonical poller
     -> trading/mira/orch/weather/weatherbot: down file -> stays down
```

---

## 7. Rollback

### Re-enable a specific profile:
```bash
sudo bash scripts/telegram-polling-guard.sh revert
# OR manually: edit gateway_state.json, set "gateway_state": "running"
# Then: hermes -p <profile> gateway start (inside container)
```

### Remove settle delay volume mount:
```bash
# Remove from docker-compose.yml:
#   - /opt/hermes-green/scripts/99-telegram-settle-delay:/etc/cont-init.d/99-telegram-settle-delay:ro
# Then: docker compose up -d (recreates container)
```

### Full git rollback:
```bash
git revert <commit-sha>
```

---

## 8. Remaining Considerations

1. **orchestrator state file race**: The running default gateway may update orchestrator's gateway_state.json to "starting". This is cosmetic — "starting" is not in `_AUTOSTART_STATES` and won't trigger auto-start on next restart.

2. **Image updates**: If `nousresearch/hermes-agent:latest` is updated, the settle delay init script will re-apply the patch automatically on next boot. If the upstream fixes the conflict handler, the init script is idempotent and will detect the already-patched state.

3. **Upstream contribution**: The 15s settle delay should be contributed upstream to the Hermes Agent project as a proper fix for the PTB conflict handler race condition.

---

## 9. Final Verdict: GREEN

- Persistent fix across container restarts and image updates
- Three-layer defense: gateway_state.json + init script + management CLI
- Zero polling conflicts post-settle
- No secrets exposed, no trading configs changed, no trading containers restarted
- Fully reversible via management script or git revert
