"""Selection cycle for the 12 gates — PBO, DSR, MinBTL, WFA.

This module implements the four statistical gates that the deterministic runner
cannot compute from a single backtest because they are properties of a
*selection*, not of one configuration. The runner evaluates one spec and leaves
PBO, DSR, MinBTL, WFA as null; this module produces those four numbers from a
declared universe of specs and writes `data/validation/<cycle>.json`, which
the runner (and the backtest) can then consume.

What it computes, and how:

  PBO   Probability of Backtest Overfitting by CSCV (Bailey, Borwein,
        Lopez de Prado & Zhu, 2015): split the daily return matrix into S
        contiguous blocks, take every combination of S/2 blocks as in-sample,
        pick the config with the best in-sample Sharpe, and record its
        out-of-sample rank. PBO is the share of splits where that config lands
        at or below the OOS median (logit <= 0).

  DSR   Deflated Sharpe Ratio: the observed Sharpe is compared with the
        expected maximum Sharpe of N independent trials, then mapped through
        the skew/kurtosis-adjusted normal CDF. Computed per search-space group.

  MinBTL Minimum Backtest Length: how many years of data are needed for the
        best Sharpe of N trials to be distinguishable from noise,
        ~2*ln(N)/SR_best^2.

  WFA   Walk-forward: K expanding windows. For each fold the config with the
        best in-sample profit factor is traded out-of-sample; the gate asks for
        at least 30 trades per fold.

Usage (as CLI):
    python -m server.selection --cycle CYCLE-2026-11 --blocks 10 --folds 5
    python -m server.selection --cycle CYCLE-2025 --from 2025-01-01 --to 2026-01-01
    python -m server.selection --cycle CYCLE-2026-11 --from-registry --db data/terminal.db

Usage (as library):
    from server.selection import run_selection_cycle
    result = run_selection_cycle(cycle_id="CYCLE-2026-11", blocks=10, folds=5)
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Reuse the runner's backtest logic
from .strategy.spec_schema import StrategySpec
from .strategy import registry
from .strategy.registry import load_spec_file
from .config import Settings, InstrumentConfig, SessionTemplate, load_settings

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "validation"
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
    # n puede ser 1 en una partición degenerada: el aviso de numpy no aporta
    # nada y ensuciaría el log del ciclo.
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = s / n
        var = (ss - s * s / n) / (n - 1.0)
        var = np.maximum(var, 0.0)
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
            v = pf(is_t["r_net"].to_numpy())
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
            "oos_pf": round(float(pf(oos_t["r_net"].to_numpy())), 4) if not oos_t.empty else None,
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
        "oos_pf_aggregate": round(float(pf(agg["r_net"].to_numpy())), 4) if len(agg) else None,
        "distinct_configs_chosen": len({f["chosen"] for f in out if f["chosen"]}),
    }


# ----------------------------------------------------------------------- PF helper

def pf(x: np.ndarray) -> float:
    gp = x[x > 0].sum()
    gl = -x[x < 0].sum()
    return float(gp / gl) if gl > 0 else float("inf")


# ----------------------------------------------------------------------- CPCV

def cpcv(daily: pd.DataFrame, blocks: int = 10, test_blocks: int = 2,
         purge: int = 1) -> dict:
    """Combinatorial Purged Cross-Validation over the search space."""
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
        banned = set(test_set)
        for t in test_set:
            for d in range(1, purge + 1):
                banned.add((t - d) % blocks)
                banned.add((t + d) % blocks)
        train = [i for i in range(blocks) if i not in banned]
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
        "method": f"CPCV (Lopez de Prado 2018), {blocks} bloques, {test_blocks} de test, purga {purge}",
    }


# ----------------------------------------------------------------------- PSR

def probabilistic_sharpe(returns: np.ndarray, sr0_daily: float = 0.0) -> dict:
    """Probabilistic Sharpe Ratio against a benchmark, without multiplicity."""
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


# ------------------------------------------------------------------- universe

DEFAULT_UNIVERSE_SPECS = [
    "BTC-TREND-1D",
    "BTC-TREND-4H",
    "BTC-MOM-5M",
]


def load_universe_specs(
    spec_dir: Path, all_specs: bool = False
) -> list[StrategySpec]:
    """Load the default universe, or every JSON in `spec_dir` with `all_specs`."""
    if all_specs:
        paths = sorted(spec_dir.glob("*.json"))
    else:
        paths = [spec_dir / f"{spec_id}.json" for spec_id in DEFAULT_UNIVERSE_SPECS]
    specs = []
    for spec_path in paths:
        if spec_path.exists():
            spec = load_spec_file(spec_path)
            # El motor resuelve la estrategia por id: sin registrar la spec, el
            # backtest responde ERROR y el ciclo no mide nada.
            registry.register_spec(spec.id, spec_path)
            specs.append(spec)
        elif not all_specs:
            print(f"Warning: spec {spec_path.stem} not found at {spec_path}")
    return specs


def run_universe(specs: list[StrategySpec], df5: pd.DataFrame, quiet: bool = False) -> tuple[dict, dict]:
    """Backtest every spec once; return a daily return matrix and a trade log."""
    daily: dict[str, pd.Series] = {}
    trade_log: dict[str, pd.DataFrame] = {}
    summary = []

    for spec in specs:
        name = spec.label
        # El motor determinista es el mismo que mide el terminal; antes se le
        # pasaba el DataFrame a `run_backtest`, que espera una ruta y reventaba.
        trade_df, _equity, metrics = run_backtest_for_spec(spec, df5, quiet=quiet)
        if trade_df.empty:
            if not quiet:
                print(f"  {name:26s} sin trades")
            continue

        trade_log[name] = trade_df
        daily[name] = trade_df.groupby(trade_df["ts"].dt.date)["r_net"].sum()
        closed = metrics.get("closed", {})
        summary.append({
            "name": name,
            "spec_id": spec.id,
            "timeframe": spec.timeframe_signal,
            "trades": closed.get("trades", 0),
            "pf_net": closed.get("profit_factor", 0.0),
            "exp_r": closed.get("expectancy_r", 0.0),
            "days": int(daily[name].size),
        })

    matrix = pd.DataFrame(daily).fillna(0.0).sort_index()
    return {"matrix": matrix, "trades": trade_log, "summary": summary}, {"universe": summary}


# Simplified helper - full implementation would use the actual backtest
def bars_for(df5: pd.DataFrame, tf: str) -> tuple[pd.DataFrame, str]:
    """Resample the frozen 5m series to the signal timeframe (no new data)."""
    if tf == "5m":
        return df5, "5m (native)"
    rule = tf
    # Simplified resample
    bars = df5.resample(rule).agg({
        "o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"
    }).dropna()
    return bars, "resampled from 5m"


# ----------------------------------------------------------------------- backtest execution

def run_backtest_for_spec(
    spec: StrategySpec,
    df5: pd.DataFrame,
    quiet: bool = False,
    base: Settings | None = None,
    cost_multiplier: float = 1.0,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, list, dict]:
    """Run backtest for a single spec using the deterministic engine.

    Con `base`, mandan los límites y costes del perfil; la spec solo aporta la
    estrategia y sus parámetros. Sin `base` se usan los límites de investigación.
    Con `cost_multiplier` se re-ejecuta el mismo backtest con comisión, fees,
    medio spread y slippage multiplicados (el estrés de costes).

    Returns (trades_df, equity_curve, metrics_dict) or (empty_df, [], {}) if no trades.
    """
    from .backtest import run_backtest

    tf = spec.timeframe_signal
    name = spec.label

    # Build settings from spec
    settings = Settings()
    settings.strategy.id = spec.id
    settings.strategy.timeframe = tf
    settings.strategy.timeframe_signal = tf
    settings.strategy.params = spec.params.model_dump(exclude_none=True)

    # Copy execution config from spec
    spec_exec = spec.execution if hasattr(spec, "execution") else None
    if spec_exec:
        settings.execution.commission_per_unit_side = 0.0
        settings.execution.commission_pct_side = 0.0
        settings.execution.slippage_ticks = 1
        settings.execution.max_slippage_ticks = 4
        settings.execution.fill_model = spec_exec.fill if hasattr(spec_exec, "fill") else "next_open"
        settings.execution.simulate_partial_fills = False
        settings.execution.partial_fill_ratio = 0.6
        settings.execution.fee_maker_bps = 2.0
        settings.execution.fee_taker_bps = 5.0
        settings.execution.half_spread_bps = 0.07
        settings.execution.assumed_fill = "taker"
        settings.execution.impact_model = "none"
        settings.execution.funding = "none"
        settings.execution.cooldown_bars = spec.entry.cooldown_bars if hasattr(spec.entry, "cooldown_bars") else 0
        settings.execution.stop_floor_frac = 0.0
    else:
        settings.execution = Settings().execution

    # Copy costs from spec
    spec_costs = spec.costs if hasattr(spec, "costs") else None
    if spec_costs:
        cost_dict = spec_costs.model_dump(exclude_none=True)
        settings.execution.fee_maker_bps = cost_dict.get("fee_maker_bps", 2.0)
        settings.execution.fee_taker_bps = cost_dict.get("fee_taker_bps", 5.0)
        settings.execution.half_spread_bps = cost_dict.get("half_spread_bps", 0.07)
        settings.execution.assumed_fill = cost_dict.get("assumed_fill", "taker")
        settings.execution.impact_model = cost_dict.get("impact_model", "none")
        settings.execution.funding = cost_dict.get("funding", "none")

    # Convert spec risk to Settings RiskConfig format
    spec_risk = spec.risk if hasattr(spec, "risk") else None
    if spec_risk:
        risk_dict = spec_risk.model_dump(exclude_none=True)
        # Map spec risk fields to Settings risk fields
        settings.risk.initial_capital = 250000.0
        settings.risk.risk_per_trade_pct = risk_dict.get("risk_per_trade", 0.005) * 100  # fraction to pct
        settings.risk.max_daily_loss_pct = 3.0
        settings.risk.max_daily_profit_pct = 0.0
        settings.risk.max_drawdown_pct = risk_dict.get("max_mdd_budget", 0.0) * 100
        settings.risk.max_trades_per_day = 3
        settings.risk.max_concurrent_positions = 1
        settings.risk.max_units_per_trade = 5
        settings.risk.max_stop_ticks = 10000
        settings.risk.min_stop_ticks = 0
        settings.risk.trade_window_start = "00:00"
        settings.risk.trade_window_end = "23:59"
        settings.risk.close_at_session_end = False
        settings.risk.session_close_time = "23:59"
        settings.risk.cooldown_minutes = 0
        settings.risk.no_trade_after_consecutive_losses = 0
        settings.risk.loss_streak_cooldown_min = 0
        settings.risk.soft_brakes = False
        settings.risk.soft_brake_floor = 0.25
        settings.risk.soft_brake_halt_multiple = 2.0
        settings.risk.sizing = risk_dict.get("sizing", "fixed_fractional")
        settings.risk.target_vol_annual = risk_dict.get("target_vol_annual")
        settings.risk.max_gross_leverage = risk_dict.get("max_gross_leverage")
        settings.risk.max_mdd_budget = risk_dict.get("max_mdd_budget", 0.0)
    else:
        settings.risk = Settings().risk

    settings.feed.provider = "csv"
    settings.instruments.primary = spec.instrument
    settings.instruments.items = [InstrumentConfig(
        symbol=spec.instrument,
        role="primary",
        enabled=True,
        tick_size=0.25,
        tick_value=0.5,
        lot_size=1,
        currency="USD",
        decimals=2,
        session_template="24h"
    )]
    settings.instruments.templates = [
        SessionTemplate(name='RTH', timezone='America/New_York', open='09:30', close='16:00', weekdays=[0,1,2,3,4]),
        SessionTemplate(name='24h', timezone='UTC', open='00:00', close='23:59', weekdays=[0,1,2,3,4,5,6])
    ]

    if base is not None:
        # Los límites del perfil mandan: capital, riesgo por operación, topes de
        # unidades, stop, operaciones/día, drawdown y costes reales. De la spec
        # solo salen la estrategia y el símbolo que casa con el CSV.
        settings = base.model_copy(deep=True)
        settings.strategy.id = spec.id
        settings.strategy.timeframe = tf
        settings.strategy.timeframe_signal = tf
        settings.strategy.params = spec.params.model_dump(exclude_none=True)
        primary = next(
            (
                item
                for item in settings.instruments.items
                if item.symbol == settings.instruments.primary
            ),
            None,
        )
        if primary is None:
            raise ValueError("el perfil no declara el instrumento primario")
        item = primary.model_copy(deep=True)
        item.symbol = spec.instrument
        settings.instruments.items = [item]
        settings.instruments.primary = item.symbol

    if cost_multiplier != 1.0:
        from .stress import stressed_settings

        settings = stressed_settings(settings, cost_multiplier)

    # Write df5 to a temporary CSV for the backtest
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        df5.to_csv(f.name, index=False)
        csv_path = f.name

    try:
        settings.feed.provider = "csv"
        settings.feed.csv_path = csv_path

        # Run backtest using the existing backtest module
        result = run_backtest(settings, csv_path)
        trades = result.trades
        if not trades:
            return pd.DataFrame(), [], {}

        # Mismo agregado que el CLI: los consumidores leen `metrics["closed"]`.
        from .stats import aggregate
        metrics = aggregate(
            trades, settings.risk.initial_capital, timezone_name="UTC"
        )

        # Build trade log DataFrame
        trade_rows = []
        for trade in trades:
            trade_rows.append({
                "ts": trade.closed_ts,
                "r_net": trade.pnl_net / (settings.risk.initial_capital * settings.risk.risk_per_trade_pct / 100) if trade.pnl_net else 0.0,
                "r_gross": trade.pnl_gross / (settings.risk.initial_capital * settings.risk.risk_per_trade_pct / 100) if trade.pnl_gross else 0.0,
                "symbol": trade.symbol,
                "side": trade.side,
                "pnl_net": trade.pnl_net,
                "pnl_gross": trade.pnl_gross,
            })

        trade_df = pd.DataFrame(trade_rows)
        if trade_df.empty:
            return pd.DataFrame(), [], {}

        trade_df["ts"] = pd.to_datetime(trade_df["ts"], utc=True)
        trade_df = trade_df.sort_values("ts").reset_index(drop=True)

        return trade_df, result.equity, metrics

    except Exception as e:
        if diagnostics is not None:
            diagnostics["error"] = str(e)
        if not quiet:
            print(f"  {name:26s} ERROR: {e}")
        return pd.DataFrame(), [], {}
    finally:
        # Clean up temp file
        import os
        try:
            os.unlink(csv_path)
        except OSError:
            # El temporal ya no está (o nunca llegó a escribirse): limpiar no
            # puede tumbar el ciclo.
            pass


def _iso_day(value: str) -> datetime:
    """Fecha ISO del CLI; sin zona se asume UTC, como el resto del motor."""
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _window(
    df: pd.DataFrame, start: datetime | None, end: datetime | None
) -> pd.DataFrame:
    """Recorta el dataset congelado a [start, end); sin fechas, no toca nada."""
    if start is None and end is None:
        return df
    stamps = pd.to_datetime(df["ts"], utc=True)
    keep = pd.Series(True, index=df.index)
    if start is not None:
        keep &= stamps >= start
    if end is not None:
        keep &= stamps < end
    return df.loc[keep].reset_index(drop=True)


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _spec_sources(spec_dir: Path, root: Path) -> dict[str, str]:
    """Map label -> source file so the ledger can cite the exact spec."""
    sources: dict[str, str] = {}
    for path in sorted(spec_dir.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        label = document.get("label") if isinstance(document, dict) else None
        if isinstance(label, str) and label:
            sources[label] = _relative_path(path, root)
    return sources


def _validation_value(spec: Any, key: str) -> Any:
    validation = getattr(spec, "validation", None)
    if isinstance(validation, dict):
        return validation.get(key)
    return getattr(validation, key, None)


def _spec_payload(spec: Any, source: str | None) -> dict[str, Any]:
    try:
        document = spec.model_dump(mode="json")
    except Exception:
        document = {}
    fingerprint = getattr(spec, "spec_hash", None)
    if not isinstance(fingerprint, str):
        fingerprint = "sha256:" + hashlib.sha256(
            json.dumps(document, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    return {
        "id": getattr(spec, "id", None),
        "label": getattr(spec, "label", None),
        "version": getattr(spec, "version", None),
        "family": getattr(spec, "family", None),
        "timeframe": getattr(spec, "timeframe_signal", None),
        "group": getattr(spec, "_group", None) or getattr(spec, "id", None),
        "seed": _validation_value(spec, "seed"),
        "trials_declared": _validation_value(spec, "trials_declared"),
        "source": source,
        "fingerprint": fingerprint,
        "document": document,
    }


def _dataset_payload(
    root: Path,
    source: Path,
    df5: pd.DataFrame,
    start: datetime | None,
    end: datetime | None,
) -> dict[str, Any]:
    try:
        file_hash = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError:
        file_hash = None
    stamps = pd.Series(
        pd.to_datetime(df5["ts"] if "ts" in df5.columns else df5.index, utc=True)
    )
    return {
        "path": _relative_path(source, root),
        "sha256": file_hash,
        "rows": int(len(df5)),
        "columns": [str(column) for column in df5.columns],
        "first_ts": stamps.iloc[0].isoformat() if len(stamps) else None,
        "last_ts": stamps.iloc[-1].isoformat() if len(stamps) else None,
        "window": {
            "from": start.isoformat() if start is not None else None,
            "to": end.isoformat() if end is not None else None,
        },
    }


def _daily_points(series: pd.Series) -> list[dict[str, Any]]:
    return [
        {"date": str(day), "r_net": float(value)}
        for day, value in series.sort_index().items()
    ]


def run_selection_cycle(
    cycle_id: str = "CYCLE-2026-11",
    blocks: int = 10,
    folds: int = 5,
    test_blocks: int = 2,
    purge: int = 1,
    spec_dir: Path | None = None,
    quiet: bool = False,
    start: datetime | None = None,
    end: datetime | None = None,
    base_settings: Settings | None = None,
    all_specs: bool = False,
    stress_multiplier: float = 2.0,
    ledger_path: Path | str | None = None,
    dataset_path: Path | str | None = None,
) -> dict:
    """Run the full selection cycle and return the payload.

    Con `base_settings`, cada backtest usa los límites y costes de ese perfil en
    vez de los de investigación: el ciclo mide el bot que va a operar.
    Con `stress_multiplier > 1`, cada configuración se re-ejecuta con los costes
    multiplicados y el resultado queda en `payload["stress"]`.
    Con `dataset_path`, el ciclo usa ese pickle de 5m en lugar del congelado; la
    ruta y su hash quedan en el artefacto y en el trial ledger.
    """
    root = Path(ROOT)
    if spec_dir is None:
        spec_dir = root / "data" / "specs"

    dataset_path = (
        Path(dataset_path)
        if dataset_path is not None
        else root / "data" / "btc_5m.pkl"
    )
    df5 = pd.read_pickle(dataset_path) if dataset_path.exists() else pd.DataFrame()
    if df5.empty:
        raise FileNotFoundError(
            f"Frozen 5m dataset not found at {dataset_path}"
        )
    df5 = _window(df5, start, end)
    if df5.empty:
        raise ValueError(f"la ventana pedida no deja velas en {dataset_path}")

    specs = load_universe_specs(spec_dir, all_specs=all_specs)
    if not specs:
        raise ValueError("No specs loaded")

    spec_sources = _spec_sources(spec_dir, root)
    specs_hash_raw = hashlib.sha256(
        json.dumps(
            [spec.model_dump(mode="json") for spec in specs], sort_keys=True
        ).encode("utf-8")
    ).hexdigest()
    dataset_meta = _dataset_payload(root, dataset_path, df5, start, end)
    target_ledger = (
        Path(ledger_path)
        if ledger_path is not None
        else root / "data" / "validation" / f"{cycle_id}.trials.jsonl"
    )
    from .trial_ledger import TrialLedger, reconstruct_ledger

    ledger = TrialLedger(
        target_ledger,
        cycle_id=cycle_id,
        blocks=blocks,
        dataset=dataset_meta,
        specs_hash="sha256:" + specs_hash_raw,
    )
    discarded_trials: list[dict[str, Any]] = []

    # Run backtest for each spec
    daily: dict[str, pd.Series] = {}
    trade_log: dict[str, pd.DataFrame] = {}
    summary = []
    stress_summary: list[dict] = []

    if not quiet:
        print(f"Running backtests for {len(specs)} specs...")

    for spec in specs:
        name = spec.label
        diagnostics: dict[str, Any] = {}
        trade_df, equity, metrics = run_backtest_for_spec(
            spec, df5, base=base_settings, diagnostics=diagnostics
        )
        spec_record = _spec_payload(spec, spec_sources.get(name))
        seed = _validation_value(spec, "seed")

        if trade_df.empty:
            reason = "error" if diagnostics.get("error") else "sin_trades"
            ledger.record_trial(
                spec=spec_record,
                dataset=dataset_meta,
                status="discarded",
                seed=seed,
                daily_returns=[],
                metrics=None,
                discard_reason=reason,
                error=diagnostics.get("error"),
            )
            discarded_trials.append(
                {"label": name, "reason": reason, "error": diagnostics.get("error")}
            )
            if not quiet:
                print(f"  {name:26s} sin trades")
            continue

        # Aggregate to daily returns (in R multiples)
        trade_df["day"] = trade_df["ts"].dt.date
        daily_returns = trade_df.groupby("day")["r_net"].sum()
        daily[name] = daily_returns

        trade_log[name] = trade_df

        closed_metrics = metrics.get("closed", {})
        summary.append({
            "name": name,
            "spec_id": spec.id,
            "timeframe": spec.timeframe_signal,
            "variant": spec.get("_variant") if hasattr(spec, "_variant") else None,
            "trades": closed_metrics.get("trades", 0),
            "pf_net": closed_metrics.get("profit_factor", 0.0),
            "exp_r": closed_metrics.get("expectancy_r", 0.0),
            "days": int(daily_returns.size),
        })

        stress_entry = None
        if stress_multiplier and stress_multiplier > 1.0:
            stress_diagnostics: dict[str, Any] = {}
            _, _, stress_metrics = run_backtest_for_spec(
                spec,
                df5,
                base=base_settings,
                cost_multiplier=stress_multiplier,
                diagnostics=stress_diagnostics,
            )
            stressed_closed = stress_metrics.get("closed", {})
            stress_entry = {
                "name": name,
                "base_pf_net": summary[-1]["pf_net"],
                "base_exp_r": summary[-1]["exp_r"],
                "trades": stressed_closed.get("trades", 0),
                "pf_net": stressed_closed.get("profit_factor", 0.0),
                "exp_r": stressed_closed.get("expectancy_r", 0.0),
                "pnl_net": stressed_closed.get("pnl_net", 0.0),
                "survives": bool(
                    stressed_closed.get("trades", 0) > 0
                    and stressed_closed.get("profit_factor", 0.0) > 1.0
                    and stressed_closed.get("expectancy_r", 0.0) > 0.0
                ),
                "status": "evaluated" if stressed_closed else "discarded",
            }
            if stress_diagnostics.get("error"):
                stress_entry["discard_reason"] = "error"
                stress_entry["error"] = stress_diagnostics["error"]
            elif not stressed_closed:
                stress_entry["discard_reason"] = "sin_trades"
            stress_summary.append(stress_entry)
            summary[-1]["stress"] = stress_entry
            if not quiet:
                print(
                    f"  {name:26s} x{stress_multiplier:g}  "
                    f"PF {stress_entry['pf_net']:.3f}  exp {stress_entry['exp_r']:+.3f} R  "
                    f"{'sobrevive' if stress_entry['survives'] else 'no sobrevive'}"
                )

        ledger.record_trial(
            spec=spec_record,
            dataset=dataset_meta,
            status="evaluated",
            seed=seed,
            daily_returns=_daily_points(daily_returns),
            metrics=dict(summary[-1]),
            stress=stress_entry,
        )

        if not quiet:
            print(f"  {name:26s} {len(trade_df):6d} trades  PF {summary[-1]['pf_net']:.3f}  "
                  f"exp {summary[-1]['exp_r']:+.3f} R")

    matrix = pd.DataFrame(daily).fillna(0.0).sort_index()

    if matrix.empty or matrix.shape[1] < 3:
        ledger.record_selection(
            selected=None,
            not_selected=list(daily),
            discarded=discarded_trials,
            pbo={"pbo": None},
            dsr={"dsr": None},
            dsr_config=None,
        )
        raise SystemExit("universo insuficiente: se necesitan al menos 3 configuraciones con trades")

    if not quiet:
        print(f"matriz diaria {matrix.shape[0]} días × {matrix.shape[1]} configuraciones")

    # Compute gates
    pbo = cscv_pbo(matrix, blocks=blocks)
    sr_daily = {c: sharpe_daily(matrix[c].to_numpy()) for c in matrix.columns}
    best = max(sr_daily, key=sr_daily.get)

    # DSR per search space group
    groups: dict[str, list[str]] = {}
    for spec in specs:
        group = getattr(spec, "_group", None) or spec.id
        groups.setdefault(group, []).append(spec.label)
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
    best_group = next((getattr(s, "_group", None) or s.id for s in specs if s.label == best), None)
    if best_group and best_group in dsr_by_group:
        dsr = dict(dsr_by_group[best_group])
        dsr["source"] = f"grupo {best_group}"
    else:
        dsr["source"] = "universo completo"

    mbtl = min_backtest_length(len(matrix.columns), dsr.get("sharpe_annual") or 0.0)
    wfa = walk_forward(trade_log, folds=folds)
    cp = cpcv(matrix, blocks=blocks, test_blocks=test_blocks, purge=purge)
    psr = probabilistic_sharpe(matrix[best].to_numpy())

    stress_block = None
    if stress_summary:
        selected_stress = next(
            (item for item in stress_summary if item["name"] == best), None
        )
        stress_block = {
            "multiplier": stress_multiplier,
            "method": "rerun",
            "selected": best,
            "selected_survives": bool(
                selected_stress and selected_stress["survives"]
            ),
            "survivors": [
                item["name"] for item in stress_summary if item["survives"]
            ],
            "configs": stress_summary,
        }

    not_selected = [label for label in matrix.columns if label != best]
    reconstruction = reconstruct_ledger(ledger.path)
    ledger.record_selection(
        selected=best,
        not_selected=not_selected,
        discarded=discarded_trials,
        pbo=pbo,
        dsr=dsr,
        dsr_config=best,
    )
    ledger_hash = "sha256:" + hashlib.sha256(ledger.path.read_bytes()).hexdigest()
    reconstruction_matches = (
        reconstruction["pbo"].get("pbo") == pbo.get("pbo")
        and reconstruction["dsr"].get("dsr") == dsr.get("dsr")
        and reconstruction["dsr_config"] == best
        and reconstruction["matrix"]
        == {"days": int(matrix.shape[0]), "columns": int(matrix.shape[1])}
    )

    years = matrix.index.to_series().diff().dt.days.sum() / 365.25

    # Data hash
    import io
    buf = io.BytesIO()
    df5.to_pickle(buf, compression=None)
    data_hash = hashlib.sha256(buf.getvalue()).hexdigest()

    payload = {
        "cycle_id": cycle_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method_version": "1.0.0",
        "inputs": {
            "data_hash": "sha256:" + data_hash,
            "specs_hash": "sha256:" + specs_hash_raw,
            "universe_size": len(specs),
            "daily_observations": int(matrix.shape[0]),
            "coverage_years": round(float(years), 2),
            "limits_source": "perfil" if base_settings is not None else "investigacion",
            "stress_multiplier": stress_multiplier,
            "dataset": dataset_meta,
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
        "stress": stress_block,
        "trial_ledger": {
            "path": _relative_path(ledger.path, root),
            "sha256": ledger_hash,
            "trials": reconstruction["trials"],
            "discarded": reconstruction["discarded"],
            "selected": best,
            "not_selected": not_selected,
            "reconstruction": {
                "pbo": reconstruction["pbo"].get("pbo"),
                "dsr": reconstruction["dsr"].get("dsr"),
                "dsr_config": reconstruction["dsr_config"],
                "matrix": reconstruction["matrix"],
                "matches": reconstruction_matches,
            },
        },
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
            "El estrés de costes re-ejecuta cada configuración con comisión, fees, "
            "medio spread y slippage multiplicados; no se estima desde el PnL base.",
            "El trial ledger guarda cada spec, dataset, semilla y descarte; su "
            "reconstrucción vuelve a calcular PBO y DSR desde las series diarias y "
            "debe coincidir con las cifras de este artefacto. No cambia ninguna puerta.",
        ],
    }

    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description="Selection cycle: PBO, DSR, MinBTL, WFA")
    ap.add_argument("--cycle", default="CYCLE-2026-11")
    ap.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="ruta del trial ledger; por defecto data/validation/<cycle>.trials.jsonl",
    )
    ap.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="pickle de velas 5m; por defecto data/btc_5m.pkl",
    )
    ap.add_argument("--blocks", type=int, default=10, help="CSCV blocks S (even)")
    ap.add_argument("--folds", type=int, default=5, help="walk-forward folds")
    ap.add_argument("--test-blocks", type=int, default=2, help="CPCV blocks held out per path")
    ap.add_argument("--purge", type=int, default=1, help="CPCV purge blocks")
    ap.add_argument("--spec-dir", type=Path, default=None, help="directory with spec JSON files")
    ap.add_argument(
        "--config",
        type=Path,
        default=Path("profiles/okx/config.json"),
        help="perfil cuyos límites y costes usa el ciclo",
    )
    ap.add_argument(
        "--all-specs",
        action="store_true",
        help="carga todos los .json del directorio, no solo el universo por defecto",
    )
    ap.add_argument(
        "--stress-multiplier",
        type=float,
        default=2.0,
        help="multiplicador de costes del estrés; 1 lo apaga",
    )
    ap.add_argument(
        "--from",
        dest="date_from",
        default=None,
        help="primer día ISO (AAAA-MM-DD), incluido; sin esto, desde el inicio",
    )
    ap.add_argument(
        "--to",
        dest="date_to",
        default=None,
        help="día ISO (AAAA-MM-DD) de corte, excluido; sin esto, hasta el final",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    base_settings = None
    if args.config is not None:
        if Path(args.config).is_file():
            base_settings = load_settings(args.config)
            if not args.quiet:
                print(f"límites del perfil: {args.config}")
        elif not args.quiet:
            print(f"Aviso: no encuentro {args.config}; uso los límites de investigación")

    payload = run_selection_cycle(
        cycle_id=args.cycle,
        blocks=args.blocks,
        folds=args.folds,
        test_blocks=args.test_blocks,
        purge=args.purge,
        spec_dir=args.spec_dir,
        quiet=args.quiet,
        start=_iso_day(args.date_from) if args.date_from else None,
        end=_iso_day(args.date_to) if args.date_to else None,
        base_settings=base_settings,
        all_specs=args.all_specs,
        stress_multiplier=args.stress_multiplier,
        ledger_path=args.ledger,
        dataset_path=args.dataset,
    )

    args.spec_dir = args.spec_dir or (ROOT / "data" / "specs")
    OUT_DIR = ROOT / "data" / "validation"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{args.cycle}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if not args.quiet:
        print(f"Validation written to {path}")
        trial_ledger = payload.get("trial_ledger") or {}
        if trial_ledger.get("path"):
            print(f"Trial ledger written to {trial_ledger['path']}")


if __name__ == "__main__":
    main()
