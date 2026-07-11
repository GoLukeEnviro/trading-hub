# Architecture Decision Records (ADRs)

Dieses Verzeichnis enthält alle Architekturentscheidungen für trading-hub.

## Index

| Datei | Datum | Thema | Status |
|---|---|---|---|
| [2026-05-14-soul-agents-sync.md](2026-05-14-soul-agents-sync.md) | 2026-05-14 | SOUL/AGENTS Sync | ACCEPTED |
| [ADR-2026-06-10-watchdog-ownership.md](ADR-2026-06-10-watchdog-ownership.md) | 2026-06-10 | Watchdog Ownership | ACCEPTED |
| [ADR-2026-06-27-controlled-self-improvement-human-gated-apply.md](ADR-2026-06-27-controlled-self-improvement-human-gated-apply.md) | 2026-06-27 | SI v2 Human-Gated Apply | ACCEPTED |
| [ADR-2026-06-27-si-v2-restart-with-overlay-runtime-proof.md](ADR-2026-06-27-si-v2-restart-with-overlay-runtime-proof.md) | 2026-06-27 | SI v2 Restart + Overlay Runtime Proof | ACCEPTED |
| [ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md](ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target.md) | 2026-07-01 | SI v2 Autonomous Dry-Run Loop | ACCEPTED |
| [ADR-2026-07-11-hermes-root-runtime-authority.md](ADR-2026-07-11-hermes-root-runtime-authority.md) | 2026-07-11 | Hermes Root Runtime Authority | ACCEPTED |
| [ADR-2026-07-11-hermes-r7a-dryrun-topology.md](ADR-2026-07-11-hermes-r7a-dryrun-topology.md) | 2026-07-11 | HermesTrader R7A Dry-Run-Topology | ACCEPTED |
| [APPROVED_EXECUTE_LIVE_CANARY.md](APPROVED_EXECUTE_LIVE_CANARY.md) | — | Approved: Live Canary Execute | APPROVED |
| [APPROVED_LIVE_CANARY_ROLLBACK.md](APPROVED_LIVE_CANARY_ROLLBACK.md) | — | Approved: Live Canary Rollback | APPROVED |
| [APPROVED_LIVE_CANARY_TRANSITION.md](APPROVED_LIVE_CANARY_TRANSITION.md) | — | Approved: Live Canary Transition | APPROVED |

## Konventionen

- Format: `ADR-YYYY-MM-DD-kurzbeschreibung.md`
- Status: `DRAFT` → `ACCEPTED` → (`SUPERSEDED` / `DEPRECATED`)
- Jedes ADR verweist auf zugehörige Issues
- Keine rückwirkenden Änderungen — bei Änderung neues ADR mit `SUPERSEDES: <altes ADR>`
