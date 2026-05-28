# Status-Quo Freeze: Vor freqforge Rollout
**Datum:** 2026-05-29
**Status:** STABLE — Frequenzforge-Rollout bereit nach Freigabe

## Git-State
- HEAD: 974901a (chore: untrack runtime state files)
- Unstaged: external_cron_guardian.sh, git_guard.sh (Session-Änderungen)
- Untracked: 4 docs/context/*.md, 1 .pre-cleanup Backup

## Container-Status
| Container | Uptime | Status |
|-----------|--------|--------|
| freqforge-canary | Up 3 days | STABLE |
| regime-hybrid | Up 2 days | STABLE |
| freqforge | Up 3 days | STABLE (noch kein Shared-Group) |

## Shared-Group Modell
- GID 10000 (ftuser) auf Host erstellt
- hermes (UID 1337) in Gruppe ftuser
- Canary + regime-hybrid: chown 1337:10000 + setgid 2775
- freqforge: noch nicht umgestellt (nächster Schritt)

## Guardian
- Repair-Loops (Section 5) entfernt
- Backup: external_cron_guardian.sh.pre-cleanup
- Monitoring aktiv, kein perm_drift

## Ownership
- docs/context/: alle hermes:hermes
- Keine root-owned Dateien im Trading-Repo
- /opt/hermes/docs/context/: root:root (korrekt)

## Rollback-Referenz (freqforge Pre-State)
Vor freqforge-Rollout: genaue Ownership mit stat -c '%U:%G %a %n' erfassen.
NICHT chown -R 10000:10000 als Rollback — das bricht das Shared-Group-Modell.

## Nächster Schritt
- [ ] User-Freigabe für freqforge-Rollout
- [ ] freqforge rw-Mount-Pfade identifizieren
- [ ] stat-Snapshot der Pfade erstellen
- [ ] Shared-Group anwenden (1337:10000 + 2775)
- [ ] Container-Neustart + Log-Verifikation
