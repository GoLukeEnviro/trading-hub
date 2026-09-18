# RiskGuard Baseline Contract v1

**Status:** Active · **Contract:** `riskguard_baseline_contract_v1` · **Schema:** `riskguard_state` v1 · **Contract version:** 1.0.0
**Issue:** #749 (Gate 1 of the Agent0 autonomous dry-run master plan, #730)
**Binding repository commit:** current `origin/main` at the time of state initialization (recorded in the state file)

> This contract defines the **versioned, conservative dry-run-only baseline** for
> the RiskGuard state consumed by the SI-v2 apply gates on Agent0. It does not
> enable live trading and grants no live authority. Anything missing, corrupt,
> unknown or out of scope fails closed.

---

## 1. Identity

| Field | Value |
|---|---|
| Contract name | `riskguard_baseline_contract_v1` |
| Schema name | `riskguard_state` |
| `schema_version` | `1` |
| Contract version | `1.0.0` |
| Canonical state path (Agent0) | `<checkout>/orchestrator/state/riskguard/riskguard_state.json` (repo-relative; the consumer resolves it from the repository root, so it is identical on the source host and on Agent0) |
| Owner / mode | `hermes:hermes`, file mode `0644`, directory owned by the checkout owner |
| Schema file | `self_improvement_v2/contracts/riskguard_state.schema.json` |
| Initializer | `self_improvement_v2/scripts/riskguard_init_baseline.py` |
| Module | `self_improvement_v2/src/si_v2/risk/riskguard_baseline.py` |
| Consumer adapter | `derive_riskguard_status` / `read_riskguard_status` in `controlled_apply_actuator.py` |

**Consumer semantics (unchanged):** PASS requires `summary.status == "ACTIVE"`,
at least one pair with verdict `ACCEPTED`, and **no** pair with verdict
`BLOCK_ENTRY`. Everything else — including missing/corrupt/unknown state — is
`FAIL` and blocks.

## 2. Operating mode

- `mode` is `ACTIVE`, `operating_mode` is `DRY_RUN_ONLY`.
- `live_authority` is `false` — always. A state with `live_authority=true` is
  invalid and fails closed.
- There is **no implicit upgrade path to live**: switching operating modes is a
  separate, externally approved mode transition outside this contract.
- Missing, corrupt, unknown-schema or unreadable state blocks fail-closed.

## 3. Bot scope

**Allowed (exactly three trading bots):**

| Bot | Role |
|---|---|
| `freqtrade-freqforge` | Trading bot (dry-run) |
| `freqtrade-freqforge-canary` | Canary trading bot (dry-run, first apply stage) |
| `freqtrade-regime-hybrid` | Trading bot (dry-run) |

**Explicitly not allowed:**

- `freqai-rebel` (profile-gated; `NOT_REPRODUCIBLE` per ADR-2026-07-11),
- unknown bot IDs,
- `freqtrade-webserver` and `rainbow` as trading actors.

Unknown bots, pairs and actions are fail-closed (`BLOCK_ENTRY` semantics).

## 4. Change allowlist

Only already-implemented, documented and reversible dry-run parameters are
admissible. **No new parameter is invented by this contract.**

Admissible parameters (source: `safe_parameters.SAFE_PARAMETERS` + ranges):

| Parameter | Accepted range |
|---|---|
| `rsi_period` | 2 – 50 |
| `stoploss_pct` | −0.5 – −0.001 |
| `take_profit_pct` | 0.001 – 0.5 |
| `stake_factor` | 0.1 – 5.0 |
| `max_open_trades` | 1 – 20 |
| `cooldown_candles` | 0 – 100 |

Explicitly locked: `dry_run`, exchange/credential fields, pairlist expansion,
strategy swap, risk/capital limit increases, kill-switch configuration,
live/canary-live fields, and Docker/network/scheduler/host security
configuration. These appear in the forbidden-field list and are rejected at any
nesting depth.

## 5. Risk limits

All limits come from accepted, versioned project sources — no values are
estimated:

- parameter ranges: `safe_parameters._PARAMETER_RANGES`,
- minimum apply cooldown: `7` days (`apply_actuator.COOLDOWN_DAYS`),
- pair universe: `orchestrator/config/riskguard-pair-universe.json` (tracked),
- the `production-risk-limits-spec.md` is a **Draft** for the future live
  transition and is deliberately **not** imported into this dry-run baseline.

