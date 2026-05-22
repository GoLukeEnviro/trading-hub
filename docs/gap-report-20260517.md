# GAP-Report — Trading-Hub Repository (aktualisiert 17. Mai 2026)

**Erstellt:** 2026-05-17T12:30 UTC  
**Zuständiger Fachagent:** Meta-Orchestrator (Grok-4.3 via xAI OAuth)  
**Scope:** Repository-Struktur, Komponenten-Status, Dokumentation, Konformität mit SOUL.md und AGENTS.md  
**Ausgeschlossen:** Runtime-Änderungen, Strategie-Modifikationen, Config-Änderungen (per User-Vorgabe: nur Documentation & Analysis)

## Executive Summary

Das Trading-Hub Repository ist gut strukturiert und umfangreich dokumentiert. Die Kern-Execution-Fleet (Freqtrade-Bots) und der Signal-Generator (ai-hedge-fund-crypto) laufen in Docker. Allerdings bestehen signifikante Abweichungen vom Soll-Zustand:

- RiskGuard und ShadowLogger existieren **ausschließlich als Spezifikation** in AGENTS.md und SOUL.md — **nicht als deployte Services oder aktive Code-Integration**.
- trading_pipeline.py existiert nicht im Repository.
- MCP-Bitget-Server läuft in redundanten Instanzen (mehrere Python-Prozesse + Node MCP-Filesystem).
- Momentum-Bot bleibt im Zombie-Status.
- Gesamtabweichung: **ca. 35-40 %** (keine Verbesserung seit letztem Report, da keine neuen Layer implementiert wurden).

User-Präferenz: Nur Dokumentations-Updates und Analysen. Keine Änderungen an Strategie-Dateien, Konfigurationen oder Runtime-Operationen.

Stärkste Stärken: Umfassende Kontext-Dokumentation (49 Reports), strikte Dry-Run-Policy, Holographic Memory aktiv.

Kritischste Lücke: Fehlende mechanische Sicherheitslayer, die laut SOUL.md Pflicht sind.

## 1. Vollständiger Systemcheck

### Container & Prozesse (aktuell)
- hermes-agent: Up
- ai-hedge-fund-crypto: Up (healthy)
- Freqtrade-Fleet: Alle relevanten Bots Up (Regime-Hybrid, FreqForge, Canary, Rebel, Momentum, Webserver)
- MCP: Mehrere Instanzen von bitget_mcp_server.py + mcp-server-filesystem (Redundanz erkannt)
- Kein trading_pipeline.py Prozess

### Kernkomponenten Status
| Komponente              | Status     | Integrität | Dokumentation | Realer Stand |
|-------------------------|------------|------------|---------------|--------------|
| Orchestrator (Hermes)   | ACTIVE     | PASS       | EXCELLENT     | Steuert alles |
| Signal Layer            | ACTIVE     | PASS       | GOOD          | Produziert hermes_signal.json |
| MCP Paper Execution     | PARTIAL    | PARTIAL    | GOOD          | Redundante Prozesse, kein Daemon |
| RiskGuard               | MISSING    | FAIL       | SPEC-ONLY     | Nur in AGENTS.md beschrieben |
| ShadowLogger            | MISSING    | FAIL       | SPEC-ONLY     | Nur in AGENTS.md beschrieben |
| FreqForge Shadow        | ACTIVE     | PASS       | EXCELLENT     | Liest SQLite read-only |
| Momentum Bot            | ZOMBIE     | FAIL       | STALE         | 0 Trades seit Primo-Decommission |
| Holographic Memory      | ACTIVE     | PASS       | GOOD          | Aktiv |
| SOUL.md + Paper Override| ACTIVE     | PASS       | GOOD          | Temporär bis 18.05. |

