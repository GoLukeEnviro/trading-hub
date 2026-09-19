# Agent0 — runtime-execution wiring for the dry-run apply chain (2026-09-19)

> Continuation of the 2026-09-18 AUTONOMOUS_DRY_RUN activation. Status:
> **`RUNTIME_EXECUTION_WIRED`** — the canary apply path is executable,
> rehearsal-gated, rollback-verified, and still has not applied a real
> (non-no-op) change because no canary candidate exists in the evidence.

---

## 1. Gates, issues, PRs, merge commits

| Step | Issue | PR | Merge | Result |
|---|---|---|---|---|
| P1 — runtime portability (R7A) | #757 | #758 | `1af7873` | host paths repo-relative, compose-derived names, overlay bind mount, explicit `ComposeContext`, portable state dir |
| P2a — proof-draft fix | #759 | #760 | `fe59125` | executor draft carries expected values; fail-closed without them |
| P2 — E2E rehearsal | #761 | runtime | — | `P2_REHEARSAL_PASS` (overlay recreate → GREEN proof → rollback → 4/4 checks) |
| P3 — wiring | #762 | #763 | `07a5265` | rehearsal-gated switch, automatic rollback, blocker on unverified rollback |
| P4 — evidence + state | this report | (this PR) | — | documentation and canonical state |

## 2. Runtime state

```text
REHEARSAL_EVIDENCE=/opt/data/logs/si-v2-apply-chain/rehearsal/rehearsal-20260919T081735Z.json
REHEARSAL_RESULT=P2_REHEARSAL_PASS
WIRING=activation.json runtime_execution.wired=true (rehearsal-gated)
EVALUATOR_STATUS=NO_QUALIFIED_PROPOSAL (no canary candidate in the evidence)
EXECUTED_RUNTIME=false (nothing to execute yet)
ROLLBACK_PATH=proven (P2: base compose recreate + overlay removal + cmdline check)
LIVE_TRADING=NO
```

## 3. P2 rehearsal (the load-bearing proof)

- No-op overlay (`max_open_trades: 3` = current value) written to the canary
  `user_data`; recreate through the merged executor path
  (`ComposeContext`, project `hermestrader-dryrun`, env-file, both files):
  **`EXECUTED_GREEN`** with `RuntimeEffectProof=GREEN` — overlay visible to
  the bot, `/proc/1/cmdline` carried the overlay, loaded values matched
  (`merged_fallback`).
- Rollback immediately: base compose recreate, overlay removed on host and
  in the container volume; **4/4 checks green** (config SHA unchanged,
  cmdline without overlay, overlay absent, trades unchanged 6/3).
- Fleet untouched apart from the canary recreate; both other trading bots
  and webserver/rainbow kept their restart counts at 0.

## 4. P3 wiring behaviour

- Switch off → prepare-only (unchanged from 2026-09-18).
- Switch on with PASS evidence → execution enabled; GREEN keeps the change
  and writes the T0 measurement record; any other outcome rolls back
  automatically and verifies; unverified rollback is a hard blocker event.
- First automatic-mode run with the switch on: cycle `20260919T082956Z`
  GREEN, apply chain `NO_QUALIFIED_PROPOSAL` (the only candidate targets
  `freqtrade-freqforge`; stage 1 is canary-only), `executed_runtime=false`.

## 5. Why no real apply happened

The candidate generator produces proposals for whichever bot underperforms
in the cycle evidence. On 2026-09-19 that was `freqtrade-freqforge`
(and earlier `freqtrade-regime-hybrid`), never the canary. The chain
therefore correctly applies nothing. This is a **property of the evidence**,
not a defect: the canary-only first stage is the safety boundary. When the
canary produces a qualified candidate, the wired path will apply it
autonomously (policy-gated, snapshot-backed, rollback-capable,
measurement-bound) and alert on the result.

## 6. Mutation counters / live trading

All cycle mutation counters remain 0; the only runtime effect ever produced
by this work was the P2 no-op rehearsal, which was rolled back and verified.
`dry_run=true` everywhere; no live orders; no exchange keys; no
`dry_run=false`.

## 7. One next step

**Await the first qualified canary candidate.** The generator must emit a
canary-targeted proposal from live cycle evidence (canary underperformance
vs. fleet). When it does, the wired path applies it automatically, the T0
measurement window opens, and the measurement decision engine (KEEP /
ROLLBACK / EXTEND / INVALID) closes the loop. Nothing else is pending.
