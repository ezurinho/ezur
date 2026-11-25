from __future__ import annotations

from datetime import timedelta

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
    # El objetivo es una orden limite: se cobra el precio, sin slippage.
    assert events[-1].trade.exit_price == 102.25
    assert "exit_slippage" not in events[-1].diagnostics


def test_an_explicit_exit_price_is_respected(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    trade = engine.execution.close("manual", price=100.5, when=NOW)
    assert trade is not None
    assert trade.exit_price == pytest.approx(100.5)
    assert "exit_slippage" not in trade.diagnostics


def test_a_market_close_pays_slippage(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    engine.execution.last_price = 100.5
    trade = engine.execution.close("manual", when=NOW)
    assert trade is not None
    assert trade.exit_price == pytest.approx(100.25)
    assert trade.diagnostics["exit_slippage"] == pytest.approx(0.25)


def test_open_pnl_charges_both_sides(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    position = engine.execution.position
    assert position is not None
    spec = engine.execution._instrument("PRIMARY")
    gross = (
        (100.5 - position.entry_price)
        / spec.tick_size
        * spec.tick_value
        * position.units
    )
    expected = (
        gross
        - position.entry_fees
        - engine.execution._fees("PRIMARY", position.units, 100.5)
    )
    assert engine.execution.open_pnl(position, 100.5) == pytest.approx(expected)
    assert engine.execution.open_pnl(position, position.entry_price) < 0


def test_ambiguous_bar_resolves_stop_first(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=103.0, l=99.0)})
    assert events[-1].reason == "stop"
    assert events[-1].diagnostics["ambiguous_bar"] is True
    assert events[-1].trade is not None
    assert events[-1].trade.diagnostics["ambiguous_bar"] is True


def test_stop_fills_at_the_open_when_the_bar_gaps_through_it(
    engine, decision, signal_long
):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=98.0, h=98.6, l=97.5)})
    assert events[-1].reason == "stop"
    assert events[-1].trade is not None
    # Stop en 99.5, apertura en 98.0, un tick de slippage: 97.75.
    assert events[-1].trade.exit_price == pytest.approx(97.75)
    assert events[-1].diagnostics["gap_through_stop"] is True
    assert events[-1].diagnostics["exit_slippage"] == pytest.approx(0.25)


def test_short_stop_fills_at_the_open_when_the_bar_gaps_through_it(engine, decision):
    from server.strategy.base import Signal

    signal = Signal(
        key="gap-short",
        side="short",
        reason="t",
        ts=NOW,
        stop_price=100.5,
        target_price=98.0,
    )
    engine.execution.arm(decision, signal, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=100.2, l=99.6)})
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=102.0, h=102.4, l=101.5)})
    assert events[-1].reason == "stop"
    assert events[-1].trade is not None
    # Stop en 100.5, apertura en 102.0, un tick en contra: 102.25.
    assert events[-1].trade.exit_price == pytest.approx(102.25)
    assert events[-1].diagnostics["gap_through_stop"] is True
    assert events[-1].diagnostics["exit_slippage"] == pytest.approx(0.25)


def test_commission_applied_per_side(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    trade = engine.execution.close("manual", price=100.5, when=NOW)
    assert trade is not None
    spec = engine.execution._instrument("PRIMARY")
    contract = spec.tick_value / spec.tick_size
    bps = 5.0 + 0.07
    expected = (
        2 * 0.62 * decision.units
        + decision.units * contract * (100.25 + 100.5) * bps * 1e-4
    )
    assert trade.fees == pytest.approx(expected)


def test_market_close_applies_adverse_slippage(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    trade = engine.execution.close("manual", when=NOW)
    assert trade is not None
    # El último precio es 100.5 y el cierre a mercado paga un tick en contra.
    assert trade.exit_price == pytest.approx(100.25)
    assert trade.diagnostics["exit_slippage"] == pytest.approx(0.25)


def test_commission_can_be_a_percentage_of_notional(engine, decision, signal_long):
    from server.config import ExecutionConfig

    engine.execution.config = ExecutionConfig.model_validate(
        {**engine.execution.config.model_dump(), "commission_pct_side": 0.001}
    )
    spec = engine.execution._instrument("PRIMARY")
    contract = spec.tick_value / spec.tick_size

    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=101.0, l=99.8)})
    trade = engine.execution.close("manual", price=100.5, when=NOW)

    assert trade is not None
    # 10 pb de 100.25 al entrar y de 100.50 al salir, más el coste de
    # bolsa/slippage del modelo de costes (5 pb + medio spread por lado).
    bps = 5.0 + 0.07
    expected = decision.units * contract * (100.25 + 100.5) * (0.001 + bps * 1e-4)
    assert trade.fees == pytest.approx(expected)


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
    assert engine.execution.cancel_all() == 1
    assert engine.execution.pending_orders() == []
    assert engine.execution.cancel_all() == 0


