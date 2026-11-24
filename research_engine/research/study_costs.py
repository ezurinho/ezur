"""Reference study: does a 5-minute BTC perp signal survive realistic costs?

Purpose: provide *real*, reproducible numbers for the prompt audit, not to
propose a profitable strategy. Four families are tested with a small,
a-priori (literature-motivated) grid, no optimisation:

  1. trend      : Donchian breakout (close > highest high of previous N bars)
  2. momentum   : EMA(fast)/EMA(slow) state
  3. mean_rev   : z-score of close vs rolling mean, fade the extreme
  4. orb        : session opening-range breakout (London 08:00 UTC, NY 13:30 UTC)

Execution model (conservative, no lookahead):
  - signal on close of bar t  ->  fill at open of bar t+1, adverse slippage
  - stop / target checked on every later bar's high/low, stop first on ties
  - gap through the stop fills at the bar open, not at the stop price
  - time stop at the open of bar entry+H
  - costs charged on both legs, in units of R, via stop distance

Outputs: cache/study_results.json + printed tables.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
TICK = 0.10          # BTCUSDT perp minimum price movement (Binance trading rules)
RISK_FRAC = 0.005    # 0.5% equity risked per trade (fixed-fractional)
BARS_PER_DAY = 288


# ----------------------------------------------------------------------------- data
def load() -> pd.DataFrame:
    df = pd.read_pickle(CACHE / "btc_5m.pkl")
    df = df.reset_index(drop=True)
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["ema12"] = c.ewm(span=12, adjust=False).mean()
    df["ema48"] = c.ewm(span=48, adjust=False).mean()
    df["ema96"] = c.ewm(span=96, adjust=False).mean()
    df["ema192"] = c.ewm(span=192, adjust=False).mean()
    df["ema24"] = c.ewm(span=24, adjust=False).mean()
    return df


# ------------------------------------------------------------------- trade engine
@dataclass(frozen=True)
class Exit:
    k_atr: float
    tp_r: float
    max_hold: int


def run_trades(df: pd.DataFrame, entries: list[tuple[int, int, float]], ex: Exit) -> pd.DataFrame:
    """entries: list of (bar_index_of_signal, side(+1/-1), stop_distance_abs).

    One position at a time: an entry is skipped while a previous trade is open
    (no pyramiding, no overlapping trades).
    """
    o = df["open"].to_numpy()
    hi = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    n = len(df)
    rows = []
    last_exit = -1
    for sig_i, side, dist in entries:
        if sig_i <= last_exit:
            continue
        i = sig_i + 1                      # fill at next bar open
        if i >= n or dist <= 0:
            continue
        entry = o[i]
        stop = entry - side * dist
        tp = entry + side * ex.tp_r * dist
        exit_i, exit_px, reason = None, None, None
        last = min(n - 1, i + ex.max_hold)
        for j in range(i, last + 1):
            if j > i:
                gap_hit = (side == 1 and o[j] <= stop) or (side == -1 and o[j] >= stop)
                if gap_hit:
                    exit_i, exit_px, reason = j, o[j], "gap_stop"
                    break
            if side == 1:
                if lo[j] <= stop:
                    exit_i, exit_px, reason = j, stop, "stop"
                    break
                if hi[j] >= tp:
                    exit_i, exit_px, reason = j, tp, "target"
                    break
            else:
                if hi[j] >= stop:
                    exit_i, exit_px, reason = j, stop, "stop"
                    break
                if lo[j] <= tp:
                    exit_i, exit_px, reason = j, tp, "target"
                    break
        if exit_i is None:
            exit_i, exit_px, reason = last, o[last], "time"
        r_gross = side * (exit_px - entry) / dist
        last_exit = exit_i
        rows.append(
            dict(sig_i=sig_i, entry_i=i, exit_i=exit_i, side=side, entry=entry,
                 exit=exit_px, stop_dist=dist, stop_dist_frac=dist / entry,
                 r_gross=r_gross, reason=reason)
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------- generators
def trend_entries(df: pd.DataFrame, n: int) -> list[tuple[int, int, float]]:
    hi, lo, c, atr = (df[k].to_numpy() for k in ("high", "low", "close", "atr"))
    up = pd.Series(hi).rolling(n).max().shift(1).to_numpy()
    dn = pd.Series(lo).rolling(n).min().shift(1).to_numpy()
    out = []
    for i in range(n + 1, len(df) - 1):
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        if c[i] > up[i]:
            out.append((i, 1, 1.5 * atr[i]))
        elif c[i] < dn[i]:
            out.append((i, -1, 1.5 * atr[i]))
    return out


def momentum_entries(df: pd.DataFrame, fast: str, slow: str) -> list[tuple[int, int, float]]:
    f, s, atr = df[fast].to_numpy(), df[slow].to_numpy(), df["atr"].to_numpy()
    state = np.where(f > s, 1, -1)
    change = np.r_[False, state[1:] != state[:-1]]
    out = []
    for i in range(1, len(df) - 1):
        if change[i] and np.isfinite(atr[i]) and atr[i] > 0:
            out.append((i, int(state[i]), 1.5 * atr[i]))
    return out


def meanrev_entries(df: pd.DataFrame, n: int, z: float, ex_r: float) -> list[tuple[int, int, float]]:
    c, atr = df["close"].to_numpy(), df["atr"].to_numpy()
    ma = pd.Series(c).rolling(n).mean().to_numpy()
    sd = pd.Series(c).rolling(n).std().to_numpy()
    out = []
    for i in range(n + 1, len(df) - 1):
        if not np.isfinite(sd[i]) or sd[i] <= 0 or not np.isfinite(atr[i]):
            continue
        zz = (c[i] - ma[i]) / sd[i]
        if zz < -z:
            out.append((i, 1, ex_r * atr[i]))
        elif zz > z:
            out.append((i, -1, ex_r * atr[i]))
    return out


def orb_entries(df: pd.DataFrame, range_bars: int, sessions: tuple[tuple[int, int], ...]) -> list[tuple[int, int, float]]:
    """Session opening-range breakout. sessions: (hour, minute) in UTC."""
    ts = df["ts"]
    o, hi, lo, c, atr = (df[k].to_numpy() for k in ("open", "high", "low", "close", "atr"))
    dates = ts.dt.strftime("%Y-%m-%d").to_numpy()
    minutes = (ts.dt.hour * 60 + ts.dt.minute).to_numpy()
    out = []
    start_idx: dict[tuple[str, int], int] = {}
    for i in range(len(df)):
        key_min = minutes[i]
        for k, (hh, mm) in enumerate(sessions):
            if key_min == hh * 60 + mm:
                start_idx[(dates[i], k)] = i
        for k, (hh, mm) in enumerate(sessions):
            s = start_idx.get((dates[i], k))
            if s is None:
                continue
            r_end = s + range_bars            # last bar of the opening range
            session_end = s + 96              # 8h of bars
            if i <= r_end or i >= min(session_end, len(df) - 1):
                continue
            if not np.isfinite(atr[i]) or atr[i] <= 0:
                continue
            # only the first breakout of the session, and no entries in the last 12 bars
            prev_break = 0
            for j in range(r_end + 1, i):
                if c[j] > np.max(hi[s:r_end + 1]) or c[j] < np.min(lo[s:r_end + 1]):
                    prev_break = 1
                    break
            if prev_break or i > session_end - 12:
                continue
            rng_hi = np.max(hi[s:r_end + 1])
            rng_lo = np.min(lo[s:r_end + 1])
            width = rng_hi - rng_lo
            if width <= 0:
                continue
            if c[i] > rng_hi:
                out.append((i, 1, max(width, 0.5 * atr[i])))
            elif c[i] < rng_lo:
                out.append((i, -1, max(width, 0.5 * atr[i])))
    return out


# ---------------------------------------------------------------------- metrics
def metrics(trades: pd.DataFrame, df: pd.DataFrame, cost_bps_rt: float) -> dict:
    if trades.empty:
        return dict(n=0)
    t = trades.copy()
    t["r_net"] = t["r_gross"] - (cost_bps_rt / 1e4) / t["stop_dist_frac"]
    t["ret"] = RISK_FRAC * t["r_net"]
    t["exit_ts"] = df["ts"].to_numpy()[t["exit_i"].to_numpy()]

    eq = (1 + t.sort_values("exit_ts")["ret"]).cumprod()
    peak = eq.cummax()
    mdd = float((eq / peak - 1).min()) if len(eq) else 0.0

    by_day = t.groupby(t["exit_ts"].dt.floor("D"))["ret"].sum()
    days = pd.date_range(df["ts"].iloc[0].floor("D"), df["ts"].iloc[-1].floor("D"), freq="D")
    daily = by_day.reindex(days, fill_value=0.0)
    sd = daily.std(ddof=1)
    sharpe = float(daily.mean() / sd * math.sqrt(365)) if sd > 0 else 0.0
    downside = daily[daily < 0].std(ddof=1)
    sortino = float(daily.mean() / downside * math.sqrt(365)) if downside and downside > 0 else 0.0

    gp = t.loc[t["r_net"] > 0, "r_net"].sum()
    gl = -t.loc[t["r_net"] < 0, "r_net"].sum()
    years = (df["ts"].iloc[-1] - df["ts"].iloc[0]).days / 365.25
    cagr = float(eq.iloc[-1] ** (1 / years) - 1) if len(eq) else 0.0
    return dict(
        n=int(len(t)), win=float((t["r_net"] > 0).mean()),
        expectancy_r=float(t["r_net"].mean()), pf=float(gp / gl) if gl > 0 else float("inf"),
        mdd=mdd, sharpe=sharpe, sortino=sortino, cagr=cagr,
        calmar=float(cagr / abs(mdd)) if mdd < 0 else float("inf"),
        avg_win_r=float(t.loc[t["r_net"] > 0, "r_net"].mean()) if (t["r_net"] > 0).any() else 0.0,
        avg_loss_r=float(t.loc[t["r_net"] < 0, "r_net"].mean()) if (t["r_net"] < 0).any() else 0.0,
        hit_stop=float((t["reason"].isin(["stop", "gap_stop"])).mean()),
        hit_target=float((t["reason"] == "target").mean()),
        r_gross_mean=float(t["r_gross"].mean()),
    )


def cscv_pbo(perf: pd.DataFrame, s_blocks: int = 10) -> float:
    """Bailey et al. CSCV: probability that the IS-best config ranks below median OOS."""
    n_obs, n_cfg = perf.shape
    edges = np.linspace(0, n_obs, s_blocks + 1).astype(int)
    blocks = [perf.iloc[edges[i]:edges[i + 1]] for i in range(s_blocks)]
    logits = []
    half = s_blocks // 2
    for combo in combinations(range(s_blocks), half):
        is_idx = list(combo)
        oos_idx = [b for b in range(s_blocks) if b not in combo]
        is_df = pd.concat([blocks[b] for b in is_idx])
        oos_df = pd.concat([blocks[b] for b in oos_idx])
        is_perf = is_df.mean() / is_df.std(ddof=1).replace(0, np.nan)
        oos_perf = oos_df.mean() / oos_df.std(ddof=1).replace(0, np.nan)
        best = is_perf.idxmax()
        ranks = oos_perf.rank(method="average")
        w = ranks[best] / (n_cfg + 1)
        w = min(max(w, 1e-6), 1 - 1e-6)
        logits.append(math.log(w / (1 - w)))
    return float(np.mean(np.array(logits) < 0))


def deflated_sharpe(sr_ann: float, trials: list[float], years: float, skew: float, kurt: float) -> dict:
    """Bailey & Lopez de Prado (2014). SR values are annualized."""
    nd = NormalDist()
    n = len(trials)
    var_sr = float(np.var(trials, ddof=1))
    emc = 0.5772156649
    z = (1 - emc) * nd.inv_cdf(1 - 1 / n) + emc * nd.inv_cdf(1 - 1 / (n * math.e))
    sr0 = math.sqrt(var_sr) * z
    t_obs = years  # annualized SR -> t = SR * sqrt(years)
    denom = math.sqrt(max(1e-12, 1 - skew * sr_ann + (kurt - 1) / 4 * sr_ann ** 2))
    dsr = nd.cdf((sr_ann - sr0) * math.sqrt(t_obs) / denom)
    return dict(sr0_ann=sr0, dsr=dsr, trials=n, minbtl_years=2 * math.log(n) / max(sr_ann, 1e-9) ** 2)


# ------------------------------------------------------------------------- main
def main() -> None:
    df = load()
    span_is_end = int(len(df) * 0.60)
    span_oos_start = int(len(df) * 0.80)
    configs: list[dict] = []

    def add(name, family, trades, exits, params):
        configs.append(dict(name=name, family=family, trades=trades, exits=exits, params=params))

    for n in (48, 96, 192, 288, 576):
        tr = run_trades(df, trend_entries(df, n), Exit(1.5, 2.0, 288))
        add(f"trend_donchian_{n}", "trend", tr, Exit(1.5, 2.0, 288), dict(n=n))

    for fast, slow in (("ema12", "ema48"), ("ema24", "ema96"), ("ema48", "ema192")):
        tr = run_trades(df, momentum_entries(df, fast, slow), Exit(1.5, 2.0, 288))
        add(f"momentum_{fast}_{slow}", "momentum", tr, Exit(1.5, 2.0, 288), dict(fast=fast, slow=slow))

    for n in (48, 96, 192):
        tr = run_trades(df, meanrev_entries(df, n, 2.0, 2.0), Exit(2.0, 1.0, 48))
        add(f"meanrev_z2_{n}", "mean_rev", tr, Exit(2.0, 1.0, 48), dict(n=n))

    # wider, cost-tolerant variants: stop floor of 50bp / 100bp of price
    def floor_entries(entries, floor):
        c = df["close"].to_numpy()
        return [(i, side, max(dist, floor * c[i])) for i, side, dist in entries]

    add("trend_donchian_288_floor50bp", "trend", run_trades(df, floor_entries(trend_entries(df, 288), 0.005), Exit(1.5, 2.0, 288)), Exit(1.5, 2.0, 288), dict(n=288, floor=0.005))
    add("trend_donchian_576_floor100bp", "trend", run_trades(df, floor_entries(trend_entries(df, 576), 0.01), Exit(1.5, 2.0, 288)), Exit(1.5, 2.0, 288), dict(n=576, floor=0.01))
    add("orb_30min_floor100bp", "orb", run_trades(df, floor_entries(orb_entries(df, 6, ((8, 0), (13, 30))), 0.01), Exit(1.0, 2.0, 96)), Exit(1.0, 2.0, 96), dict(range_bars=6, floor=0.01))

    sessions = ((8, 0), (13, 30))
    for rb in (3, 6, 12):
        tr = run_trades(df, orb_entries(df, rb, sessions), Exit(1.0, 2.0, 96))
        add(f"orb_{rb * 5}min", "orb", tr, Exit(1.0, 2.0, 96), dict(range_bars=rb))

    cost_scenarios = {
        "gross_0bps": 0.0,
        "maker_2.07bps": 2.07 * 2,
        "taker_5.07bps": 5.07 * 2,
        "stress_7.6bps": 7.6 * 2,
    }

    # ---- same engine on higher timeframes (resampled from the same 5m data)
    high_tf = {}
    for label, rule in (("4h", "4h"), ("1d", "1D")):
        agg = df.set_index("ts").resample(rule, label="left", closed="left").agg(
            open=("open", "first"), high=("high", "max"), low=("low", "min"),
            close=("close", "last"), volume=("volume", "sum")).dropna().reset_index()
        agg["ts"] = pd.to_datetime(agg["ts"], utc=True)
        pc = agg["close"].shift(1)
        tr = pd.concat([agg.high - agg.low, (agg.high - pc).abs(), (agg.low - pc).abs()], axis=1).max(axis=1)
        agg["atr"] = tr.rolling(14).mean()
        rows = {}
        for n in ((6, 12, 24, 48) if label == "4h" else (10, 20, 40, 55, 100)):
            trd = run_trades(agg, trend_entries(agg, n), Exit(2.0, 4.0, 20 if label == "4h" else 90))
            for cost_label, cost in (("gross", 0.0), ("taker", 10.14)):
                m = metrics(trd, agg, cost)
                if m.get("n", 0):
                    rows[f"donchian_{n}_{cost_label}"] = m
        high_tf[label] = rows
        print(f"\n=== {label} Donchian (resampled) ===")
        print(pd.DataFrame(rows).T[["n", "win", "expectancy_r", "pf", "sharpe", "mdd"]].round(3).to_string())

    out_years = (df.ts.iloc[-1] - df.ts.iloc[0]).days / 365.25
    # ---- aggregate results per cost scenario
    out: dict[str, dict] = {}
    for label, c in cost_scenarios.items():
        rows = {}
        for cfg in configs:
            m = metrics(cfg["trades"], df, c)
            if m.get("n", 0) == 0:
                continue
            rows[cfg["name"]] = m
        out[label] = rows

    # ---- PBO / DSR on the realistic taker scenario, daily net returns per config
    daily = {}
    for cfg in configs:
        t = cfg["trades"]
        if t.empty:
            continue
        cost = cost_scenarios["taker_5.07bps"]
        r_net = t["r_gross"] - (cost / 1e4) / t["stop_dist_frac"]
        ret = RISK_FRAC * r_net
        ser = pd.Series(ret.to_numpy(), index=df["ts"].to_numpy()[t["exit_i"].to_numpy()])
        daily[cfg["name"]] = ser.groupby(pd.Series(ser.index).dt.floor("D").to_numpy()).sum()
    perf = pd.DataFrame(daily).fillna(0.0).sort_index()
    pbo = cscv_pbo(perf)
    taker_sr = {k: (v.mean() / v.std(ddof=1) * math.sqrt(365) if v.std(ddof=1) > 0 else 0.0)
                for k, v in perf.items()}
    best = max(taker_sr, key=taker_sr.get)
    best_ser = perf[best]
    yrs = len(perf) / 365.0
    if taker_sr[best] > 0:
        dsr = deflated_sharpe(
            sr_ann=taker_sr[best], trials=list(taker_sr.values()), years=yrs,
            skew=float(best_ser.skew()), kurt=float(best_ser.kurtosis() + 3),
        )
    else:
        dsr = dict(sr0_ann=float("nan"), dsr=0.0, trials=len(taker_sr), minbtl_years=float("nan"))

    out["pbo_cscv_taker"] = dict(pbo=pbo, n_configs=perf.shape[1], n_days=perf.shape[0])
    out["dsr_taker_best"] = dict(config=best, sr_ann=taker_sr[best], **dsr)
    bh = df["close"].to_numpy()
    bh_ret = pd.Series(bh).pct_change().fillna(0.0)
    bh_daily = bh_ret.groupby(df["ts"].dt.floor("D").to_numpy()).apply(lambda x: (1 + x).prod() - 1)
    bh_eq = (1 + bh_daily).cumprod()
    out["buy_and_hold"] = dict(
        cagr=float(bh_eq.iloc[-1] ** (365.25 / len(bh_daily)) - 1),
        sharpe=float(bh_daily.mean() / bh_daily.std(ddof=1) * math.sqrt(365)),
        mdd=float((bh_eq / bh_eq.cummax() - 1).min()),
        first=float(bh[0]), last=float(bh[-1]),
    )
    out["high_tf"] = high_tf
    out["cost_in_R"] = {
        cfg["name"]: dict(median_stop_frac=float(cfg["trades"]["stop_dist_frac"].median()),
                          median_cost_R_taker=float((0.001014 / cfg["trades"]["stop_dist_frac"]).median()),
                          per_year=float(len(cfg["trades"]) / out_years))
        for cfg in configs if not cfg["trades"].empty
    }
    out["data"] = dict(rows=int(len(df)), start=str(df.ts.iloc[0]), end=str(df.ts.iloc[-1]),
                       years=round((df.ts.iloc[-1] - df.ts.iloc[0]).days / 365.25, 3))
    (CACHE / "study_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    # ---- print
    pd.set_option("display.width", 200)
    print(f"DATA rows={len(df):,} {df.ts.iloc[0]} -> {df.ts.iloc[-1]} years={out['data']['years']}")
    for label in cost_scenarios:
        rows = out[label]
        tab = pd.DataFrame(rows).T[["n", "win", "expectancy_r", "pf", "sharpe", "mdd"]]
        print(f"\n=== {label} (round-trip cost {cost_scenarios[label]:.2f} bps) ===")
        print(tab.round(3).to_string())
        fam = {}
        for name, m in rows.items():
            fam.setdefault(name.split("_")[0], []).append(m["expectancy_r"])
        print("mean expectancy R by family:", {k: round(float(np.mean(v)), 4) for k, v in fam.items()})
    print("\nPBO (CSCV, taker):", round(pbo, 3), "configs", perf.shape[1], "days", perf.shape[0])
    print("DSR best:", json.dumps(out["dsr_taker_best"], indent=2))


if __name__ == "__main__":
    main()
