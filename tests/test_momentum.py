"""El momentum compra ganadores, vende perdedores y ejecuta al día siguiente."""

import numpy as np
import pandas as pd

from server.momentum import run_momentum

START = pd.Timestamp("2025-01-06", tz="UTC")  # lunes


def _panel() -> pd.DataFrame:
    dates = pd.date_range(START, periods=90, freq="D")
    index = np.arange(len(dates))
    closes = pd.DataFrame(
        {
            "WIN1": 100 * np.exp(0.010 * index),
            "WIN2": 100 * np.exp(0.008 * index),
            "FLAT1": 100 * np.exp(0.000 * index),
            "FLAT2": 100 * np.exp(0.000 * index),
            "LOSE1": 100 * np.exp(-0.008 * index),
            "LOSE2": 100 * np.exp(-0.010 * index),
        },
        index=dates,
    )
    return closes


def test_compra_ganadores_y_vende_perdedores():
    result = run_momentum(_panel(), lookback=7, holding=7, legs=2, capital=25_000)

    assert result.periods
    first = result.periods[0]
    assert set(first["longs"]) == {"WIN1", "WIN2"}
    assert set(first["shorts"]) == {"LOSE1", "LOSE2"}
    assert first["execution"] > first["signal"]
    assert first["cost"] > 0
    assert result.summary()["operations"] >= 8


def test_mas_costes_baja_el_neto():
    closes = _panel()
    cheap = run_momentum(closes, lookback=7, holding=7, legs=2, cost_per_leg_side=0.0)
    expensive = run_momentum(closes, lookback=7, holding=7, legs=2, cost_per_leg_side=0.01)

    assert cheap.summary()["net_pct"] > expensive.summary()["net_pct"]


def test_sin_historia_suficiente_no_hay_periodos():
    result = run_momentum(_panel().iloc[:5], lookback=28, holding=7, legs=2)
    assert result.periods == []
