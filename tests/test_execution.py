from __future__ import annotations

import pytest

from server.models import RiskDecision
from tests.conftest import NOW, make_bar


@pytest.fixture
def decision() -> RiskDecision:
    return RiskDecision(approved=True, code="approved", units=5, risk_per_unit=1.0)


def test_fill_at_next_open_with_bounded_slippage(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    assert engine.execution.position is not None
    assert engine.execution.position.entry_price == pytest.approx(100.25)


def test_bracket_copied_from_signal(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    position = engine.execution.position
    assert position.stop_price == 99.5
    assert position.target_price == 102.25


def test_target_exit(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=101.0, h=103.0, l=100.8)})
    assert events[-1].type == "exit"
    assert events[-1].reason == "target"
    assert events[-1].trade is not None
    assert events[-1].trade.exit_price == 102.25


def test_ambiguous_bar_resolves_stop_first(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=103.0, l=99.0)})
    assert events[-1].reason == "stop"
    assert events[-1].diagnostics["ambiguous_bar"] is True
    assert events[-1].trade is not None
    assert events[-1].trade.diagnostics["ambiguous_bar"] is True


def test_commission_applied_per_side(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    trade = engine.execution.close("manual", price=100.5, when=NOW)
    assert trade is not None
    assert trade.fees == pytest.approx(2 * 0.62 * decision.units)


def test_signal_is_executed_only_once(engine, decision, signal_long):
    first = engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    second = engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    assert first is not None
    assert second is None


def test_no_second_entry_with_open_position(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    other = signal_long.model_copy(update={"key": "another"})
    assert engine.execution.arm(decision, other, "PRIMARY", 100.0, NOW) is None


def test_unapproved_decision_arms_nothing(engine, signal_long):
    rejected = RiskDecision(approved=False, code="x", message="no")
    assert engine.execution.arm(rejected, signal_long, "PRIMARY", 100.0, NOW) is None
    assert engine.execution.pending_orders() == []


def test_cancel_all_clears_pending(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.cancel_all()
    assert engine.execution.pending_orders() == []


def test_slippage_is_capped_by_max_slippage_ticks(settings):
    from server.execution import ExecutionEngine
    from server.strategy.base import Signal

    settings.execution.slippage_ticks = 10
    settings.execution.max_slippage_ticks = 2
    engine = ExecutionEngine(
        settings.execution,
        {item.symbol: item for item in settings.instruments.items},
    )
    signal = Signal(key="cap", side="long", reason="t", ts=NOW, stop_price=99.5)
    engine.arm(
        RiskDecision(approved=True, units=1, risk_per_unit=1.0),
        signal,
        "PRIMARY",
        100.0,
        NOW,
    )
    engine.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    # 2 ticks * 0.25 = 0.50, not 10 ticks
    assert engine.position.entry_price == pytest.approx(100.5)


# --- fill models ----------------------------------------------------------
def _with_model(engine, model: str) -> None:
    from server.config import ExecutionConfig

    engine.execution.config = ExecutionConfig.model_validate(
        {**engine.execution.config.model_dump(), "fill_model": model}
    )


def test_intrabar_rejects_a_gap_through_the_stop(engine, decision, signal_long):
    _with_model(engine, "intrabar")
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    # Opens below the stop: entering here would be born stopped out.
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=99.0, h=99.4, l=98.6)})
    assert engine.execution.position is None
    assert [event.type for event in events] == ["cancel"]
    assert events[0].reason == "gap_through_stop"
    assert engine.execution.orders[-1].status == "rejected"


def test_entry_bar_can_kill_the_trade_and_says_so(engine, decision, signal_long):
    _with_model(engine, "intrabar")
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=100.4, l=99.2)})
    assert [event.type for event in events] == ["fill", "exit"]
    assert events[1].reason == "stop"
    assert events[1].diagnostics["same_bar_exit"] is True
    assert events[1].trade is not None
    assert engine.execution.position is None


def test_next_open_fills_through_a_gap_that_intrabar_would_refuse(
    engine, decision, signal_long
):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=99.0, h=99.4, l=98.6)})
    # next_open takes the bad fill and books the loss; intrabar refuses it.
    assert [event.type for event in events] == ["fill", "exit"]
    assert events[1].diagnostics["same_bar_exit"] is True
    assert events[0].price == pytest.approx(99.25)


def test_signal_price_fills_at_the_signal_when_the_bar_trades_through_it(
    engine, decision, signal_long
):
    _with_model(engine, "signal_price")
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=100.6, h=101.0, l=99.9)})
    assert events[0].type == "fill"
    assert events[0].reason == "signal_price"
    assert engine.execution.position.entry_price == pytest.approx(100.25)


def test_signal_price_falls_back_and_says_so(engine, decision, signal_long):
    _with_model(engine, "signal_price")
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=101.0, h=101.6, l=100.9)})
    assert events[0].reason == "next_open"
    assert events[0].diagnostics["fill_fallback"] == "outside_range"
    assert engine.execution.position.entry_price == pytest.approx(101.25)


def test_signal_price_gap_beyond_slippage_degrades_instead_of_lying(
    engine, decision, signal_long
):
    _with_model(engine, "signal_price")
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=100.2, h=101.0, l=100.1)})
    # 100.25 (signal + slippage) is inside the bar, so the good fill survives.
    assert events[0].reason == "signal_price"
