# ADR-2026-07-11: Hermes Root-Runtime-Authority (R0)

**Status:** Accepted
**Date:** 2026-07-11
**Author:** R0 Governance Decision (human-directed)
**Related roadmap:** Root-Runtime-Roadmap phases R0 – R7 (see `docs/state/current-operational-state.md`)

---

## Table of Contents

1. [Context](#1-context)
2. [Decision](#2-decision)
3. [Security Mechanisms of the Root Executor](#3-security-mechanisms-of-the-root-executor)
4. [External Live Authority Boundary](#4-external-live-authority-boundary)
5. [Explicitly NOT Auto-Authorized](#5-explicitly-not-auto-authorized)
6. [Relationship to D1/D2/D3 (SEC-1 Predecessor Architecture)](#6-relationship-to-d1d2d3-sec-1-predecessor-architecture)
7. [Consequences](#7-consequences)
8. [Follow-Up Phases](#8-follow-up-phases)
9. [References](#9-references)

---

## 1. Context

Since the SEC-1 hardening decision, Hermes (the meta-orchestrator container,
UID 10000) has operated under a strict least-privilege model with **no**
`docker.sock` access. Instead, Hermes was given narrow, purpose-built
capabilities, built up incrementally:

- **D1 — Read-only Docker proxy:** a `tecnativa/docker-socket-proxy`
  instance, internal-only, exposing a read-only subset of the Docker API.
  Hermes can observe container state but cannot mutate it.
- **D2 — Allowlisted host runner:** `hermes-runtime-runner`, a fixed-command
  host-side executor with a hardcoded action map, JSONL audit log, per-service
  locks, backup-freshness checks, and an approval-token gate for anything
  beyond `dry_run`.
- **D3 — Audited operator bridge:** `hermes-bridge`, a Unix-socket daemon
  exposing a small, versioned set of read (and later narrowly-scoped,
  approval-gated) actions to Hermes, with full JSONL audit and a kill switch.

This "narrow slice" model (D1 read-only visibility, D2 fixed-command
mutation, D3 audited bridge) was deliberately conservative: it let Hermes
prove operational value (fleet visibility, controlled apply, GitHub
reporting) without ever trusting it with general-purpose root authority.

As Hermes's operational scope grows (fleet migration from `agent0` to
HermesTrader, systemd/Docker/network administration, broader infrastructure
work), the fixed-command-map model becomes a bottleneck: every new
capability requires a new hardcoded action, a new allowlist entry, and a new
review cycle. This does not scale to "Hermes operates HermesTrader as a
general-purpose infrastructure agent."

**This ADR records the deliberate decision to lift that narrow-slice
restriction** and grant Hermes full root-level runtime authority over
HermesTrader — not by running the Hermes stack itself as root, but through a
dedicated, UID-separated root executor service. D1/D2/D3 are not deleted;
they are superseded as the primary access path and remain documented as
historical predecessor architecture (see [Section 6](#6-relationship-to-d1d2d3-sec-1-predecessor-architecture)).

> **Naming note:** the roadmap phases in this ADR (R0–R7) are unrelated to
> the "D1/D2 live fleet rollout" phase labels used elsewhere in
> `docs/state/current-operational-state.md` (SI-v2 canary/fleet rollout
> gating). Both happen to use short alphanumeric codes; they are different
> domains (runtime access architecture vs. SI-v2 trading rollout gating).

---

## 2. Decision

Hermes is granted **full root-level runtime authority** on HermesTrader,
implemented as a **UID-separated privilege boundary**, not as a
privileged container:

```
Hermes Agent / UI  (stays UID 10000, unprivileged)
        |
        | local authenticated Unix socket (peer-credential UID check)
        v
hermes-root-executor.service  (UID 0, full host/Docker authority)
```

- The Hermes agent and UI process **continue to run as UID 10000**,
  unprivileged, with no `docker.sock`, no `sudo`, and no root filesystem
  access of its own.
- A new **`hermes-root-executor.service`** (UID 0, implementation in **Phase
  R1**, not part of this ADR) is the only process with actual root
  authority. It listens on a **local-only Unix domain socket** — no TCP, no
  network exposure.
- Hermes talks to the executor exclusively through that socket. The executor
  authenticates the caller via **`SO_PEERCRED`** (kernel-enforced peer
  credential check against the connecting UID), so only the Hermes UID (or
  other explicitly allowed local UIDs) can issue commands — the socket
  cannot be reached from outside the host and cannot be spoofed by a
  non-root, non-Hermes local process.
- Once implemented (Phase R1), the executor can perform full Docker
  management, systemd unit control, host filesystem operations, user/group
  administration, and firewall/network configuration — the complete set of
  host administration actions, not a fixed allowlist of pre-approved
  commands.

This is a **governance and architecture decision** (R0). The executor itself
is **not implemented by this ADR** — implementation is Phase R1 of the
Root-Runtime-Roadmap (see [Section 8](#8-follow-up-phases)).

---

## 3. Security Mechanisms of the Root Executor

The root executor (Phase R1 implementation) MUST provide the following
mechanisms; they are binding design constraints for that phase, recorded
here at decision time:

| Mechanism | Purpose |
|-----------|---------|
| **Local socket only** | No TCP listener, no network exposure. Unreachable from outside the host, including from other Tailscale nodes. |
| **Peer-credential check (`SO_PEERCRED`)** | Kernel-enforced verification of the connecting process's UID before accepting any command. Only the Hermes UID (and any other explicitly allowlisted local UID) may issue commands. |
| **Exclusive locks** | Per-resource (e.g. per-container, per-service) locking to prevent concurrent conflicting mutations. |
| **Command timeout** | Every executed command has a bounded maximum runtime; the executor must not allow indefinitely hanging operations. |
| **Full audit log** | Every command, its caller, arguments, timestamp, and result are logged append-only, mirroring the JSONL audit discipline already established by D2/D3. |
| **Secret redaction in logs** | Audit logs and command output must never contain credentials, tokens, or key material in cleartext; redaction happens before persistence. |
| **Emergency disable switch (kill switch)** | A kill-switch file/mechanism that immediately halts all executor command processing, independent of any individual command's own safety logic. |

---

## 4. External Live Authority Boundary

Full root authority means that **locally-enforced safety controls are
technically bypassable by definition**: a process with root authority could,
in principle, edit its own `dry_run` flag, overwrite or delete a kill-switch
file, or fabricate its own local "approval" artifact, because root can
modify any local file. Root authority therefore **cannot be the basis** for
authorizing live trading with real capital. A separate, externally-anchored
control is required — and is the central safety mechanism of this whole
architecture:

- **Root access authorizes host and dry-run runtime actions only** —
  infrastructure administration, deployment, configuration, Docker
  management, and diagnostics. It does **not**, by itself, authorize any
  live-capital action.
- **Live actions (`dry_run=false`, real capital in trading) require an
  externally signed, time-limited approval artifact**, containing at
  minimum: task, target bot, expiry time, nonce, and the specific permitted
  action.
- **The private signing key never resides on HermesTrader.** Only the
  corresponding **public key** lives on the host. The root executor
  verifies signatures only — it has no capability to mint a valid approval
  itself, because it never possesses the private key.
- **Live exchange credentials do not reside on the host** prior to formal,
  explicit sign-off for live operation.
- **A locally created marker or file (e.g. a self-written `approved.json`)
  is never sufficient live authorization** — only a cryptographically
  signed, externally issued approval counts.
- **Live trading remains a separate, independently approval-gated
  concern.** Root access is infrastructure authority; it is not, and must
  never be treated as, live-trading authority. This separation is the
  central safety mechanism of this entire architecture and must not be
  weakened by any future phase without a new, explicit ADR.

---

## 5. Explicitly NOT Auto-Authorized

The following remain blocked even with full root runtime authority in
place, and require the External Live Authority Boundary approval described
above:

- `dry_run=false` / disabling dry-run mode
- Real live trading of any kind
- Provisioning exchange secrets for real capital
- Increasing capital limits
- Weakening RiskGuard checks or thresholds
- Bypassing or disabling the kill switch

---

## 6. Relationship to D1/D2/D3 (SEC-1 Predecessor Architecture)

D1 (read-only Docker proxy), D2 (allowlisted host runner), and D3 (audited
operator bridge) are **not deleted and not retroactively wrong** — they were
the correct conservative first step and remain documented, working
infrastructure. Their status changes as follows:

- **Status: superseded as the primary Hermes access path**, effective with
  this ADR (R0) and full effect after Phase R1 ships.
  - `hermes-runtime-runner` (D2), `hermes-bridge` (D3), and the read-only
    Docker proxy (D1) may continue running during the R1–R2 transition and
    can serve as a fallback/rollback path if the root executor needs to be
    disabled.
  - Once the root executor (R1) is implemented, audited (R2), and load-bearing,
    D1/D2/D3 are expected to be retired in favor of the single root-executor
    path — that retirement is itself a future decision, not made by this
    ADR.
- Historical implementation detail for D1/D2/D3 remains in the memory
  records `hermestrader-d1-readonly-docker-visibility.md`,
  `hermestrader-d2-impl.md`, and the D3 bridge series
  (`hermestrader-d3-bridge-slice1.md` through
  `hermestrader-d3-bridge-protocol-fix.md`) and is not reproduced here.

---

## 7. Consequences

### Positive

- Removes the scaling bottleneck of a fixed-command allowlist: new
  operational capabilities (systemd, networking, user management, general
  Docker administration) no longer each require a bespoke D2-style action
  and review cycle.
- Keeps a clean, auditable **UID separation** between the unprivileged
  Hermes process and the privileged executor, rather than running Hermes
  itself as root.
- Establishes, at the governance level, a hard architectural boundary
  between infrastructure authority (root-capable) and live-trading
  authority (externally signed only) — this is a stronger guarantee than
  the previous model, which had no explicit statement of this boundary.
- D1/D2/D3 remain available as a conservative fallback path during the
  transition.

### Risks

- A compromised or buggy `hermes-root-executor.service` has full host
  authority; the blast radius of any executor defect is much larger than
  under the D1/D2/D3 model. This makes the Section 3 security mechanisms
  (peer-credential check, audit, kill switch, timeouts) load-bearing, not
  optional hardening.
- Peer-credential checks rely on correct UID hygiene on the host; any future
  user/group misconfiguration (see the shared-group and operator-console UID
  history in this project) could widen the set of callers able to reach the
  executor. UID allowlists must be reviewed whenever new local users are
  added.
- Until D1/D2/D3 are formally retired, there are two parallel access paths
  to Hermes-triggered host mutation; operators must track which path is
  authoritative during the transition to avoid split-brain audit trails.

### Future work (not part of this ADR)

- **Phase R1** — implement `hermes-root-executor.service` per Section 3.
- **Phase R2** — audit, locking, and mutation evidence hardening on top of
  R1.
- **Phases R3–R5b** — fleet reproducibility decision and migration of the
  four trading bots (`freqforge`, `freqforge-canary`, `regime-hybrid`,
  `freqai-rebel`) from the old `agent0` VPS to HermesTrader. **As of this
  ADR, all four bots still run exclusively on `agent0`** — this decision
  does not move them, and no bot is running locally on HermesTrader yet.
- **Phase R6** — permanent reconciliation via systemd.
- **Phase R7** — SI-v2 runtime integration (shadow/dry-run only, gated
  independently per the External Live Authority Boundary above).

---

## 8. Follow-Up Phases

| Phase | Scope |
|-------|-------|
| R0 (this ADR) | Governance decision: root-runtime-authority model, External Live Authority Boundary |
| R0.5 | Secret exposure architecture closure |
| R1 | Implement unprivileged Hermes + `hermes-root-executor.service` |
| R2 | Audit, locking, and mutation evidence hardening |
| R3 | Fleet reproducibility decision |
| R4 | Greenfield compose stack and Rainbow runtime |
| R5a | HermesTrader deployment and parity |
| R5b | `agent0` cutover |
| R6 | Permanent reconciliation via systemd |
| R7 | SI-v2 runtime integration (shadow/dry-run only) |

---

## 9. References

| Document | Location |
|----------|----------|
| AGENTS.md — Hermes / VPS Operator Console sections | `AGENTS.md` |
| SOUL.md — Git and Documentation Discipline | `SOUL.md` |
| Current operational state | `docs/state/current-operational-state.md` |
| D1 read-only Docker visibility (memory) | `hermestrader-d1-readonly-docker-visibility.md` |
| D2 runtime runner implementation (memory) | `hermestrader-d2-impl.md` |
| D3 operator bridge series (memory) | `hermestrader-d3-bridge-slice1.md`, `hermestrader-d3-bridge-wiring.md`, `hermestrader-d3-bridge-protocol-fix.md` |
| VPS Operator Console (PR #486) | `docs/context/hermestrader-operator-console-20260710.md` |
| Issue #423 | Canonical roadmap issue, GoLukeEnviro/trading-hub |
| Issue #504 (R7A) | Bot-fleet architecture, GoLukeEnviro/trading-hub |
