# Rainbow: Harden Producer Lifecycle and Factory-Mode Observability

**Status:** Backlog — not started
**Priority:** M
**Dependency:** Rainbow Recovery GREEN, SI-v2 Scheduled Cycle GREEN

---

## Goal

Harden the Rainbow Producer lifecycle so it survives graceful shutdowns, host reboots, and non-interactive process termination. Fix factory-mode logging so all log output (including `--factory` path) is captured in the persistent log file.

The producer must reliably feed fresh signals into the SI-v2 Active Cycle Runner so scoring-eligible cycles don't break when the producer stops.

---

## Acceptance Criteria

### Boot Persistence

1. Move PID file from `/tmp/rainbow_producer.pid` to persistent path (e.g., `/opt/data/rainbow/rainbow_producer.pid`)
2. Move log file from `/tmp/rainbow_producer.log` to persistent path (e.g., `/opt/data/rainbow/rainbow_producer.log`)
3. Create or update `orchestrator/scripts/rainbow_producer_manager.sh` to use persistent paths
4. Add a simple freshness watchdog script that checks `/health` and reports if Producer is DOWN
5. Document boot-persistence plan with explicit approval gate before enabling any auto-start mechanism
6. Do NOT enable cron-based or systemd auto-restart until approval is given in a separate rollout issue

### Factory-Mode Logging Fix

7. In `ai4trade-bot/rainbow/main.py`, call `setup_logging()` inside `create_app()` (the factory path) so logs are produced when the manager runs with `--factory`
8. Ensure no duplicate handler registration when `create_app()` is called after `main()`-path `setup_logging()` has already run
9. Add or extend tests for factory-mode logging in the ai4trade-bot test suite
10. Verify log output from the factory path appears in the persistent log file after restart via manager

### Safety Invariants (must not be violated)

- No change to SI-v2 scoring logic
- No bypass of Rainbow freshness guard (900s)
- No synthetic re-timestamping
- No `dry_run=false`
- No live trading mutation
- No change to `can_execute=False` / `dry_run_only=True`
- No change to `PAUSED / L3_REPOSITORY_ONLY` controller state

---

## Implementation Notes

### PID/Log relocation

Current:
```
/tmp/rainbow_producer.pid
/tmp/rainbow_producer.log
```

Target:
```
/opt/data/rainbow/rainbow_producer.pid
/opt/data/rainbow/rainbow_producer.log
```

### Factory logging fix

File: `ai4trade-bot/rainbow/main.py`

The `create_app()` function (called by `uvicorn --factory`) does not call `setup_logging()`. Only `main()` calls it. The fix should:

1. Add a `_log_initialized` guard to prevent double-init
2. Call `setup_logging()` at the start of `create_app()`
3. Ensure log file path is configurable via environment variable or config

---

## Dependencies

- Rainbow Producer Recovery: GREEN (completed 2026-06-23)
- SI-v2 Scheduled Cycle: GREEN (2 consecutive cycles confirmed)
- ai4trade-bot repo accessible

---

## Reference to Self-Improvement Loop

Without fresh Rainbow signals, the SI-v2 Active Cycle Runner runs but produces cycles without scoring-eligible Rainbow data. This task stabilizes the path:

```
Producer → Adapter → Active Cycle → Evidence Bundle → ShadowProposal → Scoring Gate
```

By hardening the Producer lifecycle, SI-v2 can sustain long-running scoring-eligible cycles with real 4-bot data.

---

## Related Reports

- `docs/reports/rainbow-producer-freshness-recovery-2026-06-23.md`
- `docs/reports/si-v2-scheduled-cycle-proof-after-rainbow-recovery-2026-06-23.md`
