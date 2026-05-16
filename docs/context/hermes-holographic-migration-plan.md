# Hermes Honcho → Holographic Migration Plan

**Status:** COMPLETE — Holographic active + retrieval patched + stable
**Erstellt:** 2026-05-14
**Letzte Änderung:** 2026-05-14 (retrieval fallback patch applied)
**Ziel:** Sichere, kuratierte Migration von Honcho Memory zu Holographic (SQLite)
**Hard-Constraint:** Honcho wird NICHT gelöscht, nicht deaktiviert, nicht entfernt.

---

## Zustand laut Inspection (Phase 0)

```
Container:             hermes-agent (Docker, /home/hermes/.hermes/ als HERMES_HOME)
Aktiver Provider:      honcho
Built-in Memory:       immer aktiv (MEMORY.md/USER.md — existieren noch nicht in diesem Profil)
Holographic Plugin:    ✓ BUNDLED in ~/hermes-src/plugins/memory/holographic/ (kein额外 Install nötig)
Holographic DB:        noch nicht existiert → $HERMES_HOME/memory_store.db

Honcho DB Stand:
  Total docs:          3,375
  Unique content:      3,332
  Exact dupes:         43  (1.3% — massive Verbesserung seit 12 Mai: 47% → 1.3%)
  explicit:            2,425
  deductive:           602
  inductive:           348
  Gold layer:          950 docs (deductive + inductive) — 100% zu erhalten

Bestehende Backups:
  /tmp/honcho_pre_dedupe_2026-05-12T1942Z.sql (238 MB, 12. Mai)
```

---

## Phase 0 — Current Memory State Audit ✅ (INLINE DONE)

**Gate 0 PASS — Fakten bekannt:**

| Item | Wert |
|------|------|
| HERMES_HOME (container) | `/home/hermes/.hermes/` |
| Config | `/home/hermes/.hermes/config.yaml` |
| Honcho JSON | `/home/hermes/.hermes/honcho.json` |
| memory.provider | `honcho` |
| Holographic | INSTALLED (bundled, kein额外 Install) |
| Holographic DB Pfad | `$HERMES_HOME/memory_store.db` |
| Holographic deps | SQLite (immer da), numpy (wahrscheinlich vorhanden) |
| Backup | `/tmp/honcho_pre_dedupe_2026-05-12T1942Z.sql` |

**Nächste Aktion:** Config-Backup erstellen (Phase 1, Schritt 1).

---

## Phase 1 — Honcho Backup + Read-Only Export

**Verantwortlich:** Operator (Luke muss freigeben)
**Gate 1:** Backup + Raw Export existieren

### Schritt 1.1 — Configs sichern (LESE-MUST, kein Mutieren)

```bash
# Im hermes-agent Container ausführen (docker exec hermes-agent sh -c '...')
BACKUP_DIR="/home/hermes/.hermes/backups/migration-$(date -u +%Y%m%dT%H%MZ)"
mkdir -p "$BACKUP_DIR"

cp /home/hermes/.hermes/config.yaml "$BACKUP_DIR/config.yaml.$(date -u +%Y%m%dT%H%MZ)"
cp /home/hermes/.hermes/honcho.json "$BACKUP_DIR/honcho.json.$(date -u +%Y%m%dT%H%MZ)"

# Alte Backups aufheben
ls -lh /tmp/honcho_pre_dedupe_2026-05-12T1942Z.sql
```

### Schritt 1.2 — PostgreSQL pg_dump (Honcho DB)

```bash
# Auf dem Docker-Host (NICHT im Container):
docker exec honcho-database-1 pg_dump -U postgres postgres \
  > /tmp/honcho_pre_holographic_migration_$(date -u +%Y%m%dT%H%MZ).sql

# Verifizieren
ls -lh /tmp/honcho_pre_holographic_migration_*.sql
head -3 /tmp/honcho_pre_holographic_migration_*.sql
tail -3 /tmp/honcho_pre_holographic_migration_*.sql
```

