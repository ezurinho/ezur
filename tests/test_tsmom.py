"""El TSMOM long-only entra en tendencia positiva y se queda fuera en negativa."""

import numpy as np
import pandas as pd

from server.tsmom import run_tsmom

START = pd.Timestamp("2024-01-01", tz="UTC")


def _prices(up: bool = True, days: int = 160) -> pd.DataFrame:
    dates = pd.date_range(START, periods=days, freq="D")
    index = np.arange(days)
    rising = 100.0 * np.exp(0.005 * index)
    falling = 100.0 * np.exp(-0.005 * index)
    if up:
        return pd.DataFrame({"UP": rising, "DOWN": falling}, index=dates)
    return pd.DataFrame({"UP": falling, "DOWN": falling * 0.9}, index=dates)


def test_entra_en_tendencia_positiva():
    result = run_tsmom(_prices(up=True), lookback=28)
    assert result.episodes
    assert result.summary()["net_usd"] > 0
    assert all(item["symbol"] == "UP" for item in result.episodes)


def test_en_tendencia_negativa_se_queda_fuera():
    result = run_tsmom(_prices(up=False), lookback=28)
    assert result.episodes == []


def test_los_costes_reducen_el_neto():
    prices = _prices(up=True)
    cheap = run_tsmom(prices, lookback=28, cost_per_side=0.0)
    expensive = run_tsmom(prices, lookback=28, cost_per_side=0.01)
    assert cheap.summary()["net_usd"] > expensive.summary()["net_usd"]
