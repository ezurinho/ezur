"""El carry cross-sectional cobra funding y no duplica el P&L de precio."""

import numpy as np
import pandas as pd

from server.funding_xs import run_funding_xs

START = pd.Timestamp("2024-01-01", tz="UTC")


def _panels(days: int = 220) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range(START, periods=days, freq="D")
    symbols = [f"S{i}" for i in range(12)]
    wave = np.sin(np.arange(days)[:, None] / 5.0 + np.arange(12)[None, :])
    funding = pd.DataFrame(0.00005 * wave, index=dates, columns=symbols)
    funding.iloc[:-7, 0] = 0.0005
    funding.iloc[-7:, 0] = 0.002
    funding.iloc[:-7, 1] = -0.0005
    funding.iloc[-7:, 1] = -0.002
    prices = pd.DataFrame(100.0, index=dates, columns=symbols)
    return funding, prices


def test_corto_recibe_funding_positivo_y_largo_el_negativo():
    funding, prices = _panels()
    result = run_funding_xs(funding, prices, lookback=90, quantile=0.2, weekly=True)

    assert result.episodes
    late = [item for item in result.episodes if item["symbol"] in ("S0", "S1")]
    assert late
    assert all(item["funding_pnl"] > 0 for item in late)
    assert abs(result.summary()["price_pnl_usd"]) < 1e-6


def test_los_costes_reducen_el_neto():
    funding, prices = _panels()
    cheap = run_funding_xs(funding, prices, cost_per_side=0.0)
    expensive = run_funding_xs(funding, prices, cost_per_side=0.01)
    assert cheap.summary()["net_usd"] > expensive.summary()["net_usd"]


def test_sin_dispersion_no_hay_posiciones():
    dates = pd.date_range(START, periods=200, freq="D")
    symbols = [f"S{i}" for i in range(12)]
    funding = pd.DataFrame(0.0, index=dates, columns=symbols)
    prices = pd.DataFrame(100.0, index=dates, columns=symbols)
    result = run_funding_xs(funding, prices)
    assert result.episodes == []
