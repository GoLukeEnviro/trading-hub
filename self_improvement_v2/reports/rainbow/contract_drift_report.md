# Rainbow Contract Drift Report

> **Generated:** 2026-06-10  
> **Run by:** RainbowContractDriftGuard  
> **Schema:** `self_improvement_v2/contracts/rainbow_signal_envelope.schema.json`  
> **Fixtures:** `self_improvement_v2/fixtures/rainbow-signals/`  

---

## Verdict: GREEN — All checks passed

| Check | Result |
|-------|--------|
| Total fixtures | 7 |
| Passed | 7 |
| Expected malformed | 1 |
| Unexpected failures | 0 |
| Schema field drifts | 0 |
| Fixture drifts | 0 |

---

## Fixture Results

| Fixture | Expected | Actual | Notes |
|---------|----------|--------|-------|
| `valid_long_signal.json` | PASS | PASS | ✅ |
| `valid_short_signal.json` | PASS | PASS | ✅ |
| `no_signal.json` | WARN | WARN | ✅ Non-actionable |
| `heartbeat.json` | WARN | WARN | ✅ Non-actionable |
| `stale_signal.json` | WARN | WARN | ✅ Stale status |
| `partial_metadata_signal.json` | PASS | PASS | ✅ |
| `malformed_missing_required_fields.json` | FAIL | FAIL | ✅ Expected malformed |

---

## Schema vs Validator Comparison

| Field | Schema | Validator | Status |
|-------|--------|-----------|--------|
| `event_type` | required | required | ✅ Match |
| `schema_version` | required | required | ✅ Match |
| `source_system` | required | required | ✅ Match |
| `source_id` | required | required | ✅ Match |
| `strategy_id` | required | required | ✅ Match |
| `symbol` | required | required | ✅ Match |
| `timestamp_utc` | required | required | ✅ Match |
| `direction` | required | required | ✅ Match |
| `confidence` | required | required | ✅ Match |
| `metadata` | required | required | ✅ Match |
| `redaction_status` | required | required | ✅ Match |

---

*Report generated deterministically by `RainbowContractDriftGuard`.*  
*No network, Docker, Freqtrade, Telegram, or runtime calls were made.*
