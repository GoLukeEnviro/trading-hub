# Canonical Status Truth Layer Repair — Operator Report

## Executive Verdict
- Runtime: GREEN.
- Reporting truth layer: partially fixed and now canonicalized, but overall verdict remains WARNING because stale drawdown state and legacy non-canonical reports still exist.
- Rebel is explicitly classified as VISIBILITY_GAP, not a live-trading failure.

## Health Scores
- runtime_health_score: 92
- reporting_health_score: 68
- data_quality_score: 79
- auditability_score: 82
- overall_operational_score: 81

## Canonical Sources
Safe for decisions:
- /home/hermes/projects/trading/ai-hedge-fund-crypto/output/hermes_signal.json
- /home/hermes/projects/trading/freqtrade/shared/primo_signal_state.json
- /home/hermes/projects/trading/orchestrator/state/riskguard/riskguard_state.json
- /home/hermes/projects/trading/orchestrator/state/riskguard/riskguard_health.json
- /home/hermes/projects/trading/orchestrator/logs/shadow_decisions.jsonl
- active bot configs/state files exposed via fleet-healthcheck output (dry-run only)

Historical / stale / sandbox-only:
- /opt/data/profiles/orchestrator/state/drawdown_state.json (STALE)
- /home/hermes/projects/trading/docs/state/autopilot/latest.md (HISTORICAL)
- Bitget MCP paper book outputs (SANDBOX_ONLY)
- /home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.json and .md (diagnostic, non-canonical)
- /home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.json and .md (legacy validator, non-canonical)

## Files Changed
Canonical layer files created/updated in this pass:
- /home/hermes/projects/trading/orchestrator/reports/canonical_trading_status_latest.json — new machine-readable canonical status.
- /home/hermes/projects/trading/docs/state/canonical-trading-status.md — new human-readable canonical status.
- /home/hermes/projects/trading/docs/state/current-operational-state.md — regenerated from live sources.
- /home/hermes/projects/trading/docs/state/autopilot/latest.md — converted to historical/non-canonical marker.
- /home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.json — refreshed with explicit Rebel classification.
- /home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.md — refreshed report output.
- /home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.json — refreshed legacy validation output.
- /home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.md — refreshed legacy validation output.
- /home/hermes/projects/trading/orchestrator/scripts/fleet_healthcheck.py — updated to classify Rebel as VISIBILITY_GAP and surface bot classification.
- /home/hermes/projects/trading/orchestrator/scripts/multicycle_validator.py — updated to separate active vs decommissioned state files.
- /home/hermes/projects/trading/orchestrator/scripts/quality_hub_monitor.py — updated Rebel classification and reporting wording.

Worktree carry-over present before this repair, not modified by me in this pass:
- /home/hermes/projects/trading/dashboard.py
- /home/hermes/projects/trading/freqforge/user_data/strategies/FreqForge_Override.py
- /home/hermes/projects/trading/orchestrator/scripts/observation_runner.py

## Validation Evidence
- JSON parse checks succeeded:
  - python3 -m json.tool /home/hermes/projects/trading/orchestrator/reports/canonical_trading_status_latest.json
  - python3 -m json.tool /home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.json
  - python3 -m json.tool /home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.json
- Syntax checks succeeded:
  - python3 -m py_compile /home/hermes/projects/trading/dashboard.py /home/hermes/projects/trading/freqforge/user_data/strategies/FreqForge_Override.py /home/hermes/projects/trading/orchestrator/scripts/fleet_healthcheck.py /home/hermes/projects/trading/orchestrator/scripts/multicycle_validator.py /home/hermes/projects/trading/orchestrator/scripts/observation_runner.py /home/hermes/projects/trading/orchestrator/scripts/quality_hub_monitor.py
- No whitespace issues remain:
  - git diff --check returned clean
- Runtime containers remained up:
  - docker ps showed freqtrade-freqforge, freqtrade-freqforge-canary, freqtrade-regime-hybrid, freqai-rebel, ai-hedge-fund-crypto, freqtrade-webserver, trading-dashboard, trading-guardian, and supporting services still running.
- No dry_run=false changes found in the generated canonical docs/reports.
- No API keys or secrets were exposed in the generated canonical docs/reports; only placeholder values such as absent/no_host_mount appear.

## Remaining Risks
- /opt/data/profiles/orchestrator/state/drawdown_state.json is stale and not verified current.
- /home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.* remains RED because it is tied to legacy wrapper assumptions and should not be used as canonical live truth.
- Rebel remains a VISIBILITY_GAP: the bot is alive and dry_run=true, but its full audit surface is incomplete.
- Bitget MCP paper book values are synthetic and must remain SANDBOX_ONLY.

## Next Safe Step
Refresh the drawdown_state writer with a verified current snapshot, then re-run the canonical report generation once the live risk view is refreshed.
