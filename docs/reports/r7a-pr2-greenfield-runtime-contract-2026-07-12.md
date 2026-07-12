# R7A PR-2 — Greenfield Runtime Contract Report

**Datum:** 2026-07-12  
**Branch:** `feat/r7a-greenfield-compose-rainbow-tests`  
**Base:** `7aec717` (PR #519 merge — R7A PR-1 Docs)  
**Issue:** #504 (R7A), #496 (R7 Measurement), #423 (Live-Gate)  
**Autor:** Hermes Orchestrator  

---

## 1. Basis-SHA

```
7aec717 docs(r7a): ADR + Reconciliation-Report + Registry + State-Note [PR-1] (#519)
```

---

## 2. Geänderte Dateien

| Datei | Aktion | LOC |
|-------|--------|-----|
| `freqtrade/bots/regime-hybrid/user_data/config.example.json` | NEW | 67 |
| `freqtrade/bots/webserver/user_data/config.example.json` | NEW | 67 |
| `docker-compose.hermestrader-dryrun.yml` | NEW | ~220 |
| `services/rainbow/rainbow.include.yml` | NEW | 53 |
| `config/rainbow.internal.yml` | NEW | 32 |
| `docs/integration/rainbow-hermestrader-wiring.md` | NEW | 120 |
| `docs/specs/hermestrader-r7a-storage-state-contract.md` | NEW | 170 |
| `tests/test_hermestrader_dryrun_compose.py` | NEW | ~350 |
| `docs/reports/r7a-pr2-greenfield-runtime-contract-2026-07-12.md` | NEW | (this file) |

---

## 3. Fleet-Modell

**Selected:** OPTION_C  
**Default-Services:** freqforge + canary + regime-hybrid + webserver + rainbow  
**Profile-gated:** freqai-rebel (`profiles: ["rebel"]`)

| Bot | Strategie | dry_run | Config |
|-----|-----------|---------|--------|
| freqforge | FreqForge_Override | true | config.example.json |
| canary | FreqForge_Override | true | config.example.json |
| regime-hybrid | RegimeSwitchingHybrid_v7_v04_Integration | true | config.example.json |
| webserver | (support) | true | config.example.json |
| rebel | RebelLiquidation | true | (profile-gated) |

---

## 4. Config-Inventar

| Service | `config.example.json` getrackt | `dry_run: true` | Credentials sanitisiert |
|---------|-------------------------------|-----------------|------------------------|
| freqforge | ✅ (pre-existing) | ✅ | ✅ CHANGE_ME |
| canary | ✅ (pre-existing) | ✅ | ✅ CHANGE_ME |
| regime-hybrid | ✅ NEW | ✅ | ✅ CHANGE_ME |
| webserver | ✅ NEW | ✅ | ✅ CHANGE_ME |

**Aktive Configs (`config.json`)**: gitignored, host-seitig, Deploy via Secrets-Injection.

---

## 5. Dockerfile.hermes10000

Current state uses `FROM freqtradeorg/freqtrade:stable` (movable tag).

**Known risk:** The tag can move. A digest pin is recommended for R5a deployment but
is out of scope for this repo-only PR — the actual digest is only known after a
deterministic build, which requires `docker build` (host operation, not repo work).

**Healthcheck compatibility:** The `freqtradeorg/freqtrade:stable` image includes
`python3` but does NOT include `curl`. All healthchecks in the greenfield compose
use `python3` for HTTP checks.

---

## 6. Render-Ausgabe

The compose file is valid YAML and renders without structural errors. Full
`docker compose config` rendering requires a running Docker daemon (R5a scope).
The test suite validates structure via `yaml.safe_load`.

---

## 7. Tests

Test suite: `tests/test_hermestrader_dryrun_compose.py`

Covers 20 assertion groups:
1. Compose renders as valid YAML
2. Registry/compose service agreement
3. Default fleet = OPTION_C
4. Rebel has profile, not in default start
5. All configs have `dry_run=true`
6. No `dry_run=false` in configs
7. Configs and strategies are read-only mounts
8. DB/Log paths are writable volumes
9. All services run as 10000:10000
10. No privileged containers
11. cap_drop: ALL
12. no-new-privileges:true
13. No docker.sock mount
14. No 0.0.0.0 port binds
15. Rainbow has no published ports
16. No /home/hermes/projects paths
17. Healthchecks use python3, not curl
18. Log rotation configured
19. No secrets in committed configs
20. Rainbow config: ta_collector, no evaluation, no delivery

---

## 8. Secret Scan

All committed config files contain only `CHANGE_ME` / `CHANGE...WORD` placeholders.
No api_key, api_secret, jwt_secret_key with real values. Exchange section contains
only `name`, `pair_whitelist`, `pair_blacklist`.

---

## 9. Bekannte Rest-Risiken

| Risiko | Status | Mitigation |
|--------|--------|------------|
| `Dockerfile.hermes10000` uses `stable` tag | OPEN | Digest pin at R5a deploy |
| Rainbow build context references external repo | OPEN | ai4trade-bot SHA must be recorded at deploy |
| Active `config.json` not in repo | BY DESIGN | Secrets injected at deploy time |
| `docker compose config` not tested without daemon | OPEN | R5a pre-deploy render check |
| Legacy compose test (`test_docker_compose_contracts.py`) tests RSI/Momentum | KNOWN | Legacy test, not part of greenfield contract |

---

## 10. Rollback

**Rollback = `git revert <merge-commit>`.**

No host mutation performed. No containers started. No volumes created.
The greenfield compose file does not affect any running service until explicitly
deployed via `docker compose up` (R5a scope, approval-gated).

---

## 11. Bestätigung

> Diese PR führt keine Runtime- oder Host-Mutation aus.  
> Keine Container wurden gestartet.  
> Keine Configs wurden auf dem Host geändert.  
> `dry_run=false` ist nicht enthalten.  
> Live-Trading bleibt #423-gated.
