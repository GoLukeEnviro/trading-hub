# Git Cleanliness Audit + Full Backup Session — 2026-06-08

**Datum:** 2026-06-08  
**Durchgeführt von:** hermes + Ara (Perplexity)  
**Scope:** `/home/hermes/projects/trading` (trading-hub) + alle nested Repos

---

## Was gemacht wurde

### 1. Trading Hub Cleanup (projects/trading)
- **Permission-Drift gefixt:** sudo + setfacl -b -R + chmod g+rw — ACLs cleared, 10000/ftuser Ownership auf hermes korrigiert
- **Explizites Staging** (nie git add .) von 2005 Files, 77118 Insertions:
  - `docker-compose.yml` (Mem0/Dream-Mode Recovery: LLM-Base-URL, Model gpt-oss:20b, EMBEDDING_DIMS 1024→2560, env_file + Live-Patch-Volumes)
  - 36 `docs/context/*.md` (Memory V2 Curation/Backfill/Exact-ID-Patch/Dream-Mode/Retirement, Self-Improvement Runs, Telegram-Hygiene, Trade-Exports, Ledger-Watchdog, Issue-9, branch-full-audit, gesamt-aenderungsuebersicht)
  - `docs/runbooks/hermes-gateway-debug.md`
  - 3 Convenience-Symlinks: `freqtrade/freqai-rebel`, `freqforge-canary`, `regime-hybrid`
  - `polymarket-fadi/` (21.159 TS/TSX Files — vollständiger Polymarket Bot + Dashboard)
  - `orchestrator/archive/20260606-telegram-alert-queue/` (1963 Alert-JSONs mit Fleet-Reports, PnL, WR, Quarantäne-History)
- **Commit:** `8ac2af8` — gepusht auf origin/main
- **Re-Verify:** main up-to-date, 0 untracked docs/context/*.md, keine Secrets getrackt, 23 verbleibende Untracked (korrekt: Data-Dumps, episode-py, mem0-v1-archive)

### 2. Nested Repos gesichert (alle vorher KEIN Remote-Backup)
| Repo lokal | GitHub | Letzter Commit |
|---|---|---|
| polymarket-fadi/repo | [GoLukeEnviro/polymarket-fadi](https://github.com/GoLukeEnviro/polymarket-fadi) | 8264701 CRITICAL FIX: Apply v3.1 |
| weatherbot | [GoLukeEnviro/weatherbot-hermes](https://github.com/GoLukeEnviro/weatherbot-hermes) | 3cabb23 Update config.json |
| Polymarket-BTC-15-Minute-Trading-Bot | [GoLukeEnviro/polymarket-btc-15m-bot](https://github.com/GoLukeEnviro/polymarket-btc-15m-bot) | 69985e5 adjust on live signals |
| btc5m-bot | [GoLukeEnviro/btc5m-bot](https://github.com/GoLukeEnviro/btc5m-bot) | 2577df2 v1.0.0: BTC 5-min (force) |

Push-Methode: gh HTTPS + Token (robuster als SSH-Alias in dieser Umgebung wegen HOME-Abweichung)

---

## Verbleibende Todos (nächste Session)

- [ ] Cleanup Phase 1-5 aus plan.md: decommissioned Bots (momentum/, mvs/, rsi/), .bak-Müll, 4.5G Working Tree
- [ ] SSH-Alias auf nested Repos wiederherstellen (optional)
- [ ] .gitignore härten für neue dated Backup-Patterns
- [ ] polymarket-fadi gitlink (160000) klären — ggf. nested .git entfernen + direkt tracken

---

## Hygiene-Status nach Session

- Keine Verlustrisiken mehr
- Alle wichtigen Sources auf GitHub gesichert
- Branch healthy, keine Secrets getrackt
- Permission-Drift in docs/context/ behoben

**Supersedes:** `git-hygiene-run-2026-06-07.md`, `branch-full-audit-2026-06-07.md`
