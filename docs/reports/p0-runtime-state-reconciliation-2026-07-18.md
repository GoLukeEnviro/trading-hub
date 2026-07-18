# P0 Runtime State Reconciliation — 2026-07-18

**Issue:** #580

**Tracker:** #605

**Repository base:** `d4f5c16bcbfcffad493f45e29dcba88abbbabd62`

**Classification:** A0 evidence, one bounded A2 state reconciliation, followed
by A1 documentation only

**Final P0 gate:** `EVIDENCE_COMPLETE / RECONCILIATION_REQUIRED`

## Scope and safety boundary

The audit answered only deployment provenance, protocol use, executor audit,
container health/image/restart metadata, shared mount topology, and
kill-switch state resolution. It used formatted read-only queries and did not
collect raw container environments or secret values.

The A0 audit performed no runtime mutation. A later, separately authorized A2
action changed only the expired physical kill-switch record to match its
already effective `NORMAL` result. No container, strategy, deployment,
credential, order, or live-capital state was changed.

## Evidence matrix

| Question | Evidence | Result |
|---|---|---|
| Does the executor run and accept the intended peer? | Service active; UID `10000` completed genuine v1 read-only actions | **PASS** |
| Is R5A healthy? | FreqForge, Canary, Regime, Webserver, Rainbow all healthy | **PASS — 5/5** |
| Is the SI-v2 four-bot fleet complete on HermesTrader? | FreqForge, Canary, Regime present; Rebel absent | **PARTIAL — 3/4** |
| Are other workloads present? | Two additional `rainbow-live` containers observed | **RECONCILE** |
| Any restart signal? | Webserver `RestartCount=2`; other canonical health evidence remained green | **OBSERVED** |
| Do observed workloads share the reader? | Three trading bots and Webserver bind the same host shared directory read-only | **PASS for observed workloads** |
| Is legacy protocol unused? | 85 of 172 records since 2026-07-13 are legacy | **FAIL** |
| Is audit structured? | JSONL parses; sampled v1 records expose action, decision, identity, and audit ID | **PASS** |
| Is audit complete and durable? | No pre-execution intent record and no `fsync` durability boundary | **FAIL** |
| Is deployed provenance exact and atomic? | Modules align with `782d2c`; executable header reflects `ea26ff7`; installation was non-atomic | **PARTIAL** |
| Is kill-switch meaning coherent? | Expired persisted `HALT_NEW`; canonical effective `NORMAL`; wrong-path fallback fail-closed | **PARTIAL before reconciliation** |
| Is bot-scoped freeze effective at entry? | `HALT_BOT`/`scoped_freeze` not wired into strategy entry | **NO** |

## Runtime inventory

### R5A versus SI-v2

R5A and SI-v2 are different views of the runtime:

- **R5A 5/5 healthy:** FreqForge, Canary, Regime, Webserver, Rainbow.
- **SI-v2 3/4 on HermesTrader:** FreqForge, Canary, Regime present; Rebel
  absent.

The audit did not revalidate whether an Agent0 Rebel remained active. No claim
about current Agent0 Rebel state should be inferred from the HermesTrader
absence.

Two additional `rainbow-live` containers were visible outside the canonical
R5A count. Their presence is documented but was not altered.

### Shared-reader topology

The observed three trading bots and Webserver used:

```text
host:      /opt/data/projects/trading-hub/freqtrade/shared
container: /freqtrade/shared
mode:      read-only
```

This supports a single shared source for those observed workloads. Rebel was
not running on HermesTrader, so its live mount could not be proven there.

## Executor and audit findings

The intended UID-separated path is operational: Hermes UID `10000` can use the
real v1 read-only executor actions. The executor is therefore reachable
without treating broad Operator breakglass as the normal runtime interface.

The bounded audit inventory from 2026-07-13 through the observed tail at
`2026-07-18T22:42:01Z` contained:

| Protocol/class | Count |
|---|---:|
| v1 | 87 |
| legacy | 85 |
| total | 172 |

