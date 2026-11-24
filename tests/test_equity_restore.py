"""Al arrancar manda el libro: la copia en `kv` puede estar contaminada."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from server.config import Settings
from server.db import Store
from server.engine import TradingEngine
from server.models import TradeRecord

NOW = datetime.now(timezone.utc)


def _trade(pnl: float, key: str) -> TradeRecord:
    return TradeRecord(
        symbol="BTC",
        side="long",
        units=1,
        entry_price=100.0,
        exit_price=100.0 + pnl,
        opened_ts=NOW,
        closed_ts=NOW,
        pnl_gross=pnl,
        fees=0.0,
        pnl_net=pnl,
        signal_key=key,
    )


def test_la_equity_sale_del_libro_aunque_kv_diga_otra_cosa(tmp_path):
    store = Store(tmp_path / "libro.db")
    try:
        store.insert_trade(_trade(-100.0, "a"))
        store.insert_trade(_trade(40.0, "b"))
        store.kv_set("equity", 9_999.0)  # copia contaminada

        engine = TradingEngine(Settings(), store, feed=None)

        initial = Settings().risk.initial_capital
        assert engine.state.equity == pytest.approx(initial - 60.0)
    finally:
        store.close()


def test_sin_operaciones_la_equity_es_el_capital_inicial(tmp_path):
    store = Store(tmp_path / "vacio.db")
    try:
        store.kv_set("equity", 1.0)
        engine = TradingEngine(Settings(), store, feed=None)
        assert engine.state.equity == pytest.approx(Settings().risk.initial_capital)
    finally:
        store.close()


def test_el_pico_de_equity_sobrevive_al_reinicio(tmp_path):
    store = Store(tmp_path / "pico.db")
    try:
        store.insert_trade(_trade(-100.0, "a"))
        store.kv_set("peak_equity", 26_000.0)

        engine = TradingEngine(Settings(), store, feed=None)

        assert engine.peak_equity == pytest.approx(26_000.0)
    finally:
        store.close()


def test_el_pico_nunca_queda_por_debajo_de_la_equity(tmp_path):
    store = Store(tmp_path / "pico-bajo.db")
    try:
        store.insert_trade(_trade(-100.0, "a"))
        store.kv_set("peak_equity", 1.0)

        engine = TradingEngine(Settings(), store, feed=None)

        assert engine.peak_equity == pytest.approx(engine.state.equity)
    finally:
        store.close()

def test_sin_pico_guardado_el_pico_es_la_equity_si_ya_gano(tmp_path):
    store = Store(tmp_path / "pico-nuevo.db")
    try:
        store.insert_trade(_trade(5_000.0, "a"))

        engine = TradingEngine(Settings(), store, feed=None)

        assert engine.state.equity == pytest.approx(30_000.0)
        assert engine.peak_equity == pytest.approx(30_000.0)
    finally:
        store.close()
