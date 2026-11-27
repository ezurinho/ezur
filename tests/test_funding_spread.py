"""El spread de funding cobra el extremo caro y no confunde precio con carry."""

import numpy as np
import pandas as pd
import pytest

from server.funding_spread import ASSETS, COST_PER_LEG_SIDE, VENUES, run_spread

START = pd.Timestamp("2024-01-01", tz="UTC")


def _panels(days: int = 120, high: float = 0.001) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range(START, periods=days, freq="D", tz="UTC")
    columns = pd.MultiIndex.from_product([["BTC"], list(VENUES)], names=["asset", "venue"])
    funding = pd.DataFrame(0.0, index=dates, columns=columns)
    funding[("BTC", "binance")] = high
    prices = pd.DataFrame(100.0, index=dates, columns=columns)
    return funding, prices


def test_largo_barato_y_corto_caro_cobran_el_spread():
    funding, prices = _panels()
    result = run_spread(
        funding,
        prices,
        lookback=7,
        rebalance="W",
        entry=0.12,
        exit=0.03,
        assets=("BTC",),
    )

    assert result.episodes
    assert all(item["long_venue"] == "okx" for item in result.episodes)
    assert all(item["short_venue"] == "binance" for item in result.episodes)
    summary = result.summary(capital=25_000.0)
    assert summary["funding_pnl_usd"] > 0
    assert summary["net_usd"] > 0
    assert abs(summary["price_pnl_usd"]) < 1e-6


def test_el_precio_delta_neutral_no_aporta_si_los_retornos_son_iguales():
    funding, prices = _panels()
    path = 1.001 ** np.arange(len(prices))
    for venue, level in (("binance", 100.0), ("okx", 200.0), ("hyperliquid", 50.0)):
        prices[("BTC", venue)] = level * path

    result = run_spread(
        funding,
        prices,
        lookback=7,
        rebalance="W",
        entry=0.12,
        exit=0.03,
        assets=("BTC",),
    )

    assert result.episodes
    assert abs(result.summary(capital=25_000.0)["price_pnl_usd"]) < 1e-6


def test_los_costes_reducen_el_neto_y_se_cobran_en_entrada_y_salida():
    funding, prices = _panels()
    cheap = run_spread(
        funding,
        prices,
        lookback=7,
        rebalance="W",
        entry=0.12,
        exit=0.03,
        assets=("BTC",),
        cost_per_leg_side=0.0,
    )
    expensive = run_spread(
        funding,
        prices,
        lookback=7,
        rebalance="W",
        entry=0.12,
        exit=0.03,
        assets=("BTC",),
        cost_per_leg_side=COST_PER_LEG_SIDE,
    )

    assert cheap.summary(capital=25_000.0)["net_usd"] > expensive.summary(capital=25_000.0)["net_usd"]
    expected = COST_PER_LEG_SIDE * 12_500.0 * 4.0
    assert all(item["costs"] == pytest.approx(expected) for item in expensive.episodes)


def test_el_max_hold_cierra_y_no_reentra_el_mismo_dia():
    funding, prices = _panels(days=120)
    result = run_spread(
        funding,
        prices,
        lookback=7,
        rebalance="W",
        entry=0.12,
        exit=0.03,
        assets=("BTC",),
        max_hold_days=28,
    )

    assert result.episodes
    assert all(item["days"] >= 28 for item in result.episodes[:-1])
    assert all(item["days"] <= 35 for item in result.episodes)


def test_sin_dispersion_de_funding_no_hay_posiciones():
    funding, prices = _panels(high=0.0)
    result = run_spread(
        funding,
        prices,
        lookback=7,
        rebalance="W",
        entry=0.12,
        exit=0.03,
        assets=("BTC",),
    )
    assert result.episodes == []


def test_la_entrada_usa_el_funding_hasta_t_menos_1():
    funding, prices = _panels(high=0.0, days=70)
    funding.loc[funding.index >= pd.Timestamp("2024-01-08", tz="UTC"), ("BTC", "binance")] = 0.001

    result = run_spread(
        funding,
        prices,
        lookback=7,
        rebalance="W",
        entry=0.12,
        exit=0.03,
        assets=("BTC",),
    )

    assert result.episodes
    assert result.episodes[0]["entry"] == pd.Timestamp("2024-01-15", tz="UTC")


def test_el_universo_declara_los_cinco_activos():
    assert ASSETS == ("BTC", "ETH", "SOL", "XRP", "DOGE")
