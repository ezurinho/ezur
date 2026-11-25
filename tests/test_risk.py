from __future__ import annotations

from datetime import timedelta

import pytest

from datetime import datetime, timezone

from server.config import RiskConfig
from server.models import PortfolioState
from server.strategy.base import Signal
from server.risk import RiskManager
from tests.conftest import NOW


def _portfolio(settings, **overrides) -> PortfolioState:
    payload = dict(
        equity=25000.0,
        last_price=100.0,
        daily_pnl=0.0,
        daily_trades=0,
        consecutive_losses=0,
        emergency=False,
        has_open_position=False,
        has_pending_order=False,
    )
    payload.update(overrides)
    return PortfolioState(**payload)


def _evaluate(settings, signal, portfolio, clock=None):
    manager = RiskManager(settings.risk)
    instrument = settings.instruments.by_symbol(settings.instruments.primary)
    return manager.evaluate(
        signal,
        portfolio,
        instrument,
        clock=clock or NOW,
        timezone_name=settings.instruments.template_for(instrument.symbol).timezone,
    )


@pytest.mark.parametrize(
    "portfolio_kwargs,expected",
    [
        ({"emergency": True}, "emergency_active"),
        ({"has_open_position": True}, "position_open"),
        ({"has_pending_order": True}, "order_pending"),
        ({"daily_trades": 3}, "max_trades_reached"),
        ({"consecutive_losses": 3, "daily_trades": 0}, "consecutive_losses"),
        ({"daily_pnl": -800.0}, "daily_loss_limit"),
        ({"last_price": None}, "no_price"),
    ],
)
def test_rejection_codes(settings, signal_long, portfolio_kwargs, expected):
    settings.risk.no_trade_after_consecutive_losses = 3
    decision = _evaluate(settings, signal_long, _portfolio(settings, **portfolio_kwargs))
    assert decision.approved is False
    assert decision.code == expected


def test_el_peaje_de_ida_y_vuelta_no_puede_comerse_el_riesgo(settings, signal_long):
    settings.risk.max_cost_r = 0.25
    manager = RiskManager(settings.risk)
    instrument = settings.instruments.by_symbol(settings.instruments.primary)

    def decide(fee_per_unit: float):
        return manager.evaluate(
            signal_long,
            _portfolio(settings),
            instrument,
            clock=NOW,
            timezone_name=settings.instruments.template_for(instrument.symbol).timezone,
            fee_per_unit=fee_per_unit,
        )

    # El stop arriesga 1,0 por unidad: 0,20 R de peaje cabe, 0,30 R no.
    assert decide(0.20).approved is True
    rejected = decide(0.30)
    assert rejected.approved is False
    assert rejected.code == "cost_above_budget"
    assert "0.300 R" in rejected.message


def test_el_tope_de_coste_se_puede_apagar(settings, signal_long):
    decision = RiskManager(settings.risk).evaluate(
        signal_long,
        _portfolio(settings),
        settings.instruments.by_symbol(settings.instruments.primary),
        clock=NOW,
        timezone_name="UTC",
        fee_per_unit=10.0,
    )

    assert decision.approved is True


def test_sizing_uses_instrument_spec(settings, signal_long):
    decision = _evaluate(settings, signal_long, _portfolio(settings))
    # 250 USD budget / 1.0 USD per unit = 250, capped at 5
    assert decision.approved is True
    assert decision.units == 5
    assert decision.risk_per_unit == pytest.approx(1.0)
    assert decision.risk_budget == pytest.approx(250.0)


def test_size_below_one_is_rejected(settings, signal_long):
    decision = _evaluate(settings, signal_long, _portfolio(settings, equity=50.0))
    assert decision.approved is False
    assert decision.code == "size_below_minimum"


def test_units_round_down_to_the_instrument_lot(settings, signal_long):
    settings.instruments.by_symbol(settings.instruments.primary).lot_size = 2
    decision = _evaluate(settings, signal_long, _portfolio(settings))
    assert decision.approved is True
    assert decision.units == 4


