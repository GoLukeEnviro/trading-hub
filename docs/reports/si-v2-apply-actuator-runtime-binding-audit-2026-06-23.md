# SI-v2 Apply Actuator Runtime Binding Audit

**Date:** 2026-06-23
**Issue:** #332
**Mode:** L0 Read-Only Audit
**Status:** ✅ VERIFIED

## Executive Summary

A Docker-inspect-verified audit of all 4 SI-v2 bot runtime bindings.
The audit confirms that overlay files must be placed in the actual Docker
bind-mount paths, not the repo-artifact paths used by the previous apply.

## Fleet Binding Table

All bindings verified via `docker inspect` and read-only `docker exec` checks.

| Bot ID | Container | Host user_data | Container user_data | Config | Confidence |
|--------|-----------|----------------|---------------------|--------|------------|
| `freqtrade-freqforge` | `trading-freqtrade-freqforge-1` | `/home/hermes/projects/trading/freqforge/user_data` | `/freqtrade/user_data` | `config.json` | VERIFIED |
| `freqtrade-freqforge-canary` | `trading-freqtrade-freqforge-canary-1` | `/home/hermes/projects/trading/freqforge-canary/user_data` | `/freqtrade/user_data` | `config.json` | VERIFIED |
| `freqtrade-regime-hybrid` | `trading-freqtrade-regime-hybrid-1` | `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data` | `/freqtrade/user_data` | `config.json` | VERIFIED |
| `freqai-rebel` | `trading-freqai-rebel-1` | `/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data` | `/freqtrade/user_data` | `config.json` | VERIFIED |

## Critical Finding: Path Mismatch for FreqForge

| Path | Exists | Is Mounted | Bot Can See |
|------|--------|-----------|-------------|
| `freqforge/user_data/` | ✅ | ✅ (Docker bind mount) | ✅ |
| `freqtrade/bots/freqforge/user_data/` | ✅ | ❌ | ❌ |

The previous overlay `overlay_65502d13.json` was placed in the REPO-INERT path
`freqtrade/bots/freqforge/user_data/`, which is NOT the Docker mount path for
the freqforge container. The overlay was never visible to the bot.

## Config Loading Mechanism

All 4 bots load config via `freqtrade trade --config /freqtrade/user_data/config.json`.
No bot reads `overlay_*.json` files. Freqtrade 2026.3 supports native multi-config
loading (`--config config.json --config overlay_NNN.json`).

## Evidence

- `container-trading-freqtrade-freqforge-1-inspect.txt`: Docker mount verification
- `container-trading-freqtrade-freqforge-1-readonly-runtime.txt`: Container file check
- `container-trading-freqtrade-freqforge-1-freqtrade-help.txt`: Freqtrade --help output confirming multi-config support

## Recommendation

1. All overlays must be placed in the verified `host_user_data_path` per binding
2. Use Freqtrade's `--config` stacking for safe overlay loading
3. Never write to `freqtrade/bots/freqforge/user_data/` — this path is not mounted
4. Machine proof required before mutation counter increment and measurement
