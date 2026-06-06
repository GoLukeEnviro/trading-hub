# Docs Sync — AGENTS.md + SOUL.md — 2026-06-06

## Was aktualisiert wurde

### AGENTS.md
- Container-Namen auf trading-*-1 Konvention aktualisiert + Hinweis ergänzt
- RiskGuard: SPEC ONLY → DEPLOYED (trading_pipeline.py, globale + per-pair Thresholds)
- ShadowLogger: SPEC ONLY → PARTIALLY DEPLOYED (embedded in trading_pipeline.py)
- FreqAI-Rebel: Custom Image + DB-Info ergänzt

### SOUL.md
- Geprüft: keine veralteten Referenzen (Container-Namen, Honcho, Momentum, AI-Override)
- Status: CLEAN — keine Änderungen nötig

## Warum
Container-Naming-Drift wurde 2026-06-06 entdeckt und behoben.
RiskGuard und ShadowLogger sind seit dem Pipeline-Refactor deployed, aber
AGENTS.md war nie aktualisiert worden.
Prime Directive v2.0 erfolgreich ausgeführt — Docs-Sync als abschließender Schritt.
