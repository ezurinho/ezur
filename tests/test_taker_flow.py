"""El flujo de taker compra el flujo alto y vende el bajo, después de costes."""

import numpy as np
import pandas as pd

from server.taker_flow import run_flow

START = pd.Timestamp("2024-01-01", tz="UTC")


def _panels(days: int = 160):
    dates = pd.date_range(START, periods=days, freq="D")
    symbols = ["BTCUSDT"] + [f"S{i}" for i in range(1, 12)]
    index = np.arange(days)[:, None]
    close = pd.DataFrame(
        100.0 * np.exp(0.002 * index * np.ones((1, 12)) + 0.001 * np.sin(index / 5 + np.arange(12))),
        index=dates,
        columns=symbols,
    )
    ratio = pd.DataFrame(
        0.5 + 0.05 * np.sin(index / 7 + np.arange(12)),
        index=dates,
        columns=symbols,
    )
    ratio["BTCUSDT"] = 0.5 + 0.001 * np.arange(days)
    ratio["S1"] = 0.5 - 0.001 * np.arange(days)
    notional = pd.DataFrame(50_000_000.0, index=dates, columns=symbols)
    funding = pd.DataFrame(0.0, index=dates, columns=symbols)
    return ratio, close, notional, funding


def test_compra_el_flujo_alto_y_vende_el_bajo():
    ratio, close, notional, funding = _panels()
    result = run_flow(ratio, close, notional, funding, lookback=20, signal_days=3, hold=3)
    assert result.episodes
    late = [item for item in result.episodes if item["symbol"] in ("BTCUSDT", "S1")]
    assert late
    assert any(item["symbol"] == "BTCUSDT" and item["sign"] == 1 for item in late)
    assert any(item["symbol"] == "S1" and item["sign"] == -1 for item in late)


def test_los_costes_reducen_el_neto():
    ratio, close, notional, funding = _panels()
    cheap = run_flow(ratio, close, notional, funding, cost_per_side=0.0)
    expensive = run_flow(ratio, close, notional, funding, cost_per_side=0.01)
    assert cheap.summary()["net_usd"] > expensive.summary()["net_usd"]


def test_btc_time_series_solo_largo():
    ratio, close, notional, funding = _panels()
    result = run_flow(
        ratio, close, notional, funding, lookback=20, signal_days=3, hold=1,
        long_only=True, threshold=1.0,
    )
    assert all(item["sign"] == 1 for item in result.episodes)
