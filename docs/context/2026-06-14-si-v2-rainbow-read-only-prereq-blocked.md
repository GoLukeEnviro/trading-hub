# 2026-06-14 — SI v2 Rainbow fixture → read_only: PRE-REQUISITE BLOCKED

> **SUPERSEDED** by PR #215 and
> [`2026-06-14-si-v2-rainbow-read-only-runtime-source.md`](2026-06-14-si-v2-rainbow-read-only-runtime-source.md).
> This file remains as **historical blocker evidence** documenting the
> state at 2026-06-14T19:00 UTC, before the env-override bridge
> (`SI_V2_RAINBOW_BASE_URL` / `…_ENDPOINT_PATH` / `…_TIMEOUT_SECONDS`),
> the DB-backed stub, and the freshness guard were merged. The
> pre-requisite described below was resolved by PR #215 (commit
> `9ceeedd`). For current state see
> [`docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md`](../../roadmap/roadmap-v2-blocker-first-runtime-ownership.md).

**Verdict:** BLOCKED — `ESCALATED` (clear minimal-invasive PR plan attached, not auto-applied)

**Operator:** Hermes Orchestrator
**Cycle IDs validated:** `20260614T190906Z` (manual), `20260614T181732Z` (cron, last natural)
**HEAD:** `889a747` (origin/main = same)
**Mutations introduced:** 0

---

## TL;DR

PR #214 ist grün: scheduler `64866012641a` (schedule `17 */6 * * *`) liefert
`rainbow_status=SUCCESS, rainbow_source=fixture` — Plumbing steht.

**Aber:** Eine Aktivierung auf `mode=read_only` ist mit den heutigen Hard
Constraints **nicht möglich** und sollte **nicht** in Runtime erzwungen
werden. Zwei harte Blocker:

1. **Code-Lücke** — `active_cycle_runner.py` unterstützt nur
   `SI_V2_RAINBOW_ENABLED` + `SI_V2_RAINBOW_MODE` als Env-Override. Es gibt
   **keine** Brücke für `SI_V2_RAINBOW_BASE_URL` / `…_ENDPOINT_PATH`. Mit
   `MODE=read_only` ohne diese Brücke ruft der Client
   `_get_latest_read_only_signals()` mit `base_url=None` auf und liefert
   `errors=["read_only mode requires base_url"]`.
2. **Keine dauerhafte Quelle** — der ai4trade-Bot ist nicht deployiert
   (kein Container, kein Listener auf 8000/8080). Es existieren 3 BTC/ETH/
   SOL-Signale in `/opt/data/ai4trade-bot/rainbow/storage/signals.db`
   (vom 2026-06-14T01:04, ta_1h, bullish), aber kein Producer, der sie
   unter `/signals/latest` exposen würde.

Beide Blocker brauchen expliziten Approval — Hard Constraints verbieten
"do not patch it in runtime", "do not start Docker", "do not create
long-running services without explicit approval".

## Phase 1 — Baseline (GREEN)

```text
HEAD: 889a747 | origin/main: 889a747 | branch: main
Cron-Job: 64866012641a "si-v2-active-cycle (6h, log-only)"
  schedule: 17 */6 * * * | last_run: 2026-06-14T18:17:33Z | last_status: ok
  next_run: 2026-06-15T00:17:00Z | deliver: local | enabled: true
Source/test diff vs. HEAD: none
Wrapper: /opt/data/scripts/si-v2-active-cycle-runner.sh
  mtime: 2026-06-14T17:12:26Z (unverändert seit PR #214)
Worktree: 82 modified/untracked paths, all classified
  - M docs/state/canonical-trading-status.md  (ledger-watchdog)
  - M orchestrator/reports/canonical_trading_status_latest.json  (ledger-watchdog)
  - ?? docs/context/* (history only)
  - ?? orchestrator/scripts/* (all marked for deploy but not changed here)
  - ?? HERMES_CHANGELOG.md, HERMES_METRICS.json  (runtime artifacts)
  - ?? self_improvement_v2/reports/phase2/*  (cycle outputs)
  - ?? freqtrade/Dockerfile.hermes1337, freqtrade/Dockerfile.hermes1337-freqai-rebel,
      freqtrade/patches/, freqtrade/bots/freqai-rebel/user_data/strategies/RebelLiquidationV2.py
      (untracked source, pre-existing)
```

## Phase 2 — Rainbow runtime config (CODE LIMIT)

