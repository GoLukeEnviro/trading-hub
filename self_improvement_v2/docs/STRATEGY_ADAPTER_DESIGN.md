# Strategy Adapter Design — SI v2 Phase H

> **Design Review — NO code implementation in this phase.**
> This document defines *how* strategy parameter mutations (specifically
> `rsi_period` and `cooldown_candles`) may be applied to live Freqtrade
> strategies, without implementing any real mutation code.

---

## 1. Scope

This document covers the mutation and application of two key strategy
parameters that Freqtrade's live trading system must consume:

| Parameter | Current Range | Typical Default | Impact |
|-----------|---------------|-----------------|--------|
| `rsi_period` | 2–50 | 14 | Controls RSI lookback window |
| `cooldown_candles` | 0–100 | 5 | Minimum candles between trades |

These two parameters are part of the 6-parameter `SafeParameters` set
defined in `state/schemas.py`, but they are singled out here because they
are **embedded as Python literals in Freqtrade strategy files**, not read
from configuration at runtime.

---

## 2. Mutation Approaches

### 2.1 AST-Based Text Patching (Recommended)

**Approach:** Use Python's `ast` module to parse the strategy file, find
the assignment statements for `rsi_period` and `cooldown_candles`, modify
their value nodes, and unparse the result back to source text.

**Advantages:**
- Precise — only the target assignment is modified
- Syntactically safe — malformed output cannot be generated
- No runtime modification of running strategy objects
- Roundtrip preserves comments and formatting via `unparse` (Python 3.9+)

**Disadvantages:**
- Requires the strategy file to be parseable Python
- Cannot handle dynamically-computed values (e.g., `rsi_period = 10 + 4`)
- AST unparse may produce slightly different whitespace from original

**Pseudo-implementation sketch:**

```python
import ast
import astor  # or ast.unparse in Python 3.9+

def patch_strategy_param(source: str, param: str, new_value: int) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == param:
                    node.value = ast.Constant(value=new_value)
    return ast.unparse(tree)
```

### 2.2 Regex-Based Text Patching (Fallback)

**Approach:** Use regex to find and replace `rsi_period = <int>` /
`cooldown_candles = <int>` patterns in the strategy source file.

**Advantages:**
- Works on non-parseable files (e.g., partial snippets)
- Preserves original formatting exactly
- Simple to implement

**Disadvantages:**
- Fragile — can match inside strings or comments
- No syntactic validation of the file after replacement
- Cannot distinguish module-level assignments from local ones

**Recommended fallback only:** Use regex only if AST parsing fails, and
only after a compile check of the modified file.

### 2.3 Strategy File Wrapper (Not Recommended)

**Approach:** Wrap the strategy class to read parameters from a config
file or environment variable at runtime.

**Advantages:**
- No file patching at all
- Runtime-configurable

**Disadvantages:**
- Requires modifying the strategy class hierarchy
- Requires Freqtrade to reload the strategy (restart or hot-reload)
- More invasive change with higher blast radius

---

## 3. Safety Chain

Any strategy mutation must pass through a rigorous safety chain before
it can be applied to a live system.

```
┌─────────────┐
│  1. Backup  │  Copy original strategy file to timestamped backup
└──────┬──────┘
       ▼
┌─────────────┐
│  2. Diff    │  Show the exact text changes (before/after)
└──────┬──────┘
       ▼
┌─────────────┐
│  3. Compile │  Python compile() check — ensures syntactic validity
└──────┬──────┘
       ▼
┌─────────────┐
│  4. Unit    │  Run strategy-specific unit tests (if any)
│     Tests   │
└──────┬──────┘
       ▼
┌─────────────┐
│  5. Backtest│  Run backtest on historical data with new params
└──────┬──────┘
       ▼
┌─────────────┐
│  6. Walk-   │  Run walk-forward analysis for robustness
│    Forward  │
└──────┬──────┘
       ▼
┌─────────────┐
│  7. Approval│  Human-in-the-loop approval via SI v2 gate
└──────┬──────┘
       ▼
┌─────────────┐
│  8. Shadow  │  Apply in shadow mode for N trades before live
│    Mode     │
└─────────────┘
```

### 3.1 Step Details

#### 3.1.1 Backup
- Copy the original strategy file to `backups/<strategy_name>/<timestamp>/`
- Preserve the original filename and directory structure
- Backup must be verified via SHA-256 checksum

#### 3.1.2 Diff
- Generate a unified diff between the backup and the patched file
- Show to the human approver for visual inspection
- Must not exceed 10 lines changed per mutation

#### 3.1.3 Compile
- `compile(patched_source, '<strategy_name>.py', 'exec')` must succeed
- No syntax errors allowed

#### 3.1.4 Unit Tests
- Strategy-level unit tests must pass
- Minimum: test that the strategy class can be instantiated

#### 3.1.5 Backtest
- Standard SI v2 backtest pipeline with the new parameters
- Compare Sharpe ratio, drawdown, win rate against baseline
- Must not degrade Sharpe ratio by more than 0.1

#### 3.1.6 Walk-Forward
- Walk-forward analysis with `n_splits >= 3`
- Parameter stability across windows must exceed 0.7 (correlation)

#### 3.1.7 Approval
- Must go through `ApprovalGate` in `si_v2/approve/`
- Requires explicit human sign-off with `approved=True`
- Approval is per-parameter, per-bot, per-mutation

#### 3.1.8 Shadow Mode
- Apply the patched strategy in shadow mode
- Monitor for N trades or N days (whichever is longer)
- Compare shadow decisions against live decisions
- Only promote to live after shadow period passes

---

## 4. Implementation Phasing

| Phase | Scope | Status |
|-------|-------|--------|
| H | Design document only | ✅ This document |
| I | Strategy patching utility — pure functions, no I/O | ❌ Future |
| J | Backup and diff integration | ❌ Future |
| K | Backtest + walk-forward integration | ❌ Future |
| L | Approval gate wiring | ❌ Future |
| M | Shadow mode + promotion | ❌ Future |

---

## 5. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Syntax error in patched file | High | Compile check in safety chain |
| Wrong parameter modified | Medium | Exact AST targeting + diff review |
| Backup corruption | Medium | SHA-256 verification |
| Strategy file encoding issues | Low | UTF-8 enforced |
| Freqtrade reload failure | High | Shadow mode detects before promotion |

---

## 6. Open Questions

1. How does Freqtrade discover the updated strategy file? (Restart? SIGHUP?
   File watcher?)
2. Should we support per-bot strategy variants or a single shared file?
3. What is the rollback procedure if a patched strategy causes losses?
4. Should backtest results be cached per parameter combination?