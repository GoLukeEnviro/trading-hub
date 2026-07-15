# APPROVED — R5B Gate 1 Preflight and Freeze

**Decision:** Path 1 — Fleet-wide freeze (all 4 bots including `freqai-rebel`)
**Paths 2 + 3:** Approved for follow-up implementation after Gate 1 completes.

## Marker

```
APPROVED_R5B_GATE_1_PREFLIGHT_AND_FREEZE
```

| Field | Value |
|-------|-------|
| Owner | Luke (GoLukeEnviro) |
| Date | 2026-07-15 |
| Scope | Fleet-wide HALT_NEW freeze — all 4 canonical bots |
| Impacted | `freqtrade-freqforge`, `freqtrade-freqforge-canary`, `freqtrade-regime-hybrid`, `freqai-rebel` |
| UTC start | Operator discretion within 2026-07-15 |
| Max duration | 24 hours |
| Rollback | `clear_kill_switch()` → NORMAL |
| Fail-closed | Any error keeps HALT_NEW active |
| Allowlist | Only kill_switch.py set_kill_mode / clear_kill_switch |

## Follow-up

- Path 2: Bot-scoped freeze arch (A1, integrates with HaltBotRegistry #596)
- Path 3: Rebel lifecycle gate (A2, separate marker required)
