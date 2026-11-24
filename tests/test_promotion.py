"""La puerta de promoción: cuatro criterios, todos obligatorios."""
from __future__ import annotations

import json

from server import promotion

EVIDENCE = {
    "split": {"out_of_sample": {"trades": 169, "profit_factor": 1.12}},
    "cost_per_trade_r": 0.09,
}
STRESS = {"split": {"out_of_sample": {"trades": 169, "profit_factor": 1.03}}}
CYCLE = {"pbo": {"pbo": 0.11}}


def test_una_configuracion_que_cumple_todo_se_promueve():
    verdict = promotion.evaluate(EVIDENCE, STRESS, CYCLE)

    assert verdict["passed"] is True
    assert verdict["reason"] == ""
    assert len(verdict["checks"]) == 5


def test_un_pf_fuera_de_muestra_bajo_la_tumba():
    verdict = promotion.evaluate(
        {**EVIDENCE, "split": {"out_of_sample": {"trades": 169, "profit_factor": 0.93}}},
        STRESS,
        CYCLE,
    )

    assert verdict["passed"] is False
    assert "pf_fuera_de_muestra" in verdict["failed"]


def test_pocas_operaciones_no_demuestran_nada():
    verdict = promotion.evaluate(
        {**EVIDENCE, "split": {"out_of_sample": {"trades": 40, "profit_factor": 1.4}}},
        STRESS,
        CYCLE,
    )

    assert "operaciones_fuera_de_muestra" in verdict["failed"]


def test_sin_corrida_con_coste_duplicado_no_hay_promocion():
    verdict = promotion.evaluate(EVIDENCE, None, CYCLE)

    assert verdict["passed"] is False
    assert "pf_con_coste_duplicado" in verdict["failed"]


def test_un_universo_que_es_ruido_no_se_promueve():
    verdict = promotion.evaluate(EVIDENCE, STRESS, {"pbo": {"pbo": 0.976}})

    assert "pbo_del_ciclo" in verdict["failed"]


def test_la_evidencia_tiene_que_ser_de_la_estrategia_configurada():
    verdict = promotion.evaluate(
        {**EVIDENCE, "strategy": {"id": "donchian", "version": "0.1.0"}},
        STRESS,
        CYCLE,
        {"id": "reference", "version": "0.1.0"},
    )

    assert verdict["passed"] is False
    assert verdict["failed"] == ["evidencia_de_la_estrategia"]
    assert "donchian@0.1.0" in verdict["reason"]
    assert "reference@0.1.0" in verdict["reason"]


def test_la_evidencia_de_la_estrategia_correcta_pasa():
    verdict = promotion.evaluate(
        {**EVIDENCE, "strategy": {"id": "reference", "version": "0.1.0"}},
        STRESS,
        CYCLE,
        {"id": "reference", "version": "0.1.0"},
    )

    assert verdict["passed"] is True
    assert len(verdict["checks"]) == 6


def test_el_informe_dice_de_que_corrida_sale_el_veredicto(tmp_path, capsys):
    evidencia = {
        **EVIDENCE,
        "strategy": {"id": "reference", "version": "0.1.0"},
        "dataset": "data/BTC_1h_binance.csv",
        "split": {"at": "2024-01-01T00:00:00+00:00", "out_of_sample": {"trades": 169, "profit_factor": 1.12}},
    }
    path = tmp_path / "bt.json"
    path.write_text(json.dumps(evidencia), encoding="utf-8")

    code = promotion.main(["--evidence", str(path), "--cycle", str(tmp_path / "no.json")])

    assert code == 1
    out = capsys.readouterr().out
    assert "evidencia: reference@0.1.0 · data/BTC_1h_binance.csv" in out
    assert "corte 2024-01-01T00:00:00+00:00" in out
    assert "169 ops OOS" in out


def test_el_cli_sale_con_uno_si_no_esta_promovida(tmp_path, capsys):
    evidencia = tmp_path / "bt.json"
    evidencia.write_text(json.dumps(EVIDENCE), encoding="utf-8")

    code = promotion.main(["--evidence", str(evidencia), "--cycle", str(tmp_path / "no.json")])

    assert code == 1
    assert "no promovida" in capsys.readouterr().out


def test_el_cli_promueve_con_las_tres_piezas(tmp_path, capsys):
    paths = {}
    for name, payload in (("bt", EVIDENCE), ("bt2x", STRESS), ("ciclo", CYCLE)):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = path

    code = promotion.main(
        ["--evidence", str(paths["bt"]), "--stress", str(paths["bt2x"]), "--cycle", str(paths["ciclo"])]
    )

    assert code == 0
    assert "promovida" in capsys.readouterr().out


def test_una_evidencia_con_texto_no_tumba_la_puerta():
    from server import promotion

    verdict = promotion.evaluate(
        {
            "strategy": {"id": "reference", "version": "1.0.0"},
            "split": {"out_of_sample": {"profit_factor": "n/a", "trades": "muchas"}},
            "cost_per_trade_r": "barato",
        },
        {"split": {"out_of_sample": {"profit_factor": "n/a"}}},
        {"pbo": {"pbo": "n/a"}},
        {"id": "reference", "version": "1.0.0"},
    )

    assert verdict["passed"] is False
    assert verdict["failed"] == [
        "pf_fuera_de_muestra",
        "operaciones_fuera_de_muestra",
        "coste_por_operacion",
        "pf_con_coste_duplicado",
        "pbo_del_ciclo",
    ]
    assert verdict["reason"] == "sin PF fuera de muestra, o por debajo de 1"
