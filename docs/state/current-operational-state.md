# Trading Hub — Current Operational State

> **Canonical current-state snapshot.** Reconciled on 2026-07-19 after Luke
> squash-merged SEC-1 PR #632 at
> `450c58d15d2af89f8731cc8219c19da3dedae1b8`. The bounded P0 runtime
> evidence remains the runtime baseline. SEC-1 containment is now present on
> `main`, but it has not been deployed. Detailed evidence and limitations are
> recorded in
> [`p0-runtime-state-reconciliation-2026-07-18.md`](../reports/p0-runtime-state-reconciliation-2026-07-18.md),
> [`sec1-legacy-readonly-firewall-2026-07-18.md`](../reports/sec1-legacy-readonly-firewall-2026-07-18.md),
> and
> [`sec1-post-merge-reconciliation-2026-07-19.md`](../reports/sec1-post-merge-reconciliation-2026-07-19.md).

## 1. Executive state

| Area | Current result |
|---|---|
| Trading posture | Dry-run only; live-capital authority remains external and absent |
| P0 evidence gate | `EVIDENCE_COMPLETE / RECONCILIATION_REQUIRED` |
| UID-10000 executor v1 path | **PASS** |
| Executor and fleet reachability | **PASS** |
| R5A HermesTrader stack | **PASS — 5/5 healthy** |
| SI-v2 four-bot fleet on HermesTrader | **PARTIAL — 3/4; Rebel absent** |
| Legacy executor protocol | **SEC-1 CONTAINMENT MERGED / RUNTIME NOT DEPLOYED** |
| Audit schema/structure | **PASS** |
| Audit completeness and durability | **FAIL** |
| Deployment provenance | **PARTIAL** |
| Kill switch | **NORMAL persisted and effective after bounded reconciliation** |
| Bot-scoped freeze at strategy entry | **NOT WIRED** |
| Runtime mutation during SEC-1 and this reconciliation | **NONE** |

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
- Audit durability is **FAIL**, not `UNVERIFIED`: the implementation has no
  durable `fsync` boundary and no intent-audit record before execution.
  Runtime inspection can prove that entries exist, but cannot close this
  structural gap.

SEC-1 is merged on `main` through PR #632. The repository implementation now
builds approved legacy command arguments server-side, permits only a bounded
read-only compatibility subset, rejects mutation, injection, traversal, and
unknown requests before subprocess execution, and records fixed non-secret
classifications. Its complete repository test suite passed with **1007 passed,
52 skipped**; both required GitHub checks passed before Luke's merge.

This is a repository fact, not a runtime deployment claim. The running
executor was not restarted, replaced, or revalidated in SEC-1 or this
post-merge reconciliation. Until a separately approved deployment and runtime
proof occurs, the bounded P0 observation remains authoritative for deployed
legacy behavior. SEC-3 still owns the durable intent-audit design gap.

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

**Allowed next repository work:** complete human review of this A1 post-merge
reconciliation. After it merges, SEC-1 is repository-complete. Any executor
deployment/runtime proof requires a separate, explicitly scoped A2 issue,
approval, snapshot, rollback plan, audit evidence, and bounded verification.
SEC-3 remains separate A1 design/implementation work.

**Not authorized:** R5B continuation, executor deployment, strategy reload,
container mutation, kill-switch clear/bypass, new root capabilities,
live-capital changes, or any A2/A3 action not covered by a new explicit marker.

The repository writer remains single-writer and PR-only. This work stops at
`READY_FOR_HUMAN_MERGE`; only Luke merges.
