# Persistent Bot Mapping for Self-Improvement System

**Date:** 2026-06-07  
**Status:** Authoritative, persistent assignment (overrides earlier ad-hoc mappings)

This document defines the fixed 1:1 assignment of the four self-improvement "bots" (A–D) to the real Freqtrade fleet instances. All run scripts, configs, state directories and future logic **must** use this mapping.

## Mapping

| Self-Imp Bot | Container Name                     | Service / Compose Profile | Strategy                              | Notes |
|--------------|------------------------------------|-----------------------------|---------------------------------------|-------|
| **bot_a**    | `trading-freqtrade-freqforge-1`    | freqtrade-freqforge         | `FreqForge_Override`                  | Core / main |
| **bot_b**    | `trading-freqtrade-freqforge-canary-1` | freqtrade-freqforge-canary | `FreqForge_Override`                  | Canary variant of FreqForge |
| **bot_c**    | `trading-freqtrade-regime-hybrid-1` | freqtrade-regime-hybrid    | `RegimeSwitchingHybrid_v7_v04_Integration` | Regime detection |
| **bot_d**    | `trading-freqai-rebel-1`           | freqai-rebel                | `RebelLiquidation` (+ XGBoost)        | FreqAI / ML model |

## Corresponding State & Config Locations (for reference)

- `self_improvement/bot_a/` + `var/trading-self-improvement/bot_a/` → freqforge
- `self_improvement/bot_b/` + `var/trading-self-improvement/bot_b/` → freqforge-canary
- `self_improvement/bot_c/` + `var/trading-self-improvement/bot_c/` → regime-hybrid
- `self_improvement/bot_d/` + `var/trading-self-improvement/bot_d/` → freqai-rebel

The `bot_*/bot_config.json` files contain the concrete `container_name`, `strategy_name`, `db_path` and `host_user_data_path` that implement this mapping at runtime.

## How to use

- When working on self-improvement logic, always refer to this document for which real bot a "bot_X" controls.
- When updating thresholds, data paths or running manual commands, use the container/strategy from this table.
- If the fleet changes (new container or strategy rename), update this file **and** the four `bot_*/bot_config.json` files.

## History

- 2026-06-07: Established as the single source of truth per explicit persistent assignment. Previous hybrid-inventory and ad-hoc configs from early June are superseded for self-improvement purposes.
