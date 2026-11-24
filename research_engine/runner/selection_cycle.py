"""Selection cycle for the 12 gates of PROMPT_V4 section 6.

The runner evaluates a single spec and leaves PBO, DSR, MinBTL and WFA as null
because they are properties of a *selection*, not of one backtest. This module
produces those four numbers from a declared universe of specs and writes
`runner/validation/<cycle>.json`, which the runner can then consume with
`--validation`.

What it computes, and how:

  PBO   Probability of Backtest Overfitting by CSCV (Bailey, Borwein,
        Lopez de Prado & Zhu, 2015): split the daily return matrix into S
        contiguous blocks, take every combination of S/2 blocks as in-sample,
        pick the config with the best in-sample Sharpe, and record its
        out-of-sample rank. PBO is the share of splits where that config lands
        at or below the OOS median (logit <= 0).

  DSR   Deflated Sharpe Ratio: the observed Sharpe is compared with the
        expected maximum Sharpe of N independent trials, then mapped through
        the skew/kurtosis-adjusted normal CDF.

  MinBTL Minimum Backtest Length: how many years of data are needed for the
        best Sharpe of N trials to be distinguishable from noise,
        ~2*ln(N)/SR_best^2.

  WFA   Walk-forward: K expanding windows. For each fold the config with the
        best in-sample profit factor is traded out-of-sample; the gate asks for
        at least 30 trades per fold.

Usage:
    python runner/selection_cycle.py                      # default universe
    python runner/selection_cycle.py --folds 5 --blocks 10
    python runner/selection_cycle.py --spec runner/specs/btc-trend-1d-donchian-40.json --neighbours 5
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import run_strategy as rs

ROOT = rs.ROOT
OUT_DIR = ROOT / "runner" / "validation"
BPS = 1e-4
TRADING_DAYS = 365.0  # crypto trades every day


# ------------------------------------------------------------------ statistics
def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Inverse normal CDF by bisection on erf. Accurate to ~1e-12, no scipy."""
    if not 0.0 < p < 1.0:
        return float("nan")
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def sharpe_daily(r: np.ndarray) -> float:
    r = np.asarray(r, dtype=float)
    if r.size < 3:
        return 0.0
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 0 else 0.0


def _sr_from_sums(s: np.ndarray, ss: np.ndarray, n: float) -> np.ndarray:
    """Daily Sharpe from running sums, vectorised over configs."""
    mean = s / n
    var = (ss - s * s / n) / (n - 1.0)
    var = np.maximum(var, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(var > 0, mean / np.sqrt(var), 0.0)
    return out


# ----------------------------------------------------------------------- PBO
def cscv_pbo(daily: pd.DataFrame, blocks: int = 10) -> dict:
    """Combinatorially Symmetric Cross-Validation PBO (CSCV)."""
    T, N = daily.shape
    if N < 3 or T < blocks * 4:
        return {"pbo": None, "reason": "universo o serie demasiado cortos", "n_splits": 0}

    b = T // blocks
    usable = b * blocks
    m = daily.to_numpy(dtype=float)[T - usable:]  # keep the most recent whole blocks
    m = m.reshape(blocks, b, N)

    blk_sum = m.sum(axis=1)                    # [S, N]
    blk_sq = (m * m).sum(axis=1)               # [S, N]
    blk_n = np.full(blocks, float(b))

    half = blocks // 2
    logits: list[float] = []
    ranks: list[float] = []
    chosen: list[str] = []
    cols = list(daily.columns)

    for combo in itertools.combinations(range(blocks), half):
        mask = np.zeros(blocks, dtype=bool)
        mask[list(combo)] = True
        n_is = float(blk_n[mask].sum())
        sr_is = _sr_from_sums(blk_sum[mask].sum(axis=0), blk_sq[mask].sum(axis=0), n_is)
        n_oos = float(blk_n[~mask].sum())
        sr_oos = _sr_from_sums(blk_sum[~mask].sum(axis=0), blk_sq[~mask].sum(axis=0), n_oos)

        best = int(np.argmax(sr_is))
        # rank 1 = worst, N = best, then omega in (0,1)
        rank = int((sr_oos <= sr_oos[best]).sum())
        omega = min(max(rank / (N + 1.0), 1e-6), 1 - 1e-6)
        logits.append(math.log(omega / (1 - omega)))
        ranks.append(rank / N)
        chosen.append(cols[best])

    logits_a = np.array(logits)
    pbo = float((logits_a <= 0).mean())
    return {
        "pbo": round(pbo, 4),
        "n_splits": len(logits),
        "blocks": blocks,
        "block_days": b,
        "median_logit": round(float(np.median(logits_a)), 4),
        "mean_oos_rank_pct": round(float(np.mean(ranks)), 4),
        "most_selected": pd.Series(chosen).value_counts().head(5).to_dict(),
        "method": "CSCV (Bailey et al. 2015), S=%d blocks, all C(S,S/2) splits" % blocks,
    }


def _psr_from(sr: float, n: int, skew: float, kurt: float, sr0: float) -> float | None:
    """Core PSR formula, shared by the deflated and the undeflated variants."""
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denom <= 0:
        return None
    return norm_cdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(denom))


