# FreqForge-Canary Deployment Runbook

> **Status:** Bereit zur Freigabe (Phase 5 wartet auf Approval)
> **Datum:** 2026-05-15
> **Zweck:** RSI-Slot ersetzen durch FreqForge-abgeleiteten Canary-Bot
> **Regel:** Kein Deployment ohne explizite Freigabe durch Luke

---

## RSIP Iteration Log

### Iteration 1 — Grundstruktur

Erste Version enthielt:
- Preflight-Checkliste
- Deployment-Schritte (mkdir, config, compose, stop RSI, start canary)
- Rollback-Plan

**Schwächen identifiziert:**
1. Keine Approval-Gates zwischen Phasen — Deploy koennte blind durchlaufen
2. Keine Fehler-Szenarien (Was wenn compose failt? Was wenn Pair nicht gefunden?)
3. Keine Safety-Assertions zwischen Schritten (FreqForge-check fehlt)

### Iteration 2 — Klarheit und Logik

Verbessert um:
- Approval-Gates nach Phase 4 (Validation) und vor Phase 6 (Deployment)
- Fehler-Szenarien mit Recovery-Commands
- Safety-Assertions: FreqForge-MD5-Check nach jedem Schritt
- Timing-Constraints: RSI stop erst NACH canary config validiert

**Schwächen identifiziert:**
1. Commands nicht copy-paste-ready (Variablen nicht aufgeloest)
2. Fehlende Docker-Compose Service Definition als vollstaendiges YAML
3. Keine Post-Deploy-Monitoring-Commands

### Iteration 3 — Feinschliff

Finalisiert mit:
- Alle Commands mit aufgeloesten Pfaden (copy-paste-ready)
- Vollstaendige docker-compose Service Definition
- Post-Deploy Monitoring mit erwartetem Output
- Safety-Assertions als explizite CHECK-Points

---

## Executive Summary

Der quarantaenierte RSI-Bot (0/3 WR, -2.55 USDT) wird durch einen kontrollierten FreqForge-abgeleiteten Canary ersetzt. Der Canary nutzt die gleiche Strategy-Logik (FreqForge_Override), aber mit:

- **Anderem Pair-Set:** LINK, DOT, ATOM, XRP, UNI (0 Overlap mit FreqForge)
- **Kleinerem Stake:** 50 USDT statt 100 USDT
- **Eigener DB:** tradesv3.freqforge_canary.dryrun.sqlite
- **Eigenem Container:** freqtrade-freqforge-canary auf Port 8088

FreqForge bleibt unangetastet. RSI wird gestoppt, nicht geloescht.

---

## Inventory

### FreqForge (Quelle — NICHT MODIFIZIEREN)

| Property        | Value                                                       |
|-----------------|-------------------------------------------------------------|
| Container       | freqtrade-freqforge                                         |
| Image           | freqtradeorg/freqtrade:stable                               |
| Port            | 8086                                                        |
| Mode            | spot (can_short=False)                                      |
| Config          | /home/hermes/projects/trading/freqforge/config/config_freqforge_dryrun.json |
| Strategy        | /home/hermes/projects/trading/freqforge/user_data/strategies/FreqForge_Override.py |
| DB              | tradesv3.freqforge.dryrun.sqlite                            |
| Whitelist       | BTC/USDT, ETH/USDT, SOL/USDT, AVAX/USDT, NEAR/USDT, ARB/USDT, OP/USDT |
| Stake           | 100 USDT, max_open_trades: 5                                |
| Open Trades     | 3 (SOL Long, AVAX Long, BTC Long)                           |
| Config MD5      | d4ba3543ff477deae56a2462587f0426                            |
| Strategy MD5    | 2daa67c81b116d08026623793fe3bd0d                            |

### RSI (Ziel-Slot — WIRD GESTOPPT)

