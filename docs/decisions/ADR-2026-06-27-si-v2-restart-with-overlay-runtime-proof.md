# ADR — SI-v2 Restart-with-Overlay RuntimeProof

## Status
**Proposed / Planner implemented / Runtime execution intentionally blocked**

## Context

Phase 2 (2026-06-27) hat ergeben:

```
RuntimeEffectProof Verdict: YELLOW — RESTART_WITH_OVERLAY_REQUIRED
```

Der Canary-Prozess (`trading-freqtrade-freqforge-canary-1`) läuft mit:

```
freqtrade trade --config /freqtrade/user_data/config.json --strategy FreqForge_Override
```

Ein Overlay, das durch `execute_apply()` geschrieben wird, ist im Container sichtbar (korrekter Bind-Mount), wird aber vom laufenden Prozess nicht konsumiert, da Freqtrade Config nur beim Start lädt.

Der non-canary FreqForge-Bot beweist, dass Multi-Config grundsätzlich funktioniert:

```
freqtrade trade --config /freqtrade/user_data/config.json \
  --config /freqtrade/user_data/overlay_65502d13.json \
  --strategy FreqForge_Override
```

`show-config` bestätigt dort Overlay-Werte (`stake_amount: 50 → "unlimited"`).

## Decision

### 1. Trennung von Apply und Restart

| Phase | Funktion | Verantwortung |
|-------|----------|---------------|
| Apply | `execute_apply()` | Overlay-Datei schreiben, Audit-Event, Snapshot/Rollback-Metadaten |
| Plan | `plan_canary_restart_with_overlay()` | Read-only RestartPlan bauen, validieren |
| Execute | `execute_canary_restart_with_overlay()` | **Hard-blocked** in Phase 3B-A |

### 2. RestartPlan als deterministische Datenstruktur

Der `RestartPlan` enthält:

- `bot_id`, `container_name`, `service_name`
- `host_overlay_path`, `container_overlay_path`, `overlay_sha256`
- `current_command`, `proposed_command`, `rollback_command`
- `expected_parameter`, `expected_value`
- `safety_checks` (dict aller Gates)
- `blocked_reasons` (leer wenn ready)

### 3. Kein ad-hoc Docker-Restart

`docker restart` ändert den Container-Command nicht. Ein späterer Runtime-Schritt muss einen kontrollierten Recreate/Compose-Recreate-Pfad verwenden (`docker compose -f docker-compose.yml -f override.yml up -d`).

### 4. Runtime execution bleibt hard-blocked

`execute_canary_restart_with_overlay()` gibt immer `NOT_IMPLEMENTED` zurück. Ein echter Restart erfordert:

- Separates L3 Token (`APPROVE_SI_V2_CANARY_RESTART_WITH_OVERLAY`)
- Genehmigten Runtime Executor
- Proof GREEN nach Restart
- Rollback-Command vorbereitet

## Architecture

```
execute_apply()
  → schreibt overlay_<sha>.json
  → schreibt Apply-/Audit-Event
  → schreibt Snapshot/Rollback-Metadaten
  → KEIN Restart, KEIN Docker, KEIN Compose

plan_canary_restart_with_overlay()
  → read-only
  → baut RestartPlan
  → validiert Canary, Overlay, SHA, forbidden keys, dry_run, Commandline
  → KEINE Runtime-Mutation

execute_canary_restart_with_overlay()
  → HARD-BLOCKED (NOT_IMPLEMENTED)
  → erfordert separates L3 Token in Zukunft

RuntimeEffectProof (nach Restart)
  → Proof C: Prozess-Commandline enthält Overlay
  → Proof A: show-config enthält erwarteten Wert
  → Proof B: Merged-Config-Fallback
  → Composite GREEN → measurement_allowed=true, mutation_counter++

Measurement Window (nur nach GREEN)
  → T0: sofort
  → T1: +1h
  → T2: +6h
  → T3: +24h
```

## RestartPlan Contract

```python
@dataclass(frozen=True)
class RestartPlan:
    plan_id: str
    bot_id: str
    container_name: str
    service_name: str | None
    host_overlay_path: str
    container_overlay_path: str
    overlay_sha256: str
    base_config_container_path: str
    current_command: tuple[str, ...]
    proposed_command: tuple[str, ...]
    rollback_command: tuple[str, ...]
    expected_parameter: str
    expected_value: object
    safety_checks: dict[str, bool]
    blocked_reasons: tuple[str, ...]
    created_at_utc: str
```

## Safety Invariants

