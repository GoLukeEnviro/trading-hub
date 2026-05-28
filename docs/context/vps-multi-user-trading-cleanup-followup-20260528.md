
---

## Phase 2.5 — Port-Triage & Runtime-Git-Cleanup (2026-05-28 23:10 CEST)

### Port 3000 — Caddy Reverse Proxy

| Eigenschaft | Wert |
|------------|------|
| Prozess | caddy (PID 3289768) |
| Konfiguration | `/home/claudio/caddy/Caddyfile` |
| Binding | `0.0.0.0:3000` (alle Interfaces) |
| Protokoll | HTTP (kein TLS auf :3000) |
| Funktion | Host-basiertes Routing: agent0, trade, momentum, regime, webserver, rizzcoach → jeweilige 127.0.0.1-Backends |
| Default-Fallback | `127.0.0.1:8082` (Agent Zero) |

**Bewertung:** GELB — Funktional korrekt, aber kein TLS und kein Interface-Restriction. Angreifer koennen ueber jede IP auf :3000 den Default-Handler erreichen.

**Empfehlung:** Caddy auf Tailscale-IP binden (`100.65.117.122:3000`) oder Firewall-Regel (`ufw allow from 100.64.0.0/10 to any port 3000`).

---

### Port 4096 — opencode Prozess

| Eigenschaft | Wert |
|------------|------|
| Prozess | opencode (PID 2457173) |
| Binary | `/root/.opencode/bin/opencode` |
| User | root |
| Binding | `0.0.0.0:4096` (alle Interfaces) |
| Parent | bash via VS Code Server (`/root/.vscode-server/cli/servers/Stable-.../shellIntegration-bash.sh`) |
| CWD | `/root` |

**Bewertung:** ROT — SECURITY_BLOCKER. Root-Process, oeffentlich erreichbar, VS-Code-Terminal-Tool ohne Authentifizierung. Jeder der :4096 erreichen kann, hat potentiell unauthentifizierten Zugriff.

**Empfehlung:** Sofort beenden: `pkill -f '/root/.opencode/bin/opencode'`. Danach pruefen ob opencode automatisch neustartet und ggf. systemd-timer oder VS-Code-Extension deaktivieren.

---

### Runtime-Git-Cleanup

**Durchgefuehrt:**
1. `primo_signal_state.json` — Catch-all zu `.gitignore` hinzugefuegt: `**/primo_signal_state.json`
2. `git rm --cached` fuer 2 Dateien: primo_signal_state.json (canary) + hermes_signal_fixture (research)
3. Commit `fd2f579` erstellt

**Korrektur nach Verifikation:**
- `hermes_signal_fixture_20260520.json` ist KEIN Runtime-File — es wird von 2 Trading-Bot-Konfigs referenziert:
  - `config_regime_hybrid_sideaware_v1.json` → `research_signal_file`
  - `config_regime_hybrid_sideaware_v2.json` → `research_signal_file`
- Fixture wiederhergestellt: `git add -f` + `.gitignore`-Pattern `**/hermes_signal_fixture_*.json` entfernt
- Commit amended → **neuer Hash: `974901a`**

**Finale Dateien:**
| Datei | Vorher | Nachher |
|-------|--------|---------|
| `**/primo_signal_state.json` | getrackt, Git-Churn | untracked, .gitignore |
| `hermes_signal_fixture_20260520.json` | getrackt | getrackt (bleibt) |
| `.gitignore` | — | +1 Catch-all Pattern |

**Git-Status nach Cleanup:**
```
 M orchestrator/scripts/git_guard.sh     (pre-existing, unrelated)
?? docs/context/vps-multi-user-trading-cleanup-20260528.md  (dieses Dokument)
```

---

### Remaining Blockers

| # | Blocker | Schwere | Naechster Schritt |
|---|---------|---------|-------------------|
| 1 | Port 4096 (opencode) oeffentlich als root | ROT | `pkill -f '/root/.opencode/bin/opencode'` |
| 2 | Port 3000 (Caddy) ohne TLS/IP-Restriction | GELB | Caddy bind auf Tailscale-IP oder ufw-Regel |
| 3 | UID-Mismatch (Bots=10000, hermes=1337, Guardian=1337) | GELB | Canary-Ownership-Phase (nicht freigegeben) |
| 4 | root:root Ownership auf regime-hybrid/freqai-rebel Host-Pfaden | GELB | Nach Canary-Phase klaeren |
| 5 | Swap 92% belegt (3.7G/4G) | GELB | Beobachten, ggf. swapiness anpassen |
| 6 | git_guard.sh modifiziert (working tree) | GELB | Pruefen ob Commit noetig |

