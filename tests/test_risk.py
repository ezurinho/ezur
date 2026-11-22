from __future__ import annotations

from datetime import timedelta

import pytest

from server.models import PortfolioState
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


def test_sizing_uses_instrument_spec(settings, signal_long):
    decision = _evaluate(settings, signal_long, _portfolio(settings))
    # 250 USD budget / 1.0 USD per unit = 250, capped at 5
    assert decision.approved is True
    assert decision.units == 5
    assert decision.risk_per_unit == pytest.approx(1.0)


def test_size_below_one_is_rejected(settings, signal_long):
    decision = _evaluate(settings, signal_long, _portfolio(settings, equity=50.0))
    assert decision.approved is False
    assert decision.code == "size_below_minimum"


def test_stop_too_wide_is_rejected(settings, signal_long):
    settings.risk.max_stop_ticks = 1
    decision = _evaluate(settings, signal_long, _portfolio(settings))
    assert decision.approved is False
    assert decision.code == "stop_too_wide"


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
