# Credential History Decision

**Date:** 2026-06-15
**Author:** Hermes Orchestrator (repository audit)
**Issue:** #243
**Status:** Decision documented — no history rewrite at this time.

## Affected path classes

The following path classes have been identified as potential credential exposure vectors in Git history:

| Class | Path pattern | Current-tree status |
|-------|-------------|-------------------|
| FreqForge main config | `freqforge/config/config*.json` | All ignored, only `.example.json` tracked |
| FreqForge user_data config | `freqforge/user_data/config*.json` | All ignored, only `.example.json` tracked |
| FreqForge baseline configs | `freqforge/baseline_v1/*/config*.json` | Ignored via `freqforge/baseline_v1/*/config*.json` |
| FreqForge-Canary config | `freqforge-canary/config/config*.json` | Ignored |
| FreqForge-Canary user_data | `freqforge-canary/user_data/config*.json` | All ignored, only `.example.json` tracked |
| Regime-Hybrid main config | `freqtrade/bots/regime-hybrid/config/config*.json` | Ignored |
| Regime-Hybrid research | `freqtrade/bots/regime-hybrid/config/research/config*.json` | Ignored, only `.example.json` tracked |
| Regime-Hybrid user_data | `freqtrade/bots/regime-hybrid/user_data/config*.json` | Ignored |
| RSI bot config | `freqtrade/bots/rsi/config/config*.json` | Ignored |
| Momentum bot config | `freqtrade/bots/momentum/config/config*.json` | Ignored |
| MVS bot config | `freqtrade/bots/mvs/config/config*.json` | Ignored |
| Backtest configs | `freqtrade/bots/*/config/config_backtest*.json` | Ignored |
| Episode configs | `**/user_data/config_episode_*.json` | Ignored |
| .env files | `.env`, `.env.*` | Ignored |

## Current-tree status

- **All real credentials removed from tracking.** Only sanitized `.example.json` templates with `CHANGE_ME_LOCAL_ONLY_*` placeholders or env-var indirection (`${VAR}`) are tracked.
- **Gitignore coverage is comprehensive.** The `.gitignore` file contains 294 lines with specific rules for each config path class plus negation rules for example files.
- **Secret scanner passes.** `python3 scripts/secret_scan.py --tracked` returns 0 findings against the current tree.
- **CI enforces.** `main-gate` workflow runs `secret_scan --tracked` on every commit.
- **Exposed credential types historically possible:**
  - Freqtrade WebUI passwords (`api_server.password`)
  - JWT signing secrets (`jwt_secret_key`)
  - Exchange API keys (`exchange.key`, `exchange.secret`) — most were env-var references or placeholders
  - Telegram bot tokens

## Whether real credentials were previously tracked

**Determination: POSSIBLY, but cannot be fully verified without history inspection.**

The `.gitignore` rules and containment work were applied incrementally over several PRs (#253, #267, #268). Before those PRs, the following paths were tracked in the tree at various points:

- `freqforge/user_data/config.json`
- `freqforge-canary/user_data/config.json`
- `freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v1.json` (previously tracked)
- `freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v2.json` (previously tracked)
- `freqtrade/bots/regime-hybrid/config/research/config_regime_hybrid_sideaware_v3.json` (previously tracked)
- `orchestrator/reports/canonical_trading_status_latest.json` (previously tracked)
- `orchestrator/reports/phase-33-observation-log.jsonl` (previously tracked)
- `var/kill_switch.json` (previously tracked)

These files contained credential-like fields such as `jwt_secret_key`, `password`, and in some cases partial API key values. The `password` fields used patterns like `freqfo...only` or `***` (likely truncated/redacted), and `exchange.key`/`exchange.secret` used `${ENV_VAR}` indirection.

Full disclosure: **some `jwt_secret_key` values in previously tracked configs appear to be non-placeholder strings.** This means Git history may contain real JWT signing secrets, even if they were only used in dry-run mode.

## Whether rotation is required

**Decision: ROTATION REQUIRED for dry-run credentials that were ever in tracked files.**

Even though all bots run in `dry_run=true` mode:
1. **JWT secrets** in history could allow forging API tokens if the bot's REST API is exposed.
2. **Freqtrade WebUI passwords** could be reused or derived from the historical values.
3. **Exchange API keys** — these used `${ENV_VAR}` indirection throughout, so history exposure is unlikely but cannot be ruled out without manual per-commit inspection of every tracked config.

**Minimum rotation scope:**
- Freqtrade WebUI passwords for all active bots
- JWT signing secrets for all active bots
- Any exchange API keys that were ever inlined (not env-variable-referenced) in a tracked file
- Telegram bot tokens, if any were ever non-placeholder in a tracked file

## Whether history rewrite is recommended or deferred

**Decision: REWRITE DEFERRED.**

Criteria that would justify a history rewrite:
1. **Confirmed real exchange API key/secret in history** — requires manual per-commit inspection or automated `git filter-repo` analysis.
2. **Confirmed Telegram bot token in history** — same requirement.
3. **Explicit human approval** for the rewrite operation.

Rationale for deferring:
- No confirmed live-money credential exposure (all configs are dry-run).
- A force-push history rewrite disrupts all open branches, PRs, and cloned repos.
- The current-tree containment is verified clean, and secret scanning is in CI.
- **Risk is already mitigated at the credential rotation level.** Rotating credentials makes historical exposure irrelevant.

## Rollback/re-clone implications

If history rewrite is later approved:

1. All contributors must re-clone from the rewritten remote.
2. All open PRs must be recreated from new branches.
3. The coordinator must coordinate a force-push window with no active PRs.
4. Fresh-clone rollback instructions:
   ```bash
   git clone git@github.com:GoLukeEnviro/trading-hub.git trading-hub-clean
   cd trading-hub-clean
   # Verify HEAD matches intended root-of-rewrite
   git log --oneline -1
   # Restore local runtime configs from backup/vault
   ```

5. Pre-rewrite archive should be kept as a tag or bundle for audit purposes:
   ```bash
   git bundle create pre-rewrite-243.bundle --all
   ```

## Summary

| Question | Answer |
|----------|--------|
| Current tree clean? | ✅ Yes |
| History rewrite performed? | ❌ No (deferred) |
| Rotation required? | ✅ Yes |
| Risk accepted? | ✅ Yes, with rotation mitigation |
| Decision owner | GoLukeEnviro |
