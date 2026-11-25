"""La puerta mide el coste con la ejecución del perfil que va a operar.

El 24/11 la evidencia declaraba 0,0375 R por operación y el paper pagaba 0,26 R:
la puerta aprobaba el criterio con la comisión de otra corrida. Estas pruebas
fijan la corrección, la paridad con el coste **ponderado** (fees totales /
riesgo total), el límite de divergencia y el rechazo del coste heredado cuando
falta el perfil. El coste simple queda como distribución, no como comparable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.promotion import cost_per_trade_r, evaluate

RESEARCH_EXECUTION = {
    "commission_per_unit_side": 25.2279,
    "tick_size": 0.01,
    "tick_value": 0.01,
}
PROFILE_EXECUTION = {
    "commission_per_unit_side": 0.049,
    "tick_size": 0.01,
    "tick_value": 1e-05,
}
EVIDENCE = {
    "strategy": {"id": "reference", "version": "0.1.0"},
    "dataset": "data/BTC_1m_2025.csv",
    "split": {"out_of_sample": {"trades": 0, "profit_factor": 0.0}},
    "metrics": {"trades": 234, "fees": 2195.788},
    "risk_budget": 250.0,
    "execution": RESEARCH_EXECUTION,
    "cost_per_trade_r": 0.0375348376068376,
}
# Un trade real del paper: 160 unidades, stop a 370,22 $ y 15,68 $ de comisión.
PAPER_UNITS = 160
PAPER_STOP_TICKS = 37022
PAPER_FEES = 0.049 * PAPER_UNITS * 2
PAPER_RISK = PAPER_UNITS * 1e-05 * PAPER_STOP_TICKS
# Agregado de las 13 operaciones cerradas del paper (desglose 24/11):
# ponderado = fees totales / riesgo total; simple = media por operación.
PAPER_TRADES = 13
PAPER_WEIGHTED_COST = 0.3163128017
PAPER_SIMPLE_COST = 0.3318228842


def test_el_coste_de_un_trade_es_un_punto_de_la_distribucion():
    single = PAPER_FEES / PAPER_RISK
    assert single == pytest.approx(0.2647, rel=1e-3)
    # Un solo trade no es el agregado del paper: no se usa para la paridad.
    assert single != pytest.approx(PAPER_WEIGHTED_COST)


def test_la_puerta_recalcula_el_coste_con_la_ejecucion_del_perfil():
    cost, reason = cost_per_trade_r(EVIDENCE, PROFILE_EXECUTION)

    assert reason == ""
    assert cost == pytest.approx(0.0729, rel=5e-3)
    assert cost != pytest.approx(EVIDENCE["cost_per_trade_r"])

    check = next(
        item
        for item in evaluate(EVIDENCE, execution=PROFILE_EXECUTION)["checks"]
        if item["name"] == "coste_por_operacion"
    )
    assert check["value"] == pytest.approx(cost)
    assert check["pass"] is True


def test_sin_modelo_de_ejecucion_el_coste_no_es_verificable():
    incomplete = {key: value for key, value in EVIDENCE.items() if key != "execution"}
    cost, reason = cost_per_trade_r(incomplete, PROFILE_EXECUTION)

    assert cost is None
    assert "no declara su modelo de ejecución" in reason

    check = next(
        item
        for item in evaluate(incomplete, execution=PROFILE_EXECUTION)["checks"]
        if item["name"] == "coste_por_operacion"
    )
    assert check["pass"] is False


def test_sin_perfil_el_coste_heredado_no_es_verificable():
    cost, reason = cost_per_trade_r(EVIDENCE, None)

    assert cost is None
    assert "perfil" in reason

    check = next(
        item for item in evaluate(EVIDENCE)["checks"] if item["name"] == "coste_por_operacion"
    )
    assert check["pass"] is False


def _model_cost(execution):
    return 2 * execution["commission_per_unit_side"] / execution["tick_value"]


def test_el_coste_por_unidad_de_stop_no_diverge_mas_de_dos_veces():
    research = _model_cost(RESEARCH_EXECUTION)
    profile = _model_cost(PROFILE_EXECUTION)

    assert max(research, profile) / min(research, profile) <= 2


# Corrida generada con config/okx-paper-regime.json sobre data/BTC_1m_2025.csv:
# tope de stop 40.000 tics, comisión 0,049 y tick_value 1e-5, corte 2026-01-01.
EVIDENCE_PAPER_REGIME = (
    Path(__file__).resolve().parents[1]
    / "data/research/promotion/reference-1m-paper-regime.json"
)


def test_el_paper_y_la_evidencia_no_divergen_mas_de_dos_veces():
    if not EVIDENCE_PAPER_REGIME.is_file():
        pytest.fail(
            "falta la evidencia de paridad: "
            "data/research/promotion/reference-1m-paper-regime.json"
        )
    evidence = json.loads(EVIDENCE_PAPER_REGIME.read_text(encoding="utf-8"))
    execution = evidence["execution"]
    assert execution["commission_per_unit_side"] == pytest.approx(
        PROFILE_EXECUTION["commission_per_unit_side"]
    )
    assert execution["tick_value"] == pytest.approx(PROFILE_EXECUTION["tick_value"])
    # Sin presupuesto el stop implícito no se puede reconstruir; con menos de
    # 100 operaciones fuera de muestra la corrida no sirve como evidencia.
    assert evidence["risk_budget"] > 0
    assert evidence["split"]["out_of_sample"]["trades"] >= 100

    research, reason = cost_per_trade_r(evidence, PROFILE_EXECUTION)
    assert reason == ""
    # El comparable correcto es el ponderado de las 13 operaciones del paper
    # (0,3163 R), no el 0,2647 R de un único trade. El simple (0,3318 R) queda
    # como distribución y no se usa aquí. El umbral 2× no se toca.
    paper = PAPER_WEIGHTED_COST
    ratio = max(paper, research) / min(paper, research)

    assert ratio <= 2, (
        f"la divergencia ponderada es {ratio:.2f}×; falta evidencia de research "
        "en el régimen de stop del paper"
    )