| Property        | Value                                                       |
|-----------------|-------------------------------------------------------------|
| Container       | freqtrade-rsi                                               |
| Status          | UP 3d, QUARANTINED                                          |
| Port            | 8081                                                        |
| Trades          | 3 closed, 0/3 Won, -2.548 USDT                             |
| Config          | /home/hermes/projects/trading/freqtrade/bots/rsi/config/config.json |
| DB              | /freqtrade/tradesv3.dryrun.sqlite (container root)          |

### Canary (Neu — WIRD ERSTELLT)

| Property        | Value                                                       |
|-----------------|-------------------------------------------------------------|
| Container       | freqtrade-freqforge-canary                                  |
| Image           | freqtradeorg/freqtrade:stable                               |
| Port            | 8088 (verified free)                                        |
| Mode            | spot (same as FreqForge)                                    |
| Config          | /home/hermes/projects/trading/freqtrade/bots/freqforge-canary/config/config.json |
| Strategy        | /home/hermes/projects/trading/freqtrade/bots/freqforge-canary/user_data/strategies/FreqForge_Override.py |
| DB              | tradesv3.freqforge_canary.dryrun.sqlite                     |
| Whitelist       | LINK/USDT, DOT/USDT, ATOM/USDT, XRP/USDT, UNI/USDT         |
| Stake           | 50 USDT, max_open_trades: 3                                 |
| Bot Name        | freqforge_canary_v1                                         |

---

## Pair Selection

```
FreqForge Whitelist:  BTC  ETH  SOL  AVAX  NEAR  ARB  OP
FreqForge Open:       BTC       SOL  AVAX
                              ↕ NO OVERLAP ↕
Canary Whitelist:     LINK DOT  ATOM  XRP  UNI
```

Alle 5 Paare verifiziert auf Bitget spot via `freqtrade list-pairs`.

---

## Phase 1: Preflight Validation

**CHECK 1: FreqForge unangetastet**

```bash
# Expected: 3 open trades
docker exec freqtrade-freqforge sqlite3 \
  /freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite \
  "SELECT count(*) FROM trades WHERE is_open=1;"
# PASS if: 3

# Expected: config md5 unchanged
md5sum /home/hermes/projects/trading/freqforge/config/config_freqforge_dryrun.json
# PASS if: d4ba3543ff477deae56a2462587f0426
```

**CHECK 2: Port 8088 frei**

```bash
docker ps -a --format "{{.Names}} {{.Ports}}" | grep 8088
# PASS if: empty output
```

**CHECK 3: Canary-Container existiert nicht**

```bash
docker ps -a --format "{{.Names}}" | grep freqforge-canary
# PASS if: empty output
```

**CHECK 4: Pairs auf Bitget verfuegbar**

```bash
docker exec freqtrade-freqforge freqtrade list-pairs \
  --exchange bitget \
  --config /freqtrade/config/config_freqforge_dryrun.json \
  --quote USDT --print-json | python3 -c "
import json,sys
pairs = json.load(sys.stdin)
need = ['LINK/USDT','DOT/USDT','ATOM/USDT','XRP/USDT','UNI/USDT']
for p in need:
    print(f'{p}: {\"OK\" if p in pairs else \"MISSING\"}')"
```

---

## Phase 2: Dateien erstellen

**SCHRITT 2a: Verzeichnisse**

```bash
mkdir -p /home/hermes/projects/trading/freqtrade/bots/freqforge-canary/config
mkdir -p /home/hermes/projects/trading/freqtrade/bots/freqforge-canary/user_data/strategies
```

**SCHRITT 2b: Strategy-Datei kopieren**

```bash
cp /home/hermes/projects/trading/freqforge/user_data/strategies/FreqForge_Override.py \
   /home/hermes/projects/trading/freqtrade/bots/freqforge-canary/user_data/strategies/FreqForge_Override.py
```

**SCHRITT 2c: Config schreiben**

Datei: `/home/hermes/projects/trading/freqtrade/bots/freqforge-canary/config/config.json`

