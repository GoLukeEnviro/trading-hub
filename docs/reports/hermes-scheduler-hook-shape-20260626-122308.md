# Scheduler Hook Shape Capture — Read-only Audit

**Date (UTC):** 2026-06-26 12:23:08
**Auditor:** Hermes (orchestrator profile)
**Phase:** A1 — Phase 1 of Cron History Hook Repair (L2)
**Operation Level:** L0 (read-only)
**Target:** `/opt/hermes/cron/scheduler.py` (UNTOUCHED)
**Status:** GREEN — shape captured, hook design validated, ready for Phase 2

---

## Executive Verdict

**GREEN — 95/100** — Scheduler-Hook-Anker sind eindeutig identifiziert, ein AST-/Marker-basierter Patch ist sicher machbar, ohne dass der Scheduler danach anders aussieht als vorher. Die einzige Restunsicherheit ist die Re-Apply-Pflicht nach `hermes update` (siehe Pitfall im Skill).

## Inspectionsgegenstand

| Field | Value |
|-------|-------|
| Path | `/opt/hermes/cron/scheduler.py` |
| Lines | 2268 |
| Size | 97387 bytes |
| Mode | 0644 |
| Owner | 10000:10000 |
| mtime | 2026-06-09 15:52 UTC (from upstream install) |
| Is Git repo | **NO** (`/opt/hermes` ist KEIN Git-Repo) |
| Patch durability | **OVERWRITTEN BY `hermes update`** — Hook muss re-appliable sein |

## Kritische Funktionen und Variablen

### 1. `tick()` (Hauptschleife) → `_process_job(job)`

Beide relevanten Mark-Sites liegen in `_process_job` (Z. 2093–2135):

```python
def _process_job(job: dict) -> bool:
    """Run one due job end-to-end: execute, save, deliver, mark."""
    try:
        success, output, final_response, error = run_job(job)
        # ... delivery logic ...
        delivery_error = None
        if should_deliver:
            try:
                delivery_error = _deliver_result(...)
            except Exception as de:
                delivery_error = str(de)

        # Soft-fail bei leerer Agent-Response
        if success and not final_response.strip():
            success = False
            error = "Agent completed but produced empty response (...)"

        mark_job_run(job["id"], success, error, delivery_error=delivery_error)   # ← HOOK SITE A (Z. 2129)
        return True

    except Exception as e:
        logger.error("Error processing job %s: %s", job['id'], e)
        mark_job_run(job["id"], False, str(e))                                  # ← HOOK SITE B (Z. 2134)
        return False
```

**Verfügbare Variablen an beiden HOOK-Sites:**

- `job: dict` (komplettes Job-Dict, enthält `id`, `name`, `script`, `no_agent`, `deliver`, `schedule`)
- `success: bool`
- `output: str` (no_agent: captured stdout, agent: full_output_doc)
- `error: str | None`
- `delivery_error: str | None`
- `e: Exception` (nur Site B)
- `now_iso` nicht direkt verfügbar → `datetime.now(timezone.utc).isoformat()` benutzen

### 2. Import-Section (Z. 36–46)

Sicherer Insert-Punkt **nach** Z. 44 `from hermes_time import now as _hermes_now`:

```python
sys.path.insert(0, str(Path(__file__).parent.parent))     # Z. 39 — existiert bereits

from hermes_constants import get_hermes_home               # Z. 41
from hermes_cli._subprocess_compat import windows_hide_flags  # Z. 42
from hermes_cli.config import load_config, _expand_env_vars    # Z. 43
from hermes_time import now as _hermes_now                  # Z. 44 ← HIER danach einfügen
```

Hook-Import-Block wird hier eingefügt, mit:

1. `sys.path.insert(0, "/opt/data/profiles/orchestrator/scripts")` (vor writer-Import)
2. try/except Import von `run_with_history` aus `cron_history_writer`

### 3. `run_with_history` Writer-Side

Bereits in `cron_history_writer.py` (Z. 328) implementiert. Akzeptiert exakt die Felder, die `_process_job` an beiden Hook-Sites hat. Best-effort: alle internen Fehler werden geschluckt.

### 4. `_run_job_script` (no_agent path, Z. 957)

Nicht relevant für Hook-Stelle: stdout ist bereits in `output` von `run_job(job)` aggregiert. Hook muss nicht runter in `_run_job_script`.

## Hook-Strategie

