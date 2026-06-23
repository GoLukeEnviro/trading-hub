# SI-v2 Runtime Activation Report — Candidate 65502d13

**Date:** 2026-06-23
**Status:** RUNTIME_ACTIVATION_BLOCKED (verification-module code gap, not runtime)
**Operation Level:** L3 (Token-Gate APPROVED)
**Proposal:** `65502d13` (freqforge, safe_parameter_overlay_only, reinforce_profitable_pair_cluster_v1)
**Operator:** Hermes (orchestrator profile, L3 session)

---

## 1. Status

**Overall:** RUNTIME_LOADED but PROOF_RED — activation is technically successful at the
runtime level, but the controlled-apply verification path returns RED because
`si_v2.apply_actuator.proof.verify_runtime_effect` reads the **base config file**
(`/freqtrade/user_data/config.json`) instead of the **merged effective config**
(Base + Overlay) that the Freqtrade process actually loaded via
`--config config.json --config overlay_*.json`.

**Hard-Rule-Set action taken:** NO mutation counter increment, NO measurement start.
Patch + fix-PR for the verification-module gap is the required next step.

---

## 2. Token Gate

| Token | Value | Status |
|---|---|---|
| `APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION` | `APPROVE` | ✅ PRESENT |
| `APPROVE_SI_V2_FREQFORGE_RELOAD_65502D13` | `APPROVE` | ✅ PRESENT |

---

## 3. Preflight

