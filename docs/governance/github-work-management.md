# GitHub Work Management

## One task, one branch, one PR, one report

Every implementation issue must produce one bounded pull request and validation evidence.

## Label rules

Use at most one label from each namespace:

- `area:`
- `type:`
- `priority:`
- `status:`
- `safety:`

Use special labels only when applicable.

## Source of truth

- Technical contracts and safety decisions: repository documentation and canonical roadmap issues
- Delivery grouping: GitHub Milestones
- Operational workflow status: Trading Hub Control Plane Project
- Do not maintain conflicting status values in multiple places.

Issue #423 remains the canonical live/SI-v2 roadmap. No Project field, label, milestone, issue, or advisory-data result may replace its approval gates.

## Issue requirements

Every implementation issue includes Context, Goal, Scope, Non-goals, Dependencies, Safety boundary, Acceptance criteria, Validation, Stop conditions and Expected PR title.

## Safety

No Issue, Project field, label or milestone can grant authority to:

- enable live trading
- set `dry_run=false`
- deploy exchange credentials
- bypass RiskGuard
- create order execution
- mutate runtime without the established explicit human approval process

Root/runtime authority is not live-capital authority. Live-capital actions remain subject to the repository's externally signed, time-limited approval boundary.

## Data-provider policy

External providers are optional, read-only and evidence/context-only.
API keys are environment-gated, never committed, and never required for tests.
Paid APIs are not a mandatory dependency.

Provider adapters must fail safely when unavailable. Missing credentials must never block application startup, and automated tests must not require genuine external credentials or network access.
