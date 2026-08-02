# Trading Hub — Current Operational State

> **Canonical current-state snapshot.** Reconciled on 2026-08-02 after issue backlog reconciliation. Phase C exit gate `edge_decision_recorded` is **not yet satisfied**. A0 preflight GREEN (PR #682, `72421de`). Backtest Contract GREEN (PR #687, `79ad6dd`). Issue backlog reconciled: 27→6 open issues. Phase C remains `in_progress`.
>
> **Previous:** 2026-07-31 after C5.4 and Variante-B completion. C5.3 merged (`da60da3`), C5.4 corrective merged (`8b4dace`), Variante-B complete (PRs #677, #678, #679). Phase C remains `in_progress`.
>
> **Previous:** C5.2 A0-FAIL documented (#664, `01b7fb2`). C5.3 corrective
> fully strips FreqForge_Gate0_Core_v1 of all dependencies, introduces manifest
> v3, entry-time regime classification, and selection-only evaluation with
> holdout isolation. 67 tests pass. C5.4 corrective merged (`8b4dace`):
> SelectionOutcomeV1.PASS_CANDIDATE fix, pair normalization, unified guardrails.
> Variante-B complete (PRs #677, #678, #679). Tracker #423 closed.

## Hermes runtime — native migration (2026-07-25)

> **Status:** `NATIVE_MIGRATION_LOOP_CLOSED` / `LIFECYCLE_CONTRACT_GREEN`
>
> Reconciled on 2026-07-25 after host-native cutover and lifecycle-contract fix.
> Hermes no longer runs as Docker Compose service for production gateway/dashboard.

| Field | Value | Evidence |
|---|---|---|
| Hermes version | **0.19.0** (2026.7.20) | `hermes --version` on host as uid 10000 |
| Install path | `/opt/hermes-native/current` → `releases/0.19.0` | `readlink -f` |
| Runtime | native systemd (`hermes-gateway`, `hermes-dashboard`, `hermes-native.target`) | `systemctl is-active` |
| Profile | `trading-hub-orchestrator` | `active_profile` + gateway list |
| User | `hermes` uid/gid **10000** (+ docker) | `id hermes` / process owner |
| State schema | **22** (migrated from 19) | `state.db` `schema_version` |
| Sessions | **57** preserved | `SELECT COUNT(*) FROM sessions` |
| SQLite integrity | ok | `PRAGMA integrity_check` |
| Telegram | connected | `gateway_state.json` platforms.telegram |
| Dashboard bind | `127.0.0.1:9119` only | `ss -lntp` |
| Port 8642 | no unexpected listener | `ss -lntp` |
| Caddy | reverse_proxy → 127.0.0.1:9119 | HTTPS reachable (auth/app status codes) |
| GitHub CLI | GoLukeEnviro authenticated | `gh auth status` with `GH_CONFIG_DIR` |
| Trading fleet | HermesTrader dry-run **5/5 healthy** | `docker ps` hermestrader-dryrun-* |
| Legacy container | present, **stopped**, `Restart=no` | `docker inspect hermes` |
| Legacy rollback retained | container + volumes + release 0.18.2 + restic + Hetzner snapshot | ops artefacts under `/root` and `/opt/hermes-native/releases/0.18.2` |

### Lifecycle contract

- Permanent `ExecStart` for gateway is:
  `/opt/hermes-native/current/bin/hermes -p trading-hub-orchestrator gateway run`
- **`--replace` is not** in the permanent unit (removed 2026-07-25 after audit).
- Optional CLI flag remains available for one-shot operator use; systemd Restart policy owns restarts.
- Post-fix MainPID ran as uid 10000 without `--replace`; Telegram reconnected without cutover.

### Reports

- Final migration report: `/root/reports/hermestrader-native-migration-final-20260725T003141Z.md` (on HermesTrader host)
- 15-minute observation log: `/root/reports/hermes-0.19.0-observe.log` (15/15 green, 0 restarts)
- Issue tracker: #423

### Not changed by this migration

- No trading-bot configs or bot databases mutated
- Live trading remains disabled / dry-run only
- Kill switch posture unchanged


## Governance revision pointers

```
governance_contract_revision: 1
roadmap_revision_observed: 5
roadmap_observed_at_utc: 2026-07-20T05:00:00Z
```

`governance_contract_revision` is strictly checked against
`config/governance/program-contract.yaml`; `roadmap_revision_observed` is
informational only and does not force a state-file touch on ordinary roadmap
status changes.

## Phase C — Gate-0 Strategy Evidence (2026-08-02, in progress)

Phase C exit gate is `edge_decision_recorded`. The exit gate is **not yet
satisfied**. Current sub-status:

| Sub-step | Status | Evidence |
|---|---|---|
| Strategy selected | ✅ PASS | `FreqForge_Override` — Luke signed on #604 |
| Manifest frozen | ✅ PASS | All thresholds approved; `APPROVED_GATE0_STRATEGY_AND_MANIFEST` on #604 |
| Snapshot acquisition | ✅ `EXECUTED` | 156,489 candles; A2 marker on #651. Data verified present at `/opt/data/hermes/gate0-snapshot/` (native path contract, issue #684) |
| C5.2 Core Strategy v1 | ❌ `A0-FAIL` → ✅ resolved by C5.3 | PR #662 (`2875b67`): preflight found 14 Ruff errors. C5.3 corrective PR #668 (`da60da3`) resolved all 14 items. |
| C5.3 Corrective | ✅ MERGED | PR #668 (`da60da3`): stripped strategy, manifest v3, entry-time regime, selection isolation. 67 tests pass. |
| C5.4 Corrective | ✅ MERGED | PR #675 (`8b4dace`): SelectionOutcomeV1.PASS_CANDIDATE fix, pair normalization, unified guardrails, Ruff clean. 47/47 C5.4 + 25/25 eval_bundle. |
| A0 preflight re-run | ✅ `GREEN` | PR #682 (`72421de`): 146/146 Gate-0 suite passed. Snapshot integrity OK. Ruff clean. |
| Backtest Contract | ✅ `GREEN` | PR #687 (`79ad6dd`): pinned image digest, selection dataset, funding adapter. |
| Issue backlog reconciled | ✅ `RECONCILED` | 27→6 open issues. See `docs/reports/repository-issue-backlog-reconciliation-2026-08-02.md` |
| Holdout inspected | ❌ NO | Not started; blocked by Luke ratification on #604 |
| Edge decision | ⏳ `PENDING` | Not yet recorded; blocked by holdout |

Phase C remains `in_progress` until the edge decision is recorded. Issue #604
remains open.

### Frozen manifest summary (approved by Luke on #604, updated by C5.2)

| Field | Value |
|---|---|
| Strategy | `FreqForge_Gate0_Core_v1` (C5.2 stripped variant) |
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
| max_missing_candles | 5% formula: `floor(total_expected * 0.05)` |
| min_duration_days | 90 (matches WF windows) |
| Regime classification | Entry-time, per-pair, pre-entry data only (no lookahead) |

Full manifest: [`phase-c-gate0-candidate-inventory-2026-07-19.md`](../reports/phase-c-gate0-candidate-inventory-2026-07-19.md)

### Next steps

1. **#683 read-only closure reconciliation** — verify executor, fleet, cron, writer lock
2. **Luke ratifies corrected strategy + manifest v3** — human action on #604
3. **Create A2 Bitget Snapshot v2 issue** — warm-up + funding + selection windows, new path, new A2 marker
4. **Luke issues time-limited A2 marker** — `APPROVED_A2_BITGET_SNAPSHOT_V2`
5. **Fetch/freeze warm-up + selection + sealed holdout + funding**
6. **Create A2 Selection Backtest issue**
7. **Luke issues time-limited selection-backtest marker**
8. **Execute selection-only backtest**
9. **Record PASS_SELECTION / EXTEND / REJECT / INVALID**
10. **C6 holdout ceremony** — only after separate human marker
11. **Record canonical Gate-0 edge decision**
12. **Execute #600 ADR**
13. **Reassess #496**

## Root Runtime Authority — Variante B Complete (2026-07-28)

> **Status:** `ROOT_RUNTIME_AUTHORITY_COMPLETE` / `READY_FOR_RUNTIME_OPERATIONS`
>
> Reconciled on 2026-07-28 after PR #677 (`c4dbeea`) and PR #678 (`b675708`).

| Field | Value | Evidence |
|---|---|---|
| Executor service | **active (running)** | `systemctl is-active hermes-root-executor.service` |
| Executor binary | `/usr/local/sbin/hermes-root-executor` (root:root, 0750) | `ls -la` |
| Socket | `/run/hermes-root-executor/executor.sock` (root:hermes, 0660) | `ls -la` |
| Hermes UID | **10000** (unprivilegiert) | `id hermes` |
| Total actions | **75** (17 readonly, 58 mutating) | `hermes_root/schema.py` |
| D1/D2/D3 | **RETIRED** | All inactive, no systemd units |
| sudo for Hermes | **Nicht vorhanden** | `sudo -l` |
| docker.sock for Hermes | **Nicht vorhanden** | `ls -la /var/run/docker.sock` (root:docker) |
| Audit | **AUDIT_RUNTIME_COMPLETE** | JSONL mit fsync-Durability |
| Kill switch | **Active** | `/etc/hermes-root-executor/DISABLED` |

### Capability coverage

| Domain | Actions | Status |
|--------|---------|--------|
| systemd | status, is-active, is-enabled, start, stop, restart, daemon-reload, enable, disable | ✅ |
| Docker | ps, inspect, logs, images, compose-config, create, start, stop, remove, pull, network, volume, exec | ✅ |
| R5A Compose | build, up, stop, down | ✅ |
| Filesystem | stat, ls, read, checksum, write, copy, move, remove, mkdir, chmod, chown, backup, restore | ✅ |
| Git | status, branch, log, tag-list, clone, fetch, checkout, merge, tag, clean, reset, push | ✅ |
| Caddy | validate, reload, fmt | ✅ |
| UFW | status, allow, deny, enable, disable | ✅ |
| Hostname | get, set | ✅ |
| sysctl | get, set | ✅ |
| Users/Groups | create, modify, delete, group create, group delete | ✅ |

### D1/D2/D3 retirement

- `hermes-runtime-runner` (D2): binary at `/usr/local/sbin/hermes-runtime-runner`, **inactive**, no systemd unit
- `hermes-bridge` (D3): service **inactive**, no systemd unit; client binary at `/opt/data/hermes/bin/hermes-bridge-client`
- Docker socket proxy (D1): **no container running**, no systemd unit
- All three preserved as historical reference only — not removed

### Final report

- `/root/reports/hermes-runtime-authority-final-20260728.md` (on HermesTrader host)
- `docs/reports/hermes-runtime-authority-final-20260728.md` (in repository)

- Live trading: `TARGET_ARCHITECTURE_NOT_ENABLED`
- Execution mode: Dry-run only
- Kill switch: `NORMAL`
- C4 decision: `ROLLBACK_RECOMMENDED` (preserved)
- Fleet: HermesTrader dry-run fleet (5/5 health); Hermes agent runtime is **native systemd 0.19.0** (see section above); agent0 legacy
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

**Allowed next repository work:** #683 read-only closure reconciliation — verify
executor, fleet, cron, writer lock. This is A0/A1 work. No A2 selection backtest
and no holdout inspection until Luke ratifies the corrected strategy + manifest
v3 on #604.

After Luke's ratification, a new A2 Bitget Snapshot v2 issue with a fresh A2
marker authorizes warm-up + funding + selection data fetch. Then a separate A2
selection-backtest issue. After backtest, C6 marker enables holdout inspection
and edge decision.

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
C5.1 corrective addresses all 14 items with strategy provenance,
manifest v2, partition correction, converter, adapter, and 19 tests.
Holdout remains sealed until A0 preflight + A2 selection backtest + C6 marker.

## C5.2 Gate-0 Core Strategy v1 — A0 Preflight Result (2026-07-20)

PR #662 (`2875b67`) merged by Luke, then re-evaluated via A0 preflight.

**Result: `GATE0_C52_PREFLIGHT_FAIL`**

The committed `FreqForge_Gate0_Core_v1` contains:
- 14 Ruff errors (3× F821 undefined names: `normalize_pair`, `long_risk_allowed`, `short_risk_allowed`)
- Residual Primo/FleetRisk/AI/Shadow references
- Uninitialized `risk_manager` and `_fleet_source`
- Regime classification with post-entry lookahead
- Selection runner evaluating holdout state
- Manifest v1/v2 output (no v3)

Full report: [`gate0-c52-preflight-failure-2026-07-20.md`](../reports/gate0-c52-preflight-failure-2026-07-20.md)

**A C5.3 corrective is required.** No A0 re-run, A2 marker, or holdout
inspection is valid until C5.3 is merged and re-validated.