```text
Config-Klasse: RainbowClientConfig (src/si_v2/rainbow/client.py)
  enabled: bool = False  (default fail-closed)
  mode: str = "fixture"  (supports "fixture" | "read_only")
  base_url: str | None = None
  endpoint_path: str = "/signals/latest"
  timeout_seconds: int = 30
  source_type: str = "http"

Client-Modi (read_only-Pfad): _get_latest_read_only_signals()
  - liest base_url, _fetch_read_only_payloads() macht urllib.request.urlopen
  - URL = base_url.rstrip("/") + "/" + endpoint_path.lstrip("/")
  - KEIN Auth-Header, KEINE Credentials, KEINE secrets
  - Erwartet JSON-Liste ODER Dict mit "signals"-Liste

active_cycle_runner.py: _load_rainbow_signals() (lines 404-444)
  Unterstütze Env-Overrides:
    SI_V2_RAINBOW_ENABLED  → aktiviert Master-Switch
    SI_V2_RAINBOW_MODE     → "fixture" | "read_only"
  FEHLENDE Env-Overrides:
    SI_V2_RAINBOW_BASE_URL       (notwendig für read_only)
    SI_V2_RAINBOW_ENDPOINT_PATH  (optional, default /signals/latest)
    SI_V2_RAINBOW_TIMEOUT_SECONDS (optional, default 30)

Konstruktion des RainbowClientConfig in active_cycle_runner.py
  (lines 455-460) übergibt nur:
    enabled, mode, fixture_path, max_records
  → KEIN base_url, KEIN endpoint_path
  → read_only-Mode kann technisch nicht funktionieren ohne Patch
```

## Phase 3 — Durable read_only-Quelle (NICHT VERFÜGBAR)

```text
ai4trade-bot-Baum: /opt/data/ai4trade-bot/ (master, kein Deployment)
  rainbow/distribution/api.py existiert (FastAPI, GET /signals/latest)
  rainbow/storage/signals.db  →  3 Zeilen in Tabelle "signals"
    - 3b710387…  BTC/USDT  ta_1h  bullish  conf 0.80  value 64501.03
    - 0be10389…  ETH/USDT  ta_1h  bullish  conf 0.95  value 1680.40
    - 51b6fe91…  SOL/USDT  ta_1h  bullish  conf 0.80  value  68.65
    timestamp aller Zeilen: 2026-06-14T01:04:16Z (≈18h alt, kein Producer aktiv)

Container-Landschaft: kein rainbow/ai4trade-Container läuft
  ss -ltnp  →  keine Listener auf 8000/8080/8081/8001/9090/5000/8888
  ps aux    →  kein uvicorn/gunicorn/fastapi/http.server
  curl-Tests 127.0.0.1:8000-8888 → alle 000/fail

Status Rainbow-Producer: NICHT LÄUFT
Status Rainbow-Quelle: vorhanden, aber ohne aktiven HTTP-Server
```

## Phase 4 — Decision

Aktivierungs-Pfad blockiert. Nächste Aktion NICHT in Runtime, sondern
ein **minimaler Follow-up-PR**, der die Env-Var-Brücke schließt UND eine
lokale, credential-freie, dauerhafte Quelle schafft.

**Vorgeschlagener PR-Titel:** `SI v2: add Rainbow read_only runtime endpoint env override + local DB-backed stub`

**Umfang (geschätzt ~5–8 Commits, alle klein, alle testbar):**

1. `src/si_v2/loop/active_cycle_runner.py`:
   - Ergänze Env-Override für `SI_V2_RAINBOW_BASE_URL`,
     `SI_V2_RAINBOW_ENDPOINT_PATH` (default `/signals/latest`),
     `SI_V2_RAINBOW_TIMEOUT_SECONDS` (default `30`).
   - Konstruiere `RainbowClientConfig` mit allen Feldern aus cfg, nicht
     nur `enabled/mode/fixture_path/max_records`.
   - Validierung: nicht-leere base_url bei `mode=read_only` →
     sonst fail-closed mit klarem Fehler im Status-Report.
   - Test: `tests/test_active_cycle_runner.py` um read_only-Cases
     erweitern (missing base_url, valid base_url mit Stub, timeout).
2. `orchestrator/scripts/rainbow_db_stub_server.py` (NEU, read-only):
   - HTTP-Server, der `/signals/latest` aus
     `/opt/data/ai4trade-bot/rainbow/storage/signals.db` liest und
     mapped (DB-Schema 1:1 in das vom Client-Mapper
     `_map_crypto_signal_to_envelope` erwartete Format).
   - KEINE Auth, KEINE Credentials, KEINE Mutation, KEIN Schreiben in
     die DB, KEIN eigener Producer.
   - Lädt nicht in den Trading-Fleet, sondern wird nur vom
     SI-v2-Wrapper auf 127.0.0.1 konsumiert.
