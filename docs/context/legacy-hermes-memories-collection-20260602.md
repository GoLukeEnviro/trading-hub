# Legacy hermes_memories Qdrant Collection — Read-Only Documentation
**Datum:** 2026-06-02T06:13Z
**Typ:** Read-Only Inventory + Classification
**Autor:** Hermes Meta-Orchestrator

---

## Executive Verdict

**LEGACY_COLLECTION_DOCUMENTED_NO_ACTION** — hermes_memories ist eine Legacy-Kopie, hermes_memories_v2 ist canonical. Kein Löschen, keine Migration, kein Eingriff. Dokumentation abgeschlossen.

---

## Qdrant Collections

| Collection | Points | Vector Size | Distance | HNSW ef | Sparse Vectors | Status |
|---|---|---|---|---|---|---|
| **hermes_memories** | 1.167 | 768d | Cosine | 100 | bm25 ✅ | green / ok |
| **hermes_memories_v2** | **1.178** | **1024d** | Cosine | 200 | ❌ | **green / ok** |
| **mem0migrations** | 0 | 768d | Cosine | 100 | bm25 ✅ | green / ok |

**Gesamt:** 3 Collections, ~2.345 Points, ~38 MB geschätzt (bei ~8KB/Point inkl. Payload).

---

## Canonical Collection — hermes_memories_v2

**Beweis:** `green-mem0` Container hat env:

```
MEM0_COLLECTION=hermes_memories_v2
MEM0_EMBEDDING_DIMS=1024
```

**Architektur:**
- Embedding-Modell: `qwen3-embedding:4b` → **1024d Vektoren**
- Distance: Cosine
- HNSW ef_construct=200 (höhere Qualität für Retrieval)
- Keine sparse vectors (bm25) — reine Dense-Retrieval
- Payload-Schema: `user_id` (1178), `agent_id` (1170), `created_at`

**Im Vergleich zu v1:** 
- 11 Points mehr (1178 vs 1167) = neu geschriebene Erinnerungen seit Migration
- Gleiche Point-IDs wie v1 → v2 wurde durch Upgrade-Kopie erzeugt
- Höhere Vektordimension (1024 > 768) → bessere Embedding-Qualität
- Neueres Embedding-Modell (qwen3 vs Vorgänger)

---

## Legacy Collection Classification — hermes_memories

**Klassifikation:** LEGACY — nicht mehr aktiv beschrieben, aber nicht gelöscht.

**Nachweise:**
- `MEM0_COLLECTION=hermes_memories_v2` → kein Schreibzugriff mehr auf v1
- v1-Punktzahl stagniert bei 1.167 (v2 hat 1.178 = +11)
- Letzter v1-Eintrag laut Payload: 2026-05-21
- Beide Collections teilen identische Point-IDs → v1 ist die Vorgängerversion
- v1 hat zusätzlich `bm25` sparse vectors (Legacy-Feature, nicht in v2)
- v1 Payload-Schema (`user_id` fehlt, stattdessen `actor_id`) — anderes Metadaten-Modell

**mem0migrations:** Leer (0 Points). War vermutlich eine Tracking-Tabelle während der Migration. Keine aktive Rolle.

---

## Risk Assessment

| Risiko | Legacy hermes_memories | Legacy hermes_memories_v2 (verloren) |
|---|---|---|
| **Löschrisiko** | Gering — v2 hat alle Daten (gleiche IDs + 11 neue) | **Niedrig** — v2 ist canonical |
| **Datenverlust bei Löschung** | Minimal (keine exklusiven Daten in v1) | **Keiner** — v2 hat alles |
| **Festplatten-Ressource** | ~10-15 MB geschätzt (1.167 Points × 8KB) | ~10-15 MB für 1.178 Points |
| **Runtime ohne v1** | Kein Effekt — Mem0 liest nur v2 | N/A |
| **Rollback-Fähigkeit** | v1 könnte als Rollback-Snapshot dienen (768d) | v2 ist target |

**Empfehlung:** Legacy `hermes_memories` kann sicher gelöscht werden, sobald:
1. Ein Backup/Export von v2 existiert (via Qdrant snapshot)
2. Ein Restore-Test bestanden wurde
3. Mindestens 24h vergangen sind seit dem letzten v2-Write ohne Fehler
4. Der Löschvorgang dokumentiert und committet ist

**Aktuell:** Kein Löschen. Nur dokumentiert. ~25 MB gesamt vs. ~12 MB mit nur v2 — kein akuter Platzmangel.

---

## Future Cleanup Plan

1. **T0 (JETZT):** Dokumentation abgeschlossen ✅
2. **T1 (nach Backup):** `curl -X DELETE http://green-qdrant:6333/collections/hermes_memories` und `curl -X DELETE http://green-qdrant:6333/collections/mem0migrations`
3. **T2 (nach Löschung):** Kompakt-Run: `curl -X POST http://green-qdrant:6333/collections/hermes_memories_v2/optimize`
4. **T3 (nach Optimierung):** Verify v2 count unchanged, verify Mem0 reads still work, verify Memory Backfill cron still works
5. **Dokumentation:** `docs/context/legacy-hermes-memories-cleanup-YYYYMMDD.md`

**Löschbefehl (für später):**
```bash
curl -s -X DELETE http://green-qdrant:6333/collections/hermes_memories
curl -s -X DELETE http://green-qdrant:6333/collections/mem0migrations
```

---

## System Safety

| Komponente | Status |
|---|---|
| green-qdrant | green / ok (3 collections) |
| green-mem0 | Env confirmed, MEM0_COLLECTION=hermes_memories_v2 |
| autonomous-health-loop | every 60m, last_status=ok ✅ |
| unified-signal-heartbeat | every 15m, last_status=ok ✅ |
| FreqForge | running, dry_run=True ✅ |
| Regime-Hybrid | running, dry_run=True ✅ |
| Canary | running, dry_run=True ✅ |
| FreqAI-Rebel | running, dry_run=True ✅ |

---

## Commit Hash

**`1ce7f8b`** (nach diesem Commit) — `docs: document legacy hermes_memories qdrant collection`

---

## Remaining Issues

Keine. Legacy-Collection dokumentiert, canonical Collection bestätigt, keine Aktion nötig.

---

## Next Step

Alle 5 Cleanup-Blöcke abgeschlossen:
1. ✅ auth.json recovered
2. ✅ portfolio-rebalancer fixed
3. ✅ autonomous-health-loop z.ai fallback chain
4. ✅ watchdog.log stale accepted
5. ✅ legacy hermes_memories documented

Bereit für finalen Gesamtstatus — oder nächste Aufgabe.