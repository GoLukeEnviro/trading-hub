# Agent0 — AUTONOMOUS_DRY_RUN activation (2026-09-18)

> Gate 1–4 of the master GOAL (`MASTER-GOAL: RiskGuard v1 fertigstellen und
> SI-v2 auf Agent0 vollständig in den sicheren Modus AUTONOMOUS_DRY_RUN
> überführen`, owner authorization 2026-09-18). Status:
> **`SAFETY_CONTROL_PLANE_GREEN_NO_QUALIFIED_PROPOSAL`** — see §10.

---

## 1. Gates, issues, PRs, merge commits

| Gate | Issue | PR | Merge commit | Result |
|---|---|---|---|---|
| 1 — RiskGuard baseline contract v1 | #749 | #750 | `586f13c` | `RISKGUARD_CONTRACT_V1_MERGED` |
| 2 — RiskGuard runtime init | — (runtime) | — | — | `SAFETY_CONTROL_PLANE_GREEN` |
| 3 — Controlled canary proof | — (runtime) | — | — | `NO_QUALIFIED_PROPOSAL` (chain proof) |
| 4 — AUTONOMOUS_DRY_RUN activation | #752 | #753 | `095464d` | activated; first automatic run proven |

## 2. RiskGuard contract and runtime state

- Contract v1 active: `docs/specs/riskguard-baseline-contract-v1.md`
  (schema `riskguard_state` v1, contract `riskguard_baseline_contract_v1`
  v1.0.0, repo-relative canonical path).
- Runtime state initialized with the merged initializer **only**:
  `<checkout>/orchestrator/state/riskguard/riskguard_state.json`,
  sha256 `167a7e147aa0529f4b09e04318a54ebc717ca47c5d6c7320c0add6c5dd66f454`,
  owner `hermes:hermes`, mode `0644`, `binding_commit=586f13c`, mode `ACTIVE`,
  `operating_mode=DRY_RUN_ONLY`, `live_authority=false`, exactly the three
  allowed bots, `freqai-rebel` forbidden.
- Pre-state: the directory did not exist (nothing overwritten); backup
  evidence in `/opt/data/backups/riskguard-init-20260918T152052Z/`.
- Consumer: `derive_riskguard_status` → `PASS`;
  cycle bundle `control_plane.riskguard.status=PASS` (sha-bound).

## 3. Owner authorization and scope

- Marker: `docs/decisions/APPROVED_AUTONOMOUS_DRY_RUN_AGENT0.md`
  (Luke; Agent0; three allowed dry-run bots; canary-first; existing
  parameter allowlist; no live trading; references the operator GOAL; no
  cryptographic signature invented).
- Runtime activation record (tamper-checked by the evaluator):
  `/opt/data/logs/si-v2-apply-chain/state/activation.json`.
- Not authorized and not done: `dry_run=false`, live capital, exchange keys,
  new pairs/strategies, risk-limit increases, `freqai-rebel`, holdout/Gate-0.

## 4. Canary / no-apply result (Gate 3)

- Only real candidate in the newest bundles: `dfd4063b030da46c` targeting
  `freqtrade-regime-hybrid` (the canary never had a candidate).
- Full chain proof (real candidate, unmodified): pipeline `BLOCKED`
  (`non_canary_target`), executor `EXECUTOR_BLOCKED`, **zero** artifacts
  written, container identities/restart counts unchanged.
- Result: `NO_QUALIFIED_PROPOSAL` — the automation correctly applied
  **nothing**. Evidence: `/tmp/ag0/g3_chain_proof.json` (host local) and the
  cycle bundles of `20260918T143928Z`, `20260918T144426Z`, `20260918T152121Z`.

## 5. Measurement decision

- No apply happened, so no measurement window opened. The ledger contains no
  ACTIVE/OPEN window (`BASELINE_ONLY` + `PENDING_APPLICATION` only) — this is
  the correct state for `NO_QUALIFIED_PROPOSAL`.
