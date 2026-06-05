# 2026-06-05 — Ledger Integrity Watchdog Deployment

## Summary
- **Deployed:** `ledger_integrity_watchdog.py` (Tier-1 autonomous, idempotent, no_agent)
- **Schedule:** `*/30 * * * *` (every 30 min)
- **Cron job_id:** `6f2c7456da39` (recreated twice to defeat scheduler-stall pitfall; current ID is from 3rd creation)
- **Mutations scope:** `fleet_risk_state.json` (audit-trail append only), `canonical_trading_status_latest.json`, `canonical-trading-status.md`, `current-operational-state.md`, `docs/context/ledger-watchdog-<date>.md`
- **Read-only:** `drawdown_state.json` (LIVE_RISK), `fleet_risk_state.json` (except `_audit[]`)
- **No-touch:** strategy code, configs, pairlists, dry_run flags, risk parameters

## What it checks
1. **Source completeness:** active bots (from `canonical-trading-status.md` Active Fleet table) ↔ `portfolio.sources` keys in LEDGER. Mapping via alias table (`freqforge` → `baseline_v1_freqforge`, etc.). Substring fallback for unmapped bots.
2. **Drawdown threshold:** LEDGER `current_drawdown > 3.0%` (R2 trigger of `fleet_risk_auto_params.py`). Note: R2 reads LIVE_RISK, not LEDGER — this is a WATCH flag.
3. **LIVE-LEDGER gap:** `drawdown_state.jsonportfolio_current - fleet_risk_state.jsonportfolio.current_equity`. Currently 1061.62 USDT, of which 994 USDT is the missing rebel source and ~67 USDT is 4-day drift.

## Idempotency design
- Fingerprint = stable JSON of `{missing[], dd_exceeds, dd_value, live_ledger_delta}`
- New audit entry ONLY if `fingerprint != state.last_fingerprint`
- Reporting-Health notes: single watchdog slot (old entries filtered out before prepending fresh)
- Auditability decay: only when `appended_audit=True`
- All atomic writes via `tempfile.mkstemp` + `os.replace`

## Lock
- Path: `/opt/data/profiles/orchestrator/state/locks/ledger_integrity.lock/`
- Stale threshold: 30 min (Takeover: rmtree + recreate + warning log)
- Clean release after every run (try/finally)

## Files
- Script (deployed): `/opt/data/profiles/orchestrator/scripts/ledger integrty_watchdog.py` (23,903 bytes)
- Script (working tree): `/home/hermes/projects/trading/orchestrator/scripts/ledger integrty_watchdog.py` (23,903 bytes)
- Log: `/opt/data/profiles/orchestrator/logs/ledger integrty_watchdog.log`
- State: `/opt/data/profiles/orchestrator/state/ledger_integrity_watchdog_state.json`
- Report (today): `/home/hermes/projects/trading/docs/context/ledger-watchdog-2026-06-05.md`
- Backup of pre-deployment ledger: `/home/hermes/projects/trading/freqtrade/shared/fleet_risk_state.json.bak.2026-06-05T12-05-pre-remove-backtest` (also from earlier regime_hybrid_backtest repair)

## Findings at first deployment (Run 1, 2026-06-05 12:44:46)
- Sources: **WARNING** — missing `freqai-rebel` (994 USDT not in LEDGER)
- Drawdown: **WARNING** — 3.42% > 3.0% R2 threshold
- Live Gap: **INFO** — 1061.62 USDT delta (994 from missing rebel, 67 from 4-day drift)

Audit entry written to `fleet_risk_state.json:_audit[1]`. Fingerprint: `{"dd_exceeds": true, "dd_value": 0.034244, "live_ledger_delta": 1061.62, "missing": ["freqai-rebel"]}`.

## Idempotency verification
- 4 manual test runs (12:44–12:49): only 1 audit entry written, only 1 reporting-health note in canonical
- Stale-lock takeover: tested with 1h-old lock, succeeded
- Fresh-lock skip: tested with fresh lock, returned `status:skipped, exit:0`
- Broken JSON: tested with `{ broken json`, returned `status:error, exit:2` without crash
- All cleanups (lock release, log write) happen in `try/finally`

## Known scheduler pitfall encountered
- **Issue:** First 3 job creations had `last_run_at=null` even after `next_run_at` passed.
- **Confirmed:** 2026-06-05 13:14: `next_run_at=13:00:00` passed, `last_run_at=null`.
- **Workaround applied:** Delete+Recreate the no_agent job, identical params, new job_id. This is documented in `trading-fleet-operations` skill.
- **Current state:** Job ID `6f2c7456da39`, `next_run_at=2026-06-05T13:30:00+00:00`. Awaiting first tick at 13:30 to confirm scheduler is actually firing.

## Next steps (Tier 2 — user approval required)
1. **Add `rebel` source_key to LEDGER collector** — would close the 994 USDT gap
2. **LIVE_RISK refresh** — would close the 67 USDT drift and the 4-day staleness
3. **Watchdog extensions (optional Tier 1)**:
   - Signal freshness check (hermes_signal.json age > 30 min)
   - Permission error trend monitor (per orchestrator config file)
   - Rebel trade activity (catches VISIBILITY_GAP change)
