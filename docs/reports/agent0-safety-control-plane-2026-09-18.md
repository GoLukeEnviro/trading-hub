# Agent0 — Safety-Control-Plane: Kill-Switch-Reconciliation & RiskGuard-Blocker

**Datum:** 2026-09-18 · **Host:** Agent0 (`agent0-1`, tailnet `100.103.203.107`)
**Issue:** #730 (Safety-Control-Plane-Schritt) · **Klasse:** A2-Host-Mutation (Kill-Switch) + A1 (Repo)
**Deployter Commit:** `d9d7e1a` (`origin/main`)

> Dieser Report belegt die Herstellung eines kanonischen Safety-Zustands auf Agent0.
> Ergebnis: `PARTIAL` — Kill-Switch-Reconciliation **GREEN**; RiskGuard-Baseline
> **`BLOCKED_BY_MISSING_RISKGUARD_BASELINE_CONTRACT`** (kein versionierter Contract im
> Repository vorhanden; es wurde kein State erfunden).

---

## 1. Kanonischer Kill-Switch: Pfad und Zustand

Genau **eine** kanonische Host-Datei:

| Feld | Wert |
|---|---|
| Kanonischer Pfad | `/home/hermes/trading-hub/var/kill_switch.json` (aufgelöst; kein Symlink) |
| Projektion (ro-Mount in alle Container) | `freqtrade/shared/kill_switch.json` → `/freqtrade/shared/kill_switch.json` |
| Host-Zustand **nachher** | **`NORMAL`** (`operator-reconciliation`, 2026-09-18T14:28:54Z) |
| Projektions-Zustand | `NORMAL` (unverändert) |
| `kill_switch_proof.py` | **GREEN** (host/container consistent, nicht stale) |

Weitere Kill-Switch-Dateien existieren im System **nicht** (nur das Staging-Paket
`/srv/tradinghub-staging-20260917/repo/shared/kill_switch.json` — Transferartefakt,
keine Laufzeitdatei). Keine parallelen autoritativen Dateien.

## 2. Vorher-Artefakt, Provenienz-Beweis, Rollback

**Vorher-Zustand (gesichert):** `HALT_NEW`, sha256
`c2568b197dabe41d35aa7a7a814c96bf34a1143547a044a716d0fe0e922128c3`,
mtime `2026-09-17 00:05:27 +0200`, `triggered_by=drawdown_guard`.

**Provenienz-Evidenz (Testartefakt, kein aktiver Sicherheitsentscheid):**

1. Der Reason-String ist **byte-identisch** mit dem Testfall
   `test_fleet_drawdown_guard.py::TestDrawdownGuard::test_daily_loss_triggers_at_threshold`
   (`Daily drawdown 5.00% >= 5.0% (day_start=100000, equity=94999)`).
2. **Reproduktion 2026-09-18:** Mit umgeleitetem `KILL_SWITCH_FILE` erzeugte
   `FleetDrawdownGuard` das identische Payload (gleicher Reason, `triggered_by=drawdown_guard`);
   die echte Datei blieb dabei unangetastet.
3. **Zeitfenster:** mtime liegt im pytest-Lauf-Fenster der Staging-Verifikations-Session
   (pytest-Cache 00:01:40, Ceremony-Artefakte 00:08).
4. **Kein Operator/Incident-Trigger:** kein Cron-Job, kein systemd-Timer, kein
   deployter `drawdown_guard` (`fleet_risk_state.json` fehlt, `/home/hermes/projects/trading`
   existiert nicht); Registry/Incidents referenzieren den Eintrag nicht.
5. **Ursache behoben:** PR #743 (`a02d91e`) pinnt die Testpfade; die Suite berührt die
   Datei nicht mehr (Red-Proof im PR).

**Immutable Backups (nie überschreiben, nie löschen):**

| Artefakt | Pfad | Schutz |
|---|---|---|
| HALT_NEW-Artefakt | `/opt/data/backups/kill-switch-reconciliation/kill_switch.HALT_NEW.artifact.20260918T142854Z.json` | `chattr +i`, mode 444, root |
| Reconciliation-Record | `…/reconciliation-record.20260918T142854Z.json` | `chattr +i`, mode 444, root |

