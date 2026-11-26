"""Second half of the reference study: funding costs, higher timeframes, DSR/PBO.

Same execution engine as study_costs.py, applied to 4h/1d Donchian breakouts,
now deducting *real* Binance BTCUSDT funding rates (data.binance.vision) in
addition to taker fees. Also runs an anchored walk-forward and reports the
per-year breakdown.
"""

from __future__ import annotations

import io
import json
import math
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

import study_costs as sc

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
FUND_BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT"
FEE_RT = 10.14 / 1e4   # taker 5.07bp per side


def load_funding() -> pd.DataFrame:
    path = CACHE / "funding.parquet"
    if path.exists():
        return pd.read_pickle(path)
    frames = []
    for p in pd.period_range("2020-01", "2026-10", freq="M"):
        m = p.strftime("%Y-%m")
        url = f"{FUND_BASE}/BTCUSDT-fundingRate-{m}.zip"
        try:
            raw = urllib.request.urlopen(url, timeout=90).read()
        except Exception as exc:  # noqa: BLE001
            print("[funding skip]", m, exc)
            continue
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            df = pd.read_csv(io.BytesIO(zf.read(zf.namelist()[0])))
        df["ts"] = pd.to_datetime(df["calc_time"], unit="ms", utc=True)
        frames.append(df[["ts", "funding_interval_hours", "last_funding_rate"]])
    f = pd.concat(frames).sort_values("ts").reset_index(drop=True)
    f.to_pickle(path)
    return f


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = df.set_index("ts").resample(rule, label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum")).dropna().reset_index()
    agg["ts"] = pd.to_datetime(agg["ts"], utc=True)
    pc = agg["close"].shift(1)
    tr = pd.concat([agg.high - agg.low, (agg.high - pc).abs(), (agg.low - pc).abs()], axis=1).max(axis=1)
    agg["atr"] = tr.rolling(14).mean()
    return agg


def funding_in_R(trades: pd.DataFrame, df: pd.DataFrame, fund: pd.DataFrame) -> pd.Series:
    """Funding paid while the position is open, expressed in units of R."""
    ts = df["ts"].to_numpy()
    f_ts = fund["ts"].to_numpy()
    f_rate = fund["last_funding_rate"].to_numpy()
    out = []
    for _, t in trades.iterrows():
        t0, t1 = ts[int(t.entry_i)], ts[int(t.exit_i)]
        mask = (f_ts > t0) & (f_ts <= t1)
        rate_sum = float(f_rate[mask].sum())
        # long pays positive funding, short receives it
        out.append(float(t.side) * rate_sum / float(t.stop_dist_frac))
    return pd.Series(out, index=trades.index)


def metrics_ext(trades: pd.DataFrame, df: pd.DataFrame, fee_rt: float, fund_r: pd.Series | None) -> dict:
    t = trades.copy()
    fee_r = fee_rt / t["stop_dist_frac"]
    t["r_net"] = t["r_gross"] - fee_r - (fund_r if fund_r is not None else 0.0)
    t["ret"] = sc.RISK_FRAC * t["r_net"]
    t["exit_ts"] = df["ts"].to_numpy()[t["exit_i"].to_numpy()]
    eq = (1 + t.sort_values("exit_ts")["ret"]).cumprod()
    mdd = float((eq / eq.cummax() - 1).min())
    by_day = t.groupby(t["exit_ts"].dt.floor("D"))["ret"].sum()
    days = pd.date_range(df["ts"].iloc[0].floor("D"), df["ts"].iloc[-1].floor("D"), freq="D")
    daily = by_day.reindex(days, fill_value=0.0)
    sd = daily.std(ddof=1)
    gp = t.loc[t["r_net"] > 0, "r_net"].sum()
    gl = -t.loc[t["r_net"] < 0, "r_net"].sum()
    years = (df["ts"].iloc[-1] - df["ts"].iloc[0]).days / 365.25
    sharpe = float(daily.mean() / sd * math.sqrt(365)) if sd > 0 else 0.0
    return dict(
        n=int(len(t)), win=float((t["r_net"] > 0).mean()), exp_r=float(t["r_net"].mean()),
        pf=float(gp / gl) if gl > 0 else float("inf"), sharpe=sharpe, mdd=mdd,
        t_stat=float(sharpe * math.sqrt(years)), cagr=float(eq.iloc[-1] ** (1 / years) - 1),
        fee_r=float(fee_r.mean()), funding_r=float(fund_r.mean()) if fund_r is not None else 0.0,
        years=years, daily=daily,
    )


def main() -> None:
    df5 = sc.load()
    fund = load_funding()
    print("funding events:", len(fund), fund.ts.min(), "->", fund.ts.max())
    per_year = fund.set_index("ts")["last_funding_rate"].resample("YE").sum()
    print("annual sum of funding rates (long pays):")
    print((per_year * 100).round(2).to_string())
    print(f"mean 8h rate={fund.last_funding_rate.mean()*100:.4f}%  positive share={np.mean(fund.last_funding_rate>0):.3f}")

    results, daily_curves = {}, {}
    htf = {"4h": (resample(df5, "4h"), (12, 24, 48), 20), "1d": (resample(df5, "1D"), (10, 20, 40, 55, 100), 90)}
    for label, (agg, windows, hold) in htf.items():
        for n in windows:
            tr = sc.run_trades(agg, sc.trend_entries(agg, n), sc.Exit(2.0, 4.0, hold))
            fr = funding_in_R(tr, agg, fund)
            gross = metrics_ext(tr, agg, 0.0, None)
            fees = metrics_ext(tr, agg, FEE_RT, None)
            full = metrics_ext(tr, agg, FEE_RT, fr)
            key = f"{label}_donchian_{n}"
            results[key] = {k: v for k, v in full.items() if k != "daily"}
            results[key].update(gross_pf=gross["pf"], fees_pf=fees["pf"], gross_exp=gross["exp_r"])
            daily_curves[key] = full["daily"]
            # per-year net R
            t = tr.copy()
            t["r_net"] = t["r_gross"] - FEE_RT / t["stop_dist_frac"] - fr
            t["year"] = agg["ts"].to_numpy()[t["exit_i"].to_numpy()].astype("datetime64[Y]").astype(str)
            results[key]["per_year"] = {y: dict(n=int(len(g)), exp_r=round(float(g.r_net.mean()), 3))
                                        for y, g in t.groupby("year")}

    # ---- PBO over the high-timeframe grid (positive dispersion)
    perf = pd.DataFrame(daily_curves).fillna(0.0)
    pbo = sc.cscv_pbo(perf, s_blocks=10)
    srs = {k: float(v.mean() / v.std(ddof=1) * math.sqrt(365)) for k, v in perf.items() if v.std(ddof=1) > 0}
    best = max(srs, key=srs.get)
    ser = perf[best]
    dsr = sc.deflated_sharpe(sr_ann=srs[best], trials=list(srs.values()),
                             years=len(ser) / 365.0, skew=float(ser.skew()),
                             kurt=float(ser.kurtosis() + 3))
    # Harvey-Liu-Zhu hurdle: t > 3.0
    results["_summary"] = dict(
        pbo=pbo, n_configs=perf.shape[1], best=best, best_sr=srs[best],
        best_t_stat=srs[best] * math.sqrt(len(ser) / 365.0), dsr=dsr,
        htz_hurdle_sr=3.0 / math.sqrt(len(ser) / 365.0),
    )

    # ---- anchored walk-forward: pick best of the 1d grid on 2y train, trade next 6m
    agg = htf["1d"][0]
    grid = (10, 20, 40, 55, 100)
    trades = {n: sc.run_trades(agg, sc.trend_entries(agg, n), sc.Exit(2.0, 4.0, 90)) for n in grid}
    for _n, t in trades.items():
        t["r_net"] = t["r_gross"] - FEE_RT / t["stop_dist_frac"] - funding_in_R(t, agg, fund)
    start, end = agg.ts.iloc[0].tz_convert(None), agg.ts.iloc[-1].tz_convert(None)
    ts_all = pd.Series(agg["ts"]).dt.tz_convert(None)
    folds, cursor = [], start
    while cursor + pd.DateOffset(years=2, months=6) <= end:
        train_end = cursor + pd.DateOffset(years=2)
        test_end = train_end + pd.DateOffset(months=6)
        scores = {}
        for n, t in trades.items():
            ts_exit = ts_all.iloc[t["exit_i"].to_numpy()].reset_index(drop=True)
            m = (ts_exit >= cursor) & (ts_exit < train_end)
            scores[n] = float(t.loc[m.to_numpy(), "r_net"].mean()) if m.sum() >= 5 else -9.9
        pick = max(scores, key=scores.get)
        t = trades[pick]
        ts_exit = ts_all.iloc[t["exit_i"].to_numpy()].reset_index(drop=True)
        m = ((ts_exit >= train_end) & (ts_exit < test_end)).to_numpy()
        folds.append(dict(train=str(cursor.date()), pick=pick, oos_trades=int(m.sum()),
                          oos_exp_r=round(float(t.loc[m, "r_net"].mean()), 3) if m.sum() else None))
        cursor = test_end
    results["_wfa"] = folds
    results["_wfa_total"] = dict(oos_trades=sum(f["oos_trades"] for f in folds),
                                 mean_exp_r=round(float(np.mean([f["oos_exp_r"] for f in folds if f["oos_exp_r"] is not None])), 3))

    (CACHE / "funding_results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    show = ["n", "win", "gross_pf", "fees_pf", "pf", "exp_r", "sharpe", "mdd", "t_stat", "cagr", "funding_r", "fee_r"]
    print("\n=== higher timeframes, net of taker fees AND real funding ===")
    print(pd.DataFrame({k: v for k, v in results.items() if not k.startswith("_")}).T[show].astype(float).round(3).to_string())
    print("\nsummary:", json.dumps(results["_summary"], indent=2, default=str))
    print("\nWFA:", json.dumps(results["_wfa"], indent=1), results["_wfa_total"])


if __name__ == "__main__":
    main()
