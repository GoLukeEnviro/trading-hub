# Freqtrade Config Credential Management

> **Policy:** Real credentials must never be committed to version control.
> Only example/template configs with `CHANGE_ME_*` placeholders are tracked.

## File layout

| File type | Pattern | Tracked? | Purpose |
|-----------|---------|----------|---------|
| Example config | `*.example.json` | ✅ Yes | Template with safe placeholders (`CHANGE_ME_LOCAL_ONLY_*`) |
| Real runtime config | `config.json` / `config_*.json` | ❌ No (`.gitignore`) | Contains real JWT secrets, API passwords, exchange keys |
| Research config | `config_*.json` (in `research/`) | ❌ No (`.gitignore`) | Same as runtime, for research strategies |
| Backtest results | `*.sqlite` | ❌ No | Runtime data |

## Four-bot fleet example configs

| Bot | Example config path |
|-----|-------------------|
| FreqForge | `freqforge/user_data/config.example.json` |
| FreqForge-Canary | `freqforge-canary/user_data/config.example.json` |
| Regime-Hybrid (v1/v2/v3) | `freqtrade/bots/regime-hybrid/config/research/config_*.example.json` |
| FreqAI-Rebel | `freqtrade/bots/freqai-rebel/user_data/config.example.json` |

## Safe placeholder values

All tracked configs use these placeholder values:

| Field | Placeholder |
|-------|------------|
| `api_server.jwt_secret_key` | `CHANGE_ME_LOCAL_ONLY_SECRET` |
| `api_server.password` | `CHANGE_ME_LOCAL_ONLY_PASSWORD` |
| `exchange.key` | `CHANGE_ME_LOCAL_ONLY_KEY` |
| `exchange.secret` | `CHANGE_ME_LOCAL_ONLY_SECRET` |
| `telegram.token` | `CHANGE_ME_LOCAL_ONLY_TOKEN` |

## Setting up local runtime configs

1. Copy the example config:
   ```bash
   cp freqforge/user_data/config.example.json freqforge/user_data/config.json
   ```

2. Replace all `CHANGE_ME_*` values with real credentials.

3. Verify the config is gitignored:
   ```bash
   git check-ignore freqforge/user_data/config.json
   # Should return the path (exit code 0)
   ```

4. Verify no real secrets are committed:
   ```bash
   python scripts/secret_scan.py --root . freqforge/user_data/config.json
   # Should report findings (config is gitignored, but scan catches accidental commits)
   ```

## drawdown_guard.py credential resolution

As of PR #317, `drawdown_guard.py` resolves API passwords via environment variables:

| Env var | Bot |
|---------|-----|
| `FREQTRADE_FREQFORGE_PASS` | FreqForge |
| `FREQTRADE_CANARY_PASS` | FreqForge-Canary |
| `FREQTRADE_REGIME_HYBRID_PASS` | Regime-Hybrid |
| `FREQTRADE_REBEL_PASS` | FreqAI-Rebel |

Resolution order: env var → host config file → container config → empty (safe failure).

## Validation

Run `tests/test_config_credential_safety.py` to verify:
- All example configs contain only safe placeholders
- All four bots have example configs
- `.gitignore` properly excludes real configs
- dry_run=true is preserved in all examples