def test_lot_larger_than_the_cap_is_rejected(settings, signal_long):
    settings.risk.max_units_per_trade = 3
    settings.instruments.by_symbol(settings.instruments.primary).lot_size = 5
    decision = _evaluate(settings, signal_long, _portfolio(settings))
    assert decision.approved is False
    assert decision.code == "size_below_minimum"


def test_min_notional_uses_the_rounded_lot_size(settings, signal_long):
    instrument = settings.instruments.by_symbol(settings.instruments.primary)
    instrument.lot_size = 2
    instrument.contract_size = 2
    instrument.min_notional = 900
    decision = _evaluate(settings, signal_long, _portfolio(settings))
    assert decision.approved is False
    assert decision.code == "below_min_notional"

    instrument.min_notional = 800
    decision = _evaluate(settings, signal_long, _portfolio(settings))
    assert decision.approved is True
    assert decision.units == 4


def test_size_factor_reports_the_realized_size_after_lot_rounding(settings, signal_long):
    settings.risk.soft_brakes = True
    settings.risk.no_trade_after_consecutive_losses = 3
    settings.instruments.by_symbol(settings.instruments.primary).lot_size = 2
    decision = _evaluate(
        settings,
        signal_long,
        _portfolio(settings, consecutive_losses=3),
    )
    assert decision.approved is True
    assert decision.units == 2
    assert decision.size_factor == pytest.approx(0.4)
    assert "40" in decision.message


def test_stop_too_wide_is_rejected(settings, signal_long):
    settings.risk.max_stop_ticks = 1
    decision = _evaluate(settings, signal_long, _portfolio(settings))
    assert decision.approved is False
    assert decision.code == "stop_too_wide"


def test_stop_too_tight_is_rejected(settings, signal_long):
    settings.risk.min_stop_ticks = 100
    decision = _evaluate(settings, signal_long, _portfolio(settings))
    assert decision.approved is False
    assert decision.code == "stop_too_tight"


def test_a_stop_above_the_minimum_is_approved(settings, signal_long):
    settings.risk.min_stop_ticks = 1
    decision = _evaluate(settings, signal_long, _portfolio(settings))
    assert decision.approved is True


def test_outside_trade_window_is_rejected(settings, signal_long):
    settings.risk.trade_window_start = "09:00"
    settings.risk.trade_window_end = "10:00"
    decision = _evaluate(settings, signal_long, _portfolio(settings))
    assert decision.approved is False
    assert decision.code == "outside_window"


def test_exclusion_window_is_half_open(settings, signal_long):
    # NOW is 15:00 UTC = 10:00 in the session timezone.
    settings.risk.entry_exclusion_start = "09:30"
    settings.risk.entry_exclusion_end = "10:30"
    inside = _evaluate(settings, signal_long, _portfolio(settings))
    assert inside.code == "excluded_window"

    # The end bound is exclusive: at 10:30 the entry is allowed again.
    settings.risk.entry_exclusion_end = "10:00"
    at_end = _evaluate(settings, signal_long, _portfolio(settings))
    assert at_end.approved is True


def test_cooldown_blocks_after_recent_exit(settings, signal_long):
    settings.risk.cooldown_minutes = 5
    portfolio = _portfolio(settings, last_exit_ts=NOW - timedelta(minutes=1))
    decision = _evaluate(settings, signal_long, portfolio)
    assert decision.approved is False
    assert decision.code == "cooldown_active"


def test_cooldown_expires(settings, signal_long):
    settings.risk.cooldown_minutes = 5
    portfolio = _portfolio(settings, last_exit_ts=NOW - timedelta(minutes=10))
    assert _evaluate(settings, signal_long, portfolio).approved is True


def test_daily_profit_limit_when_configured(settings, signal_long):
    settings.risk.max_daily_profit_pct = 1.0
    decision = _evaluate(settings, signal_long, _portfolio(settings, daily_pnl=300.0))
    assert decision.approved is False
    assert decision.code == "daily_profit_limit"


