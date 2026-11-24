"""La config de validación conserva la estrategia y quita el freno que trunca el OOS."""
from pathlib import Path

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
    assert settings.risk.max_trades_per_day == 8


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
