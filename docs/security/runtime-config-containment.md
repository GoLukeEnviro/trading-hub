# Runtime Config Containment and Credential Rotation Plan

Date: 2026-06-15
Issues: #243, #253
Status: repository containment implemented; external credential rotation remains human-owned.

## What changed

The GAP audit found tracked runtime configuration/report files with credential-like fields. This PR contains the repository-side containment step:

- remove tracked runtime configs from source control
- add sanitized `.example.json` templates with placeholders only
- extend `.gitignore` so local runtime configs/reports stay untracked
- add a redacted secret scanner for tracked files
- add contract tests proving real config paths are ignored and examples remain dry-run/local-only

## Removed from tracking

These files must remain local runtime state only and are now ignored:

- `freqforge/user_data/config.json`
- `freqforge-canary/user_data/config.json`
- `freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v1.json`
- `freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v2.json`
- `freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v3.json`
- `freqtrade/bots/regime-hybrid/user_data/momentum_v2_backtest.json`
- `orchestrator/reports/canonical_trading_status_latest.json`
- `orchestrator/reports/phase-33-observation-log.jsonl`
- `var/kill_switch.json`

## Sanitized examples added

- `freqforge/user_data/config.example.json`
- `freqforge-canary/user_data/config.example.json`
- `freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v1.example.json`
- `freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v2.example.json`
- `freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v3.example.json`
- `freqtrade/bots/regime-hybrid/user_data/momentum_v2_backtest.example.json`

The examples force `dry_run: true` where the source config has a `dry_run` field, bind API servers to `127.0.0.1`, disable OpenAPI on examples, and replace secret-bearing fields with `CHANGE_ME_LOCAL_ONLY_*` placeholders.

## Required human action outside Git

Repository containment does **not** rotate credentials. A human/operator must rotate any credential that may have existed in the tracked files before treating this incident as fully closed:

1. Rotate Freqtrade WebUI/API passwords and JWT secrets for affected bots.
2. Rotate any exchange API key/secret that appeared in tracked research/backtest configs, even if the bot remains dry-run.
3. Rotate Telegram tokens if any tracked research config contained a non-placeholder token.
4. Recreate local runtime config files from the sanitized examples and secret manager/local vault values.
5. Confirm all bot configs still have `dry_run: true` before any runtime restart or recreate.

Do not print old or new credentials in logs, PR comments, issues, or chat.

## History cleanup decision

No Git history rewrite is performed in this PR. History rewriting would require explicit human approval because it rewrites repository history and can disrupt every clone and open branch.

Current risk decision for this PR:

- current tree containment: implemented
- current-tree secret scan: required and documented in CI
- historical exposure: escalated to human for rotate-vs-rewrite decision
- live trading: unchanged; `dry_run=false` is not introduced

If the human later approves history cleanup, use a dedicated incident runbook/PR and include fresh-clone rollback instructions. Until then, assume any credential that was ever tracked must be rotated.

## Local validation commands

```bash
python3 scripts/secret_scan.py --tracked
python3 -m pytest tests/test_secret_scan_contracts.py tests/test_runtime_config_containment.py -q
python3 -m pytest tests/test_kill_switch.py tests/test_kill_switch_dry_run_integration.py -q
python3 -m compileall bridge primo shadowlock intelligence orchestrator tests scripts
```

## Rollback

Repository rollback is a normal Git revert of the containment PR. Runtime rollback must not restore old credentials. If an example template is insufficient, copy it locally to the ignored runtime path and fill values from the operator's secret store, keeping `dry_run: true`.
