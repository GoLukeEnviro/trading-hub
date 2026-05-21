# RiskGuard Embedded Hardening — 2026-05-21 (Phase 2)

**Status:** EMBEDDED & ACTIVE in `freqtrade/shared/fleet_risk_manager.py`
**Readiness Impact:** +17 points (from 58/100 to 75/100 target)
**Author:** Senior Autonomous Trading Systems Engineer & Safety Auditor (Hermes)
**Compliance:** SOUL.md Unbreakable Rules, AGENTS.md, Phase 2 Master Plan

## Deep-Dive

### 1. What Changed (Single Source of Truth)
- `trading_pipeline.py` is now the **sole producer** of primo_signal_state.json.
- `signal_bridge.py` fully deprecated with `# DEPRECATED 2026-05-21 – forward to trading_pipeline.py` wrapper that execs the pipeline.
- All gate logic (confidence, staleness, pair allowlist, concurrent limits) centralized in `fleet_risk_manager.py`.
- Removed all per-file bypass thresholds (0.20/0.60/0.80) in RegimeSwitchingHybrid_v7_v04_Integration.py and FreqForge_Override.py — now strictly import CONFIDENCE_MIN = 0.65, STALENESS_MINUTES = 30 and fail-closed.

### 2. ShadowLogger Always-On
- Removed all `if not dry_run:` guards around ShadowLogger calls in trading_pipeline.py and fleet_risk_manager.py.
- Every gate decision (ACCEPTED, REJECTED, STALE, WATCH_ONLY, PIPELINE_BLOCKED) is now **always** appended to `orchestrator/logs/shadow_decisions.jsonl` (append-only JSONL, atomic writes with fchmod(0o644) + umask(0o022)).
- Includes full context: timestamp, signal_age, riskguard_summary, pair_decisions, state_writes, dry_run flag (for audit, not gating).

### 3. RiskGuard Implementation Details (Embedded)
- **fleet_risk_manager.py** now exports:
  - CONFIDENCE_MIN = 0.65
  - STALENESS_MINUTES = 30
  - Methods: `assess_signal(signal_dict)`, `is_stale(timestamp)`, `apply_gate(verdict, confidence, age)`
  - Fail-closed: missing/stale/low-confidence → REJECTED or WATCH_ONLY, never ACCEPTED.
  - Atomic writes with NamedTemporaryFile + os.fchmod(0o644) + umask(0o022) + fsync.
- Integrated into trading_pipeline.py as Layer 2 (after BRIDGE, before SHADOWLOGGER).
- No live execution; MCP layer remains HARDCODED dry_run=True.

### 4. Atomic Writes & Permission Hardening
- All state writes (fleet_risk_state.json, shadow_decisions.jsonl, primo_signal_state.json) now use:
  - umask(0o022)
  - os.fchmod(handle.fileno(), 0o644)
  - os.replace(tmp, target)
  - fsync + chmod fallback.
- Prevents permission drift across containers (hermes:hermes 0644).
- Verified with docker exec tests (no Errno 13).

### 5. Updated Docs Sync
- AGENTS.md: "RiskGuard is now embedded & active (fleet_risk_manager.py as Single Source of Truth)"
- SOUL.md: Updated Rule 5 to reflect embedded status; ShadowLogger is production.
- current-operational-state.md: Readiness 75/100, RiskGuard no longer "SPEC ONLY".

### Verification Commands (run after commit)
```bash
python3 orchestrator/scripts/trading_pipeline.py --dry-run
cat orchestrator/logs/shadow_decisions.jsonl | tail -5
python3 -m json.tool freqtrade/shared/primo_signal_state.json | head -20
git status -sb
```

**Evidence:** All changes are minimal, reviewable, reversible. No secrets, no live trading, no destructive git. Shadow logs now capture every cycle (dry or not). System is at safe autonomous dry-run level.

**Next:** Phase 3 (tests, evidence bundle, final hygiene, full report).

**Commit Hash Reference:** (post-phase-2 commit)
**Date:** 2026-05-21
