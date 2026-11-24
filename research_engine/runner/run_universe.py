"""Run one strategy across several perpetual futures, as one trade stream.

Why this exists. The trend line is not rejected for lack of profit factor: the 1d
ensemble has a net PF of 1.50 over 311 trades. It is rejected for lack of power,
t 1.66 against a hurdle of 3.0, and the minimum backtest length says 14.6 years are
needed while 6.8 exist. The only single-asset remedy is a decade of waiting. Extra
assets add observations that extra years cannot.

What it does NOT do. It does not claim independence. Crypto perps are strongly
correlated, so the aggregate t-stat is optimistic and the correlation is measured
and reported next to it. It also does not touch the single-asset engine: the same
`build_entries`, `run_trades`, `funding_in` and `metrics_block` run per symbol, and
the merge happens on exit timestamps as a single account would experience it.

    python runner/run_universe.py --spec runner/specs/btc-trend-1d-ensemble.json
    python runner/run_universe.py --spec ... --symbols BTCUSDT ETHUSDT
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import run_strategy as rs

ROOT = Path(__file__).resolve().parent.parent
MULTI = ROOT / "research" / "cache" / "multi"
OUT = Path(__file__).resolve().parent / "out-universe"
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]


def load_symbol(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame | None, dict]:
    kpath = MULTI / f"{symbol}_5m.pkl"
    if not kpath.exists():
        raise SystemExit(f"falta {kpath}; ejecuta research/load_multi.py")
    df = pd.read_pickle(kpath)
    fpath = MULTI / f"{symbol}_funding.pkl"
    fund = pd.read_pickle(fpath) if fpath.exists() else None
    step = df["ts"].diff().dropna()
    info = {
        "symbol": symbol,
        "bars": int(len(df)),
        "start": str(df["ts"].iloc[0]),
        "end": str(df["ts"].iloc[-1]),
        "gaps": int((step > pd.Timedelta(minutes=5)).sum()),
        "duplicates": int(df["ts"].duplicated().sum()),
        "sha256": hashlib.sha256(kpath.read_bytes()).hexdigest()[:16],
        "funding_events": int(len(fund)) if fund is not None else 0,
    }
    return df, fund, info


def run_symbol(spec: dict, symbol: str, df5: pd.DataFrame,
               fund: pd.DataFrame | None) -> tuple[pd.DataFrame, dict]:
    """Same engine as the single-asset runner, applied to one symbol."""
    bars, _ = rs.bars_for(df5, spec["timeframe_signal"])
    trades, weights = rs.run_portfolio(bars, spec, rs.run_trades, rs.build_entries)
    if trades.empty:
        return trades, {"symbol": symbol, "n": 0}

    fee_rt_bps = 2 * (spec["costs"]["fee_taker_bps"] + spec["costs"]["half_spread_bps"])
    fund_r = rs.funding_in(spec, trades, bars, fund)
    d = trades["stop_dist_frac"].to_numpy()
    r_gross = trades["r_gross"].to_numpy()
    fee_r = (fee_rt_bps * rs.BPS) / d
    stress_r = (fee_rt_bps * rs.STRESS_MULT * rs.BPS) / d
    r_net = (r_gross - fee_r - fund_r) * rs.vol_factors(bars, trades, spec)
    r_stress = (r_gross - stress_r - fund_r) * rs.vol_factors(bars, trades, spec)
    if weights is not None:
        r_net, r_stress = r_net * weights, r_stress * weights

    out = pd.DataFrame({
        "symbol": symbol,
        "exit_ts": bars["ts"].to_numpy()[trades["exit_i"].to_numpy()],
        "entry_ts": bars["ts"].to_numpy()[trades["entry_i"].to_numpy()],
        "r_gross": r_gross,
        "r_net": r_net,
        "r_stress": r_stress,
        "fee_r": fee_r,
        "fund_r": fund_r,
    })
    m = rs.metrics_block(trades, bars, r_net, r_stress, fee_r, fund_r,
                         seed=7, block=rs.BLOCK, reps=rs.REPS)
    return out, {
        "symbol": symbol,
        "n": int(len(trades)),
        "pf_net": m.get("pf_net"),
        "pf_stress": m.get("pf_stress"),
        "sharpe": m.get("sharpe"),
        "t_stat": m.get("t_stat"),
        "mdd": m.get("mdd"),
        "exp_net_r": m.get("exp_net_r"),
        "win": m.get("win"),
    }


def correlation_penalty(per_symbol: dict[str, pd.DataFrame],
                       price_daily: dict[str, pd.Series] | None = None) -> dict:
    """How much overlap there is between the symbols' return streams.

    Two numbers, because they answer different questions and only one of them is
    favourable. The correlation of the *strategy's* daily returns is low here, but
    largely because a breakout strategy is flat most days: two books that never
    trade on the same day are uncorrelated without being independent. The
    correlation of the *underlying* daily price returns is the dependence a critic
    would point at, so it is measured too and the conservative figure is the one
    used to discount the aggregate t-stat.

    The aggregate treats every trade as independent; effective power is roughly
    n / (1 + (k-1) * rho).
    """
    series = {}
    for sym, t in per_symbol.items():
        if t.empty:
            continue
        s = t.set_index("exit_ts")["r_net"].groupby(level=0).sum()
        series[sym] = s.resample("D").sum()
    if len(series) < 2:
        return {"pairs": {}, "mean_rho": None, "effective_multiplier": 1.0}

    def mean_offdiag(corr: pd.DataFrame) -> float:
        off = corr.to_numpy()[~np.eye(len(corr), dtype=bool)]
        return float(np.nanmean(off))

    def pairs_of(corr: pd.DataFrame) -> dict:
        return {f"{a}~{b}": round(float(corr.loc[a, b]), 3)
                for i, a in enumerate(corr.columns) for b in list(corr.columns)[i + 1:]}

    strat = pd.DataFrame(series).fillna(0.0).corr()
    rho_strat = mean_offdiag(strat)
    k = len(series)

    # Third view: correlate only the days where both books were actually in the
    # market. This is the most generous reading and it is reported last on purpose.
    frame = pd.DataFrame(series).fillna(0.0)
    cond_vals = []
    for i, a in enumerate(frame.columns):
        for b in list(frame.columns)[i + 1:]:
            both = frame[(frame[a] != 0) & (frame[b] != 0)]
            if len(both) < 20:
                continue
            r = both[a].corr(both[b])
            if np.isfinite(r):
                cond_vals.append(float(r))
    rho_cond = float(np.mean(cond_vals)) if cond_vals else None

    market = None
    rho_market = None
    if price_daily and len(price_daily) >= 2:
        mframe = pd.DataFrame(price_daily).fillna(0.0)
        market = mframe.corr()
        rho_market = mean_offdiag(market)

    used = max(rho_strat, rho_market) if rho_market is not None else rho_strat
    mult = 1.0 / (1.0 + (k - 1) * max(used, 0.0))
    mult_cond = (1.0 / (1.0 + (k - 1) * max(rho_cond, 0.0))) if rho_cond is not None else None
    return {
        "pairs": pairs_of(strat),
        "mean_rho": round(rho_strat, 3),
        "mean_rho_market": round(rho_market, 3) if rho_market is not None else None,
        "mean_rho_conditional": round(rho_cond, 3) if rho_cond is not None else None,
        "market_pairs": pairs_of(market) if market is not None else None,
        "rho_used": round(used, 3),
        "effective_multiplier": round(mult, 3),
        "effective_multiplier_conditional": round(mult_cond, 3) if mult_cond else None,
        "note": ("Tres correlaciones: la de la estrategia (baja porque no opera todos "
                 "los días), la condicional a que ambos libros estén dentro, y la de "
                 "mercado. El ajuste del t usa la mayor, que es la de mercado."),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run one spec across several symbols")
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    if spec.get("portfolio"):
        label = spec["label"]
    else:
        label = spec.get("label") or args.spec.stem

    per_symbol, summary, infos, frames = {}, [], [], []
    price_daily: dict[str, pd.Series] = {}
    for sym in args.symbols:
        df5, fund, info = load_symbol(sym)
        infos.append(info)
        trades, row = run_symbol(spec, sym, df5, fund)
        per_symbol[sym] = trades
        summary.append(row)
        price_daily[sym] = (df5.set_index("ts")["close"].resample("D").last()
                            .ffill().pct_change().fillna(0.0))
        if not trades.empty:
            frames.append(trades)
        if not args.quiet:
            if row["n"]:
                print(f"  {sym:9s} n={row['n']:5d}  PF {row['pf_net']:.3f}  "
                      f"SR {row['sharpe']:.2f}  t {row['t_stat']:.2f}  "
                      f"MDD {row['mdd']:.1%}")
            else:
                print(f"  {sym:9s} sin trades")

    if not frames:
        raise SystemExit("ningún activo operó")

    merged = pd.concat(frames, ignore_index=True).sort_values(
        ["exit_ts", "symbol"], kind="stable").reset_index(drop=True)

    # Budget: the spec's risk is split across the symbols actually traded, so the
    # portfolio does not silently double its exposure by adding assets.
    k = len(frames)
    scale = 1.0 / k
    r_net = merged["r_net"].to_numpy() * scale
    r_stress = merged["r_stress"].to_numpy() * scale

    exit_index = pd.DatetimeIndex(merged["exit_ts"])
    eq = (1 + rs.RISK * r_net)
    ser = pd.Series(eq.cumprod(), index=exit_index).sort_index()
    daily = ser.resample("D").last().ffill().pct_change().fillna(0.0)
    sd = daily.std(ddof=1)
    sharpe = float(daily.mean() / sd * math.sqrt(365)) if sd and sd > 0 else 0.0
    years = len(daily) / 365
    gp, gl = r_net[r_net > 0].sum(), -r_net[r_net < 0].sum()
    pf = float(gp / gl) if gl > 0 else None
    gps, gls = r_stress[r_stress > 0].sum(), -r_stress[r_stress < 0].sum()
    corr = correlation_penalty(per_symbol, price_daily)

    primary = args.symbols[0]
    agg = {
        "symbols": args.symbols,
        "assets_traded": k,
        "n": int(len(merged)),
        "pf_net": round(pf, 3) if pf else None,
        "pf_stress": round(float(gps / gls), 3) if gls > 0 else None,
        "exp_net_r": round(float(r_net.mean()), 4),
        "win": round(float((r_net > 0).mean()), 3),
        "sharpe": round(sharpe, 2),
        "t_stat": round(float(sharpe * math.sqrt(years)), 2),
        "t_stat_adjusted": round(float(sharpe * math.sqrt(years) *
                                       math.sqrt(corr["effective_multiplier"])), 2),
        "t_stat_conditional": (round(float(sharpe * math.sqrt(years) *
                                          math.sqrt(corr["effective_multiplier_conditional"])), 2)
                               if corr.get("effective_multiplier_conditional") else None),
        "years": round(years, 2),
        "mdd": round(float((ser / ser.cummax() - 1).min()), 3),
        "risk_scale_per_asset": round(scale, 4),
    }

    plan_bps = 0.4
    payload = {
        "spec_id": spec["id"],
        "version": spec["version"],
        "label": label,
        "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "spec_hash": "sha256:" + rs.canonical_hash(spec),
        "universe": infos,
        "aggregate": agg,
        "by_symbol": summary,
        "correlation": corr,
        "caveats": [
            "El t agregado trata cada trade como independiente; los activos están "
            "correlacionados. `t_stat_adjusted` descuenta la correlación media.",
            "El riesgo por trade se divide entre los activos que operan, así que el "
            "MDD no se multiplica por el número de activos.",
            "Un activo que pierde no se elimina: quitar el que falla convierte el "
            "universo en otra selección.",
            "El benchmark es el de cada activo; el alpha agregado requiere comparar "
            "contra una cartera equiponderada de los mismos activos, y no se calcula aquí.",
        ],
    }
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{spec['id']}-v{spec['version']}-universe.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"agregado  n={agg['n']}  PF {agg['pf_net']}  2x {agg['pf_stress']}  "
          f"SR {agg['sharpe']}  t {agg['t_stat']} (ajustado {agg['t_stat_adjusted']})  "
          f"MDD {agg['mdd']:.1%}")
    print(f"correlación estrategia {corr['mean_rho']} · condicional "
          f"{corr['mean_rho_conditional']} · mercado {corr['mean_rho_market']}")
    print(f"t ajustado por la mayor de ellas ({corr['rho_used']}): "
          f"{agg['t_stat_adjusted']}" +
          (f" · condicional {agg['t_stat_conditional']}" if agg["t_stat_conditional"] else ""))
    print(f"\nresultado  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
