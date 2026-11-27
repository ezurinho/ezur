"""Basis spot-perp, simulador determinista de H9.

Regla del pre-registro H9: para cada activo se calcula el basis diario
(``perp/spot - 1``) y el funding diario. La senal es la media de ambos en los
ultimos ``lookback`` dias, con datos hasta t-1. Si el carry esperado supera
``entry`` y el activo esta en el quintil (o decil) superior, se compra spot y se
vende el perpetuo con el mismo notional. Se sale cuando el carry cae por debajo
de ``exit``, el activo sale de la banda de permanencia o se cumple
``max_hold_days``. El P&L separa precio, funding y costes.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from server.funding_xs import CAPITAL, FundingResult


class BasisResult(FundingResult):
    """Mismo resumen que H5; los episodios anaden basis y score de entrada."""


ASSETS = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "DOTUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "TRXUSDT",
    "ATOMUSDT",
    "NEARUSDT",
    "ETCUSDT",
    "FILUSDT",
    "UNIUSDT",
    "AAVEUSDT",
    "SANDUSDT",
)
COST_PER_LEG_SIDE = 0.0007
MAX_HOLD_DAYS = 28
HOLD_BUFFER = 0.40


@dataclass
class BasisPosition:
    symbol: str
    leg_notional: float
    entry_date: pd.Timestamp
    entry_score: float
    entry_basis: float
    entry_funding: float
    price_pnl: float = 0.0
    funding_pnl: float = 0.0
    costs: float = 0.0
    missing_marks: int = 0
    missing_funding: int = 0


def load_panels(
    spot_path: Path, perp_path: Path, funding_path: Path
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spot = pd.read_csv(spot_path, parse_dates=["dt"])
    perp = pd.read_csv(perp_path, parse_dates=["dt"])
    funding = pd.read_csv(funding_path, parse_dates=["dt"])
    for frame in (spot, perp, funding):
        frame["dt"] = pd.to_datetime(frame["dt"], utc=True).dt.floor("D")
    spot_wide = spot.pivot_table(index="dt", columns="symbol", values="close", aggfunc="last").sort_index()
    perp_wide = perp.pivot_table(index="dt", columns="symbol", values="close", aggfunc="last").sort_index()
    funding_wide = funding.pivot_table(index="dt", columns="symbol", values="rate", aggfunc="sum").sort_index()
    dates = pd.date_range(
        min(spot_wide.index.min(), perp_wide.index.min()),
        max(spot_wide.index.max(), perp_wide.index.max()),
        freq="D",
        tz="UTC",
    )
    return (
        spot_wide.reindex(dates),
        perp_wide.reindex(dates),
        funding_wide.reindex(dates),
    )


def _score_frame(
    spot: pd.DataFrame,
    perp: pd.DataFrame,
    funding: pd.DataFrame,
    lookback: int,
    basis_override: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Score pre-registrado. `basis_override` existe sólo para tests de nulidad:
    sustituye el basis observado en la señal y deja intactos precio y ejecución."""
    basis = basis_override if basis_override is not None else perp / spot - 1.0
    minimum = max(2, math.ceil(lookback * 0.8))
    basis_mean = basis.rolling(lookback, min_periods=minimum).mean()
    funding_mean = funding.rolling(lookback, min_periods=minimum).mean()
    return (basis_mean + funding_mean).shift(1)


def _rebalance_day(date: pd.Timestamp, mode: str) -> bool:
    return mode.upper() == "D" or date.weekday() == 0


