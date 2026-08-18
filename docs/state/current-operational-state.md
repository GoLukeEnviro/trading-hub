# Trading Hub — Current Operational State

> **Canonical current-state snapshot.** Reconciled on 2026-08-18 after #702 reopen (auto-close corrected: PR #714 delivered only the A1 Precondition-Teil; the A2 selection backtest did **not** run) and #708 completion (Luke decision `FUNDING_CONTRACT_V2_OPTION=A` 2026-08-18 comment 5329852393; contract v2 frozen via PR #712 `fa3fb89` merged). Phase C exit gate `edge_decision_recorded` is **not yet satisfied** (Gate-0 `EXTEND`; #702 A2 execution is **operator-gated** — see the #702 section). Phase C remains `in_progress`.
>
> **Previous:** 2026-08-18 after #708 completion (Luke decision `FUNDING_CONTRACT_V2_OPTION=A`; contract v2 frozen via PR #712 `fa3fb89` merged; state reconciled via PR #713) and #705 completion (canonical funding data contract, PR #706 `96f1865`).
>
> **Previous:** 2026-08-13 after #708 reopen (auto-close corrected; options analysis PR #709 `90fb9d9` merged; **Luke decision pending**) and #705 completion (canonical funding data contract, PR #706 `96f1865`).
>
> **Previous:** 2026-08-02 after #674 completion. A0 preflight GREEN (PR #682, `72421de`). Backtest Contract GREEN (PR #687, `79ad6dd`). Issue backlog reconciled: 27→5 open issues. #674 complete (PR #690, `ea04ca2`).
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
governance_contract_revision: 2
roadmap_revision_observed: 6
roadmap_observed_at_utc: 2026-08-04T14:00:00Z
```

`governance_contract_revision` is strictly checked against
`config/governance/program-contract.yaml`; `roadmap_revision_observed` is
informational only and does not force a state-file touch on ordinary roadmap
status changes.

## Standing Owner Authorization (2026-08-04)

```text
OWNER_STANDING_AUTHORIZATION=ACTIVE
OWNER_STANDING_AUTHORIZATION_SOURCE=#605_COMMENT_5179703046
PER_TASK_HUMAN_MARKER_REQUIRED=NO
A1_MERGE_HUMAN_GATE=STANDING_APPROVED
A2_HUMAN_GATE=STANDING_APPROVED
A3_HUMAN_GATE=STANDING_APPROVED_WHEN_TECHNICAL_CONTRACT_IS_GREEN
```

Luke granted the Standing Owner Authorization on 2026-08-04 (#605 comment
`5179703046`, `OWNER_STANDING_AUTHORIZATION_V1`). Missing per-task human
markers are no longer valid blockers. All technical guardrails (CI, merge
guard, writer lock, branch protection, snapshot, canary, allowlist, rollback,
audit, measurement, RiskGuard, kill switch, C4 KEEP, runtime baseline,
breakglass, revocation) remain required. See
`docs/decisions/ADR-2026-08-04-standing-owner-authorization.md`.

## Issue #697 — Freqtrade-native dataset (A2 run complete)

```text
ISSUE_697_A2_RUN=COMPLETE
RUN_ID=issue697-20260803T155723Z
DATASET_PATH=/opt/data/gate0-freqtrade-native-r1
FUNDING_CONTRACT_DECISION=REJECT_INCOMPLETE_FUNDING
GATE0_DISPOSITION=EXTEND
SELECTION_BACKTEST_AUTHORIZED=NO
HOLDOUT_INSPECTED=NO
LIVE_TRADING=NO
```

The A2 download/freeze run completed with accepted outcome B: native
Freqtrade/CCXT funding history is reproducibly capped (~90 days; the run
persisted one page of ~33 days per pair). The human funding decision
(#697 comment `5179705029`) rejects incomplete funding for the canonical
Gate-0 selection, sets Gate-0 disposition `EXTEND`, and prohibits any
selection backtest until a new canonical funding data contract exists.

## Phase C — Gate-0 Strategy Evidence (2026-08-04, in progress)

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
| Issue backlog reconciled | ✅ `RECONCILED` | 27→5 open issues. See `docs/reports/repository-issue-backlog-reconciliation-2026-08-02.md` |
| #674 import-guard isolation | ✅ COMPLETE | PR #690 (`ea04ca2`): deterministic ImportError simulation, 18/18 tests. See `docs/reports/trading_pipeline-import-guard-isolation-2026-08-02.md` |
| #604 ratification | ✅ COMPLETE | Luke ratified V3_1 (comment 5168056708, 2026-08-03); issue closed completed |
| #697 native dataset | ✅ `EXECUTED` | RUN `issue697-20260803T155723Z`, 12 files / 254,425 rows, frozen at `/opt/data/gate0-freqtrade-native-r1`; funding incomplete (native + REST ~90d cap) |
| Funding contract decision | ✅ `REJECT_INCOMPLETE_FUNDING` | Luke (#697 comment 5179705029); Gate-0 disposition `EXTEND`; selection backtest NOT authorized |
| Holdout inspected | ❌ NO | Not started; blocked by funding contract decision (no valid selection backtest) |
| Edge decision | ⏳ `PENDING` | Not yet recorded; requires new canonical funding data contract first |

Phase C remains `in_progress` until the edge decision is recorded. Issue #604
is closed (ratified); #697 is reconciled (accepted outcome B).

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

1. **#683** — ✅ DONE (recovery executed 2026-08-13, `RUNTIME_BASELINE_GREEN`; issue closed)
2. **#604 ratification** — ✅ COMPLETE (Luke ratified V3_1, comment 5168056708, 2026-08-03)
3. **#697 native dataset** — ✅ EXECUTED (RUN `issue697-20260803T155723Z`, frozen; funding incomplete)
4. **Funding contract decision** — ✅ `REJECT_INCOMPLETE_FUNDING` (Luke, #697 comment 5179705029); Gate-0 disposition `EXTEND`
5. **#699 A1 prerequisite (PR #700)** — ✅ MERGED (`a5c1d99`, 2026-08-13): `scripts/hermes-native-change-c.sh` on `main`
6. **#699 A2 host execution (Hermes 0.19.0 → 0.20.0 via Change C)** — ⏳ `BLOCKED_BY_MISSING_A2_TECHNICAL_PREREQUISITES` (see section below)
7. **#705 canonical funding data contract** — ✅ COMPLETE (PR #706 `96f1865`, 2026-08-13)
8. **#708 new canonical funding data contract (longer history)** — ✅ COMPLETE (Luke decision `FUNDING_CONTRACT_V2_OPTION=A` 2026-08-18 comment 5329852393; contract v2 frozen via PR #712 `fa3fb89` merged 2026-08-18; issue closed)
9. **Create A2 Selection Backtest issue** — ✅ DONE (#702 created 2026-08-13)
10. **Execute selection-only backtest** — ⏳ **OPERATOR-GATED** (see the #702 section below): A1 precondition merged (PR #714 `0bf5db1`); A2 execution blocked on (a) results-dir ownership and (b) executor-policy approval marker. One operator action unblocks it: `sudo chown 10000:10000 /opt/data/gate0-backtest-results`
11. **Record PASS_SELECTION / EXTEND / REJECT / INVALID**
12. **C6 holdout ceremony** — only after valid selection outcome
13. **Record canonical Gate-0 edge decision**
14. **Execute #600 ADR**
15. **Reassess #496**

## Issue #705 — Canonical Funding Data Contract (2026-08-13)

**Status:** `COMPLETE` — PR #706 merged `96f1865` (2026-08-13T19:09:16Z), issue closed.

The canonical funding data contract for the Gate-0 selection backtest is
defined and implemented (A1, repository-only):

| Deliverable | Result | Evidence |
|---|---|---|
| Funding contract documented | ✅ | `docs/reports/canonical-funding-data-contract-2026-08-13.md` (source, ~90-day limit, coverage criterion, fail-closed gap handling) |
| Fallback source evaluated | ✅ VERWORFEN | Bitget WS replay (real-time only); external archives (Tardis.dev/CryptoHFTData) + synthetic/zero-fill (`external_data_mix=PROHIBITED`, `synthetic_funding=PROHIBITED`, `funding_rate_zero=PROHIBITED` — Luke #697 `5179705029`) |
| Adapter hardening | ✅ | `FundingCoverage`, `compute_funding_coverage()`, `validate_funding_coverage()` (fail-closed), `funding_coverage_report()`, `convert_funding_to_freqtrade_with_coverage()` (no partial file on incomplete coverage) |
| Tests | ✅ | 18 new tests; 63/63 `test_backtest_contract.py`; 138/138 contract suites from repo root; 29/29 safety scanners; Ruff clean |

**Contract values:** `FUNDING_STATUS=INCOMPLETE_CONFIRMED_NATIVE_LIMIT`,
`FUNDING_SOURCE=bitget_rest`, `FUNDING_HISTORY_LIMIT_DAYS=90`,
required window `2024-12-01T00:00:00Z` → `2026-06-30T00:00:00Z` (no grace).

**Consequence:** the canonical dataset does **not** satisfy the coverage
criterion. Per Luke's decision (`REJECT_INCOMPLETE_FUNDING`, Gate-0
disposition `EXTEND`), the selection backtest (#702) is **not authorized**
until a new canonical funding data contract (longer history) exists.

## Issue #708 — New Canonical Funding Data Contract v2 (2026-08-13)

**Status:** `COMPLETE` — Luke decision `FUNDING_CONTRACT_V2_OPTION=A`
(2026-08-18, comment 5329852393); contract v2 frozen via PR #712
`fa3fb89` merged 2026-08-18T15:11:52Z; issue closed (decision signed
before merge — auto-close now correct).

**Frozen contract values (Option A):**
`FUNDING_CONTRACT_V2_OPTION=A` · `FUNDING_STATUS=INCOMPLETE_CONFIRMED_NATIVE_LIMIT` ·
`FUNDING_COST_MODEL=ESTIMATED_GAP` · `FUNDING_ESTIMATE_METHOD=PER_PAIR_MEDIAN_CAPPED` ·
`FUNDING_ESTIMATE_CAP=0.001` · `FUNDING_ESTIMATE_LABEL=ESTIMATED`.

Semantics: dataset coverage criterion stays fail-closed (no grace, no
silent gaps); cost-model gap filled with a per-pair median estimate
derived exclusively from real observed rates, explicitly labeled
`ESTIMATED`, with uncertainty band. `synthetic_funding=PROHIBITED` and
`funding_rate_zero=PROHIBITED` remain binding.

The #705 contract confirmed no policy-compliant fallback source for longer
funding history exists. Issue #708 (created 2026-08-13) delivers the
read-only options analysis and decision framework:

| Option | Description | Policy fit | Gate-0 progress |
|---|---|---|---|
| A | Documented gap, best-effort funding estimate in cost model | ⚠️ needs narrow Luke confirmation (estimate ≠ `synthetic_funding`) | ✅ with uncertainty band |
| B | Window reduction to available funding coverage | ✅ | ✅ weaker evidence (manifest change) |
| C | Keep `REJECT_INCOMPLETE_FUNDING` / `EXTEND` (no backtest) | ✅ | ❌ stall |
| D | Narrow policy amendment for external funding archive | ❌ needs amendment | ✅ strongest |

**Recommended default (no new decision):** Option C. If Luke wants Gate-0
progress: **Option A** (smallest compliant step, needs explicit confirmation).

**Decision framework:** `docs/reports/canonical-funding-data-contract-v2-options-2026-08-13.md`.
Luke's signed comment (2026-08-18, comment 5329852393) selected **Option A**;
the contract values are frozen in `si_v2/research/backtest_contract.py` (PR #712).

## Issue #702 — Selection-only backtest (A2, operator-gated; reopened 2026-08-18)

**Status:** `REOPENED` — A1 precondition merged; A2 execution **NOT started**
(`OPERATOR_GATED`).

PR #714 (`fix/research: make Gate-0 backtest command executable and allowlist
Gate-0 paths`, merge `0bf5db1`, 2026-08-18T16:44:23Z) delivered the **A1
Precondition-Teil** of #702 only:

- `BACKTEST_COMMAND` fixed: `--user 10000:10000` → `--group-add 10000`
  (ftuser + supplemental GID 10000; the pinned image cannot execute
  `--user 10000:10000` — #697 finding, verified 2026-08-18)
- Executor allowlist extended: `/opt/data/gate0-freqtrade-native-r1` (read)
  and `/opt/data/gate0-backtest-results` (read+write)
- CI 3/3 SUCCESS, merge guard `ready:true`, blockers `[]`

Because the PR body contained `Closes #702`, GitHub auto-closed #702 at
2026-08-18T16:44:24Z — **one second after the merge**. The A2 selection
backtest itself had **not** run (no results persisted, no
`PASS_SELECTION`/`EXTEND`/`REJECT`/`INVALID` recorded). This is the same
decision-issue auto-close trap documented for #708 (PR #711). The issue was
**reopened** (REST `state=open`) with a documenting comment; the merge
happened **before** the A2 deliverable, so the auto-close is incorrect.

