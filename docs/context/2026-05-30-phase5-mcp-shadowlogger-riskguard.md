# Phase 5: MCP Fix, ShadowLogger, RiskGuard Service — 2026-05-30

## 1. MCP ccxt-Fehler behoben

**Problem:** `trading_pipeline.py` importierte `ccxt` als Fallback für den
MCP Execution Layer. ccxt war nicht im system Python installiert (PEP 668
Debian-Restriktion), aber stand im Hermes venv (`/opt/hermes/.venv/`).

**Fix:**
- Shebang von `#!/usr/bin/env python3` auf `#!/opt/hermes/.venv/bin/python3` geändert
- Script executable gemacht (`chmod +x`)
- Jetzt läuft der MCP Execution Layer sauber durch

**Effekt:** Pipeline executed jetzt BTC/ETH/SOL Paper-Orders via MCP:
- BTC/USDT SHORT 0.027 → paper closed (dry_run=true)
- ETH/USDT SHORT 0.986 → paper closed (dry_run=true)
- SOL/USDT SHORT 24.1 → paper closed (dry_run=true)

## 2. ShadowLogger verifiziert

**Status:** Bereits aktiv und lauffähig. 170 Einträge, 276KB, append-only.
Letzter Eintrag von 20:27 UTC. Schema v1.0, vollständige Entscheidungen
mit Signal-Age, RiskGuard-Summary, Pair-Decisions und State-Writes.

Kein Ausbau nötig — ShadowLogger ist produktiv und dokumentiert jeden
Pipeline-Cycle vollständig.

## 3. RiskGuard als separaten Service deployt

**Neue Datei:** `riskguard_service.py` in `/opt/data/profiles/orchestrator/scripts/`
**Cron:** `riskguard-service` (410dcbe0df50, */30min, no_agent)
**State-Dir:** `orchestrator/state/riskguard/`

**Service-Layer:**
- LAYER 1: HEALTH — `riskguard_health.json` mit Signal-Freshness, State/Audit-Status
- LAYER 2: EVALUATE — RG-1 bis RG-5 Logik (pure function)
- LAYER 3: AUDIT — `riskguard_audit.jsonl` (append-only)
- LAYER 4: STATE — `riskguard_state.json`

**Warum separat:**
- Kann unabhängig von der Trading-Pipeline laufen
- Eigenes Health-Check-File → Monitoring-fähig
- Append-only Audit → forensisch nutzbar
- Redundanz: Signal wird unabhängig evaluiert
