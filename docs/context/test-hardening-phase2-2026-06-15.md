# Phase 2 Test Hardening Context — 2026-06-15

- Created temp-path Shadowlock tests for writer, indexer, queries, and healthcheck behavior.
- Added static Docker Compose contract tests for the four Freqtrade bots.
- Added control-plane safety tests for JSON loading and reconcile rollback.
- Added deterministic regime detector tests and explicit malformed-input handling.
- Added Rainbow read_only freshness round-trip coverage in `self_improvement_v2`.
- Safe root test suite passes; focused coverage subset passes and emits `coverage.xml`.
- The full artifact-dependent `self_improvement_v2` suite still expects Rainbow files that are missing in this checkout.
