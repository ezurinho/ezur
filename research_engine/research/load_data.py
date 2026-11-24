"""Download and validate BTCUSDT perpetual 5m klines from data.binance.vision.

Source: https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m/
Coverage verified: 2020-01 .. 2026-10 (monthly files; no earlier files exist).
Output: cache/btc_5m.parquet with UTC timestamps and OHLCV.
"""

from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m"
CACHE = Path(__file__).resolve().parent / "cache"
COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


def months(start: str, end: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")]


def download(month: str) -> pd.DataFrame | None:
    url = f"{BASE}/BTCUSDT-5m-{month}.zip"
    try:
        raw = urllib.request.urlopen(url, timeout=120).read()
    except Exception as exc:  # noqa: BLE001
        print(f"[skip] {month}: {exc}", file=sys.stderr)
        return None
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = zf.namelist()[0]
        text = zf.read(name).decode()
    first = text.split(",", 1)[0]
    header = 0 if first.replace("-", "").isdigit() else 1
    df = pd.read_csv(io.StringIO(text), header=None, names=COLS, skiprows=header)
    df = df[pd.to_numeric(df["open_time"], errors="coerce").notna()].copy()
    for c in COLS:
        if c != "ignore":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ts"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df[[
        "ts", "open", "high", "low", "close", "volume", "quote_volume",
        "count", "taker_buy_volume",
    ]]


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / "btc_5m.pkl"
    frames = []
    for m in months("2020-01", "2026-10"):
        df = download(m)
        if df is not None:
            frames.append(df)
    data = pd.concat(frames, ignore_index=True).sort_values("ts")
    dup = int(data["ts"].duplicated().sum())
    data = data.drop_duplicates("ts").reset_index(drop=True)

    gaps = data["ts"].diff().dropna()
    step = pd.Timedelta(minutes=5)
    missing = int((gaps // step - 1).clip(lower=0).sum())
    big = gaps[gaps > step]

    print(f"rows={len(data):,}  span={data.ts.min()} -> {data.ts.max()}  dupes={dup}")
    print(f"expected_bars={int((data.ts.max() - data.ts.min()) / step) + 1:,}  missing_bars={missing:,}")
    print("gaps>5m:", [(str(t), str(g)) for t, g in zip(data.loc[big.index, 'ts'].head(10), big.head(10))])
    print(f"price_last={data.close.iloc[-1]:,.2f}  price_min={data.low.min():,.2f}  price_max={data.high.max():,.2f}")
    data.to_pickle(out)
    print("saved", out)


if __name__ == "__main__":
    main()
