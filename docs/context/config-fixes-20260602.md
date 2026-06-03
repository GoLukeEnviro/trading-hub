# Config Fixes — 2026-06-02

**Kontext:** Systematische Fehlerbehebung nach Phase 1 Completion.

## Fix 1: config.yaml — ungueltiger Key `base_url_env` entfernt

**Datei:** `/opt/data/profiles/orchestrator/config.yaml`

**Problem:** Zeilen 8 und 12 enthielten `base_url_env: OLLAMA_BASE_URL` bzw. `base_url_env: GLM_BASE_URL`. Der Config-Parser (`hermes_cli/config.py` Z. 2893) erkennt diesen Key nicht — er kennt nur `base_url`. Die Hermes-Overlays fuer `ollama-cloud` und `zai` setzen `base_url_env_var` bereits intern, sodass die Angabe im config redundant war.

**Aktion:** Beide `base_url_env` Zeilen entfernt.

**Verifikation:** Warnung "unknown config keys ignored: base_url_env" sollte ab naechstem Hermes-Start verschwinden.

## Fix 2: config.yaml — rate_limit_delay fuer zai hinzugefuegt

**Datei:** `/opt/data/profiles/orchestrator/config.yaml`

**Problem:** Cron-Job `dedd76b423ce` (daily-signal-confidence-monitor) erhielt HTTP 429 von zai/glm-5.1 um 18:01:59. Transient, aber ohne konfiguriertem `rate_limit_delay` wird der Retry sofort durchgefuehrt.

**Aktion:** `rate_limit_delay: 2` (Sekunden) fuer Provider `zai` hinzugefuegt.

**Hinweis:** 429 wird durch bestehenden Retry-Mechanismus (3 Versuche, `api_max_retries: 3`) abgefangen. Bei haeufigem Auftreten kann `rate_limit_delay` weiter erhoeht werden.

## Nicht behoben (transient / Agent-Laufzeitfehler)

| Fehler | Grund |
|--------|-------|
| skill_view: `dream-mode` referenziert Datei in `local-memory-ops` | Agent hat falschen Skill-Namen beim Aufruf verwendet. Datei liegt korrekt unter `local-memory-ops/references/`. |
| skill_manage patch fuzzy match failure | Agent hat `old_string` nicht exakt getroffen. Datei `local-memory-ops/SKILL.md` ist intakt. |
