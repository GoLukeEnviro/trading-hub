# Operational State — Trading Hub

**Last updated:** 2026-05-25 09:45 UTC
**Update trigger:** max_open_trades-block v4.7 permanent structural fix + recovery-first hardening
**Author:** Hermes Agent

> This file is a validated snapshot, not live telemetry. Re-check container and cron
> state before making any operational decision.

---

## 1. Fleet / operating mode

- Trading Hub remains in **dry-run only** mode.
- `ai-hedge-fund-crypto` is the active signal core.
- Hermes remains the meta-orchestrator for audits, repairs, cron, and docs.
- The Freqtrade fleet remains the dry-run execution layer.
- `trading-guardian` permission hardening is active and should stay in the
  read-only safety posture described in the recent audit docs.
- RiskGuard is still a spec-only safety layer in the repo.
- ShadowLogger remains the passive evidence layer / spec reference.

### Documented bots

| Bot | Role | Current posture |
|-----|------|-----------------|
| FreqForge | Baseline dry-run bot | Active (max_open_trades=5) |
| Regime-Hybrid | Futures dry-run bot | Active (max_open_trades=5) |
| Momentum | Futures dry-run bot | Not deployed |
| FreqForge Canary | Spot dry-run clone | Active (max_open_trades=3) |
| FreqAI-Rebel | FreqAI dry-run bot | Active, permanent quarantine (max_open_trades=0) |
| MVS | Preserved strategy only | Not deployed |

### Repair note (2026-05-25 09:45 UTC)

- `orchestrator/scripts/system_optimizer.py` is now on v4.7 and executes a `recovery_preflight()` before any new block logic, so expired pauses are force-restored immediately when the recent 24h window is green.
- Consecutive-loss analysis is now bounded by `max(cursor, now-24h)`, which prevents old historical loss windows from re-triggering a fresh fleet block.
- Host-side optimizer state/config writes now use atomic replace + timestamped backups, and container config writes create `.bak-<timestamp>` snapshots before replacement.
- Verified live state after restart + pipeline + optimizer rerun: FreqForge `5`, Regime-Hybrid `5`, Canary `3`, Rebel `0` (intentional permanent quarantine); no immediate re-block occurred.

---

## 2. Repository and documentation state

- `main` is synced with `origin/main` at the time of this snapshot.
- The documentation layer was refreshed to reflect the current safety model and
  repo layout.
- `docs/context/` is the historical archive; it is not the canonical current
  state.
- `docs/state/current-operational-state.md` is the current snapshot file.
- Several strategy, research, and runtime artifacts remain intentionally local
  until they are classified, reviewed, or archived.

---

## 3. Local-only runtime artifacts

The following classes of files are expected to remain uncommitted:

- `.hermes/` local plans and cleanup notes
- `docs/context/git-cleanup-snapshots/`
- `docs/context/memory-migration-staging/`
- `events/` and `proposals/`
- `shared/hermes_signal.json`
- `freqtrade/shared/*state*.json`
- `freqtrade/shared/*.lock`
- `freqtrade/shared/fleet_correlation_matrix.json`
- `freqtrade/bots/*/user_data/primo_signal_state.json`
- `freqtrade/bots/*/user_data/signals/`
- `freqtrade/bots/regime-hybrid/config/research/automation/latest_*.json`
- `freqtrade/bots/regime-hybrid/config/research/automation/*_events.jsonl`
- `freqtrade/bots/regime-hybrid/config/research/automation/*_state.json`
- `orchestrator/config/cron_jobs_backup.json`
- `orchestrator/backups/`
- `**/*.bak`, `**/*.bak-*`, `*.backup.*`

---

## 4. Known risks before live trading

1. Live trading is still not approved.
2. Strategy or config changes require explicit review.
3. Runtime state can drift from the docs, so validate live before action.
4. Research and automation artifacts are intentionally split from production
   logic and may remain uncommitted until they are classified.
5. Historical reports in `docs/context/` should not be mistaken for current
   runtime telemetry.

---

## 5. Validation commands

```bash
git branch --show-current
git status -sb
git diff --name-status
git rev-parse HEAD
git rev-parse origin/main
git check-ignore -v shared/hermes_signal.json \
  freqtrade/shared/fleet_risk_state.json \
  freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json \
  docs/context/git-cleanup-snapshots/
python3 /home/hermes/projects/trading/freqtrade/shared/fleet_watcher.py --once --tail-lines 20
```

---

## 6. Cleanup report reference

See `docs/context/final-repo-cleanup-and-docs-refresh-20260521.md` for the
final cleanup classification and documentation alignment notes.
