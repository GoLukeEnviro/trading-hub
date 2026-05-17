# Freqtrade WebUI Überwachungsplan v1.0

## Status: v1.0-VALIDATED-AND-BINDING

## 1. Zielsetzung
Zentrales Monitoring aller Freqtrade-Instanzen über das FreqUI/WebUI.

## 2. Sicherheits-Status (STAND 2026-05-17)
- **Port Isolation**: Jedes Bot-API-Binding ist auf `127.0.0.1` begrenzt.
- **Docker Exposure**: Keine Exposition gegenüber `0.0.0.0`.
- **Dry-Run Enforcement**: Alle Bots laufen mit `dry_run: true`.

## 3. Monitoring-Infrastruktur
- **Caddy**: Agiert als Reverse Proxy auf dem Host-Netzwerk.
- **Tailscale**: Funneling erfolgt über verschlüsselte Tailscale-Endpoints.
- **Port 9092**: Reservierter Monitoring-Port (Tailscale-Intern).

## 4. Maintenance
- Änderungen an `config*.json` Dateien müssen das `127.0.0.1` API-Binding beibehalten.
- Neue Bots werden automatisch über den Wildcard-Config-Scanner erfasst.
