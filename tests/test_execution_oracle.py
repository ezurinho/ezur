from __future__ import annotations

from datetime import timedelta

import pytest

from server.config import Settings
from server.execution import ExecutionEngine
from server.models import RiskDecision
from server.strategy.base import Signal
from tests.conftest import NOW, make_bar


def _engine(*, slippage: int = 0, commission: float = 0.0, model: str = "next_open") -> ExecutionEngine:
    settings = Settings()
    settings.execution.slippage_ticks = slippage
    settings.execution.max_slippage_ticks = slippage
    settings.execution.commission_per_unit_side = commission
    settings.execution.fill_model = model
    return ExecutionEngine(
        settings.execution,
        {item.symbol: item for item in settings.instruments.items},
    )


def _arm(engine: ExecutionEngine, *, side: str = "long", stop: float = 99.5, target: float = 102.25) -> None:
    signal = Signal(key=f"oracle-{side}", side=side, reason="oracle", ts=NOW, stop_price=stop, target_price=target)
    engine.arm(RiskDecision(approved=True, code="approved", units=5, risk_per_unit=0.25), signal, "PRIMARY", 100.0, NOW)


def _trade(engine: ExecutionEngine, bars: list[dict]):
    events = []
    for index, bar in enumerate(bars):
        events.extend(engine.on_bar({"PRIMARY": make_bar(t=NOW + timedelta(minutes=index), **bar)}))
    return next((event.trade for event in reversed(events) if event.trade is not None), None), events


@pytest.mark.parametrize(
    ("side", "second", "want_entry", "want_exit", "want_pnl", "want_reason"),
    [
        ("long", {"o": 101.0, "h": 103.0, "l": 100.8}, 100.0, 102.25, 22.5, "target"),
        ("long", {"o": 98.0, "h": 99.4, "l": 97.5}, 100.25, 97.75, -25.0, "stop"),
        ("short", {"o": 102.0, "h": 102.5, "l": 100.6}, 99.75, 102.25, -25.0, "stop"),
        ("short", {"o": 96.0, "h": 96.5, "l": 95.0}, 100.0, 97.75, 22.5, "target"),
        ("long", {"o": 100.5, "h": 103.0, "l": 99.0}, 100.0, 99.5, -5.0, "stop"),
        ("long", {"o": 103.0, "h": 104.0, "l": 100.8}, 100.0, 102.25, 22.5, "target"),
    ],
)
def test_fill_oracle_matches_hand_calculated_pnl(side, second, want_entry, want_exit, want_pnl, want_reason):
    engine = _engine(slippage=1 if second["o"] in {98.0, 102.0} else 0)
    _arm(engine, side=side, stop=100.5 if side == "short" else 99.5, target=97.75 if side == "short" else 102.25)
    trade, _ = _trade(
        engine,
        [
            {"o": 100.0, "h": 100.2 if side == "short" else 100.4, "l": 99.8},
            second,
        ],
    )
    assert trade is not None
    assert trade.entry_price == pytest.approx(want_entry)
    assert trade.exit_price == pytest.approx(want_exit)
    assert trade.pnl_net == pytest.approx(want_pnl)
    assert trade.exit_reason == want_reason


def test_entry_gap_oracle_rejects_instead_of_booking_a_profit():
    engine = _engine()
    _arm(engine)
    trade, events = _trade(engine, [{"o": 99.0, "h": 99.4, "l": 98.6}])
    assert trade is None
    assert engine.position is None
    assert [event.reason for event in events] == ["gap_through_stop"]


def test_commission_oracle_subtracts_both_sides():
    engine = _engine(commission=0.62)
    _arm(engine)
    trade, _ = _trade(
        engine,
        [
            {"o": 100.0, "h": 100.4, "l": 99.8},
            {"o": 101.0, "h": 103.0, "l": 100.8},
        ],
    )
    assert trade is not None
    assert trade.pnl_gross == pytest.approx(22.5)
    assert trade.fees == pytest.approx(6.2)
    assert trade.pnl_net == pytest.approx(16.3)


def test_manual_close_oracle_applies_adverse_slippage():
    engine = _engine(slippage=1)
    _arm(engine)
    engine.on_bar({"PRIMARY": make_bar(o=100.0, h=100.4, l=99.8)})
    trade = engine.close("manual", when=NOW + timedelta(minutes=1))
    assert trade is not None
    # Entrada y salida pagan el mismo tick adverso: 100.25 -> 100.25.
    assert trade.exit_price == pytest.approx(100.25)
    assert trade.pnl_net == pytest.approx(0.0)