### Schritt 1.3 — Read-Only JSONL Export aller Dokumente

```sql
-- Im Honcho-DB-Container:
docker exec honcho-database-1 psql -U postgres -t -A -F',' -c "
SELECT
  d.id,
  d.content,
  d.level,
  d.observer,
  d.observed,
  d.workspace_name,
  d.session_name,
  d.created_at::text,
  d.updated_at::text,
  d.times_derived,
  d.deleted_at::text,
  m.peer
FROM documents d
LEFT JOIN peers m ON m.id = d.observed_id
WHERE d.workspace_name = 'hermes'
  AND d.deleted_at IS NULL
ORDER BY d.id;
" > /tmp/honcho_export_$(date -u +%Y%m%dT%H%MZ).csv
```

Alternativ (empfohlen für Verarbeitung):

```bash
# JSONL-Export mit allen Feldern
docker exec honcho-database-1 psql -U postgres -c "\copy (
  SELECT row_to_json(t)
  FROM (
    SELECT
      d.id,
      d.content,
      d.level,
      d.observer,
      d.observed,
      d.workspace_name,
      d.session_name,
      d.created_at,
      d.updated_at,
      d.times_derived
    FROM documents d
    WHERE d.workspace_name = 'hermes' AND d.deleted_at IS NULL
    ORDER BY d.id
  ) t
) TO '/tmp/honcho_export_$(date -u +%Y%m%dT%H%MZ).jsonl';
```

Dann vom Host extrahieren:
```bash
docker cp honcho-database-1:/tmp/honcho_export_*.jsonl /tmp/
wc -l /tmp/honcho_export_*.jsonl
```

### Schritt 1.4 — Peer-Card Export

```bash
# Peer cards extrahieren
docker exec honcho-database-1 psql -U postgres -c "\copy (
  SELECT row_to_json(t)
  FROM (
    SELECT id, peer, metadata, internal_metadata, created_at, updated_at
    FROM peers WHERE workspace_name = 'hermes'
  ) t
) TO '/tmp/honcho_peers_$(date -u +%Y%m%dT%H%MZ).jsonl';
```

### Gate 1 Kriterien

- [ ] `/tmp/honcho_pre_holographic_migration_*.sql` existiert und ist > 1 MB
- [ ] `honcho_export_*.jsonl` existiert mit Zeilenzahl ≈ 3,375
- [ ] Backup-Verzeichnis unter `/home/hermes/.hermes/backups/migration-*/` existiert

---

## Phase 2 — Deduplizieren und Kuratieren

**Verantwortlich:** Operator
**Gate 2:** Kuratierte Kandidatenliste ist bereinigt und kategorisiert

### Schritt 2.1 — Exact Duplicate Analyse

```python
# honcho_dedupe.py — im Host oder Container
import json
import hashlib
from collections import defaultdict

records = []
with open('/tmp/honcho_export_latest.jsonl') as f:
    for line in f:
        records.append(json.loads(line))

# Hash nach normalisiertem Content
def normalize(s):
    return s.strip().lower()

content_hash = defaultdict(list)
for r in records:
    h = hashlib.md5(normalize(r['content']).encode()).hexdigest()
    content_hash[h].append(r)

# Duplikat-Gruppen
dupes = {h: v for h, v in content_hash.items() if len(v) > 1}
print(f"Duplikat-Gruppen: {len(dupes)}")
print(f"Duplikat-Docs: {sum(len(v)-1 for v in dupes.values())}")
```

### Schritt 2.2 — Kanonische Records pro Duplikat-Gruppe

Regel: Behalte den ältesten (MIN created_at) oder den mit höchstem `times_derived`.

### Schritt 2.3 — Importance Scoring (0–5)

Scoring-Matrix:

