"""Export the numbers used by the summary page (monthly equity points + CI)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import study_costs as sc
import funding_study as fs

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"


def monthly_equity(trades: pd.DataFrame, df: pd.DataFrame, fee_rt: float, fund_r: pd.Series | float = 0.0):
    t = trades.copy()
    t["r_net"] = t["r_gross"] - fee_rt / t["stop_dist_frac"] - fund_r
    t["ret"] = sc.RISK_FRAC * t["r_net"]
    t["exit_ts"] = df["ts"].to_numpy()[t["exit_i"].to_numpy()]
    t = t.sort_values("exit_ts")
    eq = (1 + t["ret"]).cumprod()
    ser = pd.Series(eq.to_numpy(), index=t["exit_ts"])
    m = ser.resample("ME").last().ffill()
    m = pd.concat([pd.Series([1.0]), m]).reset_index(drop=True)
    return [round(float(x), 4) for x in m]


def pf_ci_block(trades: pd.DataFrame, fee_rt: float, fund_r: pd.Series, block: int = 5, reps: int = 10000, seed: int = 7):
    r = (trades["r_gross"] - fee_rt / trades["stop_dist_frac"] - fund_r).to_numpy()
    n = len(r)
    rng = np.random.default_rng(seed)
    out = np.empty(reps)
    for k in range(reps):
        idx = []
        while len(idx) < n:
            start = rng.integers(0, n)
            idx.extend(range(start, min(start + block, n)))
        x = r[np.array(idx[:n])]
        gp = x[x > 0].sum()
        gl = -x[x < 0].sum()
        out[k] = gp / gl if gl > 0 else np.nan
    out = out[np.isfinite(out)]
    return [round(float(np.percentile(out, 2.5)), 3), round(float(np.percentile(out, 97.5)), 3)]


def main() -> None:
    df5 = sc.load()
    fund = fs.load_funding()
    out = {}

    tr5 = sc.run_trades(df5, sc.trend_entries(df5, 288), sc.Exit(1.5, 2.0, 288))
    out["equity_5m_trend288_gross"] = monthly_equity(tr5, df5, 0.0)
    out["equity_5m_trend288_net"] = monthly_equity(tr5, df5, 10.14 / 1e4)

    d1 = fs.resample(df5, "1D")
    tr1 = sc.run_trades(d1, sc.trend_entries(d1, 40), sc.Exit(2.0, 4.0, 90))
    fr1 = fs.funding_in_R(tr1, d1, fund)
    out["equity_1d40_gross"] = monthly_equity(tr1, d1, 0.0)
    out["equity_1d40_fees"] = monthly_equity(tr1, d1, 10.14 / 1e4)
    out["equity_1d40_full"] = monthly_equity(tr1, d1, 10.14 / 1e4, fr1)
    out["pf_ci_1d40"] = pf_ci_block(tr1, 10.14 / 1e4, fr1)
    out["months"] = [str(x)[:7] for x in pd.period_range("2020-01", "2026-11", freq="M")]
    out["funding_by_year"] = {
        "2020": 17.24, "2021": 30.61, "2022": 4.16, "2023": 7.87,
        "2024": 11.96, "2025": 5.13, "2026": 2.60,
    }
    (CACHE / "chart_data.json").write_text(json.dumps(out), encoding="utf-8")
    print("months", len(out["months"]), "ci", out["pf_ci_1d40"])
    for k in ("equity_5m_trend288_gross", "equity_5m_trend288_net", "equity_1d40_full"):
        v = out[k]
        print(k, "start", v[0], "end", v[-1], "max", max(v), "min", min(v))


if __name__ == "__main__":
    main()
