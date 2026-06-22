# P0 Security Status — 2026-06-22

**Baseline:** `main` at `2f8a70a`  
**Auditor:** Hermes Meta-Orchestrator  
**Audit Report:** `docs/reports/comprehensive-code-project-audit-2026-06-22.md`

---

## Summary

All P0 security items are **closed or deferred with accepted risk**. The system is safe for SI-v2 observation loop operation in dry-run mode.

---

## P0 Item Status

| P0-Item | Description | Status | Commit | Tests |
|---------|-------------|--------|--------|-------|
| **P0-1** | Kill Switch fail-CLOSED | ✅ **DONE** | `8e6c555` (#315) | 38 tests in `test_kill_switch.py` |
| **P0-2** | Kill Switch TOCTOU Race | ✅ **DONE** | `8e6c555` (#315) | Auto-clear no-write regression test |
| **P0-3** | drawdown_guard Credentials | ✅ **DONE** | `84b1258` (#317) | 9 tests in `test_drawdown_guard_credentials.py` |
| **P0-4** | Config Templates & Safety | ✅ **DONE** | `9fe0b9c` (#318) | 16 tests in `test_config_credential_safety.py` |
| **P0-5a** | Docker Mount Impact Audit | ✅ **DONE** | `a5e788a` (#319) | Read-only audit report |
| **P0-5b** | Script Proxy Compatibility | ✅ **DONE** | `f1fd086` (#320) | 299 passed, grep-verified clean |
| **P0-5c** | Socket Mount Removal | 🔶 **DEFERRED** | `2f8a70a` (#321) | Accepted risk — see decision record |

---

## P0-5c: Why Deferred

The direct Docker socket mount on `hermes-green` remains as an **explicitly accepted operational risk**. Removal was attempted (P0-5c) but blocked by compose/container config drift that would produce a different container on recreate.

**Decision:** Socket stays. Risk is governed by documented guardrails. See `docs/context/p0-5-docker-access-governance-decision-20260622.md`.

**This does not block the SI-v2 loop.** All monitoring scripts are proxy-compatible (P0-5b). Docker access works via both the direct socket and the proxy simultaneously.

---

## Remaining Risk Profile

| Risk | Severity | Status |
|------|----------|--------|
| Docker socket grants host-level power | Medium | Accepted, governed |
| Compose ↔ container drift | Medium | Tracked as P1 |
| Proxy has EXEC=1 + POST=1 | Low-Medium | Accepted (needed for bot reads) |

---

## P1 Follow-up (Not Blocking SI-v2)

| P1-Item | Description |
|---------|-------------|
| Compose Reconciliation | Fix env_file path, add missing mounts, pin image tag |
| ShadowLock Hash-Chaining | Add `prev_entry_sha256` for tamper-evidence |
| Dashboard Auth | Add token/basic-auth behind Caddy reverse proxy |
| Bare Excepts | Replace 25 bare `except:` in orchestrator with typed handlers |
| `shell=True` | Replace 8× `subprocess.run(shell=True)` with list-form |
| Ruff Auto-fix | 707 auto-fixable lint errors across codebase |

---

## SI-v2 Readiness

The SI-v2 observation loop is now safe to operate:

- ✅ Kill switch fails CLOSED on all error paths
- ✅ No hardcoded credentials in tracked code or configs
- ✅ Config templates cover all 4 fleet bots with safe placeholders
- ✅ Docker monitoring scripts are proxy-compatible
- ✅ Dry-run enforcement unchanged (`LIVE_FORBIDDEN`)
- ✅ All 299 tests pass (1 skipped)
- ✅ Secret scan clean

**Next priority:** SI-v2 active cycle proof — 4/4 bots read → evidence bundle → ShadowProposal → mutations=0 → approval pending.
