# Telegram + Healthcheck Fix — 2026-06-06

## Änderungen

### Telegram Integration
**Problem:** Kein Telegram-Block in aktiven Freqtrade-Configs (G-01).

**Lösung:** Env-basiert via `FREQTRADE__TELEGRAM__*` Umgebungsvariablen:
1. `/opt/data/.env.telegram` erstellt mit:
   - `FREQTRADE__TELEGRAM__ENABLED=true`
   - `FREQTRADE__TELEGRAM__TOKEN=***` (aus /opt/data/.env)
   - `FREQTRADE__TELEGRAM__CHAT_ID=***REDACTED***`
2. `docker-compose.yml`: `env_file: /opt/data/.env.telegram` hinzugefügt zu:
   - `freqtrade-freqforge`
   - `freqtrade-freqforge-canary`
   - `freqtrade-regime-hybrid`
   - `freqai-rebel`
   - `freqtrade-webserver`

**Kein Config-Edit nötig** — Freqtrade liest `FREQTRADE__*` Env-Vars automatisch.

**Restart erforderlich** für alle 5 Container damit Env-Vars aktiv werden.

### Healthchecks
**Problem:** 5/5 Trading-Containern ohne Healthcheck (G-03).

**Lösung:** `wget`-basierter Healthcheck auf `/api/v1/ping` hinzugefügt:
```yaml
healthcheck:
  test: ["CMD-SHELL", "wget -qO- http://localhost:8080/api/v1/ping >/dev/null || exit 1"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```
(Start_period 120s für FreqAI-Rebel wegen Modell-Ladezeit)

**Restart erforderlich** für alle 5 Container.

### FreqAI-Rebel DB Path (G-08 korrigiert)
**Geprüft:** Config nutzt `freqai_rebel` (Underscore), die aktive DB `tradesv3.freqai_rebel.dryrun.sqlite` existiert mit 80K und ist frisch (Jun 6).
**Kein Fix nötig** — Config ist korrekt. Nur die 0-byte `tradesv3.freqai-rebel.dryrun.sqlite` ist ein Stale-Artifact.

## Noch ausstehend (Restart erforderlich)
```bash
docker compose up -d --no-deps freqtrade-freqforge
docker compose up -d --no-deps freqtrade-freqforge-canary
docker compose up -d --no-deps freqtrade-regime-hybrid
docker compose up -d --no-deps freqai-rebel
docker compose up -d --no-deps freqtrade-webserver
```
(Jeweils einzeln, mit 20s Pause dazwischen zur Validierung)

## Git Diff
```diff
 docker-compose.yml | 29 +++++++++++++++++++++++++++++
 1 file changed, 29 insertions(+)
```
