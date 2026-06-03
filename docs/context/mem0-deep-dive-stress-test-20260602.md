# Mem0 Deep Dive Stress Test — 2026-06-02

**Datum:** 2026-06-02 17:15 UTC
**Model:** glm-5.1 via Z.AI
**Tester:** Hermes Orchestrator (autonomous)

---

## 1. Executive Summary

| Dimension | Status | Details |
|-----------|--------|---------|
| Docker Stack | GREEN | Alle 4 Container running (34h - 4d uptime) |
| REST API | GREEN | Health ok, 0 Fehler in 30min, 0 Cloud-Calls |
| Plugin Bridge | RED | MemoryClient-Import, kein REST-Bridge — Hermes-native mem0_* Tools kaputt |
| Datenintegrität | GREEN | 982 Memories, 1024d Cosine, Altersverteilung gesund |
| Search Quality | YELLOW | AVG 0.777 — knapp unter Gate 0.78 |
| Write Performance | GREEN | 6.0s (Cloud LLM), as expected |
| Extraction Policy | GREEN | Temporäre Inputs blockiert, Durable-Inputs deduped (kein Fehler) |
| Fault Tolerance | GREEN | Unicode, Long-Query, Unknown-User, High-Limit — alle stabil |
| Ressourcen | GREEN | 158MB mem0 + 141MB Qdrant + 3.4GB Ollama — moderat |
| Monitoring | GREEN | Watchdog OK, Scheduler tickt, Restart unless-stopped |
| Backups | RED | Keine Qdrant-Snapshots vorhanden |

**GESAMTVERDICT: WARNING**
REST API und Stack sind gesund. Aber: Plugin Bridge kaputt (P1), keine Qdrant-Backups (P2), Search Quality marginal unter Gate (P3).

---

## 2. Docker Runtime Topologie

```
Container          Image                             Status         Ports
green-mem0         hermes-mem0-local-api:stable      Up 34h (ok)    127.0.0.1:8788->8787
green-ollama       ollama/ollama:latest              Up 4d          127.0.0.1:11436->11434
green-qdrant       qdrant/qdrant:latest              Up 4d          127.0.0.1:6336->6333
hermes-green       nousresearch/hermes-agent:latest  Up 7h          127.0.0.1:8642->8642, :8083->9119
```

**Network:** hermes-green_green-net (single bridge)
**Restart Policy:** unless-stopped (alle Container)
**Volumes:** green-qdrant-data (persistent), green-ollama-data (persistent)
**Green-mem0:** KEINE Volumes (config baked in image)

---

## 3. Qdrant Collection Inventory

| Collection | Dimensions | Distance | Status |
|-----------|-----------|----------|--------|
| hermes_memories_v2 | 1024 | Cosine | AKTIV (qwen3-embedding:4b) |
| hermes_memories | 768 | Cosine | LEGACY (nomic-embed-text) |
| mem0migrations | - | - | System |

---

## 4. Mem0 Health & Config

```json
{
  "status": "ok",
  "backend": "local-mem0",
  "vector_store": "qdrant",
  "llm_provider": "ollama",
  "llm_model": "gpt-oss:120b",
  "embedder_provider": "ollama",
  "embedder_model": "qwen3-embedding:4b",
  "cloud_required": false,
  "extraction_policy": "v1"
}
```

**Env-Vars (bestätigt):**
- MEM0_COLLECTION=hermes_memories_v2
- OLLAMA_BASE_URL=http://green-ollama:11434
- QDRANT_HOST=green-qdrant
- MEM0_EMBEDDER_MODEL=qwen3-embedding:4b
- MEM0_EMBEDDING_DIMS=1024
- OPENROUTER_API_KEY nicht gesetzt (gut — blockiert Cloud-Hijack)

**Extraction Policy:** Health meldet "v1" (nicht "v1.2"). Möglicher Diskrepanz — Skill dokumentiert v1.2 als aktiv.

---

## 5. Plugin Bridge Status — RED

**Befund:** `/opt/hermes/plugins/memory/mem0/__init__.py` enthält:
- 2 Referenzen auf `MemoryClient` / `from mem0 import` (legacy SDK)
- 0 Referenzen auf `_rest_get` / `_rest_post` / `requests` (REST bridge fehlt)

**Auswirkung:**
- `mem0_profile()` → "mem0 package not installed"
- `mem0_search()` → "mem0 package not installed"
- `mem0_conclude()` → "mem0 package not installed"

**Ursache:** Hermes-Update hat die REST-Bridge überschrieben (bekanntes Problem seit 2026-05-22).

**Workaround aktiv:** Direkte REST-Aufrufe via `execute_code` + `docker exec green-mem0 curl localhost:8787` funktionieren.

**Behebung:** REST-Bridge-Pattern muss erneut angewendet werden (Skill dokumentiert den Fix).

---

## 6. Datenintegrität

### Memory Count: 982
### Altersverteilung:

| Altersgruppe | Count | Anteil |
|-------------|-------|--------|
| < 24h | 12 | 1.2% |
| 1-7d | 3 | 0.3% |
| 7-30d | 967 | 98.5% |
| > 30d | 0 | 0% |
| Parse-Fehler | 0 | 0% |

**Bewertung:** 98.5% der Memories sind 7-30 Tage alt — bulk import aus der Migrierungsphase. Wenig frisches Wachstum (12 in <24h), was auf geringe conclude-Aktivität hindeutet (Plugin Bridge kaputt).

---

## 7. Search Quality Benchmark

