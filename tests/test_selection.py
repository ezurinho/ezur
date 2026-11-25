"""El ciclo de selección: PBO, DSR, MinBTL, WFA y CPCV sobre datos sintéticos."""
from __future__ import annotations

import json
import math
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from server import selection


def _matrix(days: int = 240, configs: int = 5, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=days, freq="D")
    return pd.DataFrame(
        rng.normal(0.0, 0.01, size=(days, configs)),
        index=index,
        columns=[f"cfg{i}" for i in range(configs)],
    )


def _trade_log(seed: int = 3) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    stamps = pd.date_range("2024-01-01", periods=400, freq="6h", tz="UTC")
    frames = {}
    for name, edge in (("alpha", 0.2), ("beta", -0.1)):
        frames[name] = pd.DataFrame(
            {
                "ts": stamps,
                "r_net": rng.normal(edge, 1.0, size=len(stamps)),
            }
        )
    return frames


# --- normal -----------------------------------------------------------------


def test_norm_cdf_es_la_normal_estandar():
    assert selection.norm_cdf(0.0) == pytest.approx(0.5)
    assert selection.norm_cdf(1.959963984540054) == pytest.approx(0.975, abs=1e-9)
    assert selection.norm_cdf(-1.0) == pytest.approx(1 - selection.norm_cdf(1.0))


def test_norm_ppf_deshace_la_cdf_y_rechaza_los_extremos():
    assert selection.norm_ppf(0.5) == pytest.approx(0.0, abs=1e-6)
    assert selection.norm_ppf(0.975) == pytest.approx(1.96, abs=1e-3)
    assert math.isnan(selection.norm_ppf(0.0))
    assert math.isnan(selection.norm_ppf(1.0))


# --- sharpe -----------------------------------------------------------------


def test_sharpe_diario_pide_muestra_y_dispersion():
    assert selection.sharpe_daily(np.array([0.1, 0.2])) == 0.0
    assert selection.sharpe_daily(np.array([0.0, 0.0, 0.0, 0.0])) == 0.0
    assert selection.sharpe_daily(np.array([0.01, 0.02, 0.03, 0.04])) > 0


def test_sr_from_sums_coincide_con_el_sharpe_de_la_columna():
    values = np.array([0.01, -0.02, 0.03, 0.005, -0.001])
    sums = np.array([values.sum()])
    squares = np.array([(values**2).sum()])

    rendered = selection._sr_from_sums(sums, squares, float(values.size))

    assert rendered[0] == pytest.approx(selection.sharpe_daily(values))


def test_sr_from_sums_devuelve_cero_sin_varianza():
    rendered = selection._sr_from_sums(np.array([1.0]), np.array([1.0]), 1.0)
    assert rendered[0] == 0.0


# --- PBO --------------------------------------------------------------------


def test_cscv_pbo_exige_universo_y_serie():
    short = _matrix(days=10, configs=2)
    result = selection.cscv_pbo(short, blocks=10)

    assert result["pbo"] is None
    assert "demasiado cortos" in result["reason"]


def test_cscv_pbo_mide_la_seleccion_sobre_todas_las_particiones():
    result = selection.cscv_pbo(_matrix(), blocks=10)

    assert 0.0 <= result["pbo"] <= 1.0
    assert result["n_splits"] == math.comb(10, 5)
    assert result["blocks"] == 10
    assert set(result["most_selected"]) <= set(_matrix().columns)
    assert "CSCV" in result["method"]


# --- PSR y DSR --------------------------------------------------------------


def test_psr_degenerado_cuando_los_momentos_no_permiten_la_formula():
    assert selection._psr_from(1.0, 100, skew=10.0, kurt=3.0, sr0=0.0) is None


def test_deflated_sharpe_pide_observaciones():
    result = selection.deflated_sharpe(np.zeros(10), np.array([0.01, 0.02]))

    assert result["dsr"] is None
    assert "30 observaciones" in result["reason"]


def test_deflated_sharpe_pide_dispersion_entre_intentos():
    result = selection.deflated_sharpe(
        np.linspace(-1, 1, 100), np.array([0.02, 0.02, 0.02])
    )

    assert result["dsr"] is None
    assert "dispersión" in result["reason"]