**Rollback:**
`sudo chattr -i <backup> && sudo cp -p <backup> var/kill_switch.json && sudo chattr +i <backup>`
(Rollback ist selbst immutable-geschützt; Alternativbefehl via `set_kill_mode('HALT_NEW')`
steht im Record.)

**Reconciliation- Funktion:** ausschließlich `freqtrade.shared.kill_switch.set_kill_mode`
(kein `echo NORMAL`). Autorisierung: Operator-GOAL 2026-09-18.

## 3. RiskGuard: `BLOCKED_BY_MISSING_RISKGUARD_BASELINE_CONTRACT`

**Konsumentenvertrag (bestehend, unverändert):**
`RISKGUARD_STATE_PATH = /home/hermes/projects/trading/orchestrator/state/riskguard/riskguard_state.json`;
PASS-Bedingungen (Adapter `derive_riskguard_status`): `summary.status=="ACTIVE"`,
≥1 Pair `ACCEPTED`, kein Pair `BLOCK_ENTRY`; alles andere inkl. fehlender/korrupter
Datei → **fail-closed BLOCKED**.

**Befund:** Es existiert **kein versionierter RiskGuard-Baseline-Contract** im Repository:

- kein Schema/Contract für den State (nur der Producer `orchestrator/scripts/riskguard_service.py`,
  der aus Live-Signalen schreibt — Signalquelle auf Agent0 nicht vorhanden),
- keine Init-/Baseline-Prozedur, kein Beispiel-State, keine Schema-Tests,
  keine Bot-Scoping-Semantik (`freqai-rebel`-Ausschluss), keine Owner/Mode-Vorgabe,
- der Pfad zeigt zudem auf den historischen HermesTrader-Baum (`/home/hermes/projects/trading`),
  der auf Agent0 nicht existiert.

Per GOAL wurde **kein eigener State erfunden**. Der Runtime-Zustand bleibt korrekt
fail-closed: `riskguard`-Provenienz im Bundle = `status="FAIL"`, `present=false`,
`fail_closed=true`.

**Exakt der fehlende Contract (zu liefern in einem separaten A1-Task):**

1. **Schema** (`riskguard_state` v1) mit Feldern: `schema_version`, `timestamp`,
   `summary.status ∈ {ACTIVE, DEGRADED}`, `summary.total_pairs/accepted/watch_only/block_entry`,
   `pairs{<PAIR>:{verdict ∈ {ACCEPTED, WATCH_ONLY, BLOCK_ENTRY}, confidence, action,
   allow_long_bias, allow_short_bias, riskguard_reason}}` — plus JSON-Schema-Datei.
2. **Kanonischer Pfad** für Agent0 (Host-nativ, z. B. unterhalb des Agent0-Checkouts)
   mit Owner/Mode-Vorgabe und atomarem Schreibverfahren.
3. **Bot-Scoping:** genau die drei aktiven Bots; `freqai-rebel` explizit ausgeschlossen
   (disabled), unbekannte Bots/Paare/Aktionen → fail-closed.
4. **Dry-Run-Baseline-Semantik:** keine Live-Autorität, keine automatische Schwellenlockerung,
   konservative Defaults aus `docs/specs/production-risk-limits-spec.md` und
   `orchestrator/config/riskguard-pair-universe.json`.
5. **Init-Prozedur** (vorgesehene Funktion, kein Freitext-Write), Validierungs- und
   Regressionstests (inkl. fail-closed: fehlend/korrupt/falsches Scoping).

## 4. Verbraucherkonsistenz-Matrix (18 Checks)

