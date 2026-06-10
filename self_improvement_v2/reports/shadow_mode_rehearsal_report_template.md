# Shadow-mode Rehearsal Report

> **SI v2 — Shadow-mode / Controlled Dry-run Rehearsal Evaluation Report**
>
> **Template — Not an approval to trade live.**
> This template is for documenting the results of a controlled, read-only
> rehearsal. It must not be used to execute runtime actions or to authorise
> live trading.
>
> All sections below are **filled after** the rehearsal completes.
> No section should be pre-filled with assumptions about the outcome.

---

## 1. Run Metadata

| Field | Value |
|-------|-------|
| **Run ID** | `dr-<YYYYMMDD>-<HHMMSS>-<random8>` |
| **Run Name** | |
| **Date (UTC)** | |
| **Run By** | |
| **Approval Token** | |
| **Approval Scope** | |
| **Rehearsal Mode** | ☐ Shadow-mode / ☐ Controlled Dry-run |

---

## 2. Environment Snapshot

| Component | Version / Reference |
|-----------|---------------------|
| **Git Branch** | |
| **Git Commit** | |
| **Python Version** | |
| **SI v2 Version** | |
| **Host OS** | |
| **Docker Fleet State** | (containers running, health) |

---

## 3. Preflight Verification

| Check | Result | Evidence |
|-------|--------|----------|
| No-live-trading invariants | ☐ PASS / ☐ FAIL | |
| All offline tests pass | ☐ PASS / ☐ FAIL | |
| Dry-run evidence schema valid | ☐ PASS / ☐ FAIL | |
| Forbidden conditions checked | ☐ PASS / ☐ FAIL | |
| RiskGuard available | ☐ YES / ☐ NO | |
| ShadowLogger available | ☐ YES / ☐ NO | |
| All bots in `dry_run=true` | ☐ YES / ☐ NO | |
| No exchange credentials exposed | ☐ YES / ☐ NO | |

---

## 4. Commands Executed

| # | Category | Target Bot(s) | Command / API Call | Duration | Status |
|---|----------|--------------|-------------------|----------|--------|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |

---

## 5. Observations

### 5.1 Signal Validation

| Source | Signal Count | Valid | Invalid | Anomalies |
|--------|-------------|-------|---------|-----------|
| | | | | |

### 5.2 Bot Health

| Bot ID | Status | Last Trade | Open Trades | Dry-run Balance |
|--------|--------|-----------|-------------|-----------------|
| | | | | |

### 5.3 Config Comparison

| Config Key | Expected | Actual | Drift |
|-----------|----------|--------|-------|
| | | | |

---

## 6. Validation Outcome

| Metric | Value |
|--------|-------|
| **Overall Status** | ☐ PASSED / ☐ FAILED / ☐ DEGRADED |
| **Total Commands** | |
| **Failed Commands** | |
| **Warnings** | |
| **Anomalies Detected** | |
| **Safety Verdict** | ☐ Safe / ☐ Degraded / ☐ Blocked |

---

## 7. Artifacts Produced

| Type | Path | Checksum (SHA-256) |
|------|------|--------------------|
| Log | | |
| Report | | |
| Evidence | | |
| Manifest | | |

---

## 8. Residual Risks

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| R-01 | | | |

---

## 9. Approval for Next Phase

| Field | Value |
|-------|-------|
| **Next Phase** | |
| **Required Token** | |
| **Reviewer** | |
| **Review Timestamp (UTC)** | |

---

> **This is a template document.**
> It does not authorise any live trading, dry_run=false configuration,
> real adapter usage, or deployment action.
> All runtime actions require a separate, explicit human approval token.
