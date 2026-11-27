"""El pairs entra en la desviación, sale en la reversión y paga costes."""

import numpy as np
import pandas as pd

from server.pairs import run_pairs

START = pd.Timestamp("2025-01-01", tz="UTC")


def _panel() -> pd.DataFrame:
    dates = pd.date_range(START, periods=120, freq="D")
    index = np.arange(len(dates))
    base = 0.02 * np.sin(index / 6.0)
    return pd.DataFrame({"ETHBTC": 0.05 * np.exp(base)}, index=dates)


def test_entra_en_la_desviacion_y_sale_en_la_reversion():
    result = run_pairs(_panel(), lookback=20, threshold=1.5, exit_z=0.3, max_hold=40)

    assert result.episodes
    first = result.episodes[0]
    assert first["entry"] > START
    assert first["exit"] > first["entry"]
    assert first["operations"] == 4
    assert first["costs"] > 0


def test_mas_costes_baja_el_neto():
    cheap = run_pairs(_panel(), lookback=20, threshold=1.5, cost_per_leg_side=0.0)
    expensive = run_pairs(_panel(), lookback=20, threshold=1.5, cost_per_leg_side=0.01)
    assert cheap.summary()["net_pct"] > expensive.summary()["net_pct"]


def test_sin_desviacion_no_hay_episodios():
    dates = pd.date_range(START, periods=80, freq="D")
    flat = pd.DataFrame({"ETHBTC": 0.05}, index=dates)
    result = run_pairs(flat, lookback=20, threshold=2.0)
    assert result.episodes == []