| Invariant | Erzwungen durch |
|-----------|-----------------|
| Canary-only | `_check_canary_only()` — blockiert alle nicht-`freqtrade-freqforge-canary` |
| Overlay im Canary user_data | `_check_overlay_path()` — resolved path muss unter canary user_data liegen |
| Keine forbidden keys | `_check_overlay_content()` — `RESTART_FORBIDDEN_KEYS` (9 Keys) |
| `dry_run=true` | `_check_dry_run()` — fehlend/false → blocked |
| Command hat `--config` | `_check_current_command()` — kein `--config` → blocked |
| Kein Overlay-Duplikat | `_build_proposed_command()` — überspringt wenn bereits vorhanden |
| Rollback ohne Overlay | `_build_rollback_command()` — entfernt alle `overlay_`-Configs |
| Kein subprocess/Docker | Planner ist pure Python — keine subprocess calls |
| Kein echter Restart | `execute_canary_restart_with_overlay()` gibt `NOT_IMPLEMENTED` |

## Forbidden Keys (RESTART_FORBIDDEN_KEYS)

```
dry_run
strategy
pair_whitelist
exchange
api_server
db_url
user_data_dir
telegram
external_message_consumer
```

Erweitert `SAFETY_FORBIDDEN_KEYS` aus `overlay_merge.py` um `strategy`, `pair_whitelist`, `db_url`, `user_data_dir`.

## Rollback Plan

### Rollback A — Overlay geschrieben, Restart noch nicht erfolgt

- Overlay-Datei ignorieren oder entfernen.
- Kein Runtime-Effekt.
- Kein Measurement.

### Rollback B — Restart mit Overlay erfolgt, Proof RED/YELLOW

- Compose-Override-Datei quarantainen.
- Canary mit Base-Command neu starten (ohne Override).
- `show-config` beweist Baseline.
- Overlay-Datei nach Snapshot entfernen.

### Rollback C — Measurement läuft, Metriken verschlechtern sich

- Measurement Window als `rollback_attributed` schließen.
- Canary zurück auf Base-Config starten.
- ShadowLogger Rollback-Event schreiben.

## Required Tests Before Execution

| # | Test | Status |
|---|------|--------|
| 1 | Valid canary overlay produces ready RestartPlan | ✅ Implementiert |
| 2 | Wrong bot is blocked | ✅ Implementiert |
| 3 | Missing overlay file is blocked | ✅ Implementiert |
| 4 | Overlay outside canary user_data is blocked | ✅ Implementiert |
| 5 | Overlay with dry_run key is blocked | ✅ Implementiert |
| 6 | Overlay with strategy key is blocked | ✅ Implementiert |
| 7 | Overlay with pair_whitelist key is blocked | ✅ Implementiert |
| 8 | Overlay with exchange key is blocked | ✅ Implementiert |
| 9 | dry_run false in pre_apply_config blocks | ✅ Implementiert |
| 10 | Missing dry_run in pre_apply_config blocks | ✅ Implementiert |
| 11 | Current command without base config blocks | ✅ Implementiert |
| 12 | Proposed command appends overlay after base config | ✅ Implementiert |
| 13 | Proposed command does not duplicate overlay | ✅ Implementiert |
| 14 | Rollback command equals base command | ✅ Implementiert |
| 15 | Plan includes overlay sha256 | ✅ Implementiert |
| 16 | Plan is JSON-serializable (to_dict) | ✅ Implementiert |
| 17 | execute is hard-blocked / NOT_IMPLEMENTED | ✅ Implementiert |
| 18 | No subprocess/docker call in planner | ✅ Implementiert |
| 19 | Non-canary overlay anomaly is rejected | ✅ Implementiert |
| 20 | Expected parameter and value stored in plan | ✅ Implementiert |

## Open Risks

| Risiko | Mitigation |
|--------|------------|
| Compose-Override verweist auf falsches Overlay | Restart-Gate prüft SHA vor Restart |
| Stale Overlay-Dateien | Cleanup-Skript nach Apply; Overlay-Pfad ist deterministisch |
| Non-Canary Overlay-Anomalie (`overlay_65502d13.json` auf `freqforge`) | Historisch/Deferred — nicht im Apply-Pfad für Canary |
| Token-Hardening (statisches Token) | Design akzeptiert statisches Token für Phase 3B-A. Später: Time-limited oder Hermes-sourced |
| `docker compose up` als Restart-Mechanismus | Bewährter Compose-Mechanismus. `up -d` stoppt alten und startet neuen Container |
| SAFE_PARAMETERS vs SAFETY_REQUIRED_KEYS Inkonsistenz | safe_parameters.py (6 Keys) dominiert Apply-Pfad. Harmonisierung ist Hygiene-Track |

## Next Step

**Luke bewertet diesen ADR und gibt Freigabe für Merge des RestartPlan-Implementierungs-PRs.** Nach Merge: Phase 3B-B (Compose-Override-Generator + Restart-Gate-Checker) oder Phase 3C (Runtime Executor Sprint) — je nach Lukes Priorisierung.
