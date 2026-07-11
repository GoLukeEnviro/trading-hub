# Bot Registry — Trading Hub

> **Regel:** `bot_a`, `bot_b`, `bot_c`, `bot_d` sind verboten.
> Immer den logischen Namen aus dieser Registry verwenden.

## Aktive Bots (Legacy — `docker-compose.yml`)

| Logischer Name | Container | Compose-Service | Strategie |
|---|---|---|---|
| `trading.freqforge` | `trading-freqtrade-freqforge-1` | `freqtrade-freqforge` | `FreqForge_Override` |
| `trading.freqforge_canary` | `trading-freqtrade-freqforge-canary-1` | `freqtrade-freqforge-canary` | `FreqForge_Override` |
| `trading.regime_hybrid` | `trading-freqtrade-regime-hybrid-1` | `freqtrade-regime-hybrid` | `RegimeSwitchingHybrid_v7_v04_Integration` |
| `trading.rebel` | `trading-freqai-rebel-1` | `freqai-rebel` | `RebelLiquidation` |
| `trading.freqtrade_webserver` | `trading-freqtrade-webserver-1` | `freqtrade-webserver` | *(zentrale API/UI/Telegram-Owner)* |

## Greenfield Bots (R7A — `docker-compose.hermestrader-dryrun.yml`)

> Kanonischer Stack ab Issue #504. Dry-run only (Live-Gate #423).

| Bot | Service (greenfield) | Profile | Compose-Datei |
|---|---|---|---|
| `freqforge` | `freqtrade-freqforge` | default | `docker-compose.hermestrader-dryrun.yml` |
| `canary` | `freqtrade-freqforge-canary` | default | `docker-compose.hermestrader-dryrun.yml` |
| `regime-hybrid` | `freqtrade-regime-hybrid` | default | `docker-compose.hermestrader-dryrun.yml` |
| `rebel` | `freqai-rebel` | `rebel` (opt-in) | `docker-compose.hermestrader-dryrun.yml` |
| `rainbow` | `rainbow` | default | `services/rainbow/rainbow.include.yml` |

### Profil-Erklärung

- **default**: Startet mit `docker compose up` ohne `--profile`-Flag
- **rebel (opt-in)**: Startet nur mit `docker compose --profile rebel up` — NOT_REPRODUCIBLE bis PR-3

## YAML-Format (für Scripts/Jobs)

```yaml
trading.freqforge:
  container: trading-freqtrade-freqforge-1
  compose_service: freqtrade-freqforge
  strategy: FreqForge_Override

trading.freqforge_canary:
  container: trading-freqtrade-freqforge-canary-1
  compose_service: freqtrade-freqforge-canary
  strategy: FreqForge_Override

trading.regime_hybrid:
  container: trading-freqtrade-regime-hybrid-1
  compose_service: freqtrade-regime-hybrid
  strategy: RegimeSwitchingHybrid_v7_v04_Integration

trading.rebel:
  container: trading-freqai-rebel-1
  compose_service: freqai-rebel
  strategy: RebelLiquidation

trading.freqtrade_webserver:
  container: trading-freqtrade-webserver-1
  compose_service: freqtrade-webserver
  role: central_api_ui_telegram_owner

# R7A Greenfield
trading.rainbow:
  compose_service: rainbow
  role: ta_collector_internal_only
  profile: default
  compose_file: docker-compose.hermestrader-dryrun.yml
```

## Gegencheck auf VPS

```bash
# Laufende Bots verifizieren
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -Ei "freq|trade|rebel|rainbow"

# Bot-Verzeichnisse
ls -la /home/hermes/projects/trading/freqtrade/bots/
```

> **Konflikt-Regel:** Wenn Verzeichnisname und Docker/Compose-Name widersprechen,
> gewinnt **Docker/Compose** — das ist die laufende Realität.

## Mapping: Alt → Neu (Migration)

| Alt (verboten) | Neu (korrekt) |
|---|---|
| `bot_a` | `trading.freqforge` |
| `bot_b` | `trading.freqforge_canary` |
| `bot_c` | `trading.regime_hybrid` |
| `bot_d` | `trading.rebel` |

---
*Erstellt: 2026-06-10 — Quelle: Docker Compose + Container Audit*  
*Aktualisiert: 2026-07-11 — R7A Greenfield-Sektion + Profile-Spalte (Issue #504)*