def _close(
    positions: dict[str, BasisPosition],
    symbol: str,
    date: pd.Timestamp,
    daily: pd.Series,
    result: BasisResult,
    capital: float,
    cost_per_leg_side: float,
) -> None:
    position = positions.pop(symbol)
    close_cost = cost_per_leg_side * position.leg_notional * 2.0
    position.costs += close_cost
    daily.loc[date] -= close_cost / capital
    result.episodes.append(
        {
            "symbol": symbol,
            "entry": position.entry_date,
            "exit": date,
            "days": (date - position.entry_date).days,
            "entry_score_bp": round(position.entry_score * 1e4, 4),
            "entry_basis_bp": round(position.entry_basis * 1e4, 4),
            "entry_funding_bp": round(position.entry_funding * 1e4, 4),
            "price_pnl": position.price_pnl,
            "funding_pnl": position.funding_pnl,
            "costs": position.costs,
            "net": position.price_pnl + position.funding_pnl - position.costs,
            "operations": 2,
            "missing_marks": position.missing_marks,
            "missing_funding": position.missing_funding,
        }
    )


def run_basis_carry(
    spot: pd.DataFrame,
    perp: pd.DataFrame,
    funding: pd.DataFrame,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    lookback: int = 7,
    rebalance: str = "W",
    quantile: float = 0.2,
    entry: float = 0.00025,
    exit: float = 0.00010,
    max_hold_days: int = MAX_HOLD_DAYS,
    hold_buffer: float = HOLD_BUFFER,
    assets: tuple[str, ...] = ASSETS,
    cost_per_leg_side: float = COST_PER_LEG_SIDE,
    capital: float = CAPITAL,
    basis_override: pd.DataFrame | None = None,
) -> BasisResult:
    assets = tuple(assets)
    if not assets:
        return BasisResult()
    spot = spot.reindex(columns=list(assets)).sort_index()
    perp = perp.reindex(columns=list(assets)).sort_index()
    funding = funding.reindex(columns=list(assets)).sort_index()
    if basis_override is not None:
        basis_override = basis_override.reindex(columns=list(assets)).sort_index()
    scores = _score_frame(spot, perp, funding, lookback, basis_override)

    start_ts = pd.Timestamp(start, tz="UTC") if start is not None else spot.index.min()
    end_ts = pd.Timestamp(end, tz="UTC") if end is not None else spot.index.max()
    eval_dates = [date for date in perp.index if start_ts <= date < end_ts and date in spot.index]
    if len(eval_dates) < max(lookback + 10, 20):
        return BasisResult()

    spot_ffilled = spot.ffill(limit=2)
    perp_ffilled = perp.ffill(limit=2)
    max_positions = max(1, int(round(len(assets) * quantile)))
    leg_notional = capital / max_positions / 2.0

    positions: dict[str, BasisPosition] = {}
    result = BasisResult()
    daily = pd.Series(0.0, index=pd.DatetimeIndex(eval_dates))
    rebalances = 0

    for index, date in enumerate(eval_dates):
        # 1) Marcar la cartera abierta al cierre anterior.
        if index > 0:
            previous = eval_dates[index - 1]
            for symbol, position in list(positions.items()):
                if date <= position.entry_date:
                    continue
                spot_now = float(spot_ffilled.loc[date, symbol])
                spot_prev = float(spot_ffilled.loc[previous, symbol])
                perp_now = float(perp_ffilled.loc[date, symbol])
                perp_prev = float(perp_ffilled.loc[previous, symbol])
                if (
                    np.isfinite(spot_now)
                    and np.isfinite(spot_prev)
                    and spot_prev > 0
                    and np.isfinite(perp_now)
                    and np.isfinite(perp_prev)
                    and perp_prev > 0
                ):
                    spot_return = spot_now / spot_prev - 1.0
                    perp_return = perp_now / perp_prev - 1.0
                    pnl = (spot_return - perp_return) * position.leg_notional
                    position.price_pnl += pnl
                    daily.loc[date] += pnl / capital
                else:
                    position.missing_marks += 1

                rate = float(funding.loc[date, symbol]) if date in funding.index else float("nan")
                if np.isfinite(rate):
                    cash = rate * position.leg_notional
                    position.funding_pnl += cash
                    daily.loc[date] += cash / capital
                else:
                    position.missing_funding += 1

        # 2) Rebalanceo al cierre.
        if not _rebalance_day(date, rebalance):
            continue
        rebalances += 1
        row = scores.loc[date].replace([np.inf, -np.inf], np.nan) if date in scores.index else pd.Series(dtype=float)
        available = [
            symbol
            for symbol in assets
            if symbol in row.index
            and np.isfinite(float(row[symbol]))
            and np.isfinite(float(spot.loc[date, symbol]))
            and np.isfinite(float(perp.loc[date, symbol]))
        ]
        ranked = row[available].sort_values(ascending=False)
        count = max(1, int(round(len(ranked) * quantile))) if len(ranked) else 0
        hold_cut = max(count, math.ceil(len(ranked) * hold_buffer)) if len(ranked) else 0
        rank_of = {symbol: place + 1 for place, symbol in enumerate(ranked.index)}
        blocked: set[str] = set()

        for symbol, position in list(positions.items()):
            rank = rank_of.get(symbol)
            age = (date - position.entry_date).days
            if (
                rank is None
                or float(ranked[symbol]) < exit
                or rank > hold_cut
                or age >= max_hold_days
            ):
                _close(positions, symbol, date, daily, result, capital, cost_per_leg_side)
                if age >= max_hold_days:
                    blocked.add(symbol)

        slots = max(0, max_positions - len(positions))
        if date == eval_dates[-1]:
            slots = 0
        candidates = [
            symbol
            for symbol in ranked.index
            if symbol not in positions
            and symbol not in blocked
            and rank_of[symbol] <= count
            and float(ranked[symbol]) >= entry
        ]
        for symbol in candidates[:slots]:
            spot_price = float(spot.loc[date, symbol])
            perp_price = float(perp.loc[date, symbol])
            if spot_price <= 0 or perp_price <= 0:
                continue
            position = BasisPosition(
                symbol=symbol,
                leg_notional=leg_notional,
                entry_date=date,
                entry_score=float(ranked[symbol]),
                entry_basis=float(perp_price / spot_price - 1.0),
                entry_funding=float(funding.loc[date, symbol])
                if date in funding.index and np.isfinite(funding.loc[date, symbol])
                else float("nan"),
            )
            position.costs += cost_per_leg_side * leg_notional * 2.0
            daily.loc[date] -= position.costs / capital
            positions[symbol] = position

    final_date = eval_dates[-1]
    for symbol in list(positions):
        _close(positions, symbol, final_date, daily, result, capital, cost_per_leg_side)

    result.daily = daily
    result.weeks = rebalances
    return result


