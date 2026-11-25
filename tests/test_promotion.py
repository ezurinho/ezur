"""La puerta de promoción: cuatro criterios, todos obligatorios."""
from __future__ import annotations

import json

from server import promotion

EVIDENCE = {
    "dataset": "data/BTC_1h_binance.csv",
    "split": {"out_of_sample": {"trades": 169, "profit_factor": 1.12}},
    "cost_per_trade_r": 0.09,
}
STRESS = {"split": {"out_of_sample": {"trades": 169, "profit_factor": 1.03}}}
CYCLE = {"pbo": {"pbo": 0.11}, "universe": [{"timeframe": "1h"}]}


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
    verdict = promotion.evaluate(
        EVIDENCE, STRESS, {"pbo": {"pbo": 0.976}, "universe": [{"timeframe": "1h"}]}
    )

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


def test_la_evidencia_tiene_que_ser_de_la_configuracion_medida():
    verdict = promotion.evaluate(
        {
            **EVIDENCE,
            "strategy": {"id": "reference", "version": "0.1.0"},
            "config_hash": "aaaaaaaaaaaaaaaa",
        },
        STRESS,
        CYCLE,
        {"id": "reference", "version": "0.1.0"},
        "bbbbbbbbbbbbbbbb",
    )

    assert verdict["passed"] is False
    assert verdict["failed"] == ["evidencia_de_la_configuracion"]
    assert "aaaaaaaaaaaaaaaa" in verdict["reason"]


def test_la_configuracion_medida_promueve():
    verdict = promotion.evaluate(
        {
            **EVIDENCE,
            "strategy": {"id": "reference", "version": "0.1.0"},
            "config_hash": "aaaaaaaaaaaaaaaa",
        },
        STRESS,
        CYCLE,
        {"id": "reference", "version": "0.1.0"},
        "aaaaaaaaaaaaaaaa",
    )

    assert verdict["passed"] is True
    assert len(verdict["checks"]) == 7


def test_una_evidencia_sin_hash_no_se_puede_atribuir():
    verdict = promotion.evaluate(
        {**EVIDENCE, "strategy": {"id": "reference", "version": "0.1.0"}},
        STRESS,
        CYCLE,
        {"id": "reference", "version": "0.1.0"},
        "aaaaaaaaaaaaaaaa",
    )

    assert verdict["failed"] == ["evidencia_de_la_configuracion"]


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

def test_la_puerta_avisa_si_la_corrida_termino_antes_del_corte():
    from server import promotion

    verdict = promotion.evaluate(
        {
            "strategy": {"id": "reference", "version": "0.1.0"},
            "split": {"at": "2026-01-01T00:00:00+00:00", "out_of_sample": {"trades": 0}},
            "metrics": {"last_ts": "2025-02-04T00:50:00+00:00", "profit_factor": 0.0},
            "cost_per_trade_r": 0.05,
        },
        None,
        None,
        {"id": "reference", "version": "0.1.0"},
    )

    assert "corrida_completa_hasta_el_corte" in verdict["failed"]
    assert "antes del corte" in verdict["reason"]


def test_la_puerta_prioriza_la_muestra_cuando_es_numerica():
    from server import promotion

    verdict = promotion.evaluate(
        {
            "strategy": {"id": "reference", "version": "0.1.0"},
            "split": {
                "at": "2026-01-01T00:00:00+00:00",
                "out_of_sample": {"trades": 4, "profit_factor": 0.0},
            },
            "metrics": {"last_ts": "2026-01-11T08:00:00+00:00"},
            "cost_per_trade_r": 0.05,
        },
        None,
        None,
        {"id": "reference", "version": "0.1.0"},
    )

    assert "operaciones_fuera_de_muestra" in verdict["failed"]
    assert verdict["reason"] == "muestra fuera de muestra insuficiente: 4 < 100"


def test_la_puerta_no_usa_un_pbo_de_otro_marco():
    from server import promotion

    verdict = promotion.evaluate(
        {
            "strategy": {"id": "reference", "version": "0.1.0"},
            "dataset": "data/BTC_1h_binance.csv",
            "split": {
                "at": "2026-01-01T00:00:00+00:00",
                "out_of_sample": {
                    "trades": 200,
                    "profit_factor": 1.5,
                },
            },
            "metrics": {"last_ts": "2026-02-01T00:00:00+00:00"},
            "cost_per_trade_r": 0.05,
        },
        {"split": {"out_of_sample": {"profit_factor": 1.2}}},
        {"pbo": {"pbo": 0.01}, "universe": [{"timeframe": "1d"}]},
        {"id": "reference", "version": "0.1.0"},
    )

    assert verdict["passed"] is False
    assert "pbo_del_ciclo" in verdict["failed"]
    assert verdict["reason"] == "el ciclo mide 1d, no 1h: PBO no comparable"


def test_el_marco_del_dataset_se_lee_con_punto_o_guion_bajo():
    from server import promotion

    assert promotion._timeframe("data/BTC_1d.csv") == "1d"
    assert promotion._timeframe("data/BTC_1h_binance.csv") == "1h"
    assert promotion._timeframe("data/BTC_1m_2025.csv") == "1m"
    assert promotion._timeframe("data/sin_marco.csv") == ""


def test_la_puerta_no_acepta_un_ciclo_sin_marco():
    from server import promotion

    verdict = promotion.evaluate(EVIDENCE, STRESS, {"pbo": {"pbo": 0.01}})

    assert "pbo_del_ciclo" in verdict["failed"]
    assert verdict["reason"] == "el ciclo no declara marco: no se puede verificar el PBO"


def test_la_puerta_no_acepta_una_evidencia_sin_dataset():
    from server import promotion

    evidence = {key: value for key, value in EVIDENCE.items() if key != "dataset"}
    verdict = promotion.evaluate(evidence, STRESS, CYCLE)

    assert "pbo_del_ciclo" in verdict["failed"]
    assert "no declara dataset" in verdict["reason"]


def test_un_pf_con_coste_duplicado_bajo_lo_dice():
    from server import promotion

    verdict = promotion.evaluate(
        EVIDENCE, {"split": {"out_of_sample": {"profit_factor": 0.9}}}, CYCLE
    )

    assert verdict["failed"] == ["pf_con_coste_duplicado"]
    assert verdict["reason"] == "PF con coste duplicado 0.9 ≤ 1"


def test_un_pbo_no_comparable_se_muestra_como_guion():
    from server import promotion

    verdict = promotion.evaluate(
        {
            "strategy": {"id": "reference", "version": "0.1.0"},
            "dataset": "data/BTC_1h_binance.csv",
            "split": {
                "at": "2026-01-01T00:00:00+00:00",
                "out_of_sample": {"trades": 200, "profit_factor": 1.5},
            },
            "metrics": {"last_ts": "2026-02-01T00:00:00+00:00"},
            "cost_per_trade_r": 0.05,
        },
        {"split": {"out_of_sample": {"profit_factor": 1.2}}},
        {"pbo": {"pbo": 0.01}, "universe": [{"timeframe": "1d"}]},
        {"id": "reference", "version": "0.1.0"},
    )
    text = promotion.render(verdict)
    row = next(line for line in text.splitlines() if line.startswith("pbo_del_ciclo"))

    assert "—" in row
    assert "0.01" not in row
