# Rainbow Contracts

This directory holds local contract snapshots derived from upstream sources.

## Rainbow Signal Envelope Contract Snapshot

| Field | Value |
|-------|-------|
| File | `rainbow_signal_envelope.schema.json` |
| Upstream source | `GoLukeEnviro/ai4trade-bot` → `docs/integration/rainbow-signal-provider-contract.md` |
| Upstream merged baseline | `bbcaf25e9636cfacc9ae1c7c9cf4ea37aa013687` (R1 baseline) |
| Historical roadmap reference | `f6c42c6e7483af413dbf30fa91aa68917952c632` (legacy reference, contract identical) |
| Contract document blob | Git blob SHA: `1b49e515cb39084ea4517fb3ddf45a6376984fe7` (identical at both refs) |
| Upstream read-only endpoints | `GET /signals/latest` (raw `CryptoSignal`), `GET /signals/canonical/latest` (canonical envelope) |
| Upstream issue | #51 (contract) |
| Fixtures issue | #56 (sanitized fixture pack) |
| Validator issue | #79 (Rainbow Signal Envelope Validator) |
| Snapshot issue | #82 (this contract snapshot) |
| Schema version | 1 |

### What This Snapshot Covers

The JSON schema defines the **trading-hub Signal Envelope** format — the canonical cross-system signal container used by the Rainbow validator (#79), fixtures (#56), and all downstream Rainbow consumers.

This snapshot is reconciled against the merged upstream baseline `bbcaf25`. The contract document blob is identical at the historical reference `f6c42c6` and at the merged baseline `bbcaf25`, so no schema or validator change is required for R1.

### Excluded pending upstream work

- ai4trade-bot PR #66 (`Add isolated Rainbow AI4Trade delivery worker`) is **not merged** as of R1. Its `canonical_symbol` / `timeframe` delta in `core/signals/adapters.py` is pending upstream work and must not be copied into this repository before the upstream contract is finalized.
- trading-hub PR #488 (`Align Rainbow read-only client contract`) is **not merged** as of R1. It depends on the final PR #66 upstream contract and is therefore blocked.

### What This Snapshot Does NOT Cover

- The upstream `CanonicalSignalEnvelope` from ai4trade-bot (richer model with `Actionability`, `InvalidationRule`, `DataQuality`, etc.) beyond the fields mapped into the trading-hub envelope.
- The internal `CryptoSignal` model used within the Rainbow subsystem.
- Ingestion pipelines, webhook subscriptions, or delivery-worker activation.
- Live runtime behavior or service health.

### Update Procedure

When the upstream contract changes:

1. Read the updated `docs/integration/rainbow-signal-provider-contract.md` in ai4trade-bot at the intended merged baseline.
2. Verify the contract document blob matches the baseline recorded above; if it differs, classify every change before patching.
3. Update `rainbow_signal_envelope.schema.json` to reflect new fields, constraints, or required properties.
4. Bump `schema_version` if the change is breaking.
5. Update tests in `self_improvement_v2/tests/test_rainbow_contract_snapshot.py`.
6. Run `test_rainbow_contract_drift_guard.py` to check for drift between schema, fixtures, and validator.
7. Commit with message `docs(rainbow): update contract snapshot`.

### Related Files

| File | Purpose |
|------|---------|
| `rainbow_signal_envelope.schema.json` | Local JSON Schema snapshot |
| `self_improvement_v2/src/si_v2/rainbow/validator.py` | Validator consuming this contract |
| `self_improvement_v2/fixtures/rainbow-signals/` | Fixtures validated against this contract |
| `self_improvement_v2/tests/test_rainbow_contract_snapshot.py` | Contract snapshot tests |
| `self_improvement_v2/tests/test_rainbow_signal_validator.py` | Validator tests (40 fixtures) |
| `self_improvement_v2/tests/test_rainbow_contract_drift_guard.py` | Drift guard tests |
