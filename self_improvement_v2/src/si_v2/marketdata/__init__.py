"""Read-only market data ingestion adapters for the canonical market-data contract.

Provides the core OHLCV data models and a read-only adapter interface
for fetching market data. All adapters are offline-capable and require
no exchange API credentials.
"""

from __future__ import annotations

from si_v2.marketdata.adapter import FileBasedMarketDataAdapter, ReadOnlyMarketDataAdapter, StubMarketDataAdapter
from si_v2.marketdata.models import OHLCVDataset, OHLCVRow, OHLCVTimeframe

__all__: list[str] = [
    "FileBasedMarketDataAdapter",
    "OHLCVDataset",
    "OHLCVRow",
    "OHLCVTimeframe",
    "ReadOnlyMarketDataAdapter",
    "StubMarketDataAdapter",
]
