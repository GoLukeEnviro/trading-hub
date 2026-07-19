<!--
GENERATED FROM config/governance/canonical-roadmap.yaml
DO NOT EDIT MANUALLY
-->

# Canonical Program Roadmap

Roadmap revision: 1  
Governance contract revision: 1

| Phase | Title | Status | Depends on | Exit gate | Issue(s) | Class |
|---|---|---|---|---|---|---|
| G0 | Canonical Program Governance | in_progress | — | governance_consistency_green | — | — |
| A | State and Tracker Reconciliation | pending | G0 | canonical_state_reconciled | — | — |
| B | SEC-1/SEC-3 Runtime Deployment | blocked | A | executor_security_runtime_green | #636 | A2 |
| C | Gate-0 Strategy Evidence | blocked | A | edge_decision_recorded | #604 | A1 |
| D | Runtime Safety Wiring | blocked | B, C | safety_entry_path_green | — | — |
| E | R5B/R6 Fleet Reconciliation | blocked | D | canonical_four_bot_fleet_green | — | — |
| F | R7 Dry-run Measurement | blocked | E | sufficient_measurement_evidence | #496 | — |
| G | Allocator and Execution Readiness | blocked | F | gate_3_green | #600, #601, #602 | — |
| H | Micro-live Canary | blocked | G | micro_live_canary_validated | #603 | — |
