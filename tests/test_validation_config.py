"""La config de validación conserva la estrategia y separa los frenos."""

from pathlib import Path
from types import SimpleNamespace

from server.backtest import profile_fingerprint, research_fingerprint
from server.config import load_settings
from server.promotion import cost_metrics, daily_cap_rejections

ROOT = Path(__file__).resolve().parents[1]

EXECUTION = {"commission_per_unit_side": 0.049, "tick_size": 0.01, "tick_value": 0.01}


def _trade(units: int) -> SimpleNamespace:
    return SimpleNamespace(entry_price=100.0, stop_price=99.0, units=units, fees=0.049)


def test_la_config_de_validacion_quita_el_freno_y_conserva_lo_demas():
    settings = load_settings(ROOT / "config/okx-validation.json")

    assert settings.strategy.id == "reference"
    assert settings.strategy.params["fast"] == 7
    assert settings.strategy.params["slow"] == 21
    assert settings.execution.commission_per_unit_side == 0.049
    assert settings.risk.soft_brakes is False
    assert settings.risk.max_drawdown_pct >= 100


def test_apretar_el_tope_de_operaciones_no_cambia_lo_que_se_mide():
    """El tope es freno, no investigación. No se fija su valor aquí.

    Si mañana se baja a 1-2 ops/día, la muestra OOS se recortaría en silencio:
    que el tope viva en el perfil y no en la huella de investigación es el
    aviso. El valor concreto lo manda el perfil y puede cambiar sin re-medir.
    """
    valid = load_settings(ROOT / "config/okx-validation.json")
    apretado = valid.model_copy(deep=True)
    apretado.risk.max_trades_per_day = 1

    assert research_fingerprint(apretado) == research_fingerprint(valid)
    assert profile_fingerprint(apretado) != profile_fingerprint(valid)


def test_el_tope_de_unidades_se_cuenta_con_trades_sinteticos():
    """`trades_at_cap` es el tope de tamaño (`max_units_per_trade`), no el diario.

    Se comprueba siempre, sin depender de artefactos en `data/`: dos trades y
    uno de ellos con las unidades al tope.
    """
    metrics = cost_metrics(
        [_trade(300), _trade(150)], EXECUTION, budget=300.0, max_units=300
    )

    assert metrics["trades"] == 2
    assert metrics["trades_at_cap"] == 1
    assert metrics["trades_at_units_cap"] == 1
    assert metrics["cap_rate"] == 0.5

    holgado = cost_metrics(
        [_trade(300), _trade(150)], EXECUTION, budget=300.0, max_units=1000
    )
    assert holgado["trades_at_units_cap"] == 0
    assert holgado["cap_rate"] == 0.0


def test_el_tope_diario_sale_de_los_rechazos_no_del_tamano():
    assert daily_cap_rejections(None) == 0
    assert daily_cap_rejections({"position_open": 12}) == 0
    assert daily_cap_rejections({"max_trades_reached": 7}) == 7


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
    assert _profile_contract_size(ROOT / "profiles" / "okx") is None