def probabilistic_sharpe(returns: np.ndarray, sr0_daily: float = 0.0) -> dict:
    """Probabilistic Sharpe Ratio against a benchmark, without multiplicity.

    PSR(SR) is the probability that the true Sharpe exceeds `sr0_daily`, corrected
    for skew and fat tails but not for how many trials were run. Against zero it
    answers one question only: is there any skill at all, rather than noise.
    """
    r = np.asarray(returns, dtype=float)
    n = r.size
    if n < 30:
        return {"psr": None, "reason": "menos de 30 observaciones"}
    sr = sharpe_daily(r)
    s = pd.Series(r)
    skew = float(s.skew())
    kurt = float(s.kurt()) + 3.0
    psr = _psr_from(sr, n, skew, kurt, sr0_daily)
    if psr is None:
        return {"psr": None, "reason": "denominador no positivo (momentos degenerados)"}
    return {
        "psr": round(float(psr), 4),
        "sharpe_daily": round(sr, 4),
        "sharpe_annual": round(sr * math.sqrt(TRADING_DAYS), 4),
        "sr0_annual": round(sr0_daily * math.sqrt(TRADING_DAYS), 4),
        "observations": int(n),
        "method": "PSR (Bailey & Lopez de Prado 2012), sin ajuste por multiplicidad",
    }


