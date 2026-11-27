"""Reversion de pares spot contra BTC, simulador determinista.

Regla del pre-registro H4: z-score del logaritmo del par contra su media y
desviacion de ``lookback`` dias; se entra cuando ``|z| > threshold`` y se sale
cuando ``|z| < exit_z`` o tras ``max_hold`` dias. Ejecucion al cierre del dia
siguiente, costes por pata y lado, cartera dollar-neutral repartida en 6 pares.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

COST_PER_LEG_SIDE = 0.0007
EXIT_Z = 0.5
MAX_HOLD = 30
RISK_FRACTION = 0.01


@dataclass
class PairResult:
    daily: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    episodes: list[dict] = field(default_factory=list)

    @property
    def net(self) -> float:
        return float((1.0 + self.daily).prod() - 1.0) if len(self.daily) else 0.0

    def summary(self, capital: float = 25_000.0, years: float | None = None) -> dict:
        if years is None:
            years = len(self.daily) / 365.25 if len(self.daily) else 0.0
        equity = (1.0 + self.daily).cumprod()
        drawdown = float((equity / equity.cummax() - 1.0).min()) if len(equity) else 0.0
        pnl = [item["net"] for item in self.episodes]
        gross_profit = sum(value for value in pnl if value > 0)
        gross_loss = -sum(value for value in pnl if value < 0)
        operations = sum(item["operations"] for item in self.episodes)
        total_net = self.net * capital
        top5 = sum(sorted(pnl, reverse=True)[:5])
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
            "expectancy_r": round((sum(pnl) / operations) / (capital * RISK_FRACTION) if operations else 0.0, 4),
            "cost_r": round((sum(item["costs"] for item in self.episodes) / operations) / (capital * RISK_FRACTION) if operations else 0.0, 4),
            "pnl_without_top5": round(total_net - top5, 2),
            "total_costs_usd": round(sum(item["costs"] for item in self.episodes), 2),
        }


def load_pairs(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["dt"])
    return frame.pivot_table(index="dt", columns="symbol", values="close", aggfunc="last").sort_index()


def run_pairs(
    closes: pd.DataFrame,
    lookback: int,
    threshold: float,
    capital: float = 25_000.0,
    cost_per_leg_side: float = COST_PER_LEG_SIDE,
    max_hold: int = MAX_HOLD,
    exit_z: float = EXIT_Z,
) -> PairResult:
    closes = closes.sort_index().ffill()
    n_pairs = len(closes.columns)
    leg_notional = capital / (2.0 * n_pairs)
    zscores = {
        symbol: (np.log(closes[symbol]) - np.log(closes[symbol]).rolling(lookback).mean())
        / np.log(closes[symbol]).rolling(lookback).std()
        for symbol in closes.columns
    }
    dates = list(closes.index)
    result = PairResult()
    open_positions: dict[str, dict] = {}
    daily = pd.Series(0.0, index=dates)

    for index, date in enumerate(dates):
        if index < lookback + 1:
            continue
        for symbol in closes.columns:
            price = float(closes[symbol].iloc[index])
            previous = float(closes[symbol].iloc[index - 1])
            if not np.isfinite(price) or not np.isfinite(previous) or previous <= 0:
                continue
            position = open_positions.get(symbol)
            if position is None:
                z = zscores[symbol].iloc[index - 1]
                if np.isfinite(z) and abs(z) > threshold:
                    open_positions[symbol] = {
                        "entry_index": index,
                        "entry_price": price,
                        "direction": 1.0 if z < 0 else -1.0,
                    }
                    daily.iloc[index] -= 2.0 * cost_per_leg_side * leg_notional / capital
                continue
            daily.iloc[index] += (
                position["direction"] * (price / previous - 1.0) * leg_notional / capital
            )
            held = index - position["entry_index"]
            # La senal de salida es la del cierre anterior: se ejecuta hoy, no
            # con el mismo cierre que la genera.
            z = zscores[symbol].iloc[index - 1]
            if (np.isfinite(z) and abs(z) < exit_z) or held >= max_hold:
                gross = position["direction"] * (price / position["entry_price"] - 1.0)
                costs = 4.0 * cost_per_leg_side * leg_notional
                result.episodes.append(
                    {
                        "symbol": symbol,
                        "entry": dates[position["entry_index"]],
                        "exit": date,
                        "direction": position["direction"],
                        "gross": gross * leg_notional,
                        "costs": costs,
                        "net": gross * leg_notional - costs,
                        "operations": 4,
                    }
                )
                daily.iloc[index] -= 2.0 * cost_per_leg_side * leg_notional / capital
                del open_positions[symbol]

    result.daily = daily[daily.index >= dates[min(lookback + 1, len(dates) - 1)]]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Reversion de pares spot contra BTC")
    parser.add_argument("--from", dest="start", default="2020-01-01")
    parser.add_argument("--to", dest="end", default="2026-11-01")
    parser.add_argument("--panel", default="data/pairs/spot_pairs_1d.csv")
    parser.add_argument("--capital", type=float, default=25_000.0)
    args = parser.parse_args()

    closes = load_pairs(Path(args.panel))
    closes = closes[(closes.index >= args.start) & (closes.index < args.end)]
    years = (pd.Timestamp(args.end, tz="UTC") - pd.Timestamp(args.start, tz="UTC")).days / 365.25
    for lookback, threshold in ((20, 2.0), (30, 2.0), (60, 2.0), (30, 1.5), (30, 2.5)):
        result = run_pairs(closes, lookback, threshold, capital=args.capital)
        print(lookback, threshold, result.summary(capital=args.capital, years=years), flush=True)


if __name__ == "__main__":
    main()
