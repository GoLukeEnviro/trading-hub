# Kill-Switch Runbook

> **Component:** `freqtrade/shared/kill_switch.py`
> **Trigger:** `orchestrator/scripts/kill_switch_trigger.sh`
> **State file:** `var/kill_switch.json` (host), `/freqtrade/shared/kill_switch.json` (container)
> **Integration:** Choke point in `primo_signal.py:primo_gate_allows()`
> **PR:** #220 — feat(kill-switch): wire central kill_switch.py + patch primo_signal + trigger script

---

## 1. Purpose

The kill switch is the highest-priority, central choke point for fleet-wide entry blocking.
It sits in `primo_gate_allows()` — the function every Freqtrade strategy calls before entering
a position. When active, it overrides all other signal logic.

Three modes:

| Mode | Effect | Use case |
|------|--------|----------|
| `NORMAL` | No blocking. All gates pass to primo/risk logic. | Normal operation |
| `HALT_NEW` | Block all new entries fleet-wide. Open positions are kept. | Elevated risk, manual pause, operator override |
| `EMERGENCY` | Block entries AND signal strategies to close open positions. | Drawdown breach, exchange outage, emergency |

---

## 2. File Architecture

```
trading-hub/
├── var/kill_switch.json              # Host state file (not tracked in git)
├── freqtrade/shared/kill_switch.py   # Python module — loaded by FT containers + pipeline
├── freqtrade/shared/primo_signal.py  # Choke point — calls is_kill_active()
└── orchestrator/scripts/
    └── kill_switch_trigger.sh        # CLI + auto-check trigger
```

### State file (`var/kill_switch.json`)

```json
{
  "mode": "NORMAL",
  "reason": "",
  "triggered_at": "",
  "triggered_by": "",
  "auto_clear_at": ""
}
```

Valid modes: `NORMAL`, `HALT_NEW`, `EMERGENCY`.

### Path resolution (priority)

1. `$KILL_SWITCH_FILE` env var override
2. `/freqtrade/shared/kill_switch.json` (inside FT containers)
3. `var/kill_switch.json` relative to project root (host pipeline)

---

## 3. CLI Usage

### Trigger script

```bash
./orchestrator/scripts/kill_switch_trigger.sh <command> [reason]
```

| Command | Description |
|---------|-------------|
| `status` | Print current state |
| `halt [reason]` | Activate `HALT_NEW` — block all new entries |
| `emergency [reason]` | Activate `EMERGENCY` — block entries + close positions |
| `clear [reason]` | Revert to `NORMAL` |
| `auto-check` | Read `fleet_risk_state.json`, auto-activate if drawdown exceeds thresholds |

### Examples

```bash
# Check status
./orchestrator/scripts/kill_switch_trigger.sh status

# Halt new entries during manual review
./orchestrator/scripts/kill_switch_trigger.sh halt "manual review of signal drift"

# Emergency — drawdown breach detected
./orchestrator/scripts/kill_switch_trigger.sh emergency "DD 15% across fleet — emergency close"

# Clear after incident resolved
./orchestrator/scripts/kill_switch_trigger.sh clear "review complete, resume normal ops"
```

### Python module (direct)

```python
from kill_switch import (
    get_kill_mode,      # -> "NORMAL" | "HALT_NEW" | "EMERGENCY"
    is_kill_active,     # -> bool (True if not NORMAL)
    is_emergency,       # -> bool (True if EMERGENCY)
    set_kill_mode,      # set mode with reason + optional auto-clear
    clear_kill_switch,   # revert to NORMAL
    load_kill_state,    # get full state dict
)
```

### CLI via Python directly

```bash
# Same commands as trigger script
python3 freqtrade/shared/kill_switch.py status
python3 freqtrade/shared/kill_switch.py halt "manual halt"
python3 freqtrade/shared/kill_switch.py emergency "drawdown breach"
python3 freqtrade/shared/kill_switch.py clear
```

---

## 4. Auto-Check (Drawdown Guard)

The `auto-check` command reads `freqtrade/shared/fleet_risk_state.json` to find the
worst drawdown across all bots, then acts automatically:

| Condition | Threshold (default) | Action |
|-----------|-------------------|--------|
| Worst DD >= EMERGENCY threshold | 18% | Activate `EMERGENCY` |
| Worst DD >= HALT threshold | 12% | Activate `HALT_NEW` |
| Worst DD < both thresholds | — | No action |

The script **skips** if a kill switch is already active (no unnecessary state changes).

### Configurable thresholds

```bash
DD_HALT_THRESHOLD=15 DD_EMERGENCY_THRESHOLD=22 \
    ./orchestrator/scripts/kill_switch_trigger.sh auto-check
```

### Cron integration

Expected pattern: `auto-check` triggered via Hermes cron job on a regular cadence
(e.g., every 30 min during trading hours).

---

## 5. Auto-Clear (Timer)

`set_kill_mode()` supports an `auto_clear_minutes` parameter. When set, the module
reverts to `NORMAL` mode after the specified number of minutes.

```python
from kill_switch import set_kill_mode

# Auto-clear after 60 minutes
set_kill_mode("HALT_NEW", reason="scheduled maintenance",
              auto_clear_minutes=60, triggered_by="cron")
```

The `load_kill_state()` function checks `auto_clear_at` on every read and clears
automatically if the timestamp has passed.

---

## 6. Monitoring

### What to check

- Current mode: `./kill_switch_trigger.sh status`
- Reason + triggered_by: included in status output
- Drawdown: read `freqtrade/shared/fleet_risk_state.json` manually
- `primo_gate_allows()` logs: grep for `"BLOCKED by kill switch"` in Freqtrade logs

### Dashboard indicators

The following should be surfaced on the operational dashboard:

