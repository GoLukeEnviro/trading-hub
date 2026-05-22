# Rebel Stage-1 jq Patch Test — 2026-05-20

## Scope
Implemented and tested the Rebel-specific Stage-1 function `apply_approved_rebel_patch()` in `freqtrade/bots/regime-hybrid/config/research/automation/self_optimizer.py`.

## Safety Rules Kept
- Only allowed paths are processed:
  - `freqai.model_training_parameters.scale_pos_weight`
  - `freqai.feature_parameters.DI_threshold`
  - `freqai.expiration_hours`
  - `stake_amount`
- `requires_new_identifier=true` returns `requires_new_identifier_and_retrain` and does not patch.
- No strategy, feature engineering, or label code is edited.
- Sequence: validation -> backup -> jq patch -> API reload -> verification -> event log.
- Rollback restores backup and reloads on failure after backup.

## Implementation Notes
- Replaced fragile dynamic `python3 -c` patching with jq commands executed inside `freqai-rebel`.
- Added API readiness wait after `reload_config`; Rebel temporarily drops API connectivity during reload.
- `/api/v1/show_config` is called as a mandatory post-reload health/config endpoint, but the Freqtrade 2026.3 response omits nested `freqai` settings. For `freqai.*` keys, verification therefore falls back to `/freqtrade/user_data/config.json` after successful reload and reachable `/show_config`.
- `jq` was installed in the running Rebel container because it was absent from the image.

## Test Result
Test proposal: set `freqai.feature_parameters.DI_threshold` to `1.1`.

Result:
- status: `success`
- verification.passed: `true`
- rollback_performed: `false`
- event: `/home/hermes/projects/trading/events/rebel/rebel-test-di-threshold-1.1_patch_success_20260520T195406Z.json`
- current container config DI_threshold: `1.1`

## Follow-up
DI_threshold is currently left at 1.1 after the successful test. Decide whether to keep it for observation or restore the previous 1.5 using another approved Stage-1 proposal.