VARIANTS = (
    ("H9-C7-Q20-W-25", 7, "W", 0.20, 0.00025, 0.00010),
    ("H9-C30-Q20-W-25", 30, "W", 0.20, 0.00025, 0.00010),
    ("H9-C7-Q20-D-25", 7, "D", 0.20, 0.00025, 0.00010),
    ("H9-C7-Q10-W-25", 7, "W", 0.10, 0.00025, 0.00010),
    ("H9-C7-Q20-W-10", 7, "W", 0.20, 0.00010, 0.00005),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Basis spot-perp (H9)")
    parser.add_argument("--from", dest="start", default="2023-07-01")
    parser.add_argument("--to", dest="end", default="2025-01-01")
    parser.add_argument("--spot", default="data/basis/spot_daily.csv")
    parser.add_argument("--perp", default="data/basis/perp_daily.csv")
    parser.add_argument("--funding", default="data/basis/funding_daily.csv")
    args = parser.parse_args()

    spot, perp, funding = load_panels(Path(args.spot), Path(args.perp), Path(args.funding))
    years = (pd.Timestamp(args.end, tz="UTC") - pd.Timestamp(args.start, tz="UTC")).days / 365.25
    for name, lookback, rebalance, quantile, entry, exit in VARIANTS:
        result = run_basis_carry(
            spot,
            perp,
            funding,
            start=args.start,
            end=args.end,
            lookback=lookback,
            rebalance=rebalance,
            quantile=quantile,
            entry=entry,
            exit=exit,
        )
        print(name, json.dumps(result.summary(years=years), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
