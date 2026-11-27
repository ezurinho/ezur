"""Desequilibrio de flujo de taker, simulador determinista.

Regla del pre-registro H7: flujo = taker_buy_base / volume; z-score de ``lookback``
dias; senal = media de los ultimos ``signal_days`` z al cierre t-1; se ejecuta al
cierre t. Quintiles dollar-neutral, rebalanceo cada ``hold`` dias, costes por
posicion y funding incluido.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from server.funding_xs import FundingResult, Position

COST_PER_SIDE = 0.0006
CAPITAL = 25_000.0
MIN_NOTIONAL = 5_000_000.0


def load_data(flow_path: Path, funding_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = pd.read_csv(flow_path, parse_dates=["dt"])
    frame["notional"] = frame["volume"] * frame["close"]
    frame["ratio"] = frame["taker_buy_base"] / frame["volume"].replace(0.0, np.nan)
    ratio = frame.pivot_table(index="dt", columns="symbol", values="ratio", aggfunc="last").sort_index()
    close = frame.pivot_table(index="dt", columns="symbol", values="close", aggfunc="last").sort_index()
    notional = frame.pivot_table(index="dt", columns="symbol", values="notional", aggfunc="last").sort_index()

    funding = pd.read_csv(funding_path, parse_dates=["dt"])
    funding["rate_8h"] = funding["rate"] * 8.0 / funding["interval_h"].clip(lower=1)
    funding["date"] = funding["dt"].dt.floor("D")
    daily_funding = funding.groupby(["date", "symbol"])["rate_8h"].sum().unstack("symbol").sort_index()
    return ratio, close, notional, daily_funding


def _zscore(ratio: pd.DataFrame, lookback: int) -> pd.DataFrame:
    mean = ratio.rolling(lookback).mean()
    std = ratio.rolling(lookback).std().where(lambda value: value > 1e-12)
    return (ratio - mean) / std


def run_flow(
    ratio: pd.DataFrame,
    close: pd.DataFrame,
    notional: pd.DataFrame,
    funding: pd.DataFrame,
    lookback: int = 20,
    signal_days: int = 3,
    hold: int = 3,
    quantile: float = 0.2,
    long_only: bool = False,
    threshold: float | None = None,
    capital: float = CAPITAL,
    cost_per_side: float = COST_PER_SIDE,
) -> FundingResult:
    ratio = ratio.sort_index()
    close = close.sort_index().ffill()
    notional = notional.sort_index().ffill()
    z = _zscore(ratio, lookback)
    dates = list(close.index)
    if len(dates) < lookback + signal_days + 5:
        return FundingResult()

    positions: dict[str, Position] = {}
    result = FundingResult()
    daily = pd.Series(0.0, index=dates)
    last_rebalance: int | None = None

    for index, date in enumerate(dates):
        if index == 0:
            continue
        # P&L de la cartera abierta.
        for symbol, position in list(positions.items()):
            price = float(close[symbol].iloc[index])
            previous = float(close[symbol].iloc[index - 1])
            if not np.isfinite(price) or not np.isfinite(previous) or previous <= 0:
                continue
            pnl = position.sign * (price / previous - 1.0) * position.notional
            position.price_pnl += pnl
            daily.iloc[index] += pnl / capital
            rate = (
                funding.loc[date, symbol]
                if date in funding.index and symbol in funding.columns
                else np.nan
            )
            if np.isfinite(rate) and position.entry_date < date:
                cash = -position.sign * float(rate) * position.notional
                position.funding_pnl += cash
                daily.iloc[index] += cash / capital

        # Rebalanceo.
        if last_rebalance is not None and index - last_rebalance < hold:
            continue
        if index - 1 < lookback + signal_days - 1:
            continue
        signal = z.iloc[index - signal_days : index].mean()
        signal = signal.replace([np.inf, -np.inf], np.nan).dropna()
        eligible = []
        for symbol in signal.index:
            if symbol not in close.columns:
                continue
            hist = notional[symbol].iloc[max(0, index - 20) : index]
            if not np.isfinite(close[symbol].iloc[index]) or close[symbol].iloc[index] <= 0:
                continue
            if not np.isfinite(hist.median()) or hist.median() < MIN_NOTIONAL:
                continue
            eligible.append(symbol)
        signal = signal[eligible]

        if long_only:
            # La variante BTC-TS solo opera BTCUSDT, no todo el panel.
            target = {
                symbol: 1
                for symbol in signal.index
                if symbol == "BTCUSDT" and signal[symbol] > (threshold or 0.0)
            }
            notional_per = capital
        elif len(signal) >= 4:
            count = max(2, int(round(len(signal) * quantile)))
            ranked = signal.sort_values()
            shorts = set(ranked.index[:count])
            longs = set(ranked.index[-count:])
            target = {symbol: 1 for symbol in longs} | {symbol: -1 for symbol in shorts}
            notional_per = capital * 0.5 / count
        else:
            target = {}
            notional_per = 0.0

        for symbol in list(positions):
            if symbol not in target or positions[symbol].sign != target[symbol]:
                position = positions.pop(symbol)
                close_cost = cost_per_side * position.notional
                position.costs += close_cost
                daily.iloc[index] -= close_cost / capital
                result.episodes.append(
                    {
                        "symbol": symbol,
                        "sign": position.sign,
                        "entry": position.entry_date,
                        "exit": date,
                        "price_pnl": position.price_pnl,
                        "funding_pnl": position.funding_pnl,
                        "costs": position.costs,
                        "net": position.price_pnl + position.funding_pnl - position.costs,
                        "operations": 2,
                    }
                )
        for symbol, sign in target.items():
            if symbol in positions:
                continue
            price = float(close[symbol].iloc[index])
            if not np.isfinite(price) or price <= 0:
                continue
            position = Position(
                symbol=symbol,
                sign=sign,
                notional=notional_per,
                entry_date=date,
                entry_price=price,
            )
            position.costs += cost_per_side * notional_per
            daily.iloc[index] -= cost_per_side * notional_per / capital
            positions[symbol] = position
        last_rebalance = index

    final_date = dates[-1]
    for symbol, position in list(positions.items()):
        close_cost = cost_per_side * position.notional
        position.costs += close_cost
        daily.iloc[-1] -= close_cost / capital
        result.episodes.append(
            {
                "symbol": symbol,
                "sign": position.sign,
                "entry": position.entry_date,
                "exit": final_date,
                "price_pnl": position.price_pnl,
                "funding_pnl": position.funding_pnl,
                "costs": position.costs,
                "net": position.price_pnl + position.funding_pnl - position.costs,
                "operations": 2,
            }
        )
    result.daily = daily
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Flujo de taker en perpetuos")
    parser.add_argument("--from", dest="start", default="2020-01-01")
    parser.add_argument("--to", dest="end", default="2026-11-01")
    parser.add_argument("--flow", default="data/flow/taker_flow_1d.csv")
    parser.add_argument("--funding", default="data/funding_xs/funding_panel.csv")
    args = parser.parse_args()

    ratio, close, notional, funding = load_data(Path(args.flow), Path(args.funding))
    mask = (close.index >= args.start) & (close.index < args.end)
    ratio, close, notional = ratio[mask], close[mask], notional[mask]
    funding = funding[(funding.index >= args.start) & (funding.index < args.end)]
    years = (pd.Timestamp(args.end, tz="UTC") - pd.Timestamp(args.start, tz="UTC")).days / 365.25

    variants = [
        ("Z20-3D", 20, 3, 3, 0.2, False, None),
        ("Z5-1D", 5, 1, 1, 0.2, False, None),
        ("Z60-3D", 60, 3, 3, 0.2, False, None),
        ("Z20-3D-T", 20, 3, 3, 1.0 / 3.0, False, None),
        ("BTC-TS", 20, 3, 1, 1.0, True, 1.0),
    ]
    for name, lookback, signal_days, hold, quantile, long_only, threshold in variants:
        result = run_flow(
            ratio, close, notional, funding,
            lookback=lookback, signal_days=signal_days, hold=hold,
            quantile=quantile, long_only=long_only, threshold=threshold,
        )
        print(name, result.summary(years=years), flush=True)


if __name__ == "__main__":
    main()
