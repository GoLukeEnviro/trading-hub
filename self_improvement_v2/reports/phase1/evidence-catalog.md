# SI v2 — Offline Evidence Catalog

**Version:** 1.0
**Date:** 2026-06-15
**Schema Version:** EVIDENCE_SCHEMA_VERSION = 1

## Overview

This catalog defines the evidence categories, file paths, and schema references used by the SI v2 self-improvement loop. All items are offline-only — no service calls, no secrets, no trading changes.

## Evidence Categories

| Category | Type | Path | Format |
|----------|------|------|--------|
| Telemetry Snapshot | Derived | `self_improvement_v2/reports/phase2/evidence/multi_bot_cycle_*.json` | JSON |
| Shadow Proposal | Report | `self_improvement_v2/reports/phase2/multi_bot_read_analyze_shadow_proposal.md` | Markdown |
| Cycle Report | Report | `self_improvement_v2/reports/phase2/active_cycle_runner_report.md` | Markdown |
| Shadow Log | Derived | `self_improvement_v2/reports/phase2/shadow_logs/shadow_*.jsonl` | JSONL |
| Attribution Fixtures | Fixture | `self_improvement_v2/tests/fixtures/attribution/scenarios.json` | JSON |
| Attribution Sanity Report | Report | `self_improvement_v2/reports/phase1/attribution-sanity-report.md` | Markdown |
| Evidence Catalog (this file) | Index | `self_improvement_v2/reports/phase1/evidence-catalog.md` | Markdown |
| Attribution Models | Schema | `self_improvement_v2/src/si_v2/attribution/models.py` | Python |
| Attribution Engine | Source | `self_improvement_v2/src/si_v2/attribution/engine.py` | Python |
| Offline Aggregator | Source | `self_improvement_v2/src/si_v2/attribution/offline_aggregator.py` | Python |
| Proposal Candidate Schema | Schema | `self_improvement_v2/src/si_v2/proposal/schema.py` | Python |
| Proposal Fixtures | Fixture | `self_improvement_v2/tests/fixtures/proposal/candidates.json` | JSON |
| Regime Labels | Fixture | `self_improvement_v2/src/si_v2/analysis/regime_labels.py` | Python |
| Measurement Ledger | Derived | `self_improvement_v2/reports/phase2/measurement/ledger_*.json` | JSON |
| Rainbow Signal Envelopes | Source | `self_improvement_v2/src/si_v2/rainbow/client.py` | Python |

## Evidence Lifecycle

1. **Source**: Code modules that produce or process evidence (attribution engine, fleet analyzer, telemetry connector)
2. **Fixture**: Synthetic test data used during development and CI
3. **Derived**: Output produced by proof scripts or cycle runners during dry-run operation
4. **Report**: Human-readable summaries of derived evidence
5. **Index**: Catalogs and cross-references (this file)

## Schema Versioning

All evidence bundles include a `schema_version` field. Current version is `1`. Breaking changes increment the version number; the cycle runner checks `EVIDENCE_SCHEMA_VERSION` before processing bundles from previous versions.
