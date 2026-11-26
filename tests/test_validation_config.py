"""La config de validación conserva la estrategia y quita el freno que trunca el OOS."""
import json
from pathlib import Path

import pytest

from server.backtest import profile_fingerprint, research_fingerprint
from server.config import load_settings

ROOT = Path(__file__).resolve().parents[1]


def test_la_config_de_validacion_quita_el_freno_y_conserva_lo_demas():
    settings = load_settings(ROOT / "config/okx-validation.json")

    assert settings.strategy.id == "reference"
    assert settings.strategy.params["fast"] == 7
    assert settings.strategy.params["slow"] == 21
    assert settings.execution.commission_per_unit_side == 0.049
    assert settings.risk.soft_brakes is False
    assert settings.risk.max_drawdown_pct >= 100


def test_el_tope_de_operaciones_es_un_freno_y_no_muerde_en_la_referencia():
    """El tope es freno, no investigación, y la corrida de referencia lo confirma.

    Si mañana se baja a 1-2 ops/día, la muestra OOS se recortaría en silencio:
    este test es el aviso. No fija el valor (el perfil manda), exige que no
    muerda en la evidencia citada.
    """
    valid = load_settings(ROOT / "config/okx-validation.json")
    apretado = valid.model_copy(deep=True)
    apretado.risk.max_trades_per_day = 1

    # Cambiar el tope no cambia qué se mide, solo cuánto se arriesga/opera.
    assert research_fingerprint(apretado) == research_fingerprint(valid)
    assert profile_fingerprint(apretado) != profile_fingerprint(valid)

    evidence = ROOT / "data/research/promotion/profile-15m-2025-2026-years.json"
    if not evidence.is_file():
        pytest.skip("falta la evidencia de referencia en data/research/promotion")
    report = json.loads(evidence.read_text(encoding="utf-8"))
    assert report["trades_at_cap"] == 0


def test_la_config_de_validacion_solo_cambia_el_freno():
    """Si el perfil vivo cambia, la validación debe actualizarse con él."""
    live = load_settings(ROOT / "profiles/okx/config.json")
    valid = load_settings(ROOT / "config/okx-validation.json")

    assert valid.strategy == live.strategy
    assert valid.execution == live.execution
    assert valid.risk.initial_capital == live.risk.initial_capital

    live_risk = live.risk.model_dump()
    valid_risk = valid.risk.model_dump()
    changed = {key for key, value in live_risk.items() if valid_risk.get(key) != value}
    assert changed == {"max_drawdown_pct", "soft_brakes"}


def test_el_perfil_vivo_no_infiere_un_contract_size_ambiguo():
    from server.paper import _profile_contract_size

    live = load_settings(ROOT / "profiles/okx/config.json")
    instrument = live.instruments.by_symbol(live.instruments.primary)
    assert instrument.lot_size == 1
    assert instrument.min_notional is None
    assert instrument.contract_size is None
    assert _profile_contract_size(ROOT / "profiles/okx") is None