| Status | Color | Meaning |
|--------|-------|---------|
| `NORMAL` | 🟢 Green | Normal operation |
| `HALT_NEW` | 🟠 Yellow | Entries blocked, positions held |
| `EMERGENCY` | 🔴 Red | All trading halted, positions closing |

---

## 7. Incident Response

### Scenario: DD breach detected

```bash
# 1. Check current state
./kill_switch_trigger.sh status

# 2. If threshold crossed — activate
./kill_switch_trigger.sh emergency "DD $(get_worst_dd)% — automatic activation"

# 3. Investigate root cause
#    - Check Freqtrade logs
#    - Check market conditions
#    - Check signal quality

# 4. When resolved — clear
./kill_switch_trigger.sh clear "DD recovered, root cause: [summary]"
```

### Scenario: Manual operator override

```bash
# Immediate halt
./kill_switch_trigger.sh halt "operator override during configuration change"

# After work completed
./kill_switch_trigger.sh clear "config change validated, resuming"
```

---

## 8. Safety Principles

1. **Fail-safe:** If `kill_switch.py` cannot be imported by a strategy, a fallback
   no-op function is used that always returns `False` (not blocked). Kill switch
   protection degrades gracefully — the strategy continues with normal logic.
2. **Atomic writes:** All state file writes use `.tmp` + `os.replace()` to prevent
   half-written reads.
3. **mtime cache:** `load_kill_state()` caches on file mtime — no redundant I/O
   during strategy loop.
4. **Auto-clear:** Timer-based auto-clear is evaluated on every read, not on an
   external scheduler — no missed clears.
5. **Drawdown guard:** `auto-check` does not override an already-active kill switch.
   Human clear is required to resume after auto-activation.

---

## 9. Reference

- `freqtrade/shared/kill_switch.py` — 270 lines, 3 modes, atomic file-based state
- `orchestrator/scripts/kill_switch_trigger.sh` — CLI wrapper (status/halt/emergency/clear/auto-check)
- `freqtrade/shared/primo_signal.py:primo_gate_allows()` — integration point
- `var/kill_switch.json` — runtime state file (not tracked in git)
- `var/kill_switch.json.example` — template for state file (tracked, never mutated)
- `orchestrator/scripts/drawdown_guard.py` — periodic fleet-health + drawdown monitor; calls `kill_switch_trigger.sh auto-check` at configured cadence

---

## 10. Activation Ceremony — Guarded Cron / Scheduler Configuration

### Purpose

Enable the `auto-check` drawdown guard as a scheduled (cron) job *only* after a
validated activation ceremony. This prevents accidental or premature wiring of
the kill switch auto-trigger before the following preconditions are met.

### Preconditions (all must be GREEN)

| # | Check | Required state | Evidence |
|---|-------|----------------|----------|
| 1 | Controller status | `PAUSED`, `IDLE`, or `STOPPED` | `orchestrator/control/STATE.json` |
| 2 | Queue empty | No pending work items | `orchestrator/control/QUEUE.json` |
| 3 | Active fields null | No active work item, branch, or PR | `orchestrator/control/STATE.json` |
| 4 | Baseline reconciled | `STATE.canonical_main_commit == QUEUE.base_commit` | Both files |
| 5 | `var/kill_switch.json` exists | NORMAL mode, valid JSON | `python3 freqtrade/shared/kill_switch.py status` |
| 6 | `var/kill_switch.json.example` present | Template matches current schema | `diff var/kill_switch.json.example var/kill_switch.json` (keys only) |

### Ceremony Steps

```bash
# ── Step 1: Verify preconditions ──
./orchestrator/scripts/kill_switch_trigger.sh status
# Expected: Mode: NORMAL, Reason: (empty), Triggered_by: (empty)

# ── Step 2: Verify state file template ──
diff <(python3 -c "import json; print(sorted(json.load(open('var/kill_switch.json.example')).keys()))") \
      <(python3 -c "import json; print(sorted(json.load(open('var/kill_switch.json')).keys()))")

# ── Step 3: Dry-run the auto-check (no-op if no threshold breached) ──
DD_HALT_THRESHOLD=12 DD_EMERGENCY_THRESHOLD=18 \
    ./orchestrator/scripts/kill_switch_trigger.sh auto-check

# ── Step 4: Enable the cron job ──
# Add the following entry to the Hermes cron config or system crontab:
#   */30 * * * * hermes /home/hermes/projects/trading/orchestrator/scripts/kill_switch_trigger.sh auto-check >> /home/hermes/projects/trading/orchestrator/logs/kill_switch_auto_check.log 2>&1

# ── Step 5: Observe for 2 cycles (60 min) ──
# Verify logs at orchestrator/logs/kill_switch_auto_check.log
# Verify no spurious activations
```

### Verification

After ceremony, run:

```bash
./orchestrator/scripts/kill_switch_trigger.sh status
# Mode: NORMAL  (unless a threshold was actually breached during observation)
```

### Rollback

If the cron job fires spuriously:

```bash
# 1. Remove the cron entry
# 2. Clear any unintended activation
./orchestrator/scripts/kill_switch_trigger.sh clear "rollback: spurious activation during ceremony"
# 3. Investigate root cause (thresholds too low, stale fleet_risk_state, etc.)
```

### Safety invariants (enforced by design)

1. **Fail-closed:** `auto-check` never overrides an already-active kill switch.
2. **Dry-run first:** The script only activates when thresholds are actually breached.
3. **Observability:** Every auto-check decision is logged and surfaced via `status`.
4. **Idempotent:** Re-running `auto-check` when already active is a no-op.
5. **Ceremony-gated:** Cron is never enabled without explicit validated ceremony.
6. **No runtime mutation:** The trigger script is pure file I/O — no Docker, no Freqtrade API calls, no network.
