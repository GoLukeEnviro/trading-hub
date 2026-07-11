# Bot Registry — Compose Contract

> **Single source of truth** for the active Freqtrade Fleet service set.

## Rule

`docs/registry/bot-registry.md` defines the canonical set of compose
service names that constitute the active Fleet. Tests under
`tests/test_docker_compose_contracts.py` parse this registry at test time
and assert the named services exist in the compose manifests.

## Composition files in scope

- `docker-compose.yml` (main)
- `freqtrade/docker-compose.fleet.yml`

## Conflict resolution

- **Service in registry, missing from a compose file:** the test reports
  the missing service for that file. The registry is SoT; missing
  compose definitions are drift that must be fixed.
- **Service in a compose file, missing from the registry:** the test
  does not fail. Compose may legitimately include additional services
  (webservers, dashboards, sidecars) that are not strictly "the Fleet".
  Such services are surfaced by the test output but are not violations.
- **Service in both:** green. This is the happy path.
- **Service in registry + compose, but a contract property fails** (e.g.
  `user: 10000:10000` or read-only config mount): the test reports
  `XFAIL` with a reason string. XFAILs are tracked in
  `_R7A_DEFERRED_DRIFT` inside `tests/test_docker_compose_contracts.py`.
  Each entry MUST include the violated property and is to be resolved
  in the R7A architecture-decision PR (Compose path migration + fleet
  reconciliation). The rule is "no silent xfails" — every XFAIL is
  enumerated, explained, and tracked.

## Known R7A-deferred drift (enumerated, tracked, not silent)

| Service | Property | Tracking |
|---|---|---|
| `freqtrade-freqforge` | `user:10000:10000` | R7A architecture PR |
| `freqtrade-freqforge-canary` | `user:10000:10000` | R7A architecture PR |
| `freqtrade-regime-hybrid` | `user:10000:10000` | R7A architecture PR |
| `freqai-rebel` | `user:10000:10000` | R7A architecture PR |
| `freqtrade-webserver` | `user:10000:10000`, `config:ro-mount` | R7A architecture PR |

These were silently green in the previous test (which hardcoded a
smaller service list) and are now explicitly tracked.

## History

- **2026-07-11** — created as part of the R7A clarification PR
  ([Issue #504](../../issues/504)). Aligns the contract test with
  the AGENTS.md rule "Docker/Compose wins on naming" while preserving
  the registry as the canonical Fleet-membership list. Resolves
  **Konflikt #1** from
  `reports/r7-runtime-topology-reconciliation-2026-07-11.md` at the
  test-contract level only.
- The remaining 7 R7A conflicts (Compose paths pointing at
  `/home/hermes/...`, missing Rebel strategy, Rainbow service not
  defined in any compose, branch drift, state paths, current-state
  documentation staleness, missing artifacts) require an explicit R7A
  architecture decision (Option A/B/C) and are **out of scope** for the
  test contract.