| Query | Top Score |
|-------|-----------|
| trading bot configuration | 0.7908 |
| Docker infrastructure setup | 0.7473 |
| Ollama embedding model | 0.8566 |
| Freqtrade stoploss ATR | 0.8172 |
| user communication preferences | 0.7322 |
| memory backfill pipeline | 0.7394 |
| Qdrant vector store dimensions | 0.8056 |
| extraction policy durable facts | 0.7393 |
| hermes agent config yaml | 0.7779 |
| paper trading dry run safety | 0.7621 |

**AVG: 0.7768** — Gate PASS >= 0.78 → **FAIL (knapp)**
**Best:** Ollama embedding model (0.857)
**Worst:** user communication preferences (0.732)

---

## 8. Performance

| Operation | Latenz | Bewertung |
|-----------|--------|-----------|
| Health GET | 1.6ms | Ausgezeichnet |
| List All (982 items) | 46ms | Ausgezeichnet |
| Search (Avg 5 Samples) | 553ms | Gut |
| Search (First call) | 1.3s | Kaltstart-Effekt |
| Search (Warm) | 300-560ms | Gut |
| Write (Cloud LLM) | 6.0s | Erwartet (gpt-oss:120b via Ollama Cloud) |

---

## 9. Fault Tolerance Tests

| Test | Ergebnis | Bewertung |
|------|---------|-----------|
| Empty Query | status=null, 0 Results | Korrekt — leer gibt nichts |
| Long Query (1000 chars) | status=ok, 20 Results | Stabil |
| Unicode/Sonderzeichen | status=ok, 20 Results | Stabil |
| Unknown User | status=ok, 0 Results | Korrekt — keine Daten |
| High Limit (1000) | status=null, 0 Results | Grenzwertig — 0 statt max |
| GET /all ohne user_id | 422 Validation Error | Korrekt — user_id required |

---

## 10. Ressourcen-Verbrauch

| Container | CPU | RAM | Disk |
|-----------|-----|-----|------|
| green-mem0 | 0.18% | 158 MB | baked (kein Volume) |
| green-qdrant | 0.29% | 141 MB | 2.7 GB |
| green-ollama | 0.00% | 3.37 GB | 5.1 GB |
| **Total** | **0.47%** | **3.67 GB** | **7.8 GB** |

---

## 11. Monitoring & Cron

| Komponente | Status |
|-----------|--------|
| Watchdog Script | Vorhanden, ausführbar |
| Watchdog letzter Run | OK — 982 Memories, API reachable |
| Scheduler Tick | 17:12 UTC (aktuell) |
| Restart Policy | unless-stopped (alle) |
| Qdrant Snapshots | **KEINE vorhanden** |
| Memory Backfill Script | Vorhanden (37KB, aktuell) |
| Backfill Logs | Keine gefunden |
| Cron Jobs (mem0-bezogen) | Keine in jobs.json aufgelistet |

---

## 12. Ollama Modelle

| Modell | Größe | Typ |
|--------|-------|-----|
| qwen3-embedding:4b | 2.5 GB | AKTIV (Embeddings, 2560→1024d) |
| nomic-embed-text:latest | 274 MB | LEGACY Backup |
| qwen2.5:3b | 1.9 GB | Fallback LLM |
| mxbai-embed-large:latest | 669 MB | Inaktiv (NICHT kompatibel mit v2 Collection) |
| gpt-oss:120b-cloud | - | Cloud Proxy (extrahiert Fakten) |

---

## 13. Identifizierte Schwachstellen

### P1 — Plugin Bridge kaputt [CRITICAL]
- Hermes-native `mem0_*` Tools funktionslos
- Jeder Agent-Session verliert automatische Memory-Integration
- Behelf: Direkte REST-Aufrufe via execute_code
- **Fix:** REST-Bridge in `/opt/hermes/plugins/memory/mem0/__init__.py` erneut anwenden

### P2 — Keine Qdrant-Snapshots [HIGH]
- 982 Memories haben kein Backup auf Qdrant-Ebene
- Container-Recreate oder Volume-Verlust = Datenverlust
- **Fix:** Snapshot erstellen: `POST /collections/hermes_memories_v2/snapshots`

### P3 — Search Quality marginal unter Gate [MEDIUM]
- AVG 0.777 vs Gate 0.78 — nur 0.003 unter dem Schwellenwert
- 3 Queries unter 0.75 (preferences, backfill, extraction policy)
- Ursache: Query-Terminologie vs Storage-Terminologie Diskrepanz
- **Beobachtung:** Keine Sofortaktion, aber Trend überwachen

### P4 — Extraction Policy Version Diskrepanz [LOW]
- Health meldet "v1", Skill dokumentiert "v1.2"
- Entweder Policy nicht korrekt geladen oder Health-Endpoint nicht aktualisiert
- **Prüfung:** Policy-Datei im Container inspizieren

### P5 — Geringes Memory-Wachstum [LOW]
- Nur 12 Memories in <24h, 3 in 1-7d
- Plugin Bridge kaputt = kein automatisches conclude
- Memory Backfill hat keine Logs — unklar ob Cron aktiv
- **Fix:** Plugin Bridge reparieren löst dieses Problem indirekt

---

## 14. Empfehlungen (priorisiert)

1. **[P1] Plugin Bridge reparieren** — REST-Bridge Pattern aus Skill anwenden
2. **[P2] Qdrant Snapshot erstellen** — Einmalig, dann als Cron alle 7 Tage
3. **[P3] Search Quality beobachten** — Nächsten Benchmark nach Bridge-Fix
4. **[P4] Policy Version prüfen** — Container-Inspektion der Policy-Datei
5. **[P5] Memory Backfill Cron prüfen** — Job in jobs.json eintragen falls fehlend
