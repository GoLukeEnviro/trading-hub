# Rainbow Fixture Review Report

> **Generated:** Offline — deterministic output
> **Fixture directory:** `self_improvement_v2/fixtures/rainbow-signals`
> **Validator:** `RainbowSignalEnvelopeValidator` (#79)

---

## Summary

| Metric | Value |
|--------|-------|
| Total fixtures | 7 |
| Pass (PASS) | 3 |
| Warn (WARN) | 3 |
| Fail (FAIL) | 1 |
| Expected malformed | 1 |
| Unexpected failures | 0 |

---

## Fixture Detail

| File | Type | Verdict | Errors | Warnings | Notes |
|------|------|---------|--------|----------|-------|
| `heartbeat.json` | heartbeat | WARN | 0 | 1 | Health signal; Heartbeat event — not a trading signal |
| `malformed_missing_required_fields.json` | malformed | FAIL | 8 | 0 | Expected malformed |
| `no_signal.json` | no_signal | WARN | 0 | 1 | Non-actionable; No-signal event — not an actionable signal |
| `partial_metadata_signal.json` | partial_metadata | PASS | 0 | 0 | Degraded quality |
| `stale_signal.json` | stale | WARN | 0 | 2 | Past expiry threshold; Signal marked as 'stale' by data_quality (freshness=108000s); Signal is stale: 112771s old (threshold=3600s) |
| `valid_long_signal.json` | valid_signal | PASS | 0 | 0 | Valid signal |
| `valid_short_signal.json` | valid_signal | PASS | 0 | 0 | Valid signal |

---

*Report generated deterministically by `RainbowFixtureReviewReportGenerator`.*
*No network, Docker, Freqtrade, Telegram, or runtime calls were made.*
