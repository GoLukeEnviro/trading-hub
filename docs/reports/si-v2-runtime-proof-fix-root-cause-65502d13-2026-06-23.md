# SI-v2 Runtime Proof Fix — Root Cause Analysis (Candidate 65502d13)

**Date:** 2026-06-23
**Reference activation run:** `/opt/data/reports/si-v2-runtime-activation-65502d13-20260623T163750Z/`
**PR scope:** fix `verify_runtime_effect` to prove multi-config effective state, not the base config.

---

## Summary

The runtime activation of candidate `65502d13` on FreqForge was technically
successful — Freqtrade's strategy resolver logged `max_open_trades: 3` and
`stake per trade: unlimited USDT` at startup, and the running container's
`/api/v1/show_config` (with auth) returns the overlay values. However, the
SI-v2 controlled-apply verifier returned `proof_status: RED` and therefore
correctly blocked the mutation counter increment and measurement start.

The cause is a structural verifier bug, not a runtime problem.

---

## What happened at runtime

1. **Overlay file placed at the correct path:**
   `/home/hermes/projects/trading/freqforge/user_data/overlay_65502d13.json`
   (SHA-256 `f8e32f97a4d8c26cc18b844065522c10c9a53316c4f4d66612968c4f67db4e36`).
2. **`docker-compose.yml` patched** to add a second `--config` argument to the
   FreqForge service command:
   `trade --config /freqtrade/user_data/config.json --config /freqtrade/user_data/overlay_65502d13.json --strategy FreqForge_Override`
3. **FreqForge container recreated** with the new command (targeted only
   FreqForge; other bots untouched).
4. **Freqtrade startup logs** confirm the overlay was loaded:
   - `freqtrade.resolvers.strategy_resolver - INFO - Strategy using max_open_trades: 3`
   - `freqtrade.rpc.rpc_manager - INFO - Sending rpc message: ... *Stake per trade:* unlimited USDT ...`
   - `Dry run is enabled. All trades are simulated.`
   - `Bot heartbeat. PID=1, version='2026.3', state='RUNNING'`
5. **`/api/v1/show_config` (auth)** returns the overlay values:
   `{"dry_run": true, "max_open_trades": 3.0, "stake_amount": "unlimited", "strategy": "FreqForge_Override", ...}`.

The runtime IS loaded. The hard safety gates are intact. **No live trading,
no `dry_run=false`, no strategy change.**

---

## Why `RuntimeEffectProof` returned RED

The verifier at
`self_improvement_v2/src/si_v2/apply_actuator/proof.py:191–202` (pre-fix)
called:

```python
loaded_ok, mismatches = check_effective_config_loaded(
    binding.container_name,
    binding.container_config_path,  # = /freqtrade/user_data/config.json (BASE config)
    proposal.parameters,            # = {max_open_trades: 3, stake_amount: "unlimited", tradable_balance_ratio: 0.99}
)
```

`check_effective_config_loaded` (pre-fix) does a `docker exec cat
container_config_path` and compares the JSON it reads (the **base config**)
against the **overlay parameters**. Result:

```
max_open_trades: expected=3, got=5
stake_amount: expected='unlimited', got=50
tradable_balance_ratio: expected=0.99, got=0.95
```

All three "mismatches" are the same value pair read twice — once from the
base file (which legitimately still has 5/50/0.95) and once from the overlay
parameters (3/unlimited/0.99). The verifier never looked at the effective
config that the running process actually loaded.

`verify_runtime_effect` then classified this as `proof_status: RED`, the
mutation-counter rule blocked the increment, and the measurement rule blocked
the measurement start. **The hard safety gates worked correctly.** They
refused to validate an unverifiable activation.

The bug is purely in the *verifier*, not in the runtime state, not in the
strategy, not in the docker compose wiring.

---

## Why this is a verifier code gap, not a runtime failure

- The container has the overlay file in the right path (Proof: file visibility check passed).
- The Freqtrade process was started with the overlay file as a `--config` argument
  (Proof: `pid=1 cmdline=/usr/local/bin/python3.13 ... freqtrade trade --config /freqtrade/user_data/config.json --config /freqtrade/user_data/overlay_65502d13.json --strategy FreqForge_Override`).
- The Freqtrade process has the overlay values in its in-memory config
  (Proof: startup logs from `strategy_resolver` and `rpc_manager`).
- The `show_config` REST endpoint returns the overlay values
  (Proof: HTTP 200 response with `max_open_trades: 3.0`, `stake_amount: "unlimited"`).

All three independent evidence channels agree: the runtime is loaded. The
verifier's third check (read the base config file and compare to overlay
parameters) is the only one that disagrees — because the base config file
correctly still has the pre-overlay values, and the verifier was checking
the wrong file for the effective state.

---

## The fix

Multi-config proof strategy: C + (A or B).

### Proof C — Process command proof (auth-free)

Read the Freqtrade process command line from `/proc/1/cmdline` inside the
container and verify it contains `--config <overlay_container_path>`. This
proves the bot was *started* with the overlay. It is necessary but not
sufficient — the file could still be missing or unreadable.

### Proof A — Authoritative effective config proof (with auth)

