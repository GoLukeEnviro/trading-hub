# Research Signal Tools

Research-only tooling for historical signal archiving and rolling walk-forward backtests.

Location:

```text
freqtrade/bots/regime-hybrid/config/research/signal_tools/
```

No active Freqtrade strategy/config is modified by these files. The archiver is not started automatically.

## Files

### `signal_archiver.py`

Polls a current signal state JSON file and appends only changed versions to JSONL.

Defaults inside the Freqtrade container:

```text
source:  /freqtrade/user_data/primo_signal_state.json
archive: /freqtrade/user_data/signals/historical_signals.jsonl
period:  30 seconds
```

Archive record shape:

```json
{
  "timestamp_utc": "2026-05-20T04:00:00+00:00",
  "source_hash": "...",
  "fresh": true,
  "stale": false,
  "age_minutes": 1.2,
  "pairs_count": 3,
  "pair_keys": ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
  "data": { "pairs": { } }
}
```

Manual one-shot test:

```bash
python3 /freqtrade/config/research/signal_tools/signal_archiver.py --once
```

Manual long-running start in `screen`:

```bash
screen -S signal-archiver
python3 /freqtrade/config/research/signal_tools/signal_archiver.py
# detach: Ctrl-A then D
```

Manual long-running start in `tmux`:

```bash
tmux new -s signal-archiver
python3 /freqtrade/config/research/signal_tools/signal_archiver.py
# detach: Ctrl-B then D
```

Useful options:

```bash
python3 signal_archiver.py --help
python3 signal_archiver.py --source /path/to/primo_signal_state.json --archive /path/to/historical_signals.jsonl
python3 signal_archiver.py --skip-stale
```

`--skip-stale` avoids writing `stale=true` records. Without it, stale records are still archived when they change. That is useful for diagnosing bridge outages.

## `signal_loader.py`

Provides `HistoricalSignalLoader` for strategy research.

Example use in a research strategy:

```python
import sys
sys.path.insert(0, "/freqtrade/config/research/signal_tools")
from signal_loader import HistoricalSignalLoader

class MyResearchStrategy(IStrategy):
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.signal_loader = HistoricalSignalLoader(
            "/freqtrade/user_data/signals/historical_signals.jsonl",
            strict=False,
        )

    def _historical_gate_allows(self, pair: str, candle_time, side: str) -> bool:
        signal = self.signal_loader.get_signal_at(pair, candle_time)
        action = str(signal.get("action", "")).lower()
        bias = str(signal.get("bias", "")).lower()
        confidence = float(signal.get("confidence", 0.0) or 0.0)

        if side == "long":
            return action in ("buy", "long") and bias == "bullish" and confidence >= 0.70
        if side == "short":
            return action in ("sell", "short") and bias == "bearish" and confidence >= 0.70
        return False
```

Important: `HistoricalSignalLoader` uses binary search and supports both futures pair keys (`BTC/USDT:USDT`) and normalized keys (`BTC/USDT`).

## `walk_forward_backtest.py`

Rolling walk-forward runner for Freqtrade research strategies.

Default windows:

```text
train = 30 days
test  = 7 days
step  = 7 days
```

It runs `freqtrade backtesting` per OOS test window and parses Freqtrade JSON reports from the result ZIP. It does not parse terminal output with regex.

Example for Regime-Hybrid research v3:

```bash
python3 /freqtrade/config/research/signal_tools/walk_forward_backtest.py \
  --strategy ResearchRegimeHybridSideAwareV3 \
  --config /freqtrade/config/research/config_regime_hybrid_sideaware_v3.json \
  --strategy-path /freqtrade/user_data/strategies \
  --timerange 20260301-20260517 \
  --timeframe 15m \
  --train-days 30 \
  --test-days 7 \
  --step-days 7 \
  --min-trades 5 \
  --enable-protections
```

Output:

- terminal table
- CSV under `/freqtrade/user_data/backtest_results/walk_forward/walk_forward_results_YYYYMMDD.csv`
- optional equity-index CSV via `--equity-csv /path/to/equity.csv`

Hyperopt support is intentionally conservative:

```bash
--hyperopt --hyperopt-epochs 50 --hyperopt-min-trades 20
```

When enabled, train-window hyperopt runs before each OOS window, but the script does not automatically apply parameters. That avoids silent shadow-JSON contamination. Parameter adoption must remain a separate audited step.

## Safety Notes

- Research-only tooling.
- No container restart.
- No live trading.
- No exchange credentials.
- No active strategy/config mutation.
- Archiver must be started manually if desired.
