from __future__ import annotations

import json

from server.config import Settings
from server.edge import measure, measure_path


def _settings() -> Settings:
    settings = Settings()
    settings.execution.commission_per_unit_side = 0.049
    settings.instruments.items[0].tick_size = 0.01
    settings.instruments.items[0].tick_value = 1e-05
    return settings


def _evidence(expectancy: float | None = 0.13, cost: float = 0.05) -> dict:
    document = {
        "execution": {
            "commission_per_unit_side": 0.049,
            "tick_size": 0.01,
            "tick_value": 1e-05,
        },
        "cost_per_trade_r_weighted": cost,
        "cost_per_trade_r": cost,
        "cost_method": "real_risk",
        "cost_scope": "out_of_sample",
        "split": {"out_of_sample": {"expectancy_r": expectancy}},
        "metrics": {"expectancy_r": expectancy, "trades": 105},
    }
    return document


def test_la_esperanza_que_supera_el_coste_pasa():
    guard = measure(_evidence(0.13), _settings())
    assert guard.passes is True
    assert "supera" in guard.detail()
    assert "+0.130" in guard.detail()
    assert "0.050" in guard.detail()


def test_la_esperanza_que_no_supera_el_coste_no_pasa():
    guard = measure(_evidence(0.03), _settings())
    assert guard.passes is False
    assert "no supera" in guard.detail()
    assert "+0.030" in guard.detail()
    assert "0.050" in guard.detail()


def test_empatar_no_es_superar():
    guard = measure(_evidence(0.05), _settings())
    assert guard.passes is False


def test_sin_tramo_fuera_de_muestra_usa_la_global():
    document = _evidence(0.13)
    document.pop("split")
    guard = measure(document, _settings())
    assert guard.scope == "global"
    assert guard.passes is True


def test_sin_modelo_de_ejecucion_no_hay_cifra_de_coste():
    document = _evidence(0.13)
    document.pop("execution")
    guard = measure(document, _settings())
    assert guard.cost_r is None
    assert guard.passes is None
    assert "modelo de ejecución" in (guard.reason or "")


def test_sin_evidencia_no_se_inventa_una_guarda(tmp_path):
    guard = measure(None, _settings())
    assert guard.passes is None
    assert guard.expectancy_r is None
    assert measure_path(tmp_path / "no-existe.json", _settings()) is None


def test_una_evidencia_ilegible_no_bloquea(tmp_path):
    path = tmp_path / "rota.json"
    path.write_text("{no es json", encoding="utf-8")
    assert measure_path(path, _settings()) is None


def test_la_evidencia_de_disco_se_mide_igual(tmp_path):
    path = tmp_path / "evidencia.json"
    path.write_text(json.dumps(_evidence(0.13)), encoding="utf-8")
    guard = measure_path(path, _settings())
    assert guard is not None
    assert guard.passes is True