```json
{
  "max_open_trades": 3,
  "stake_currency": "USDT",
  "stake_amount": 50,
  "tradable_balance_ratio": 0.95,
  "last_stake_amount_min_ratio": 0.5,
  "fiat_display_currency": "USD",
  "dry_run": true,
  "dry_run_wallet": 1000,
  "cancel_open_orders_on_exit": false,
  "exchange": {
    "name": "bitget",
    "pair_whitelist": [
      "LINK/USDT",
      "DOT/USDT",
      "ATOM/USDT",
      "XRP/USDT",
      "UNI/USDT"
    ],
    "pair_blacklist": [
      "UST/USDT", "LUNA/USDT", "LUNC/USDT",
      "TUSD/USDT", "USDC/USDT", "DAI/USDT"
    ]
  },
  "entry_pricing": {
    "price_side": "other",
    "use_order_book": true,
    "order_book_top": 1,
    "price_last_balance": 0.0
  },
  "exit_pricing": {
    "price_side": "other",
    "use_order_book": true,
    "order_book_top": 1
  },
  "order_types": {
    "entry": "limit",
    "exit": "limit",
    "stoploss": "market",
    "stoploss_on_exchange": false
  },
  "unfilledtimeout": {
    "entry": 30,
    "exit": 30,
    "exit_timeout_count": 0,
    "unit": "minutes"
  },
  "pairlists": [
    { "method": "StaticPairList" }
  ],
  "api_server": {
    "enabled": true,
    "listen_ip_address": "0.0.0.0",
    "listen_port": 8088,
    "verbosity": "info",
    "enable_openapi": false,
    "jwt_secret_key": "REDACTED-rotate-after-deployment",
    "CORS_origins": [],
    "username": "canary",
    "password": "canary_readonly"
  },
  "bot_name": "freqforge_canary_v1",
  "initial_state": "running",
  "force_entry_enable": false,
  "process_only_new_candles": true,
  "internals": { "process_throttle_secs": 5 },
  "db_url": "sqlite:////freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite",
  "user_data_dir": "/freqtrade/user_data"
}
```

**SCHRITT 2d: Docker-Compose Service hinzufuegen**

Datei: `/home/hermes/projects/trading/freqtrade/docker-compose.fleet.yml`

Am Ende vor dem Ende einfuegen:

```yaml
  # ---------------------------------------------------------------------------
  # CANARY — FreqForge-Canary (RSI Replacement)
  # ---------------------------------------------------------------------------
  freqtrade-freqforge-canary:
    image: freqtradeorg/freqtrade:stable
    container_name: freqtrade-freqforge-canary
    restart: unless-stopped
    networks:
      - ki-fabrik
    ports:
      - "127.0.0.1:8088:8088"
    volumes:
      - /home/hermes/projects/trading/freqtrade/bots/freqforge-canary/config:/freqtrade/config:ro
      - /home/hermes/projects/trading/freqtrade/bots/freqforge-canary/user_data:/freqtrade/user_data:rw
      - /home/hermes/projects/trading/freqtrade/shared:/freqtrade/shared:rw
      - /home/hermes/projects/trading/freqtrade/logs:/freqtrade/logs:rw
    command: >
      trade
      --dry-run
      -vv
      --strategy FreqForge_Override
      --config /freqtrade/config/config.json
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"
    labels:
      - "hermes.bot=freqforge-canary"
      - "hermes.phase=fleet"
      - "hermes.exchange=bitget"
```

---

## Phase 3: Pre-Deployment Safety Check

**CHECK: FreqForge noch unangetastet nach Datei-Erstellung**

```bash
md5sum /home/hermes/projects/trading/freqforge/config/config_freqforge_dryrun.json
# PASS if: d4ba3543ff477deae56a2462587f0426

docker exec freqtrade-freqforge sqlite3 \
  /freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite \
  "SELECT count(*) FROM trades WHERE is_open=1;"
# PASS if: 3
```

---

## Phase 4: Deployment (APPROVAL GATE)

**NUR NACH EXPLIZITER FREIGABE DURCH LUKE**

### Schritt 4a: RSI stoppen