# ---------------------------------------------------------------------- CPCV
def cpcv(daily: pd.DataFrame, blocks: int = 10, test_blocks: int = 2,
         purge: int = 1) -> dict:
    """Combinatorial Purged Cross-Validation over the search space.

    Every combination of `test_blocks` contiguous blocks is held out once, the
    best config is picked on the remaining blocks minus `purge` blocks adjacent to
    each test block (returns overlap across the boundary), and its rank is measured
    out of sample. It yields C(blocks, test_blocks) paths instead of the handful a
    walk-forward produces, and unlike CSCV the train/test split stays temporal.
    """
    T, N = daily.shape
    if N < 3 or T < blocks * 4:
        return {"paths": 0, "reason": "universo o serie demasiado cortos"}

    b = T // blocks
    usable = b * blocks
    m = daily.to_numpy(dtype=float)[T - usable:]
    m = m.reshape(blocks, b, N)
    blk_sum = m.sum(axis=1)
    blk_sq = (m * m).sum(axis=1)
    blk_n = np.full(blocks, float(b))

    oos_sr: list[float] = []
    oos_rank: list[float] = []
    chosen: list[str] = []
    cols = list(daily.columns)

    for test in itertools.combinations(range(blocks), test_blocks):
        test_set = set(test)
        # Purge: a block touching a test block shares overlapping return windows.
        banned = set(test_set)
        for t in test_set:
            for d in range(1, purge + 1):
                banned.add((t - d) % blocks)
                banned.add((t + d) % blocks)
        train = [i for i in range(blocks) if i not in banned]
        # Only require a usable training side. Demanding `blocks//2` blocks silently
        # dropped every path whose test blocks sit far apart (each test block bans
        # its own neighbours), so the reported share was measured on a biased subset.
        if len(train) < 2 or not test:
            continue

        n_is = float(blk_n[train].sum())
        sr_is = _sr_from_sums(blk_sum[train].sum(axis=0), blk_sq[train].sum(axis=0), n_is)
        idx = list(test)
        n_oos = float(blk_n[idx].sum())
        sr_oos_all = _sr_from_sums(blk_sum[idx].sum(axis=0), blk_sq[idx].sum(axis=0), n_oos)

        best = int(np.argmax(sr_is))
        s_oos = float(sr_oos_all[best])
        rank = int((sr_oos_all <= s_oos).sum()) / N
        oos_sr.append(s_oos)
        oos_rank.append(rank)
        chosen.append(cols[best])

    if not oos_sr:
        return {"paths": 0, "reason": "sin combinaciones válidas"}

    ranks = np.array(oos_rank)
    srs = np.array(oos_sr)
    # Same convention as the PBO: the selected config must beat the median of
    # its own out-of-sample field, otherwise the selection added no information.
    return {
        "paths": len(oos_sr),
        "blocks": blocks,
        "test_blocks": test_blocks,
        "purge_blocks": purge,
        "block_days": b,
        "share_below_median": round(float((ranks <= 0.5).mean()), 4),
        "mean_oos_rank_pct": round(float(ranks.mean()), 4),
        "mean_oos_sr_daily": round(float(srs.mean()), 5),
        "median_oos_sr_daily": round(float(np.median(srs)), 5),
        "share_negative_oos": round(float((srs < 0).mean()), 4),
        "most_selected": pd.Series(chosen).value_counts().head(5).to_dict(),
        "method": (f"CPCV (Lopez de Prado 2018), {blocks} bloques, {test_blocks} de test, "
                   f"purga {purge}"),
    }