3. `orchestrator/scripts/si-v2-rainbow-db-stub.service` (NEU) oder
   ein Wrapper-Block, der den Stub-Server pro Cycle startet/stoppt
   (kein dauerhafter Daemon, sondern `start; curl; stop` oder
   `python -m http`-Inline-Lifecycle).
4. `/opt/data/scripts/si-v2-active-cycle-runner.sh` Update:
   - `SI_V2_RAINBOW_MODE=read_only`
   - `SI_V2_RAINBOW_BASE_URL=http://127.0.0.1:<port>`
   - `SI_V2_RAINBOW_ENDPOINT_PATH=/signals/latest`
   - Stub-Server-Lifecycle: start vor cycle, stop nach cycle.
5. `tests/test_rainbow_read_only_client.py` & End-to-End-Test:
   - Stub-Server mit 3 Zeilen → `count=3, source=read_only,
     status=SUCCESS, directions=[bullish, …]`.
   - Empty DB → `status=SUCCESS, count=0, source=empty`.
   - 404/timeout/network-error → `status=UNAVAILABLE` mit klarer
     `errors`-Liste.
6. `docs/context/2026-06-XX-si-v2-rainbow-read-only-pr-merged.md` mit
   Akzeptanz-Beweisen (manual + cron one-shot proof + history-gate
   0/10 → 1/10 nach 1. Cycle, weiter auf 10/10 nach 10 Cron-Ticks).

**Out of scope (per Hard Constraints):**
- ai4trade-Bot deployen (würde Docker-Start + Producer-Aktivierung
  erfordern — explizit verboten)
- ai4trade-Bot mit LLM-Evaluationen, Webhooks, etc. verbinden
- Scoring-Logik in ShadowProposal (separater Diskussionspunkt, nicht
  Teil dieses PRs)
- docker-compose / systemd / supervisor-Setup
- Persistenter Stub-Server als Daemon

**Risiko:**
- Stub-Server liest live DB → Falls die DB von einem anderen Prozess
  gelockt ist, muss `mode=ro` (SQLite URI) benutzt werden. Bewährt,
  siehe PR #210/211.
- Stub-Server muss unter 127.0.0.1 bleiben, niemals 0.0.0.0.

## Phase 5 — Enable read_only observation

**SKIPPED.** Wrapper bleibt unverändert. `SI_V2_RAINBOW_MODE=fixture`.
Backup-Datei wird **nicht** erzeugt, weil keine Mutation stattfindet.
Hard Constraint: "If current code lacks env support for read_only base
URL: stop and propose a minimal follow-up PR: do not patch it in
runtime."

## Phase 6 — Manual proof (in current fixture state)

**Zweck:** Bestätigen, dass die Plumbing-Schicht im aktuellen Zustand
stabil ist. NICHT als Beweis für `read_only` (das war nie das Ziel
dieses Runs).

```text
command: PYTHONPATH=src python3 src/si_v2/loop/active_cycle_runner.py
exit: 0
cycle_id: 20260614T190906Z
fleet_verdict: GREEN
ledger_status: SUCCESS  (cycles scanned: 23, mutations_all_zero: True)
controller_state: PAUSED / L3_REPOSITORY_ONLY
mutation_counters:  runtime=0, config=0, live_trading=0,
                    docker=0, strategy=0
secrets_found:  False

Per-Bot:
  - freqtrade-freqforge:        NO_PROPOSAL  sha=106092f3
  - freqtrade-regime-hybrid:    NO_PROPOSAL  sha=c369c70b
  - freqtrade-freqforge-canary: NO_PROPOSAL  sha=9ef4814e
  - freqai-rebel:               NO_PROPOSAL  sha=1b8aaabe

Rainbow (manueller Run, env ohne SI_V2_RAINBOW_ENABLED):
  status:  DISABLED        (erwartet, da secrets-env-file keine
                            SI_V2_RAINBOW_* Vars enthält und der
                            manuelle Aufruf diese nicht setzt)
  count:   0
  source:  ""
  errors:  []

Rainbow (cron-driven, env aus Wrapper, letzter Run um 18:17):
  cycle:   20260614T181732Z
  status:  SUCCESS         (Plumbing GRÜN)
  source:  fixture         (nicht scoringfähig per Design)
  count:   6
  directions: ['long', 'short', 'no_signal']
  errors:  []
```

**Bewertung:** Plumbing steht, Mutations 0, Secret-Scan clean, alle 4
Bots authentifiziert. Bestätigt PR #214 ist operativ. Aber: Rainbow-
History akkumuliert weiterhin **nur fixture-Signale**, also nicht
scoringfähig.

## Phase 7 — Scheduler one-shot proof

