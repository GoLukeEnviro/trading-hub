import pandas as pd
from pathlib import Path

src_dir = Path("/freqtrade/user_data/data/bitget/futures")

for f in sorted(src_dir.glob("*-1h-futures.feather")):
    pair_base = f.name.split("-1h-futures")[0]
    dst = src_dir / f"{pair_base}-1d-futures.feather"
    
    df = pd.read_feather(f)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    
    daily = df.resample("1d").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna()
    
    daily.reset_index(inplace=True)
    daily.to_feather(dst)
    print(f"{pair_base}: {len(daily)} candles")

print("Done")