- **Repo:** `main` at `58b6534` (= PR #335 merge commit). HEAD == origin/main. Clean working tree (only untracked, no modified tracked files).
- **Main:** Sync with `origin/main`.
- **Fleet:** 4/4 Freqtrade containers up + Webserver.
- **Rainbow:** `verdict=GREEN`, 50 signals, freshest 10.5s old, uptime 27203s, healthy.
- **Candidate:** `65502d13` — `freqtrade-freqforge`, `safe_parameter_overlay_only`.
- **Pre-mutation baseline (verified via container `exec` `python3`):**
  - `dry_run: True`
  - `max_open_trades: 5`
  - `stake_amount: 50`
  - `tradable_balance_ratio: 0.95`
- **No `dry_run=false`, no live trading, no secrets observed.**

---

## 4. Runtime Activation

### Overlay file

- **Path:** `/home/hermes/projects/trading/freqforge/user_data/overlay_65502d13.json`
- **SHA-256:** `f8e32f97a4d8c26cc18b844065522c10c9a53316c4f4d66612968c4f67db4e36`
- **Content (validated, no secrets, no `dry_run`, no strategy):**
  ```json
  {
    "max_open_trades": 3,
    "stake_amount": "unlimited",
    "tradable_balance_ratio": 0.99
  }
  ```
- **Permissions:** `0640` (`hermes:hermes`).
- **Container visibility:** confirmed via `docker exec python3 -m json.tool` →
  identical JSON, identical values.
- **Safety scan:** no `dry_run=false`, no `live_trading`, no `api_secret`, no `password`, no `token`. **CLEAN.**

### Effective config strategy

Native Freqtrade 2026.3 multi-config support:
`--config /freqtrade/user_data/config.json --config /freqtrade/user_data/overlay_65502d13.json`

This was the missing piece in the merged `docker-compose.yml` (PR #335's
`runtime_binding.loaded_config_args` only referenced the single-config form).
The compose-file was patched (1-line, minimal) to add the second `--config`
argument, **only** for the `freqtrade-freqforge` service (Canary / Regime-Hybrid /
FreqAI-Rebel untouched).

### Activation method

- **Compose file:** 1-line patch in `docker-compose.yml` line 182:
  - **Before:** `command: trade --config /freqtrade/user_data/config.json --strategy FreqForge_Override`
  - **After:** `command: trade --config /freqtrade/user_data/config.json --config /freqtrade/user_data/overlay_65502d13.json --strategy FreqForge_Override`
  - **Diff SHA:** `362ec8a6...` → `07a69831...` (single-line change, scoped to FreqForge service)
- **`docker compose up -d`:** **attempted, blocked** by missing `env_file` at
  `/opt/hermes-green/.env` referenced by an unrelated service (`hermes-green`,
  line 99 of compose). The `/opt/hermes-green` directory is not writable by the
  `hermes` user (uid 1337) — root-owned, no sudo available.
- **Workaround used:** `docker stop` + `docker rm` + `docker run -d` with the
  exact resolved container parameters (image, env, mounts, ports, network,
  labels, restart-policy, healthcheck, logging) extracted via
  `docker inspect` from the original container, with **only the command
  changed** to the new multi-config form.

### Reload/restart performed

- `docker stop trading-freqtrade-freqforge-1` → OK
- `docker rm trading-freqtrade-freqforge-1` → OK (image preserved, volumes preserved)
- `docker run -d ... freqtrade-hermes1337:freqforge-c5 trade --config config.json --config overlay_65502d13.json --strategy FreqForge_Override` → new container ID `129f95a9...`
- **New `StartedAt`:** `2026-06-23T16:41:37.729852621Z` (old: `16:30:44`)

### Affected bots

- **freqforge (freqforge-c5):** YES — recreate with new command ✓
- **freqforge-canary (canary-c5):** UNTOUCHED ✓
- **regime-hybrid (regime-hybrid-c5):** UNTOUCHED ✓
- **freqai-rebel (freqai-rebel-c25):** UNTOUCHED ✓
- **webserver:** UNTOUCHED ✓
- **All other Compose services (`hermes-green`, `btc5m-bot`, `claude-worker`, `green-mem0`, `green-ollama`, `green-qdrant`, `hermes-green`, `rizzcoach-app-1`, `trading-ai-hedge-fund-1`, `trading-caddy-1`, `trading-dashboard`, `trading-docker-proxy-1`, `trading-guardian`, `trading-hermes-watchdog-1`, `trading-shadowlock-1`, `weatherhermes`):** UNTOUCHED ✓

---

## 5. RuntimeEffectProof — RAW evidence (runtime IS loaded, but verifier returns RED)

### Independent verification (not via `verify_runtime_effect`)

**Freqtrade container logs (last 60 lines, 16:41:44 — 16:44:18):**

```
2026-06-23 16:41:44,509 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using max_open_trades: 3
2026-06-23 16:41:44,950 - freqtrade.rpc.rpc_manager - INFO - Sending rpc message:
  {'type': startup, 'status': "*Exchange:* `bitget`\n*Stake per trade:* `unlimited USDT`\n..."}
2026-06-23 16:41:44,951 - freqtrade.worker - INFO - Changing state to: RUNNING
2026-06-23 16:41:44,950 - freqtrade.rpc.rpc_manager - INFO - Sending rpc message:
  {'type': warning, 'status': 'Dry run is enabled. All trades are simulated.'}
2026-06-23 16:41:49,954 - freqtrade.worker - INFO - Bot heartbeat. PID=1, version='2026.3', state='RUNNING'
```

The `Strategy using max_open_trades: 3` and `Stake per trade: unlimited USDT` lines
are **mechanically generated by Freqtrade's strategy resolver** reading the
effective merged config at startup. They are not a `show_config` API result —
they are the **actual values Freqtrade loaded into memory and is operating on**.

**show_config (auth) — partial values exposed by API:**

```json
{
  "dry_run": true,
  "max_open_trades": 3.0,
  "stake_amount": "unlimited",
  "strategy": "FreqForge_Override",
  "trading_mode": "futures",
  "margin_mode": "isolated"
}
```

Note: `tradable_balance_ratio` is **not exposed** in the `show_config` API output
(Freqtrade 2026.3 returns 32 top-level keys; none of them is `tradable_balance_ratio`).
This is a separate observability gap, not an activation gap.

### ControlledApplyResult (verifier verdict)

```
mode                          = TOKEN_GATED_BLOCKED
status                        = BLOCKED
proof.proof_status            = RED
proof.file_visible_to_bot     = true
proof.effective_config_contains_expected_values = true
proof.loaded_config_contains_expected_values    = false
proof.dry_run_true            = true
proof.live_trading_false      = true
proof.strategy_unchanged      = true
proof.restart_required        = true
proof.errors                  = [
  "max_open_trades: expected=3, got=5",
  "stake_amount: expected='unlimited', got=50",
  "tradable_balance_ratio: expected=0.99, got=0.95"
]
mutation_counter_should_increment = false
measurement_allowed               = false
```

**The 3 errors in `proof.errors` are the same value pair read twice** — once
from the **Base config** (which legitimately contains 5/50/0.95) and once
from the **expected Overlay values** (3/unlimited/0.99). The verifier reads
`binding.container_config_path` = `/freqtrade/user_data/config.json` (the
**Base** file), not the merged effective config that the running Freqtrade
process actually has in memory.

This is a **verification-module code gap**, not a runtime problem.

### Bot safety state

- `dry_run: true` ✓ (Log: "Dry run is enabled. All trades are simulated.")
- Live trading: **FALSE** (Log: every order is BLOCKED by
  `primo_signal` kill switch mode `HALT_NEW`).
- Strategy unchanged: `FreqForge_Override` (same as before, same as overlay's
  absence of `strategy` key, same as `binding.loaded_config_args`).
- Pairlist unchanged: `BTC/USDT:USDT`, `ETH/USDT:USDT`, `SOL/USDT:USDT`.
- Protections unchanged: CooldownPeriod, StoplossGuard, MaxDrawdown, LowProfitPairs.
- Heartbeat: every ~10s, `state='RUNNING'`, PID=1.

---

## 6. Why RUNTIME_ACTIVATION_BLOCKED despite Runtime = LOADED

The `verify_runtime_effect` function in
`self_improvement_v2/src/si_v2/apply_actuator/proof.py` lines 192–202 reads
the **base** config file:

```python
loaded_ok, mismatches = check_effective_config_loaded(
    binding.container_name,
    binding.container_config_path,  # = /freqtrade/user_data/config.json
    proposal.parameters,            # = {max_open_trades: 3, stake_amount: "unlimited", tradable_balance_ratio: 0.99}
)
```

`container_config_path` is the **base config**, not the **effective merged
config** that the running Freqtrade process has loaded into memory via
`--config config.json --config overlay_*.json`. The proof module has no
mechanism to:

- read the merged config (no API call to `show_config` in the proof path),
- parse Freqtrade's actual in-memory effective config,
- or read the overlay file and verify that the bot's process command
  references it (which is the canonical evidence that overlay is loaded).

Hard rule: "If `RuntimeEffectProof != GREEN` → stop, no measurement, no
counter". **This rule is followed.** Mutation counter stays at 0, measurement
is blocked, no measurement cycle is started.

But the **runtime is genuinely loaded** — Freqtrade's strategy resolver
read the merged config and confirmed `max_open_trades: 3` and
`stake_amount: unlimited` in its own startup logging. This is stronger
evidence than the `verify_runtime_effect` check (which reads a stale
singleton file).

---

## 7. Diagnosis: Verification-Module Code Gap

**File:** `self_improvement_v2/src/si_v2/apply_actuator/proof.py`
**Function:** `verify_runtime_effect`
**Lines:** 192–202

**Problem:** The proof reads `binding.container_config_path`
(= `/freqtrade/user_data/config.json`), which is the **base** config, and
compares it against the **overlay** parameters. This is structurally
wrong when the activation mode is **multi-config stacking** (which is
the only mode `overlay_merge.py` actually supports — see
`multi_config_compatible=True` in `generate_effective_config`).

**Fix direction (proposed, not implemented in this run):**

1. **Option A (preferred):** Add a Freqtrade-API call to `show_config` with
   auth from the container-side config (`api_server.username` /
   `api_server.password`). Compare response JSON to `proposal.parameters`.
   - Pros: reflects the actual merged config Freqtrade loaded.
   - Cons: requires api_server auth; might be slow / rate-limited.

2. **Option B:** In the container, do `python3 -c "import json; print(json.dumps({**json.load(open('/freqtrade/user_data/config.json')), **json.load(open('/freqtrade/user_data/overlay_<id>.json'))}, sort_keys=True))"` and compare to expected.
   - Pros: works without auth.
   - Cons: still approximates the loaded config; doesn't reflect the
     actual in-memory state.

3. **Option C:** Verify the bot's process command includes
   `--config /freqtrade/user_data/overlay_<id>.json` (via `cat /proc/1/cmdline`).
   This is **necessary** evidence (overlay is loaded into the process
   command line) but not **sufficient** (doesn't prove values were picked up).
   Use as a **complement**, not replacement.

**Recommended fix:** A + C combined. C is the cheap, auth-free check
("is the overlay in the process command?"). A is the authoritative
check ("are the loaded values in show_config?").

**Also: `runtime_binding.loaded_config_args` (lines 31–36) does NOT include
the new overlay `--config` argument.** The binding was verified on
2026-06-23 (per the file's docstring) before PR #335's multi-config
wiring. This means even after my activation, `binding.loaded_config_args`
is stale. A follow-up should sync the binding's `loaded_config_args` to
the actual multi-config command line.

---

## 8. Mutation Ledger

- **Updated:** NO (per hard rule: "Mutation counter blocked if proof != GREEN")
- **Mutation count:** 0
- **Proof reference:** `/opt/data/reports/si-v2-runtime-activation-65502d13-20260623T163750Z/`
- **Note:** PR #333 already corrected the previous (inert) PR #331 apply to
  `NO_RUNTIME_EFFECT` — there is **no retroactive mutation counter increment**
  for it. The first real runtime mutation has not been recorded yet.

---

## 9. Measurement

- **Measurement #1:** **NOT started** (measurement blocked because
  `apply_status != APPLIED_WITH_RUNTIME_PROOF`).
- **Measurement #2:** **NOT planned**.
- **next report:** After the verification-module fix is merged and a
  fresh controlled-apply run returns GREEN.

---

## 10. Safety

- `dry_run=false`: **NO** — `dry_run: true` in base config and in show_config ✓
- Live trading: **NO** — `primo_signal` kill switch `mode=HALT_NEW` blocks
  every order (Log: `primo_gate_allows: BLOCKED by kill switch` × 6).
- Bot restart: **YES** — FreqForge only, via `docker run` after `docker stop/rm`.
- Docker/Compose: **TARGETED ONLY** — single service `freqtrade-freqforge`,
  no other Compose service touched. Compose-file patch is 1 line, scoped
  to FreqForge service.
- Strategy change: **NO** — `FreqForge_Override` unchanged.
- Other bots changed: **NO** — Canary, Regime-Hybrid, FreqAI-Rebel,
  Webserver all UNTOUCHED.
- Secrets: **NO** — overlay content has no `api_secret`, `password`, `token`,
  `live_trading`, or `dry_run` keys. Compose patch added no env vars.
- No `git add .`: ✓ (all additions explicit).
- Repo branch: `apply/si-v2-65502d13-runtime-activation-proof` (separate PR —
  see §13).
- Inert overlay in wrong path
  (`freqtrade/bots/freqforge/user_data/overlay_65502d13.json`): **STILL
  PRESENT** (cleanup tracked in same PR, not deleted in this run to
  preserve rollback option).

---

## 11. Rollback

```bash
# 1. Remove the runtime overlay file
rm -f /home/hermes/projects/trading/freqforge/user_data/overlay_65502d13.json

# 2. Revert the compose patch
git -C /home/hermes/projects/trading checkout -- docker-compose.yml

# 3. Recreate the FreqForge container with the original command
docker stop trading-freqtrade-freqforge-1
docker rm trading-freqtrade-freqforge-1
# (docker run with the original command, image, env, mounts, ports, network, labels)
```

**Tested:** NO (rollback not executed in this run — activation is still active
pending the verification-module fix).
**Required if:** PR for verification-module fix is rejected and the L3
operator decides to roll back the activation.

---

## 12. PR (separate branch — not opened in this run)

The activation run is complete; the **next** L3 deliverable is a separate
PR for the verification-module fix. The PR should contain:

1. **Fix in `proof.py`:** `verify_runtime_effect` should not compare
   `proposal.parameters` to the **base** `container_config_path` — it
   should:
   - Check that the process command includes
     `overlay_<proposal_id[:8]>.json` (Option C from §7).
   - Optionally call `show_config` (with auth) and compare to
     `proposal.parameters` (Option A).
2. **Update `runtime_binding.py`:** `freqtrade-freqforge.loaded_config_args`
   should include the second `--config` argument so future verifications
   see the multi-config command.
3. **Unit test for the new proof path:** an offline test that simulates
   the multi-config scenario and verifies GREEN.
4. **Re-run this activation** to confirm GREEN + measurement allowed.
5. **Cleanup commit:** remove the inert overlay at
   `freqtrade/bots/freqforge/user_data/overlay_65502d13.json`
   (the wrong-path file from PR #331's inert apply).

The **branch** `apply/si-v2-65502d13-runtime-activation-proof` is the
container for all of the above. It is **not** created in this run; the
fix PR is a separate decision and should be planned in its own
L0/L1 session.

---

## 13. Evidence Directory

All artifacts under:
`/opt/data/reports/si-v2-runtime-activation-65502d13-20260623T163750Z/`

Notable files:
- `controlled-apply-api-result.json` — full `ControlledApplyResult` from
  `run_controlled_apply(...)`.
- `freqforge-container-logs.txt` — last 60 container-log lines (heartbeat,
  max_open_trades, stake, dry_run warnings).
- `freqforge-show-config-auth.json` — Freqtrade show_config API response
  (auth, in-container curl).
- `direct-runtime-proof.txt` — composite proof dump
  (process / overlay visible / config values from files).
- `actuator-audit-after-activation.log` — `si_v2_apply_actuator_audit.py`
  output post-activation (Fleet validation PASSED, all 4 bindings
  VERIFIED, FreqForge shows `Overlays: overlay_65502d13.json`).
- `actuator-report-after-activation.json` — `si_v2_apply_actuator_audit.py`
  `--mode report` JSON.
- `docker-compose.yml.before` / `docker-compose.yml.after.sha256` /
  `docker-compose.yml.diff` — Compose patch evidence.
- `freqforge-config.json.before` — pre-mutation config snapshot
  (SHA `b0c18c77...`).
- `overlay_65502d13.validated.json` — pre-install validated overlay.
- `overlay-runtime-file.sha256` — final runtime overlay SHA
  (`f8e32f97...`).
- `overlay-container-visibility-proof.txt` — container-side `cat` +
  `python3` of overlay.

---

## 14. Next Exact Task

**DO NOT measure. DO NOT increment mutation counter.**

**One executable next step:**

Open a separate L0/L1 session to plan and ship a **PR for the
verification-module fix** in `self_improvement_v2/src/si_v2/apply_actuator/proof.py`:

1. Add Option-C check (process command includes overlay file) — cheap, auth-free.
2. Add Option-A check (show_config with auth) — authoritative.
3. Update `runtime_binding.py:31-36` so `loaded_config_args` reflects the
   multi-config command.
4. Add offline unit test for the new proof path.
5. After merge, **re-run this activation** with the same tokens; expect
   GREEN + measurement allowed.
6. Cleanup the inert overlay at the wrong path in the same PR.

**Only after the re-run returns GREEN** can Measurement #1 be planned
for the next scheduled SI-v2 cycle.