### Schnittstellen & Konformität
- Signal-Chain: hermes_signal.json vorhanden, aber keine RiskGuard/ShadowLogger dazwischen.
- SOUL.md: Wird für Read-Only und Dry-Run eingehalten. Regel 5 und 6 (RiskGuard/ShadowLogger) nicht umgesetzt.
- Interne Richtlinien: Keine Credentials, archive-before-delete befolgt.
- Branchen-Best-Practices: Gute Modularität, aber fehlende automatisierte Gates und Retention.

## 2. Strukturierter Lückenscheck

**Funktionale Lücken:**
- RiskGuard und ShadowLogger: Fehlen komplett als aktive Komponenten.
- trading_pipeline.py: Nicht vorhanden.
- MCP: Läuft als manuelle Prozesse, kein stabiler Daemon/Auto-Restart.
- 60-Paper-Trades-Gate: Nicht automatisiert.

**Interne Richtlinien:**
- SOUL.md Regel 5/6 verletzt (Sicherheitslayer fehlen).
- Paper-Override muss nach 18.05. zurückgesetzt werden.
- Redundante MCP-Prozesse verstoßen gegen Effizienz-Best-Practices.

**Branchen-Best-Practices:**
- Keine automatische Log-Retention.
- Fehlende Whitelists für Pairs/Leverage in MCP.
- Git-Contamination durch viele .bak und snapshots.

## 3. Gezielter Blindfleckencheck

**Versteckte Risiken:**
- Redundante MCP-Prozesse (Ressourcenverschwendung + potenzielle Konflikte).
- Ollama-Cloud Single-Point-of-Failure für Signal-Generierung.
- Stale-Signale trotz theoretischer RiskGuard (da nicht implementiert).
- Git-Contamination erschwert LLM-Analysen.

**Unerkannte Abhängigkeiten:**
- trading_pipeline.py als zentraler Punkt — existiert aber nicht.

**Nicht dokumentierte Abweichungen:**
- MCP-Redundanz nicht in AGENTS.md erfasst.
- Mehrere MCP-Prozesse laufen parallel ohne Koordination.

## 4. Abschließender GAP-Check

**Quantitative Bewertung:**  
Gesamtabweichung **35-40 %** (Risiko-Layer fehlen, Redundanz, Zombie-Bot).

**Qualitative Bewertung:**  
Das System ist research- und limited paper-trading-ready. Für sichere Phase-Gates und 60-Trades-Sperre fehlen die Pflicht-Sicherheitskomponenten. Aktueller Stand entspricht dem Report vom 16.05. weitgehend — keine wesentlichen Fortschritte bei den kritischen Layern.

## Priorisierte Handlungsempfehlungen (nur Documentation & Analysis)

1. **PRIO 1 — Korrigierte GAP-Dokumentation finalisieren**  
   Dringlichkeit: HOCH (für interne Reviews)  
   Nutzen: Klare Ist/Soll-Transparenz.

2. **PRIO 2 — AGENTS.md und SOUL.md auf aktuellen MCP-Redundanz-Status updaten**  
   Dringlichkeit: MITTEL  
   Nutzen: Vermeidung von Fehlannahmen.

3. **PRIO 3 — Repository-Hygiene-Audit**  
   Dringlichkeit: NIEDRIG  
   Nutzen: Bessere Performance für Analysen.

**Hinweis zu Prio 1 (MCP-Daemon):**  
Per expliziter User-Vorgabe (nur Documentation & Analysis, keine Runtime-Operationen) wird keine Daemon-Implementierung oder Prozess-Änderung durchgeführt. Dies bleibt als Eskalationspunkt für zukünftige Phase-Gates.

**Langfristiger Nutzen:**  
Vollständige Konformität mit SOUL.md, sichere Basis für 60-Paper-Trades-Phase und spätere Freigaben.

---

**Bericht abgeschlossen. LOCK FOR REVIEW.**  
**Nächster Schritt:** Nur auf explizite Anweisung für weitere reine Dokumentations-Updates.

Datei gespeichert unter: /home/hermes/projects/trading/docs/gap-report-20260517.md