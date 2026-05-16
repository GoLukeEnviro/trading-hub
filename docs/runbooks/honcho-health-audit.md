# Honcho Health Audit — Runbook

**Typ:** Read-Only Audit
**Zweck:** Honcho-API und Datenbank-Gesundheit prüfen ohne Eingriff

---

## Constraints (non-negotiable)

- Keine Datenbank-Mutationen
- Keine Service-Restarts
- Keine ENV-Änderungen
- Keine Container-Erstellung oder -Löschung
- Read-Only Inspection nur

---

## Audit Steps

### 1. Container Status

```bash
docker ps -a --filter "name=honcho"
```

### 2. Port Mapping

```bash
docker port honcho-api-1
```

### 3. PostgreSQL Document Count (Direct Query)

```bash
docker exec honcho-database-1 psql -U postgres -d honcho -c "SELECT COUNT(*) FROM documents;"
```

### 4. Container Logs (Last 20 Lines)

```bash
docker logs honcho-api-1 --tail 20
docker logs honcho-database-1 --tail 20
```

### 5. API Endpoint Check (From Host)

```bash
curl -s --connect-timeout 5 http://localhost:8000/v1/healthcheck
curl -s --connect-timeout 5 http://127.0.0.1:8000/v1/healthcheck
```

### 6. API Endpoint Check (From Container Network)

```bash
docker exec honcho-api-1 curl -s --connect-timeout 5 http://localhost:8000/v1/healthcheck
```

---

## Decision Matrix

| Check | Result | Classification | Action |
|-------|--------|---------------|--------|
| Container Running | false | DOWN | Eskalation |
| Container Running | true + Port Mapped | check API | weiter mit Schritt 5 |
| API Response 200 | true | HEALTHY | Kein Handlungsbedarf |
| API Response Non-200 | true | DEGRADED | Logs prüfen (Schritt 4) |
| API Timeout/Error | — | UNREACHABLE | Container-Netzwerk prüfen |
| DB Count | 0 | EMPTY | Warnung — keine Dokumente |
| DB Count | > 0 | OK | DB funktioniert |

---

## Escalation Criteria

Wenn nach Schritt 4+5+6 keine Klarheit:

1. Luke über Telegram informieren
2. Geplante Diagnose-Aktion nennen
3. Explizite Freigabe für Eingriffe abwarten

**Kein Service-Restart ohne Freigabe.**

---

## Referenz

- Honcho Container: `honcho-api-1`, `honcho-database-1`
- API Port: 8000/tcp → 127.0.0.1:8000
- Database: PostgreSQL, DB=honcho
- writeFrequency: session (unverifiziert)
- Document Count (letzte Prüfung): 3,509 (2026-05-14)
- Operational State: `docs/state/current-operational-state.md`