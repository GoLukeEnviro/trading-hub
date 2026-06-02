# Trading Permission Rollout — Final Report

**Datum:** 2026-05-29
**Git HEAD:** e958879
**Status:** ROLLOUT ABGESCHLOSSEN

---

## Shared-Group Permission Model — Angewendet und Stabil

| Service | Image | UID | Rollout | Status |
|---------|-------|-----|---------|--------|
| freqforge-canary | freqtrade-hermes10000:stable | 10000 | Shared-Group (1337:10000, 2775) | STABLE (seit 2026-05-28 23:50) |
| regime-hybrid | freqtrade-hermes10000:stable | 10000 | Shared-Group (1337:10000, 2775) | STABLE (seit 2026-05-29 00:01) |
| freqforge | freqtrade-hermes10000:stable | 10000 | Shared-Group (1337:10000, 2775) | STABLE (seit 2026-05-29 01:xx) |

**Mechanismus:** Host-User hermes (UID 1337) + Container-User ftuser (UID 10000) teilen Gruppe ftuser (GID 10000).
Runtime-Verzeichnisse: `chown -R 1337:10000` + setgid 2775 auf Dirs + g+rw auf Files.
Neue Dateien erben GID 10000 via setgid.

---

## Kein Rollout Notwendig

| Service | Image | UID | Grund |
|---------|-------|-----|-------|
| freqai-rebel | freqtradeorg/freqtrade:2026.3_freqai | 1000 | Docker Named Volume (kein Bind-Mount-Konflikt), isoliert, UID 1000 = ftuser |
| freqtrade-webserver | freqtradeorg/freqtrade:stable | 1000 | Isoliertes Network, separate Pfade, UID 1000 = ftuser, kein Shared-Access |

---

## Aktive Architektur

### UID-Modelle
- **UID 10000 Bots** (custom Image): freqforge-canary, regime-hybrid, freqforge
  - Gemeinsame Gruppe GID 10000 (ftuser) + setgid 2775
  - Host-User hermes (1337) und Container-User (10000) koexistieren via Group-Permissions
- **UID 1000 Bots** (Standard-Image): freqai-rebel, freqtrade-webserver
  - claudio (UID 1000) mapped direkt auf ftuser
  - Kein Shared-Access-Konflikt, isolierte Paths/Volumes

### Guardian
- **Aktiver Mechanismus:** systemd Timer `trading-cron-guardian.timer` (alle 5 Min)
- **Service:** `trading-cron-guardian.service`
- **Script:** `/home/hermes/projects/trading/orchestrator/scripts/external_cron_guardian.sh`
- **Section 5 (Permission Drift Repair):** DEAKTIVIERT — nicht mehr noetig dank Shared-Group-Modell
- **Monitoring/Alerting:** Aktiv (perm_drift Zaehler, Container-Health, Signal-State)

### Ownership-Regel
- Repo-Dateien unter `/home/hermes/projects/trading/`: **hermes:hermes**
- System-Pfade (`/opt/`, `/etc/`, `/root/`): **root:root**
- Runtime-Dirs der UID-10000-Bots: **hermes:ftuser (1337:10000)** mit setgid

---

## Cleanup-Kandidaten

### 1. Stale `trading-guardian` Docker-Container
- **Was:** Alter Docker-Container `trading-guardian` (nicht mehr aktiv genutzt)
- **Aktiver Guardian:** systemd Timer, nicht dieser Container
- **Risiko:** Niedrig — Container ist inaktiv/obsolet
- **Aktion:** Stoppen + entfernen (nach Snapshot/Verify)

### 2. `/home/hermes/freqai-rebel/` root:root Leiche
- **Was:** Leerers Legacy-Verzeichnis, root:root owned
- **Risiko:** Niedrig — wird nicht genutzt, freqai-rebel laeuft via Docker Named Volume
- **Aktion:** Loeschen nach Verify dass wirklich leer

### 3. Optional: Webserver Config Ownership
- **Was:** `freqtrade.json` in Docker Volume ist root:root 644
- **Symptom:** Intermittent PermissionError in Logs bei Restart (self-healing via restart policy)
- **Risiko:** Niedrig — self-healing, aber unsauber
- **Aktion:** Optional `chown claudio:claudio` — Low Priority

---

## Risiken und Rollback

### Rollback Shared-Group (NICHT empfohlen)
- **Nicht** `chown -R 10000:10000` — wuerde Shared-Group-Modell brechen
- Stattdessen: Pre-Rollout-Zustand aus `stable-state-before-freqforge-rollout-20260529.md` extrahieren
- Rollback nur bei echten Problemen, nicht praeventiv

### Bekannte Einschraenkungen
- `git_guard.sh` Rewrite (85 -> 22 Zeilen) liegt unstaged — braucht separaten Review
- `external_cron_guardian.sh.pre-cleanup` Backup liegt untracked — kein Repo-Material

---

## Empfohlene Cleanup-Reihenfolge

1. Stale `trading-guardian` Container stoppen/entfernen
2. `/home/hermes/freqai-rebel/` Leiche entfernen
3. Optional: Webserver config ownership anpassen

Jeder Schritt einzeln freigeben.

---

## Verifikationsergebnisse (2026-05-29)

- Container: Alle 5 aktiv und stabil
- Git: HEAD e958879, erwartet: git_guard.sh (modified), .pre-cleanup (untracked)
- Root-Files im Repo: 0
- Guardian Timer: `trading-cron-guardian.timer` active, enabled, letzter Run SUCCESS