### Marker-Pattern

Wir verwenden **eindeutige ASCII-Marker**, die per AST-Check / Regex-Lookup gefunden werden:

```python
# HERMES_CRON_HISTORY_HOOK_BEGIN
... (durch apply_cron_history_hook.py generierter Block) ...
# HERMES_CRON_HISTORY_HOOK_END
```

- **Import-Block Marker** direkt nach Z. 44
- **Call-Block Marker** direkt nach jedem der zwei `mark_job_run(...)` Calls

### Idempotenz

`--apply` prüft vor Insertion, ob `HERMES_CRON_HISTORY_HOOK_BEGIN` schon im File ist. Wenn ja: skip mit Status `ALREADY_PATCHED`.

### Backup-Manifest

`/opt/data/profiles/orchestrator/state/cron_history_patches/`:

```
scheduler.py.<YYYYMMDD_HHMMSS>.bak    # Backup
MANIFEST.jsonl                          # SHA256 + timestamp + reason per backup
```

### Target-SHA Capture

Vor `--apply` wird SHA256 des Originals gespeichert; bei `--rollback <backup>` wird SHA256 gegen Original-MANIFEST verifiziert.

## Generierte Hook-Inhalte

### Import-Block (inserted after `from hermes_time import now as _hermes_now`)

```python
# HERMES_CRON_HISTORY_HOOK_BEGIN
try:
    import sys as _hermes_cron_sys
    _HERMES_CRON_HISTORY_DIR = "/opt/data/profiles/orchestrator/scripts"
    if _HERMES_CRON_HISTORY_DIR not in _hermes_cron_sys.path:
        _hermes_cron_sys.path.insert(0, _HERMES_CRON_HISTORY_DIR)
    from cron_history_writer import run_with_history as _hermes_cron_run_with_history
except Exception:  # pragma: no cover - best-effort
    def _hermes_cron_run_with_history(*_a, **_kw):
        return False
# HERMES_CRON_HISTORY_HOOK_END
```

### Hook-Call-Block (inserted after each `mark_job_run(...)`)

```python
# HERMES_CRON_HISTORY_HOOK_CALL_BEGIN
try:
    _hermes_cron_run_with_history(
        job,
        no_agent=bool(job.get("no_agent")),
        status="ok" if success else "error",
        error_text=(error or delivery_error or None) if not success else None,
        stdout_text=(output if isinstance(output, str) else None),
        finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    )
except Exception:
    pass
# HERMES_CRON_HISTORY_HOOK_CALL_END
```

## Risikoeinschätzung

| Risiko | Wahrscheinlichkeit | Mitigation |
|--------|--------------------|------------|
| Patch überlebt `hermes update` nicht | HOCH | Skill-Pitfall dokumentiert; idempotenter Marker + Re-Apply-Skript |
| History-Fehler kippt Job-Status | NIEDRIG | try/except wrap, best-effort helper |
| Doppelinsert bei mehrfachem Apply | NIEDRIG | Marker-Detection vor Insertion |
| `py_compile` bricht nach Patch | NIEDRIG | Patch wird AST-/Indent-safe gebaut; Test-Fixture kompiliert |
| ImportError blockiert Scheduler | NIEDRIG | try/except im Import-Block, Fallback-Funktion no-op |
| jobs.json Mutation | UNMÖGLICH | Hook schreibt nirgendwo jobs.json |

## Pitfall: /opt/hermes ist NICHT Git-tracked

Bereits in `hermes-cron-runtime-contract` Skill dokumentiert. Konsequenzen:

- Hook darf in L2 nur die **Datei** ändern, nicht die `jobs.json`
- Nach jedem `hermes update` muss der Hook re-appliziert werden
- Re-Apply läuft idempotent (Marker-Detection) — kann via Cron-Job automatisiert werden, **aber** das ist ein separater L3-Schritt

## Stop-Conditions für Phase 2

- ✅ scheduler.py existiert (2268 Zeilen)
- ✅ Ziel-Funktionen lokalisiert
- ✅ Verfügbare Variablen dokumentiert
- ✅ Marker-Pattern definiert
- ✅ Import-Insertion-Punkt gewählt (nach Z. 44)
- ✅ Idempotenz-Strategie definiert
- ✅ Backup-Layout definiert

Alle Phase-2-Voraussetzungen erfüllt. Phase 2 kann starten.
