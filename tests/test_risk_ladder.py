"""Los frenos recortan tamaño en vez de cerrar la puerta, salvo el tope duro."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from server.config import InstrumentConfig, RiskConfig
from server.models import PortfolioState
from server.risk import RiskManager, _drawdown_size
from server.strategy.base import Signal

STAMP = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
PEAK = 25_200.0


def _signal() -> Signal:
    return Signal(key="k", side="long", ts=STAMP, stop_price=99.0, target_price=103.0)


def _instrument() -> InstrumentConfig:
    # riesgo por unidad = 1 tick de distancia / tick_size * tick_value = 1.0
    return InstrumentConfig(symbol="X", tick_size=0.01, tick_value=0.01)


def _config(**overrides) -> RiskConfig:
    base = dict(
        initial_capital=25_000.0,
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=3.0,
        max_drawdown_pct=5.0,
        max_trades_per_day=100,
        max_units_per_trade=100_000,
        max_stop_ticks=100_000,
        trade_window_start="00:00",
        trade_window_end="23:59",
        no_trade_after_consecutive_losses=3,
        loss_streak_cooldown_min=45,
        soft_brakes=True,
    )
    base.update(overrides)
    return RiskConfig(**base)


def _portfolio(equity: float, **overrides) -> PortfolioState:
    base = dict(equity=equity, peak_equity=PEAK, last_price=100.0, daily_pnl=0.0)
    base.update(overrides)
    return PortfolioState(**base)


def test_el_tamano_a_media_maquina_recorta_unidades():
    decision = RiskManager(_config()).evaluate(
        _signal(), _portfolio(PEAK * 0.95), _instrument()
    )

    assert decision.approved
    assert decision.code == "approved"
    assert decision.size_factor == pytest.approx(round(59 / 239, 4))
    assert decision.units < 240  # 240 sería el tamaño completo al 1 % de 24.000
    assert "tamaño al 25%" in decision.message


def test_sin_soft_brakes_el_mismo_drawdown_rechaza():
    decision = RiskManager(_config(soft_brakes=False)).evaluate(
        _signal(), _portfolio(PEAK * 0.95), _instrument()
    )

    assert not decision.approved
    assert decision.code == "max_drawdown_reached"


def test_el_tope_duro_sigue_parando():
    decision = RiskManager(_config()).evaluate(
        _signal(), _portfolio(PEAK * 0.90), _instrument()  # 10 % = 2x el límite
    )

    assert not decision.approved
    assert decision.code == "max_drawdown_reached"


def test_la_racha_de_perdidas_recorta_en_vez_de_bloquear():
    decision = RiskManager(_config()).evaluate(
        _signal(),
        _portfolio(PEAK, consecutive_losses=3, last_exit_ts=STAMP - timedelta(minutes=10)),
        _instrument(),
        clock=STAMP,
    )

    assert decision.approved
    assert decision.size_factor == pytest.approx(0.5)


def test_la_racha_sigue_bloqueando_sin_soft_brakes():
    decision = RiskManager(_config(soft_brakes=False)).evaluate(
        _signal(),
        _portfolio(PEAK, consecutive_losses=3, last_exit_ts=STAMP - timedelta(minutes=10)),
        _instrument(),
        clock=STAMP,
    )

    assert not decision.approved
    assert decision.code == "consecutive_losses"


def test_la_perdida_diaria_al_ochenta_recorta_y_al_limite_para():
    suave = RiskManager(_config()).evaluate(
        _signal(), _portfolio(PEAK, daily_pnl=-620.0), _instrument()
    )
    muro = RiskManager(_config()).evaluate(
        _signal(), _portfolio(PEAK, daily_pnl=-750.0), _instrument()
    )

    assert suave.approved and suave.size_factor <= 0.5
    assert not muro.approved and muro.code == "daily_loss_limit"


def test_la_escalera_de_drawdown_es_monotona():
    values = [_drawdown_size(pct, 5.0, 0.25) for pct in (0.0, 2.5, 3.75, 5.0, 8.0)]

    assert values[0] == 1.0
    assert values[1] == 1.0
    assert values[2] == pytest.approx(0.625)
    assert values[3] == 0.25
    assert values[4] == 0.25
    assert values == sorted(values, reverse=True)