Call the bot's `/api/v1/show_config` endpoint with HTTP basic auth
(username/password resolved from the base config's `api_server` block).
The response reflects the in-memory config that Freqtrade is actually
using. This is the strongest proof available.

### Proof B — Deterministic merged-config fallback (no auth)

If Proof A is unavailable (api_server disabled, REST not reachable, auth
missing), read the base config and the overlay from inside the container,
merge them in Python with last-wins-per-key semantics (the same precedence
Freqtrade uses for `--config config.json --config overlay_*.json`), and
compare against `proposal.parameters`. This proves the *effective* config
that the running process would produce if it picked up both files.

### GREEN rule

All of the following must be true:

- `file_visible_to_bot = True`
- `process_command_uses_overlay = True`  ← NEW (Proof C)
- `effective_config_contains_expected_values = True`  (from the draft)
- `loaded_config_contains_expected_values = True`  ← NOW from A or B
- `dry_run_true = True`
- `live_trading_false = True`
- `strategy_unchanged = True`

**C alone is not enough** (process could reference a missing file). **A or B
alone is not enough** (the values could be coming from the base file without
the overlay being loaded). **C + (A or B) together is robust.**

### Fail-closed

- overlay visible but not in process command → RED (`process_command_missing_overlay`)
- effective values mismatch (any source) → RED (`effective_merged_config_mismatch` / `api_effective_config_mismatch`)
- A and B both unavailable → RED (`api_proof_unavailable` + `effective_merged_config_mismatch`)
- `dry_run: false` in merged config → RED
- strategy changed → RED
- file not visible → RED (`file_visibility_failure`)

The new `RuntimeEffectProof.errors` are tagged with a stable prefix
(`process_command_missing_overlay`, `effective_merged_config_mismatch`,
`api_effective_config_mismatch`, `api_proof_unavailable`,
`file_visibility_failure`, `draft_mismatch`, `draft_missing_key`) so future
operators can diagnose failures by reading the error strings.

---

## Why the hard safety gates still did the right thing

The original `verify_runtime_effect` returning RED did **exactly** what the
mutation-counter rule and measurement rule are designed to do: refuse to
increment and refuse to start measurement unless the proof is GREEN. The
fact that the proof was RED for a *verifier bug* rather than a *runtime
problem* is irrelevant to the safety property: the system is fail-closed,
so any non-GREEN result blocks downstream effects.

This is the correct behavior. We do not bypass the gate. We fix the verifier
so that the gate produces the right answer for the right reason.

---

## Scope of this fix

**In scope:**
- `self_improvement_v2/src/si_v2/apply_actuator/proof.py` — replace single-file
  proof with multi-config proof strategy (C + A + B).
- `self_improvement_v2/src/si_v2/apply_actuator/models.py` — add
  `process_command_uses_overlay` and `proof_method` fields to
  `RuntimeEffectProof` for diagnostics.
- `self_improvement_v2/src/si_v2/apply_actuator/runtime_binding.py` —
  docstring/comment that `loaded_config_args` reflects the base process
  args; the proof layer dynamically derives the expected overlay path from
  the proposal_id rather than hardcoding it into the static binding.
- `self_improvement_v2/tests/test_apply_actuator_runtime_proof_multiconfig.py`
  — new offline test file for the multi-config proof path.
- `docker-compose.yml` — keep the existing 1-line FreqForge activation
  command (already applied; commit it in this PR as the canonical runtime
  activation state for candidate 65502d13).
- `docs/reports/si-v2-runtime-activation-65502d13-2026-06-23.md` — keep
  the activation report in the PR.
- `docs/reports/si-v2-runtime-proof-fix-root-cause-65502d13-2026-06-23.md`
  — this file.

**Out of scope (deferred):**
- Global `/opt/hermes-green/.env` Compose blocker (causes `docker compose
  up -d` to abort with `env file not found`). Documented as operational
  friction; not fixed in this PR.
- Removal of the inert wrong-path overlay at
  `freqtrade/bots/freqforge/user_data/overlay_65502d13.json` (the
  previous PR #331 apply artifact). Tracked for cleanup in this PR.
- AI4Trade / Rainbow runtime changes. Neither is the cause of the verifier
  bug. (See Phase 9 read-only check.)
- Hardcoding the activated overlay path into the static
  `BotRuntimeBinding.loaded_config_args`. The new proof path derives the
  expected overlay path from `proposal.proposal_id` at verification time.

**No live trading, no `dry_run=false`, no strategy change, no other bot
touched, no mutation counter increment, no measurement start.**

---

## Re-run after merge

After this PR is merged, re-running the same L3 runtime activation with the
existing overlay file and the same tokens should return:

```
mode=ACTUATOR_VERIFIED
status=APPLIED_WITH_RUNTIME_PROOF
proof.proof_status=GREEN
proof.process_command_uses_overlay=True
proof.proof_method=api (or "merged_fallback" if REST auth fails)
proof.loaded_config_contains_expected_values=True
mutation_counter_should_increment=True
measurement_allowed=True
```

Only then should Measurement #1 be planned for the next scheduled SI-v2 cycle.
