# Hermes Dashboard Memory Provider Endpoint Check

**Datum:** 2026-06-26T02:06:00Z  
**Container:** hermes-green (Hermes Agent v0.16.0, upstream c6dc2fcd, Image: nousresearch/hermes-agent:c11.2-hermes-home)  
**Audit-Typ:** Read-only

---

## Verdict: 🟢 CORE GREEN / 🟡 DASHBOARD YELLOW

**Core Mem0 Stack ist voll funktionsfähig.** Der Fehler im Dashboard ist ein Frontend/Backend-Route-Drift: der Backend-Route `/api/memory/providers/mem0/config` existiert (web_server.py:6694), aber **kein Frontend-Code ruft ihn auf**. Das Frontend nutzt nur `/api/memory`, `/api/memory/provider`, `/api/memory/reset`. Der Endpunkt ist orphaned.

---

## Core Mem0 Status: ✅ GREEN

| Komponente | Status | Details |
|---|---|---|
| green-mem0 API | ✅ OK | `/health` responds, actively processing (insert + query) |
| green-qdrant | ✅ OK | Collection `hermes_memories_v3` → 1936 points, 768d |
| green-ollama | ✅ OK | 4 models available, embeddings + chat completions flowing |
| Recall (read-only) | ✅ OK | `memories/search` returned 15 results with scores 0.57–0.64 |
| Mem0 write path | ✅ OK | Logs show active vector inserts (02:02 UTC) |
| Container health | ✅ OK | All 4 containers running, hermes-green up 45 min |

---

## Dashboard Endpoint Result

| Test | URL | Result |
|---|---|---|
| Container → endpoint | `http://127.0.0.1:9119/api/memory/providers/mem0/config` | **401 Unauthorized** |
| Host → endpoint | `http://127.0.0.1:8083/api/memory/providers/mem0/config` | **Connection refused** (port 8083 not bound on host) |

Der 401 kommt vom Dashboard-Auth-Middleware, nicht vom Route-Handler. Der Host-Port 8083 ist trotz Docker-Mapping (`127.0.0.1:8083->9119/tcp`) nicht erreichbar — separater Netzwerk-Issue.

---

## Route Inventory

### Backend (Container: `/opt/hermes/hermes_cli/web_server.py`)

| Zeile | Route | Status |
|---|---|---|
| 6611 | `@app.get("/api/memory")` | ✅ Existiert, von Frontend genutzt |
| 6694 | `@app.get("/api/memory/providers/mem0/config")` | ✅ Existiert, **NOT von Frontend genutzt** — orphaned |
| 8338 | `@app.get("/api/{path:path}")` SPA Fallback | ✅ Existiert — erzeugt "No such API endpoint" für unbekannte `/api/*` Pfade |

### Frontend (`web/src/lib/api.ts` + gebündeltes JS)

| Endpoint | Aufgerufen von | Im Bundle |
|---|---|---|
| `/api/memory` (GET) | `api.ts:861 getMemory()` | ✅ Ja |
| `/api/memory/provider` (POST) | `api.ts:863 setMemoryProvider()` | ✅ Ja |
| `/api/memory/reset` (POST) | `api.ts:869 resetMemory()` | ✅ Ja |
| `/api/memory/providers/mem0/config` | **Niemand** | ❌ **Nicht im Bundle** |

Beide JS-Bundles (Container `index-DauAC2x2.js` und Host-Cache `index-D6vfG-wo.js`) enthalten **keinen** Verweis auf `/api/memory/providers/mem0/config`.

---

## Likely Root Cause

**Route-Drift mit orphaned Backend-Route.** Der Endpunkt `/api/memory/providers/mem0/config` wurde im Backend implementiert (v0.16.0, web_server.py:6694) aber **nie im Frontend verdrahtet**. Die Dashboard-UI zeigt Memory-Provider-Status über `/api/memory` (GET) an, nicht über den spezifischen Config-Endpunkt.

Mögliche Erklärung der Fehlermeldung:
1. **Browser-Cache** — alter Frontend-Build mit einem Test-Aufruf des Endpunkts, der nach Container-Neustart 401/SPA-Fallback traf
2. **Dashboard-Extension/Plugin** — ein dynamisch geladenes Plugin oder Bookmarklet hat diesen Pfad aufgerufen
3. **Caddy Reverse-Proxy** — wenn der Dashboard-Zugriff über Caddy läuft, könnte ein Rewrite/Routing-Issue den Request auf einen ungültigen Pfad umleiten

Die Fehlermeldung "No such API endpoint: /api/memory/providers/mem0/config" entspricht exakt dem SPA-Fallback-Format (web_server.py:8338). Der Fallback wird nur für `/api/*` Pfade getriggert, die **kein** gematchtes Backend-Route haben. Da der Route existiert, muss der Request entweder (a) nicht beim Dashboard-Server angekommen sein, oder (b) ein anderes Format/Variante des Pfads verwendet haben.

---

## Fix Recommendation

1. **Frontend-Integration (optional):** Den orphaned Backend-Route im Frontend verdrahten, z.B. in der Memory-Sektion der ConfigPage.tsx oder PluginsPage.tsx. Der Route liefert bereits sanitisierte Config-Daten (provider, enabled, mode, local_mem0_api_url, rerank, user_id — keine Secrets).

2. **Alternativ: Route entfernen** wenn keine Frontend-Integration geplant ist. Reduziert Angriffsfläche.

3. **Host-Port 8083:** Docker-Port-Mapping überprüfen. `docker port hermes-green` zeigt `9119/tcp -> 127.0.0.1:8083` aber Host-seitig ist 8083 nicht gebunden. Möglicherweise rootless-Docker-Port-Konflikt.

4. **Auth-Middleware:** `--insecure` Flag sollte API-Auth für Dashboard-Endpunkte deaktivieren, aber curl von innen gibt 401. Auth-Middleware-Logik prüfen.

---

## Risks

| Risiko | Schwere | Beschreibung |
|---|---|---|
| Kein Recall-Betrieb betroffen | — | Alle Memory-Operationen (write, recall, search) funktionieren normal |
| Kein Agent-Lauf betroffen | — | Gateway nutzt Memory-Plugin intern, nicht den Dashboard-Endpunkt |
| Host-Port 8083 unerreichbar | 🟡 Mittel | Dashboard ist vom Host nicht direkt erreichbar (nur via Caddy/Netzwerk) |

---

## Next Action

1. **Option A (bevorzugt):** Frontend-Route `/api/memory/providers/mem0/config` in PluginsPage.tsx oder ConfigPage.tsx verdrahten — zeigt Mem0-Config-Status im Dashboard.
2. **Option B:** Orphaned Route entfernen, wenn nicht benötigt.
3. **Optional:** Host-Port 8083 Docker-Netzwerk-Issue separat untersuchen.
4. **Verify:** Nach Fix: Dashboard-Page hard-refreshen und Memory-Provider-Status prüfen.

---

*Audit abgeschlossen. Keine Mutationen durchgeführt. Keine Secrets exponiert.*
