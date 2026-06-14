# SI v2: Rainbow read_only Signal Provider Client v1

Date: 2026-06-14
Status: GREEN
Operation level: L2 (repo-only, read-only runtime path)

## Scope

Implement the SI v2 Rainbow client so it can consume Rainbow `CryptoSignal` payloads via a strictly read-only HTTP GET path, map them to the §5 envelope, validate them with the existing validator, and fail closed on malformed or unavailable upstream data.

No apply path, no trading, no Docker mutation, no Telegram work, no secrets.

## Files changed

- `self_improvement_v2/src/si_v2/rainbow/client.py`
- `self_improvement_v2/tests/test_rainbow_read_only_client.py`

## What changed

### Client

Added `read_only` mode to `RainbowSignalProviderClient`:

- new config fields:
  - `base_url`
  - `endpoint_path`
  - `timeout_seconds`
  - `source_type` (v1 supports `http` only)
- HTTP GET only via stdlib `urllib.request`
- no auth headers, no tokens, no secret usage
- explicit fail-closed behavior for:
  - missing `base_url`
  - unsupported `source_type`
  - HTTP/network failures
  - invalid JSON payloads
  - malformed / incomplete upstream signal rows
  - validator failures
- maps upstream Rainbow `CryptoSignal` rows into the SI v2 §5 envelope
- validates every mapped envelope through `RainbowSignalEnvelopeValidator`
- preserves safety metadata under `metadata.actionability`:
  - `can_execute: false`
  - `dry_run_only: true`

### Tests

Added read-only coverage for:

- missing `base_url` fail-closed
- successful GET + map + validate for 3 signals
- malformed upstream payload partial rejection
- stale signal warning path without crash
- HTTP 503 fail-closed
- timeout / network error fail-closed
- GET-only / no authorization header proof
- `max_records` limit behavior

## Validation evidence

### Focused tests

Passed:

- `tests/test_rainbow_read_only_client.py`
- `tests/test_rainbow_signal_validator.py`

### Wider regression set

Passed:

- `tests/test_telemetry_normalizer.py`
- `tests/test_active_cycle_runner.py`
- `tests/test_runner_ledger_integration.py`
- `tests/test_multi_bot_fleet_analyzer.py`
- `tests/test_signal_models.py`
- `tests/test_freqtrade_signal_fusion.py`
- `tests/test_measurement_models.py`
- `tests/test_measurement_ledger.py`
- `tests/test_attribution_report.py`
- `tests/test_rainbow_read_only_client.py`
- `tests/test_rainbow_signal_validator.py`

Note: `tests/test_multi_bot_proof_safety.py` was requested in the acceptance checklist but does not exist in the current repo state of this branch base. This is repo drift, not a client failure.

### Guardrails

Passed:

- `pytest -q -k 'forbidden_patterns or no_forbidden_patterns'`

### Ruff

Passed via `uvx ruff check --no-cache ...`

### No-Any verification

Search result over the touched Rainbow source/test files:

- explicit `Any`: 0 matches
- `dict[str, Any]`: 0 matches
- `list[Any]`: 0 matches
- `: Any`: 0 matches

### Runtime proof

A temporary local read-only HTTP endpoint (`/signals/latest`) was started and populated from the proven Rainbow `signals.db` rows in `/opt/data/ai4trade-bot/rainbow/storage/signals.db`.

Observed result:

- rows served: 3
- client source: `read_only`
- signals fetched: 3
- errors: 0
- validated symbols: `SOL/USDT`, `ETH/USDT`, `BTC/USDT`
- validated directions: all `long`
- safety metadata on every signal:
  - `can_execute: false`
  - `dry_run_only: true`

## Safety statement

Confirmed:

- no trading execution path added
- no apply path added
- no Docker changes
- no cron mutation
- no Telegram work
- no secrets used or logged
- client remains read-only and fail-closed

## Next recommended task

Use this client in the SI v2 scheduled observation cycle behind a read-only source configuration, then prove ledger ingestion of validated Rainbow envelopes end-to-end without introducing any apply capability.
