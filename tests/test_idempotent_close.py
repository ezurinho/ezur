"""Un cierre repetido no puede contarse dos veces, ni en la fila ni en la cuenta."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from server.db import Store
from server.models import TradeRecord


def _trade(stamp: datetime | None = None) -> TradeRecord:
    opened = stamp or datetime(2026, 11, 23, 14, 0, tzinfo=timezone.utc)
    return TradeRecord(
        symbol="PRIMARY",
        side="long",
        units=1,
        entry_price=100.0,
        exit_price=99.0,
        stop_price=99.0,
        target_price=None,
        opened_ts=opened,
        closed_ts=opened + timedelta(minutes=5),
        pnl_gross=-1.0,
        fees=0.0,
        pnl_net=-1.0,
        r_multiple=-1.0,
        exit_reason="stop",
        mode="paper",
    )


def test_insert_trade_once_says_whether_the_row_was_new(tmp_path):
    store = Store(tmp_path / "once.db")
    try:
        trade = _trade()
        first_id, first_new = store.insert_trade_once(trade)
        second_id, second_new = store.insert_trade_once(trade)

        assert first_new is True
        assert second_new is False
        assert second_id == first_id
        assert store.count_trades() == 1
    finally:
        store.close()


def test_a_repeated_close_is_not_counted_twice_in_memory(engine):
    """La fila era única desde el índice; la equity no lo era."""
    trade = _trade()

    equity_before = engine.state.equity
    trades_before = engine.state.day_stats.trades

    engine._on_trade_closed(trade)
    equity_after = engine.state.equity
    assert equity_after == equity_before - 1.0
    assert engine.state.day_stats.trades == trades_before + 1

    engine._on_trade_closed(trade)

    assert engine.state.equity == equity_after
    assert engine.state.day_stats.trades == trades_before + 1
    assert engine.store.count_trades() == 1
    assert engine.state.position is None
