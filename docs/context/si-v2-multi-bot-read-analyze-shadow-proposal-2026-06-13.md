# SI v2 — Multi-Bot Read/Analyze/Shadow-Proposal Cycle (2026-06-13)

## What was done

Advanced the SI v2 Self-Improvement Loop from the single-bot proof
(PR #207) to a **fleet-level** cycle. The loop now loads the readonly
Freqtrade bot registry, performs authenticated REST reads against **all
four enabled bots**, analyzes the per-bot evidence, and emits either a
metadata-only ShadowProposal or an explicit `NO_PROPOSAL` decision per
bot. Every ShadowProposal is passed through the existing shadow-only
safety path (RiskGuard-style local check + ShadowLogger + documented
`PENDING_HUMAN` state).

## Files added

- `self_improvement_v2/src/si_v2/loop/__init__.py`
- `self_improvement_v2/src/si_v2/loop/fleet_analyzer.py` — pure decision
  logic. Per-bot rules (A/B/C/D) and a deterministic fleet-level
  verdict (GREEN / YELLOW / RED). No I/O, no Freqtrade calls, safe to
  unit-test with synthetic evidence.
- `self_improvement_v2/src/si_v2/proofs/multi_bot_read_analyze_shadow_proposal.py`
  — proof script that wires the registry, the readonly REST connector,
  the fleet analyzer, the RiskGuard-style local check, and the
  ShadowLogger together. Writes an evidence bundle (JSON) and a fleet
  report (markdown).
- `self_improvement_v2/tests/test_multi_bot_fleet_analyzer.py` — 19
  unit tests covering all decision branches, fleet verdict, safety
  properties (no executable parameters, no live trading), and
  no-secret-leakage with `monkeypatch`.
- `self_improvement_v2/tests/test_multi_bot_proof_safety.py` — 6 unit
  tests for the proof script's RiskGuard-style local check.

## Files produced (cycle output)

- `self_improvement_v2/reports/phase2/multi_bot_read_analyze_shadow_proposal.md`
  — the fleet report.
- `self_improvement_v2/reports/phase2/evidence/multi_bot_cycle_20260613T111045Z.json`
  — the evidence bundle (per-bot redacted telemetry + per-bot
  decisions + safety results + fleet summary).
- `self_improvement_v2/reports/phase2/shadow_logs/shadow_*.jsonl` —
  one ShadowLogger entry per bot.

## Cycle result

- All 4 enabled bots processed.
- All 4 `/api/v1/ping` calls returned HTTP 200.
- All 4 `/api/v1/status` calls were attempted after JWT login was
  attempted. The required Freqtrade JWT env vars
  (`SI_V2_FREQTRADE_*_USERNAME` / `_PASSWORD`) are **not present in
  this session**, so JWT login fails closed per bot with
  `YELLOW_MISSING_ENV_VARS` and no secret value is ever read, printed,
  or persisted.
- Per-bot decision: **4 × `SHADOW_PROPOSAL`** with hypothesis
  `telemetry_reachability_baseline_established` (the loop documents a
  concrete, falsifiable observation: this bot is reachable via its
  Docker DNS name; the next cycle should authenticate to fetch full
  status).
- All 4 ShadowProposals pass the RiskGuard-style local check
  (`PASS_SHADOW_ONLY`) and are recorded by the ShadowLogger
  (`LOGGED`). Approval status is `PENDING_HUMAN`.
- Fleet verdict: **YELLOW** — loop logic executed end-to-end for all
  four bots, but JWT env vars are missing.

## Safety properties verified (all 0)

| Property                          | Value |
|-----------------------------------|-------|
| `runtime_mutations`               | `0`   |
| `config_mutations`                | `0`   |
| `live_trading_mutations`          | `0`   |
| `docker_mutations`                | `0`   |
| `network_mutations`               | `0`   |
| `healthcheck_mutations`           | `0`   |
| `ci_mutations`                    | `0`   |
| `strategy_mutations`              | `0`   |
| Freqtrade `GET` calls (data)      | `8`   |
| Freqtrade `POST` calls (auth)     | `0`   |
| Freqtrade `PUT` / `PATCH` / `DELETE` | `0` |
| `shadow_proposals_executed`       | `0`   |
| `secrets_in_repo`                 | `No`  |
| `secrets_printed`                 | `No`  |
| `tokens_persisted`                | `No`  |
| Controller state                  | `PAUSED / L3_REPOSITORY_ONLY` |

## How to promote YELLOW → GREEN

Set the following environment variables in the session that runs the
proof (the names are already in
`self_improvement_v2/config/freqtrade_bots.readonly.json`):

- `SI_V2_FREQTRADE_FREQFORGE_USERNAME` / `_PASSWORD`
- `SI_V2_FREQTRADE_REGIME_HYBRID_USERNAME` / `_PASSWORD`
- `SI_V2_FREQTRADE_FREQFORGE_CANARY_USERNAME` / `_PASSWORD`
- `SI_V2_FREQTRADE_FREQAI_REBEL_USERNAME` / `_PASSWORD`

Then re-run:

```bash
PYTHONPATH=src self_improvement_v2/.venv/bin/python \
    self_improvement_v2/src/si_v2/proofs/multi_bot_read_analyze_shadow_proposal.py
```

## Tests

- 25 new unit tests pass.
- The pre-existing
  `test_no_any_types.py` / `test_no_forbidden_patterns.py` /
  `test_live_trading_invariants.py` failures (against PR #207 files)
  are not caused by this change; they were already failing on
  `main` / `feat/si-v2-readonly-freqtrade-jwt-auth` before this cycle.
- New files pass `ruff check` cleanly.

## Non-Goals (not changed)

- No docker-compose.yml change.
- No network / port / healthcheck / CI change.
- No strategy / config / runtime mutation.
- No controller activation.
- No live-trading enablement.
- No `dry_run=False` anywhere.
- No env-var values read, printed, logged, or persisted.
