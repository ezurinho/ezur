"""Benchmark de entradas aleatorias: mismo stop, tamaño, número y filtros."""
from __future__ import annotations

import numpy as np
import pandas as pd

from server.random_entries import _simulate, random_entry_benchmark


def _bars(periods: int = 2_000, frequency: str = "15min") -> pd.DataFrame:
    rng = np.random.default_rng(4)
    stamps = pd.date_range("2024-01-01", periods=periods, freq=frequency, tz="UTC")
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.5, size=periods))
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame(
        {
            "o": open_,
            "h": np.maximum(open_, close) + 0.6,
            "l": np.minimum(open_, close) - 0.6,
            "c": close,
        },
        index=stamps,
    )


def _trades(bars: pd.DataFrame, count: int = 8) -> pd.DataFrame:
    rows = []
    for index in range(count):
        side = 1 if index % 2 == 0 else -1
        entry = float(bars["o"].iloc[index * 100 + 2])
        rows.append(
            {
                "opened_ts": bars.index[index * 100 + 1],
                "entry_price": entry,
                "stop_price": entry - side * 2.0,
                "target_price": entry + side * 2.0,
                "units": 3,
                "fees": 0.2,
                "pnl_net": 2.0 if index % 3 else -2.2,
                "side": "buy" if side > 0 else "sell",
            }
        )
    return pd.DataFrame(rows)


def test_el_benchmark_conserva_numero_de_operaciones_y_es_determinista():
    bars = _bars()
    trades = _trades(bars)

    result = random_entry_benchmark(
        trades,
        bars,
        config="cfg",
        iterations=12,
        seed=7,
        time_stop_bars=40,
        max_trades_per_day=4,
        cooldown_minutes=0,
    )
    repeated = random_entry_benchmark(
        trades,
        bars,
        config="cfg",
        iterations=12,
        seed=7,
        time_stop_bars=40,
        max_trades_per_day=4,
        cooldown_minutes=0,
    )

    assert result["available"] is True
    assert result["trades"] == len(trades)
    assert result["random_trades"] == len(trades)
    assert result["iterations_completed"] == 12
    assert 0.0 <= result["p_value"] <= 1.0
    assert 0.0 <= result["share_random_ge_actual"] <= 1.0
    assert result["same"]["trades"] is True
    assert result == repeated


def test_el_benchmark_respeta_el_cupo_diario_y_el_numero_exacto():
    bars = _bars(periods=96 * 10)
    trades = _trades(bars, count=6)

    result = random_entry_benchmark(
        trades,
        bars,
        iterations=5,
        seed=3,
        time_stop_bars=10,
        min_gap_bars=96,
        max_trades_per_day=1,
        cooldown_minutes=0,
    )

    assert result["available"] is True
    assert result["trades"] == 6
    assert result["random_trades"] == 6


def test_el_simulador_aplica_stop_primero_cuando_la_vela_toca_los_dos():
    bars = pd.DataFrame(
        {
            "o": [100.0, 100.0],
            "h": [101.0, 110.0],
            "l": [99.0, 90.0],
            "c": [100.0, 100.0],
        },
        index=pd.date_range("2024-01-01", periods=2, freq="15min", tz="UTC"),
    )

    exit_idx, exit_price, reason = _simulate(
        bars, 1, side=1, stop=95.0, target=105.0, time_stop_bars=1
    )

    assert exit_idx == 1
    assert exit_price == 95.0
    assert reason == "stop"


def test_sin_columnas_de_operacion_no_inventa_un_benchmark():
    result = random_entry_benchmark(
        pd.DataFrame({"pnl_net": [-1.0, 2.0]}), _bars(), iterations=2
    )

    assert result["available"] is False
    assert "faltan columnas" in result["reason"]
