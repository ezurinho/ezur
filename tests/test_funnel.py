"""El embudo: cuántas ideas entraron y cuántas sobrevivieron, sin esconder el desgaste."""
from __future__ import annotations

import json

from server import funnel

ENTRIES = [
    {
        "verdict": "APROBADA",
        "dataset_id": "d1",
        "strategy": {"id": "reference", "version": "0.1.0"},
    },
    {
        "verdict": "RECHAZADA",
        "dataset_id": "d1",
        "strategy": {"id": "reference", "version": "0.1.0"},
    },
    {
        "verdict": "INCONCLUSO",
        "dataset_id": "d2",
        "strategy": {"id": "donchian", "version": "0.1.0"},
    },
    {"verdict": "", "dataset_id": None, "strategy": "suelta"},
]


def test_el_embudo_cuenta_cada_etapa():
    report = funnel.build_funnel(ENTRIES)

    assert report["stages"] == {
        "experiments": 4,
        "strategies": 3,
        "datasets": 2,
        "rejected": 1,
        "inconclusive": 1,
        "approved": 1,
    }
    assert report["verdicts"] == {"APROBADA": 1, "RECHAZADA": 1, "INCONCLUSO": 1, "": 1}
    assert report["survival_rate"] == 0.25


def test_el_embudo_agrupa_por_estrategia():
    report = funnel.build_funnel(ENTRIES)

    assert report["by_strategy"]["reference@0.1.0"] == {
        "experiments": 2,
        "verdicts": {"APROBADA": 1, "RECHAZADA": 1},
    }
    assert report["by_strategy"]["suelta"]["experiments"] == 1


def test_un_embudo_vacio_no_divide_por_cero():
    report = funnel.build_funnel([])

    assert report["stages"]["experiments"] == 0
    assert report["survival_rate"] == 0.0
    assert report["by_strategy"] == {}


def test_el_formato_nombra_las_etapas_y_las_estrategias():
    text = funnel.format_funnel(funnel.build_funnel(ENTRIES))

    assert "Embudo de evaluación" in text
    assert "Experimentos registrados" in text
    assert "25.0%" in text
    assert "reference@0.1.0: 2 experimento(s)" in text


def test_un_ledger_que_no_existe_da_un_embudo_vacio(tmp_path):
    report = funnel.load_funnel(tmp_path / "no-existe.jsonl")

    assert report["stages"]["experiments"] == 0


def test_la_cli_imprime_el_texto_por_defecto(tmp_path, capsys):
    code = funnel.main(["--ledger", str(tmp_path / "no-existe.jsonl")])

    out = capsys.readouterr().out
    assert code == 0
    assert "Tasa de supervivencia" in out


def test_la_cli_imprime_json_si_se_pide(tmp_path, capsys):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        "\n".join(
            json.dumps(
                {"verdict": entry["verdict"], "strategy": {"id": "x", "version": "1"}}
            )
            for entry in ENTRIES
        )
        + "\n",
        encoding="utf-8",
    )

    code = funnel.main(["--ledger", str(ledger), "--json"])

    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["stages"]["experiments"] == 4
