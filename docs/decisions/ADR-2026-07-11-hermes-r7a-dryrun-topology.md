# ADR-2026-07-11: HermesTrader R7A Dry-Run-Topology

**Status:** ACCEPTED  
**Datum:** 2026-07-11  
**Autor:** CodeLuke  
**Issues:** #504 (R7A), #496 (R7-Messung), #423 (Live-Gate)  
**Verweis:** R3-Report → `docs/reports/r3-fleet-reproducibility-decision-2026-07-11.md`

**Roadmap-Mapping:** Root-Runtime Roadmap
`R4 — Greenfield Compose + Rainbow Runtime`
entspricht `R7A` / Issue #504.

**PR-Split:** PR #519 dokumentiert die Architekturentscheidung.
`docker-compose.hermestrader-dryrun.yml`, Rainbow-Wiring und Tests
werden erst durch PR-2 eingeführt.

---

## Kontext

Das trading-hub Projekt betreibt mehrere Freqtrade-Bots auf dem HermesTrader-VPS. Die bisherigen Compose-Dateien (`docker-compose.yml`, `freqtrade/docker-compose.fleet.yml`, `freqtrade/bots/freqai-rebel/docker-compose.yml`) sind inhärent widersprüchlich, historisch gewachsen und nicht auf einen kanonischen Stand gebracht worden (R3-Befund: drei divergierende Compose-Dateien). Rainbow wurde bisher nur als Standalone betrieben, nie als integrierter Service im trading-hub Stack.

R3-Entscheidung (OPTION_C): freqforge + canary + regime-hybrid als reproduzierbarer Fleet-Kern; rebel als NOT_REPRODUCIBLE eingestuft und damit aus dem Default-Deploy ausgeschlossen bis PR-3 (Rebel Epic).

## Entscheidung

**Geplante kanonische Datei ab PR-2:** `docker-compose.hermestrader-dryrun.yml`

Diese Datei ist das einzige offizielle Compose für den HermesTrader-Stack ab R7A. Sie ersetzt keine Legacy-Dateien (kein Löschen), sondern ist ein Greenfield-Compose parallel zum Altbestand.

### Was kanonisch ist

- OPTION_C: `freqtrade-freqforge` + `freqtrade-freqforge-canary` + `freqtrade-regime-hybrid` im Default
- `freqai-rebel` ausschließlich via `profiles: ["rebel"]` (opt-in, default aus)
- Rainbow als `internal-only` Service ohne `ports:`-Mapping, TA-only
- Netzwerk: `trading_internal` (bridge)
- Build via `freqtrade/Dockerfile.hermes10000` (kein `freqtradeorg/freqtrade:stable`)
- User: `10000:10000` für alle Bot-Services
- `dry_run: true` in allen Config-JSONs — `dry_run=false` ist **verboten** (Live-Gate #423)

### Legacy-Dateien (deprecated, nicht löschen)

| Datei | Status | Grund |
|---|---|---|
| `docker-compose.yml` | deprecated (Fleet-Teil) | Rollback-Sicherheit |
| `freqtrade/docker-compose.fleet.yml` | deprecated (veraltet) | Rollback-Sicherheit |
| `freqtrade/bots/freqai-rebel/docker-compose.yml` | deprecated | Rebel Epic (PR-3) |

### Rainbow Integration

- Include via `services/rainbow/rainbow.include.yml`
- Config vendored aus ai4trade-bot @ **b65510a** (PR #76, Dashboard + TA-Fix)
  - **Achtung:** Pin bei Host-Deploy aktualisieren falls ai4trade-bot weitergewachsen ist
  - > `bbcaf25` bleibt der dokumentierte Rainbow-R1-Contract-Baseline-Pin.
    > `b65510a` ist der für PR-2 vorgeschlagene Runtime-/Vendoring-Pin.
    > PR-2 muss den Versionssprung gegen ai4trade-bot verifizieren und belegen.
- `config/rainbow.internal.yml`: TA-Collector aktiv, `evaluation.enabled: false`, kein `delivery_worker`
- Healthcheck: HTTP `/health` (nicht Heartbeat-Datei — DB liegt unter `/app/rainbow/storage/`, nicht `/app/storage/`)
- Build-Context: `${AI4TRADE_CONTEXT:-../ai4trade-bot}`
- Kein `ports:`-Mapping — SI-v2 erreicht Rainbow via `http://rainbow:8000` im internen Netz

### HermesTrader-Pfade (VPS)

```
/opt/data/projects/trading-hub      ← trading-hub checkout
/opt/data/projects/ai4trade-bot     ← ai4trade-bot checkout (Rainbow Build-Context)
```

### SI-v2 Wiring (Read-Only-Modus)

```
SI_V2_RAINBOW_BASE_URL=http://rainbow:8000
SI_V2_RAINBOW_MODE=read_only
SI_V2_RAINBOW_ENABLED=true
```

Mutation-Counter muss 0 bleiben solange `read_only` aktiv ist.

## Konsequenzen

### Positiv
- Kanonischer Entry Point für alle R7A+ Deployments
- Rebel ist sicher isoliert bis Reproducibility-Problem gelöst (PR-3)
- Rainbow TA-Baseline ermöglicht R7-Messung (#496)
- Kein Host-State-Risiko durch Greenfield-Isolation

### Negativ / Trade-offs
- Drei Legacy-Compose-Dateien bleiben als toter Code im Repo (bewusst)
- ai4trade-bot Pin muss manuell beim Deploy geprüft werden
- Canary-Config hat `.bak`-Problem — muss vor erstem `up` händisch geprüft werden

### Nicht geändert
- Live-Trading bleibt **#423-gated**
- agent0 läuft weiter auf Legacy-Compose bis explizite Freigabe
- Host-Mutation erst nach BACKUP_GATE_GREEN + expliziter User-Freigabe

## Fleet-Optionen (zur Referenz)

| Option | Beschreibung | Status |
|---|---|---|
| OPTION_A | Struktureller Aufbau (alle Bots einzeln) | Strukturell Grundlage |
| OPTION_C | freqforge + canary + regime-hybrid (R7A-Gate) | **AKTIV** |
| rebel | freqai-rebel (opt-in via Profile) | NOT_REPRODUCIBLE bis PR-3 |

## R7A-Gate-Kriterien (vor Host-Deploy)

1. `BACKUP_GATE_GREEN` auf HermesTrader bestätigt
2. Explizite User-Freigabe
3. `docker compose -f docker-compose.hermestrader-dryrun.yml config` fehlerfrei
4. `pytest tests/test_hermestrader_dryrun_compose.py -q` grün
5. Legacy `docker-compose.yml` bleibt parallel aktiv

---

*Dieses ADR ersetzt keine vorherigen ADRs. Es ergänzt ADR-2026-07-11-hermes-root-runtime-authority.md.*