| # | Konsument | Ergebnis |
|---|---|---|
| 1–2 | Host (`kill_switch.py` Default) | **NORMAL**, `is_kill_active=False` |
| 3 | Projektion (ro-Mount) | **NORMAL** |
| 4–6 | `freqtrade-freqforge` / `-canary` / `-regime-hybrid` (Container) | **NORMAL**, `active=False` (je im Container gemessen) |
| 7–10 | SI-v2-Runner-Provenienz | host `NORMAL` (sha `47c7d924…`), Projektion `NORMAL` (sha `0b068f05…`), `consistent=true`, RiskGuard-Provenienz aufgezeichnet (fail-closed FAIL) |
| 11–12 | Scheduler-Wrapper | installiert (`0700`), Runtime-Env vorhanden |
| 13 | Apply-Gate (expliziter kanonischer Pfad) | **PASS** — "Kill-switch mode is NORMAL" |
| 14 | Apply-Gate (Default-Resolution im Checkout) | fail-closed ohne expliziten Pfad — **by design** (Apply-Pfade übergeben explizit; bestätigt) |
| 15 | RiskGuard-Gate (kanonischer State) | fail-closed BLOCKED (State fehlt — §3) |

**Effektiv: überall `NORMAL` mit derselben kanonischen Provenienz (host == Projektion,
sha-verifiziert, `consistent=true`).**

## 5. Negative Fail-closed-Tests (isoliert, temporäre Pfade)

| # | Probe | Erwartung | Ergebnis |
|---|---|---|---|
| 1 | Temp `HALT_NEW` | blockt | ✅ Apply-Gate blockt, Ceremony-Gate blockt |
| 2 | RiskGuard-State fehlt | blockt | ✅ fail-closed BLOCKED (Adapter + Ceremony) |
| 3 | Ungültiges Schema (`pairs` kein Objekt) | blockt | ✅ FAIL → BLOCKED |
| 4 | Korrupte JSON | blockt | ✅ fail-closed BLOCKED |
| 5 | Unbekannter Kill-Switch-Mode (`YOLO`) | blockt | ✅ "unrecognised - fail-closed BLOCKED" |
| 6 | Positivkontrolle `NORMAL` | passiert | ✅ PASS |
| 7 | Positivkontrolle RiskGuard ACCEPTED | passiert | ✅ PASS |

**9/9 Proben bestanden.** Danach: Produktionszustand unverändert
(Host `NORMAL`, Projektion `NORMAL`, RiskGuard weiter absent/fail-closed); keine
Bot-Config/Strategie angefasst, keine echten Trades beeinflusst.

## 6. SI-v2-Read-only-Revalidierung

```text
cycle_id=20260918T143928Z
fleet_verdict=GREEN        ping_ok=3/3        rainbow=SUCCESS (read_only, fresh)
mutation_runtime=0  mutation_config=0  mutation_live_trading=0
mutation_docker=0   mutation_strategy=0
control_plane.kill_switch: host NORMAL, projection NORMAL, consistent=true
control_plane.riskguard:   FAIL, present=false, fail_closed=true (BLOCKER §3)
```

Die neue `control_plane`-Sektion ist ab jetzt **Bestandteil jedes Evidence-Bundles**
(PR #746). Kein Apply, keine Config-/Strategie-Änderung, keine Secret-Ausgabe.

## 7. Änderungen, PRs, Merge-Commits

| PR | Merge-Commit | Inhalt |
|---|---|---|
| #746 | `d9d7e1a` | `control_plane`-Provenienz im Evidence-Bundle (read-only, fail-closed) + 9 Regressionstests — Issue #745 |

Host-Mutationen (außerhalb des Repos): Kill-Switch-Reconciliation (§2), immutable
Backups/Record (§2). Checkout auf `d9d7e1a` per Fast-Forward nachgeführt (sauber,
kein Branch-Wechsel/Commit/Reset).

## 8. Genau ein nächster Schritt

**`BLOCKED_BY_MISSING_RISKGUARD_BASELINE_CONTRACT`:** Ein A1-Task liefert den unter §3
spezifizierten, versionierten RiskGuard-Baseline-Contract (Schema + kanonischer Agent0-Pfad
+ Bot-Scoping + Dry-Run-Baseline + Init-Prozedur + Tests). Erst danach ist der
RiskGuard-Teil der Safety-Control-Plane grün; `AUTONOMOUS_DRY_RUN` bleibt bis dahin
unaktiviert.

---

**Belege:** `/tmp/ag0/consumers_matrix.json`, Reconciliation-Record (immutable, Agent0),
Cycle-Log `cycle-20260918T143928Z.log`. Keine Secrets in diesem Report.
