# Rainbow Producer Lifecycle Hardening — Phase A

**Date:** 2026-06-23
**Branch:** `fix/rainbow-producer-lifecycle-phase-a`
**Commit:** Phase A preparation (repo-only, no runtime restart)
**Classification:** GREEN
**Issue:** [#325](https://github.com/GoLukeEnviro/trading-hub/issues/325)

---

## 1. Scope

Prepare Rainbow Producer lifecycle hardening in the trading-hub repo:
- Migrate PID/log paths from `/tmp` to persistent `/opt/data/rainbow/`
- Add a stdlib-only readiness/status checker with HTTP-based freshness validation
- Add 26 tests covering health, signals, freshness, edge cases, and safety
- **No runtime restart.** Active producer keeps old `/tmp` paths until Phase C.
- **No auto-restart enablement.**
- **No factory logging fix** (that's Phase B in ai4trade-bot).

---

## 2. Changed Files

| File | Change |
|------|--------|
| `orchestrator/scripts/rainbow_producer_manager.sh` | PIDFILE → `/opt/data/rainbow/rainbow-producer.pid`, LOGFILE → `/opt/data/rainbow/rainbow-producer.log`, `mkdir -p` on start |
| `orchestrator/scripts/rainbow_producer_readiness_check.py` | **NEW** — stdlib-only readiness checker |
| `tests/test_rainbow_producer_readiness_check.py` | **NEW** — 26 unit + integration tests |
| `docs/backlog/rainbow-producer-lifecycle-hardening.md` | Updated status to Phase A completed |

---

## 3. Readiness Checker

```bash
python3 orchestrator/scripts/rainbow_producer_readiness_check.py \
  --base-url http://127.0.0.1:8000 \
  --freshness-max-seconds 900
```

**Live result at time of writing:**
```
Verdict       : GREEN
Health        : healthy
Signal count  : 50
Freshest ts   : 2026-06-23T08:13:43.689404+00:00
Age (seconds) : 3.9
Freshness max : 900s
Fresh         : True
```

### Exit codes
- `0` → **GREEN** — health reachable, signals present, freshest ≤ max_age
- `1` → **RED/YELLOW** — unreachable, empty, stale, or future timestamps
- `2` → Invalid arguments

### Features
- Stdlib-only (`urllib.request`, `json`, `argparse`, `datetime`), zero dependencies
- Human-readable + `--json` output modes
- Configurable `--base-url` and `--freshness-max-seconds`
- No secrets, no auth headers, no mutation

---

## 4. Test Suite

**26 tests, all passing.**

| Category | Tests | Coverage |
|----------|-------|----------|
| `_iso_to_dt` | 3 | Z-suffix, offset, microseconds |
| `_fetch_json` | 4 | dict, list, refused, malformed |
| `check_health` | 3 | healthy, unreachable, unexpected type |
| `check_signals` | 7 | list, dict wrapper, empty, no timestamps, unreachable, stale, unparseable |
| `main()` exit codes | 5 | healthy→0, unreachable→1, stale→1, empty→1, json output |
| No secrets / no auth | 2 | headers check, source scan |
| CLI args | 2 | base-url override, --help |

---

## 5. Validation Commands

```bash
# Bash syntax
bash -n orchestrator/scripts/rainbow_producer_manager.sh   # ✅

# Python compile
python3 -m py_compile orchestrator/scripts/rainbow_producer_readiness_check.py  # ✅

# Live readiness check
python3 orchestrator/scripts/rainbow_producer_readiness_check.py  # ✅ GREEN

# All tests
.venv/bin/python -m pytest tests/test_rainbow_producer_readiness_check.py -q  # ✅ 26 passed

# Safety scan
grep -RniE 'dry_run[" ]*[:=][" ]*false' orchestrator self_improvement_v2 docs tests  # ✅ clean
```

---

## 6. Current Runtime Status

Rainbow Producer: **RUNNING** (PID 171665, uptime ~2h21m)

⚠️ Active producer still uses old `/tmp/rainbow-producer.pid` and `/tmp/rainbow-producer.log` until next approved restart (Phase C). The manager script changes take effect on next `start`/`restart`.

---

## 7. Non-Goals (this phase does NOT)

- Restart Rainbow or any other service
- Enable auto-restart, cron-based restart, systemd, or s6
- Touch Docker or Docker Compose
- Change SI-v2 scoring logic
- Change Freqtrade config or strategy
- Fix factory-mode logging in ai4trade-bot
- Enable boot persistence
- Set `dry_run=false` or enable live trading

---

## 8. Next Steps

| Phase | Scope | Repo |
|-------|-------|------|
| **B** | Factory logging fix: `setup_logging()` in `create_app()` path | ai4trade-bot |
| **C** | L3 Runtime: controlled Rainbow restart, new PID/log paths active | trading-hub |
| **D** | Boot-persistence / auto-restart (requires explicit approval) | trading-hub |
