"""TSMOM long-only en perpetuos, simulador determinista.

Regla del pre-registro H6: senal de retorno de ``lookback`` dias al cierre del
lunes; se entra al cierre del martes solo si la senal es positiva, equal-weight
o inverso a volatilidad, rebalanceo semanal y costes por posicion. El resumen
compara contra BTC buy-and-hold porque una estrategia long-only puede ser beta.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

COST_PER_SIDE = 0.0007
CAPITAL = 25_000.0
RISK_FRACTION = 0.01


@dataclass
class Position:
    symbol: str
    notional: float
    entry_date: pd.Timestamp
    entry_price: float
    price_pnl: float = 0.0
    costs: float = 0.0


@dataclass
class TsmomResult:
    daily: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    episodes: list[dict] = field(default_factory=list)

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
            "pnl_without_top5": round(total_net - top5, 2),
            "costs_usd": round(sum(item["costs"] for item in self.episodes), 2),
        }


def load_prices(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["dt"])
    return frame.pivot_table(index="dt", columns="symbol", values="close", aggfunc="last").sort_index()


def buy_and_hold(prices: pd.DataFrame, symbol: str = "BTCUSDT") -> dict:
    series = prices[symbol].dropna()
    if len(series) < 2:
        return {}
    daily = series.pct_change().dropna()
    net = float((1.0 + daily).prod() - 1.0)
    equity = (1.0 + daily).cumprod()
    return {
        "symbol": symbol,
        "net_pct": round(net * 100, 4),
        "cagr_pct": round(((1.0 + net) ** (365.25 / len(daily)) - 1.0) * 100, 4),
        "max_dd_pct": round(float((equity / equity.cummax() - 1.0).min()) * 100, 4),
        "sharpe": round(float(daily.mean() / daily.std() * np.sqrt(365.25)), 4) if daily.std() else 0.0,
    }


def run_tsmom(
    prices: pd.DataFrame,
    lookback: int = 28,
    inverse_vol: bool = False,
    rebalance_days: int = 7,
    capital: float = CAPITAL,
    cost_per_side: float = COST_PER_SIDE,
) -> TsmomResult:
    prices = prices.sort_index().ffill()
    dates = list(prices.index)
    if len(dates) < lookback + 40:
        return TsmomResult()
    positions: dict[str, Position] = {}
    result = TsmomResult()
    daily = pd.Series(0.0, index=dates)
    last_rebalance: int | None = None

    for index, date in enumerate(dates):
        if index == 0:
            continue
        # P&L de precio de la cartera abierta.
        for symbol, position in list(positions.items()):
            price = float(prices[symbol].iloc[index])
            previous = float(prices[symbol].iloc[index - 1])
            if not np.isfinite(price) or not np.isfinite(previous) or previous <= 0:
                continue
            pnl = (price / previous - 1.0) * position.notional
            position.price_pnl += pnl
            daily.iloc[index] += pnl / capital

        # Rebalanceo: senal del cierre anterior, ejecucion al cierre de hoy.
        if date.weekday() != 1:  # martes
            continue
        if last_rebalance is not None and index - last_rebalance < rebalance_days:
            continue
        signal_date = index - 1
        if signal_date < lookback:
            continue
        signal = prices.iloc[signal_date] / prices.iloc[signal_date - lookback] - 1.0
        available = [
            symbol
            for symbol in prices.columns
            if np.isfinite(signal.get(symbol, np.nan))
            and np.isfinite(prices[symbol].iloc[index])
            and prices[symbol].iloc[index] > 0
        ]
        active = [symbol for symbol in available if signal[symbol] > 0]
        if not active:
            target: dict[str, float] = {}
        elif inverse_vol:
            vol = prices[active].pct_change().iloc[max(0, signal_date - 20) : signal_date].std() * np.sqrt(365.25)
            inv = (1.0 / vol.replace(0.0, np.nan)).dropna()
            target = {symbol: float(inv[symbol] / inv.sum()) for symbol in inv.index}
        else:
            target = {symbol: 1.0 / len(active) for symbol in active}

        for symbol in list(positions):
            if symbol not in target:
                position = positions.pop(symbol)
                close_cost = cost_per_side * position.notional
                position.costs += close_cost
                daily.iloc[index] -= close_cost / capital
                result.episodes.append(
                    {
                        "symbol": symbol,
                        "entry": position.entry_date,
                        "exit": date,
                        "price_pnl": position.price_pnl,
                        "costs": position.costs,
                        "net": position.price_pnl - position.costs,
                        "operations": 2,
                    }
                )
        for symbol, weight in target.items():
            if symbol in positions:
                continue
            price = float(prices[symbol].iloc[index])
            notional = capital * weight
            position = Position(symbol=symbol, notional=notional, entry_date=date, entry_price=price)
            position.costs += cost_per_side * notional
            daily.iloc[index] -= cost_per_side * notional / capital
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
                "entry": position.entry_date,
                "exit": final_date,
                "price_pnl": position.price_pnl,
                "costs": position.costs,
                "net": position.price_pnl - position.costs,
                "operations": 2,
            }
        )
    result.daily = daily
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="TSMOM long-only en perpetuos")
    parser.add_argument("--from", dest="start", default="2020-01-01")
    parser.add_argument("--to", dest="end", default="2026-11-01")
    parser.add_argument("--prices", default="data/funding_xs/perp_1d_panel.csv")
    args = parser.parse_args()

    prices = load_prices(Path(args.prices))
    prices = prices[(prices.index >= args.start) & (prices.index < args.end)]
    years = (pd.Timestamp(args.end, tz="UTC") - pd.Timestamp(args.start, tz="UTC")).days / 365.25
    bench = buy_and_hold(prices)
    variants = [
        ("H6-28-EW", 28, False, 7),
        ("H6-60-EW", 60, False, 7),
        ("H6-90-EW", 90, False, 7),
        ("H6-28-IV", 28, True, 7),
        ("H6-28-BI", 28, False, 14),
    ]
    for name, lookback, inverse, days in variants:
        result = run_tsmom(prices, lookback, inverse, days)
        print(name, result.summary(years=years), flush=True)
    print("BENCH", bench, flush=True)


if __name__ == "__main__":
    main()
