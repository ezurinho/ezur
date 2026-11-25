"""El ciclo de selección contra el motor real: specs, CSV temporal y universo."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from server import selection
from server.strategy import registry
from server.strategy.spec_schema import Params, load_spec

SPEC_ID = "BTC-TREND-15M"
SYMBOL = "BTCUSDT_PERP"


def _spec_document(**changes) -> dict:
    document = {
        "id": SPEC_ID,
        "name": "Ruptura de canal 15 m",
        "version": "1.0.0",
        "label": "trend_15m",
        "family": "trend",
        "hypothesis": (
            "Una ruptura del canal de 20 velas en 15 m conserva inercia "
            "suficiente para pagar los costes del perpetual."
        ),
        "instrument": SYMBOL,
        "timeframe_signal": "15m",
        "data_requirements": {
            "datasets": ["klines_5m"],
            "min_coverage": "2020-01-01/2026-01-01",
            "integrity": {"gaps": 0, "duplicates": 0, "timezone": "UTC"},
        },
        "entry": {
            "rule": "donchian_breakout",
            "long": "cierre > canal",
            "short": "cierre < canal",
        },
        "exit": {"stop": "atr_k * atr", "target": "tp_r * riesgo", "time_stop_bars": 40},
        "params": {"atr_k": 2.0, "tp_r": 2.0, "N": 20},
        "risk": {"sizing": "fixed_fractional", "risk_per_trade": 0.005, "max_mdd_budget": 0.2},
        "costs": {
            "fee_maker_bps": 2.0,
            "fee_taker_bps": 5.0,
            "assumed_fill": "taker",
            "half_spread_bps": 0.07,
            "impact_model": "none",
            "funding": "none",
        },
        "execution": {
            "signal_bar": "closed",
            "fill": "next_bar_open",
            "intrabar_priority": "stop_first",
            "gap_fill": "bar_open",
        },
        "validation": {"trials_declared": 1, "is_oos_split": "0.60/0.20/0.20", "seed": 7},
    }
    document.update(changes)
    return document


def _registered_spec(tmp_path: Path, monkeypatch, **changes):
    """Registra la spec y aísla el registro para no ensuciar otros tests."""
    monkeypatch.setattr(registry, "_SPEC_BUILDERS", dict(registry._SPEC_BUILDERS))
    monkeypatch.setattr(registry, "_SPEC_CACHE", dict(registry._SPEC_CACHE))
    path = tmp_path / f"{SPEC_ID}.json"
    path.write_text(json.dumps(_spec_document(**changes)), encoding="utf-8")
    spec = load_spec(path)
    registry.register_spec(spec.id, path)
    return spec


def _df5(bars: int = 3000, drift: float = 6.0, noise: float = 40.0, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    stamps = pd.date_range("2025-01-01", periods=bars, freq="5min", tz="UTC")
    close = 100_000 + np.cumsum(rng.normal(0.0, noise, bars) + drift)
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame(
        {
            "ts": stamps.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "symbol": SYMBOL,
            "o": open_,
            "h": np.maximum(open_, close) + rng.uniform(1, 30, bars),
            "l": np.minimum(open_, close) - rng.uniform(1, 30, bars),
            "c": close,
            "v": rng.uniform(1, 10, bars),
        }
    )


def _flat_df5(bars: int = 400) -> pd.DataFrame:
    stamps = pd.date_range("2025-01-01", periods=bars, freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "ts": stamps.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "symbol": SYMBOL,
            "o": 100.0,
            "h": 100.0,
            "l": 100.0,
            "c": 100.0,
            "v": 1.0,
        }
    )


# --- run_backtest_for_spec ---------------------------------------------------


def test_run_backtest_for_spec_devuelve_operaciones_y_metricas(tmp_path, monkeypatch):
    spec = _registered_spec(tmp_path, monkeypatch)

    trades, equity, metrics = selection.run_backtest_for_spec(spec, _df5())

    assert len(trades) > 0
    assert len(equity) > 0
    assert metrics["closed"]["trades"] == len(trades)
    assert list(trades.columns) == [
        "ts",
        "r_net",
        "r_gross",
        "symbol",
        "side",
        "pnl_net",
        "pnl_gross",
    ]
    assert trades["ts"].is_monotonic_increasing
    assert str(trades["ts"].dt.tz) == "UTC"


def test_run_backtest_for_spec_sin_operaciones_devuelve_vacio(tmp_path, monkeypatch):
    spec = _registered_spec(tmp_path, monkeypatch)

    trades, equity, metrics = selection.run_backtest_for_spec(spec, _flat_df5())

    assert trades.empty
    assert equity == []
    assert metrics == {}


def test_run_backtest_for_spec_sin_execution_ni_risk_usa_los_del_motor(monkeypatch):
    """Una spec sin execution/costs/risk no revienta: cae a los valores por defecto."""
    monkeypatch.setattr(registry, "_SPEC_BUILDERS", dict(registry._SPEC_BUILDERS))
    fake = SimpleNamespace(
        id="donchian",
        label="plugin",
        timeframe_signal="5m",
        instrument="BTC",
        params=Params(
            atr_k=1.5, tp_r=2.0, channel=20, atr_period=14, stop_atr=1.5, rr=2.0
        ),
        execution=None,
        costs=None,
        risk=None,
    )

    trades, equity, metrics = selection.run_backtest_for_spec(fake, _df5(bars=1500))

    assert isinstance(trades, pd.DataFrame)
    assert isinstance(equity, list)
    assert isinstance(metrics, dict)


def test_run_backtest_for_spec_con_estrategia_desconocida_no_tumba_el_ciclo(
    tmp_path, monkeypatch, capsys
):
    spec = _registered_spec(tmp_path, monkeypatch)
    registry._SPEC_BUILDERS.pop(spec.id, None)
    registry._SPEC_CACHE.pop(spec.id, None)

    trades, equity, metrics = selection.run_backtest_for_spec(spec, _df5(bars=200))

    assert trades.empty
    assert equity == []
    assert metrics == {}
    assert "ERROR" in capsys.readouterr().out


# --- run_universe ------------------------------------------------------------


def test_run_universe_construye_la_matriz_diaria(tmp_path, monkeypatch):
    spec = _registered_spec(tmp_path, monkeypatch)

    result, extra = selection.run_universe([spec], _df5(), quiet=True)

    matrix = result["matrix"]
    assert list(matrix.columns) == [spec.label]
    assert matrix.index.is_monotonic_increasing
    assert len(result["summary"]) == 1
    assert result["summary"][0]["trades"] == len(result["trades"][spec.label])
    assert extra["universe"] == result["summary"]


def test_run_universe_sin_operaciones_avisa_si_no_esta_quieto(tmp_path, monkeypatch, capsys):
    spec = _registered_spec(tmp_path, monkeypatch)

    result, _extra = selection.run_universe([spec], _flat_df5(), quiet=False)

    assert result["matrix"].empty
    assert result["summary"] == []
    assert "sin trades" in capsys.readouterr().out


def test_load_universe_specs_avisa_de_las_que_faltan(tmp_path, capsys):
    specs = selection.load_universe_specs(tmp_path)

    assert specs == []
    assert "not found" in capsys.readouterr().out


# --- ramas sueltas -----------------------------------------------------------


def test_probabilistic_sharpe_pide_treinta_observaciones():
    result = selection.probabilistic_sharpe(np.linspace(-0.01, 0.01, 20))

    assert result["psr"] is None
    assert "30" in result["reason"]


def test_cpcv_sin_combinaciones_validas_no_inventa_metricas():
    matrix = pd.DataFrame(
        np.zeros((20, 3)),
        index=pd.date_range("2024-01-01", periods=20, freq="D"),
        columns=["a", "b", "c"],
    )

    result = selection.cpcv(matrix, blocks=2, test_blocks=2, purge=0)

    assert result["paths"] == 0
    assert "sin combinaciones" in result["reason"]


# Los nombres de fichero son los que busca `load_universe_specs`; el contenido
# va en 5m nativo porque el motor remuestrea a `timeframe_signal` y un 1d sobre
# velas de 5m produce stops de decenas de miles de ticks.
UNIVERSE = [
    ("BTC-TREND-1D", "trend_n8", "5m", 8),
    ("BTC-TREND-4H", "trend_n12", "5m", 12),
    ("BTC-MOM-5M", "trend_n20", "5m", 20),
]


def test_window_recorta_inclusivo_excluyente():
    """--from entra y --to no: el corte de fin de año no debe colar la vela siguiente."""
    df = pd.DataFrame(
        {
            "ts": [
                "2024-12-31T23:55:00+00:00",
                "2025-01-01T00:00:00+00:00",
                "2025-06-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ]
        }
    )
    out = selection._window(
        df,
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert out["ts"].tolist() == [
        "2025-01-01T00:00:00+00:00",
        "2025-06-01T00:00:00+00:00",
    ]
    assert selection._window(df, None, None) is df


def test_run_selection_cycle_trae_operaciones_y_pf_reales(tmp_path, monkeypatch):
    """El resumen del ciclo no puede salir a cero: ahí se perdía metrics["closed"]."""
    monkeypatch.setattr(registry, "_SPEC_BUILDERS", dict(registry._SPEC_BUILDERS))
    monkeypatch.setattr(registry, "_SPEC_CACHE", dict(registry._SPEC_CACHE))

    data_dir = tmp_path / "data"
    specs_dir = data_dir / "specs"
    specs_dir.mkdir(parents=True)
    _df5(bars=60 * 288, drift=4.0, noise=25.0).to_pickle(data_dir / "btc_5m.pkl")

    for spec_id, label, timeframe, window in UNIVERSE:
        path = specs_dir / f"{spec_id}.json"
        path.write_text(
            json.dumps(
                _spec_document(
                    id=spec_id,
                    label=label,
                    timeframe_signal=timeframe,
                    params={"atr_k": 2.0, "tp_r": 2.0, "N": window},
                )
            ),
            encoding="utf-8",
        )
        registry.register_spec(spec_id, path)

    monkeypatch.setattr(selection, "ROOT", tmp_path)

    payload = selection.run_selection_cycle(
        cycle_id="CYCLE-TEST",
        blocks=6,
        folds=3,
        test_blocks=2,
        purge=1,
        spec_dir=specs_dir,
        quiet=True,
    )

    summary = payload["universe"]
    assert {row["name"] for row in summary} == {"trend_n8", "trend_n12", "trend_n20"}
    for row in summary:
        assert row["trades"] > 0, f"{row['name']} sin operaciones"
        assert row["pf_net"] > 0, f"{row['name']} con PF cero"
        assert row["exp_r"] != 0.0
        assert row["days"] > 0
    assert payload["inputs"]["daily_observations"] > 0
    assert payload["pbo"]["pbo"] is not None
    assert payload["wfa"]["evaluated_folds"] >= 1


def test_momentos_degenerados_se_reportan_sin_numero(monkeypatch):
    """Si el denominador del PSR no es positivo, se dice el motivo y no se inventa."""
    monkeypatch.setattr(selection, "_psr_from", lambda *args: None)
    returns = np.linspace(-0.01, 0.01, 60)

    dsr = selection.deflated_sharpe(returns, np.array([0.1, 0.2, 0.3]))
    psr = selection.probabilistic_sharpe(returns)

    assert dsr["dsr"] is None and "degenerados" in dsr["reason"]
    assert psr["psr"] is None and "degenerados" in psr["reason"]