def test_deflated_sharpe_penaliza_los_intentos():
    rng = np.random.default_rng(11)
    returns = rng.normal(0.002, 0.01, size=200)
    trials = rng.normal(0.0, 0.02, size=5)

    result = selection.deflated_sharpe(returns, trials)

    assert 0.0 <= result["dsr"] <= 1.0
    assert result["trials"] == 5
    assert result["observations"] == 200
    assert result["sr0_daily"] > 0


def test_min_backtest_length_sin_sharpe_positivo():
    result = selection.min_backtest_length(5, -0.2)

    assert result["minbtl_years"] is None
    assert "Sharpe no positivo" in result["reason"]


def test_min_backtest_length_crece_con_los_intentos():
    few = selection.min_backtest_length(2, 0.5)
    many = selection.min_backtest_length(50, 0.5)

    assert few["minbtl_years"] > 0
    assert many["minbtl_years"] > few["minbtl_years"]


def test_probabilistic_sharpe_pide_observaciones():
    result = selection.probabilistic_sharpe(np.zeros(5))

    assert result["psr"] is None
    assert "30 observaciones" in result["reason"]


def test_probabilistic_sharpe_mide_contra_cero_sin_deflactar():
    rng = np.random.default_rng(13)
    returns = rng.normal(0.002, 0.01, size=300)

    result = selection.probabilistic_sharpe(returns)

    assert 0.0 <= result["psr"] <= 1.0
    assert result["sr0_annual"] == 0.0
    assert "sin ajuste por multiplicidad" in result["method"]


# --- profit factor y walk-forward -------------------------------------------


def test_profit_factor_suma_ganancias_contra_perdidas():
    assert selection.pf(np.array([1.0, -0.5, 0.5])) == pytest.approx(3.0)
    assert selection.pf(np.array([1.0, 0.0])) == math.inf


def test_walk_forward_sin_operaciones_no_inventa_folds():
    result = selection.walk_forward({}, folds=5)

    assert result["folds"] == []
    assert result["min_trades_per_fold"] is None


def test_walk_forward_elige_en_cada_fold_y_mide_el_fuera_de_muestra():
    result = selection.walk_forward(_trade_log(), folds=4, min_is_trades=3)

    assert len(result["folds"]) == 4
    assert result["evaluated_folds"] == 4
    assert result["total_oos_trades"] > 0
    assert result["distinct_configs_chosen"] >= 1
    assert all(fold["chosen"] in {"alpha", "beta"} for fold in result["folds"])


def test_walk_forward_deja_el_fold_vacio_si_no_hay_historia():
    result = selection.walk_forward(_trade_log(), folds=3, min_is_trades=10_000)

    assert result["evaluated_folds"] == 0
    assert all(fold["chosen"] is None for fold in result["folds"])
    assert result["oos_pf_aggregate"] is None


# --- CPCV -------------------------------------------------------------------


def test_cpcv_exige_universo_y_serie():
    result = selection.cpcv(_matrix(days=10, configs=2), blocks=10)

    assert result["paths"] == 0
    assert "demasiado cortos" in result["reason"]


def test_cpcv_recorre_todas_las_particiones_con_purga():
    result = selection.cpcv(_matrix(), blocks=10, test_blocks=2, purge=1)

    assert result["paths"] == math.comb(10, 2)
    assert result["purge_blocks"] == 1
    assert 0.0 <= result["share_below_median"] <= 1.0
    assert 0.0 <= result["share_negative_oos"] <= 1.0


# --- universo y CLI ---------------------------------------------------------


def test_bars_for_devuelve_el_cinco_minutos_tal_cual():
    df5 = _matrix().rename(columns={"cfg0": "o", "cfg1": "h", "cfg2": "l", "cfg3": "c", "cfg4": "v"})

    bars, source = selection.bars_for(df5, "5m")

    assert source == "5m (native)"
    assert bars is df5


def test_bars_for_reexpresa_a_la_ventana_pedida():
    index = pd.date_range("2024-01-01", periods=24, freq="5min")
    df5 = pd.DataFrame(
        {
            "o": np.arange(24, dtype=float),
            "h": np.arange(24, dtype=float) + 1,
            "l": np.arange(24, dtype=float) - 1,
            "c": np.arange(24, dtype=float),
            "v": np.ones(24),
        },
        index=index,
    )

    bars, source = selection.bars_for(df5, "1h")

    assert source == "resampled from 5m"
    assert len(bars) == 2
    assert bars["h"].iloc[0] == 12


