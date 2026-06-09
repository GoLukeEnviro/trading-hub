# Hermes Gateway / Desktop App / TUI Debug Runbook

**Stand:** 2026-06-08 (Session 019ea68f-e4eb-7a33-aada-ab25898a1a60)
**Symptom:** "hermes desktop app gateway funktioniert schon wieder nicht" (recurring)

## Schnell-Diagnose (immer zuerst, < 60s)

```bash
# 1. Logs (das eine Kommando das fast alles zeigt)
docker logs hermes-green --since 30m 2>&1 | grep -iE 'gateway|error|traceback|fail|halt|slash_worker|tui_gateway' | tail -80

# 2. s6 Profile-Gateways (Crash-Loops erkennen an "up since" Sekunden)
for svc in default orchestrator trading mira weatherbot weather; do
  echo "=== gateway-$svc ==="; s6-svstat /run/service/gateway-$svc 2>/dev/null || echo "NO SVSTAT";
done

# 3. Patch-Mechanismus prüfen (warum Patches oft nicht greifen)
docker exec hermes-green cat /opt/hermes/docker/main-wrapper.sh | grep -A10 -i -E 'patch|cp |overlay'

# 4. MCP / claudio-Pfade (häufigster "schon wieder"-Killer durch UID-Mix)
docker exec hermes-green sh -c 'ls -ld /home/claudio/hermes-pr7/skills 2>/dev/null || echo "claudio paths invisible inside container"'
```

## Root Cause (in diesem Fall)
Die `config.toml` (und Profile-Configs) referenzieren `/home/claudio/hermes-pr7/skills` + MCP-FS-Pfade für alle Skills.

Im `hermes-green` Container (uid hermes/10000 oder root) sind `/home/claudio/*` **nicht gemountet und nicht sichtbar**.

→ Jeder neue `tui_gateway.slash_worker` (TUI/Desktop-Session) oder Profile-Gateway, der beim `HermesCLI(...)` Init die Skills/MCPs lädt, scheitert oder hängt.

Das erklärt "schon wieder" nach Restarts, neuen Sessions, Config-Reloads oder wenn der Container neu gebaut wurde.

Zusätzlich:
- `main-wrapper.sh` (der echte Entrypoint) macht **kein** automatisches `cp` aus `/opt/hermes/patches/` für `tui_gateway/` oder `hermes_cli/`. Das patches/-Dir enthält (Stand jetzt) nur .md-Audits.
- s6 `gateway-*` laufen als supervise (seit Container-Start), aktive Worker-PIDs sind oft nur die Log-Forwarder + gelegentliche slash_worker.
- "Gateway is not running" aus `hermes gateway status` ist normal, solange nur die s6-Profile + Dashboard laufen (kein separates messaging-gateway systemd service).

## Sofort-Fix (Quick-Win, was hier geholfen hat)
1. Config bereinigen (nur erreichbare Pfade):
   - `/home/hermes/.grok/config.toml` (und ggf. Profile unter `/opt/data/profiles/*/`) : claudio-Pfade aus `[mcp_servers.filesystem]` und `[skills].paths` entfernen/kommentieren. Nur `/home/hermes` + lokale .grok/skills lassen.
2. Stale Worker killen (damit neue Session sauberen Worker mit neuer Config bekommt):
   ```bash
   docker exec hermes-green pkill -f 'tui_gateway.slash_worker' || true
   ```
3. Optional: Betroffenen s6 Profile gezielt restarten (nicht ganzen Container):
   ```bash
   docker exec hermes-green s6-svc -r /run/service/gateway-default   # oder orchestrator etc.
   ```
4. Letzter Ausweg: `docker restart hermes-green` (s6 bringt alles zurück, Sessions im RAM weg).

## Verification (10-Punkte, immer durchlaufen)
1. `docker ps | grep hermes-green` — healthy.
2. `curl -s http://127.0.0.1:8083/ | grep -o 'Hermes Agent - Dashboard'` — Web-UI antwortet (embedded Chat auch).
3. `docker exec ... hermes gateway status` + `gateway list`.
4. s6-svstat auf `/run/service/gateway-*` — "up", keine Sekunden-Up-times (kein Loop).
5. Logs sauber (keine neuen Restarts/Tracebacks in den letzten Minuten außer intentional).
6. Neuer TUI/Desktop-Session Test: `/session-info`, einfacher Prompt, `/status` — neuer slash_worker Prozess erscheint, JSON-Protokoll funktioniert (kein immediate ok:false).
7. Native `hermes desktop` / gui (falls genutzt) startet und chat antwortet.
8. Port 8083 listening + erreichbar (`curl -sf http://127.0.0.1:8083/api/status`). ~~8642~~ deprecated.
9. Keine Permission/Claudio-Pfad-Fehler mehr beim MCP/Skills-Load in neuen Workern.
10. Dashboard-Prozess mem nicht explodierend.

## Artefakte / wo was liegt
- Container: `hermes-green` (image nousresearch/hermes-agent:latest), CMD = gateway run & dashboard, s6 supervised profile gateways unter `/run/service/gateway-*`, Logs in `/opt/data/logs/gateways/*/current` (bind `/opt/hermes/config`).
- tui_gateway Worker: `/opt/hermes/tui_gateway/slash_worker.py` (stdio JSON {id,command} → HermesCLI.process_command → {id,ok,output|error}).
- Transport/Attach: `tui_gateway/{transport.py,ws.py,server.py}` (Stdio oder WS, ContextVar für current transport, Peer-Gone-Handling).
- Wrapper (wichtig!): `/opt/hermes/docker/main-wrapper.sh` (env, venv, drop to hermes user, kein Patch-Auto-Apply für Core-Python).
- Host Config (für lokalen TUI/MCP): `/home/hermes/.grok/config.toml`.
- Dev-Source (für echte Bugfixes): typischerweise `/home/claudio/hermes-pr7/` (nicht hier editieren, upstream + Image-Rebuild).

## Wann was tun
- Nur "läuft wieder": pkill + config bereinigen + targeted s6-svc -r.
- Echter Bug in slash_worker / transport / gateway init: Source in claudio/hermes-pr7 anpassen, dann Image bauen oder Volume-Mount + Wrapper erweitern (damit Patches greifen).
- s6-Profile hängen im Loop: Logs + svstat, dann gezielter Restart oder Fix im Profile-Setup (Messaging, Cron, Memory etc.).
- MCP/Skills generell kaputt: Config-Pfade prüfen + Sichtbarkeit im Container (uid-Mapping, Volumes).

Nächstes Mal "schon wieder" → diese 4 Befehle + Config-Check. 30 Sekunden bis Ursache.

(Erstellt aus Session 019ea68f... nach erfolgreicher Diagnose + Fix der claudio-Pfad-Problematik.)
