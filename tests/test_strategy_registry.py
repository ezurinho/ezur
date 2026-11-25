"""El registro: plugins por id, specs por fichero, y nunca importar a mano."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from server.strategy import registry, spec_driven
from server.strategy.spec_schema import Params

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


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    """El registro es estado global: cada prueba lo deja como lo encontró."""
    monkeypatch.setattr(registry, "_SPECS_LOADED", True)
    monkeypatch.setattr(registry, "_SPEC_BUILDERS", dict(registry._SPEC_BUILDERS))
    monkeypatch.setattr(registry, "_SPEC_CACHE", dict(registry._SPEC_CACHE))


def _write_spec(directory: Path, name: str = "spec.json", **changes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps({**SPEC, **changes}), encoding="utf-8")
    return path


def test_los_plugins_estan_disponibles():
    assert {"null", "reference", "donchian", "fade", "trend"} <= set(registry.available())


def test_resolver_un_plugin_devuelve_su_estrategia():
    strategy = registry.resolve_strategy("reference", {"fast": 7, "slow": 21})

    assert strategy.id == "reference"
    assert strategy.params.fast == 7


def test_resolver_un_id_desconocido_lo_dice():
    with pytest.raises(KeyError, match="unknown strategy"):
        registry.resolve_strategy("no_existe")


def test_los_parametros_del_plugin_se_validan_en_el_registro():
    with pytest.raises(ValidationError):
        registry.resolve_strategy("reference", {"fast": 50, "slow": 10})


def test_el_esquema_de_un_plugin_expone_su_modelo():
    schema = registry.strategy_schema("reference")

    assert schema["type"] == "plugin"
    assert "fast" in schema["params_schema"]["properties"]


def test_el_esquema_de_un_id_desconocido_lo_dice():
    with pytest.raises(KeyError, match="unknown strategy"):
        registry.strategy_schema("no_existe")


def test_una_spec_registrada_se_resuelve_por_su_id(tmp_path):
    path = _write_spec(tmp_path / "specs")
    registry.register_spec("BTC-TREND-15M", path)

    strategy = registry.resolve_strategy("BTC-TREND-15M")

    assert isinstance(strategy, spec_driven.DonchianBreakoutStrategy)
    assert strategy.params.N == 20


def test_una_spec_registrada_acepta_parametros_que_la_sobrescriben(tmp_path):
    path = _write_spec(tmp_path / "specs")
    registry.register_spec("BTC-TREND-15M", path)

    strategy = registry.resolve_strategy("BTC-TREND-15M", {"N": 55})

    assert strategy.params.N == 55


def test_el_esquema_de_una_spec_incluye_la_spec_completa(tmp_path):
    path = _write_spec(tmp_path / "specs")
    registry.register_spec("BTC-TREND-15M", path)

    schema = registry.strategy_schema("BTC-TREND-15M")

    assert schema["type"] == "spec"
    assert schema["rule"] == "donchian_breakout"
    assert schema["full_spec"]["id"] == "BTC-TREND-15M"


def test_una_spec_cuyo_fichero_no_se_llama_como_el_id_sigue_cargando(tmp_path):
    path = _write_spec(tmp_path / "specs", name="otro-nombre.json")
    registry.register_spec("BTC-TREND-15M", path)

    strategy = registry.resolve_strategy("BTC-TREND-15M")

    assert isinstance(strategy, spec_driven.DonchianBreakoutStrategy)


def test_cargar_una_spec_que_no_esta_falla_con_su_ruta(tmp_path, monkeypatch):
    monkeypatch.setenv("EZUR_SPEC_DIR", str(tmp_path))

    with pytest.raises(KeyError, match="not found"):
        registry._load_spec_strategy("BTC-QUE-NO-EXISTE")


def test_una_regla_sin_implementacion_lo_dice():
    fake = SimpleNamespace(
        entry=SimpleNamespace(rule="magia"),
        params=Params(atr_k=1.0, tp_r=2.0),
        model_dump=lambda **kwargs: {},
    )

    with pytest.raises(KeyError, match="not implemented"):
        registry._build_strategy_from_spec(fake)


def test_un_spec_roto_no_tumba_el_registro(tmp_path, monkeypatch):
    broken = tmp_path / "roto.json"
    broken.write_text("{ no es json", encoding="utf-8")
    monkeypatch.setenv("EZUR_SPEC_DIR", str(tmp_path))
    monkeypatch.setattr(registry, "_SPECS_LOADED", False)

    registry._ensure_specs_loaded()

    assert registry._SPECS_LOADED is True


def test_el_registro_carga_las_specs_del_directorio(tmp_path, monkeypatch):
    _write_spec(tmp_path)
    monkeypatch.setenv("EZUR_SPEC_DIR", str(tmp_path))
    monkeypatch.setattr(registry, "_SPECS_LOADED", False)

    assert "BTC-TREND-15M" in registry.available()


def test_las_utilidades_de_fichero_delegan_en_el_esquema(tmp_path):
    path = _write_spec(tmp_path)

    assert registry.load_spec_file(path).id == "BTC-TREND-15M"
    assert registry.validate_spec_file(path) == []

    roto = tmp_path / "roto.json"
    roto.write_text(json.dumps({**SPEC, "family": "magia"}), encoding="utf-8")
    assert registry.validate_spec_file(roto)
