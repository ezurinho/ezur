"""Las órdenes pendientes no sobreviven al cierre de la sesión."""
from __future__ import annotations

from datetime import datetime, timezone

from server.config import Settings
from server.db import Store
from server.engine import TradingEngine
from server.models import Order, SessionInfo

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def _engine(tmp_path):
    store = Store(tmp_path / "ordenes.db")
    return TradingEngine(Settings(), store, feed=None)


def _order() -> Order:
    return Order(
        id="o1",
        symbol="BTC",
        side="long",
        units=1,
        price=100.0,
        created_ts=NOW,
        signal_key="senal",
    )


def _session(is_open: bool) -> SessionInfo:
    return SessionInfo(
        id="2026-11-24:demo",
        label="demo",
        is_open=is_open,
        open_ts=NOW,
        close_ts=NOW,
        phase="open" if is_open else "pre",
    )


def test_una_orden_pendiente_no_cruza_el_cierre(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.execution.orders.append(_order())

        engine._on_new_session(_session(False))

        assert engine.execution.has_pending() is False
        assert engine.execution.orders[0].status == "cancelled"
    finally:
        engine.store.close()


def test_una_orden_pendiente_sigue_si_la_sesion_esta_abierta(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.execution.orders.append(_order())

        engine._on_new_session(_session(True))

        assert engine.execution.has_pending() is True
        assert engine.execution.orders[0].status == "pending"
    finally:
        engine.store.close()
