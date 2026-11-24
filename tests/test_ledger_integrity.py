"""El libro no puede contener operaciones imposibles ni contar una dos veces."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from server.db import Store
from server.engine import TradingEngine
from server.models import Bar, Position, Tick, TradeRecord
from server.strategy.registry import resolve_strategy

STAMP = datetime(2026, 11, 23, 4, 0, tzinfo=timezone.utc)


def _trade(closed: datetime, exit_price: float, signal_key: str = "") -> TradeRecord:
    return TradeRecord(
        symbol="PRIMARY",
        side="long",
        units=1,
        entry_price=100.0,
        exit_price=exit_price,
        stop_price=99.0,
        target_price=None,
        opened_ts=STAMP,
        closed_ts=closed,
        pnl_gross=exit_price - 100.0,
        fees=0.0,
        pnl_net=exit_price - 100.0,
        r_multiple=exit_price - 100.0,
        exit_reason="stop",
        mode="paper",
        signal_key=signal_key,
    )


def _engine(store: Store, settings) -> TradingEngine:
    return TradingEngine(settings, store, strategy=resolve_strategy("null", None), mode="paper")


def test_an_out_of_order_tick_cannot_close_a_live_position(store, settings):
    """Un backfill que repite una vela vieja no puede tocar una posición viva."""
    engine = _engine(store, settings)
    primary = settings.instruments.primary
    engine.execution.restore(
        Position(
            symbol=primary,
            side="long",
            units=1,
            entry_price=100.0,
            stop_price=99.0,
            target_price=102.0,
            opened_ts=STAMP,
            signal_key="2026-11-23:long:0400",
        )
    )
    engine.state.position = engine.execution.position
    engine._previous_tick_ts = STAMP + timedelta(minutes=10)

    stale = Tick(
        ts=STAMP + timedelta(minutes=5),
        bars={
            primary: Bar(
                t=STAMP + timedelta(minutes=5), o=100.0, h=100.0, l=90.0, c=95.0, v=1.0
            )
        },
    )
    engine._process(stale)

    assert engine.execution.position is not None
    assert store.count_trades() == 0


def test_close_persists_the_signal_key(store, settings):
    engine = _engine(store, settings)
    primary = settings.instruments.primary
    engine.execution.restore(
        Position(
            symbol=primary,
            side="long",
            units=1,
            entry_price=100.0,
            stop_price=99.0,
            target_price=102.0,
            opened_ts=STAMP,
            signal_key="2026-11-23:long:0400",
        )
    )

    trade = engine.execution.close("stop", 99.0, STAMP + timedelta(minutes=3))

    assert trade is not None
    assert trade.signal_key == "2026-11-23:long:0400"


def test_insert_rejects_a_close_before_the_open(store):
    impossible = _trade(closed=STAMP - timedelta(minutes=57), exit_price=99.0)

    with pytest.raises(ValueError, match="antes de abrir"):
        store.insert_trade_once(impossible)

    assert store.count_trades() == 0


def test_the_second_close_of_the_same_signal_is_dropped(store):
    """Misma señal, dos cierres distintos: el segundo no entra ni se suma."""
    first = _trade(closed=STAMP + timedelta(minutes=3), exit_price=99.0, signal_key="sig-1")
    second = _trade(closed=STAMP + timedelta(minutes=45), exit_price=98.0, signal_key="sig-1")

    first_id, first_new = store.insert_trade_once(first)
    second_id, second_new = store.insert_trade_once(second)

    assert first_new is True
    assert second_new is False
    assert second_id == first_id
    assert store.count_trades() == 1


def test_equity_matches_the_ledger(engine):
    engine._on_trade_closed(_trade(closed=STAMP + timedelta(minutes=3), exit_price=99.0))
    engine._on_trade_closed(_trade(closed=STAMP + timedelta(minutes=9), exit_price=101.0))

    trades = engine.store.list_trades(limit=10)
    assert len(trades) == 2
    assert engine.state.equity == pytest.approx(25000.0 + sum(row["pnl_net"] for row in trades))
    assert engine.state.day_stats.pnl == pytest.approx(sum(row["pnl_net"] for row in trades))
