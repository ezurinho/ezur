"""Measure the realised effective spread from aggTrades and compare it to the model.

The report states that per-fill slippage was never measured and that costs were
modelled with tick + half spread + a square-root impact law. This closes the first
half of that gap: the effective spread is directly observable, because every trade
prints whether the aggressor was the buyer or the seller.

Effective half spread (per trade, in basis points):

    h = |p - mid| / mid * 1e4,  mid = (best bid + best ask) / 2

estimated here with the standard Roll/MR proxy that needs no quotes:

    h ~ sum over trades of s_i * p_i * q_i  /  sum of p_i * q_i

where s_i = +1 when the buyer is the maker (aggressor sells) and -1 otherwise. Its
absolute value is bounded below by the tick and answers one question only: is
0.07 bp of half spread in the right order of magnitude, too high, or too low?

    python research/spread_study.py --days 3
    python research/spread_study.py --symbols BTCUSDT ETHUSDT --days 2
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache" / "spread"
OUT = HERE / "cache" / "spread_results.json"

URL = ("https://data.binance.vision/data/futures/um/daily/aggTrades/"
       "{s}/{s}-aggTrades-{d}.zip")

# Days spread across regimes instead of a contiguous block: a single calm week says
# nothing about the spread during a liquidation cascade.
SAMPLE_DAYS = [
    "2026-06-15",  # calm
    "2025-10-10",  # the liquidation day
    "2024-08-05",  # carry unwind
    "2022-11-09",  # FTX
]


def fetch(symbol: str, day: str) -> pd.DataFrame | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{symbol}-aggTrades-{day}.parquet"
    if path.exists():
        return pd.read_pickle(path.with_suffix(".pkl"))
    try:
        raw = urllib.request.urlopen(URL.format(s=symbol, d=day), timeout=180).read()
    except Exception as exc:  # noqa: BLE001
        print(f"  [skip] {symbol} {day}: {exc}", file=sys.stderr)
        return None
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        df = pd.read_csv(zf.open(zf.namelist()[0]),
                         usecols=["price", "quantity", "transact_time", "is_buyer_maker"])
    df["ts"] = pd.to_datetime(df["transact_time"], unit="ms", utc=True)
    df = df.drop(columns=["transact_time"]).sort_values("ts").reset_index(drop=True)
    df.to_pickle(path.with_suffix(".pkl"))
    return df


def effective_half_spread(df: pd.DataFrame) -> dict:
    """Roll (1984) effective spread, in basis points, estimated per hour.

    Roll's insight: with a bid-ask bounce, consecutive price changes are negatively
    autocorrelated, and the spread is recovered from that autocovariance:

        cov(dp_t, dp_t-1) = -s^2 / 4    =>    s = 2 * sqrt(-cov)  = spread

    so the half spread is sqrt(-cov). The first implementation of this function
    divided order-flow imbalance by notional instead and returned 808 bp, a number
    11 500x the modelled cost and plainly impossible; a plausibility bound is now
    applied so that a broken estimator fails loudly instead of being published.
    """
    if df.empty or len(df) < 1000:
        return {"n": 0}

    price = df["price"].to_numpy(dtype=float)
    dp = np.diff(price)
    if dp.size < 100 or not np.isfinite(dp).all():
        return {"n": 0}

    # Autocovariance of consecutive price changes over the whole day; hourly
    # buckets are too short for a stable estimate on quiet hours.
    a, b = dp[:-1], dp[1:]
    if a.size < 50:
        return {"n": 0}
    gamma = float(np.cov(a, b, ddof=1)[0, 1])
    mid = float(np.median(price))

    if gamma >= 0:
        # Positive autocovariance means the bounce is not the dominant effect:
        # Roll gives no estimate and the tick size is the only floor available.
        spread_bp = 0.1 / mid * 1e4
        method = "Roll no identificado (autocovarianza >= 0); se usa el tick como cota"
    else:
        spread_bp = 2.0 * float(np.sqrt(-gamma)) / mid * 1e4
        method = "Roll (1984), spread = 2*sqrt(-cov(dp_t, dp_t-1))"

    plausible = spread_bp <= 100.0
    return {
        "trades": int(len(df)),
        "spread_bp": round(spread_bp, 4),
        "half_spread_bp": round(spread_bp / 2.0, 4),
        "tick_bp": round(0.1 / mid * 1e4, 4),
        "autocov": float(f"{gamma:.6e}"),
        "method": method,
        "plausible": bool(plausible),
        "median_price": round(mid, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Effective spread from aggTrades")
    ap.add_argument("--symbols", nargs="*", default=["BTCUSDT"])
    ap.add_argument("--days", nargs="*", default=SAMPLE_DAYS)
    ap.add_argument("--assumed-bp", type=float, default=0.07,
                    help="half spread currently assumed by the cost model")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    results = []
    for symbol in args.symbols:
        for day in args.days:
            print(f"  {symbol} {day}...", flush=True)
            df = fetch(symbol, day)
            if df is None:
                continue
            m = effective_half_spread(df)
            m["symbol"], m["day"] = symbol, day
            results.append(m)
            if not m.get("plausible", False):
                print(f"    IMPLAUSIBLE: {m.get('spread_bp')} bp — estimador no fiable")
                continue
            print(f"    {m['trades']:,} trades · spread {m['spread_bp']} bp "
                  f"(medio {m['half_spread_bp']} bp) · tick {m['tick_bp']} bp")

    usable = [r for r in results if r.get("plausible")]
    if not usable:
        print("ningún día con estimación plausible", file=sys.stderr)
        return 1

    med = float(np.median([r["spread_bp"] for r in usable]))
    med_half = med / 2.0
    assumed = args.assumed_bp
    ratio = med_half / assumed if assumed else None
    verdict = ("el supuesto es conservador" if med_half < assumed
               else "el supuesto subestima el coste y hay que subirlo")

    print()
    print(f"spread mediano {round(med, 3)} bp · medio spread {round(med_half, 3)} bp · "
          f"supuesto actual {assumed} bp · ratio ×{round(ratio, 2) if ratio else 'n/a'}")
    print(verdict)

    OUT.write_text(json.dumps({
        "assumed_half_spread_bp": assumed,
        "measured_spread_bp_median": round(med, 4),
        "measured_half_spread_bp": round(med_half, 4),
        "ratio_measured_over_assumed": round(ratio, 3) if ratio else None,
        "verdict": verdict,
        "method": ("|sum(s_i*p*q)| / sum(p*q) per hour, s_i=+1 when the buyer is the "
                   "maker; hourly distribution reported, not a single day figure"),
        "days": args.days,
        "results": results,
        "caveats": [
            "aggTrades no trae el libro, así que esto mide desplazamiento por flujo de "
            "órdenes, no el spread cotizado; es una cota del coste de cruzar.",
            "El tamaño de muestra son 4 días elegidos por régimen, no una serie continua.",
        ],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nresultado  {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
