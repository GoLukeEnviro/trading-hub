# Canonical Funding Data Contract v2 — Options Analysis and Decision Framework

**Date:** 2026-08-13
**Author:** Hermes (trading-hub-orchestrator)
**Issue:** #708 (A1; follow-up of #697 `next_action=DEFINE_NEW_DATA_CONTRACT` and #705)
**Execution class:** A1 (repository-only; no runtime, no data download, no live trading)

> **Human decision required.** Issue #708 requires Luke's signed decision on
> the funding-gap handling for the Gate-0 selection backtest. This report
> provides the read-only options analysis and a decision framework. **No
> option is selected and no contract value is frozen in this PR.** Luke's
> signed comment on #708 is the sole authority for the final selection.

## 1. Context

The Freqtrade-native dataset (#697, `/opt/data/gate0-freqtrade-native-r1/`,
12 files, 254,425 rows, RUN `issue697-20260803T155723Z`) has incomplete
funding data. Bitget/CCXT reproducibly cap funding history at ~90 days
(verified via REST V2/V3 probes and CCXT autopagination, #693/#696/#697;
oldest reachable point 2026-05-05).

The #705 contract (`docs/reports/canonical-funding-data-contract-2026-08-13.md`,
PR #706 `96f1865`) defines the coverage criterion
`[2024-12-01T00:00:00Z, 2026-06-30T00:00:00Z]` with no grace →
`FUNDING_STATUS=INCOMPLETE_CONFIRMED_NATIVE_LIMIT`, decision
`REJECT_INCOMPLETE_FUNDING` (Luke, #697 comment `5179705029`), Gate-0
disposition `EXTEND`.

#705 evaluated and **rejected** all fallback sources:

| Fallback | Verdict | Reason |
|---|---|---|
| Bitget WS history replay | VERWORFEN | real-time only, no public replay |
| External archives (Tardis.dev, CryptoHFTData) | VERWORFEN | `external_data_mix=PROHIBITED` (Luke #697 `5179705029`) |
| Synthetic funding / `funding_rate=0` | VERWORFEN | `synthetic_funding=PROHIBITED`, `funding_rate_zero=PROHIBITED` |
| REST + native mix | VERWORFEN | same ~90-day cap, violates `external_data_mix=PROHIBITED` |

**Consequence:** no policy-compliant source for longer funding history exists.
The selection backtest (#702) remains blocked until a new contract defines how
the coverage gap is handled in the cost model.

## 2. Options analysis (read-only)

### Option A — Documented gap, best-effort funding in cost model

Keep the required coverage window `[2024-12-01, 2026-06-30]` as the
**acceptance criterion for the dataset**, but define the **cost-model input**
as: use the available funding rates (native download, ~90 days) for the
period they cover, and for the uncovered period apply a documented
best-effort estimate derived from the available rates (e.g. per-pair median
funding rate, capped at a conservative bound).

- **Effect on coverage criterion:** unchanged (dataset criterion), new
  `FUNDING_COST_MODEL=ESTIMATED_GAP` contract value.
- **Effect on Gate-0 confidence:** the cost model is an estimate for
  ~80% of the window; selection outcomes carry a documented uncertainty
  margin. Confidence gates (OOS PF > 1.3, OOS DD < 25%) must be evaluated
  with a sensitivity band around the funding estimate.
- **Policy fit:** does NOT violate `synthetic_funding=PROHIBITED` **only if**
  the estimate is derived from real observed rates and explicitly labeled
  as an estimate, not as fetched data. **Requires Luke's explicit
  confirmation** that a derived estimate is not "synthetic funding" in the
  policy sense.
- **Risk:** Luke's #697 decision language (`synthetic_funding=PROHIBITED`,
  `funding_rate_zero=PROHIBITED`) may be read as prohibiting any
  non-observed rate. This option needs the narrowest possible decision.

### Option B — Window reduction to available funding coverage

Reduce the selection backtest window so that the required funding coverage
window falls entirely inside the available ~90-day funding history (i.e.
selection window ends ~2026-05-05 or later, warm-up start adjusted).

- **Effect on coverage criterion:** `FUNDING_COVERAGE_REQUIRED_FROM` /
  `FUNDING_COVERAGE_REQUIRED_TO` shrink to the available span.
- **Effect on Gate-0 confidence:** the selection window no longer matches
  the frozen manifest's calibration/WF windows (`[2025-01-01, 2026-01-01)`
  selection, WF1/WF2 2025-07-01→2025-12-31). The manifest (#604, V3_1) and
  the #702 issue pin these windows. **This option changes the frozen
  evaluation inputs** — it requires a manifest amendment and re-ratification.
- **Policy fit:** no synthetic data; fully observed rates only.
- **Risk:** changes the frozen contract; the selection window would cover
  only ~4 months of the original 13-month selection range, reducing regime
  coverage (min regimes ≥ 2 may still hold, but evidence is weaker).

### Option C — Keep `REJECT_INCOMPLETE_FUNDING` / `EXTEND` (no backtest)

Keep the #705 contract as-is. The selection backtest (#702) stays NOT
authorized. Gate-0 remains `EXTEND` until a policy-compliant funding source
with longer history becomes available (e.g. Bitget extends retention, or a
new exchange/API path is approved by Luke).

- **Effect on coverage criterion:** unchanged.
- **Effect on Gate-0 confidence:** no selection evidence is produced; the
  edge decision remains `PENDING`. The roadmap stalls at the funding gate.
- **Policy fit:** fully compliant; no new decision needed beyond confirming
  the status quo.
- **Risk:** no progress on Gate-0; the funding gap is a confirmed exchange
  limit with no known resolution date.

### Option D — Re-evaluate external data prohibition (policy change)

Propose to Luke a **narrow policy amendment** to allow a specific external
funding archive (e.g. Tardis.dev funding data for the 3 canonical pairs) as
the **funding-only** input, with the native dataset remaining the candle
source.

- **Effect on coverage criterion:** full `[2024-12-01, 2026-06-30]` coverage
  becomes achievable.
- **Effect on Gate-0 confidence:** full funding history; cost model uses
  observed rates only; strongest evidence quality.
- **Policy fit:** **violates the current** `external_data_mix=PROHIBITED`
  decision. Requires an explicit, time-limited, scope-specific Luke
  amendment to #697's decision — a policy change, not an implementation
  choice.
- **Risk:** highest governance friction; external data provenance, license,
  and hash-pinning must be added to the contract.

## 3. Decision framework (for Luke)

| Criterion | Option A | Option B | Option C | Option D |
|---|---|---|---|---|
| Full observed funding | ❌ (estimate for gap) | ✅ (reduced window) | ❌ (no backtest) | ✅ |
| Frozen manifest preserved | ✅ | ❌ (window change) | ✅ | ✅ |
| Policy compliance (current) | ⚠️ needs narrow confirmation | ✅ | ✅ | ❌ (needs amendment) |
| Gate-0 progress | ✅ (with uncertainty band) | ✅ (weaker evidence) | ❌ (stall) | ✅ (strongest) |
| Governance friction | low | medium | none | high |

**Recommended default (no new decision):** Option C — the status quo is
fully compliant and requires no new authorization. If Luke wants Gate-0
progress, **Option A** is the smallest compliant step, but it needs Luke's
explicit confirmation that a derived estimate is not `synthetic_funding`
under the #697 decision.

## 4. Contract values (proposal — NOT frozen)

If Luke selects an option, the following contract values would be recorded
in a follow-up A1 PR (this PR does not set them):

```text
FUNDING_CONTRACT_V2_OPTION=<A|B|C|D>
FUNDING_STATUS=<INCOMPLETE_CONFIRMED_NATIVE_LIMIT | COMPLETE_OBSERVED | COMPLETE_ESTIMATED>
FUNDING_COST_MODEL=<OBSERVED_ONLY | ESTIMATED_GAP | NOT_AUTHORIZED>
FUNDING_COVERAGE_REQUIRED_FROM=<unchanged | adjusted>
FUNDING_COVERAGE_REQUIRED_TO=<unchanged | adjusted>
SELECTION_BACKTEST_AUTHORIZED=<YES | NO>
```

## 5. Validation

| Check | Result |
|---|---|
| `git diff --check` | clean |
| Scope | docs only (report + state) |
| CI (Main Gate + Offline Smoke + governance-consistency) | per PR checks |

## 6. Safety status

```text
DATA_DOWNLOAD=NO            (A2, not authorized)
BACKTEST_EXECUTED=NO
HOLDOUT_INSPECTED=NO
SYNTHETIC_FUNDING=NO
FUNDING_RATE_ZERO=NO
EXTERNAL_DATA_MIX=NO
LIVE_TRADING=NO
RUNTIME_MUTATION=NO
```

## 7. Next steps

1. Merge this A1 options analysis (Standing Owner Authorization, ADR-2026-08-04).
2. **Luke signs the option decision on #708** (standalone comment, exact
   `FUNDING_CONTRACT_V2_OPTION=<...>` block).
3. A follow-up A1 PR records the selected contract values and adapts
   `validate_funding_coverage()` / `convert_funding_to_freqtrade_with_coverage()`
   if required.
4. Only then: A2 selection backtest (#702) and Gate-0 edge decision.
