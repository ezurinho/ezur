"""Download and validate perpetual futures data for several symbols.

Same public source as the single-asset study (data.binance.vision, S3), so the
provenance chain does not change: monthly 5m klines and monthly funding rates for
every symbol in `SYMBOLS`.

The point is statistical power. With one asset the trend line has 311 trades over
6.8 years and a t-stat of 1.66 against a hurdle of 3.0; waiting for the sample to
grow is the only single-asset remedy and it takes a decade. Five correlated assets
add observations in a way that one more year cannot.

    python research/load_multi.py                 # download whatever is missing
    python research/load_multi.py --symbols ETHUSDT SOLUSDT
    python research/load_multi.py --report        # validate the cache only

Output: cache/multi/<SYMBOL>_5m.pkl, cache/multi/<SYMBOL>_funding.pkl and
cache/multi_manifest.json with coverage, integrity counts and sha256 per file.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache" / "multi"
MANIFEST = HERE / "cache" / "multi_manifest.json"

KLINE_BASE = "https://data.binance.vision/data/futures/um/monthly/klines/{s}/5m/{s}-5m-{m}.zip"
FUNDING_BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate/{s}/{s}-fundingRate-{m}.zip"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT"]
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
BAR = pd.Timedelta(minutes=5)


def months(start: str, end: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")]


def _fetch(url: str, timeout: int = 120) -> bytes | None:
    try:
        return urllib.request.urlopen(url, timeout=timeout).read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None


def fetch_klines(symbol: str, month: str) -> pd.DataFrame | None:
    raw = _fetch(KLINE_BASE.format(s=symbol, m=month))
    if raw is None:
        return None
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        text = zf.read(zf.namelist()[0]).decode()
    first = text.split(",", 1)[0]
    header = 0 if first.replace("-", "").isdigit() else 1
    df = pd.read_csv(io.StringIO(text), header=None, names=COLS, skiprows=header)
    df = df[pd.to_numeric(df["open_time"], errors="coerce").notna()].copy()
    for c in COLS:
        if c != "ignore":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ts"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df[["ts", "open", "high", "low", "close", "volume", "quote_volume",
               "count", "taker_buy_volume"]]


def fetch_funding(symbol: str, month: str) -> pd.DataFrame | None:
    raw = _fetch(FUNDING_BASE.format(s=symbol, m=month))
    if raw is None:
        return None
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        df = pd.read_csv(io.BytesIO(zf.read(zf.namelist()[0])))
    df["ts"] = pd.to_datetime(df["calc_time"], unit="ms", utc=True)
    return df[["ts", "funding_interval_hours", "last_funding_rate"]]


def fetch_klines_daily(symbol: str, day: str) -> pd.DataFrame | None:
    """Daily file fallback for the holes some monthly archives leave at month edges."""
    url = ("https://data.binance.vision/data/futures/um/daily/klines/"
           f"{symbol}/5m/{symbol}-5m-{day}.zip")
    raw = _fetch(url, timeout=60)
    if raw is None:
        return None
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        text = zf.read(zf.namelist()[0]).decode()
    first = text.split(",", 1)[0]
    header = 0 if first.replace("-", "").isdigit() else 1
    df = pd.read_csv(io.StringIO(text), header=None, names=COLS, skiprows=header)
    df = df[pd.to_numeric(df["open_time"], errors="coerce").notna()].copy()
    for c in COLS:
        if c != "ignore":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ts"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df[["ts", "open", "high", "low", "close", "volume", "quote_volume",
               "count", "taker_buy_volume"]]


def fill_gaps(df: pd.DataFrame, symbol: str) -> tuple[pd.DataFrame, list[str]]:
    """Fetch the missing days from the daily archive instead of accepting the hole.

    Monthly files occasionally stop a few days early at a month boundary. A gap in
    a bar series is not cosmetic: a trade that spans it exits at the wrong price and
    the ATR is computed over a jump. Missing days are fetched one by one and the
    ones that could not be recovered are reported."""
    steps = df["ts"].diff()
    holes = df.index[steps > BAR]
    if not len(holes):
        return df, []

    wanted: list[str] = []
    for i in holes:
        start, end = df["ts"].iloc[i - 1], df["ts"].iloc[i]
        for day in pd.date_range(start.normalize() + pd.Timedelta(days=1),
                                 end.normalize(), freq="D"):
            wanted.append(day.strftime("%Y-%m-%d"))

    extra = []
    with ThreadPoolExecutor(8) as ex:
        for part in ex.map(lambda d: fetch_klines_daily(symbol, d), wanted):
            if part is not None:
                extra.append(part)
    if not extra:
        return df, wanted
    merged = pd.concat([df, *extra]).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    still = merged.index[merged["ts"].diff() > BAR]
    recovered = len(wanted) - len(still)
    print(f"  {symbol}: {len(wanted)} días rellenados desde el archivo diario"
          f" ({recovered}/{len(wanted)})")
    return merged, [merged["ts"].iloc[i].strftime("%Y-%m-%d %H:%M") for i in still]


def integrity(df: pd.DataFrame) -> dict:
    """Gaps and duplicates measured against the 5-minute grid, not guessed."""
    if df.empty:
        return {"bars": 0, "first": None, "last": None, "gaps": None, "duplicates": None}
    steps = df["ts"].diff().dropna()
    return {
        "bars": int(len(df)),
        "first": str(df["ts"].iloc[0]),
        "last": str(df["ts"].iloc[-1]),
        "gaps": int((steps > BAR).sum()),
        "duplicates": int(df["ts"].duplicated().sum()),
        "max_gap_hours": round(float(steps.max().total_seconds() / 3600), 2) if len(steps) else None,
    }


def build_symbol(symbol: str, start: str, end: str, workers: int = 8) -> dict | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    kpath = CACHE / f"{symbol}_5m.pkl"
    fpath = CACHE / f"{symbol}_funding.pkl"

    ms = months(start, end)
    if not kpath.exists():
        with ThreadPoolExecutor(workers) as ex:
            parts = [p for p in ex.map(lambda m: fetch_klines(symbol, m), ms) if p is not None]
        if not parts:
            print(f"  {symbol}: sin klines", file=sys.stderr)
            return None
        df = pd.concat(parts).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
        df, unrecovered = fill_gaps(df, symbol)
        if unrecovered:
            print(f"  {symbol}: gaps sin recuperar en {unrecovered}", file=sys.stderr)
        df.to_pickle(kpath)
    else:
        df = pd.read_pickle(kpath)

    if not fpath.exists():
        with ThreadPoolExecutor(workers) as ex:
            fparts = [p for p in ex.map(lambda m: fetch_funding(symbol, m), ms) if p is not None]
        if fparts:
            pd.concat(fparts).drop_duplicates("ts").sort_values("ts").reset_index(drop=True).to_pickle(fpath)

    fund = pd.read_pickle(fpath) if fpath.exists() else pd.DataFrame()
    entry = {
        "symbol": symbol,
        "klines": integrity(df),
        "sha256": hashlib.sha256(kpath.read_bytes()).hexdigest()[:16],
        "bytes": kpath.stat().st_size,
        "funding_events": int(len(fund)),
        "funding_sha256": (hashlib.sha256(fpath.read_bytes()).hexdigest()[:16]
                           if fpath.exists() else None),
        "funding_first": str(fund["ts"].iloc[0]) if len(fund) else None,
        "funding_last": str(fund["ts"].iloc[-1]) if len(fund) else None,
    }
    return entry


def common_window(rows: list[dict]) -> dict:
    firsts = [r["klines"]["first"] for r in rows if r["klines"]["first"]]
    lasts = [r["klines"]["last"] for r in rows if r["klines"]["last"]]
    if not firsts or not lasts:
        return {}
    lo, hi = max(firsts), min(lasts)
    years = (pd.Timestamp(hi) - pd.Timestamp(lo)).days / 365.25
    return {"start": lo, "end": hi, "years": round(years, 2),
            "binding_symbol": next(r["symbol"] for r in rows if r["klines"]["first"] == lo)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Multi-asset data download and validation")
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    ap.add_argument("--start", default="2020-01")
    ap.add_argument("--end", default="2026-10")
    ap.add_argument("--report", action="store_true", help="validate the cache, download nothing")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    rows = []
    for symbol in args.symbols:
        if args.report:
            kpath = CACHE / f"{symbol}_5m.pkl"
            if not kpath.exists():
                print(f"  {symbol:9s} sin caché")
                continue
            df = pd.read_pickle(kpath)
            rows.append({"symbol": symbol, "klines": integrity(df),
                         "sha256": hashlib.sha256(kpath.read_bytes()).hexdigest()[:16],
                         "bytes": kpath.stat().st_size,
                         "funding_events": 0, "funding_first": None, "funding_last": None})
        else:
            print(f"  descargando {symbol}...", flush=True)
            entry = build_symbol(symbol, args.start, args.end)
            if entry:
                rows.append(entry)

    if not rows:
        print("nada que hacer")
        return 1

    print()
    print(f"{'activo':9s} {'barras':>8s} {'desde':11s} {'hasta':11s} {'gaps':>5s} "
          f"{'dup':>4s} {'funding':>8s}")
    for r in rows:
        k = r["klines"]
        print(f"{r['symbol']:9s} {k['bars']:8,d} {str(k['first'])[:10]:11s} "
              f"{str(k['last'])[:10]:11s} {str(k['gaps']):>5s} {str(k['duplicates']):>4s} "
              f"{r['funding_events']:8,d}")

    win = common_window(rows)
    if win:
        print(f"\nventana común: {win['start'][:10]} → {win['end'][:10]} "
              f"({win['years']} años, limita {win['binding_symbol']})")
    bad = [r["symbol"] for r in rows if (r["klines"]["gaps"] or 0) > 0
           or (r["klines"]["duplicates"] or 0) > 0]
    if bad:
        print(f"aviso: gaps o duplicados en {bad} — revisar antes de usarlos", file=sys.stderr)

    MANIFEST.write_text(json.dumps({
        "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "data.binance.vision (S3 public archive), monthly 5m klines and fundingRate",
        "window_requested": [args.start, args.end],
        "common_window": win,
        "symbols": rows,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nmanifiesto {MANIFEST}")
    return 0 if not bad else 2


if __name__ == "__main__":
    raise SystemExit(main())
