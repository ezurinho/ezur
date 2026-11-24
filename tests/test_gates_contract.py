"""El contrato de umbrales: un fichero, dos lectores, ningún número duplicado.

Estos tests no comprueban que las puertas midan bien (eso es `test_gates.py`):
comprueban que el bot las mide con los números de `config/gates.json` y no con
una copia que alguien olvidó actualizar.
"""

from __future__ import annotations

import json

import pytest

from server import gates


def _document() -> dict:
    return gates.load_document()


def test_el_fichero_existe_y_es_json():
    path = gates.gates_path()
    assert path.is_file(), f"falta el contrato de umbrales en {path}"
    document = _document()
    assert document["version"] == "1.0"
    assert "bot" in document and "research" in document


def test_la_seccion_del_bot_cuadra_con_el_modelo():
    """Ni falta un umbral que el código usa, ni sobra uno que nadie lee."""
    document = _document()
    fields = set(gates.GateThresholds.model_fields) - {"version"}
    assert set(document["bot"]) == fields


def test_la_seccion_de_investigacion_tiene_exactamente_lo_que_usa_el_runner():
    esperado = {
        "max_pbo",
        "min_dsr",
        "min_oos_t_stat",
        "min_oos_pf_ci_low",
        "min_trades",
        "min_wfa_trades_per_fold",
        "cost_stress_multiplier",
        "min_cost_stress_pf",
        "min_plateau_pf",
        "min_benchmark_alpha_ci_low",
        "max_unexplained_gaps",
    }
    assert set(_document()["research"]) == esperado


def test_los_umbrales_tienen_sentido():
    research = _document()["research"]
    assert 0 < research["max_pbo"] < 1
    assert 0 < research["min_dsr"] <= 1
    assert research["cost_stress_multiplier"] > 1
    assert research["min_trades"] > 0
    assert research["max_unexplained_gaps"] == 0


def test_el_bot_lee_el_fichero_y_no_una_copia(tmp_path, monkeypatch):
    """Si el fichero cambia, el veredicto cambia: es la prueba de que se lee."""
    document = json.loads(gates.gates_path().read_text(encoding="utf-8"))
    document["bot"]["min_profit_factor"] = 99.0
    document["bot"]["min_expectancy_r"] = 99.0
    copia = tmp_path / "gates.json"
    copia.write_text(json.dumps(document), encoding="utf-8")

    payload = {
        "closed": {
            "trades": 100,
            "profit_factor": 2.0,
            "expectancy_r": 0.5,
            "max_drawdown": 0.0,
            "max_loss_streak": 0,
            "pnl_without_top5": 100.0,
            "top5_share": 0.1,
            "expectancy_ci80_low": 0.2,
            "ambiguous_trades": 0,
        },
        "by_side": {"long": {"trades": 50}, "short": {"trades": 50}},
    }

    antes = gates.evaluate_gates(payload)
    assert "G5" not in antes.failed

    monkeypatch.setenv(gates.GATES_ENV, str(copia))
    despues = gates.evaluate_gates(payload)
    assert "G5" in despues.failed


def test_el_veredicto_lleva_la_version_del_fichero(monkeypatch):
    document = json.loads(gates.gates_path().read_text(encoding="utf-8"))
    document["version"] = "9.9"
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "gates.json"
        copia.write_text(json.dumps(document), encoding="utf-8")
        monkeypatch.setenv(gates.GATES_ENV, str(copia))
        report = gates.evaluate_gates({"closed": {}, "by_side": {}})
    assert report.thresholds_version == "9.9"


def test_el_motor_de_estrategias_apunta_al_mismo_fichero():
    """El otro lector: si su ruta canónica no existe, el contrato está roto."""
    import os
    from pathlib import Path

    research_home = Path(
        os.getenv("EZUR_RESEARCH_HOME")
        or Path.home() / ".deepai-code" / "scratch" / "2026-11-22-motor-ia-para-estrategias-btc-a2100b36"
    )
    research_loader = research_home / "runner" / "gates.py"
    if not research_loader.is_file():
        pytest.skip(f"motor de estrategias no encontrado en {research_loader}")

    source = research_loader.read_text(encoding="utf-8")
    assert "config" in source and "gates.json" in source
    assert "max_pbo" in source and "min_dsr" in source
