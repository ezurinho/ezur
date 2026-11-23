"""Un reinicio con backfill no puede cerrar una posición en el pasado."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from server.db import Store
from server.engine import TradingEngine
from server.market.feed import CSVFeed
from server.models import Bar, Position, Tick
from server.strategy.registry import resolve_strategy

from tests.test_api_backtest import _dataset


def _engine(tmp_path: Path, settings) -> tuple[TradingEngine, Store]:
    store = Store(tmp_path / "barrier.db")
    engine = TradingEngine(settings, store, strategy=resolve_strategy("null", None), mode="paper")
    return engine, store


def test_ticks_before_the_restored_position_are_skipped(tmp_path, settings):
    engine, store = _engine(tmp_path, settings)
    try:
        primary = settings.instruments.primary
        stamp = datetime(2026, 11, 23, 4, 0, tzinfo=timezone.utc)
        engine.execution.restore(
            Position(
                symbol=primary,
                side="long",
                units=1,
                entry_price=100.0,
                stop_price=99.0,
                target_price=102.0,
                opened_ts=stamp,
            )
        )
        engine.state.position = engine.execution.position
        engine._persist()

        reborn, reborn_store = _engine(tmp_path, settings)
        assert reborn._replay_barrier == stamp

        # vela anterior a la entrada: no debe cerrar nada
        older = Tick(
            ts=stamp - timedelta(minutes=5),
            bars={
                primary: Bar(
                    t=stamp - timedelta(minutes=5), o=98.0, h=98.5, l=97.5, c=98.0, v=1.0
                )
            },
        )
        reborn._process(older)
        assert reborn.state.position is not None
        assert reborn._replay_barrier == stamp

        # vela posterior: la barrera se levanta
        newer = Tick(
            ts=stamp + timedelta(minutes=1),
            bars={
                primary: Bar(
                    t=stamp + timedelta(minutes=1), o=100.0, h=100.5, l=99.5, c=100.0, v=1.0
                )
            },
        )
        reborn._process(newer)
        assert reborn._replay_barrier is None
        reborn_store.close()
    finally:
        store.close()


def test_a_duplicate_trade_is_not_inserted_twice(tmp_path, settings):
    from server.models import TradeRecord

    store = Store(tmp_path / "dupes.db")
    try:
        stamp = datetime(2026, 11, 23, 4, 0, tzinfo=timezone.utc)
        trade = TradeRecord(
            symbol="PRIMARY",
            side="long",
            units=1,
            entry_price=100.0,
            exit_price=99.0,
            stop_price=99.0,
            target_price=None,
            opened_ts=stamp,
            closed_ts=stamp + timedelta(minutes=3),
            pnl_gross=-1.0,
            fees=0.0,
            pnl_net=-1.0,
            r_multiple=-1.0,
            exit_reason="stop",
            mode="paper",
        )
        first = store.insert_trade(trade)
        second = store.insert_trade(trade)
        assert first > 0
        assert second == first
        assert len(store.list_trades(limit=10)) == 1
    finally:
        store.close()


def test_two_distinct_trades_on_the_same_bar_are_both_kept(tmp_path, settings):
    """La deduplicación no puede comerse una operación real: dos fills distintos
    en la misma vela son dos filas."""
    from server.models import TradeRecord

    store = Store(tmp_path / "distinct.db")
    try:
        stamp = datetime(2026, 11, 23, 4, 0, tzinfo=timezone.utc)
        def trade(exit_price: float) -> TradeRecord:
            return TradeRecord(
                symbol="PRIMARY",
                side="long",
                units=1,
                entry_price=100.0,
                exit_price=exit_price,
                stop_price=99.0,
                target_price=None,
                opened_ts=stamp,
                closed_ts=stamp + timedelta(minutes=3),
                pnl_gross=exit_price - 100.0,
                fees=0.0,
                pnl_net=exit_price - 100.0,
                r_multiple=exit_price - 100.0,
                exit_reason="stop",
                mode="paper",
            )

        first = store.insert_trade(trade(99.0))
        second = store.insert_trade(trade(98.5))
        assert first > 0 and second > 0
        assert second != first
        assert len(store.list_trades(limit=10)) == 2
    finally:
        store.close()


def test_migration_removes_a_preexisting_duplicate_and_logs_it(tmp_path, settings):
    """La base ya tenía la fila repetida: el índice no puede crearse sobre ella."""
    import sqlite3

    from server.migrations import apply_migrations

    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL, side TEXT NOT NULL, units INTEGER NOT NULL,
            entry_price REAL NOT NULL, exit_price REAL NOT NULL,
            stop_price REAL, target_price REAL,
            opened_ts TEXT NOT NULL, closed_ts TEXT NOT NULL,
            pnl_gross REAL NOT NULL DEFAULT 0, fees REAL NOT NULL DEFAULT 0,
            pnl_net REAL NOT NULL DEFAULT 0, r_multiple REAL NOT NULL DEFAULT 0,
            exit_reason TEXT NOT NULL DEFAULT '', mode TEXT NOT NULL DEFAULT 'paper',
            signal_key TEXT NOT NULL DEFAULT '', diagnostics TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    row = ("PRIMARY", "long", 1, 100.0, 99.0, None, None,
           "2026-11-23T01:30:00+00:00", "2026-11-23T02:27:00+00:00",
           -1.0, 0.0, -1.0, -1.0, "stop", "paper", "", "{}")
    conn.executemany(
        "INSERT INTO trades (symbol, side, units, entry_price, exit_price, stop_price,"
        " target_price, opened_ts, closed_ts, pnl_gross, fees, pnl_net, r_multiple,"
        " exit_reason, mode, signal_key, diagnostics) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [row, row],
    )
    conn.commit()

    apply_migrations(conn)
    assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 1
    event = conn.execute(
        "SELECT message FROM events WHERE category='maintenance'"
    ).fetchone()
    assert event and "duplicada" in event[0]
    conn.close()
