# Hermes Post-Lockdown Verification — After Root Repair

**Date:** 2026-06-01 15:51 UTC
**Run as:** hermes (uid=1337, gid=1337, groups: docker, ftuser)
**Verdict: READY_FOR_24H_OBSERVATION**

---

## Executive Verdict

**GREEN — Prompt 4 (24h Observation) darf starten.**

Alle Systeme sauber. Root-Contamination vollständig beseitigt. Keine root-eigenen Dateien in den letzten 2 Stunden. Alle Ownership/Mode-Erwartungen erfüllt. Alle Container laufen, alle Bots dry_run=True, State-Persistierung funktioniert. Deploy-Grenze korrekt enforced.

---

## 1. Current User Verification

- User: **hermes** (uid=1337)
- Groups: hermes(1337), docker(110), ftuser(10000)
- Nicht root. Nicht claudio.

---

## 2. Git Health

**Repository:** `/home/hermes/projects/trading/`

**Recent commits:**
```
dae18de fix(hermes): enforce deterministic runtime ownership and deploy contract
3d5f2a9 fix(hermes): deploy all enabled jobs.json script jobs
de761b4 fix(hermes): align runtime container references from hermes-agent to hermes-green
0c8fa3b chore(hermes): establish runtime script source of truth and ownership contract
262f53e fix: guardian profile script sync — detect stale scripts, not just missing
e9ed186 fix: permanent self-healing infrastructure + systematic bug fixes
```

**Modified files (GENERATED_IGNORE):**
- `orchestrator/reports/fleet_health_latest.json`
- `orchestrator/reports/fleet_health_latest.md`

**Untracked files (DOCS_CONTEXT):**
- 11x `docs/context/*-20260601*.md` — Session-Kontextdokumente
- `orchestrator/scripts/.mcp_daemon.pid` — PID-Datei

**ACTION_REQUIRED: 0**

---

## 3. Root-Contamination Re-check

| File | Owner:Group | Mode | Status |
|------|-------------|------|--------|
| `.git/index` | hermes:hermes | 644 | OK |
| `.git/refs/heads/main` | hermes:hermes | 644 | OK |
| docs/context/* (11 Dateien) | hermes:hermes | 664 | OK |
| ai-hedge-fund-crypto/output/hermes_signal.json | hermes:ftuser | 664 | OK |
| ai-hedge-fund-crypto/output/sentiment_data.json | hermes:hermes | 664 | OK |
| ai-hedge-fund-crypto/output/latest/hermes_signal.json | hermes:ftuser | 664 | OK |

**Root-owned files (last 2h, checked dirs): 0**

---

## 4. Deploy Boundary Result

```
FAIL: deploy_cron_scripts.sh must run as root
EXIT_CODE=1
```

**Classification: EXPECTED_ROOT_LOCKDOWN_BEHAVIOR** — Deploy-Script ist root-only by design. Hermes darf nicht deployen.

---

## 5. Runtime Ownership Result

| Resource | Owner:Group | Mode | Expected | Status |
|----------|-------------|------|----------|--------|
| Runtime scripts (10 files) | 10000:ftuser | 755 | 10000:ftuser/755 | OK |
| jobs.json | 10000:ftuser | 640 | 10000:ftuser/640 | OK |
| orchestrator/state/ | hermes:ftuser | 2775 | hermes:ftuser/2775 | OK |
| orchestrator/logs/ | hermes:ftuser | 2775 | hermes:ftuser/2775 | OK |
| drawdown_state.json | hermes:ftuser | 664 | hermes:ftuser/664 | OK |
| drawdown_state_prev.json | hermes:ftuser | 664 | hermes:ftuser/664 | OK |
| container_watchdog_state.json | hermes:ftuser | 664 | hermes:ftuser/664 | OK |

**claudio-owned runtime files: 0**

---

## 6. jobs.json Status Persistence

| Check | Result |
|-------|--------|
| Host hermes can read | YES |
| Host hermes can write | NO (Permission denied) — correct |
| hermes-green (UID 10000) can write | YES (touch test passed) |
| `last_run_at` field exists | YES (currently null — initial state) |
| `last_status` field exists | YES |
| `last_error` field exists | YES |
| `next_run_at` field exists | YES |

**Verdict: Working as designed.** Hermes-green runtime context can write; host hermes cannot.

---

## 7. Jobs Coverage

**9 enabled=True script jobs — all verified:**

| Job | Script | Git | Runtime | CRON_ONLY |
|-----|--------|-----|---------|-----------|
| signal-heartbeat | ai_hedge_signal_heartbeat.sh | OK | OK | No |
| trading-pipeline | trading_pipeline.py | OK | OK | No |
| drawdown-guard | drawdown_guard.py | OK | OK | No |
| container-watchdog | container_watchdog.sh | OK | OK | No |
| mcp-watchdog | mcp_watchdog.sh | OK | OK | No |
| daily-backup | backup_rotation.py | OK | OK | No |
| portfolio-rebalancer | portfolio_rebalancer.py | OK | OK | No |
| cron-guardian | restore_cron_jobs.sh | OK | OK | No |
| smart-heartbeat | smart_heartbeat.py | OK | OK | No |

+ 1 agent job (Fleet Report) — no script, prompt-based.

**Missing scripts: 0. CRON_ONLY scripts: 0.**

---

## 8. Safety Checks

### drawdown_guard dry-run
- Portfolio: $3,499.30 / $3,450.00 start (+$49.30, DD: 0.0%)
- 4/4 Bots erreichbar
- Signal age: 7.4 min (FRESH)
- State written to: `orchestrator/state/drawdown_state.json` ✅

### container_watchdog
- All 5 containers: running
- State written to: `orchestrator/state/container_watchdog_state.json` ✅

### smart_heartbeat signal source
- Reads: `ai-hedge-fund-crypto/output/latest/hermes_signal.json` ✅
- Signal freshness: 0.3 min (FRESH) ✅

---

## 9. Trading Dry-Run Safety

| Bot | Config | dry_run | Status |
|-----|--------|---------|--------|
| freqtrade-freqforge | config_freqforge_dryrun.json | True | OK |
| freqtrade-freqforge-canary | config_canary_dryrun.json | True | OK |
| freqtrade-regime-hybrid | config_regime_hybrid_dryrun.json | True | OK |
| freqai-rebel | user_data/config.json | True | OK |

**All bots: dry_run=True. No live trading.**

---

## 10. Runtime Health

| Container | Status | Uptime |
|-----------|--------|--------|
| hermes-green | Running | 5h |
| trading-guardian | Running | 13h |
| green-mem0 | Healthy | 9h |
| green-qdrant | Running | 3d |
| green-ollama | Running | 3d |
| ai-hedge-fund-crypto | Healthy | 13h |
| freqtrade-freqforge | Running | 11h |
| freqtrade-freqforge-canary | Running | 11h |
| freqtrade-regime-hybrid | Running | 11h |
| freqai-rebel | Running | 11h |
| freqtrade-webserver | Running | 4d |

**All containers operational.**

---

## Ready For 24h Observation?

**YES. Prompt 4 darf starten.**

Keine roten Punkte. Alle Systeme sauber und konsistent.
