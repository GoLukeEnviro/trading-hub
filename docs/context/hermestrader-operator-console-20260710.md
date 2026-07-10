# HermesTrader Operator Console — Claude Code CLI + Codex CLI (Host-Level, Non-Trading)

**Datum:** 2026-07-10
**Status:** X2_CLAUDE_CODE_CODEX_CLI_OAUTH_INSTALL_GREEN
**Scope:** Host-Infrastruktur auf HermesTrader. Betrifft NICHT die SI-v2-Loop, Freqtrade, RiskGuard oder Hermes Trading-Zugriff.

---

## 1. Warum

Der VPS-Betreiber (Mensch) brauchte einen sicheren, OAuth-basierten Weg, Claude Code CLI und OpenAI Codex CLI direkt auf HermesTrader fuer VPS-weite Wartungsarbeiten (Admin, Debugging, Docker-Inspektion) zu nutzen, getrennt von `deploy` (Repo/Git-Arbeitsuser) und `hermes` (Agent-Container). Ziel: kein Scope-Drift zwischen Repo-Arbeit und allgemeiner Host-Administration.

## 2. User/Access Matrix (Ergaenzung zu bestehendem Modell)

| User | UID:GID | Docker | Sudo | Gruppen | Zweck |
|------|---------|--------|------|---------|-------|
| root | 0:0 | voll | voll | root | Systembesitzer |
| operator (NEU) | 10001:37 | NEIN | NUR Breakglass-Wrapper (sudoers-Allowlist) | operator | Mensch, haelt Claude/Codex OAuth-Sessions |
| deploy | 1000:1000 | JA | JA (%sudo) | deploy,sudo,hermes,docker | Repo/Git/Deployment (unveraendert) |
| hermes | 10000:10000 | NEIN | NEIN | hermes | Agent-Container (unveraendert, kein docker.sock) |

`operator` ist passwortlos gesperrt (`passwd -l`), kein direkter SSH-Login. Zugriff ausschliesslich via `su - operator` durch root. Kein Mitglied der `sudo`-Gruppe (bewusst entfernt nach Security-Review — Gruppenmitgliedschaft haette trotz gesperrtem Passwort die volle `(ALL:ALL) ALL`-Regel gewaehrt).

## 3. Installierte Tools

| Tool | Version | Installationsweg | Binary |
|---|---|---|---|
| Claude Code CLI | 2.1.197 | offizielles apt-Repo (Fingerprint verifiziert: 31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE) | /usr/bin/claude (systemweit) |
| Codex CLI | 0.144.0 | offizieller Standalone-Installer, im operator-Kontext | /home/operator/.local/bin/codex + Symlink /usr/local/bin/codex |

Beide Tools authentifizieren ausschliesslich per OAuth/Browser-Login als `operator`. Keine statischen API-Keys, keine Secrets in Shell-Configs.

## 4. Breakglass-Modell (hart erzwungen)

- Script `/usr/local/sbin/operator-breakglass-root`: erfordert Pflicht-Grund-Argument, loggt `timestamp | caller | reason` nach `/var/log/hermestrader-operator/breakglass.log`, startet danach root-Shell.
- sudoers (`/etc/sudoers.d/operator`): `operator ALL=(root) NOPASSWD: /usr/local/sbin/operator-breakglass-root` — einzige erlaubte sudo-Aktion.
- Verifiziert per `sudo -n -l`: nur dieser eine Eintrag. Negativtest bestaetigt Ablehnung aller anderen sudo-Kommandos.

## 5. tmux-Helper (unter /usr/local/bin/)

- `tradinghub-operator-claude` — startet Claude Code CLI Session als operator
- `tradinghub-operator-codex` — startet Codex CLI Session als operator
- `operator-root` — fragt nach Grund, ruft Breakglass-Wrapper auf

## 6. Auswirkung auf Trading-Hub / Hermes

- **Keine.** Hermes-Container unveraendert (kein docker.sock, Bridge weiterhin ALLOWED getestet).
- `deploy`-User und Trading-Hub-Repo-Zugriff unveraendert.
- SI-v2-Loop, Freqtrade, RiskGuard, ShadowLogger, Kill-Switch: keine Beruehrung.
- Diese Aenderung ist reine Host-Infrastruktur fuer menschliche VPS-Wartung, keine Runtime-/Trading-Mutation.

## 7. Reports (vollstaendige Details, ausserhalb des Repos)

- `/root/reports/hermestrader-x2-claude-code-codex-cli-oauth-install-2026-07-10.md` (root-only)
- `/opt/data/hermes/reports/hermestrader-x2-claude-code-codex-cli-oauth-install-2026-07-10.md` (sanitized, Hermes-lesbar unter /opt/data/reports/ im Container)