---

### GO/HOLD Empfehlung

**Gesamt-Status: GELB**

| Massnahme | Status |
|-----------|--------|
| Port 4096 schliessen | GO — Security-Blocker, kein Trade-Impact |
| Port 3000 haerten | GO — nach Port 4096, konfig-Change am Caddy |
| Ownership-Canary | HOLD — erst nach Port-Fixes + User-Freigabe |
| Guardian-Cleanup | HOLD — abhaengig von Ownership-Stabilisierung |
| Autonomie-Freigabe | HOLD — alle Blocker muessen GELB oder besser sein |

**Naechster konkreter Schritt:**
```bash
# 1. Port 4096 schliessen
ssh neu "pkill -f '/root/.opencode/bin/opencode' && echo 'KILLED' || echo 'NOT_FOUND'"

# 2. Verifizieren
ssh neu "ss -tlnp | grep 4096 || echo 'PORT_CLOSED'"
```

---

*Updated: 2026-05-28 23:15 CEST — Port-Triage + Runtime-Git-Cleanup + Fixture-Korrektur*

---

## Port 4096 Fix (2026-05-28 23:20 CEST)

### Durchfuehrung

| Schritt | Ergebnis |
|---------|----------|
| PID identifiziert | 2457173 (opencode, root, pts/9) |
| Binary verifiziert | `/root/.opencode/bin/opencode` |
| SIGTERM | Prozess ueberlebt (ignoriert SIGTERM) |
| SIGKILL | Prozess terminiert |
| Port-Check nach Kill | Port 4096 geschlossen |
| Auto-Restart-Check (5s) | Kein Restart, Port bleibt geschlossen |

### Verbleibende opencode-Prozesse

| PID | Gestartet | Status | Listener |
|-----|-----------|--------|----------|
| 838092 | 2026-05-20 | bash-Wrapper, laeuft weiter | keine |
| 838093 | 2026-05-20 | opencode Hauptprozess, laeuft weiter | keine |
| 2457173 | 2026-05-28 19:32 | **GETOETET** (SIGKILL) | — |

Die verbleibenden Prozesse (838092/838093) sind die Hintergrundinstanz vom 20. Mai. Sie haben **keine offenen Ports** und stellen kein Sicherheitsrisiko dar. Der getoetete Prozess (2457173) war eine Terminal-Session ueber VS Code Server, die den Listener auf 0.0.0.0:4096 geoeffnet hatte.

### Ergebnis

**Port 4096: VON ROT AUF GRUEN.**

Der Security-Blocker ist behoben. Kein oeffentlicher Listener mehr auf Port 4096.

### Updated Blocker-Liste

| # | Blocker | Vorher | Jetzt |
|---|---------|--------|-------|
| 1 | Port 4096 (opencode) | ROT | **GELOEST** |
| 2 | Port 3000 (Caddy) kein TLS/IP-Restriction | GELB | GELB (naechster Schritt) |
| 3 | UID-Mismatch (Bots=10000, hermes=1337) | GELB | GELB (HOLD) |
| 4 | root:root Ownership regime-hybrid/freqai-rebel | GELB | GELB (HOLD) |
| 5 | Swap 92% | GELB | GELB (beobachten) |
| 6 | git_guard.sh modified (working tree) | GELB | GELB |

---

*Updated: 2026-05-28 23:22 CEST — Port 4096 Security-Blocker geschlossen*

---

## Port 3000 Preflight (2026-05-28 23:30 CEST)

### Caddy-Identifikation

| Eigenschaft | Wert |
|------------|------|
| Container | caddy (caddy:latest) |
| Network Mode | host (shared host network stack) |
| PID | 3289768 |
| Uptime | 6 Tage |
| Aktive Caddyfile | /home/claudio/caddy/Caddyfile → /etc/caddy/Caddyfile |
| Listen | :3000 (0.0.0.0:3000, HTTP, kein TLS) |

### Warum 0.0.0.0:3000?

Host network mode + kein bind-Eintrag = Caddy hoert auf allen Interfaces.
Tailscale-Traffic kommt ueber tailscale0-Interface, daher wird 0.0.0.0 benoetigt
UM Tailscale zu erreichen. Alternative: explizit auf Tailscale-IP binden.

### Ist Port 3000 oeffentlich erreichbar?

**NEIN.** UFW INPUT default policy = DROP. Keine Allow-Regel fuer Port 3000.