def test_pending_orders_expire_after_their_ttl(engine, decision, signal_long):
    order = engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    assert order is not None
    assert engine.execution.expire_pending(120, NOW + timedelta(seconds=121)) == 1
    assert order.status == "cancelled"
    assert engine.execution.pending_orders() == []
    assert engine.execution.expire_pending(120, NOW + timedelta(seconds=122)) == 0


def test_young_pending_orders_survive_expiry(engine, decision, signal_long):
    order = engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    assert order is not None
    assert engine.execution.expire_pending(120, NOW + timedelta(seconds=119)) == 0
    assert order.status == "pending"


def test_fill_revalidates_minimum_notional(settings, decision):
    from server.execution import ExecutionEngine
    from server.strategy.base import Signal

    instrument = settings.instruments.by_symbol(settings.instruments.primary)
    instrument.contract_size = 2
    instrument.min_notional = 1000
    settings.execution.slippage_ticks = 0
    engine = ExecutionEngine(
        settings.execution,
        {item.symbol: item for item in settings.instruments.items},
    )
    signal = Signal(key="min-notional", side="long", reason="t", ts=NOW, stop_price=99.0, target_price=101.0)
    engine.arm(decision, signal, "PRIMARY", 100.0, NOW)

    events = engine.on_bar({"PRIMARY": make_bar(o=99.25, h=99.5, l=99.0)})

    assert engine.position is None
    assert events[0].reason == "below_min_notional"
    assert engine.orders[-1].status == "rejected"


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


def test_entry_bar_can_kill_the_trade_and_says_so(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=100.4, l=99.2)})
    assert [event.type for event in events] == ["fill", "exit"]
    assert events[1].reason == "stop"
    assert events[1].diagnostics["same_bar_exit"] is True
    assert events[1].trade is not None
    assert engine.execution.position is None


@pytest.mark.parametrize("model", ["next_open", "signal_price"])
def test_every_fill_model_rejects_an_entry_gap_through_the_stop(engine, decision, signal_long, model):
    _with_model(engine, model)
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    # Entrar con el stop por encima de la entrada convertiría el gap en un
    # beneficio al cerrar inmediatamente: ningún modelo puede bookearlo.
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=99.0, h=99.4, l=98.6)})
    assert engine.execution.position is None
    assert [event.type for event in events] == ["cancel"]
    assert events[0].reason == "gap_through_stop"
    assert engine.execution.orders[-1].status == "rejected"


def test_later_stop_gap_fills_at_open_with_adverse_slippage(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=100.4, l=99.8)})
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=98.0, h=99.4, l=97.5)})
    trade = events[-1].trade
    assert trade is not None
    assert trade.exit_reason == "stop"
    assert trade.exit_price == pytest.approx(97.75)
    assert trade.diagnostics["gap_stop"] is True
    assert trade.pnl_net < 0


def test_short_stop_gap_fills_at_open_with_adverse_slippage(engine, decision):
    from server.strategy.base import Signal

    signal = Signal(key="short-gap", side="short", reason="t", ts=NOW, stop_price=100.5, target_price=97.75)
    engine.execution.arm(decision, signal, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=100.2, l=99.8)})
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=102.0, h=102.5, l=100.6)})
    trade = events[-1].trade
    assert trade is not None
    assert trade.exit_price == pytest.approx(102.25)
    assert trade.diagnostics["gap_stop"] is True
    assert trade.pnl_net < 0


def test_target_gap_fills_at_the_configured_target(engine, decision, signal_long):
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    engine.execution.on_bar({"PRIMARY": make_bar(o=100.0, h=100.4, l=99.8)})
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=103.0, h=104.0, l=100.8)})
    trade = events[-1].trade
    assert trade is not None
    assert trade.exit_reason == "target"
    # En un hueco no se inventa el mejor open: el objetivo límite cobra su nivel.
    assert trade.exit_price == pytest.approx(102.25)


def test_signal_price_degrades_when_pre_entry_stop_is_unknowable(engine, decision, signal_long):
    _with_model(engine, "signal_price")
    engine.execution.arm(decision, signal_long, "PRIMARY", 100.0, NOW)
    events = engine.execution.on_bar({"PRIMARY": make_bar(o=100.6, h=101.0, l=99.0)})
    assert events[0].reason == "next_open"
    assert events[0].diagnostics["fill_fallback"] == "pre_entry_stop_unknown"
    assert engine.execution.position is None
    assert events[-1].reason == "stop"


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