# ----------------------------------------------------------------------- DSR
def deflated_sharpe(best_returns: np.ndarray, all_sr_daily: np.ndarray) -> dict:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).

    `all_sr_daily` are the daily Sharpes of the trials that constitute the
    selection. Their dispersion is the estimator of the variance of Sharpe
    ratios under the null, so the set has to be the actual search space: mixing
    families with opposite signs inflates it and makes the deflated ratio
    collapse by construction.
    """
    r = np.asarray(best_returns, dtype=float)
    n = r.size
    if n < 30:
        return {"dsr": None, "reason": "menos de 30 observaciones"}

    sr = sharpe_daily(r)
    var_sr = float(np.var(all_sr_daily, ddof=1)) if all_sr_daily.size > 1 else 0.0
    trials = float(all_sr_daily.size)
    gamma = 0.5772156649015329  # Euler-Mascheroni
    if var_sr <= 0 or trials < 2:
        return {"dsr": None, "reason": "sin dispersión entre trials"}
    sr0 = math.sqrt(var_sr) * ((1 - gamma) * norm_ppf(1 - 1 / trials)
                               + gamma * norm_ppf(1 - 1 / (trials * math.e)))

    s = pd.Series(r)
    skew = float(s.skew())
    kurt = float(s.kurt()) + 3.0  # pandas returns excess kurtosis
    psr = _psr_from(sr, n, skew, kurt, sr0)
    if psr is None:
        return {"dsr": None, "reason": "denominador no positivo (momentos degenerados)"}
    dsr = psr
    return {
        "dsr": round(float(dsr), 4),
        "sharpe_daily": round(sr, 4),
        "sharpe_annual": round(sr * math.sqrt(TRADING_DAYS), 4),
        "sr0_daily": round(sr0, 4),
        "sr0_annual": round(sr0 * math.sqrt(TRADING_DAYS), 4),
        "trials": int(trials),
        "skew": round(skew, 4),
        "kurtosis": round(kurt, 4),
        "observations": int(n),
    }


def min_backtest_length(n_trials: int, sr_annual: float) -> dict:
    """Minimum Backtest Length in years (Bailey et al. 2014)."""
    if not sr_annual or sr_annual <= 0:
        return {"minbtl_years": None, "reason": "Sharpe no positivo"}
    years = 2.0 * math.log(max(n_trials, 2)) / (sr_annual ** 2)
    return {"minbtl_years": round(years, 2), "n_trials": int(n_trials),
            "sr_annual": round(sr_annual, 4)}


# ----------------------------------------------------------------------- WFA
def walk_forward(trade_log: dict[str, pd.DataFrame], folds: int = 5,
                 min_is_trades: int = 3, warmup: float = 0.30) -> dict:
    """Expanding-window walk-forward over the same universe.

    The first `warmup` share of the sample is in-sample only, so every
    out-of-sample fold has history behind it and no fold is empty by design.
    """
    valid = [t for t in trade_log.values() if not t.empty]
    if not valid:
        return {"folds": [], "min_trades_per_fold": None}
    start = min(t["ts"].min() for t in valid)
    end = max(t["ts"].max() for t in valid)
    first_oos = start + (end - start) * warmup
    edges = pd.date_range(first_oos, end, periods=folds + 1)

    out = []
    oos_all: list[pd.DataFrame] = []
    for k in range(folds):
        lo, hi = edges[k], edges[k + 1]
        best, best_pf, best_n = None, -1.0, 0
        for name, t in trade_log.items():
            is_t = t[t["ts"] < lo]
            if len(is_t) < min_is_trades:
                continue
            v = rs.pf(is_t["r_net"].to_numpy())
            if v > best_pf:
                best, best_pf, best_n = name, v, len(is_t)
        if best is None:
            out.append({"fold": k + 1, "is_end": str(lo.date()), "oos": [str(lo.date()), str(hi.date())],
                        "chosen": None, "oos_trades": 0, "oos_pf": None, "is_pf": None})
            continue
        oos_t = trade_log[best][(trade_log[best]["ts"] >= lo) & (trade_log[best]["ts"] < hi)]
        if not oos_t.empty:
            oos_all.append(oos_t)
        out.append({
            "fold": k + 1,
            "is_end": str(lo.date()),
            "oos": [str(lo.date()), str(hi.date())],
            "chosen": best,
            "is_trades": best_n,
            "is_pf": round(float(best_pf), 4),
            "oos_trades": int(len(oos_t)),
            "oos_pf": round(float(rs.pf(oos_t["r_net"].to_numpy())), 4) if not oos_t.empty else None,
        })

    counts = [f["oos_trades"] for f in out if f["chosen"]]
    agg = pd.concat(oos_all, ignore_index=True) if oos_all else pd.DataFrame(columns=["r_net"])
    return {
        "folds": out,
        "folds_requested": folds,
        "warmup_share": warmup,
        "evaluated_folds": len(counts),
        "min_trades_per_fold": int(min(counts)) if counts else 0,
        "total_oos_trades": int(sum(counts)),
        "oos_pf_aggregate": round(float(rs.pf(agg["r_net"].to_numpy())), 4) if len(agg) else None,
        "distinct_configs_chosen": len({f["chosen"] for f in out if f["chosen"]}),
    }


# ------------------------------------------------------------------- universe
def neighbour_specs(spec: dict, param: str, values: list[float]) -> list[dict]:
    """Clone a spec along one parameter axis (the axis the researcher tuned)."""
    out = []
    for v in values:
        s = json.loads(json.dumps(spec))
        nb = int(round(float(s["params"][param]) * v))
        nb = max(nb, 3)
        s["params"][param] = nb
        s["label"] = f"{s.get('label', spec['id'].lower())}_{param}{nb}"
        s["version"] = spec["version"]
        s["_variant"] = f"{param}={nb}"
        out.append(s)
    return out


DEFAULT_UNIVERSE = [
    ("runner/specs/btc-trend-1d-donchian-40.json", "N", [0.5, 0.7, 1.0, 1.4, 2.0]),
    ("runner/specs/btc-trend-4h-donchian-24.json", "N", [0.5, 0.7, 1.0, 1.4, 2.0]),
    ("runner/specs/btc-mom-5m-ema-12-48.json", "slow", [0.5, 0.7, 1.0, 1.4, 2.0]),
]


def registry_universe(db: Path) -> list[dict]:
    """Every configuration the researcher actually evaluated, taken from the registry.

    The PBO must count the whole search space. Simulating a neighbourhood of three
    reference specs understates the selection if the researcher also looked at other
    families (5m momentum, mean reversion, opening range). These are the 19 runs that
    produced a verdict in the registry, rebuilt as executable specs.
    """
    import verify_registry as vr  # noqa: PLC0415  (same directory, imported lazily)

    rows = vr.load_rows(db, None)
    universe = []
    seen: dict[str, int] = {}
    for row in rows:
        spec = vr.spec_from_run(row)
        label = row["id"].split("-v")[0].split("BTC-", 1)[-1]
        short = row["id"].split("-v")[-1].split("-", 1)[-1]
        spec["id"] = row["strategy_id"] + " / " + short
        name = f"{label}_{short}"
        # Three versions of the same variant can share a label. The registry is
        # append-only, so the disambiguation happens here, in the view: a label is
        # what identifies a row in a table, and two identical rows cannot be told
        # apart in a table.
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            name = f"{name}_v{seen[name]}"
        spec["label"] = name
        spec["version"] = "1.0.0"
        spec["_variant"] = "registrada"
        spec["_group"] = row["strategy_id"]
        universe.append(spec)
    return universe


def run_universe(universe: list[dict], df5: pd.DataFrame, quiet: bool = False) -> tuple[dict, dict]:
    """Backtest every spec once; return a daily return matrix and a trade log."""
    daily: dict[str, pd.Series] = {}
    trade_log: dict[str, pd.DataFrame] = {}
    summary = []

    for spec in universe:
        name = spec["label"]
        tf = spec["timeframe_signal"]
        bars, _ = rs.bars_for(df5, tf)
        fund = rs.fs.load_funding() if spec["costs"]["funding"] == "real_timestamps" else None
        entries = rs.build_entries(bars, spec)
        trades = rs.run_trades(bars, entries, spec)
        if trades.empty:
            if not quiet:
                print(f"  {name:26s} sin trades")
            continue

        fee_rt = 2 * (spec["costs"]["fee_taker_bps"] + spec["costs"]["half_spread_bps"])
        fund_r = rs.funding_in(spec, trades, bars, fund)
        d = trades["stop_dist_frac"].to_numpy()
        r_net = trades["r_gross"].to_numpy() - (fee_rt * BPS) / d - fund_r

        ts = pd.to_datetime(bars["ts"].iloc[trades["exit_i"].to_numpy()].to_numpy(), utc=True)
        log = pd.DataFrame({"ts": ts, "r_net": r_net}).reset_index(drop=True)
        trade_log[name] = log

        by_day = log.set_index("ts")["r_net"].groupby(level=0).sum()
        daily[name] = by_day.resample("D").sum()

        summary.append({
            "name": name, "spec_id": spec["id"], "timeframe": tf,
            "variant": spec.get("_variant"),
            "trades": int(len(log)),
            "pf_net": round(float(rs.pf(r_net)), 4),
            "exp_r": round(float(r_net.mean()), 4),
            "days": int(by_day.size),
        })
        if not quiet:
            print(f"  {name:26s} {len(log):6d} trades  PF {summary[-1]['pf_net']:.3f}  "
                  f"exp {summary[-1]['exp_r']:+.3f} R")

    matrix = pd.DataFrame(daily).fillna(0.0).sort_index()
    return {"matrix": matrix, "trades": trade_log, "summary": summary}, {"universe": summary}


# ----------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="Selection cycle: PBO, DSR, MinBTL, WFA")
    ap.add_argument("--cycle", default="CYCLE-2026-11")
    ap.add_argument("--blocks", type=int, default=10, help="CSCV blocks S (even)")
    ap.add_argument("--folds", type=int, default=5, help="walk-forward folds")
    ap.add_argument("--test-blocks", type=int, default=2, help="CPCV blocks held out per path")
    ap.add_argument("--param", default=None, help="tune only one axis of a single spec")
    ap.add_argument("--spec", type=Path, default=None, help="single base spec for the universe")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--from-registry", action="store_true",
                    help="use every registered configuration as the search space "
                         "(19 runs) instead of parametric neighbourhoods")
    ap.add_argument("--db", type=Path, default=ROOT / "app" / "registry.db")
    ap.add_argument("--register", default=None,
                    help="registry base URL (POST /api/cycles); refused if the artifact disagrees")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    df5, data = rs.load_data()
    print(f"dataset {data['sha256'][:16]} · {len(df5)} barras 5m")

    universe: list[dict] = []
    if args.from_registry:
        universe = registry_universe(args.db)
        print(f"universo: {len(universe)} configuraciones registradas (espacio real de búsqueda)")
    elif args.spec:
        base = json.loads(args.spec.read_text(encoding="utf-8"))
        axis = args.param or "N"
        universe = neighbour_specs(base, axis, [0.5, 0.7, 1.0, 1.4, 2.0])
    else:
        for rel, axis, values in DEFAULT_UNIVERSE:
            base = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            universe.extend(neighbour_specs(base, axis, values))

    if not args.from_registry:
        print(f"universo: {len(universe)} configuraciones")
    res, meta = run_universe(universe, df5, quiet=args.quiet)
    matrix, trade_log, summary = res["matrix"], res["trades"], res["summary"]

    if matrix.empty or matrix.shape[1] < 3:
        raise SystemExit("universo insuficiente: se necesitan al menos 3 configuraciones con trades")

    print(f"matriz diaria {matrix.shape[0]} días × {matrix.shape[1]} configuraciones")

    pbo = cscv_pbo(matrix, blocks=args.blocks)
    sr_daily = {c: sharpe_daily(matrix[c].to_numpy()) for c in matrix.columns}
    best = max(sr_daily, key=sr_daily.get)

    # DSR per search space: the variants of one hypothesis is the selection the
    # researcher actually ran. The pooled figure is reported for context only.
    # A registry universe groups by strategy_id (`_group`), not by run id, so
    # each hypothesis keeps the number of trials it really had.
    groups: dict[str, list[str]] = {}
    for spec in universe:
        groups.setdefault(spec.get("_group") or spec["id"], []).append(spec["label"])
    dsr_by_group = {}
    for sid, names in groups.items():
        present = [n for n in names if n in matrix.columns]
        if len(present) < 2:
            continue
        srs = np.array([sr_daily[n] for n in present])
        top = present[int(np.argmax(srs))]
        d = deflated_sharpe(matrix[top].to_numpy(), srs)
        d["config"] = top
        d["trials"] = len(present)
        dsr_by_group[sid] = d

    dsr = deflated_sharpe(matrix[best].to_numpy(), np.array(list(sr_daily.values())))
    dsr_pooled = dict(dsr)
    best_group = next((s.get("_group") or s["id"] for s in universe if s["label"] == best), None)
    if best_group and best_group in dsr_by_group:
        dsr = dict(dsr_by_group[best_group])
        dsr["source"] = f"grupo {best_group}"
    else:
        dsr["source"] = "universo completo"

    mbtl = min_backtest_length(len(matrix.columns), dsr.get("sharpe_annual") or 0.0)
    wfa = walk_forward(trade_log, folds=args.folds)
    cp = cpcv(matrix, blocks=args.blocks, test_blocks=args.test_blocks)
    psr = probabilistic_sharpe(matrix[best].to_numpy())

    years = matrix.index.to_series().diff().dt.days.sum() / 365.25
    payload = {
        "cycle_id": args.cycle,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method_version": "1.0.0",
        "inputs": {
            "data_hash": data["sha256"][:16],
            "specs_hash": "sha256:" + rs.canonical_hash([{k: v for k, v in s.items() if k != "_variant"}
                                                         for s in universe]),
            "universe_size": len(summary),
            "daily_observations": int(matrix.shape[0]),
            "coverage_years": round(float(years), 2),
        },
        "universe": summary,
        "pbo": pbo,
        "dsr": dsr,
        "dsr_pooled": dsr_pooled,
        "dsr_by_group": dsr_by_group,
        "dsr_config": best,
        "minbtl": mbtl,
        "wfa": wfa,
        "cpcv": cp,
        "psr": psr,
        "caveats": [
            "PBO y DSR son propiedades de este universo, no de una configuración suelta.",
            "El DSR de la puerta se calcula dentro del grupo de variantes de cada "
            "hipótesis (el espacio de búsqueda real); el valor agrupado se incluye "
            "solo como contexto y suele ser más severo porque suma familias con "
            "signo opuesto.",
            "El universo son vecindades paramétricas de las specs de referencia: si el "
            "investigador probó otras variantes fuera de esta lista, el PBO real es peor.",
            "WFA elige de nuevo en cada fold, así que mide el procedimiento de selección, "
            "no la config ganadora del ciclo.",
            "El PSR se reporta contra cero y sin deflactar: mide si hay habilidad, no si "
            "sobrevive a la multiplicidad. Por construcción es mayor que el DSR; no "
            "sustituye a la puerta.",
            "La puerta de meseta (±20%) es un heurístico, no un test calibrado: la "
            "literatura reciente encuentra que la geometría de la meseta es un diagnóstico "
            "débil frente al PSR (Plateaus, Peaks and the PBO, 2025).",
        ],
    }

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.cycle}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def f(v, n=3):
        return "—" if v is None else f"{v:.{n}f}".replace(".", ",")

    print()
    print(f"PBO     {f(pbo.get('pbo'))}  (≤ 0,20)  · {pbo.get('n_splits')} particiones, "
          f"{pbo.get('blocks')} bloques")
    print(f"DSR     {f(dsr.get('dsr'))}  (≥ 0,95)  · {dsr.get('source')}: mejor SR anual "
          f"{f(dsr.get('sharpe_annual'), 2)} vs SR0 {f(dsr.get('sr0_annual'), 2)} en "
          f"{dsr.get('trials')} trials")
    print(f"MinBTL  {f(mbtl.get('minbtl_years'), 1)} años (≤ {f(years, 1)} disponibles)")
    print(f"WFA     {wfa.get('min_trades_per_fold')} trades/fold mínimo "
          f"({wfa.get('total_oos_trades')} OOS en {args.folds} folds, "
          f"PF agregado {f(wfa.get('oos_pf_aggregate'))})")
    print(f"CPCV    {cp.get('paths')} caminos · elegido bajo la mediana OOS en "
          f"{f(cp.get('share_below_median'))} de ellos · SR OOS medio "
          f"{f(cp.get('mean_oos_sr_daily'), 4)}/día")
    print(f"PSR     {f(psr.get('psr'))} contra cero (sin deflactar; SR anual "
          f"{f(psr.get('sharpe_annual'), 2)})  ·  DSR {f(dsr.get('dsr'))} con {dsr.get('trials')} trials")
    try:
        shown = path.relative_to(ROOT)
    except ValueError:
        shown = path
    print(f"\nvalidation  {shown}")

    if args.register:
        reg = {
            "id": args.cycle, "name": "Ciclo " + args.cycle.split("-")[-1] + " · selección 3 familias",
            "pbo": pbo.get("pbo"), "dsr": dsr.get("dsr"),
            "minbtl_years": mbtl.get("minbtl_years"),
            "coverage_years": round(float(years), 2),
            "sr_best": dsr.get("sharpe_annual"), "sr0": dsr.get("sr0_annual"),
            "trials": dsr.get("trials"), "wfa_min_trades": wfa.get("min_trades_per_fold"),
            "wfa_folds": wfa.get("evaluated_folds"),
            "wfa_total_trades": wfa.get("total_oos_trades"),
            "validation_ref": shown.as_posix() if isinstance(shown, Path) else str(shown),
            "actor": "runner",
            "notes": (f"universo {len(summary)} configs · PBO CSCV {pbo.get('n_splits')} particiones · "
                      f"DSR sobre {dsr.get('source')} · WFA {wfa.get('evaluated_folds')} folds "
                      f"con warmup {wfa.get('warmup_share')}"),
        }
        body = json.dumps(reg).encode("utf-8")
        req = urllib.request.Request(f"{args.register.rstrip('/')}/api/cycles", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                print("registro:", resp.status, json.loads(resp.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            print("registro rechazado:", exc.code, exc.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            print("registro fallido:", exc)


if __name__ == "__main__":
    main()