def test_load_universe_specs_avisa_de_las_que_faltan(tmp_path, capsys):
    assert selection.load_universe_specs(tmp_path) == []
    assert "no encontrada" in capsys.readouterr().out.replace("not found at", "no encontrada")


def test_el_ciclo_falla_sin_el_dataset_congelado(tmp_path, monkeypatch):
    monkeypatch.setattr(selection, "ROOT", tmp_path)

    with pytest.raises(FileNotFoundError):
        selection.run_selection_cycle(cycle_id="CYCLE-TEST", quiet=True)


def test_run_universe_sin_specs_no_inventa_matriz():
    result, extra = selection.run_universe([], pd.DataFrame())

    assert result["matrix"].empty
    assert extra["universe"] == []


def _fake_spec(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        label=name,
        id="BTC-TREND-15M",
        timeframe_signal="15m",
        _group="BTC-TREND-15M",
        model_dump=lambda mode="json": {"id": name},
    )


def test_el_ciclo_completo_produce_pbo_dsr_y_wfa(tmp_path, monkeypatch):
    monkeypatch.setattr(selection, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    rng = np.random.default_rng(5)
    index = pd.date_range("2024-01-01", periods=120 * 288, freq="5min")
    price = 100 + np.cumsum(rng.normal(0, 0.1, size=index.size))
    pd.DataFrame(
        {"o": price, "h": price + 0.2, "l": price - 0.2, "c": price, "v": 1.0},
        index=index,
    ).to_pickle(tmp_path / "data" / "btc_5m.pkl")

    specs = [_fake_spec(name) for name in ("a", "b", "c")]
    monkeypatch.setattr(selection, "load_universe_specs", lambda spec_dir: specs)

    def fake_backtest(spec, df5, quiet=False):
        stamps = pd.date_range("2024-01-02", periods=120, freq="D", tz="UTC")
        returns = rng.normal(0.05, 1.0, size=120)
        trades = pd.DataFrame(
            {"ts": stamps, "r_net": returns, "pnl_net": returns, "pnl_gross": returns}
        )
        return trades, [], {
            "closed": {"trades": 120, "profit_factor": 1.2, "expectancy_r": 0.1}
        }

    monkeypatch.setattr(selection, "run_backtest_for_spec", fake_backtest)

    payload = selection.run_selection_cycle(
        cycle_id="CYCLE-TEST", blocks=10, folds=3, quiet=True
    )

    assert payload["cycle_id"] == "CYCLE-TEST"
    assert payload["pbo"]["n_splits"] == math.comb(10, 5)
    assert payload["inputs"]["universe_size"] == 3
    assert payload["dsr_config"] in {"a", "b", "c"}
    assert payload["wfa"]["folds_requested"] == 3
    assert payload["dsr"]["source"] == "grupo BTC-TREND-15M"
    assert payload["psr"]["observations"] == 120
    assert len(payload["caveats"]) >= 5


def test_el_cli_escribe_el_json_del_ciclo(tmp_path, monkeypatch):
    monkeypatch.setattr(selection, "ROOT", tmp_path)
    monkeypatch.setattr(
        selection, "run_selection_cycle", lambda **kwargs: {"cycle_id": "CYCLE-TEST"}
    )
    monkeypatch.setattr(
        sys, "argv", ["selection", "--cycle", "CYCLE-TEST", "--quiet"]
    )

    selection.main()

    written = json.loads(
        (tmp_path / "data" / "validation" / "CYCLE-TEST.json").read_text(
            encoding="utf-8"
        )
    )
    assert written == {"cycle_id": "CYCLE-TEST"}


def test_el_ciclo_falla_sin_specs(tmp_path, monkeypatch):
    monkeypatch.setattr(selection, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    pd.DataFrame(
        {"o": [1.0], "h": [1.0], "l": [1.0], "c": [1.0], "v": [1.0]}
    ).to_pickle(tmp_path / "data" / "btc_5m.pkl")

    with pytest.raises(ValueError, match="No specs loaded"):
        selection.run_selection_cycle(cycle_id="CYCLE-TEST", quiet=True)
