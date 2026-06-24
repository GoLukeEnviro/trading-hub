# 2026-06-24 — Root Agent Instructions aligned to proven SI-v2 loop

## Status

Docs-only alignment for Issue #342.

## Operation level

L2 — repository documentation only.

## Evidence basis

- Post-PR341 proof report: `docs/reports/si-v2-active-cycle-proof-post-pr341-2026-06-24.md`
- Evidence bundle: `self_improvement_v2/reports/phase2/evidence/active_cycle_20260624T055059Z.json`
- Evidence SHA-256: `694641dea7025f49de82a378a6a4d0ce3ad8ecf5ab0214dc70af5eb4252a9aa0`
- Validated main commit: `f14b286a2d1cf501a1aff552d3449c5ceae4a10d`

## Alignment decision

Root agent instructions now treat the SI-v2 loop as the primary operational
focus and assume the proven active fleet contains exactly these four bot ids:

- `freqtrade-freqforge`
- `freqtrade-freqforge-canary`
- `freqtrade-regime-hybrid`
- `freqai-rebel`

## Scope guard

The alignment explicitly blocks drift into Docker, Guardian, Cron, generic
healthchecks, generic CI, and infrastructure cleanup unless such work directly
blocks the SI-v2 loop or Luke explicitly approves it.

## Safety confirmation

- No runtime changes.
- No Docker, Compose, Cron, Guardian, Freqtrade config, strategy, environment,
  proposal apply, approval token, or live-trading action.
- No runtime artifacts staged except the docs proof report, if selected for this
  docs-only PR.
- Mutation counters remain evidence-only and unchanged by this docs work.

## Follow-up

After this docs alignment, review PR #330 against the post-PR341 evidence shape
and decide whether it should be updated, superseded, or closed. Then run the P3
Scheduler Continuity Proof before any Controlled Apply discussion.