- The measurement contract itself is unchanged: window, decision gates
  (`KEEP` / `ROLLBACK` / `EXTEND` / `INVALID`) and rollback obligations stay
  as specified in the master GOAL §Gate 3.

## 6. Scheduler and watchdog evidence

- Exactly **one cycle scheduler**: `si-v2-active-cycle-agent0`
  (`5f26075be2cb`, `17 */6 * * *`), now with the apply-chain evaluation step
  under its own `.apply-chain.lock`.
- Exactly **one watchdog**: `si-v2-watchdog-agent0` (`fdae4e06667c`,
  `23 * * * *`, alert-only, no repair). First **automatic** watchdog run:
  18:23:36 local (`on_time`), status `ok`, `rc_problems=none fleet=5
  ks=NORMAL rg=PASS`.
- First **automatic** post-activation run: cycle `20260918T161738Z` at
  18:17:36 local (`fleet_verdict=GREEN`, `ping_ok=3/3`, rainbow
  `SUCCESS/read_only`, all mutation counters 0) with the apply chain logging
  `apply_chain_status=NO_QUALIFIED_PROPOSAL`.
- Apply-overlap lock proven: a second acquire while held is refused.
- Alerts: Telegram delivery to `telegram:610209401` verified (`sent`),
  BLOCKER/PREPARED events alert; `NO_QUALIFY` stays silent.

## 7. Reboot / recovery proof

- Scheduler registration survives restart: two jobs, each exactly once
  (`hermes cron list` + `jobs.json`); ticker heartbeat fresh.
- RiskGuard state re-validates against contract v1
  (`validate_state ok=True`), kill-switch reads consistent (`NORMAL`).
- Incomplete-transaction fail-closed: an interpreter state without the
  authorization marker yields `BLOCKED_MARKER` with
  `executed_runtime=false` — no unknown change is continued after recovery.
- Fleet healthy before and after every probe; no restarts.

## 8. Backup and restore proof

- Config/state snapshot: `/opt/data/backups/agent0-autonomous-dryrun-20260918T161821Z/`
  (3 bot configs with SHA-256, kill switch, RiskGuard state, scheduler
  inventory `jobs.json`, SI-v2 evidence inventory).
- Kill-switch proof: host `NORMAL`, sha
  `47c7d924e2a526f7fef4d3c0dc49bad050198ed2cf6b72c835e9373bad86da1c`.
- Isolated restore test: `RESTORE_PROOF=PASS` (fresh kill-switch and
  RiskGuard reads pass on restored copies; canary config `dry_run=true`).

## 9. Mutation counters and live-trading proof

- All cycle mutation counters 0 (runtime, config, live-trading, docker,
  strategy) in every cycle, including the post-activation automatic run.
- `live_authority=false` in the contract state; no live orders, no exchange
  keys, no `dry_run=false` anywhere. **Live trading: still 0.**

## 10. Status line and next step

```text
STATUS=SAFETY_CONTROL_PLANE_GREEN_NO_QUALIFIED_PROPOSAL
RISKGUARD_CONTRACT=ACTIVE (586f13c)
RISKGUARD_STATE=PASS (167a7e14…)
KILL_SWITCH=NORMAL (host+projection consistent)
FLEET=5/5 healthy; SI-v2 cycle GREEN; mutations 0
SCHEDULER=exactly one cycle job + exactly one watchdog
AUTONOMOUS_DRY_RUN=ACTIVATED (marker APPROVED_AUTONOMOUS_DRY_RUN_AGENT0)
APPLY_CHAIN=canary-first, fail-closed, prepare-only
CANARY_APPLY=none (NO_QUALIFIED_PROPOSAL — no canary candidate existed)
RUNTIME_EXECUTION_WIRED=false (deliberate; next step)
LIVE_TRADING=NO
```

**One next step:** wire the runtime execution stage of the apply chain —
verify the R7A topology end to end (overlay consumption via compose
override, ceremony `execute_runtime=True`, `RuntimeEffectProof`) and only
then enable it, so a future qualified canary candidate can be applied and
measured automatically.
