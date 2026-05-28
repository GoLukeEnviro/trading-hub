# TAG1 Regime-Hybrid Last 5 Trades

Generated: 2026-05-26 UTC

## Last 24h summary

```
0|0|0|0|0
```

## Last 5 closed trades

```csv
pair,"ROUND(open_rate,6)","ROUND(close_rate,6)","ROUND(close_profit*100,3)","ROUND(close_profit_abs,4)",enter_tag,exit_reason,close_date
OP/USDT:USDT,0.1338,0.134,0.029,0.0294,trend_pullback_long,roi,"2026-05-22 15:31:02.006000"
NEAR/USDT:USDT,1.5957,1.5979,0.018,0.0176,trend_pullback_long,roi,"2026-05-20 04:41:17.006000"
ARB/USDT:USDT,0.1151,0.1156,0.308,0.3083,range_reversion_long,roi,"2026-05-18 00:45:06.927000"
SOL/USDT:USDT,89.518,89.638,0.004,0.004,range_reversion_long,roi,"2026-05-15 16:35:43.319000"
AVAX/USDT:USDT,9.912,9.615,-3.123,-3.097,trend_pullback_long,stop_loss,"2026-05-15 13:31:26.939000"
```

## Relevant runtime logs after RR fix restart

```
2026-05-26 21:59:59,946 - freqtrade.commands.trade_commands - INFO - worker found ... calling exit
2026-05-26 22:00:06,950 - freqtrade.resolvers.strategy_resolver - INFO - Override strategy 'minimal_roi' with value from the configuration: {'0': 0.015, '30': 0.01, '60': 0.005, '120': 0.002}.
2026-05-26 22:00:06,951 - freqtrade.resolvers.strategy_resolver - INFO - Override strategy 'stoploss' with value from the configuration: -0.04.
2026-05-26 22:00:06,951 - freqtrade.resolvers.strategy_resolver - INFO - Override strategy 'trailing_stop' with value from the configuration: True.
2026-05-26 22:00:06,952 - freqtrade.resolvers.strategy_resolver - INFO - Override strategy 'trailing_stop_positive' with value from the configuration: 0.01.
2026-05-26 22:00:06,952 - freqtrade.resolvers.strategy_resolver - INFO - Override strategy 'trailing_stop_positive_offset' with value from the configuration: 0.02.
2026-05-26 22:00:06,953 - freqtrade.resolvers.strategy_resolver - INFO - Override strategy 'trailing_only_offset_is_reached' with value from the configuration: True.
2026-05-26 22:00:06,955 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using minimal_roi: {'0': 0.015, '30': 0.01, '60': 0.005, '120': 0.002}
2026-05-26 22:00:06,955 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using timeframe: 15m
2026-05-26 22:00:06,956 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using stoploss: -0.04
2026-05-26 22:00:06,956 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using trailing_stop: True
2026-05-26 22:00:06,956 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using trailing_stop_positive: 0.01
2026-05-26 22:00:06,957 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using trailing_stop_positive_offset: 0.02
2026-05-26 22:00:06,957 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using trailing_only_offset_is_reached: True
2026-05-26 22:00:06,958 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using use_custom_stoploss: True
2026-05-26 22:00:06,958 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using process_only_new_candles: True
2026-05-26 22:00:06,959 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using order_types: {'entry': 'limit', 'exit': 'limit', 'stoploss': 'limit', 'stoploss_on_exchange': False, 
'stoploss_on_exchange_interval': 60}
2026-05-26 22:00:06,959 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using order_time_in_force: {'entry': 'GTC', 'exit': 'GTC'}
2026-05-26 22:00:06,960 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using stake_currency: USDT
2026-05-26 22:00:06,960 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using stake_amount: 50
2026-05-26 22:00:06,960 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using startup_candle_count: 500
2026-05-26 22:00:06,961 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using use_exit_signal: True
2026-05-26 22:00:06,961 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using exit_profit_only: False
2026-05-26 22:00:06,962 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using ignore_roi_if_entry_signal: False
2026-05-26 22:00:06,962 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using exit_profit_offset: 0.0
2026-05-26 22:00:06,963 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using disable_dataframe_checks: False
2026-05-26 22:00:06,963 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using i
```