Known legacy categories included Docker (1) and Systemd (6). Legacy records do
not retain enough structured argv/subcommand detail to retroactively prove
that every invocation was read-only. Audit IDs and correlation fields were
present for sampled v1 records; raw identifiers and unredacted payloads are
intentionally not copied into Git because the aggregate and structural result
is sufficient for this decision record.

### Why durability is FAIL

The daemon appends audit entries, but the inspected implementation lacks both:

- an intent record durably written before command execution; and
- an explicit `flush` + `fsync` durability boundary.

Consequently, an executor action may occur without a durable corresponding
record after a crash or power loss. More runtime tail inspection cannot turn
this into PASS. SEC-3 must change the structure and test crash boundaries.

## Deployment provenance

The service environment named repository commit
`782d2c04f59ee96151581de436b069095d28b019`. Installed Python modules matched
that revision. The executable wrapper/header still carried `ea26ff7`, while
the daemon body was unchanged. This establishes the deployed code lineage well
enough for **PARTIAL** provenance, but the installation is not atomically tied
to one immutable artifact. Future deployment proof should bind executable,
modules, unit environment, and artifact digest in one transaction.

## Kill-switch semantics and bounded reconciliation

### Before

- Physical tracked state: expired `HALT_NEW`.
- Canonical effective state: `NORMAL` by expiry semantics.
- Incorrect-default-path read: fail-closed fallback.

This is a path-resolution inconsistency, not evidence of three concurrently
effective fleet modes.

### Authorized action

Luke supplied:

```text
APPROVED_A2_KILL_SWITCH_STATE_RECONCILIATION — Issue #580,
gültig für 15 Minuten ab jetzt.
```

Before the write, the exact source file was copied to:

```text
/opt/data/hermes/runtime-snapshots/issue-580/20260718T231844Z/kill_switch.json.before
```

SHA-256:

```text
44bc2beda4c96ed8f49833f5c26ecfe851016ad3ec4118efc93174d454cb6b87
```

The snapshot directory is owned by UID/GID `10000:10000`, directory mode
`0700`; snapshot files are mode `0600` and were flushed durably. The only
state change reconciled the expired physical record to `NORMAL`. The final
file matches the tracked canonical `NORMAL` payload, persisted and effective
modes both resolve to `NORMAL`, and the shared checkout is clean.

Rollback is restoration of the exact snapshot above. No rollback was needed.
Two fail-closed pre-write attempts (snapshot-directory ownership, then Git
safe-directory context) made no state change before the successful bounded
run.

## Required follow-ups

### SEC-1 — legacy read-only compatibility firewall

SEC-1 must default-deny mutating or unknown legacy combinations:

- Docker: explicit safe read-only subcommands only.
- Systemd: `status`, `show`, and `is-active` for allowlisted units only.
- `fs_stat`/`fs_ls`: allowlisted roots and options only.
- Audit: normalized subcommand, classification, and redacted digest; no raw
  values that could contain secrets.
- After an observation window without required legacy clients: remove legacy
  protocol completely.

This is a separate code PR after the reconcile PR merges.

### SEC-3 — durable intent audit

Add a pre-execution intent record, explicit durability boundary, linked
completion record, and crash/power-loss-oriented tests. Existing entry counts
do not waive this requirement.

### Kill-switch path and scoped freeze

Track separately from SEC-1:

- one canonical shared path;
- explicit host/container configuration;
- one canonical query returning persisted and effective mode;
- expiry, missing-file, host, and container tests; and
- later strategy-entry integration for `HALT_BOT`/`scoped_freeze`.

Do not modify the physical file again merely to simplify documentation.

## Decision

P0 evidence collection is complete. The runtime is not declared green:
legacy use, audit durability, deployment atomicity, extra workloads, fleet
completeness, and scoped-freeze wiring remain reconciliation items.

**GO:** this A1 state-reconcile PR; SEC-1 as a separate PR after human merge.

**NO-GO:** R5B continuation, executor deployment, container or strategy
mutation, live trading, kill-switch bypass, or any new root capability.

Repository work stops at `READY_FOR_HUMAN_MERGE`; Luke is the only merger.
