# Rainbow Contracts

This directory holds local contract snapshots derived from upstream sources.

## Rainbow Signal Envelope Contract Snapshot

| Field | Value |
|-------|-------|
| File | `rainbow_signal_envelope.schema.json` |
| Upstream source | `GoLukeEnviro/ai4trade-bot` → `docs/integration/rainbow-signal-provider-contract.md` |
| Upstream issue | #51 (contract) |
| Fixtures issue | #56 (sanitized fixture pack) |
| Validator issue | #79 (Rainbow Signal Envelope Validator) |
| Snapshot issue | #82 (this contract snapshot) |
| Schema version | 1 |

### What This Snapshot Covers

The JSON schema defines the **trading-hub Signal Envelope** format — the canonical cross-system signal container used by the Rainbow validator (#79), fixtures (#56), and all downstream Rainbow consumers.

For the raw `GET /signals/latest` producer surface, the client maps the upstream
`metadata.canonical_symbol` field to this schema's required `symbol` field. The
base `asset` (`BTC`, `ETH`, `SOL`) is not a cross-system trading symbol; an
unmapped asset must fail closed.

### What This Snapshot Does NOT Cover

- The upstream `CanonicalSignalEnvelope` from ai4trade-bot (richer model with `Actionability`, `InvalidationRule`, `DataQuality`, etc.)
- The internal `CryptoSignal` model used within the Rainbow subsystem
- API endpoints, ingestion pipelines, webhook subscriptions
- Live runtime behavior or service health

### Update Procedure

When the upstream contract changes:

1. Read the updated `docs/integration/rainbow-signal-provider-contract.md` in ai4trade-bot.
2. Update `rainbow_signal_envelope.schema.json` to reflect new fields, constraints, or required properties.
3. Bump `schema_version` if the change is breaking.
4. Update tests in `self_improvement_v2/tests/test_rainbow_contract_snapshot.py`.
5. Run `test_rainbow_contract_drift_guard.py` to check for drift between schema, fixtures, and validator.
6. Commit with message `docs(rainbow): update contract snapshot`.

### Related Files

| File | Purpose |
|------|---------|
| `rainbow_signal_envelope.schema.json` | Local JSON Schema snapshot |
| `self_improvement_v2/src/si_v2/rainbow/validator.py` | Validator consuming this contract |
| `self_improvement_v2/fixtures/rainbow-signals/` | Fixtures validated against this contract |
| `self_improvement_v2/tests/test_rainbow_contract_snapshot.py` | Contract snapshot tests |
| `self_improvement_v2/tests/test_rainbow_signal_validator.py` | Validator tests (40 fixtures) |
| `self_improvement_v2/tests/test_rainbow_contract_drift_guard.py` | Drift guard tests |