```bash
docker stop freqtrade-rsi
# Verify:
docker ps -a --format "{{.Names}} {{.Status}}" | grep rsi
# Expected: Exited
```

### Schritt 4b: Canary starten

```bash
cd /home/hermes/projects/trading/freqtrade
docker compose -f docker-compose.fleet.yml up -d freqtrade-freqforge-canary
```

### Fehler-Szenario: Canary startet nicht

```bash
# Check logs
docker logs freqtrade-freqforge-canary --tail 30

# Hauefigste Ursachen:
# 1. "pair not found" → Whitelist pruefen
# 2. "strategy not found" → Strategy-Datei im user_data/strategies/ pruefen
# 3. "port already in use" → Port-Kollision pruefen

# Recovery:
docker rm -f freqtrade-freqforge-canary
# Fix config, retry Schritt 4b
```

---

## Phase 5: Post-Deployment Verification

**CHECK 1: Container laeuft**

```bash
docker ps --format "{{.Names}} {{.Status}}" | grep canary
# Expected: Up X seconds
```

**CHECK 2: Logs fehlerfrei**

```bash
docker logs freqtrade-freqforge-canary --tail 40 2>&1 | grep -iE "error|fail|traceback"
# Expected: empty (no errors)
```

**CHECK 3: Strategy + Pairs geladen**

```bash
docker logs freqtrade-freqforge-canary --tail 40 2>&1 | grep -iE "whitelist|strategy"
# Expected: "Whitelist with 5 pairs: ['LINK/USDT', ...]"
# Expected: "FreqForge_Override"
```

**CHECK 4: DB isoliert**

```bash
docker exec freqtrade-freqforge-canary sqlite3 \
  /freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite \
  "SELECT name FROM sqlite_master WHERE type='table';"
# Expected: trades, orders, etc. (fresh DB)

# CROSS-CHECK: FreqForge DB unveraendert
docker exec freqtrade-freqforge sqlite3 \
  /freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite \
  "SELECT count(*) FROM trades WHERE is_open=1;"
# Expected: 3 (unchanged)
```

**CHECK 5: Entries erlaubt oder idle**

```bash
docker logs freqtrade-freqforge-canary --tail 80 2>&1 | grep -iE "enter|entry|signal"
# Expected: Either entry signals or "no enter signals" (both OK for first run)
```

---

## Rollback

```bash
# 1. Canary stoppen + entfernen
docker stop freqtrade-freqforge-canary
docker rm freqtrade-freqforge-canary

# 2. Compose-Service entfernen (optional — Config bleibt fuer Audit)
# Aus docker-compose.fleet.yml den canary-Service-Block loeschen

# 3. RSI wieder starten (optional)
docker start freqtrade-rsi

# 4. Verify FreqForge unangetastet
docker exec freqtrade-freqforge sqlite3 \
  /freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite \
  "SELECT count(*) FROM trades WHERE is_open=1;"
```

---

## No-Touch Confirmation

```
NICHT MODIFIZIERT durch dieses Runbook:
  ✓ FreqForge config:        d4ba3543ff477deae56a2462587f0426
  ✓ FreqForge strategy:      2daa67c81b116d08026623793fe3bd0d
  ✓ FreqForge container:     Running, 3 open trades
  ✓ FreqForge DB:            tradesv3.freqforge.dryrun.sqlite
  ✓ RSI data/config:         Erhalten (nur Container gestoppt)
  ✓ Exchange credentials:    Unveraendert
  ✓ dry_run:                 true (beide Bots)
```

---

## Improvement Summary (RSIP)

| Iteration | Fokus              | Wichtigste Verbesserung                              |
|-----------|--------------------|-------------------------------------------------------|
| 1         | Grundstruktur      | Basis-Schritte + Rollback                             |
| 2         | Klarheit/Logik     | Approval-Gates, Fehler-Szenarien, Safety-Assertions   |
| 3         | Feinschliff        | Copy-paste-Commands, vollstaendiges YAML, Monitoring  |