# --- trailing drawdown guard (lección de Freqtrade) ------------------------
def _drawdown_state(**kwargs):
    base = dict(equity=25000.0, peak_equity=25000.0, last_price=100.0)
    base.update(kwargs)
    return PortfolioState(**base)


def test_drawdown_guard_blocks_entries_below_the_peak(engine, signal_long):
    from server.config import RiskConfig

    engine.risk = engine.risk.__class__(
        RiskConfig.model_validate({**engine.risk.config.model_dump(), "max_drawdown_pct": 5.0})
    )
    spec = engine.settings.instruments.by_symbol("PRIMARY")
    decision = engine.risk.evaluate(
        signal_long, _drawdown_state(equity=23600.0), spec
    )
    assert decision.approved is False
    assert decision.code == "max_drawdown_reached"
    assert "drawdown" in decision.message


def test_drawdown_guard_allows_entries_inside_the_limit(engine, signal_long):
    from server.config import RiskConfig

    engine.risk = engine.risk.__class__(
        RiskConfig.model_validate({**engine.risk.config.model_dump(), "max_drawdown_pct": 5.0})
    )
    spec = engine.settings.instruments.by_symbol("PRIMARY")
    decision = engine.risk.evaluate(signal_long, _drawdown_state(equity=24000.0), spec)
    assert decision.code != "max_drawdown_reached"


def test_drawdown_guard_is_off_by_default(engine, signal_long):
    spec = engine.settings.instruments.by_symbol("PRIMARY")
    decision = engine.risk.evaluate(signal_long, _drawdown_state(equity=1000.0), spec)
    assert decision.code != "max_drawdown_reached"


def test_drawdown_measures_realised_equity_not_ratios(engine, signal_long):
    """Un pico alto con pérdidas pequeñas en R no debe bloquear igual que una caída real."""
    from server.config import RiskConfig

    engine.risk = engine.risk.__class__(
        RiskConfig.model_validate({**engine.risk.config.model_dump(), "max_drawdown_pct": 10.0})
    )
    spec = engine.settings.instruments.by_symbol("PRIMARY")
    decision = engine.risk.evaluate(signal_long, _drawdown_state(equity=24500.0), spec)
    assert decision.code != "max_drawdown_reached"


def _streak_portfolio(last_exit: datetime) -> PortfolioState:
    return PortfolioState(
        equity=10_000,
        peak_equity=10_000,
        consecutive_losses=5,
        last_exit_ts=last_exit,
        last_price=100.0,
    )


def _signal() -> Signal:
    return Signal(side="long", stop_price=99.0, target_price=103.0, reason="test")


def test_streak_block_lasts_until_session_end_by_default(settings, signal_long):
    settings.risk.no_trade_after_consecutive_losses = 3
    clock = NOW
    portfolio = _portfolio(
        settings,
        consecutive_losses=5,
        last_exit_ts=clock - timedelta(hours=3),
    )
    decision = _evaluate(settings, signal_long, portfolio, clock=clock)
    assert decision.code == "consecutive_losses"
    assert "min" not in decision.message


def test_streak_block_lifts_after_the_configured_cooldown(settings, signal_long):
    settings.risk.no_trade_after_consecutive_losses = 3
    settings.risk.loss_streak_cooldown_min = 30
    portfolio = _portfolio(
        settings,
        consecutive_losses=5,
        last_exit_ts=NOW - timedelta(minutes=10),
    )

    early = _evaluate(settings, signal_long, portfolio, clock=NOW)
    assert early.code == "consecutive_losses"
    assert "30 min" in early.message

    later = _evaluate(
        settings, signal_long, portfolio, clock=NOW + timedelta(minutes=21)
    )
    assert later.approved is True


def test_cooldown_without_a_previous_exit_still_blocks(settings, signal_long):
    settings.risk.no_trade_after_consecutive_losses = 3
    settings.risk.loss_streak_cooldown_min = 15
    portfolio = _portfolio(settings, consecutive_losses=4)
    portfolio.last_exit_ts = None
    decision = _evaluate(settings, signal_long, portfolio, clock=NOW)
    assert decision.code == "consecutive_losses"


