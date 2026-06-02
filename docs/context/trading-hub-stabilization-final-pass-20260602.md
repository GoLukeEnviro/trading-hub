# Trading Hub Stabilization — Final Pass
## 2026-06-02 01:26 UTC

### Starting State

- Single-Orchestrator migration: committed in `8b30a80`
- Scheduler: recovered after jobs.json/config.yaml permission repair
- FleetRisk cursor: committed in `33a5354`, deployed but not runtime-validated
- 4 P2 error jobs: ghostbuster, daily-backup, portfolio-rebalancer, daily-signal-confidence-monitor
- 4/4 bots: running, dry_run=True

### Runtime Deploy Proof

| Script | Git vs Runtime | Owner | Mode |
|--------|---------------|-------|------|
| global_trigger_lock.sh | diff=0 | hermes:hermes | 755 |
| unified_signal_heartbeat.sh | diff=0 | hermes:hermes | 755 |
| trading_pipeline.py | diff=0 | hermes:hermes | 755 |
| system_optimizer.py | diff=0 | hermes:hermes | 755 |

**Deploy method:** `system_optimizer.py` was manually deployed to runtime after `deploy_cron_scripts.sh` failed on its diff/pipefail edge case. Fixed: runtime now matches Git for all 4 key scripts.

### Scheduler and Unified Heartbeat Status

| Job | last_run_at | last_status | Schedule |
|-----|------------|-------------|----------|
| unified-signal-heartbeat | 01:02:12 UTC | ok | */15 min |
| trading-pipeline | 01:10:49 UTC | ok | */10 min |
| system-optimizer | 01:11:56 UTC | ok | alle 5 min |
| critical-event-watchdog | 01:10:50 UTC | ok | */10 min |
| heartbeat-writer | 01:15:57 UTC | ok | */15 min |
| signal-heartbeat | — | paused | REPLACED |
| smart-heartbeat | — | paused | REPLACED |

### FleetRisk Cursor Status

```
Vor Fix:  analysis_cursor = 2026-05-30T13:56:21  (56h frozen)
Nach Fix: analysis_cursor = 2026-06-01T21:57:17  (48h forward)

Cursor bewegt um:
- 2026-06-01T21:57:17.056000 — aktuelle Position
- Cursor-Aktualisierung bestätigt im system-optimizer Log:
  "CLEANUP: cleared expired guard state: consec_loss_state.json (cursor advanced)"
- Alle 4 Bots lesbar: FreqForge + Canary + Regime-Hybrid via host_dbs,
  Rebel via docker exec fallback
```

### P2 Job Results

| Job | Before | Classification | Fix | After |
|-----|--------|---------------|-----|-------|
| ghostbuster | error (00:06) | **STALE STATUS** — script runs clean (exit 0) | Kein Fix nötig. Error status von Scheduler-Stall-Periode | Exit 0, nächster Tick 02:00 |
| daily-backup | error (01.06. 02:02) | **REAL_BUG** — shutil.rmtree crash auf Cross-UID Dateien | PermissionError-toleranter Cleanup in backup_rotation.py | Exit 0, nächster Tick 02:00 UTC |
| portfolio-rebalancer | error (01.06. 06:00) | **STALE STATUS** — script runs clean (exit 0). Läuft nur Montags. | Kein Fix nötig. DeprecationWarning (utcnow) vorhanden aber nicht crash-verursachend | Exit 0, nächster Tick 08.06. |
| daily-signal-confidence-monitor | error (01.06. 18:01) | **SELF-HEALED** nach Scheduler Recovery | Kein Fix nötig | last_status=ok, last_run=00:07 |

**Commits:**
- `33a5354` — FleetRisk cursor host_dbs fix
- `8dad433` — daily-backup PermissionError-tolerant cleanup

### Trading Safety

| Check | Status |
|-------|--------|
| Alle 4 Bots dry_run=True | ✅ |
| Kein Trading-Bot restartet | ✅ (20h+ uptime) |
| Keine Configs geändert | ✅ |
| Keine Strategien geändert | ✅ |
| Keine Credentials exponiert | ✅ |

### Changed Files

```
orchestrator/scripts/backup_rotation.py        |  9 +++++++--
orchestrator/scripts/system_optimizer.py       | 80 +++++++++++++-----------
2 files changed, 65 insertions(+), 24 deletions(-)
```

### Commits

```
8dad433 — fix(ops): make daily-backup PermissionError-tolerant during stale cleanup
33a5354 — fix(orchestrator): resolve FleetRisk closed-trade cursor lookup
8b30a80 — fix(orchestrator): unify signal heartbeat and serialize trigger execution
```

### Remaining Issues

| Issue | Priority | Note |
|-------|----------|------|
| ghostbuster error status | P3 | Clears on next tick (02:00), script runs clean |
| portfolio-rebalancer error status | P3 | Nächster Tick 08.06., script runs clean |
| daily-backup previous error status | P2 | Fixed in 8dad433, clears on next tick (02:00) |
| portfolio-rebalancer utcnow deprecation | P4 | Cosmetic, no crash |
| trading-guardian undokumentiert | P3 | Separate investigation needed |
| Cron-Job-Konsolidierung 38 → 15-20 | P3 | Zukunftsthema |

### Final Classification

```
SYSTEM_GREEN_DRYRUN_READY

Kriterien:
- Single-Orchestrator läuft automatisch ✓
- Scheduler tickt zuverlässig ✓
- FleetRisk Cursor aktiv ✓
- Canonical/Latest synchron ✓
- 4/4 Bots dry_run=True ✓
- 0 ungelöste Blockierer ✓
- 3 error-Jobs: alle STALE oder gefixt, script-seitig OK ✓
```

### Next Step

Deine Wahl:
1. **Nichts tun** — System läuft stabil, nächster Error-Check morgen früh (06:00 daily-heartbeat, 02:00 backup)
2. **Cron-Konsolidierung** — 38 Jobs auf 15-20 reduzieren
3. **trading-guardian klären** — Container dokumentieren oder dekommissionieren
4. **deploy_cron_scripts.sh pipefail bug fixen** — diff/wc-l Kombination bricht ab