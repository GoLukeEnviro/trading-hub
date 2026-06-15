# Kill-Switch Dry-Run Validation Runbook

Issue: #245

This runbook verifies the merged kill-switch wiring without live trading, exchange calls, container restarts, or Docker mutation.

## Safety boundary

- Allowed: local unit tests, temp-file state, mocked `primo_signal` kill-switch hooks.
- Forbidden without explicit approval: container restart/recreate, live exchange calls, `dry_run=false`, manual order placement.

## Expected behavior

| State / signal condition | Expected Freqtrade-facing behavior |
| --- | --- |
| `NORMAL` with no signal | Strategy keeps native dry-run logic (`primo_gate_allows=True`). |
| `WATCH_ONLY` signal verdict | Entries are blocked unless explicit bias allowance exists. |
| `HALT_NEW` kill switch | All new entries are blocked. Existing positions are not force-closed. |
| `EMERGENCY` kill switch | All new entries are blocked and strategies may emit emergency exit intent through their normal dry-run exit hooks. |

## Automated proof

```bash
python3 -m pytest tests/test_kill_switch.py tests/test_kill_switch_dry_run_integration.py -q
```

These tests use temp files and monkeypatches only. They do not contact Freqtrade, Docker, exchanges, or the running fleet.

## Manual dry-run proof path

Manual proof must be performed only after approval if it touches running containers.

1. Snapshot local runtime config and kill-switch state.
2. Confirm every bot config has `dry_run: true`.
3. Set kill-switch state through the approved trigger script.
4. Observe dry-run logs for entry blocking only.
5. Clear kill switch back to `NORMAL`.
6. Record evidence under `docs/context/`.

## Rollback

For automated tests, rollback is automatic because temp files are deleted by pytest. For manual runtime proof, restore the snapshotted kill-switch file or run the approved clear command, then verify mode is `NORMAL`.
