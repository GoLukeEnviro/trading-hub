# Kill-Switch Reference Procedure

> **Component:** `freqtrade/shared/kill_switch.py`
> **State file:** `var/kill_switch.json` (host), `/freqtrade/shared/kill_switch.json` (container)
> **Runbook:** `docs/runbooks/kill-switch.md` (full operational reference)
> **Last updated:** 2026-07-03

---

## Quick Reference

### Modes

| Mode | Effect | Use Case |
|------|--------|----------|
| `NORMAL` | No blocking | Normal operation |
| `HALT_NEW` | Block all new entries, keep positions | Elevated risk, manual pause |
| `EMERGENCY` | Block entries + signal exit all positions | Drawdown breach, exchange outage |

### CLI (Python module)

```bash
# Status
python3 freqtrade/shared/kill_switch.py status

# Halt new entries
python3 freqtrade/shared/kill_switch.py halt "reason"

# Emergency — close all positions
python3 freqtrade/shared/kill_switch.py emergency "reason"

# Clear — revert to NORMAL
python3 freqtrade/shared/kill_switch.py clear
```

### CLI (trigger script)

```bash
./orchestrator/scripts/kill_switch_trigger.sh status
./orchestrator/scripts/kill_switch_trigger.sh halt "reason"
./orchestrator/scripts/kill_switch_trigger.sh emergency "reason"
./orchestrator/scripts/kill_switch_trigger.sh clear
```

### Python API

```python
from freqtrade.shared.kill_switch import (
    get_kill_mode,      # -> "NORMAL" | "HALT_NEW" | "EMERGENCY"
    is_kill_active,     # -> bool
    is_emergency,       # -> bool
    set_kill_mode,      # set mode with reason + optional auto-clear
    clear_kill_switch,  # revert to NORMAL
    load_kill_state,    # full state dict
)
```

---

## Rollback Procedure (Canary)

When rolling back `freqtrade-freqforge-canary` from live to dry-run:

1. **Set kill switch to EMERGENCY:**
   ```bash
   python3 freqtrade/shared/kill_switch.py emergency "canary rollback — max_drawdown breach"
   ```

2. **Stop canary container:**
   ```bash
   docker stop freqtrade-freqforge-canary
   ```
   Or use the emergency stop script:
   ```bash
   ./orchestrator/scripts/emergency_stop.sh --reason "canary rollback"
   ```

3. **Restore dry-run config** from `var/si_v2/live_canary_activation_ceremony/pre_activation_config_snapshot.json`

4. **Redeploy canary in dry-run mode**

5. **Verify dry-run operation** (logs, DB, API health)

6. **Reset kill switch to NORMAL:**
   ```bash
   python3 freqtrade/shared/kill_switch.py clear "canary rollback complete"
   ```

7. **File post-mortem** in `docs/incidents/`

---

## Safety Principles

- **Fail-safe:** Module returns HALT_NEW on any read error
- **Atomic writes:** `.tmp` + `os.replace()` pattern
- **Auto-clear:** Timer-based, evaluated on every read
- **No override:** `auto-check` does not override an active kill switch
