# Fleet Health Report — 2026-07-03

**Status:** 🟡 WARNINGS — Canary ohne Port-Exposure, API nur intern erreichbar

## Container Status

| Name | Status | Ports | Health |
|------|--------|-------|--------|
| freqtrade-freqforge | Up 4 days | :8086→8080 | healthy |
| freqtrade-freqforge-canary | Up 4 days | **kein Port** | (kein Healthcheck) |
| freqtrade-regime-hybrid | Up 4 days | :8085→8080 | (kein Healthcheck) |
| freqai-rebel | Up 4 days | :8087→8080 | (kein Healthcheck) |
| freqtrade-webserver | Up 3 weeks | :8180→8080 | (kein Healthcheck) |
| ai-hedge-fund | Up | — | healthy |
| shadowlock | Up | — | **unhealthy** |
| guardian | Up | — | (kein Healthcheck) |
| dashboard | Up | — | (kein Healthcheck) |

## System

- **Disk:** 201G / 301G = **70%** ⚠️
- **Memory:** 9.5G / 31.3G = 40%
- **Swap:** 601M / 4G = 15%

## API Reachability

| Bot | Port | Extern | Intern (docker exec) |
|-----|------|--------|---------------------|
| freqforge | 8086 | ❌ Leere Response | ✅ pong |
| freqforge-canary | — | ❌ Kein Port | ✅ pong |
| regime-hybrid | 8085 | ❌ Leere Response | ✅ pong |
| freqai-rebel | 8087 | ❌ Leere Response | ✅ pong |

**Problem:** API antwortet auf `curl localhost:<port>` mit leerer Response, aber `docker exec` → `localhost:8080` funktioniert. Die Port-Mappings sind aktiv, aber die API scheint nur auf IPv6 oder internem Docker-Netz zu lauschen.

## Findings

- 🟢 Alle 4 Bots laufen und antworten auf Ping (intern)
- 🟢 Keine Restarts, alle stabil seit 4+ Tagen
- 🟢 Memory und CPU im Rahmen (Canary 64%, Regime-Hybrid 62%, Rebel 40%)
- 🟡 **Canary hat keinen exposed Port** — nur per `docker exec` erreichbar
- 🟡 **API extern antwortet leer** — Port-Mapping aktiv, aber curl bekommt leere Response
- 🟡 **Shadowlock unhealthy** — sollte geprüft werden
- 🟡 **Disk bei 70%** — sollte beobachtet werden
- 🔴 **Keine Log-Rotation sichtbar** — Docker-Standard-JSON-Logs könnten unbegrenzt wachsen
