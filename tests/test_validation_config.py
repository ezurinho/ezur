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
