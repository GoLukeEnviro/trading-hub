# Hermes Agent Plugins & Features Implementation Plan
## Quelle: David Ondrej — "100 hours of Hermes Agent lessons in 46 minutes"
## Video: https://youtu.be/G47mnkGkYwQ

---

## Current State Assessment (IST-Zustand)

| Component | Status | Details |
|-----------|--------|---------|
| Model | minimax-m2.5-free via opencode-zen | Free-tier, 256K ctx |
| Memory | Holographic (SQLite) | Active, 369 facts |
| Plugins | sfa-enforcer | Minimal |
| MCP Servers | None configured | No mcp_servers section |
| Gateway | Telegram connected | TELEGRAM_HOME_CHANNEL set |
| Profiles | orchestrator, trading, mira, weatherbot | 4 profiles |
| Skills | 30+ categories installed | Rich skill library |
| Security | tirith ON, redact_secrets ON | Good baseline |
| Toolsets | All enabled (disabled_toolsets: []) | Broad access |

---

## Implementation Plan — 7 Phasen

### Phase 1: MCP Server Integration (Model Context Protocol)
**Priorität: HOCH** — Das ist der Game-Changer in Davids Video.

MCP Server erlauben Hermes, externe Tools direkt als native Tools zu nutzen.
Aktuell hast du NULL MCP-Server konfiguriert.

**Implementierung:**

```bash
# 1. Filesystem MCP Server (lokaler Dateizugriff mit erweiterten Capabilities)
hermes mcp add filesystem --command "npx -y @modelcontextprotocol/server-filesystem /home/hermes/projects/trading"

# 2. Memory MCP Server (persistent key-value store, komplementär zu Holographic)
hermes mcp add memory --command "npx -y @modelcontextprotocol/server-memory"

# 3. GitHub MCP Server (erweiterter GitHub-Zugang)
# Erfordert GITHUB_TOKEN in .env
hermes mcp add github --url "https://github.com/mcp/servers" --command "npx -y @modelcontextprotocol/server-github"

# 4. Brave Search MCP (falls du den 422-Fehler vermeiden willst)
# Erfordert BRAVE_API_KEY
hermes mcp add brave-search --command "npx -y @modelcontextprotocol/server-brave-search"
```

**Verification:**
```bash
hermes mcp list
hermes mcp test filesystem
/reload-mcp  # In-Session Reload
```

---

### Phase 2: Multi-Provider Credential Pooling
**Priorität: HOCH** — Redundanz und Cost-Optimization.

Aktuell: 1 Provider (opencode-zen/minimax). David zeigt wie man ein Pool aufbaut.

**Implementierung:**

```bash
# 1. OpenRouter als Fallback/Alternative
hermes auth add  # Interactive: Provider=openrouter, API Key

# 2. Google Gemini (free tier für auxiliary tasks)
hermes config set auxiliary.vision.provider google
hermes config set auxiliary.vision.model gemini-2.0-flash

# 3. DeepSeek als Cost-Efficient Option
hermes auth add  # Provider=deepseek

# 4. Model-Switching Setup
hermes model  # Interactive picker — configure multiple models
```

**Verification:**
```bash
hermes auth list
hermes doctor
```

---

### Phase 3: Gateway Platform Expansion
**Priorität: MITTEL** — Multi-Platform Messaging.

Aktuell: Nur Telegram. David zeigt Discord, Slack, WhatsApp Integration.

**Implementierung:**

```bash
# 1. Discord Bot Setup
hermes gateway setup  # → Discord section
# Bot Token, Application ID, Server ID eintragen
# WICHTIG: "Message Content Intent" in Discord Developer Portal aktivieren!

# 2. WhatsApp (falls gewünscht)
hermes gateway setup  # → WhatsApp section

# 3. Email Integration (himalaya)
hermes skills install email/himalaya  # Falls nicht schon installiert

# 4. Gateway Restart
hermes gateway restart
```

**Verification:**
```bash
hermes gateway status
/platforms  # In-Session Check
```

---

### Phase 4: Autonomous Orchestration Layer
**Priorität: HOCH** — Das ist der Kern von Davids "7 Levels".

Aufbau einer autonomen Orchestrierung mit Cron Jobs, Webhooks, und Subagent-Delegation.

**4a. Cron Job Architecture (Scheduler)**

```bash
# Trading Signal Collector (alle 30 Min)
hermes cron create "30m" --name "signal-collector"

# Fleet Health Check (stündlich)
hermes cron create "every 1h" --name "fleet-health"

# Daily Report (09:00 UTC)
hermes cron create "0 9 * * *" --name "daily-report"
```

