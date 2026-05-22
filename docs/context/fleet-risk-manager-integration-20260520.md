# FleetRiskManager Integration — 2026-05-20

Status: implemented in dry-run only.

## Was wurde ergänzt?
- Shared module: `/home/hermes/projects/trading/freqtrade/shared/fleet_risk_manager.py`
- Equity updater: `/home/hermes/projects/trading/freqtrade/shared/update_fleet_equity.py`
- Correlation refresh: `/home/hermes/projects/trading/freqtrade/shared/calculate_correlation_matrix.py`
- Strategy integration:
  - `/home/hermes/projects/trading/freqforge/user_data/strategies/FreqForge_Override.py`
  - `/home/hermes/projects/trading/freqforge-canary/user_data/strategies/FreqForge_Override.py`
  - `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/strategies/RegimeSwitchingHybrid_v7_v04_Integration.py`

## Verhalten
- Entry checks now combine:
  - fleet drawdown ladder
  - cluster win/loss history
  - correlation throttle from shared matrix
  - existing Primo/FleetGuard logic
- Trade/open-close state is synced into a shared JSON snapshot.
- No live orders or live-exchange changes were introduced.

## Shared state / artifacts
- Fleet state: `/home/hermes/projects/trading/freqtrade/shared/fleet_risk_state.json`
- Correlation matrix: `/home/hermes/projects/trading/freqtrade/shared/fleet_correlation_matrix.json`
- Shared dir permissions were adjusted to allow container user `ftuser` (uid 1000) to update the shared state via the mounted volume.

## Periodic execution
- Hermes cron job created:
  - `FleetRisk equity updater` every 5m
  - `Fleet correlation refresh` every 72h
- Wrapper scripts are stored under `/opt/data/profiles/orchestrator/scripts/`.

## Validation
- Python syntax checks passed for all touched Python files.
- Equity updater and correlation refresh were smoke-tested successfully.
