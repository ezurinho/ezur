"""La métrica de coste usa el riesgo real, no el presupuesto nominal.

El ponderado (fees totales / riesgo total) es el comparable con el nominal y
el que usa la puerta. El simple (media de fees/riesgo por operación) se queda
como distribución: no se mezcla con el nominal ni decide la aprobación.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from server.promotion import cost_metrics, cost_per_trade_r, evaluate

EXECUTION = {
    "commission_per_unit_side": 0.05,
    "tick_size": 0.01,
    "tick_value": 0.01,
}
EVIDENCE_REAL = {
    "strategy": {"id": "reference", "version": "0.1.0"},
    "dataset": "data/BTC_1m_2025.csv",
    "split": {"out_of_sample": {"trades": 100, "profit_factor": 1.30}},
    "metrics": {"trades": 2, "fees": 20.0},
    "risk_budget": 100.0,
    "execution": EXECUTION,
    "cost_per_trade_r": 0.30,
    "cost_per_trade_r_weighted": 0.30,
    "cost_per_trade_r_simple": 0.90,
    "cost_method": "real_risk",
    "cost_scope": "out_of_sample",
    "avg_risk_per_trade": 75.0,
    "avg_stop_ticks": 75.0,
}


def test_cost_metrics_uses_each_trade_risk_not_the_budget():
    trades = [
        SimpleNamespace(entry_price=100.0, stop_price=99.0, units=100, fees=10.0),
        SimpleNamespace(entry_price=100.0, stop_price=99.5, units=100, fees=10.0),
    ]
    metrics = cost_metrics(trades, EXECUTION, budget=100.0, max_units=100)
    # Riesgos: 100 $ y 50 $; costes: 0,10 R y 0,20 R.
    assert metrics["trades"] == 2
    assert metrics["avg_risk_per_trade"] == pytest.approx(75.0)
    assert metrics["avg_stop_ticks"] == pytest.approx(75.0)
    # Ponderado: 20 $ de fees / 150 $ de riesgo = 0,1333 R; es el comparable
    # con el nominal y el que debe usar la puerta.
    assert metrics["cost_per_trade_r"] == pytest.approx(20.0 / 150.0)
    assert metrics["cost_per_trade_r_weighted"] == pytest.approx(20.0 / 150.0)
    # Simple: media de 0,10 y 0,20 = 0,15 R; es distribución, no la métrica.
    assert metrics["cost_per_trade_r_simple"] == pytest.approx(0.15)
    assert metrics["cost_per_trade_r_median"] == pytest.approx(0.15)
    assert metrics["cost_per_trade_r_p90"] == pytest.approx(0.19)
    assert metrics["cost_per_trade_r_p99"] == pytest.approx(0.199)
    assert metrics["cost_above_1r"] == 0
    assert metrics["cost_min"] == pytest.approx(0.10)
    assert metrics["cost_max"] == pytest.approx(0.20)
    # El nominal (fees / ops / presupuesto) diría 0,10 R: se queda corto.
    assert metrics["cost_per_trade_r_nominal"] == pytest.approx(0.10)
    assert metrics["risk_budget_utilization"] == pytest.approx(0.75)
    assert metrics["trades_at_cap"] == 2


def test_gate_uses_the_measured_real_cost():
    cost, reason = cost_per_trade_r(EVIDENCE_REAL, EXECUTION)
    assert reason == ""
    assert cost == pytest.approx(0.30)
    # El nominal sería 20 $ / 2 ops / 100 $ = 0,10 R y pasaría el límite.
    check = next(
        item
        for item in evaluate(EVIDENCE_REAL, execution=EXECUTION)["checks"]
        if item["name"] == "coste_por_operacion"
    )
    assert check["value"] == pytest.approx(0.30)
    assert check["method"] == "real_risk"
    assert check["metric"] == "weighted"
    assert check["simple"] == pytest.approx(0.90)
    assert check["scope"] == "out_of_sample"
    assert check["pass"] is False


def test_el_simple_es_distribucion_y_no_aprueba():
    cheap_weighted = {
        **EVIDENCE_REAL,
        "cost_per_trade_r": 0.20,
        "cost_per_trade_r_weighted": 0.20,
        "cost_per_trade_r_simple": 1.50,
    }
    check = next(
        item
        for item in evaluate(cheap_weighted, execution=EXECUTION)["checks"]
        if item["name"] == "coste_por_operacion"
    )
    # La media simple es alta, pero el ponderado es el que decide.
    assert check["value"] == pytest.approx(0.20)
    assert check["simple"] == pytest.approx(1.50)
    assert check["metric"] == "weighted"
    assert check["pass"] is True


def test_el_coste_real_tiene_que_ser_del_tramo_fuera_de_muestra():
    evidence = {**EVIDENCE_REAL, "cost_scope": "all"}
    check = next(
        item
        for item in evaluate(evidence, execution=EXECUTION)["checks"]
        if item["name"] == "coste_por_operacion"
    )
    assert check["value"] is None
    assert check["method"] == "unknown"
    assert check["pass"] is False
    assert "fuera de muestra" in check["reason"]


def test_sin_modelo_de_ejecucion_el_metodo_es_desconocido():
    check = next(
        item
        for item in evaluate(EVIDENCE_REAL, execution=None)["checks"]
        if item["name"] == "coste_por_operacion"
    )
    assert check["value"] is None
    assert check["method"] == "unknown"
    assert check["metric"] == "unknown"
    assert check["pass"] is False


def test_real_cost_is_repriced_with_the_profile_execution():
    profile = {**EXECUTION, "commission_per_unit_side": 0.10}
    cost, reason = cost_per_trade_r(EVIDENCE_REAL, profile)
    assert reason == ""
    assert cost == pytest.approx(0.60)


def test_trade_without_stop_or_risk_is_skipped():
    trades = [
        SimpleNamespace(entry_price=100.0, stop_price=None, units=100, fees=10.0),
        SimpleNamespace(entry_price=100.0, stop_price=100.0, units=100, fees=10.0),
    ]
    metrics = cost_metrics(trades, EXECUTION, budget=100.0)
    assert metrics["trades"] == 0
    assert metrics["cost_per_trade_r"] is None
    assert metrics["cost_per_trade_r_simple"] is None