**4b. Webhook Subscriptions**

```bash
# GitHub Webhook für Auto-PR-Review
hermes webhook subscribe github-pr --url /webhooks/github-pr

# Trading Alert Webhook
hermes webhook subscribe trading-alert --url /webhooks/trading-alert
```

**4c. Multi-Agent Orchestration Pattern**

```
Control Plane (orchestrator profile)
  ├── Worker 1: Signal Analysis (delegate_task)
  ├── Worker 2: Fleet Health (delegate_task)
  ├── Worker 3: Risk Assessment (delegate_task)
  └── Persistence: Memory + Skills + Docs
```

**Verification:**
```bash
hermes cron list
hermes webhook list
hermes status --all
```

---

### Phase 5: Advanced Memory & Context Management
**Priorität: MITTEL** — Schon aktiv, kann aber verbessert werden.

**Implementierung:**

```bash
# 1. Memory Char Limits prüfen/optimieren
hermes config set memory.memory_char_limit 2200  # Aktuell
hermes config set memory.user_char_limit 1375    # Aktuell

# 2. Self-Improvement Review aktivieren (falls nicht schon)
# Passiert automatisch bei Memory-Writes in Sessions

# 3. Session Search für Cross-Session Recall
# Schon aktiv (session_search toolset)

# 4. Skill-based Procedural Memory
# Schon aktiv (30+ Skill-Kategorien)
```

---

### Phase 6: Security Hardening & Approval Workflows
**Priorität: MITTEL** — Schon gut, kann verfeinert werden.

**Implementierung:**

```bash
# 1. Smart Approval Mode (Auto-Approve Low-Risk)
hermes config set approvals.mode smart

# 2. PII Redaction für Gateway Messages
hermes config set privacy.redact_pii true

# 3. Website Blocklist (optional)
hermes config set security.website_blocklist.enabled true

# 4. Cron Approval Mode
hermes config set approvals.cron_mode smart  # Aktuell: deny
```

---

### Phase 7: Voice & Multimedia Integration
**Priorität: NIEDRIG** — Nice-to-have.

**Implementierung:**

```bash
# 1. STT Setup (Local Whisper)
pip install faster-whisper
hermes config set stt.enabled true
hermes config set stt.provider local

# 2. TTS Optimization (Edge ist schon konfiguriert)
# Für bessere Qualität:
# hermes config set tts.provider elevenlabs  # Mit API Key

# 3. Voice Mode aktivieren (In-Session)
# /voice on
```

---

## Prioritäten-Matrix

| Phase | Impact | Aufwand | Risiko | Reihenfolge |
|-------|--------|---------|--------|-------------|
| Phase 1: MCP Servers | HIGH | LOW | LOW | **SOFORT** |
| Phase 2: Provider Pooling | HIGH | MED | LOW | Nach Phase 1 |
| Phase 4: Orchestration | HIGH | HIGH | MED | Nach Phase 2 |
| Phase 3: Platform Expansion | MED | MED | LOW | Nach Phase 4 |
| Phase 5: Memory Tuning | MED | LOW | LOW | Parallel möglich |
| Phase 6: Security | MED | LOW | LOW | Parallel möglich |
| Phase 7: Voice | LOW | LOW | LOW | Wenn Zeit |

---

## Voraussetzungen (Prerequisites)

1. **Node.js** für MCP Server (npx commands):
   ```bash
   node --version || (curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs)
   ```

2. **API Keys** für Provider Pool:
   - OPENROUTER_API_KEY
   - GOOGLE_API_KEY (für Gemini)
   - DEEPSEEK_API_KEY (optional)
   - BRAVE_API_KEY (optional, für MCP Search)

3. **Platform Tokens** für Gateway Expansion:
   - Discord Bot Token
   - WhatsApp Business API (optional)

---

## ESKALATIONSPUNKTE

Folgende Änderungen erfordern deine explizite Freigabe:
- [ ] MCP Server hinzufügen (neue externe Verbindungen)
- [ ] Provider Credentials hinzufügen (API Keys)
- [ ] Gateway Platform aktivieren (Discord/WhatsApp)
- [ ] Approval Mode ändern (smart vs manual)
- [ ] Cron Jobs erstellen/ändern

---

## Nächste Schritte

1. **Bestätige welche Phasen du umsetzen willst**
2. **Prüfe ob Node.js installiert ist** (für MCP)
3. **Stelle API Keys bereit** (für Provider Pooling)
4. **Dann starten wir Phase 1: MCP Server Integration**

_Generiert: 2026-05-16 | Modell: GLM-5.1 via Z.AI | Source: David Ondrej Video + System Audit_
