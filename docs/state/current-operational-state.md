# Trading Hub — Current Operational State

> **Canonical current-state snapshot.** Reconciled on 2026-07-19 after Phase C
> status correction. Phase C exit gate `edge_decision_recorded` is **not yet
> satisfied** — only the strategy selection and manifest freeze are complete;
> snapshot acquisition, holdout inspection, and edge decision are still
> pending. Phase C is back to `in_progress`. Roadmap revision 5. No runtime
> mutation performed by this reconciliation.
>
> **Previous:** Phase A complete (#648, `2b6915d`). G0 complete: G0.1 (PR #640
> + #642) and G0.2 (PR #645, `8c590bf`) merged; bootstrap ADR `Accepted`;
> `governance-consistency` is a required branch-protection check. Phase C
> inventory and manifest proposal merged (#649, `eca7923`); Luke signed
> strategy selection (`FreqForge_Override`) and frozen manifest on #604.

## Governance revision pointers

```
governance_contract_revision: 1
roadmap_revision_observed: 5
roadmap_observed_at_utc: 2026-07-19T22:00:00Z
```

`governance_contract_revision` is strictly checked against
`config/governance/program-contract.yaml`; `roadmap_revision_observed` is
informational only and does not force a state-file touch on ordinary roadmap
status changes.

## Phase C — Gate-0 Strategy Evidence (2026-07-19, in progress)

Phase C exit gate is `edge_decision_recorded`. The exit gate is **not yet
satisfied**. Current sub-status:

| Sub-step | Status | Evidence |
|---|---|---|
| Strategy selected | ✅ PASS | `FreqForge_Override` — Luke signed on #604 |
| Manifest frozen | ✅ PASS | All thresholds approved; `APPROVED_GATE0_STRATEGY_AND_MANIFEST` on #604 |
| Snapshot acquisition | ✅ `EXECUTED` | 156,489 candles fetched (#651, A2 marker `APPROVED_A2_GATE0_SNAPSHOT_FETCH`); C3 complete | with full execution contract before execution |
| Holdout inspected | ❌ NO | Not started; blocked by snapshot |
| Edge decision | ⏳ `PENDING` | Not yet recorded; blocked by holdout |

Phase C remains `in_progress` until the edge decision is recorded. Issue #604
remains open.

### Frozen manifest summary (approved by Luke on #604)

| Field | Value |
|---|---|
| Strategy | `FreqForge_Override` |
| Exchange | Bitget futures (linear) |
| Pairs | BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT |
| Timeframe | 15m |
| Calibration | 2025-01-01 to 2025-06-30 |
| Walk-forward | 2025-07-01 to 2025-09-30, 2025-10-01 to 2025-12-31 |
| Holdout | 2026-01-01 to 2026-06-30 (untouched) |
| OOS max drawdown | < 25% |
| OOS profit factor | > 1.3 |
| Min trades | > 100 |
| Min regimes | ≥ 2 |

Full manifest: [`phase-c-gate0-candidate-inventory-2026-07-19.md`](../reports/phase-c-gate0-candidate-inventory-2026-07-19.md)

### Next step: A2 snapshot-fetch contract

Luke's #604 comment authorizes the snapshot fetch in principle but is not yet
an executable A2 contract. A dedicated A2 issue must specify: exact time
window, target host and path, allowed public Bitget endpoints, exact pairs
and timeframes, rate/size limits, credential prohibition, hash and provenance
format, strategy-execution and holdout prohibition, cleanup scope, and audit
requirements. Luke then issues a time-limited, scope-specific A2 marker.

## Post-G0 operational state (unchanged)

- Live trading: `TARGET_ARCHITECTURE_NOT_ENABLED`
- Execution mode: Dry-run only
- Kill switch: `NORMAL`
- C4 decision: `ROLLBACK_RECOMMENDED` (preserved)
- Fleet: HermesTrader dry-run fleet (5/5 health per R5A); agent0 legacy
  containers remain outside canonical governance
- SEC-1/SEC-3: present in code, not deployed or runtime-proven

## 1. Executive state

| Area | Current result |
|---|---|
| Trading posture | Dry-run only; live-capital authority remains external and absent |
| P0 evidence gate | `EVIDENCE_COMPLETE / RECONCILIATION_REQUIRED` |
| UID-10000 executor v1 path | **PASS** |
| Executor and fleet reachability | **PASS** |
| R5A HermesTrader stack | **PASS — 5/5 healthy** |
| SI-v2 four-bot fleet on HermesTrader | **PARTIAL — 3/4; Rebel absent** |
| Legacy executor protocol | **SEC-1 MERGED / RUNTIME NOT DEPLOYED** |
| Repository audit implementation | **SEC-3 MERGED / VALIDATED / NOT DEPLOYED** |
| Deployed audit completeness and durability | **P0 FAIL remains authoritative; runtime proof pending A2** |
| Deployment provenance | **PARTIAL** |
| Kill switch | **NORMAL persisted and effective after bounded reconciliation** |
| Bot-scoped freeze at strategy entry | **NOT WIRED** |
| Runtime mutation during SEC-1, SEC-3, and post-merge reconciliation | **NONE** |

The R5A deployment and the logical SI-v2 fleet are different sets and must not
be conflated. R5A parity is satisfied by FreqForge, Canary, Regime, Webserver,
and Rainbow. The SI-v2 trading fleet expects FreqForge, Canary, Regime, and
Rebel; only the first three were present on HermesTrader during this audit.
The state of any Agent0 Rebel was not revalidated by this audit.

## 2. Runtime snapshot

The bounded live evidence was collected on 2026-07-18, with the executor audit
tail observed through `2026-07-18T22:42:01Z`.

| Workload | HermesTrader state | Notes |
|---|---|---|
| `freqtrade-freqforge` | Healthy | Dry-run trading bot |
| `freqtrade-freqforge-canary` | Healthy | Dry-run trading bot |
| `freqtrade-regime-hybrid` | Healthy | Dry-run trading bot |
| Webserver | Healthy | `RestartCount=2` |
| Rainbow | Healthy | Canonical R5A Rainbow workload |
| `freqai-rebel` | Absent | SI-v2 fleet is therefore 3/4 on HermesTrader |

Two additional `rainbow-live` containers were also present. They are not part
of the canonical R5A 5/5 count and require later lifecycle reconciliation.

The three observed trading bots and Webserver used the same read-only bind:

```text
/opt/data/projects/trading-hub/freqtrade/shared -> /freqtrade/shared (read-only)
```

This proves a common shared-reader source for the observed HermesTrader
workloads. It does not prove the absent Rebel configuration or Agent0 runtime.

## 3. Root executor, protocol, and audit

- The dedicated executor service was active and the intended UID `10000` v1
  read-only path was usable.
- The audit file was structurally parseable and contained the required v1
  identity/action/decision fields for the sampled requests.
- Since 2026-07-13, the bounded audit inventory contained **172 entries**:
  **87 v1** and **85 legacy**. Legacy use included at least one Docker request
  and six Systemd requests.
- Legacy records do not preserve sufficient structured subcommand intent to
  establish that every historical request was read-only.
- The bounded deployed-runtime audit result is **FAIL**: the inspected running
  implementation had no durable `fsync` boundary and no intent-audit record
  before execution. Repository changes cannot retroactively change that
  observation.

SEC-1 is merged on `main` through PR #632. Repository code now builds approved
legacy command arguments server-side, permits only a bounded read-only
compatibility subset, rejects mutation, injection, traversal, and unknown
requests before subprocess execution, and records fixed non-secret
classifications. Its complete repository test suite passed with **1007 passed,
52 skipped**; both required GitHub checks passed before Luke's merge.

SEC-3 is merged on `main` through PR #635 at
`a815fce782c039cbfc4f2935d5bc5f1e24f8c878`. Repository code now writes a
redacted intent event before approved subprocess execution, establishes file
flush/`fsync` and new-file parent-directory `fsync` boundaries, correlates
terminal events through a stable audit ID, and fails closed on audit durability
failure. Local validation included **1024 passed, 52 skipped**, and both
required GitHub checks succeeded for the exact SEC-3 head
`ed968fb428929343657cf0fca027f06ed681733e`.

These are repository facts only. The executor service was not installed,
restarted, reloaded, replaced, or runtime-revalidated during SEC-1, SEC-3, or
either post-merge reconciliation. The running executor must not be claimed to
have the SEC-1 firewall, pre-execution durable intent events, `fsync`
durability, correlated completion records, or SEC-3 behavior. Until a
separately approved A2 deployment and runtime-proof ceremony succeeds, the
bounded P0 observation remains authoritative for deployed behavior and runtime
audit durability remains unproven.

## 4. Deployment provenance

The running service advertised repository commit
`782d2c04f59ee96151581de436b069095d28b019`, and installed package modules
matched that revision. The installed executable retained a header associated
with `ea26ff7`, while the daemon body was unchanged. This is consistent with a
non-atomic installation path and supports **PARTIAL** provenance, not a total
deployment failure and not a fully reproducible deployment proof.

## 5. Kill-switch state and Issue #580 reconciliation

The P0 audit observed three path-dependent results:

1. the tracked physical file persisted an expired `HALT_NEW` record;
2. the canonical reader resolved its effective mode to `NORMAL` because the
   record had expired; and
3. a reader pointed at an incorrect default path failed closed.

These results prove path-dependent state resolution, not three independent
runtime modes. Under the explicit marker
`APPROVED_A2_KILL_SWITCH_STATE_RECONCILIATION`, valid for 15 minutes on
2026-07-18, only the expired physical record was reconciled to the already
effective `NORMAL` state.

- Before-state snapshot:
  `/opt/data/hermes/runtime-snapshots/issue-580/20260718T231844Z/kill_switch.json.before`
- Snapshot SHA-256:
  `44bc2beda4c96ed8f49833f5c26ecfe851016ad3ec4118efc93174d454cb6b87`
- Rollback: restore that exact snapshot.
- Result: persisted `NORMAL`, effective `NORMAL`, and the shared checkout clean.
- Excluded: container, strategy, deployment, restart, credential, order, and
  live-capital changes.

Bot-scoped `HALT_BOT`/`scoped_freeze` behavior is not yet wired into the
strategy entry path. A separate issue must establish a canonical path,
explicit Host/Container configuration, one `effective_mode` query, expiry and
missing-file tests, and eventual bot-scoped entry integration.

## 6. Go / no-go

**Allowed next repository work:** complete human review of this A1 SEC-3
post-merge reconciliation. After it merges, SEC-1 and SEC-3 are
repository-complete.

A future executor deployment and runtime proof is a separate A2 task. It
requires a dedicated GitHub issue, explicit scope-specific A2 approval, exact
commit/artifact identity, pre-deployment snapshot, command/action allowlist,
time bound, rollback procedure, canary or bounded deployment order, service
health verification, SEC-1 runtime blocking proofs, SEC-3
intent-before-execution proofs, audit correlation and durability evidence, a
secret scan, and confirmation that no trading, configuration, or kill-switch
mutation occurred.

**Not authorized:** executor deployment or restart, runtime proof, R5B
continuation, strategy reload, container mutation, kill-switch clear/bypass,
new root capabilities, live-capital changes, or any A2/A3 action not covered
by a new explicit marker.

The repository writer remains single-writer and PR-only. This work stops at
`READY_FOR_HUMAN_MERGE`; only Luke merges.

## C5.1 Corrective — Strategy identification and manifest v2 (2026-07-19)

C5 (PR #657, `55ca28f`) was merged but runtime-unverified. 15 gaps identified:
strategy mismatch (FreqForge_Override has Shorting/CustomStoploss/1h-informative/
FleetRiskManager/Primo signals vs. simplified description), partition gaps,
incorrect hash bindings, unachievable regime gate, and wrong min_duration_days.
C5.1 corrective (PR pending) addresses all 14 items with strategy provenance,
manifest v2, partition correction, converter, adapter, and 19 tests.
Holdout remains sealed until A0 preflight + A2 selection backtest + C6 marker.
