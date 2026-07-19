# Trading Hub — Current Operational State

> **Canonical current-state snapshot.** Reconciled on 2026-07-19 after Phase A
> (state and tracker reconciliation). G0 (Canonical Program Governance) is
> **complete**: G0.1 (PR #640 + #642) and G0.2 (PR #645, merge
> `8c590bf`) are merged, the bootstrap ADR is `Accepted`, and
> `governance-consistency` is a required branch-protection check on `main`.
> The roadmap revision is bumped to 2 (G0 complete, Phase A in_progress).
> Phase B (#636, SEC-1/SEC-3 runtime deployment) remains blocked (A2).
> Phase C (#604, Gate-0 strategy evidence) remains blocked (A1, depends on
> Phase A). No runtime mutation performed by this reconciliation.
>
> **Previous:** SEC-1 PR #632 merged at
> `450c58d15d2af89f8731cc8219c19da3dedae1b8` and SEC-3 PR #635 at
> `a815fce782c039cbfc4f2935d5bc5f1e24f8c878`. SEC-1 containment and SEC-3
> durable intent auditing are present in repository code on `main`, but
> neither has been deployed or runtime-proven. Detailed evidence and
> limitations are recorded in
> [`p0-runtime-state-reconciliation-2026-07-18.md`](../reports/p0-runtime-state-reconciliation-2026-07-18.md),
> [`sec1-legacy-readonly-firewall-2026-07-18.md`](../reports/sec1-legacy-readonly-firewall-2026-07-18.md),
> [`sec1-post-merge-reconciliation-2026-07-19.md`](../reports/sec1-post-merge-reconciliation-2026-07-19.md),
> [`sec3-durable-intent-audit-2026-07-19.md`](../reports/sec3-durable-intent-audit-2026-07-19.md),
> and
> [`sec3-post-merge-reconciliation-2026-07-19.md`](../reports/sec3-post-merge-reconciliation-2026-07-19.md).

## Governance revision pointers

```
governance_contract_revision: 1
roadmap_revision_observed: 4
roadmap_observed_at_utc: 2026-07-19T20:45:00Z
```

`governance_contract_revision` is strictly checked against
`config/governance/program-contract.yaml`; `roadmap_revision_observed` is
informational only and does not force a state-file touch on ordinary roadmap
status changes.

## Phase A — State and Tracker Reconciliation (2026-07-19)

Phase A is the first operational task executed under canonical program
governance. It records G0 completion and advances the roadmap.

- **G0 complete:** exit gate `governance_consistency_green` passed. The
  governance layer (contract, roadmap, schemas, renderer, offline validator,
  CI job, merge-guard extension, broker governance hook) is fully present on
  `main` and enforced via branch protection.
- **Branch protection:** `main` requires `main-gate`, `offline-smoke`, and
  `governance-consistency` status checks (strict, up-to-date); linear history
  enforced; force-push and deletion blocked.
- **Roadmap revision 2:** G0 `complete`, Phase A `in_progress` (issue #647).
  Derived View regenerated.
- **Tracker #605:** repointed to Phase A (issue #647).
- **No runtime mutation:** A1 documentation/roadmap/state only. No Docker,
  Cron, trading, kill-switch, credential, `.env`, service, socket, broker, or
  controller mutation.

### Post-G0 operational state (unchanged by Phase A)

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
