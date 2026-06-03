# Observation Watchdog task-3-watchdog — Implementation Note

## 1. Summary
- Implemented `orchestrator/scripts/observation_watchdog.py` as a standalone `report_only` watchdog for the Observation Runner heartbeat.
- The watchdog only reads the runner heartbeat, manages its own lock, writes escalation JSON files when required, and optionally posts the same escalation payload to the configured webhook.

## 2. What changed
- Added atomic watchdog locking via `state/locks/watchdog.lock` with young-lock skip and stale-lock takeover.
- Added robust heartbeat parsing for timezone-aware and naive ISO-8601 timestamps.
- Added stale/missing/unreadable heartbeat escalation handling with dedicated escalation JSON output under `/opt/data/profiles/orchestrator/escalations/`.
- Added optional webhook delivery via `HERMES_ALERT_WEBHOOK` using `curl` with a 5-second timeout and log-only failure handling.
- Added a dedicated watchdog log file at `/opt/data/profiles/orchestrator/logs/observation_watchdog.log`.

## 3. Validation
- Added `orchestrator/tests/test_observation_watchdog.py` with 9 deterministic test cases covering:
  - fresh heartbeat
  - stale heartbeat
  - missing heartbeat file
  - corrupt heartbeat file
  - young active lock skip
  - stale lock takeover
  - webhook failure handling
  - missing webhook URL handling
  - naive timestamp parsing
- Verified targeted suite with:
  - `uv run --with pytest pytest orchestrator/tests/test_observation_watchdog.py -v`
- Verified the full orchestrator test suite with:
  - `uv run --with pytest pytest orchestrator/tests -q`
- Result: all tests passed.

## 4. Runtime behavior
- The watchdog does not update the heartbeat and does not modify any runner or trading system state.
- It exits 0 for normal operation and for handled escalation paths.
- It exits 1 only for severe internal errors such as lock acquisition failures or unexpected exceptions.
- The script is executable and ready for cron wiring with the admin-provided schedule.

## 5. Notes
- The escalation payload uses the watchdog-specific agent id `hermes-trading-observation-watchdog-phase1`.
- The stale-lock path writes a dedicated escalation describing that the watchdog itself may have crashed.
- The implementation stays deliberately minimal and does not depend on `observation_common.py`.
