"""Carry cross-sectional de funding en perpetuos, simulador determinista.

Regla del pre-registro H5: cada lunes se ordenan los perpetuos por la media de
funding de 7 dias estandarizada contra 90 dias; largo del quintil inferior,
corto del superior, dollar-neutral, rebalanceo semanal y costes por posicion.
El P&L separa precio, funding y costes para no confundir carry con beta.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

COST_PER_SIDE = 0.0006
CAPITAL = 25_000.0
RISK_FRACTION = 0.01


@dataclass
class Position:
    symbol: str
    sign: int
    notional: float
    entry_date: pd.Timestamp
    entry_price: float
    price_pnl: float = 0.0
    funding_pnl: float = 0.0
    costs: float = 0.0


@dataclass
class FundingResult:
    daily: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    episodes: list[dict] = field(default_factory=list)
    weeks: int = 0

    @property
    def net(self) -> float:
        return float((1.0 + self.daily).prod() - 1.0) if len(self.daily) else 0.0

    def summary(self, capital: float = CAPITAL, years: float | None = None) -> dict:
        if years is None:
            years = len(self.daily) / 365.25 if len(self.daily) else 0.0
        equity = (1.0 + self.daily).cumprod()
        drawdown = float((equity / equity.cummax() - 1.0).min()) if len(equity) else 0.0
        nets = [item["net"] for item in self.episodes]
        operations = 2 * len(self.episodes)
        gross_profit = sum(value for value in nets if value > 0)
        gross_loss = -sum(value for value in nets if value < 0)
        total_net = self.net * capital
        top5 = sum(sorted(nets, reverse=True)[:5])
        return {
            "weeks": self.weeks,
            "episodes": len(self.episodes),
            "operations": operations,
            "net_usd": round(total_net, 2),
            "net_pct": round(self.net * 100, 4),
            "cagr_pct": round(((1.0 + self.net) ** (1.0 / years) - 1.0) * 100, 4) if years > 0 else 0.0,
            "vol_pct": round(float(self.daily.std() * np.sqrt(365.25) * 100), 4),
            "sharpe": round(float(self.daily.mean() / self.daily.std() * np.sqrt(365.25)), 4) if self.daily.std() else 0.0,
            "max_dd_pct": round(drawdown * 100, 4),
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else 0.0,
            "expectancy_r": round((sum(nets) / operations) / (capital * RISK_FRACTION) if operations else 0.0, 4),
            "cost_r": round((sum(item["costs"] for item in self.episodes) / operations) / (capital * RISK_FRACTION) if operations else 0.0, 4),
            "price_pnl_usd": round(sum(item["price_pnl"] for item in self.episodes), 2),
            "funding_pnl_usd": round(sum(item["funding_pnl"] for item in self.episodes), 2),
            "costs_usd": round(sum(item["costs"] for item in self.episodes), 2),
            "pnl_without_top5": round(total_net - top5, 2),
        }


def load_panels(funding_path: Path, price_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    funding = pd.read_csv(funding_path, parse_dates=["dt"])
    prices = pd.read_csv(price_path, parse_dates=["dt"])
    funding["rate_8h"] = funding["rate"] * 8.0 / funding["interval_h"].clip(lower=1)
    funding["date"] = funding["dt"].dt.floor("D")
    daily_funding = funding.groupby(["date", "symbol"])["rate_8h"].sum().unstack("symbol").sort_index()
    daily_prices = prices.pivot_table(index="dt", columns="symbol", values="close", aggfunc="last").sort_index()
    return daily_funding, daily_prices


def _zscore_signal(
    funding: pd.DataFrame, date: pd.Timestamp, lookback: int, raw: bool
) -> pd.Series:
    history = funding[funding.index < date].tail(lookback)
    if len(history) < lookback:
        return pd.Series(dtype=float)
    last_week = history.tail(7).mean()
    if raw:
        return last_week.dropna()
    mean = history.mean()
    std = history.std().where(lambda value: value > 1e-12)
    return ((last_week - mean) / std).dropna()


def run_funding_xs(
    funding: pd.DataFrame,
    prices: pd.DataFrame,
    lookback: int = 90,
    quantile: float = 0.2,
    weekly: bool = True,
    raw: bool = False,
    capital: float = CAPITAL,
    cost_per_side: float = COST_PER_SIDE,
) -> FundingResult:
    funding = funding.sort_index()
    prices = prices.sort_index().ffill()
    dates = list(prices.index)
    if len(dates) < lookback + 10:
        return FundingResult()
    rebalance_dates = {date for date in dates if date.weekday() == 0} if weekly else set(dates)
    positions: dict[str, Position] = {}
    result = FundingResult()
    daily = pd.Series(0.0, index=dates)

    for index, date in enumerate(dates):
        if index == 0:
            continue

        # 1) P&L de precio y funding de la cartera que ya estaba abierta.
        for symbol, position in list(positions.items()):
            if symbol not in prices.columns:
                continue
            price = float(prices[symbol].iloc[index])
            previous = float(prices[symbol].iloc[index - 1])
            if not np.isfinite(price) or not np.isfinite(previous) or previous <= 0:
                continue
            pnl = position.sign * (price / previous - 1.0) * position.notional
            position.price_pnl += pnl
            daily.iloc[index] += pnl / capital
            funded = funding.loc[date, symbol] if date in funding.index and symbol in funding.columns else np.nan
            if np.isfinite(funded) and position.entry_date < date:
                cash = -position.sign * float(funded) * position.notional
                position.funding_pnl += cash
                daily.iloc[index] += cash / capital

        # 2) Rebalanceo al cierre: cierra lo que sale, abre lo que entra.
        if date in rebalance_dates:
            signal = _zscore_signal(funding, date, lookback, raw)
            available = [
                symbol
                for symbol in signal.index
                if symbol in prices.columns and np.isfinite(prices[symbol].iloc[index])
            ]
            signal = signal[available].sort_values()
            if len(available) >= 10:
                count = max(2, int(round(len(available) * quantile)))
                longs = set(signal.index[:count])
                shorts = set(signal.index[-count:])
                target = {symbol: 1 for symbol in longs} | {symbol: -1 for symbol in shorts}
                notional = capital * 0.5 / count

                for symbol in list(positions):
                    if symbol not in target:
                        position = positions.pop(symbol)
                        close_cost = cost_per_side * position.notional
                        # El precio ya se devengo dia a dia; solo falta el coste de cierre.
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
                    if symbol in positions and positions[symbol].sign != sign:
                        flipped = positions.pop(symbol)
                        flip_cost = cost_per_side * flipped.notional
                        flipped.costs += flip_cost
                        daily.iloc[index] -= flip_cost / capital
                        result.episodes.append(
                            {
                                "symbol": symbol,
                                "sign": flipped.sign,
                                "entry": flipped.entry_date,
                                "exit": date,
                                "price_pnl": flipped.price_pnl,
                                "funding_pnl": flipped.funding_pnl,
                                "costs": flipped.costs,
                                "net": flipped.price_pnl + flipped.funding_pnl - flipped.costs,
                                "operations": 2,
                            }
                        )
                    if symbol in positions:
                        continue
                    price = float(prices[symbol].iloc[index])
                    if not np.isfinite(price) or price <= 0:
                        continue
                    position = Position(
                        symbol=symbol,
                        sign=sign,
                        notional=notional,
                        entry_date=date,
                        entry_price=price,
                    )
                    position.costs += cost_per_side * notional
                    daily.iloc[index] -= cost_per_side * notional / capital
                    positions[symbol] = position
                result.weeks += 1

    # 3) Cierra la cartera al final de la ventana para realizar el P&L.
    final_date = dates[-1]
    for symbol, position in list(positions.items()):
        price = float(prices[symbol].iloc[-1])
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
    parser = argparse.ArgumentParser(description="Carry cross-sectional de funding")
    parser.add_argument("--from", dest="start", default="2020-01-01")
    parser.add_argument("--to", dest="end", default="2026-11-01")
    parser.add_argument("--funding", default="data/funding_xs/funding_panel.csv")
    parser.add_argument("--prices", default="data/funding_xs/perp_1d_panel.csv")
    args = parser.parse_args()

    funding, prices = load_panels(Path(args.funding), Path(args.prices))
    funding = funding[(funding.index >= args.start) & (funding.index < args.end)]
    prices = prices[(prices.index >= args.start) & (prices.index < args.end)]
    years = (pd.Timestamp(args.end, tz="UTC") - pd.Timestamp(args.start, tz="UTC")).days / 365.25

    variants = [
        ("Q20-Z90-W", 90, 0.2, True, False),
        ("Q30-Z90-W", 90, 0.3, True, False),
        ("Q20-RAW-W", 90, 0.2, True, True),
        ("Q20-Z90-D", 90, 0.2, False, False),
        ("Q20-Z30-W", 30, 0.2, True, False),
    ]
    for name, lookback, quantile, weekly, raw in variants:
        result = run_funding_xs(funding, prices, lookback, quantile, weekly, raw)
        print(name, result.summary(years=years), flush=True)


if __name__ == "__main__":
    main()
