"""El contrato de las specs: lo que se acepta y, sobre todo, lo que no."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from server.strategy import spec_schema
from server.strategy.spec_schema import (
    Params,
    Portfolio,
    StrategySpec,
    load_schema,
    load_spec,
    spec_path_display,
    validate_spec,
)

HYPOTHESIS = (
    "Una ruptura del canal de 20 velas en 15 m conserva inercia suficiente para "
    "pagar los costes del perpetual."
)

SPEC: dict = {
    "id": "BTC-TREND-15M",
    "name": "Ruptura de canal 15 m",
    "version": "1.0.0",
    "label": "trend_15m",
    "family": "trend",
    "hypothesis": HYPOTHESIS,
    "instrument": "BTCUSDT_PERP",
    "timeframe_signal": "15m",
    "data_requirements": {
        "datasets": ["klines_5m"],
        "min_coverage": "2020-01-01/2026-01-01",
        "integrity": {"gaps": 0, "duplicates": 0, "timezone": "UTC"},
    },
    "entry": {"rule": "donchian_breakout", "long": "cierre > canal", "short": "cierre < canal"},
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


def _broken(**changes) -> dict:
    document = copy.deepcopy(SPEC)
    document.update(changes)
    return document


# --- esquema JSON -----------------------------------------------------------


def test_el_esquema_publicado_es_json():
    schema = load_schema()

    assert schema["type"] == "object"
    assert "id" in schema["properties"]


def test_una_spec_completa_no_tiene_errores():
    assert validate_spec(copy.deepcopy(SPEC)) == []


@pytest.mark.parametrize(
    "changes,needle",
    [
        ({"family": "magia"}, "not in"),
        ({"id": "TREND-15M"}, "does not match"),
        ({"name": "ab"}, "shorter than"),
        ({"change": "x" * 401}, "longer than"),
        ({"entry": "ruptura"}, "expected object"),
        ({"exit": {"stop": "atr", "target": "tp", "time_stop_bars": 0}}, "< minimum"),
        ({"params": {"atr_k": 0.0, "tp_r": 2.0}}, "<= exclusiveMinimum"),
        ({"data_requirements": {"datasets": [], "min_coverage": "2020-01-01/2021-01-01", "integrity": {"gaps": 0, "duplicates": 0}}}, "fewer than"),
        ({"data_requirements": {"datasets": ["klines_5m", "klines_5m"], "min_coverage": "2020-01-01/2021-01-01", "integrity": {"gaps": 0, "duplicates": 0}}}, "not unique"),
        ({"hypothesis": HYPOTHESIS, "sobra": 1}, "unexpected property"),
    ],
)
def test_el_validador_nombra_el_campo_que_falla(changes, needle):
    errors = validate_spec(_broken(**changes))

    assert errors
    assert any(needle in error for error in errors)


def test_el_validador_exige_los_campos_obligatorios():
    document = copy.deepcopy(SPEC)
    document.pop("entry")

    errors = validate_spec(document)

    assert any("missing required property 'entry'" in error for error in errors)


def test_el_validador_ignora_los_propiedades_extra_donde_el_esquema_las_permite():
    document = copy.deepcopy(SPEC)
    document["params"] = {**document["params"], "futuro": 1.5}

    assert validate_spec(document) == []


# --- pydantic ---------------------------------------------------------------


def test_los_datasets_no_se_repiten():
    with pytest.raises(ValidationError, match="datasets must be unique"):
        spec_schema.DataRequirements(
            datasets=["klines_5m", "klines_5m"],
            min_coverage="2020-01-01/2021-01-01",
            integrity={"gaps": 0, "duplicates": 0},
        )


def test_la_cobertura_tiene_formato_de_rango():
    with pytest.raises(ValidationError, match="YYYY-MM-DD"):
        spec_schema.DataRequirements(
            datasets=["klines_5m"],
            min_coverage="2020",
            integrity={"gaps": 0, "duplicates": 0},
        )


def test_las_sesiones_van_en_hh_mm():
    with pytest.raises(ValidationError, match="HH:MM"):
        spec_schema.Entry(rule="orb_session", sessions=["9:30"])


def test_el_split_tiene_que_sumar_uno():
    with pytest.raises(ValidationError, match="sum to"):
        spec_schema.Validation(trials_declared=1, is_oos_split="0.6/0.2/0.1")
    with pytest.raises(ValidationError, match="three fractions"):
        spec_schema.Validation(trials_declared=1, is_oos_split="0.6/0.4")


def test_el_portafolio_explicito_exige_pesos():
    with pytest.raises(ValidationError, match="weight on every component"):
        Portfolio(
            components=[{"label": "uno"}, {"label": "dos"}],
            weighting="explicit",
            rationale="x" * 40,
        )


def test_una_spec_valida_produce_su_hash_estable():
    spec = StrategySpec.model_validate(SPEC)
    reordered = StrategySpec.model_validate(dict(reversed(list(SPEC.items()))))

    assert spec.spec_hash == reordered.spec_hash
    assert spec.spec_hash.startswith("sha256:")


@pytest.mark.parametrize(
    "params,rule,needle",
    [
        ({"atr_k": 1.0, "tp_r": 2.0}, "donchian_breakout", "requires params.N"),
        ({"atr_k": 1.0, "tp_r": 2.0, "N": 20}, "zscore_fade", None),
        ({"atr_k": 1.0, "tp_r": 2.0, "fast": 5}, "ema_state", "params.fast and params.slow"),
        ({"atr_k": 1.0, "tp_r": 2.0, "range_bars": 6}, "orb_session", "entry.sessions"),
    ],
)
def test_las_reglas_cruzan_sus_parametros(params, rule, needle):
    document = _broken(params=params, entry={"rule": rule, "sessions": []})
    spec = StrategySpec.model_validate(document)

    if needle is None:
        spec.validate_params_for_rule()
    else:
        with pytest.raises(ValueError, match=needle):
            spec.validate_params_for_rule()


# --- ficheros ---------------------------------------------------------------


def test_load_spec_valida_esquema_y_reglas(tmp_path):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(SPEC), encoding="utf-8")

    spec = load_spec(path)

    assert spec.id == "BTC-TREND-15M"
    assert spec.params.N == 20


def test_load_spec_explica_los_errores_del_esquema(tmp_path):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(_broken(family="magia")), encoding="utf-8")

    with pytest.raises(ValueError, match="JSON Schema"):
        load_spec(path)


def test_spec_path_display_prefiere_la_ruta_relativa(tmp_path):
    inside = tmp_path / "specs" / "uno.json"
    inside.parent.mkdir()
    inside.write_text("{}", encoding="utf-8")
    outside = Path(tmp_path.parent / "fuera.json")

    assert Path(spec_path_display(inside, tmp_path)).as_posix() == "specs/uno.json"
    assert spec_path_display(outside, tmp_path) == str(outside.resolve())


def test_params_admite_claves_futuras_pero_no_rompe_las_conocidas():
    with pytest.raises(ValidationError):
        Params(atr_k=1.0, tp_r=2.0, N=1)

    params = Params(atr_k=1.0, tp_r=2.0, N=20, futuro="valor")

    assert params.model_extra == {"futuro": "valor"}