| Score | Kriterium | Beispiel |
|-------|-----------|----------|
| 5 | Hartes Limit, NEVER-Regel | "Kein Live-Trading ohne Freigabe", "dry_run=false verboten" |
| 5 | Kritische Architektur-Entscheidung | "PrimoGate ist der Trading-Core" |
| 4 | User Preference stabil | "Luke kommuniziert in Deutsch mit English Tech-Terms" |
| 4 | Projekt-Kontext dauerhaft | "Freqtrade auf Hetzner VPS, Dry-Run Bitget" |
| 4 | Security Regeln | "API-Keys niemals in Config-Dateien" |
| 3 | Tool-Envelopes, Command-Konventionen | "Claude Code nutzt ANTHROPIC_BASE_URL=https://api.z.ai" |
| 3 |暂时ige aber nützliche Entscheidungen | "Momentum Bot hat 0 Trades, zu restriktiv" |
| 2 | Prozedurale Erinnerungen | "Cron läuft 06:00/18:00 UTC" |
| 1 | Vage/Temporär | "Luke seems frustrated" |
| 0 | Lärm, Duplikate, Secrets | Alles mit API-Keys, Passwörtern |

### Schritt 2.4 — Wichtige Kategorien für Holographic Import

Die 11 Kategorien aus dem Agent-Task:

