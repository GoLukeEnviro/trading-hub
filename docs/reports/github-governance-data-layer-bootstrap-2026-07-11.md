# GitHub Governance and Data Layer Bootstrap Report

**Date:** 2026-07-11  
**Repository:** `GoLukeEnviro/trading-hub`  
**Base:** `main` @ `8dbb89082bbff40a794ba1c8832a8030d11da3f2`  
**Branch:** `docs/github-governance-data-layer-v1`  
**Runtime mutation:** `NONE`

## 1. Inventory before changes

- Default branch: `main`
- Repository write/admin permission: available
- Open pull requests: 0
- Open issues found before bootstrap: 7 (`#423`, `#477`, `#478`, `#483`, `#489`, `#496`, `#504`)
- Data-layer duplicates: none found for market data, OHLCV, yfinance, pandas-datareader, Finnhub, Alpha Vantage, DuckDB, Parquet or EvidenceBundle
- Equivalent implementation template: not found
- Equivalent GitHub work-management documentation: not found
- Canonical live roadmap: #423
- D1/D2 status: blocked by the existing C4 `ROLLBACK_RECOMMENDED` decision and missing live-fleet approval marker

The connected GitHub interface did not expose repository-wide list/create/update operations for Milestones, Projects, Project fields/views/workflows, or label color/description metadata. Counts for pre-existing Milestones, Projects and labels therefore could not be independently enumerated through the available connector surface.

## 2. Created

### Repository files

- `.github/ISSUE_TEMPLATE/implementation-task.md`
- `docs/governance/github-work-management.md`
- `docs/reports/github-governance-data-layer-bootstrap-2026-07-11.md`

### Data-layer backlog

- #511 — `[Epic] Free-first Market Data Layer for Trading Hub`
- #512 — `[Data] Add MarketDataProvider interface with optional provider registry`
- #513 — `[Data] Add normalized OHLCV quote and macro schemas`
- #514 — `[Data] Add free-first sandbox providers: yfinance and pandas-datareader`
- #515 — `[Data] Add optional free-tier API providers behind env-gated adapters`
- #516 — `[Data] Add DataQualityGate Parquet/DuckDB cache and EvidenceBundle export for SI-v2`

The Epic links all five Phase-1 issues and states that #423 remains authoritative for live gates.

### Label names created or verified

Area:
- `area:data`
- `area:si-v2`
- `area:rainbow`
- `area:runtime`
- `area:risk`
- `area:ops`
- `area:docs`
- `area:devex`

Type:
- `type:feature`
- `type:enhancement`
- `type:bug`
- `type:security`
- `type:research`
- `type:docs`
- `type:chore`

Priority:
- `priority:p0`
- `priority:p1`
- `priority:p2`
- `priority:p3`

Status:
- `status:triage`
- `status:ready`
- `status:blocked`
- `status:backlog`

Safety:
- `safety:read-only`
- `safety:dry-run`
- `safety:approval-required`
- `safety:secrets`
- `safety:live-boundary`

Special:
- `free-first`
- `provider:external`
- `evidence`
- `agent:hermes`
- `decision-required`

Connector-created label metadata is currently the GitHub default (`#EDEDED`, no description). The requested custom colors/descriptions remain blocked because the available connector exposes issue-label assignment but not label metadata updates.

## 3. Updated existing issues

- #423: added `area:si-v2`, `priority:p1`, `status:blocked`, `safety:live-boundary`
- #504: added `area:runtime`, `priority:p1`, `status:ready`, `safety:dry-run`
- #489: added `area:rainbow`, `priority:p1`, `safety:read-only`
- #496: added `area:rainbow`, `priority:p2`, `status:blocked`, `safety:dry-run`
- #483: added `area:ops`, `status:triage`
- #478: added `area:ops`, `status:triage`
- #477: added `area:ops`, `status:triage`

Existing labels and issue bodies were retained. No existing issue was closed.

## 4. Skipped

- No duplicate Data Layer Epic or Phase-1 issue existed, so no duplicate was created.
- No existing issue was assigned to a new Milestone because the requested Milestones could not be created through the available connector.
- No speculative priority or safety classification was added to stale issues #477, #478 or #483.

## 5. Blocked

The following requested GitHub objects could not be created or configured through the available connector operations:

1. Milestones:
   - `M0 — Runtime Safety Recovery`
   - `M1 — Rainbow SI-v2 Measurement Readiness`
   - `M2 — Data Layer v1 — Free-first`
   - `M3 — Operational Resilience v1`
   - `M4 — Live Decision Readiness`
2. Project: `Trading Hub Control Plane`
3. Project fields, views and native workflows
4. Project auto-add, close-to-Done and 30-day archive workflows
5. Requested label colors and descriptions
6. Assignment of #511–#516 to Milestone M2

No unsafe GitHub Actions workaround, secret-bearing automation or hidden token path was introduced.

## 6. Validation

- All six new issues are open and linked through #511.
- All Phase-1 issues carry the requested namespaced labels and `agent:hermes`.
- The Epic carries one area/type/priority/status/safety label plus applicable special labels.
- Existing issue labels were added without replacing prior labels.
- Open PR inventory was empty before the documentation branch was created.
- Changes are documentation/governance only; no application code or runtime configuration was modified.

## 7. Safety confirmation

- No live-trading change.
- No `dry_run=false`.
- No Runtime, Docker, Compose, Cron, Scheduler or host mutation.
- No secrets generated, requested, stored or committed.
- No paid data API made mandatory.
- No existing issue closed or body overwritten.
- No order, broker or execution authority introduced.
