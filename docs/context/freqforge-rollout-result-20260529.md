# Freqforge Shared-Group Rollout Result
**Datum:** 2026-05-29
**Ergebnis:** STABLE

## Geaenderter Pfad
- /home/hermes/projects/trading/freqforge/user_data
- Pre-State: hermes:hermes (1337:1337)  
- Post-State: hermes:ftuser (1337:10000) + setgid 2775

## Bereits konvertiert (keine Aenderung noetig)
- /home/hermes/projects/trading/freqtrade/shared - hermes:ftuser, 2775
- /home/hermes/projects/trading/freqtrade/logs - hermes:ftuser, 2775

## Nicht angefasst
- /home/hermes/projects/trading/freqforge/config - rw=false (read-only Mount)

## Verifikation
| Check | Ergebnis |
|-------|----------|
| Container laeuft | Up, RUNNING |
| PermissionError | KEINE |
| SQLite-Fehler | KEINE |
| dry_run | True |
| Runtime-File Inheritance | 10000:ftuser 664 |
| Root-Files im Repo | ZERO |
| Guardian | Clean, kein perm_drift |

## Bewiesener Mechanismus
SQLite-Files werden als 10000:ftuser geschrieben.
Container (UID 10000) erzeugt Dateien, setgid vererbt Gruppe ftuser (GID 10000).
Hermes (UID 1337, in Gruppe ftuser) hat group-rw Zugriff.

## Modell
- Host-Gruppe: ftuser (GID 10000)
- hermes in ftuser Gruppe
- Runtime-Dirs: chown 1337:10000, chmod 2775 (setgid)
- Runtime-Files: chmod g+rw (664)

## Naechster Kandidat
freqai-rebel - braucht vorherigen Audit wegen Docker-Volume-Verhalten.