**A2 execution blockers (verified 2026-08-18, live):**

1. **Results-dir ownership:** `/opt/data/gate0-backtest-results` is
   `deploy:deploy 2770` (created 2026-08-18T15:51Z) — neither `hermes`
   (uid 10000) nor the backtest container (ftuser + GID 10000) can write.
   Operator action: `sudo chown 10000:10000 /opt/data/gate0-backtest-results`
2. **Executor-policy approval marker:** server-side `policy.py`
   `APPROVED_MARKERS = {APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION,
   APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT}`. The Owner blanket
   authorization (2026-08-18, documented on #702) is **not** one of these
   markers; any A2 executor mutation is rejected server-side with
   `approval_reference_missing_or_invalid` (verified live via `fs_chown`
   probe). Not interpretable or bypassable by the agent.

**Remaining acceptance criteria of #702 (still open):** marker/policy
unblock (operator), selection-timerange `[2024-12-01, 2026-01-01)`, holdout
physically absent, walk-forward + regime coverage + costs/funding/slippage,
confidence gates, `lookahead-analysis` + `recursive-analysis`, reproducible
second run, outcome record.

**Prohibitions remain binding:** no holdout access, no live trading, no
`dry_run=false`, no exchange keys, no frozen-dataset mutation, no pin
changes.

## Issue #699 — Hermes 0.20.0 upgrade via Change C (A2 gate status)

**Status:** `A1_PREREQUISITE_MERGED` — A2 host execution NOT started.

| Gate | Status | Evidence |
|---|---|---|
| A1 prerequisite PR #700 | ✅ MERGED | `a5c1d99` (2026-08-13T13:32:52Z); CI green on head `0a026006` |
| Change-C script on `main` | ✅ PRESENT | `scripts/hermes-native-change-c.sh` (plan/stage/pre-cutover/cutover/validate/rollback/report) |
| Target release pinned | ✅ PRESENT | 0.20.0 / `v2026.8.3` / `3c27eb62…` (script constants) |
| Backup + restore drill | ❌ NOT PROVEN | no `backup-proof.json` at `/var/lib/hermes-native-change-c/`; no restore-drill evidence found on host |
| Executor action to run change-c | ❌ ABSENT | deployed executor @ `9551977` has no `run_script`/`change_c` action (registry: systemd/docker/fs/git/caddy/ufw/hostname/sysctl/users only) |
| Staged 0.20.0 release | ❌ NOT STAGED | `/opt/hermes-native/releases/` contains only 0.18.2 + 0.19.0; `current` → 0.19.0 |
| Snapshot / rollback / audit | ⏳ PENDING | required by issue contract; not yet in place for this upgrade |

**Blocker:** `BLOCKED_BY_MISSING_A2_TECHNICAL_PREREQUISITES` — the issue's own
acceptance criteria require (a) a verified backup + restore drill and (b) an
execution path for the Change-C script. The deployed root executor has no
action that can run `scripts/hermes-native-change-c.sh` (no generic shell
execution by design), and no backup proof exists. The A2 host execution must
not start until these technical prerequisites are green. No runtime mutation
was performed by this tick.

## Issue #683 — Runtime Closure Reconciliation (2026-08-13)

**Status:** `RUNTIME_BASELINE_GREEN` — recovery executed 2026-08-13, issue closed.

The 2026-08-02 read-only reconciliation (below) found the runtime baseline NOT
restored. The recovery run on 2026-08-13 (issue #683,
`APPROVED_A2_HERMESTRADER_RUNTIME_RECOVERY` + Standing Owner Authorization)
restored the control plane. Verified live on 2026-08-13 (this tick):

| Criterion | Result | Evidence |
|---|---|---|
| Executor service active | ✅ PASS | `systemctl is-active hermes-root-executor.service` = active; `executor_health` ALLOWED (audit `a43672d3`) |
| Executor action surface | ✅ PASS | Deployed @ `9551977`; `systemctl_is_active`, `docker_ps`, `fs_*` ALLOWED (audits `9ade2e61`, `5b1524d8`, `5c2b4e7d`, `dd835a4e`) |
| Writer lock | ✅ PASS | `/opt/data/state/repo-writer/hermes-repo-writer.lock` present (10000:10000, 0600); acquired by this tick |
| Dry-run fleet | ✅ PASS | 5/5 `Up (healthy)` via `docker_ps` (freqforge, freqforge-canary, regime-hybrid, webserver, rainbow) |
| dry_run=true configs | ✅ PASS | 5/5 configs `dry_run=True futures` (recovery report) |
| Native gateway | ✅ PASS | hermes-gateway/dashboard/desktop-serve all `active` (audits `9ade2e61`, `5b1524d8`, `5c2b4e7d`) |
| Roadmap cron | ✅ PASS | exactly 1 job `trading-hub-roadmap-tick` (`*/30 * * * *`, next run 2026-08-13T15:00Z) |
| Kill switch / live | ✅ PASS | `NORMAL`; live_trading=NO; holdout=NO |

**Full recovery report:** `/opt/data/hermes/recovery-683/recovery-report-2026-08-13.md`
(host-resident; pre/post hashes, backup manifest, smoke results, mutation inventory).

### Historical (2026-08-02) — superseded by the 2026-08-13 recovery

**Status:** `BLOCKED_BY_MISSING_A2_MARKER` — runtime baseline NOT green.

Read-only reconciliation (A0) on 2026-08-02 found the runtime baseline from
Issue #683 is **not restored**:

| Criterion | Result | Evidence |
|---|---|---|
| Executor service active | ✅ PASS | `systemctl is-active` = active; `executor_health` ALLOWED (audit `76a974ba`) |
| Executor action surface | ❌ FAIL | `fs_stat`, `fs_ls`, `systemctl_is_active`, `executor_version`, `executor_provenance` → `unknown_action`; deployed daemon ≠ repo (PR #677/#678) |
| SO_PEERCRED | ✅ PASS | UID-10000 client → root daemon audited responses |
| Writer lock | ❌ FAIL | `/opt/data/state/repo-writer/` missing |
| Dry-run fleet | ❌ FAIL | 5/5 containers **stopped** (Exited ~4 days ago) |
| dry_run=true configs | ✅ PASS | 5/5 configs `dry_run=True futures` |
| Native gateway | ✅ PASS | hermes-gateway/dashboard/target active; PID 1609337 |
| Roadmap cron | ❌ FAIL | **0 jobs**; `trading-hub-roadmap-tick` missing |
| Kill switch / live | ✅ PASS | `NORMAL`; live_trading=NO; holdout=NO |

**Blocker (historical):** The original A2 marker
(`APPROVED_A2_HERMESTRADER_RUNTIME_RECOVERY`, valid until 2026-08-01T18:00:00Z)
had expired. A fresh time-limited A2 marker from Luke was required before any
runtime mutation. No self-approval possible.

**Full report:** [`issue-683-closure-reconciliation-2026-08-02.md`](../reports/issue-683-closure-reconciliation-2026-08-02.md)

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

**Allowed next repository work:** A1 reconciliation is complete (this tick).
The next Gate-0 gate is the **A2 execution of the selection-only backtest
(#702)** — the A1 precondition merged (PR #714 `0bf5db1`, 2026-08-18) and
funding contract v2 Option A is frozen (PR #712 `fa3fb89`). #702 is reopened
and **operator-gated**: one host action
(`sudo chown 10000:10000 /opt/data/gate0-backtest-results`) plus a
policy-recognized A2 approval marker (or an explicit operator extension of
the executor `APPROVED_MARKERS`) are required before the A2 execution can
start. No A2 backtest and no holdout inspection until those are green.

**Not authorized:** executor deployment or restart, runtime proof, R5B
continuation, strategy reload, container mutation, kill-switch clear/bypass,
new root capabilities, live-capital changes, selection backtest on the frozen
dataset, synthetic funding, `funding_rate=0`, external data mixing, and the
#699 A2 upgrade itself until backup + restore drill and an execution path are
proven.

The repository writer remains single-writer and PR-only. Under the Standing
Owner Authorization (ADR-2026-08-04), A1 merges follow the path
`CI_GREEN → MERGE_GUARD_READY → EXACT_HEAD_REVERIFIED → MERGE →
POST_MERGE_RECONCILIATION`; `READY_FOR_HUMAN_MERGE` is no longer a terminal
state while the authorization is active.

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