RiskGuard may be **more conservative** than these limits (tighter bounds pass
validation), never more permissive (wider bounds fail with `limit_breach`).

## 6. Proposal and mandate contract

An apply requires a mandate with **all** of:

| Field | Meaning |
|---|---|
| `proposal_id` | Unique proposal identity |
| `bot_id` | Target bot (must be in scope) |
| `parameter` / `from_value` / `to_value` | Change, both values recorded |
| `allowlist_match` | Must be `true` |
| `evidence_refs` | Non-empty list of evidence references |
| `dry_run_mandate` | Must be exactly `DRY_RUN_ONLY` |
| `snapshot_id` | Must be present (rollback prerequisite) |
| `canary_target` | Must be `true` (canary-first) |
| `measurement_window` | `{opened_at_utc, closes_at_utc}` |
| `rollback_criterion` | Explicit rollback criterion |
| `expires_at_utc` | Mandate expiry (timezone-aware) |
| `revision` | Revision identity, used for replay protection |
| `state` | Must be `ACCEPTED` |

**Approval eligibility is not live approval.** A mandate never authorises live
trading; it authorises at most a canary-first dry-run apply under the policy
gates.

## 7. Decision states

`ACCEPTED` · `REJECTED` · `BLOCK_ENTRY` · `EXPIRED` · `INVALID`

An apply is admissible only with `ACTIVE` state, at least one matching
`ACCEPTED` mandate, and no relevant `BLOCK_ENTRY`. Mandates in `REJECTED`,
`BLOCK_ENTRY`, `EXPIRED` or `INVALID` never authorise an apply.

## 8. Atomic state management

Procedure (implemented in `initialize_baseline`):

1. build the baseline (no mandates, no live authority),
2. validate **before** write,
3. back up any existing file (never deleted; `0600` in `<state-dir>/backup/`),
4. atomic write: same-directory `tmp` file → `fsync` → `os.replace` → directory
   `fsync`; final file mode `0644`,
5. re-read and re-validate; any mismatch aborts without a partial state.

Unknown fields: the consumer adapter ignores them; the **strict validator**
rejects forbidden keys at any depth (see §4). Rotation/update always goes
through the initializer (backup + validated rewrite).

## 9. Tests

`self_improvement_v2/tests/test_riskguard_baseline_contract.py` covers:
valid conservative baseline, missing state, empty state, invalid JSON, unknown
schema version, unknown bot, rebel, `dry_run=false`, locked field, limit
breach, expired mandate, missing snapshot, missing measurement window, replay,
active `BLOCK_ENTRY`, kill-switch `HALT_NEW`, kill-switch `EMERGENCY`, and a
positive admissible dry-run case (initialize → derive PASS → mandate roundtrip).

## 10. Documentation

- **Status check:** `python -c` read of the state + `derive_riskguard_status`,
  or the SI-v2 cycle bundle `control_plane.riskguard` provenance (status,
  present, sha256, fail-closed reason) — see
  `docs/reports/agent0-dry-run-operational-2026-09-18.md`.
- **Initialization:** `python self_improvement_v2/scripts/riskguard_init_baseline.py`
  (see `--help`); re-initialization always backs up first.
- **Recovery:** restore the backed-up file or re-run the initializer; the
  consumer treats any absent/corrupt state as fail-closed, so an aborted
  initialization cannot silently unblock the apply path.
- **Rotation/update:** re-run the initializer with a new `--binding-commit`;
  the previous state is preserved in the backup directory.
- **Live boundary:** this contract is dry-run only. Live trading requires the
  separate externally signed live-authority process and is out of scope here.

### State example (no secrets)

```json
{
  "schema_version": 1,
  "contract_name": "riskguard_baseline_contract_v1",
  "contract_version": "1.0.0",
  "binding_commit": "<40-hex commit>",
  "mode": "ACTIVE",
  "operating_mode": "DRY_RUN_ONLY",
  "live_authority": false,
  "summary": {"status": "ACTIVE", "accepted": 3},
  "pairs": {"BTC/USDT": {"verdict": "ACCEPTED"}, "ETH/USDT": {"verdict": "ACCEPTED"}, "SOL/USDT": {"verdict": "ACCEPTED"}},
  "bot_scope": {"allowed": ["freqtrade-freqforge", "freqtrade-freqforge-canary", "freqtrade-regime-hybrid"]},
  "limits": {"min_apply_cooldown_days": 7},
  "mandates": []
}
```