def test_signal_price_oracle_degrades_when_pre_entry_stop_is_unknown():
    engine = _engine(model="signal_price")
    _arm(engine)
    trade, events = _trade(engine, [{"o": 100.6, "h": 101.0, "l": 99.0}])
    assert trade is not None
    assert trade.entry_price == pytest.approx(100.6)
    assert trade.exit_price == pytest.approx(99.5)
    assert trade.pnl_net == pytest.approx(-11.0)
    assert events[0].diagnostics["fill_fallback"] == "pre_entry_stop_unknown"


def test_signal_price_oracle_rejects_a_target_reached_before_entry():
    engine = _engine(model="signal_price")
    signal = Signal(
        key="oracle-target-before-entry",
        side="long",
        reason="oracle",
        ts=NOW,
        stop_price=99.5,
        target_price=101.0,
    )
    engine.arm(
        RiskDecision(approved=True, code="approved", units=5, risk_per_unit=0.25),
        signal,
        "PRIMARY",
        100.6,
        NOW,
    )
    trade, events = _trade(engine, [{"o": 101.0, "h": 101.5, "l": 100.5}])
    assert trade is None
    assert engine.position is None
    assert events[0].reason == "gap_through_target"


def test_signal_price_notional_uses_the_actual_long_fill():
    engine = _engine(model="signal_price")
    engine.instruments["PRIMARY"].contract_size = 1
    engine.instruments["PRIMARY"].min_notional = 496
    signal = Signal(key="notional-long", side="long", reason="t", ts=NOW, stop_price=98, target_price=101)
    engine.arm(RiskDecision(approved=True, units=5, risk_per_unit=1), signal, "PRIMARY", 99, NOW)
    trade, events = _trade(engine, [{"o": 100.0, "h": 100.5, "l": 98.9}])
    assert trade is None
    assert events[0].reason == "below_min_notional"


def test_signal_price_notional_does_not_reject_a_valid_long_fill():
    engine = _engine(model="signal_price")
    engine.instruments["PRIMARY"].contract_size = 1
    engine.instruments["PRIMARY"].min_notional = 496
    signal = Signal(key="notional-long-ok", side="long", reason="t", ts=NOW, stop_price=98, target_price=101)
    engine.arm(RiskDecision(approved=True, units=5, risk_per_unit=1), signal, "PRIMARY", 100, NOW)
    trade, events = _trade(engine, [{"o": 99.1, "h": 100.2, "l": 98.9}])
    assert trade is None
    assert engine.position is not None
    assert engine.position.entry_price == pytest.approx(100)
    assert all(event.reason != "below_min_notional" for event in events)


def test_signal_price_notional_uses_the_actual_short_fill():
    engine = _engine(model="signal_price")
    engine.instruments["PRIMARY"].contract_size = 1
    engine.instruments["PRIMARY"].min_notional = 505
    signal = Signal(key="notional-short", side="short", reason="t", ts=NOW, stop_price=102, target_price=99)
    engine.arm(RiskDecision(approved=True, units=5, risk_per_unit=1), signal, "PRIMARY", 100, NOW)
    trade, events = _trade(engine, [{"o": 101.1, "h": 101.2, "l": 99.8}])
    assert trade is None
    assert events[0].reason == "below_min_notional"


def test_target_gap_oracle_rejects_both_sides():
    for side, target, bar in (
        ("long", 101.0, {"o": 102.0, "h": 102.5, "l": 101.5}),
        ("short", 99.0, {"o": 98.0, "h": 98.5, "l": 97.5}),
    ):
        engine = _engine()
        _arm(engine, side=side, stop=100.5 if side == "short" else 99.5, target=target)
        trade, events = _trade(engine, [bar])
        assert trade is None
        assert events[0].reason == "gap_through_target"


def test_same_bar_target_oracle_is_counted():
    engine = _engine()
    _arm(engine)
    trade, events = _trade(engine, [{"o": 100.0, "h": 103.0, "l": 99.8}])
    assert trade is not None
    assert trade.exit_price == pytest.approx(102.25)
    assert trade.pnl_net == pytest.approx(22.5)
    assert events[-1].diagnostics["same_bar_exit"] is True
