"""Spread de funding entre venues, simulador determinista de H8.

Regla del pre-registro H8: para cada activo se ordenan los venues por la media
del funding diario de los ultimos ``lookback`` dias. Si el spread anualizado
supera ``entry``, se compra el perp del venue barato y se vende el del caro,
delta-neutral y con el mismo notional. Se sale cuando el spread cae por debajo
de ``exit``, cambia el par extremo o se cumple ``max_hold_days``. El P&L separa
precio, funding y costes.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from server.funding_xs import CAPITAL, FundingResult

VENUES = ("binance", "okx", "hyperliquid")
ASSETS = ("BTC", "ETH", "SOL", "XRP", "DOGE")
COST_PER_LEG_SIDE = 0.0007
MAX_HOLD_DAYS = 28


@dataclass
class SpreadSignal:
    asset: str
    long_venue: str
    short_venue: str
    spread: float


@dataclass
class SpreadPosition:
    asset: str
    long_venue: str
    short_venue: str
    leg_notional: float
    entry_date: pd.Timestamp
    entry_spread: float
    price_pnl: float = 0.0
    funding_pnl: float = 0.0
    costs: float = 0.0
    missing_marks: int = 0
    missing_funding: int = 0


@dataclass
class SpreadResult(FundingResult):
    spreads: list[dict] = field(default_factory=list)


def load_panels(funding_path: Path, prices_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    funding = pd.read_csv(funding_path, parse_dates=["date"])
    prices = pd.read_csv(prices_path, parse_dates=["date"])
    funding["date"] = pd.to_datetime(funding["date"], utc=True)
    prices["date"] = pd.to_datetime(prices["date"], utc=True)
    funding_wide = funding.pivot_table(
        index="date", columns=["asset", "venue"], values="rate", aggfunc="sum"
    ).sort_index()
    price_wide = prices.pivot_table(
        index="date", columns=["asset", "venue"], values="close", aggfunc="last"
    ).sort_index()
    dates = pd.date_range(
        min(funding_wide.index.min(), price_wide.index.min()),
        max(funding_wide.index.max(), price_wide.index.max()),
        freq="D",
        tz="UTC",
    )
    return funding_wide.reindex(dates), price_wide.reindex(dates)


def _venue_means(funding: pd.DataFrame, lookback: int) -> dict[str, pd.DataFrame]:
    means: dict[str, pd.DataFrame] = {}
    if "asset" not in funding.columns.names:
        return means
    for asset in funding.columns.get_level_values("asset").unique():
        frame = funding.xs(asset, level="asset", axis=1).reindex(columns=VENUES)
        minimum = max(2, math.ceil(lookback * 0.8))
        means[str(asset)] = frame.rolling(lookback, min_periods=minimum).mean().shift(1)
    return means


def _price(prices: pd.DataFrame, date: pd.Timestamp, asset: str, venue: str) -> float:
    try:
        value = prices.loc[date, (asset, venue)]
    except KeyError:
        return float("nan")
    return float(value) if pd.notna(value) else float("nan")


def _signals_at(
    means: dict[str, pd.DataFrame],
    date: pd.Timestamp,
    assets: tuple[str, ...],
) -> dict[str, SpreadSignal]:
    signals: dict[str, SpreadSignal] = {}
    for asset in assets:
        frame = means.get(asset)
        if frame is None or date not in frame.index:
            continue
        row = frame.loc[date].replace([np.inf, -np.inf], np.nan).dropna()
        if len(row) < 2:
            continue
        long_venue = str(row.idxmin())
        short_venue = str(row.idxmax())
        spread = float(row[short_venue] - row[long_venue]) * 365.0
        if spread > 0:
            signals[asset] = SpreadSignal(asset, long_venue, short_venue, spread)
    return signals


def _rebalance_day(date: pd.Timestamp, mode: str) -> bool:
    return mode.upper() == "D" or date.weekday() == 0


def _close(
    positions: dict[str, SpreadPosition],
    asset: str,
    date: pd.Timestamp,
    daily: pd.Series,
    result: SpreadResult,
    capital: float,
    cost_per_leg_side: float,
) -> None:
    position = positions.pop(asset)
    close_cost = cost_per_leg_side * position.leg_notional * 2.0
    position.costs += close_cost
    daily.loc[date] -= close_cost / capital
    result.episodes.append(
        {
            "symbol": asset,
            "long_venue": position.long_venue,
            "short_venue": position.short_venue,
            "sign": 1,
            "entry": position.entry_date,
            "exit": date,
            "days": (date - position.entry_date).days,
            "entry_spread": round(position.entry_spread * 100, 4),
            "price_pnl": position.price_pnl,
            "funding_pnl": position.funding_pnl,
            "costs": position.costs,
            "net": position.price_pnl + position.funding_pnl - position.costs,
            "operations": 2,
            "missing_marks": position.missing_marks,
            "missing_funding": position.missing_funding,
        }
    )


def run_spread(
    funding: pd.DataFrame,
    prices: pd.DataFrame,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    lookback: int = 7,
    rebalance: str = "W",
    entry: float = 0.12,
    exit: float = 0.03,
    assets: tuple[str, ...] = ASSETS,
    max_hold_days: int = MAX_HOLD_DAYS,
    cost_per_leg_side: float = COST_PER_LEG_SIDE,
    capital: float = CAPITAL,
) -> SpreadResult:
    assets = tuple(assets)
    if not assets:
        return SpreadResult()
    funding = funding.sort_index()
    prices = prices.sort_index()
    means = _venue_means(funding, lookback)
    start_ts = pd.Timestamp(start, tz="UTC") if start is not None else funding.index.min()
    end_ts = pd.Timestamp(end, tz="UTC") if end is not None else funding.index.max()
    eval_dates = [
        date for date in funding.index if start_ts <= date < end_ts and date in prices.index
    ]
    if len(eval_dates) < 10:
        return SpreadResult()

    prices_ffilled = prices.ffill(limit=2)
    positions: dict[str, SpreadPosition] = {}
    result = SpreadResult()
    daily = pd.Series(0.0, index=pd.DatetimeIndex(eval_dates))
    leg_notional = capital / len(assets) / 2.0
    rebalances = 0

    for index, date in enumerate(eval_dates):
        # 1) Marcar la cartera que ya estaba abierta al cierre anterior.
        if index > 0:
            previous = eval_dates[index - 1]
            for asset, position in list(positions.items()):
                if date <= position.entry_date:
                    continue
                long_now = _price(prices_ffilled, date, asset, position.long_venue)
                long_prev = _price(prices_ffilled, previous, asset, position.long_venue)
                short_now = _price(prices_ffilled, date, asset, position.short_venue)
                short_prev = _price(prices_ffilled, previous, asset, position.short_venue)
                if (
                    np.isfinite(long_now)
                    and np.isfinite(long_prev)
                    and long_prev > 0
                    and np.isfinite(short_now)
                    and np.isfinite(short_prev)
                    and short_prev > 0
                ):
                    long_return = long_now / long_prev - 1.0
                    short_return = short_now / short_prev - 1.0
                    pnl = (long_return - short_return) * position.leg_notional
                    position.price_pnl += pnl
                    daily.loc[date] += pnl / capital
                else:
                    position.missing_marks += 1

                rate_long = _price(
                    funding, date, asset, position.long_venue
                )
                rate_short = _price(
                    funding, date, asset, position.short_venue
                )
                if np.isfinite(rate_long) and np.isfinite(rate_short):
                    pnl = (rate_short - rate_long) * position.leg_notional
                    position.funding_pnl += pnl
                    daily.loc[date] += pnl / capital
                else:
                    position.missing_funding += 1

        # 2) Rebalanceo al cierre.
        if not _rebalance_day(date, rebalance):
            continue
        rebalances += 1
        signals = _signals_at(means, date, assets)
        blocked: set[str] = set()

        for asset, position in list(positions.items()):
            signal = signals.get(asset)
            age = (date - position.entry_date).days
            if signal is None:
                _close(positions, asset, date, daily, result, capital, cost_per_leg_side)
                continue
            if age >= max_hold_days:
                _close(positions, asset, date, daily, result, capital, cost_per_leg_side)
                blocked.add(asset)
                continue
            if (
                signal.spread < exit
                or signal.long_venue != position.long_venue
                or signal.short_venue != position.short_venue
            ):
                _close(positions, asset, date, daily, result, capital, cost_per_leg_side)

        candidates = [
            signal
            for asset, signal in signals.items()
            if asset not in positions and asset not in blocked and signal.spread >= entry
        ]
        slots = max(0, len(assets) - len(positions))
        if date == eval_dates[-1]:
            slots = 0
        for signal in sorted(candidates, key=lambda item: item.spread, reverse=True)[:slots]:
            long_price = _price(prices, date, signal.asset, signal.long_venue)
            short_price = _price(prices, date, signal.asset, signal.short_venue)
            if not (
                np.isfinite(long_price)
                and long_price > 0
                and np.isfinite(short_price)
                and short_price > 0
            ):
                continue
            position = SpreadPosition(
                asset=signal.asset,
                long_venue=signal.long_venue,
                short_venue=signal.short_venue,
                leg_notional=leg_notional,
                entry_date=date,
                entry_spread=signal.spread,
            )
            position.costs += cost_per_leg_side * leg_notional * 2.0
            daily.loc[date] -= position.costs / capital
            positions[signal.asset] = position

    final_date = eval_dates[-1]
    for asset in list(positions):
        _close(
            positions,
            asset,
            final_date,
            daily,
            result,
            capital,
            cost_per_leg_side,
        )

    result.daily = daily
    result.weeks = rebalances
    return result


VARIANTS = (
    ("H8-S7-W-12", 7, "W", 0.12, 0.03, ASSETS),
    ("H8-S30-W-12", 30, "W", 0.12, 0.03, ASSETS),
    ("H8-S7-D-12", 7, "D", 0.12, 0.03, ASSETS),
    ("H8-S7-W-8", 7, "W", 0.08, 0.03, ASSETS),
    ("H8-BTC-W-12", 7, "W", 0.12, 0.03, ("BTC",)),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Spread de funding entre venues (H8)")
    parser.add_argument("--from", dest="start", default="2023-07-01")
    parser.add_argument("--to", dest="end", default="2025-01-01")
    parser.add_argument("--funding", default="data/funding_spread/funding_daily.csv")
    parser.add_argument("--prices", default="data/funding_spread/prices_daily.csv")
    args = parser.parse_args()

    funding, prices = load_panels(Path(args.funding), Path(args.prices))
    years = (pd.Timestamp(args.end, tz="UTC") - pd.Timestamp(args.start, tz="UTC")).days / 365.25
    for name, lookback, rebalance, entry, exit, assets in VARIANTS:
        result = run_spread(
            funding,
            prices,
            start=args.start,
            end=args.end,
            lookback=lookback,
            rebalance=rebalance,
            entry=entry,
            exit=exit,
            assets=assets,
        )
        print(name, json.dumps(result.summary(years=years), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