def test_cooldown_out_of_range_is_rejected():
    with pytest.raises(ValueError):
        RiskConfig(loss_streak_cooldown_min=-1)
    with pytest.raises(ValueError):
        RiskConfig(loss_streak_cooldown_min=2000)


def test_min_stop_ticks_cannot_be_negative():
    with pytest.raises(ValueError):
        RiskConfig(min_stop_ticks=-1)


def test_last_exit_survives_a_restart(tmp_path, settings, signal_long):
    """El reinicio no puede dejar la pausa de racha sin fecha."""
    from datetime import datetime, timezone

    from server.db import Store
    from server.engine import TradingEngine

    store = Store(tmp_path / "restart.db")
    try:
        engine = TradingEngine(settings, store, strategy=None, mode="paper")
        stamp = datetime(2026, 11, 23, 10, 30, tzinfo=timezone.utc)
        engine.last_exit_ts = stamp
        engine._persist()

        reborn = TradingEngine(settings, store, strategy=None, mode="paper")
        assert reborn.last_exit_ts == stamp
    finally:
        store.close()


# --- geometría de la señal: un plugin con el signo cambiado ----------------
def _sided(side: str, stop: float, target: float | None) -> Signal:
    return Signal(
        key=f"geometry:{side}",
        side=side,  # type: ignore[arg-type]
        reason="test",
        ts=NOW,
        stop_price=stop,
        target_price=target,
    )


def test_a_long_stop_above_the_entry_is_rejected(settings):
    decision = _evaluate(settings, _sided("long", 101.0, 103.0), _portfolio(settings))
    assert decision.approved is False
    assert decision.code == "invalid_stop_side"


def test_a_short_stop_below_the_entry_is_rejected(settings):
    decision = _evaluate(settings, _sided("short", 99.0, 97.0), _portfolio(settings))
    assert decision.approved is False
    assert decision.code == "invalid_stop_side"


def test_a_target_behind_the_entry_is_rejected(settings):
    long_side = _evaluate(settings, _sided("long", 99.5, 99.0), _portfolio(settings))
    assert long_side.approved is False
    assert long_side.code == "invalid_target_side"

    short_side = _evaluate(settings, _sided("short", 100.5, 101.0), _portfolio(settings))
    assert short_side.approved is False
    assert short_side.code == "invalid_target_side"


def test_a_correct_short_is_approved(settings):
    decision = _evaluate(settings, _sided("short", 100.5, 99.0), _portfolio(settings))
    assert decision.approved is True
    assert decision.units >= 1


def test_a_signal_without_target_is_still_approved(settings):
    decision = _evaluate(settings, _sided("long", 99.5, None), _portfolio(settings))
    assert decision.approved is True

def test_el_cooldown_admite_un_cierre_sin_zona(settings, signal_long):
    settings.risk.cooldown_minutes = 5
    naive = (NOW - timedelta(minutes=1)).replace(tzinfo=None)

    decision = _evaluate(
        settings, signal_long, _portfolio(settings, last_exit_ts=naive)
    )

    assert decision.approved is False
    assert decision.code == "cooldown_active"


def test_el_cooldown_sin_zona_caduca(settings, signal_long):
    settings.risk.cooldown_minutes = 5
    naive = (NOW - timedelta(minutes=10)).replace(tzinfo=None)

    decision = _evaluate(
        settings, signal_long, _portfolio(settings, last_exit_ts=naive)
    )

    assert decision.approved is True


def test_la_pausa_por_racha_admite_un_cierre_sin_zona(settings, signal_long):
    settings.risk.no_trade_after_consecutive_losses = 3
    settings.risk.loss_streak_cooldown_min = 45
    naive = (NOW - timedelta(minutes=50)).replace(tzinfo=None)

    decision = _evaluate(
        settings,
        signal_long,
        _portfolio(settings, consecutive_losses=3, last_exit_ts=naive),
    )

    assert decision.approved is True