**SKIPPED.** One-Shot würde dieselbe Code-Pfad-Lücke treffen. Ohne
`SI_V2_RAINBOW_BASE_URL` Brücke würde der Cycle entweder bei
`fixture` bleiben (kein neuer Beweis) oder bei `read_only` mit
`base_url=None` einen leeren Status liefern (`errors=["read_only mode
requires base_url"]`). Kein Mehrwert gegenüber Phase 6.

## Phase 8 — Final report

### Status

```text
Status:             BLOCKED (ESCALATED)
Operation Level:    L0 (read-only inspection) — keine Mutationen
Reason:             Code-Default bleibt disabled, Wrapper bleibt auf
                    fixture. Aktivierung erfordert explizite Freigabe
                    und einen minimalen Folge-PR.
```

### Rainbow observation state

```text
Mode (runtime):         fixture
Source (last cron):     fixture
Source (last manual):   n/a (DISABLED, env nicht gesetzt)
Code default:           disabled / fail-closed
Score-eligible cycles:  0 / 10
Fixture SUCCESS:        3 (Cron-Cycles)
DISABLED cycles:        2 (manuell + älter)
Pre-PR-214 history:     18 (status=None, nicht zählbar)
```

### Cycle IDs

```text
Last cron:    20260614T181732Z (18:17:33Z, 6h cadence, ok)
Last manual:  20260614T190906Z (19:09:06Z, ok, GREEN)
```

### Mutation counters (Phase 6 manual cycle)

```text
runtime:        0
config:         0
live_trading:   0
docker:         0
strategy:       0
secrets_found:  False
```

### Controller

```text
state:  PAUSED / L3_REPOSITORY_ONLY  (unverändert)
```

### Source/test dirty files

```text
kein diff in self_improvement_v2/src/** oder /**/tests/**
kein diff in freqtrade/** oder orchestrator/scripts/**
kein diff im Wrapper
Worktree ist untracked/modified, aber alle Pfade klassifiziert
```

### Remaining blockers

1. **Code-Patch** für Env-Override `SI_V2_RAINBOW_BASE_URL` +
   `SI_V2_RAINBOW_ENDPOINT_PATH` in
   `src/si_v2/loop/active_cycle_runner.py`.
2. **Dauerhafte, credential-freie, lokal laufende HTTP-Quelle**, die
   `signals.db` (oder einen vergleichbaren realen Rainbow-Output)
   credential-frei unter `/signals/latest` exposen kann, ohne dass
   der ai4trade-Bot deployt werden muss.

### Recommended next task (not auto-executed)

**PR:** `SI v2: add Rainbow read_only runtime endpoint env override
+ local DB-backed stub`

**Schritte (nach Approval):**

1. Issue-Ticket mit exakt diesem Inhalt anlegen
   (Issue-#-Mapping: noch zu vergeben, vermutlich nächste freie
   Nummer im self-improvement-v2-Bereich).
2. Branch `feat/si-v2-rainbow-read-only-runtime` auf `main` basiert.
3. Patch `active_cycle_runner.py` (≤30 Zeilen, inkl. Validierung).
4. Stub-Server `orchestrator/scripts/rainbow_db_stub_server.py`
   schreiben, der `signals.db` über `mode=ro`-SQLite öffnet und
   `/signals/latest` mapped.
5. Wrapper-Update mit Stub-Server-Lifecycle (start vor cycle, stop
   nach cycle, max 60s timeout).
6. Tests:
   - `tests/test_active_cycle_runner.py`: read_only-Mode mit
     Stub-Server, missing base_url, timeout.
   - `tests/test_rainbow_read_only_client.py`: end-to-end gegen
     Stub-Server.
7. Manual proof + 6h-Scheduler-One-Shot proof:
   - `rainbow_status=SUCCESS, source=read_only, count≥1`.
   - `mutations=0, secrets=False`.
8. `docs/context/2026-06-XX-pr-NNN-rainbow-read-only-runtime-merged.md`
   mit Akzeptanzbeweisen und updated `canonical-trading-status.md`.
9. Erste 10 Cron-Cycles (≈60h) sammeln scoring-eligible history →
   `rainbow_read_only_success_cycles` steigt von 0 auf 10 →
   `history_gate_met=True`.
10. Erst danach: separater Diskussionspunkt für
    ShadowProposal-Confidence-Weighting.

### Was ist explizit nicht im Scope

- Scoring-Implementierung
- Proposal-Confidence-Anpassung
- Apply-Phase / Controller-Aktivierung
- Live-Trading / `dry_run=false`
- Freqtrade-Strategien / -Configs / Docker
- Cron-Cadence / Telegram / Scoring / Mutations

---

**Auto-generated 2026-06-14 by Hermes Orchestrator (L0, no mutations).**
