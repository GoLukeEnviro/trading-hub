# Branch Full Audit — 2026-06-07

**Auditor:** Hermes Orchestrator (auto)  
**Main HEAD:** `23b3d32872608dc3ad7e4c22b9585eb395267bcd`  
**Repository:** `/home/hermes/projects/trading/` (GoLukeEnviro/trading-hub)

---

## Executive Summary

### ⚠️ KRITISCHER FUND: Beide Branches sind VOLLSTÄNDIG in main enthalten

| Branch | HEAD SHA | Letzter Commit | Main Commits voraus | Unique Commits | Status |
|--------|----------|----------------|--------------------:|---------------:|--------|
| `chore/final-docs-and-worktree-cleanup` | `3d560f5` | 2026-05-23 17:22 UTC | **85** | **0** | ✅ SAFE TO DELETE |
| `chore/permission-hardening-guardian` | `ee075a1` | 2026-05-21 11:37 UTC | **97** | **0** | ✅ SAFE TO DELETE |

**Beide Branches sind ancestors of main** — `git merge-base --is-ancestor` bestätigt Exit-Code 0 für beide.  
Es existiert **kein einziges Commit** in diesen Branches das nicht auch auf main erreichbar ist.  
Alle Branch-Inhalte sind durch spätere main-Commits (inkl. PR #3, #6) überholt worden.

### Was ist sicher zu löschen?
**BEIDE Branches.** Kein Datenverlust möglich — jeder Commit ist auf main.

### Was muss gemergt werden?
**NICHTS.** Ein Merge würde entweder No-Op sein oder main RÜCKWÄRTS setzen.

---

## Branch A: `chore/final-docs-and-worktree-cleanup`

### Metadaten
- **HEAD:** `3d560f5d7f9e453c8cfee82fc3eb9ee2434d1d1f`
- **Letzter Commit:** 2026-05-23 17:22:11 UTC — `feat: Autonomous Trading System v4.2 finalisiert`
- **Diff-Größe:** 175 gelöscht, 36 geändert, 3 neu (vs. aktueller main)
- **Achtung:** Diese Zahlen zeigen was der Branch **NICHT hat** gegenüber main, nicht was er zusätzlich bietet.

### Neue Dateien (nicht auf main, weil Branch älter ist)

| Datei | Zeilen | Funktion | Empfehlung |
|-------|-------:|----------|------------|
| `docs/context/freqforge-shadow-evaluator-v0-1-decisions.jsonl` | 6 | Shadow evaluator decisions log | VERALTET — main hat aktuellere Version |
| `orchestrator/reports/fleet_health_latest.json` | 59 | Fleet health report snapshot | VERALTET — main hat aktuellere Version |
| `orchestrator/reports/fleet_health_latest.md` | 31 | Fleet health report markdown | VERALTET — main hat aktuellere Version |

### Geänderte Dateien (36 — alle VERALTET gegenüber main)

Wichtigste Änderungen (Branch-Version ist ÄLTER als main):

| Datei | Branch-Datum | Main-Datum | Bewertung |
|-------|-------------|-----------|-----------|
| `AGENTS.md` | 2026-05-21 | 2026-06-06 | ⚠️ VERALTET — main 16 Tage neuer |
| `README.md` | 2026-05-21 | 2026-06-03 | ⚠️ VERALTET |
| `docs/state/current-operational-state.md` | 2026-05-21 | 2026-06-05 | ⚠️ VERALTET |
| `freqforge/user_data/strategies/FreqForge_Override.py` | 2026-05-21 | 2026-06-05 | ⚠️ VERALTET — Strategie geändert auf main |
| `freqtrade/bots/regime-hybrid/user_data/strategies/RegimeSwitchingHybrid_v7_v04_Integration.py` | 2026-05-23 | 2026-06-01 | ⚠️ VERALTET — v04 Integration geändert |
| `freqtrade/shared/fleet_risk_manager.py` | 2026-05-21 | 2026-06-05 | ⚠️ VERALTET |
| `orchestrator/scripts/trading_pipeline.py` | 2026-05-23 | 2026-06-01 | ⚠️ VERALTET |
| `orchestrator/scripts/fleet_healthcheck.py` | 2026-05-12 | 2026-06-06 | ⚠️ VERALTET — 25 Tage älter |
| `orchestrator/scripts/multicycle_validator.py` | 2026-05-12 | 2026-06-05 | ⚠️ VERALTET |
| `orchestrator/scripts/system_optimizer.py` | 2026-05-12 | 2026-06-06 | ⚠️ VERALTET — massive diffs |
| `orchestrator/scripts/drawdown_guard.py` | 2026-05-12 | 2026-05-28 | ⚠️ VERALTET |

### Gelöschte Dateien (175 — existieren auf Branch, wurden auf main gelöscht)

Branch enthält noch Dateien die auf main bereinigt wurden:
- **~90 docs/context/** Berichte (historiesche Incident-Reports, Observations, Permission-Fixes)
- **~20 orchestrator/scripts/** (canary_position_monitor, config_diff_detector, fleet_auto_repair, ghostbuster, etc.)
- **FreqAI-rebel** Strategien, Dockerfiles, Caddyfile, dashboard.py
- **docker-compose.yml.bak.volumes**, **SHARED_CONSTANTS.py**, etc.

**Alle diese Löschungen waren intentional — Cleanup-PRs auf main.**

---

## Branch B: `chore/permission-hardening-guardian`

### Metadaten
- **HEAD:** `ee075a1aaefdbefc5e73b09e4c08a9d2d04359f3`
- **Letzter Commit:** 2026-05-21 11:37:48 UTC — `chore: harden trading permission guard and signal runtime writes`
- **Diff-Größe:** 256 gelöscht, 25 geändert, 10 neu, 1 renamed (vs. aktueller main)
- **Noch älter als Branch A** — 2 Tage weniger main-History.

### Neue Dateien (nicht auf main, weil Branch älter ist)

| Datei | Zeilen | Funktion | Empfehlung |
|-------|-------:|----------|------------|
| `docs/context/freqforge-shadow-evaluator-v0-1-decisions.jsonl` | 6 | Shadow evaluator decisions | VERALTET — identisch zu Branch A |
| `freqtrade/bots/momentum/user_data/primo_signal_state.json` | 220 | Signal state für momentum bot | ⚠️ UNKLAR — existiert NICHT auf main |
| `freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json` | 220 | Signal state für regime-hybrid bot | ⚠️ UNKLAR — existiert NICHT auf main |
| `freqtrade/bots/rsi/user_data/primo_signal_state.json` | 220 | Signal state für RSI bot | ⚠️ UNKLAR — existiert NICHT auf main |
| `freqtrade/shared/primo_signal_state.json` | 220 | Shared signal state | ⚠️ UNKLAR — existiert NICHT auf main |
| `freqtrade/bots/regime-hybrid/.../RegimeSwitchingHybrid_v2.py.bak_20260503_022741` | 153 | Backup alter Strategie | VERALTET — Backup-Datei |
| `freqtrade/bots/regime-hybrid/.../RegimeSwitchingHybrid_v6_1_Fett.py.bak_v04_integration` | 286 | Backup alter Strategie | VERALTET — Backup-Datei |
| `freqtrade/bots/regime-hybrid/.../RegimeSwitchingHybrid_v6_Stable.json.bak-shadow-fix` | 33 | Backup alter Config | VERALTET — Backup-Datei |
| `orchestrator/reports/fleet_health_latest.json` | 59 | Fleet health report | VERALTET |
| `orchestrator/reports/fleet_health_latest.md` | 31 | Fleet health report | VERALTET |

### ⚠️ UNKLAR: primo_signal_state.json Dateien

Branch B enthält 4 `primo_signal_state.json` Dateien die **NICHT auf main** existieren.
Da Branch B ein ancestor of main ist, wurden diese Dateien entweder:
1. Auf main absichtlich nicht hinzugefügt (weil primo_signal.py den State dynamisch erzeugt)
2. Oder durch Cleanup-PRs entfernt

**Prüfung:** primo_signal.py auf main erzeugt State zur Laufzeit → diese JSONs sind **Runtime-Artefakte**, kein Code-Verlust.

### Geänderte Dateien (25 — alle VERALTET gegenüber main)

Zusätzlich zu Branch A noch:
- `SOUL.md` — Branch-Version von 2026-05-16, main von 2026-06-06
- `freqforge-canary/user_data/strategies/FreqForge_Override.py` — ÄLTER als main
- `freqtrade/bots/momentum/user_data/strategies/momentum_bg15_v1.py` — ÄLTER
- `freqtrade/bots/regime-hybrid/user_data/strategies/RegimeSwitchingHybrid_v6_Stable.py` — ÄLTER
- `freqtrade/shared/primo_signal.py` — ÄLTER

### Renamed Dateien
- `optimize_loop.py.disabled` → `optimize_loop.py` (R096, 96% identisch) — auf main bleibt sie `.disabled`

### Gelöschte Dateien (256 — noch mehr als Branch A)

Branch B enthält zusätzlich noch:
- **~30 weitere docs/context/** Berichte (dream-mode, cron-recovery, mem0-cloud, etc.)
- **~15 weitere orchestrator/scripts/** (bitget_mcp_server, mcp_cli, signal_bridge, smart_heartbeat, etc.)
- **freqtrade/shared/README.md**, **run_fleet_watcher.sh**, **update_fleet_equity.py**
- **docs/GAP_ANALYSE.md**, **docs/bridge-plan-v0.1.md**
- **tools/riskguard/riskguard.py**

---

## Strategie-Inventar Gesamt

### Aktive Bots (dry-run, via docker-compose.fleet.yml)

| Bot | Container | Strategie (CLI) | Config-Strategie | Strategie-Datei | Zeilen |
|-----|-----------|-----------------|-------------------|-----------------|-------:|
| RSI | freqtrade-rsi | SimpleRSIOnly_v1 | SimpleRSIOnly_v1 | `freqtrade/bots/rsi/user_data/strategies/simple_rsi_only_v1.py` | 120 |
| Momentum | freqtrade-momentum | MomentumBG15_v1 | MomentumBG15_v1 | `freqtrade/bots/momentum/user_data/strategies/momentum_bg15_v1.py` | 294 |
| Regime-Hybrid | freqtrade-regime-hybrid | RegimeSwitchingHybrid_v7_v04_Integration | (im CLI arg) | `freqtrade/bots/regime-hybrid/user_data/strategies/RegimeSwitchingHybrid_v7_v04_Integration.py` | 464 |
| FreqForge Canary | freqtrade-freqforge-canary | FreqForge_Override | (im CLI arg) | `freqforge-canary/user_data/strategies/FreqForge_Override.py` | 398 |

### Inaktive/Research-Strategien (nicht im docker-compose fleet)

| Strategie | Pfad | Zeilen | Letzte Änderung | Status |
|-----------|------|-------:|-----------------|--------|
| FreqForge_Override (prod) | `freqforge/user_data/strategies/FreqForge_Override.py` | 510 | 2026-06-05 | Inaktiv (config gelöscht auf Branch A/B) |
| FreqForge_v2 | `freqforge/user_data/strategies/FreqForge_v2.py` | ? | Research | Inaktiv |
| PullbackEMA_v1 | `freqforge/user_data/strategies/PullbackEMA_v1.py` | ? | Research | Inaktiv |
| RegimeSwitchingHybrid_v6_Stable | `freqtrade/bots/regime-hybrid/.../RegimeSwitchingHybrid_v6_Stable.py` | 232 | 2026-05-23 | Backup v6 |
| RegimeSwitchingHybrid_v8_* (3 var) | `freqtrade/bots/regime-hybrid/.../` | ~200 | Research | Inaktiv |
| RegimeSwitchingHybrid_v9_1_Sentient | `freqtrade/bots/regime-hybrid/.../` | ? | Research | Inaktiv |
| FOMO_Phase3_v0 | `freqtrade/bots/fomo-phase3/.../` | ? | Research | Inaktiv |
| MinimalViableStrategy_v1 | `freqtrade/bots/mvs/.../` | ? | Research | Inaktiv |
| RebelLiquidation | `freqtrade/bots/freqai-rebel/.../` | ? | Research | Inaktiv |
| MomentumBG15_v2/v3/v3_1 | `freqtrade/bots/momentum/.../` | ? | Research | Inaktiv |

### In Branches vorhanden?

| Strategie | Branch A | Branch B | Identisch zu main? |
|-----------|:--------:|:--------:|:-------------------:|
| RegimeSwitchingHybrid_v7_v04_Integration | ✅ Geändert | ✅ Geändert | ❌ NEIN — beide ÄLTER |
| FreqForge_Override (freqforge) | ✅ Geändert | ✅ Geändert | ❌ NEIN — beide ÄLTER |
| RegimeSwitchingHybrid_v6_Stable | — | ✅ Geändert | ❌ NEIN — Branch B ÄLTER |
| momentum_bg15_v1 | — | ✅ Geändert | ❌ NEIN — Branch B ÄLTER |
| FreqForge_Override (canary) | — | ✅ Geändert | ❌ NEIN — Branch B ÄLTER |
| primo_signal.py | — | ✅ Geändert | ❌ NEIN — Branch B ÄLTER |

---

## Self-Improvement-System Status

### Dateien auf main vorhanden

| Datei | Pfad | Zeilen | Letzte Änderung | Aktiv? |
|-------|------|-------:|-----------------|--------|
| self_optimizer.py | `freqtrade/bots/regime-hybrid/config/research/automation/self_optimizer.py` | ~405 | 2026-05-28 | ⚠️ Teilweise — Branch B DELETET diese |
| fleet_monitor.py | `freqtrade/bots/regime-hybrid/config/research/automation/fleet_monitor.py` | ~405 | 2026-05-28 | ⚠️ Branch B DELETET diese |
| fleet_watcher.py | `freqtrade/shared/fleet_watcher.py` | 1,421 | 2026-06-05 | ✅ Auf main — Branch A/B DELETEN |
| fleetguard_v1.py | `freqtrade/shared/fleetguard_v1.py` | ~6 | 2026-05-28 | ✅ Auf main |
| fleet_risk_manager.py | `freqtrade/shared/fleet_risk_manager.py` | ~500 | 2026-06-05 | ✅ Auf main |

### Self-Improvement Dirs (lokal, nicht im git tracking)
- `/home/hermes/projects/trading/self_improvement/` — enthält `shared/` subdir
- `/home/hermes/projects/trading/var/fleet_monitor/` — runtime data
- Backtest-Artefakte: `freqforge*/user_data/backtest_results/self_improvement/` — lokal, nicht in git

### Cron-Job Status
- **System crontab:** Kein crontab binary auf diesem Runtime
- **Hermes cron:** 16 no_agent Jobs für Self-Improvement (Bots A-D) — konfiguriert über Hermes cronjob
- **Scripts die self_improvement referenzieren:** KEINE gefunden in `orchestrator/` (grep leer)

### Branch-Auswirkungen auf Self-Improvement
- **Branch B** löscht `self_optimizer.py` und `fleet_monitor.py` aus `config/research/automation/`
- **Branch B** löscht `fleet_watcher.py` aus `freqtrade/shared/`
- **Aber:** Branch B ist ancestor → main HAT diese Dateien bereits behalten. Keine Gefahr.

### Lücken
- Self-Improvement Cron-Jobs referenzieren Scripts die in `self_improvement/` liegen → OK, nicht in git
- `fleet_watcher.py` wird auf main aktiv verwendet → OK, nicht gelöscht auf main
- `self_optimizer.py` auf main hat 20-Zeilen-Änderung gegenüber Branch A → OK

---

## Konflikte zwischen Branches

### Dateien die in BEIDEN Branches geändert wurden (vs. main)

**85 Dateien** unterscheiden sich zwischen Branch A und Branch B. Das sind hauptsächlich:
- Dateien die auf Branch B noch existieren aber auf Branch A bereits gelöscht wurden (weil A neuer ist)
- Docs die auf Branch A bereinigt wurden, auf Branch B noch vorhanden sind

### Keine Merge-Konflikte möglich
Da beide Branches **ancestors of main** sind, kann es keine Merge-Konflikte geben.
Ein Merge wäre ein No-Op (git würde erkennen dass alles schon drin ist).

### Dateien auf main die durch neuere Commits ÜBERSCHRIEBEN wurden

**ALLE** geänderten Dateien in beiden Branches sind auf main neuer:
- Jede einzelne der 36 (A) / 25 (B) geänderten Dateien hat einen **neueren Commit auf main**
- Die Branch-Versionen sind systematisch älter (2-25 Tage)

---

## Empfohlene Merge-Reihenfolge

### ❌ KEIN MERGE NOTWENDIG

Beide Branches sind vollständig in main enthalten. Ein Merge würde:
1. `git merge` → "Already up to date" (No-Op)
2. Oder wenn force-merged → main RÜCKWÄRTS setzen

### ✅ Empfohlene Aktion

```
# Beide Branches löschen (remote + local):
git push origin --delete chore/final-docs-and-worktree-cleanup
git push origin --delete chore/permission-hardening-guardian
git branch -d chore/final-docs-and-worktree-cleanup 2>/dev/null
git branch -d chore/permission-hardening-guardian 2>/dev/null
```

**Begründung:**
- 0 unique Commits in beiden Branches
- Main ist 85/97 Commits voraus
- Alle Branch-Inhalte sind durch main überholt
- Cleanup-Artefakte (gelöschte docs, scripts) sind auf main bereits bereinigt

---

## Sicher zu löschende Branches

| Branch | Letzte Aktivität | Main-Vorsprung | Risiko | Aktion |
|--------|-----------------|---------------|--------|--------|
| `chore/final-docs-and-worktree-cleanup` | 2026-05-23 | 85 Commits | KEINS | **LÖSCHEN** |
| `chore/permission-hardening-guardian` | 2026-05-21 | 97 Commits | KEINS | **LÖSCHEN** |

---

## Rohdaten

Alle Audit-Rohdaten liegen unter:
- `/tmp/branch_audit/chore_final_docs/` — Branch A Diffs, neue Dateien, Stats
- `/tmp/branch_audit/chore_permission/` — Branch B Diffs, neue Dateien, Stats
- `/tmp/branch_audit/main_py_inventory.txt` — 709 Python-Dateien auf main
- `/tmp/branch_audit/main_sh_inventory.txt` — 51 Shell-Dateien auf main
- `/tmp/branch_audit/main_json_inventory.txt` — 548 JSON-Dateien auf main

---

*Audit abgeschlossen: 2026-06-07 | NUR LESEN — keine Änderungen am Code oder Trading-System*
