"""Carry delta-neutral de funding, simulador determinista.

No usa el motor de órdenes: el carry no tiene stop ni una sola pata, y meterlo
en el engine de spot daría un P&L falso. Este modulo mide la prima de funding y
el basis con datos congelados y costes explicitos.

La regla es la del pre-registro H2: media de los ultimos ``window`` pagos de
funding; si supera ``threshold`` se entra largo spot / corto perpetuo, y se sale
cuando la media cae por debajo de cero. La entrada y la salida se ejecutan en el
siguiente pago (rejilla de 8 h), con el cierre de esa vela.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# Un movimiento adverso de basis del 1,5 % del nocional es la unidad de riesgo
# declarada para comparar con las puertas en R; el carry no tiene stop.
RISK_FRACTION = 0.015


@dataclass
class CarryEpisode:
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    spot_entry: float
    spot_exit: float
    perp_entry: float
    perp_exit: float
    funding: float
    basis: float
    costs: float
    net: float
    net_pct: float


@dataclass
class CarryResult:
    episodes: list[CarryEpisode] = field(default_factory=list)

    @property
    def net(self) -> float:
        return sum(item.net for item in self.episodes)

    @property
    def gross_profit(self) -> float:
        return sum(item.net for item in self.episodes if item.net > 0)

    @property
    def gross_loss(self) -> float:
        return -sum(item.net for item in self.episodes if item.net < 0)

    @property
    def profit_factor(self) -> float:
        return self.gross_profit / self.gross_loss if self.gross_loss else 0.0

    def summary(self, capital: float = 25_000.0, years: float = 1.0) -> dict:
        net = self.net
        return {
            "episodes": len(self.episodes),
            "wins": sum(1 for item in self.episodes if item.net > 0),
            "profit_factor": round(self.profit_factor, 4),
            "net_usd": round(net, 2),
            "net_pct": round(net / capital * 100, 4),
            "annual_pct": round(net / capital / years * 100, 4),
            "funding_usd": round(sum(item.funding for item in self.episodes), 2),
            "basis_usd": round(sum(item.basis for item in self.episodes), 2),
            "costs_usd": round(sum(item.costs for item in self.episodes), 2),
            "avg_days": round(
                sum((item.exit_ts - item.entry_ts).total_seconds() / 86400 for item in self.episodes)
                / max(len(self.episodes), 1),
                1,
            ),
            "expectancy_r": round(
                net / max(len(self.episodes), 1) / (capital * RISK_FRACTION), 4
            ),
            "cost_r": round(
                sum(item.costs for item in self.episodes)
                / max(len(self.episodes), 1)
                / (capital * RISK_FRACTION),
                4,
            ),
        }


def load_funding(path: Path) -> pd.Series:
    frame = pd.read_csv(path, parse_dates=["dt"])
    frame = frame.sort_values("dt")
    return frame.set_index("dt")["rate"]


def load_prices(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["dt"])
    frame = frame.sort_values("dt")
    return frame.set_index("dt")["c"]


def load_spot(path: Path) -> pd.Series:
    frame = pd.read_pickle(path)
    stamp = pd.to_datetime(frame["ts"], utc=True)
    frame = frame.set_index(stamp).sort_index()
    return frame["c"]


def run_carry(
    funding: pd.Series,
    spot: pd.Series,
    perp: pd.Series,
    window: int,
    threshold: float,
    capital: float = 25_000.0,
    cost_round_trip: float = 0.0025,
    notional: float | None = None,
) -> CarryResult:
    """Ejecuta la regla congelada y devuelve los episodios cerrados."""
    notional = notional or capital
    grid = funding.index
    spot_8h = spot.resample("8h").last().reindex(grid).ffill()
    perp_8h = perp.resample("8h").last().reindex(grid).ffill()
    signal = funding.rolling(window).mean()

    result = CarryResult()
    position = False
    entry_index: int | None = None
    for index in range(window, len(grid) - 1):
        value = signal.iloc[index]
        if pd.isna(value):
            continue
        if not position and value > threshold:
            position = True
            entry_index = index + 1  # se ejecuta en el siguiente pago
        elif position and value < 0 and entry_index is not None:
            exit_index = index + 1
            if exit_index <= entry_index:
                continue
            spot_entry = float(spot_8h.iloc[entry_index])
            spot_exit = float(spot_8h.iloc[exit_index])
            perp_entry = float(perp_8h.iloc[entry_index])
            perp_exit = float(perp_8h.iloc[exit_index])
            # Nocional constante: el carry se rebalancea para no convertirse en
            # un apalancamiento creciente cuando BTC sube. El funding se cobra
            # sobre el nocional fijo; el basis es la unica parte de precio que
            # no cancela entre la pata larga de spot y la corta de perpetuo.
            quantity = notional / spot_entry
            basis = quantity * (
                (perp_entry - spot_entry) - (perp_exit - spot_exit)
            )
            funding_pnl = float(
                sum(notional * float(funding.iloc[step]) for step in range(entry_index + 1, exit_index + 1))
            )
            costs = notional * cost_round_trip
            net = funding_pnl + basis - costs
            result.episodes.append(
                CarryEpisode(
                    entry_ts=grid[entry_index],
                    exit_ts=grid[exit_index],
                    spot_entry=spot_entry,
                    spot_exit=spot_exit,
                    perp_entry=perp_entry,
                    perp_exit=perp_exit,
                    funding=funding_pnl,
                    basis=basis,
                    costs=costs,
                    net=net,
                    net_pct=net / notional,
                )
            )
            position = False
            entry_index = None
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Carry delta-neutral de funding")
    parser.add_argument("--from", dest="start", default="2020-01-01")
    parser.add_argument("--to", dest="end", default="2026-11-01")
    parser.add_argument("--capital", type=float, default=25_000.0)
    parser.add_argument("--funding", default="data/funding/BTCUSDT_funding_binance.csv")
    parser.add_argument("--perp", default="data/BTC-USDT-SWAP_1h.csv")
    parser.add_argument("--spot", default="data/btc_5m_spot_canonical.pkl")
    args = parser.parse_args()

    funding = load_funding(Path(args.funding))
    funding = funding[(funding.index >= args.start) & (funding.index < args.end)]
    spot = load_spot(Path(args.spot))
    perp = load_prices(Path(args.perp))
    years = (pd.Timestamp(args.end, tz="UTC") - pd.Timestamp(args.start, tz="UTC")).days / 365.25

    variants = [(9, 0.00005), (21, 0.00005), (63, 0.00005), (21, 0.0001), (9, 0.000025)]
    for window, threshold in variants:
        result = run_carry(funding, spot, perp, window, threshold, capital=args.capital)
        summary = result.summary(capital=args.capital, years=years)
        print(window, threshold, summary, flush=True)


if __name__ == "__main__":
    main()