Iptables-Traffic-Flow:
1. ts-input (Tailscale): ACCEPT all von tailscale0 → Port 3000 erreichbar via VPN
2. ufw-before-input (loopback): ACCEPT → Port 3000 erreichbar von localhost
3. ufw-user-input (oeffentlich): keine Regel fuer 3000 → faellt durch zu Default DROP

### Risiko-Bewertung: VON GELB AUF GELB (mit Caveat)

Port 3000 ist NICHT oeffentlich. Aber Defense-in-Depth fehlt:
- Wenn UFW deaktiviert wird (ufw disable/reset), ist Port 3000 sofort oeffentlich
- Caddy bietet keinen TLS auf :3000 (HTTP only) — aber Tailscale tunnelt verschluesselt

### Empfohlene Fixes

**Option A — UFW explicit deny (minimal, empfohlen):**
```bash
ufw deny in on eth0 to any port 3000 proto tcp comment 'Caddy: explicit deny public'
```
Rollback: `ufw delete deny in on eth0 to any port 3000 proto tcp`

**Option B — Caddy auf Tailscale-IP binden (starker Fix):**
Caddyfile `:3000` → `100.65.117.122:3000` + `docker restart caddy`
Rollback: Caddyfile zurueck auf `:3000` + `docker restart caddy`

**Option C — Status Quo akzeptieren.**

### Empfehlung

Option A als Sofortmassnahme. Option B als spaetere Hrtung.
Kein Container-Restart fuer Option A noetig.

---

*Updated: 2026-05-28 23:32 CEST — Port 3000 Preflight abgeschlossen*

---

## Port 3000 Defense-in-Depth Fix (2026-05-28 23:35 CEST)

### Angewendete Massnahme

**Option A: UFW explicit deny auf eth0**

```bash
ufw deny in on eth0 to any port 3000 proto tcp comment 'Caddy: explicit deny public'
```

### Verifikation

| Test | Ergebnis | Detail |
|------|----------|--------|
| UFW-Regel gesetzt | IPv4 + IPv6 | Regeln [13] und [19] |
| iptables-Regel aktiv | DROP tcp dpt:3000 on eth0 | 0 Pakete (kein Traffic) |
| Tailscale-Zugriff | status=302, 5.9ms | Caddy antwortet korrekt |
| Localhost-Zugriff | status=302, 5.3ms | Caddy antwortet korrekt |
| Container nicht neu gestartet | caddy Up 6 days | Kein Impact |
| Eigene Public-IP curl | 302 (erwartet) | Internes Loopback, kein echter ext. Test |

**Hinweis:** Curl von der VPS zur eigenen Public-IP (49.13.6.161:3000) zeigt 302, weil
der Kernel lokalen Traffic intern routed (kein echter eth0-Durchgang). Externer Traffic
wuerde die iptables DROP-Regel auf eth0 treffen.

### Rollback

```bash
ufw delete deny in on eth0 to any port 3000 proto tcp
```

### Updated Blocker-Liste

| # | Blocker | Vorher | Jetzt |
|---|---------|--------|-------|
| 1 | Port 4096 (opencode) oeffentlich | ROT | **GELOEST** |
| 2 | Port 3000 (Caddy) Defense-in-Depth | GELB | **GELOEST (UFW deny)** |
| 3 | UID-Mismatch (Bots=10000, hermes=1337) | GELB | GELB (HOLD) |
| 4 | root:root Ownership regime-hybrid/freqai-rebel | GELB | GELB (HOLD) |
| 5 | Swap 92% | GELB | GELB (beobachten) |
| 6 | git_guard.sh modified (working tree) | GELB | GELB |

### Gesamtbild nach Phase 2.5

| Bereich | Status |
|---------|--------|
| Runtime-Git-Cleanup | ERLEDIGT (Commit 974901a) |
| Port 4096 Security-Blocker | ERLEDIGT (SIGKILL opencode) |
| Port 3000 Defense-in-Depth | ERLEDIGT (UFW deny on eth0) |
| Ownership-Modell | HOLD — wartet auf Canary-Freigabe |
| Guardian-Rework | HOLD — abhaengig von Ownership |
| UID-Alignment | HOLD — abhaengig von Canary |

**Naechstes Gate:** Ownership-Canary (freqforge-canary UID/Permission-Test)
**Voraussetzung:** User-Freigabe fuer Phase 4/6

---

*Updated: 2026-05-28 23:37 CEST — Port 3000 Defense-in-Depth angewendet*