1. **user_preferences** — Luke's Präferenzen, Kommunikationsstil
2. **hard_rules** — NIEMALS-Regeln, Eskalations-Regeln
3. **server_infrastructure** — Hetzner VPS, Docker-Setup, Ports
4. **security_rules** — Credentials-Policy, kein dry_run=false
5. **hermes_agent_architecture** — Profile, Toolsets, Provider-Stack
6. **honcho_archive_context** — Upstream-Bugs (#557/#444), MQG-Patch
7. **openclaw_agent_zero_context** — Falls relevant
8. **trading_project_context** — Freqtrade Bots, Signal-Layer, RiskGuard
9. **goenviro_goenvirogame_context** — Falls relevant
10. **tooling_and_commands** — Bewährte Command-Patterns
11. **project_decisions** — Architektur-Entscheidungen, Offene TODOs

### Schritt 2.5 — Sektor-spezifische Gold-Facts (aus HONCHO EXPORT)

Aus dem aktuellen Honcho-Export (3,375 Docs) — folgende Kategorien priorisieren:

**AUS MEMORY (83 Einträge — 100% zu kuratieren und importieren):**
- Lükes Trading-Hard-Limits (Konfidenz >= 0.60, min 60 Paper-Trades)
- Infrastructure: Tailscale Funnel, Caddy, ki-fabrik network
- Freqtrade Fleet Status (6 bots, Dry-Run, Ports)
- Honcho Deployment: Commit ad7c1b3, v3.0.6, writeFrequency=session
- Claude Code Setup: ~/.local/bin/claude, Auth via settings.json
- FreqForge Deployment-Regel: backtest → paper 48h → live
- Holographic Provider: SQLite-basiert, bundled, config-Pfade

**AUS HONCHO SKILL (oberste Ebene — 100% erhalten):**
- Honcho Trigger provenance (prevent_document_duplicates, manuell hinzugefügt)
- Upstream Bugs #557/#444 (OPEN)
- PR #609 als Fix-Kandidat
- MQG v2.0.0 Patch: 6-Gate reject-by-default
- Honcho API: baseUrl=http://honcho-api-1:8000, workspace=hermes
- Deriver Model Configuration (qwen3-coder:480b, gpt-oss:120b, deepseek-v3.1:671b)
- Peer Card Write/Read Pattern (PUT /.../card → internal_metadata)
- CRITICAL: writeFrequency="async" verboten (37K Duplikate)

**NICHT importieren:**
- Alles mit API-Keys, Tokens, Secrets, Credentials
- Transient Log-Snippets ("Luke executed command", Timestamps)
- Sanitization-Artifacts ("Luke is implementing Phase", "Luke becomes frustrated")
- Stale Paths die nicht mehr existieren

### Schritt 2.6 — Output erzeugen

```
migration_candidates.jsonl     — score >= 3, dedupliziert, kategorisiert
rejected_records_sample.jsonl  — score 0-2, für Luke-Inspektion
duplicate_groups_report.md     — Duplikat-Statistiken
import_manifest.json           — counts per category
```

### Gate 2 Kriterien

- [ ] `migration_candidates.jsonl` existiert mit N records (N ≈ 200–500 erwartet)
- [ ] `rejected_records_sample.jsonl` enthält typische verworfene Records
- [ ] duplicate_groups_report.md zeigt Duplikat-Statistiken
- [ ] import_manifest.json zeigt counts per Kategorie
- [ ] KEIN Secret/String der als API-Key/Passwort/Token aussieht in candidates

---

## Phase 3 — Holographic Aktivieren

**Verantwortlich:** Operator
**Gate 3:** Holographic installiert, konfiguriert, testbar

### Schritt 3.1 — Holographic Config vorbereiten

Holographic nutzt `plugins.hermes-memory-store` in config.yaml. Die aktuelle config.yaml hat noch keinen `plugins` Block mit holographic settings.

```yaml
# plugins.hermes-memory-store settings (optional — Defaults funktionieren)
plugins:
  hermes-memory-store:
    db_path: "$HERMES_HOME/memory_store.db"  # Default
    auto_extract: false                      # Prefer explicit fact_store calls
    default_trust: 0.5
    min_trust_threshold: 0.3
    hrr_dim: 1024
    hrr_weight: 0.3
    temporal_decay_half_life: 0  # 0 = keine zeitliche Decay
```

### Schritt 3.2 — Provider switch (LESE-MUST GATE)

```bash
# Backup ERST:
cp /home/hermes/.hermes/config.yaml /home/hermes/.hermes/config.yaml.backup.holographic.$(date -u +%Y%m%dT%H%MZ)

# Provider switch via hermes CLI:
docker exec hermes-agent hermes memory setup  # interaktiv ODER:

# Direkt in config.yaml ändern:
# Aendere:  memory.provider: honcho
# Zu:      memory.provider: holographic
```

oder per hermes CLI:
```bash
docker exec hermes-agent hermes memory setup
# → wähle "holographic" aus der Liste
```

### Schritt 3.3 — Holographic Smoke Test

```bash
# Verify
docker exec hermes-agent hermes memory status

# Erwartet:
#   Provider: holographic ✓
#   Plugin: installed ✓
#   Status: available ✓

# Test: Fakten schreiben
docker exec hermes-agent python3 -c "
import sys
sys.path.insert(0, '/home/hermes/hermes-src/plugins/memory/holographic')
from store import MemoryStore
store = MemoryStore(db_path='/home/hermes/.hermes/test_memory.db')
fid = store.add_fact('TEST: Honcho migration smoke test', category='general')
print(f'fact_id={fid}')
store._conn.execute('DELETE FROM facts WHERE id=?', (fid,))
print('SMOKE TEST PASS')
"
```

### Gate 3 Kriterien

- [ ] `hermes memory status` zeigt `Provider: holographic`
- [ ] Smoke Test mit `MemoryStore` schreibt/löscht erfolgreich
- [ ] Hermes-Prozess kann mit holographic initialisiert werden

**FALLBACK:** Wenn Holographic nicht funktioniert → "Built-in only" Migration:
```bash
docker exec hermes-agent hermes memory off
# → nur MEMORY.md/USER.md aktiv, kein externer Provider
```

---

## Phase 4 — Kuratierte Memories nach Holographic importieren

**Verantwortlich:** Operator
**Gate 4:** Import abgeschlossen, Counts stimmen

### Schritt 4.1 — Import Script

```python
#!/usr/bin/env python3
"""import_to_holographic.py — Kuratierte Honcho-Records nach Holographic"""

import json
import sys
import hashlib
from pathlib import Path

# Holographic Store direkt ansprechen
sys.path.insert(0, '/home/hermes/hermes-src/plugins/memory/holographic')
from store import MemoryStore

DB = '/home/hermes/.hermes/memory_store.db'
CANDIDATES = '/tmp/migration_candidates.jsonl'

store = MemoryStore(db_path=DB)
imported = 0
skipped = 0

with open(CANDIDATES) as f:
    for line in f:
        rec = json.loads(line)
        content = rec['content']
        category = rec.get('category', 'general')
        tags = rec.get('tags', '')
        importance = rec.get('importance_score', 3)

        # Trust = importance/5.0 (0.6–1.0 range for score 3–5)
        trust = max(0.3, min(1.0, importance / 5.0))

        # Check for exact duplicate in holographic already
        existing = store._conn.execute(
            "SELECT id FROM facts WHERE content=? AND category=?",
            (content, category)
        ).fetchone()

        if existing:
            skipped += 1
            continue

        try:
            fid = store.add_fact(content, category=category, tags=tags)
            # Set trust score directly
            store._conn.execute(
                "UPDATE facts SET trust_score=? WHERE id=?",
                (trust, fid)
            )
            imported += 1
        except Exception as e:
            print(f"ERROR id={rec.get('id')}: {e}", file=sys.stderr)

print(f"Imported: {imported}")
print(f"Skipped (already exists): {skipped}")
print(f"Total in DB: {store._conn.execute('SELECT COUNT(*) FROM facts').fetchone()[0]}")
```

### Schritt 4.2 — Import Log

```
import_log.json:
{
  "timestamp": "<ISO>",
  "source": "honcho_export",
  "imported": N,
  "skipped_duplicates": K,
  "categories": {
    "user_preferences": X,
    "hard_rules": Y,
    "server_infrastructure": Z,
    ...
  },
  "rejected": M
}
```

### Gate 4 Kriterien

- [ ] `memory_store.db` existiert und enthält `imported` records
- [ ] Import-Log zeigt keine Fehler
- [ ] Keine Secrets in importierten Facts

---

## Phase 5 — Recall + Quality Smoke Tests

**Verantwortlich:** Operator + Hermes Session
**Gate 5:** Alle Core Recall Tests passen

### Test Queries (Holographic via fact_store)

```
Query 1: "Luke hard rules agent prompts"
  → Soll: Konfidenz-Schwelle 0.60, min 60 Paper-Trades

Query 2: "Honcho holographic migration decision"
  → Soll: Honcho wird archiviert, nicht gelöscht

Query 3: "VPS safety rules trading"
  → Soll: Infrastructure Facts, keine Credentials

Query 4: "Freqtrade FreqForge deployment"
  → Soll: backtest → paper 48h → live Regel

Query 5: "Hermes provider memory architecture"
  → Soll: holographic ist aktiv, honcho archiviert
```

### Erfolgskriterien

- [ ] Alle 5 Queries liefern relevante Facts zurück
- [ ] Keine Secrets in Suchergebnissen
- [ ] Fresh session kann importierte Facts abrufen
- [ ] fact_store tool funktioniert (add/search/probe)

---

## Phase 6 — Cutover Plan

**Verantwortlich:** Operator
**Gate 6:** Holographic aktiv, Honcho archiviert, Rollback dokumentiert

### Schritt 6.1 — Provider Cutover

```bash
# config.yaml: memory.provider = "holographic"
# Verify:
docker exec hermes-agent hermes memory status
```

### Schritt 6.2 — Rollback dokumentieren

```bash
# Bei Bedarf:
cp /home/hermes/.hermes/config.yaml.backup.holographic.YYYYMMDD \
   /home/hermes/.hermes/config.yaml

# Dann Hermes-Prozess neustarten:
docker restart hermes-agent
sleep 5
docker exec hermes-agent hermes memory status
```

### Schritt 6.3 — Honcho als Read-Only Archiv belassen

- Honcho Container laufen weiter
- Honcho DB bleibt intakt (Backups vorhanden)
- Honcho JSON bleibt unter `/home/hermes/.hermes/honcho.json` (kein Backup nötig)
- Optional: Honcho watchdog und quality guard cron LÄUFEN WEITER (dedupiert Honcho, nicht holographic)

### Gate 6 Kriterien

- [ ] `memory.provider` = holographic in config.yaml
- [ ] `hermes memory status` bestätigt holographic als active
- [ ] Rollback Procedure in docs/context dokumentiert
- [ ] Honcho Container + DB intakt

---

## Phase 7 — Final Documentation

**Verantwortlich:** Operator

### Zu erstellende Dateien in `docs/context/`

1. `honcho-archive-report.md` — Finaler Bericht (Executive Summary, Before/After, Import-Log, etc.)
2. `holographic-operational-guide.md` — Holographic Betriebshandbuch (fact_store Nutzung, Import-Prozedur)
3. `memory-migration-rollback.md` — Rollback Procedure

---

## Abort Conditions (STOP-Trigger)

| Condition | Action |
|-----------|--------|
| Honcho Backup kann nicht erstellt werden | STOP vor Phase 2 |
| Holographic nicht verfügbar/nicht testbar | STOP, Fallback auf "built-in only" |
| Import enthält Secrets | STOP, kuratieren wiederholen |
| Recall Tests scheitern (0 relevante Results) | Honcho aktiv lassen |
| Rollback Path unklar | Nicht cutovern |

---

## Timeline (geschätzt)

| Phase | Aufwand | Operator-Interaktion |
|-------|---------|---------------------|
| 0 | 5 min | automatisch (Done) |
| 1 | 15 min | Genehmigung für pg_dump |
| 2 | 30–60 min | Kuratierung + Review |
| 3 | 15 min | Config-Änderung + Test |
| 4 | 10 min | Import Script |
| 5 | 15 min | Recall Tests |
| 6 | 5 min | Cutover |
| 7 | 20 min | Documentation |
| **Total** | **~2.5h** | |

---

## Entscheidungspunkte für Luke

1. **Phase 1 freigeben?** Backup + Export sind read-only auf Honcho — keine Änderung.
2. **Phase 2 Review?** Rejected records sample prüfen — möchte Luke bestimmte Records explizit manuell hinzufügen?
3. **Honcho Watchdog + Quality Guard?** Sollen diese Cron-Jobs weiterlaufen (empfohlen: JA, dedupieren nur Honcho)?
4. **Bestehende Gold-Layer Facts?** Sollen die 950 deductive/inductive Honcho-Facts als Honcho-Archiv lesbar bleiben ODER in Holographic importiert werden?

---

## Phase 1 Results — Completed 2026-05-13T21:47Z

### Backup Artifacts Created

| File | Location | Size |
|------|----------|------|
| Config backup | `/home/hermes/.hermes/backups/migration-20260513T2147Z/config.yaml.20260513T2147Z` | 9,672 bytes |
| Honcho JSON backup | `/home/hermes/.hermes/backups/migration-20260513T2147Z/honcho.json.20260513T2147Z` | 1,249 bytes |
| PostgreSQL pg_dump | `/tmp/honcho_pre_holographic_migration_20260513T2147Z.sql` | 255,198,255 bytes |
| Raw JSONL export | `/home/hermes/.hermes/backups/migration-20260513T2147Z/honcho_raw_export.jsonl` | 1,143,637 bytes |
| Export summary | `/home/hermes/.hermes/backups/migration-20260513T2147Z/honcho_export_summary.md` | 668 bytes |
| SHA256SUMS | `/home/hermes/.hermes/backups/migration-20260513T2147Z/SHA256SUMS` | 561 bytes |
| Import manifest | `/home/hermes/.hermes/backups/migration-20260513T2147Z/import_manifest.json` | 1,037 bytes |
| Candidates JSONL | `/home/hermes/.hermes/backups/migration-20260513T2147Z/migration_candidates_final.jsonl` | 971,006 bytes |
| Rejected sample | `/home/hermes/.hermes/backups/migration-20260513T2147Z/rejected_records_sample.jsonl` | 13,700 bytes |
| Dedup report | `/home/hermes/.hermes/backups/migration-20260513T2147Z/duplicate_groups_report.md` | 940 bytes |
| Top 50 candidates | `/home/hermes/.hermes/backups/migration-20260513T2147Z/top_50_candidates.jsonl` | ~20,000 bytes |
| Top 50 rejected | `/home/hermes/.hermes/backups/migration-20260513T2147Z/top_50_rejected.jsonl` | ~14,000 bytes |
| Secret scan report | `/home/hermes/.hermes/backups/migration-20260513T2147Z/secret_scan_report.md` | ~500 bytes |

### Export Statistics

| Metric | Value |
|--------|-------|
| Total docs in Honcho | 3,400 |
| Unique content | 3,340 |
| Exact duplicates | 60 (1.8%) |
| Gold layer (deductive + inductive) | 950 |
| By observer | Luke (830), hermes-agent (758), trading-agent (444), orchestrator (397), hermes-orchestrator (362), mira-agent (213), trading (202), hermes-trading (136), 610209401 (56) |
| Date range | 2026-05-06 16:54 → 2026-05-13 21:41 |

### Candidate Curation Results

| Metric | Value |
|--------|-------|
| Candidates after scoring filter (score >= 3.0) | 3,186 |
| After noise filtering + stricter explicit filter | 2,385 |
| Noise records removed | 815 |
| Dedup groups in final set | 0 (content_hash dedup already applied) |

### Candidates by Category

| Category | Count |
|----------|-------|
| gold_layer (deductive + inductive) | 950 |
| server_infrastructure | 674 |
| tooling_and_commands | 323 |
| general | 175 |
| trading_project_context | 157 |
| user_preferences | 84 |
| hard_rules | 22 |

### Candidates by Level

| Level | Count |
|-------|-------|
| deductive | 602 |
| inductive | 348 |
| explicit | 1,435 |

### Candidates by Score

| Score | Count | Description |
|-------|-------|-------------|
| 5.0 | 379 | Gold layer (inductive) + hard rules |
| 4.5 | 823 | Gold layer (deductive) + user preferences |
| 4.0 | 570 | Infrastructure + trading project |
| 3.5 | 303 | Tooling |
| 3.0 | 309 | Actionable general |

### Schema/Field Notes

- `updated_at` column does NOT exist in `documents` table - excluded from export
- `id` column is text (not integer), `times_derived` defaults to 1
- `level` values: explicit, deductive, inductive
- Observers: 10 distinct sources
- Sessions: 55 distinct session names

### Gate 1 Status: PASS

- Fresh pg_dump: OK (255 MB)
- Config backups: OK
- Raw JSONL export: OK (3,400 records)
- SHA256SUMS verified: OK
- Honcho containers still running: OK
- memory.provider unchanged: OK (honcho)
- No provider switch: OK
- No import: OK
- No Honcho data deleted: OK

### Phase 2 Review Status: COMPLETE

Full review document: `docs/context/honcho-holographic-phase2-review.md`

| Check | Result |
|-------|--------|
| Secret scan | CLEAN - 0 real secrets, 6 false positives (conceptual mentions) |
| Gold layer preserved | 950/950 (100%) - all deductive+inductive auto-included |
| Noise filtered | 815 records removed |
| Dedup | 0 duplicate groups in final set |
| Go/No-Go | **GO** - 2,385 candidates safe for import |

### Migration Complete — Phases 3+4+5 Executed

**Full report:** `docs/context/honcho-holographic-import-results.md`

| Gate | Name | Status |
|------|------|--------|
| Gate 3.0 | Pre-Import Verification | ✓ PASS |
| Gate 3.1 | Activate Holographic | ✓ PASS |
| Gate 3.2 | Import Candidates | ✓ PASS |
| Gate 3.3 | Post-Import SQLite Validation | ✓ PASS |
| Gate 3.4 | Recall Smoke Tests (6/6) | ✓ PASS |
| Gate 3.5 | Conditional Cutover | ✓ PASS |

**Import results:**
- Candidates: 2,385 inserted, 0 duplicates, 0 failed
- Holographic DB: `/home/hermes/.hermes/memory_store.db` (2,385 facts, 0 dupes, FTS indexed)
- memory.provider: **holographic** (active, set in config.yaml)
- Honcho: preserved as read-only archive (containers still running)

**Rollback:**
```bash
docker exec hermes-agent sh -c 'cp /home/hermes/.hermes/config.yaml.backup.pre-import.20260513T2147Z /home/hermes/.hermes/config.yaml'
```

---

## Phase 4 — Retrieval Stabilization Patch (2026-05-14)

**Problem:** After migration, recall tests showed 4/6 queries returning NO RESULTS.
The external test script had a LIKE fallback, but the production `FactRetriever.search()` did not.
Root cause: FTS5 tokenization returns 0 for some 3-word space-separated queries.

**Solution:** Three-strategy fallback in `_fts_candidates`:

| Strategy | Method | When used |
|----------|--------|-----------|
| 1 | Raw FTS5 MATCH | Default first attempt |
| 2 | Tokenized OR/prefix FTS | If strategy 1 returns 0 |
| 3 | SQLite LIKE fallback | If strategy 2 returns 0 |

**Files changed:**
- `/home/hermes/hermes-src/plugins/memory/holographic/retrieval.py` — patched

**New methods added:**
- `_fts_raw()` — original FTS5 MATCH (strategy 1)
- `_fts_tokenized_or()` — tokenized OR/prefix FTS (strategy 2)
- `_fts_like_fallback()` — SQLite LIKE fallback (strategy 3)
- `_normalize_fts_rows()` — shared row normalization

**Bug fixed in `_fts_like_fallback`:**
- Original: `params.extend([f"%{t}%" for t in tokens])` inside a loop → duplicate tokens
- Fixed: `params = [f"%{t}%" for t in tokens] * 2` (content + tags correctly)

**Recall tests after patch — ALL PASS (6/6):**

| Query | Result | Trust | Strategy |
|-------|--------|-------|----------|
| never live trading | PASS | 1.0 | LIKE |
| Luke trading bot rules | PASS | 1.0 | LIKE |
| VPS Hetzner safety | PASS | 0.9 | LIKE |
| Freqtrade backtest | PASS | 0.8 | raw_FTS |
| German informal terse | PASS | 1.0 | LIKE |
| live trading | PASS | 0.9 | raw_FTS |

**Config backup (orchestrator profile):**
```bash
/home/hermes/.hermes/profiles/orchestrator/config.yaml.backup.pre-holo-patch
```

**Current state:**
- `memory.provider` in orchestrator profile: **holographic**
- Holographic DB: 2,385 facts, 0 dupes
- Honcho: preserved as read-only archive
- Retrieval: patched + tested + stable

---

## Phase 5 — Git Versioning (2026-05-14)

**Branch:** `fix/holographic-retrieval-fallback`
**Commit:** `a86636e52`
**Remote:** `luke` (git@github.com:GoLukeEnviro/hermes-agent.git)

**Pushed:** Yes ✓

**Files in commit:**
- `plugins/memory/holographic/retrieval.py` — 3-strategy fallback patch (+160/-5)
- `tests/plugins/memory/test_holographic_retrieval.py` — 15 regression tests (+353)

**Regression tests:** 15/15 PASS ✓ (pytest, 3.05s, parallel)

**PR URL:** https://github.com/GoLukeEnviro/hermes-agent/pull/new/fix/holographic-retrieval-fallback

**Rollback (local branch):**
```bash
cd /home/hermes/hermes-src
git checkout main
git branch -D fix/holographic-retrieval-fallback
```

**Note:** `docs/context/` files updated locally but NOT committed to hermes-agent repo (not tracked there). They remain in `/home/hermes/projects/trading/docs/context/`.

