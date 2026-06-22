# SI v2 Phase 4 — Operational Monitoring & Self-Healing Readiness Plan

Date: 2026-06-22
Related work: #292

## Goal
Define a report-only monitoring and readiness plan for the SI v2 fleet so that heartbeats, telemetry freshness, error spikes, alert routing, and fail-closed self-healing recommendations can be evaluated without introducing runtime actions.

## Scope
This phase is planning and report generation only.

### Included checks
- Bot heartbeat
- Telemetry freshness
- Proposal generation failures
- Exit evidence gate status
- Profitability gate trend
- Error-rate spikes
- Alert-routing readiness

### Allowed outputs
- Read-only report artifact
- Markdown or JSON summary
- Recommendation labels such as:
  - `restart_collector_recommended`
  - `pause_promotion_recommended`
  - `mark_bot_blocked_recommended`

### Explicitly excluded
- No restarts
- No Docker changes
- No Compose changes
- No Cron changes
- No runtime mutation
- No config writes
- No strategy writes
- No live-trading activation
- No automated healing actions

## Safety posture
- Fail closed on missing or stale evidence.
- Prefer warnings and recommendations over actions.
- Preserve auditability and reversibility.
- Treat all outputs as advisory until explicitly approved for runtime use.

## Proposed deliverables
1. A read-only evaluator that ingests fleet telemetry and gate outputs.
2. A deterministic report artifact describing readiness signals and failure modes.
3. A recommendation matrix mapping conditions to non-executing follow-up suggestions.
4. Test coverage proving the evaluator remains report-only.

## Acceptance criteria
- Report-only evaluator exists.
- Heartbeat and freshness are measured from existing evidence sources.
- Alert-routing readiness is represented as a recommendation, not an action.
- No mutation counters are introduced.
- No side effects are performed during evaluation.
- Tests confirm fail-closed behavior.

## Next step
Draft the implementation plan and fixture strategy for the evaluator, then keep the work report-only until a separate approval gate exists.
