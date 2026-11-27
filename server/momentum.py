"""Momentum cross-sectional long-short, simulador determinista.

No usa el motor de ordenes: la cartera tiene varias patas y no lleva stop por
operacion. Mide la continuacion de retornos con un panel de perpetuos, con
ejecucion al cierre del dia siguiente y costes sobre el turnover.

Regla del pre-registro H3: en cada rebalanceo, largo los ``legs`` activos con
mejor retorno de los ultimos ``lookback`` dias y corto los ``legs`` peores,
equiponderados y dollar-neutral.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

COST_PER_LEG_SIDE = 0.0007  # 5 pb taker + 2 pb slippage
RISK_FRACTION = 0.01  # 1 % del capital por operacion, declarado en H3


@dataclass
class MomentumResult:
    daily: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    periods: list[dict] = field(default_factory=list)

    @property
    def net(self) -> float:
        return float((1.0 + self.daily).prod() - 1.0) if len(self.daily) else 0.0

    def summary(self, capital: float = 25_000.0, years: float | None = None) -> dict:
        if not len(self.daily) or years is None:
            years = len(self.daily) / 365.25 if len(self.daily) else 0.0
        equity = (1.0 + self.daily).cumprod()
        drawdown = float((equity / equity.cummax() - 1.0).min()) if len(equity) else 0.0
        period_net = [item["net"] for item in self.periods]
        gross_profit = sum(value for value in period_net if value > 0)
        gross_loss = -sum(value for value in period_net if value < 0)
        operations = sum(item["operations"] for item in self.periods)
        total_net = self.net * capital
        top5 = sum(sorted(period_net, reverse=True)[:5]) * capital
        return {
            "periods": len(self.periods),
            "operations": operations,
            "net_usd": round(total_net, 2),
            "net_pct": round(self.net * 100, 4),
            "cagr_pct": round(((1.0 + self.net) ** (1.0 / years) - 1.0) * 100, 4) if years > 0 else 0.0,
            "vol_pct": round(float(self.daily.std() * np.sqrt(365.25) * 100), 4),
            "sharpe": round(float(self.daily.mean() / self.daily.std() * np.sqrt(365.25)), 4) if self.daily.std() else 0.0,
            "max_dd_pct": round(drawdown * 100, 4),
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else 0.0,
            "expectancy_r": round(
                (sum(period_net) / operations) / RISK_FRACTION if operations else 0.0, 4
            ),
            "cost_r": round(
                (sum(item["cost"] for item in self.periods) / operations) / RISK_FRACTION
                if operations
                else 0.0,
                4,
            ),
            "pnl_without_top5": round(total_net - top5, 2),
            "total_costs_usd": round(sum(item["cost"] for item in self.periods) * capital, 2),
        }


def load_panel(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["dt"])
    return frame.pivot_table(index="dt", columns="symbol", values="close", aggfunc="last").sort_index()


def run_momentum(
    closes: pd.DataFrame,
    lookback: int,
    holding: int,
    legs: int = 2,
    capital: float = 25_000.0,
    cost_per_leg_side: float = COST_PER_LEG_SIDE,
    funding_drag_daily: float = 0.0,
) -> MomentumResult:
    """Ejecuta la regla congelada sobre el panel de cierres."""
    closes = closes.sort_index().ffill()
    returns = closes.pct_change()
    dates = list(closes.index)
    result = MomentumResult()

    # Lunes como ancla; para H=14 se toma uno de cada dos lunes. Asi el
    # rebalanceo no cae en un dia arbitrario del calendario.
    monday_indices = [
        index
        for index in range(lookback, len(dates) - 1)
        if dates[index].weekday() == 0
    ]
    step = max(holding // 7, 1)
    signal_dates = [dates[index] for position, index in enumerate(monday_indices) if position % step == 0]

    previous_target: dict[str, float] = {}
    total_operations = 0
    for signal_date in signal_dates:
        signal_index = dates.index(signal_date)
        execution_index = signal_index + 1
        if execution_index >= len(dates) - 1:
            break
        execution_date = dates[execution_index]
        end_index = min(execution_index + holding, len(dates) - 1)
        end_date = dates[end_index]

        history = closes.iloc[signal_index - lookback : signal_index + 1]
        momentum = (history.iloc[-1] / history.iloc[0] - 1.0).dropna()
        if len(momentum) < legs * 2:
            continue
        ranked = momentum.sort_values()
        shorts = list(ranked.index[:legs])
        longs = list(ranked.index[-legs:])
        target = {symbol: 0.5 / legs for symbol in longs}
        target.update({symbol: -0.5 / legs for symbol in shorts})

        turnover = sum(
            abs(target.get(symbol, 0.0) - previous_target.get(symbol, 0.0))
            for symbol in set(target) | set(previous_target)
        )
        cost = turnover * cost_per_leg_side

        period_returns = returns.loc[execution_date:end_date].iloc[1:]
        if period_returns.empty:
            continue
        portfolio = period_returns[list(target)].mul(pd.Series(target), axis=1).sum(axis=1)
        portfolio.iloc[0] -= cost
        if funding_drag_daily:
            portfolio -= funding_drag_daily
        result.daily = pd.concat([result.daily, portfolio])

        period_net = float((1.0 + portfolio).prod() - 1.0)
        operations = 2 * len(target)
        total_operations += operations
        result.periods.append(
            {
                "signal": signal_date,
                "execution": execution_date,
                "end": end_date,
                "longs": longs,
                "shorts": shorts,
                "turnover": round(turnover, 4),
                "cost": cost,
                "net": period_net,
                "operations": operations,
            }
        )
        previous_target = target

    if len(result.daily):
        result.daily = result.daily[~result.daily.index.duplicated(keep="last")].sort_index()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Momentum cross-sectional long-short")
    parser.add_argument("--from", dest="start", default="2020-01-01")
    parser.add_argument("--to", dest="end", default="2026-11-01")
    parser.add_argument("--panel", default="data/momentum/perp_1d_panel.csv")
    parser.add_argument("--capital", type=float, default=25_000.0)
    parser.add_argument("--funding-drag", type=float, default=0.0)
    args = parser.parse_args()

    closes = load_panel(Path(args.panel))
    closes = closes[(closes.index >= args.start) & (closes.index < args.end)]
    years = (pd.Timestamp(args.end, tz="UTC") - pd.Timestamp(args.start, tz="UTC")).days / 365.25
    variants = [(14, 7, 2), (28, 7, 2), (56, 7, 2), (28, 14, 2), (28, 7, 3)]
    for lookback, holding, legs in variants:
        result = run_momentum(
            closes,
            lookback,
            holding,
            legs,
            capital=args.capital,
            funding_drag_daily=args.funding_drag,
        )
        print(lookback, holding, legs, result.summary(years=years), flush=True)


if __name__ == "__main__":
    main()
