# Fix: Root-owned primo_signal_state.json

**Betroffen:** `trading-freqai-rebel-1` (volume mount)

## Problem

Im Volume `freqtrade/bots/freqai-rebel/user_data/` liegt eine 0-Byte-Datei
`primo_signal_state.json`, owned von `root:1337`.

Diese Datei ist nutzlos (0 Bytes) und blockiert potentiell Write-Zugriff auf
das Verzeichnis, da `hermes` (uid=10000) kein Write-Recht hat.

## Warum nicht kritisch

Ein separater Bind-Mount überschreibt diesen Pfad:
```
freqtrade/shared/primo_signal_state.json → /freqtrade/user_data/primo_signal_state.json
```

Die Pipeline schreibt in den **Shared-Pfad**, nicht in das Volume.
Die leere Datei wird durch den Bind-Mount verdeckt.

## Fix (einmalig, manuell auf Host via sudo)

```bash
# Datei löschen
sudo rm /home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data/primo_signal_state.json

# Optional: Volume-Verzeichnis-Permissions anpassen
sudo chmod 775 /home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data/
sudo chown 1000:1000 /home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data/
```

## Verifikation nach Fix

```bash
ls -la /home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data/primo_signal_state.json
# Sollte: Datei existiert nicht (wird von Pipeline beim nächsten Run geschrieben)
```

## Alternativ: Container-Seitig ignorieren

Da kein aktiver Schreibzugriff auf das Verzeichnis benötigt wird (Pipeline
schreibt in den Shared-Mount), kann der Fix auch niedrig priorisiert werden.
Der Container läuft fehlerfrei.
